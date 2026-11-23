"""Durable one-shot controller source. Import does not load C or launch OS work."""

import ctypes
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


class Denied(ValueError):
    pass


class UnknownLocal(RuntimeError):
    pass


FIELDS = {
    "capability_id",
    "tenant_id",
    "project_id",
    "task_id",
    "attempt_id",
    "fencing_epoch",
    "worker_id",
    "qualification_id",
    "binding_digest",
    "workspace_id",
    "head_digest",
    "host_id",
    "host_revision",
    "host_generation",
    "host_boot_id",
    "controller_id",
    "controller_generation",
    "process_id",
    "executable_digest",
    "argv",
    "reservation_id",
    "claims",
    "lease_policy_revision",
    "not_after_boottime_ns",
}


def decode_unique(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise Denied("DUPLICATE_JSON_KEY")
            d[k] = v
        return d

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(Denied("NONFINITE_JSON")),
    )


def validate_result(result, enrollment, boottime):
    if (
        result.get("spawn_permitted") is not True
        or result.get("release_only_after_commit") is not True
    ):
        raise Denied("NO_FRESH_COMMITTED_LAUNCH_PERMISSION")
    raw = result.get("tuple_raw")
    if type(raw) is not str or hashlib.sha256(raw.encode()).hexdigest() != result.get(
        "tuple_digest"
    ):
        raise Denied("TUPLE_DIGEST")
    t = decode_unique(raw)
    if (
        type(t) is not dict
        or set(t) != FIELDS
        or result.get("tuple") != t
        or result.get("capability_id") != t["capability_id"]
    ):
        raise Denied("EXACT_TUPLE_REQUIRED")
    for k in [
        "capability_id",
        "tenant_id",
        "project_id",
        "task_id",
        "attempt_id",
        "worker_id",
        "qualification_id",
        "workspace_id",
        "host_id",
        "host_boot_id",
        "controller_id",
        "process_id",
        "reservation_id",
    ]:
        if type(t[k]) is not str or not re.fullmatch(
            "[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}", t[k]
        ):
            raise Denied("UUID")
    for k in [
        "fencing_epoch",
        "host_revision",
        "host_generation",
        "controller_generation",
        "lease_policy_revision",
        "not_after_boottime_ns",
    ]:
        if type(t[k]) is not int or t[k] < 1:
            raise Denied("FINITE_INTEGER_TUPLE")
    for k in ["binding_digest", "head_digest", "executable_digest"]:
        if type(t[k]) is not str or not re.fullmatch("[a-f0-9]{64}", t[k]):
            raise Denied("DIGEST")
    for k in [
        "tenant_id",
        "project_id",
        "host_id",
        "host_revision",
        "host_generation",
        "host_boot_id",
        "controller_id",
        "controller_generation",
        "executable_digest",
    ]:
        if t[k] != enrollment.get(k):
            raise Denied("ENROLLED_CONTROLLER_SCOPE")
    if t["claims"] != enrollment.get("claims") or type(t["claims"]) is not list or not t["claims"]:
        raise Denied("EXACT_ENROLLED_RESOURCE_CLAIMS")
    if (
        type(t["argv"]) is not list
        or not 1 <= len(t["argv"]) <= 64
        or any(type(x) is not str or "\0" in x or len(x) > 4096 for x in t["argv"])
    ):
        raise Denied("BOUNDED_ARGV")
    if not 0 <= boottime < t["not_after_boottime_ns"]:
        raise Denied("CAPABILITY_EXPIRED")
    return t


