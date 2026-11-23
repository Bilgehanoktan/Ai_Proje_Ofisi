"""Linux parent-handle ownership; no launch, stop, isolation or exit claims."""

import os
import stat
import sys
import threading

from company_os.kernel.execution_protocol import Denied, Unknown

PIPE_KEYS = ("engine_stdout_fd", "engine_stdin_fd", "engine_stderr_fd")


def _identity(fd):
    value = os.fstat(fd)
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


class LaunchObservationCloser:
    """Register before handoff; close only handles still owned by supervisor.

    The enrolled supervisor supplies the observation directly, never an engine
    frame or user JSON. FD metadata is a cleanup guard, not an isolation proof.
    Each instance owns one observation; failed closes are never retried against
    potentially reused descriptor numbers.
    """

    def __init__(self, *, expected_host_boot_id, expected_cgroup_inode):
        if sys.platform != "linux":
            raise Denied("LINUX_SUPERVISOR_HANDLES_REQUIRED")
        if type(expected_cgroup_inode) is not int or expected_cgroup_inode <= 0:
            raise Denied("EXACT_SUPERVISOR_CGROUP_REQUIRED")
        self.boot = expected_host_boot_id
        self.cgroup = expected_cgroup_inode
        self.observation = None
        self.identities = {}
        self.used = False
        self.failed = False
        self.lock = threading.Lock()

    def register(self, observation):
        with self.lock:
            if self.observation is not None or self.used:
                raise Denied("SUPERVISOR_HANDLES_ALREADY_REGISTERED")
            if (
                type(observation) is not dict
                or observation.get("state") != "CREATED_NOT_EXEC_ATTESTED"
                or observation.get("host_boot_id") != self.boot
                or observation.get("cgroup_inode") != self.cgroup
                or type(observation.get("pid")) is not int
                or observation["pid"] <= 0
            ):
                raise Denied("EXACT_SUPERVISOR_OBSERVATION_REQUIRED")
            fds = [observation.get(k) for k in ("pidfd",) + PIPE_KEYS]
            if any(type(fd) is not int or fd < 3 for fd in fds) or len(set(fds)) != 4:
                raise Denied("DISTINCT_SUPERVISOR_DESCRIPTORS_REQUIRED")
            import fcntl

            expected_modes = (os.O_RDONLY, os.O_WRONLY, os.O_RDONLY)
            identities = {fd: _identity(fd) for fd in fds}
            if os.readlink("/proc/self/fd/" + str(fds[0])) != "anon_inode:[pidfd]":
                raise Denied("ACTUAL_PIDFD_REQUIRED")
            if any(os.get_inheritable(fd) for fd in fds):
                raise Denied("NONINHERITABLE_PARENT_HANDLES_REQUIRED")
            pipe_identities = [identities[fd] for fd in fds[1:]]
            if (
                any(identity[2] != stat.S_IFIFO for identity in pipe_identities)
                or len(set(pipe_identities)) != 3
                or any(
                    fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != mode
                    for fd, mode in zip(fds[1:], expected_modes)
                )
            ):
                raise Denied("EXACT_DISTINCT_PARENT_PIPE_MODES_REQUIRED")
            self.observation = dict(observation)
            self.identities = identities

    def __call__(self, observation, *, pipes_transferred):
        with self.lock:
            if self.failed:
                raise Unknown("SUPERVISOR_HANDLE_CLOSE_UNCONFIRMED_NO_RETRY")
            if (
                self.observation is None
                or type(pipes_transferred) is not bool
                or observation != self.observation
            ):
                raise Denied("REGISTERED_HANDLE_OWNERSHIP_REQUIRED")
            if self.used:
                return
            self.used = True
            keys = ("pidfd",) if pipes_transferred else ("pidfd",) + PIPE_KEYS
            for key in keys:
                fd = self.observation[key]
                try:
                    if _identity(fd) != self.identities[fd]:
                        raise Unknown("SUPERVISOR_DESCRIPTOR_IDENTITY_CHANGED")
                    os.close(fd)
                except OSError, Unknown:
                    self.failed = True
            if self.failed:
                raise Unknown("SUPERVISOR_HANDLE_CLOSE_UNCONFIRMED_NO_RETRY")
