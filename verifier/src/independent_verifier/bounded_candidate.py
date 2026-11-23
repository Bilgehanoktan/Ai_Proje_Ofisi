"""Bounded local subprocess transport for SOURCE_TEST only.

This module provides no filesystem, identity, network or process-tree isolation.
Its output must never authorize a Kernel acceptance or an attestation.
"""

import os
import queue
import signal
import subprocess
import threading
import time


class CandidateProtocolError(ValueError):
    pass


class BoundedCandidate:
    def __init__(
        self, argv, *, cwd, env, timeout, max_line_bytes, max_output_bytes, max_stderr_bytes
    ):
        self.deadline = time.monotonic() + timeout
        self.line_cap = max_line_bytes
        self.output_cap = max_output_bytes
        self.stderr_cap = max_stderr_bytes
        self.pending = bytearray()
        self.events = queue.Queue(maxsize=32)
        self.stopped = threading.Event()
        self.failed = threading.Event()
        self.threads = []
        self.failure = None
        self.output_bytes = 0
        self.stderr_bytes = 0
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=(os.name == "posix"),
            close_fds=True,
        )
        for name, stream in [("stdout", self.proc.stdout), ("stderr", self.proc.stderr)]:
            thread = threading.Thread(target=self._read, args=(name, stream), daemon=True)
            self.threads.append(thread)
            thread.start()

    def _put(self, event):
        while not self.stopped.is_set():
            try:
                self.events.put(event, timeout=0.02)
                return
            except queue.Full:
                continue

    def _read(self, name, stream):
        try:
            while not self.stopped.is_set():
                chunk = os.read(stream.fileno(), 1024)
                if not chunk:
                    if name == "stdout":
                        self._put(("eof", b""))
                    return
                with self.lock:
                    self.output_bytes += len(chunk)
                    if name == "stderr":
                        self.stderr_bytes += len(chunk)
                    if self.output_bytes > self.output_cap or self.stderr_bytes > self.stderr_cap:
                        self.failure = "OUTPUT_BYTE_LIMIT_EXCEEDED"
                        self.failed.set()
                        return
                if name == "stdout":
                    self._put(("data", chunk))
        except OSError, ValueError:
            if not self.stopped.is_set():
                self.failure = "PIPE_READ_FAILED"
                self.failed.set()

    def _check(self, deadline):
        if self.failed.is_set():
            raise CandidateProtocolError(self.failure)
        if time.monotonic() >= min(deadline, self.deadline):
            raise TimeoutError("CANDIDATE_DEADLINE_EXCEEDED")

    def read_line(self, *, timeout, max_bytes=None):
        deadline = min(self.deadline, time.monotonic() + timeout)
        cap = self.line_cap if max_bytes is None else min(max_bytes, self.line_cap)
        while True:
            self._check(deadline)
            newline = self.pending.find(b"\n")
            length = newline + 1 if newline >= 0 else len(self.pending)
            if length > cap:
                raise CandidateProtocolError("LINE_BYTE_LIMIT_EXCEEDED")
            if newline >= 0:
                line = bytes(self.pending[: newline + 1])
                del self.pending[: newline + 1]
                return line
            try:
                kind, chunk = self.events.get(
                    timeout=min(0.02, max(0.001, deadline - time.monotonic()))
                )
            except queue.Empty:
                continue
            if kind == "eof":
                raise CandidateProtocolError("UNEXPECTED_CANDIDATE_EOF")
            self.pending.extend(chunk)

    def write_line(self, raw):
        self._check(self.deadline)
        if type(raw) is not bytes or len(raw) > self.line_cap or not raw.endswith(b"\n"):
            raise CandidateProtocolError("BOUNDED_REQUEST_REQUIRED")
        # At most one small request is outstanding. Isolate even its pipe write
        # from the supervisor deadline: an unresponsive child cannot block it.
        done = threading.Event()
        errors = []

        def write():
            try:
                view = memoryview(raw)
                while view:
                    n = os.write(self.proc.stdin.fileno(), view)
                    if n <= 0:
                        raise BrokenPipeError()
                    view = view[n:]
            except (OSError, ValueError) as exc:
                errors.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=write, daemon=True)
        self.threads.append(thread)
        thread.start()
        while not done.wait(0.02):
            self._check(self.deadline)
        self._check(self.deadline)
        if errors:
            raise CandidateProtocolError("CANDIDATE_PIPE_CLOSED")

    def finish(self):
        self.write_line(b"DONE\n")
        try:
            code = self.proc.wait(timeout=max(0.001, self.deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise TimeoutError("CANDIDATE_EXIT_DEADLINE") from None
        for thread in self.threads:
            thread.join(timeout=max(0, min(0.1, self.deadline - time.monotonic())))
        self._check(self.deadline)
        if code != 0:
            raise CandidateProtocolError("CANDIDATE_EXIT_NONZERO")
        if any(t.is_alive() for t in self.threads):
            raise CandidateProtocolError("CANDIDATE_PIPE_NOT_CLOSED")
        if self.pending:
            raise CandidateProtocolError("UNEXPECTED_TRAILING_OUTPUT")
        while not self.events.empty():
            kind, chunk = self.events.get_nowait()
            if kind == "data" and chunk:
                raise CandidateProtocolError("UNEXPECTED_TRAILING_OUTPUT")

    def close(self):
        self.stopped.set()
        try:
            if os.name == "posix":
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait(timeout=0.5)
        finally:
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                stream.close()
            for thread in self.threads:
                thread.join(timeout=0.1)