class DirFdJournal:
    def __init__(self, journal_fd):
        st = os.fstat(journal_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
            raise Denied("PRIVATE_OWNED_JOURNAL_REQUIRED")
        self.fd = journal_fd

    def reserve(self, capability_id, record):
        fd = os.open(
            capability_id + ".intent",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.fd,
        )
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(json.dumps(record, separators=(",", ":")).encode())
            f.flush()
            os.fsync(f.fileno())
        os.fsync(self.fd)


class Controller:
    def __init__(self, journal, enrollment, launcher, clock, verify_workspace):
        self.journal = journal
        self.enrollment = enrollment
        self.launcher = launcher
        self.clock = clock
        self.verify_workspace = verify_workspace

    def dispatch(self, committed_result):
        t = validate_result(committed_result, self.enrollment, self.clock())
        # Relative O_EXCL/O_NOFOLLOW creation is the local no-respawn fence. A crash
        # leaves an immutable intent. Recovery never guesses that no spawn occurred.
        try:
            self.journal.reserve(
                t["capability_id"],
                dict(tuple_digest=committed_result["tuple_digest"], state="CONSUMED_UNKNOWN_LOCAL"),
            )
        except FileExistsError:
            raise UnknownLocal("EXISTING_INTENT_RECONCILE_NO_RESPAWN") from None
        except Exception:
            raise UnknownLocal("UNCERTAIN_JOURNAL_RESERVATION_NO_RESPAWN") from None
        try:
            # Both callbacks are trusted enrolled local adapters; neither accepts caller
            # verified=true. No default verifier or fallback subprocess implementation.
            if self.verify_workspace(t["workspace_id"], t["head_digest"]) != t["head_digest"]:
                raise Denied("MEASURED_WORKSPACE_HEAD_REQUIRED")
            validate_result(committed_result, self.enrollment, self.clock())
            observation = self.launcher.spawn(t)
            return dict(
                capability_id=t["capability_id"],
                tuple_digest=committed_result["tuple_digest"],
                observation=observation,
                callback_required=True,
            )
        except Exception:
            raise UnknownLocal("UNKNOWN_LOCAL_RECONCILE_NO_RESPAWN") from None


class SnapshotVerifier:
    """Only for enrolled supervisor-owned immutable snapshots, never live trees."""

    def __init__(self, workspace_configs):
        self.configs = workspace_configs

    def __call__(self, workspace_id, expected_digest):
        from packages.workspace_manifest import build_manifest

        c = self.configs[workspace_id]
        manifest = build_manifest(
            Path(c["root"]),
            c["allowed_paths"],
            revision=c["revision"],
            source_digest=c["source_digest"],
        )
        if manifest["manifest_digest"] != expected_digest:
            raise Denied("WORKSPACE_SOURCE_HEAD_CHANGED")
        return manifest["manifest_digest"]


class LinuxLauncher:
    """Explicitly constructed only after G0, native build and isolation enrollment."""

    def __init__(
        self,
        library_path,
        library_digest,
        cgroup_fd,
        workspace_paths,
        executable_path,
        namespace_inodes,
        uid,
        boot_id,
        resource_limits,
        lease_registry,
    ):
        if sys.platform != "linux" or os.geteuid() == 0 or os.getuid() != uid:
            raise Denied("ENROLLED_ROOTLESS_LINUX_REQUIRED")
        self.namespaces = namespace_inodes
        self.uid = uid
        self.boot = boot_id
        self.cg = cgroup_fd
        self.paths = workspace_paths
        self.executable = executable_path
        if set(resource_limits) != {"memory.max", "pids.max", "cpu.max"} or any(
            "max" in v or not all(part.isdecimal() and int(part) > 0 for part in v.split())
            for v in resource_limits.values()
        ):
            raise Denied("FINITE_ENROLLED_CGROUP_LIMITS")
        self.limits = dict(resource_limits)
        self.lease_registry = lease_registry
        import fcntl

        source_fd = os.open(library_path, os.O_RDONLY | os.O_NOFOLLOW)
        library_fd = os.memfd_create("r58-approved-native", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(source_fd).st_mode):
                raise Denied("REGULAR_NATIVE_LIBRARY_REQUIRED")
            h = hashlib.sha256()
            total = 0
            while block := os.read(source_fd, 1048576):
                total += len(block)
                if total > 16777216:
                    raise Denied("NATIVE_LIBRARY_SIZE_LIMIT")
                h.update(block)
                view = memoryview(block)
                while view:
                    n = os.write(library_fd, view)
                    if n <= 0:
                        raise Denied("NATIVE_LIBRARY_COPY_FAILED")
                    view = view[n:]
            if h.hexdigest() != library_digest:
                raise Denied("NATIVE_LIBRARY_DIGEST")
            fcntl.fcntl(
                library_fd,
                fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL,
            )
            self.lib = ctypes.CDLL("/proc/self/fd/" + str(library_fd), use_errno=True)
        finally:
            os.close(source_fd)
            os.close(library_fd)
        self.lib.r65_spawn.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self.lib.r65_spawn.restype = ctypes.c_int

    def spawn(self, t):
        import fcntl
        from threading import Thread

        for k in ["user", "mnt", "net", "pid"]:
            if os.stat("/proc/self/ns/" + k).st_ino != self.namespaces[k]:
                raise Denied("ISOLATION_NAMESPACE_CHANGED")
        for name, expected in self.limits.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.cg)
            try:
                actual = os.read(fd, 256).decode().strip()
            finally:
                os.close(fd)
            if actual != expected:
                raise Denied("CGROUP_LIMIT_CHANGED")
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if boot != self.boot or boot != t["host_boot_id"]:
            raise Denied("REBOOTED_CONTROLLER")
        root = self.paths[t["workspace_id"]]
        ws = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        exe = os.open(self.executable, os.O_RDONLY | os.O_NOFOLLOW)
        mem = os.memfd_create("r58-approved-executable", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(exe).st_mode):
                raise Denied("REGULAR_EXECUTABLE_REQUIRED")
            h = hashlib.sha256()
            first = True
            while block := os.read(exe, 1048576):
                if first and not block.startswith(b"\x7fELF"):
                    raise Denied("ELF_EXECUTABLE_REQUIRED")
                first = False
                h.update(block)
                view = memoryview(block)
                while view:
                    n = os.write(mem, view)
                    if n <= 0:
                        raise Denied("EXECUTABLE_COPY_FAILED")
                    view = view[n:]
            if first or h.hexdigest() != t["executable_digest"]:
                raise Denied("EXECUTABLE_DIGEST")
            fcntl.fcntl(
                mem,
                fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL,
            )
            argv = (ctypes.c_char_p * (len(t["argv"]) + 1))(*[x.encode() for x in t["argv"]], None)
            pid = ctypes.c_int()
            pidfd = ctypes.c_int()
            lease_state = self.lease_registry.attach(t)
            endpoints = []
            spawned = False
            watch_pidfd = None
            watch_cg = None
            thread_started = False
            try:
                for _ in range(3):
                    endpoints.extend(os.pipe2(os.O_CLOEXEC))
                child_in, parent_in, parent_out, child_out, parent_err, child_err = endpoints
                if (
                    self.lib.r65_spawn(
                        self.cg,
                        mem,
                        ws,
                        argv,
                        child_in,
                        child_out,
                        child_err,
                        ctypes.byref(pid),
                        ctypes.byref(pidfd),
                    )
                    != 0
                ):
                    raise OSError(ctypes.get_errno(), "NATIVE_LAUNCH_FAILED_NO_FALLBACK")
                spawned = True
                for fd in [child_in, child_out, child_err]:
                    os.close(fd)
                    endpoints.remove(fd)
                watch_pidfd = os.dup(pidfd.value)
                watch_cg = os.dup(self.cg)

                def watchdog():
                    import select

                    try:
                        poll = select.poll()
                        poll.register(watch_pidfd, select.POLLIN)
                        while True:
                            remaining = lease_state.remaining()
                            if remaining <= 0:
                                killfd = os.open(
                                    "cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=watch_cg
                                )
                                try:
                                    os.write(killfd, b"1")
                                finally:
                                    os.close(killfd)
                                return
                            if poll.poll(min(1000, max(1, remaining // 1000000))):
                                return
                    finally:
                        os.close(watch_pidfd)
                        os.close(watch_cg)

                Thread(target=watchdog, name="r65-lease-watchdog", daemon=True).start()
                thread_started = True
                # Parent retains only broker endpoints. They never enter DB or engine output.
                observation = dict(
                    pid=pid.value,
                    pidfd=pidfd.value,
                    host_boot_id=boot,
                    cgroup_inode=os.fstat(self.cg).st_ino,
                    state="CREATED_NOT_EXEC_ATTESTED",
                    engine_stdin_fd=parent_in,
                    engine_stdout_fd=parent_out,
                    engine_stderr_fd=parent_err,
                )
                endpoints.clear()
                return observation
            except Exception:
                if spawned:
                    try:
                        killfd = os.open("cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=self.cg)
                        try:
                            os.write(killfd, b"1")
                        finally:
                            os.close(killfd)
                    finally:
                        os.close(pidfd.value)
                        if not thread_started:
                            if watch_pidfd is not None:
                                os.close(watch_pidfd)
                            if watch_cg is not None:
                                os.close(watch_cg)
                raise
            finally:
                for fd in endpoints:
                    os.close(fd)
        finally:
            os.close(ws)
            os.close(exe)
            os.close(mem)




class SpawnPlan:
    def __init__(
        self,
        *,
        executable,
        expected_executable_sha256,
        workspace_dir,
        cgroup_dir,
        argv=(),
        env=(),
        timeout_ms=5000,
    ):
        self.executable = executable
        self.expected_executable_sha256 = expected_executable_sha256
        self.workspace_dir = workspace_dir
        self.cgroup_dir = cgroup_dir
        self.argv = argv
        self.env = env
        self.timeout_ms = timeout_ms


def sha256_file(path):
    p = path if hasattr(path, "read_bytes") else open(path, "rb")
    raw = path.read_bytes() if hasattr(path, "read_bytes") else p.read()
    return hashlib.sha256(raw).hexdigest()
