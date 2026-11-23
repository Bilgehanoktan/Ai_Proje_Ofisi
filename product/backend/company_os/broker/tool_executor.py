"""Rootless Linux-only, private-dir single-file executor candidate.

Engine has no writable access to this directory. Artifact reader and manifest
measurement are enrolled supervisor adapters, never engine-provided callbacks.
"""

import base64
import hashlib
import json
import os
import stat
import sys
from uuid import uuid4

from company_os.kernel.execution_protocol import Denied, exact


def replacement(raw, expected_artifact_digest):
    if (
        type(raw) is not bytes
        or len(raw) > 32768
        or hashlib.sha256(raw).hexdigest() != expected_artifact_digest
    ):
        raise Denied("IMMUTABLE_PATCH_ARTIFACT_DIGEST")

    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise Denied("DUPLICATE_PATCH_KEY")
            d[k] = v
        return d

    p = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    exact(p, {"format", "path", "base_content_digest", "replacement_base64"})
    if p["format"] != "company.replace-file/1" or p["path"] != "task_title.py":
        raise Denied("PILOT_REPLACEMENT_FORMAT")
    if (
        type(p["base_content_digest"]) is not str
        or len(p["base_content_digest"]) != 64
        or any(c not in "0123456789abcdef" for c in p["base_content_digest"])
    ):
        raise Denied("BASE_CONTENT_DIGEST")
    data = base64.b64decode(p["replacement_base64"], validate=True)
    if len(data) > 16384 or b"\0" in data:
        raise Denied("BOUNDED_TEXT_SOURCE_REQUIRED")
    data.decode("utf-8")
    return p["base_content_digest"], data


class ToolIntentJournal:
    def __init__(self, journal):
        self.journal = journal

    def reserve(self, identity, record):
        return self.journal.reserve("tool-consume", identity, record)


class LinuxSingleFileExecutor:
    def __init__(self, *, directory_fd, measure_head):
        if sys.platform != "linux" or os.geteuid() == 0:
            raise Denied("ROOTLESS_LINUX_REQUIRED")
        st = os.fstat(directory_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise Denied("PRIVATE_BROKER_DIRECTORY_REQUIRED")
        self.fd = os.dup(directory_fd)
        self.measure_head = measure_head

    def close(self):
        os.close(self.fd)

    def read(self):
        fd = os.open("task_title.py", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            st = os.fstat(fd)
            if (
                not stat.S_ISREG(st.st_mode)
                or st.st_nlink != 1
                or st.st_uid != os.getuid()
                or st.st_size > 16384
            ):
                raise Denied("BOUNDED_OWNED_SINGLE_LINK_FILE")
            raw = os.read(fd, 16385)
            if len(raw) > 16384:
                raise Denied("SOURCE_BYTE_LIMIT")
            end = os.fstat(fd)
            if (st.st_ino, st.st_size, st.st_mtime_ns) != (
                end.st_ino,
                end.st_size,
                end.st_mtime_ns,
            ):
                raise Denied("SOURCE_CHANGED_DURING_READ")
            return st, raw
        finally:
            os.close(fd)

    def execute(self, call, *, transaction):
        import fcntl

        # Broker directory and this lock file are inaccessible to the engine.
        lock = os.open(".r60.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
                raise Denied("PRIVATE_LOCK_FILE_REQUIRED")
            fcntl.flock(lock, fcntl.LOCK_EX)
            before, raw = self.read()
            base = hashlib.sha256(raw).hexdigest()
            head = self.measure_head()
            if call.tool_id == "workspace.read":
                if call.arguments.relative_path != "task_title.py":
                    raise Denied("PILOT_PATH_OUT_OF_SCOPE")
                # Read bytes go only to a trusted artifact writer via Kernel completion.
                return dict(
                    kind="READ",
                    head_digest=head,
                    content_base64=base64.b64encode(raw[: call.arguments.max_bytes]).decode(),
                    content_digest=base,
                    truncated=len(raw) > call.arguments.max_bytes,
                )
            if call.tool_id != "patch.apply":
                raise Denied("TOOL_NOT_IMPLEMENTED")
            if call.expected_source_digest != head:
                raise Denied("SOURCE_HEAD_CAS")
            artifact = transaction.read_patch(call.patch_artifact_id)
            expected, data = replacement(artifact["raw"], artifact["sha256"])
            if expected != base:
                raise Denied("SOURCE_CONTENT_CAS")
            temporary = ".r60-" + uuid4().hex + ".stage"
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=self.fd,
            )
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                current, current_raw = self.read()
                if (
                    current.st_ino != before.st_ino
                    or hashlib.sha256(current_raw).hexdigest() != base
                    or self.measure_head() != head
                ):
                    raise Denied("SOURCE_CHANGED_BEFORE_REPLACE")
                transaction.require_current()
                os.replace(temporary, "task_title.py", src_dir_fd=self.fd, dst_dir_fd=self.fd)
                os.fsync(self.fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=self.fd)
                except FileNotFoundError:
                    pass
            _, result = self.read()
            if result != data:
                raise Denied("RESULT_READBACK_MISMATCH")
            return dict(
                kind="PATCH",
                base_head=head,
                result_head=self.measure_head(),
                base_content_digest=base,
                result_content_digest=hashlib.sha256(data).hexdigest(),
                patch_digest=artifact["sha256"],
            )
        finally:
            os.close(lock)
