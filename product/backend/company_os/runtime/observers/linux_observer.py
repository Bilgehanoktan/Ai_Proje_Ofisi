"""Read-only Linux measurements for enrolled observer ports.

Profiles/pins and proc/cgroup descriptors come from a trusted supervisor. This
module neither creates namespaces nor enrolls observers. Local measurements are
not independent runtime verification; the validator also requires an external
current enrollment/profile check.
"""

import copy
import hashlib
import os
import stat
import sys
from pathlib import Path

from company_os.kernel.execution_protocol import Denied, Unknown, canonical
from company_os.runtime.observers.observer_profile import NAMESPACES, ObserverProfile


def current_context():
    if sys.platform != "linux":
        raise Denied("LINUX_OBSERVER_REQUIRED")
    import time

    return dict(
        observer_uid=os.geteuid(),
        host_boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
    )


def _read_at(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
    try:
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > limit:
            raise Denied("OBSERVER_READ_LIMIT")
        return raw.decode("utf-8")
    finally:
        os.close(fd)


def _starttime(raw):
    # /proc stat comm can contain spaces and parentheses; fields start after
    # the last ')' (field 3). starttime is field 22, not a whitespace index 21.
    tail = raw[raw.rfind(")") + 1 :].split()
    if len(tail) < 20 or tail[0] in {"Z", "X", "x"}:
        raise Denied("LIVE_PROCESS_STAT_REQUIRED")
    value = int(tail[19])
    if value <= 0:
        raise Denied("EXACT_PROCESS_STARTTIME_REQUIRED")
    return value


def pidfd_exited(fd):
    import select

    if os.readlink("/proc/self/fd/" + str(fd)) != "anon_inode:[pidfd]":
        raise Denied("ACTUAL_OBSERVER_PIDFD_REQUIRED")
    poll = select.poll()
    poll.register(fd, select.POLLIN)
    events = poll.poll(0)
    if any(mask & (select.POLLERR | select.POLLNVAL) for _, mask in events):
        raise Denied("VALID_OBSERVER_PIDFD_REQUIRED")
    return bool(events)


class LinuxProcReader:
    def capture(self, *, pid, pidfd, require_sealed=True):
        if sys.platform != "linux":
            raise Denied("LINUX_PROC_READER_REQUIRED")
        if type(pid) is not int or pid <= 0 or type(pidfd) is not int or pidfd < 3:
            raise Denied("EXACT_OBSERVER_PROCESS_HANDLE_REQUIRED")
        if pidfd_exited(pidfd):
            raise Denied("RUNNING_PIDFD_REQUIRED")
        with Path("/proc/self/fdinfo/" + str(pidfd)).open("rb") as source:
            raw = source.read(8193)
        if len(raw) > 8192:
            raise Denied("BOUNDED_PIDFD_INFO_REQUIRED")
        info = dict(line.split(":", 1) for line in raw.decode().splitlines() if ":" in line)
        if int(info.get("Pid", "-1").strip()) != pid:
            raise Denied("PIDFD_PID_BINDING_MISMATCH")
        directory = os.open(
            "/proc/" + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        executable = None
        try:
            start = _starttime(_read_at(directory, "stat", 8192))
            status = dict(
                line.split(":", 1)
                for line in _read_at(directory, "status", 65536).splitlines()
                if ":" in line
            )
            ns = {name: os.stat("ns/" + name, dir_fd=directory).st_ino for name in NAMESPACES}
            cgroup = _read_at(directory, "cgroup", 8192).strip()
            # exe is deliberately followed only under a kernel proc directory.
            executable = os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
            before = os.fstat(executable)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 16777216:
                raise Denied("BOUNDED_OBSERVER_EXECUTABLE_REQUIRED")
            import fcntl

            try:
                seals = fcntl.fcntl(executable, fcntl.F_GET_SEALS)
            except OSError:
                seals = None
            if require_sealed is not False and (seals is None or seals & 15 != 15):
                raise Denied("SEALED_NATIVE_EXECUTABLE_REQUIRED")
            h = hashlib.sha256()
            total = 0
            while block := os.read(executable, 1048576):
                if total == 0 and not block.startswith(b"\x7fELF"):
                    raise Denied("NATIVE_ELF_PROCESS_REQUIRED")
                total += len(block)
                if total > 16777216:
                    raise Denied("OBSERVER_EXECUTABLE_LIMIT")
                h.update(block)
            fds_dir = os.open("fd", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=directory)
            try:
                descriptors = sorted(int(name) for name in os.listdir(fds_dir))
            finally:
                os.close(fds_dir)
            after = os.stat("exe", dir_fd=directory)
            if (
                (before.st_dev, before.st_ino, before.st_size)
                != (after.st_dev, after.st_ino, after.st_size)
                or start != _starttime(_read_at(directory, "stat", 8192))
                or pidfd_exited(pidfd)
            ):
                raise Denied("PROCESS_CHANGED_DURING_OBSERVATION")
            return dict(
                pid=pid,
                starttime=start,
                uid=[int(v) for v in status["Uid"].split()],
                namespace_inodes=ns,
                cgroup_membership=cgroup,
                executable_digest=h.hexdigest(),
                executable_seals=seals,
                no_new_privs=int(status["NoNewPrivs"]),
                seccomp=int(status["Seccomp"]),
                capabilities={
                    key: int(status.get(key, "-1").strip(), 16)
                    for key in ("CapEff", "CapPrm", "CapInh", "CapAmb")
                },
                descriptors=descriptors,
            )
        finally:
            if executable is not None:
                os.close(executable)
            os.close(directory)


class LinuxCgroupReader:
    def capture(self, directory_fd):
        if sys.platform != "linux" or type(directory_fd) is not int or directory_fd < 3:
            raise Denied("LINUX_CGROUP_DESCRIPTOR_REQUIRED")
        value = os.fstat(directory_fd)
        if not stat.S_ISDIR(value.st_mode):
            raise Denied("CGROUP_DIRECTORY_REQUIRED")
        # Validate the filesystem type, not merely caller-controlled filenames.
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        libc.fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
        libc.fstatfs.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(512)
        if (
            libc.fstatfs(directory_fd, buffer) != 0
            or ctypes.c_long.from_buffer(buffer).value != 0x63677270
        ):
            raise Denied("ACTUAL_CGROUP2_FILESYSTEM_REQUIRED")
        limits = {
            name: _read_at(directory_fd, name, 128).strip()
            for name in ("memory.max", "pids.max", "cpu.max")
        }
        processes = [int(v) for v in _read_at(directory_fd, "cgroup.procs", 65536).split()]
        events = dict(
            line.split() for line in _read_at(directory_fd, "cgroup.events", 4096).splitlines()
        )
        return dict(
            inode=value.st_ino,
            resource_limits=limits,
            processes=processes,
            populated=int(events["populated"]),
        )


class LinuxLaunchObserver:
    def __init__(
        self,
        *,
        profile,
        cgroup_fd,
        proc_reader=None,
        cgroup_reader=None,
        context_reader=current_context,
    ):
        if type(profile) is not ObserverProfile:
            raise Denied("PINNED_OBSERVER_PROFILE_REQUIRED")
        self.profile = profile
        self.cgroup = cgroup_fd
        self.proc_reader = LinuxProcReader() if proc_reader is None else proc_reader
        self.cgroup_reader = LinuxCgroupReader() if cgroup_reader is None else cgroup_reader
        self.context_reader = context_reader
        self.registered = None

    def _context(self):
        context = self.context_reader()
        profile = self.profile.data
        if (
            type(context["observer_uid"]) is not int
            or context["observer_uid"] != profile["observer_uid"]
            or context["host_boot_id"] != profile["host_boot_id"]
            or type(context["boottime_ns"]) is not int
            or not 0 <= context["boottime_ns"] < profile["not_after_boottime_ns"]
        ):
            raise Denied("OBSERVER_CONTEXT_OR_PROFILE_EXPIRED")
        return profile

    def observe(self, *, expected, observation):
        profile = self._context()
        if (
            expected["host_boot_id"] != profile["host_boot_id"]
            or expected["cgroup_inode"] != profile["cgroup_inode"]
            or observation["host_boot_id"] != profile["host_boot_id"]
            or observation["cgroup_inode"] != profile["cgroup_inode"]
            or observation.get("state") != "CREATED_NOT_EXEC_ATTESTED"
        ):
            raise Denied("OBSERVER_PROFILE_PROCESS_SCOPE_MISMATCH")
        before = self.cgroup_reader.capture(self.cgroup)
        process = self.proc_reader.capture(
            pid=observation["pid"], pidfd=observation["pidfd"], require_sealed=True
        )
        after = self.cgroup_reader.capture(self.cgroup)
        if before != after:
            raise Denied("CGROUP_CHANGED_DURING_OBSERVATION")
        if (
            before["inode"] != profile["cgroup_inode"]
            or before["resource_limits"] != profile["resource_limits"]
            or before["processes"] != [observation["pid"]]
            or before["populated"] != 1
        ):
            raise Denied("EXACT_DEDICATED_CGROUP_MEASUREMENT_REQUIRED")
        if (
            process["pid"] != observation["pid"]
            or process["uid"] != [profile["worker_uid"]] * 4
            or process["namespace_inodes"] != profile["namespace_inodes"]
            or process["cgroup_membership"] != "0::" + profile["cgroup_path"]
            or process["executable_digest"] != profile["executable_digest"]
            or process["executable_seals"] is None
            or process["executable_seals"] & 15 != 15
            or process["no_new_privs"] != 1
            or process["seccomp"] != 2
            or set(process["capabilities"]) != {"CapEff", "CapPrm", "CapInh", "CapAmb"}
            or any(
                type(value) is not int or value != 0 for value in process["capabilities"].values()
            )
            or process["descriptors"] != [0, 1, 2]
        ):
            raise Denied("EXACT_ISOLATED_PROCESS_MEASUREMENT_REQUIRED")
        self._context()  # Expiry/boot may change while reading OS metadata.
        identity = dict(
            pid=process["pid"],
            starttime=process["starttime"],
            host_boot_id=profile["host_boot_id"],
            uid=process["uid"],
            pid_namespace=process["namespace_inodes"]["pid"],
        )
        result = dict(
            identity=copy.deepcopy(expected),
            outcome="RUNNING",
            process_identity_digest=hashlib.sha256(canonical(identity)).hexdigest(),
            isolation_digest=hashlib.sha256(
                canonical(dict(process=process, cgroup=before, profile_digest=self.profile.sha256))
            ).hexdigest(),
        )
        self.registered = dict(
            expected=copy.deepcopy(expected), observation=copy.deepcopy(observation)
        )
        return result


class LinuxLaunchObservationValidator:
    def __init__(self, *, observer, enrollment_reader):
        self.observer = observer
        self.enrollment_reader = enrollment_reader

    def validate(self, measured, *, expected):
        # An independently maintained current enrollment/profile binding is still
        # mandatory. A profile hash or a self-reported verified=true cannot do it.
        if self.enrollment_reader is None or self.observer.registered is None:
            raise Denied("CURRENT_OBSERVER_ENROLLMENT_REQUIRED")
        profile = self.observer.profile
        if (
            self.enrollment_reader.validate(
                profile_digest=profile.sha256,
                enrollment_digest=profile.data["enrollment_digest"],
                expected=copy.deepcopy(expected),
            )
            is not True
        ):
            raise Denied("OBSERVER_ENROLLMENT_BINDING_REJECTED")
        saved = self.observer.registered
        if saved["expected"] != expected:
            raise Denied("OBSERVER_MEASUREMENT_IDENTITY_MISMATCH")
        actual = self.observer.observe(
            expected=copy.deepcopy(expected), observation=saved["observation"]
        )
        if actual != measured:
            raise Denied("OBSERVER_MEASUREMENT_CHANGED")
        if (
            self.enrollment_reader.validate(
                profile_digest=profile.sha256,
                enrollment_digest=profile.data["enrollment_digest"],
                expected=copy.deepcopy(expected),
            )
            is not True
        ):
            raise Denied("OBSERVER_ENROLLMENT_CHANGED_DURING_MEASUREMENT")
        return True


class LinuxStopObserver:
    """pidfd exit + empty cgroup + authoritative fence/journal/ledger readback.

    A zero cgroup population does NOT imply workspace fencing or ledger usage
    zero. Those values must be re-read by the enrolled authority adapter.
    """

    def __init__(
        self,
        *,
        profile,
        cgroup_fd,
        observer_id,
        authoritative_readback,
        cgroup_reader=None,
        context_reader=current_context,
        exit_reader=pidfd_exited,
        proc_reader=None,
    ):
        self.context = LinuxLaunchObserver(
            profile=profile,
            cgroup_fd=cgroup_fd,
            cgroup_reader=cgroup_reader,
            context_reader=context_reader,
            proc_reader=proc_reader,
        )
        self.pidfd = None
        self.expected = None
        self.fingerprint = None
        self.closed = False
        self.close_failed = False
        self.observer_id = observer_id
        self.authority = authoritative_readback
        self.exit_reader = exit_reader

    def bind(self, *, expected, observation):
        if self.expected is not None or self.closed:
            raise Denied("STOP_OBSERVER_ALREADY_BOUND_OR_CLOSED")
        measured = self.context.observe(expected=expected, observation=observation)
        if measured["process_identity_digest"] != expected.get("process_identity_digest"):
            raise Denied("STOP_PIDFD_PROCESS_IDENTITY_MISMATCH")
        duplicate = os.dup(observation["pidfd"])
        try:
            process = self.context.proc_reader.capture(
                pid=observation["pid"], pidfd=duplicate, require_sealed=True
            )
            profile = self.profile.data
            identity = dict(
                pid=process["pid"],
                starttime=process["starttime"],
                host_boot_id=profile["host_boot_id"],
                uid=process["uid"],
                pid_namespace=process["namespace_inodes"]["pid"],
            )
            if (
                hashlib.sha256(canonical(identity)).hexdigest()
                != expected["process_identity_digest"]
            ):
                raise Denied("STOP_PIDFD_CHANGED_DURING_BIND")
            value = os.fstat(duplicate)
            self.fingerprint = (value.st_dev, value.st_ino)
        except Exception:
            os.close(duplicate)
            raise
        self.pidfd = duplicate
        self.expected = copy.deepcopy(expected)

    def close(self):
        if self.close_failed:
            raise Unknown("STOP_OBSERVER_CLOSE_UNCONFIRMED_NO_RETRY")
        if self.closed:
            return
        self.closed = True
        if self.pidfd is not None:
            fd, self.pidfd = self.pidfd, None
            try:
                value = os.fstat(fd)
                if (value.st_dev, value.st_ino) != self.fingerprint:
                    raise Denied("STOP_OBSERVER_HANDLE_CHANGED")
                os.close(fd)
            except Exception:
                self.close_failed = True
                raise Unknown("STOP_OBSERVER_CLOSE_UNCONFIRMED_NO_RETRY") from None

    @property
    def profile(self):
        return self.context.profile

    def observe(self, *, expected):
        profile = self.context._context()
        if (
            self.closed
            or self.pidfd is None
            or expected != self.expected
            or expected["host_boot_id"] != profile["host_boot_id"]
            or expected["cgroup_inode"] != profile["cgroup_inode"]
        ):
            raise Denied("EXACT_STOP_PROCESS_IDENTITY_REQUIRED")
        state = self.authority.read(expected=copy.deepcopy(expected))
        if (
            type(state) is not dict
            or set(state) != {"identity", "workspace_fenced", "no_respawn_intent", "usage_zero"}
            or state["identity"] != expected
            or any(
                type(state[key]) is not bool
                for key in ("workspace_fenced", "no_respawn_intent", "usage_zero")
            )
        ):
            raise Denied("AUTHORITATIVE_STOP_READBACK_REQUIRED")
        value = os.fstat(self.pidfd)
        if (value.st_dev, value.st_ino) != self.fingerprint:
            raise Denied("STOP_OBSERVER_HANDLE_CHANGED")
        exited = self.exit_reader(self.pidfd)
        group = self.context.cgroup_reader.capture(self.context.cgroup)
        if (
            group["inode"] != profile["cgroup_inode"]
            or group["resource_limits"] != profile["resource_limits"]
            or type(group["populated"]) is not int
            or group["populated"] not in {0, 1}
        ):
            raise Denied("EXACT_STOP_CGROUP_MEASUREMENT_REQUIRED")
        if type(exited) is not bool:
            raise Denied("ACTUAL_PIDFD_EXIT_OBSERVATION_REQUIRED")
        stopped = exited and group["populated"] == 0 and group["processes"] == []
        if stopped and not all(
            state[key] is True for key in ("workspace_fenced", "no_respawn_intent", "usage_zero")
        ):
            raise Denied("STOP_FENCE_JOURNAL_LEDGER_NOT_RECONCILED")
        self.context._context()
        return dict(
            identity=copy.deepcopy(expected),
            observer_id=self.observer_id,
            outcome="EXITED" if stopped else "RUNNING",
            cgroup_populated=group["populated"],
            **{key: state[key] for key in ("workspace_fenced", "no_respawn_intent", "usage_zero")},
        )


class LinuxStopObservationValidator:
    def __init__(self, *, observer, enrollment_reader):
        self.observer = observer
        self.enrollment_reader = enrollment_reader

    def validate(self, measured, *, expected):
        if self.enrollment_reader is None:
            raise Denied("CURRENT_OBSERVER_ENROLLMENT_REQUIRED")
        profile = self.observer.profile
        if (
            self.enrollment_reader.validate(
                profile_digest=profile.sha256,
                enrollment_digest=profile.data["enrollment_digest"],
                expected=copy.deepcopy(expected),
            )
            is not True
        ):
            raise Denied("OBSERVER_ENROLLMENT_BINDING_REJECTED")
        if measured != self.observer.observe(expected=copy.deepcopy(expected)):
            raise Denied("STOP_MEASUREMENT_CHANGED")
        if (
            self.enrollment_reader.validate(
                profile_digest=profile.sha256,
                enrollment_digest=profile.data["enrollment_digest"],
                expected=copy.deepcopy(expected),
            )
            is not True
        ):
            raise Denied("OBSERVER_ENROLLMENT_CHANGED_DURING_MEASUREMENT")
        return True
