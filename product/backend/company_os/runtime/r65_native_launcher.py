"""MOD-004: Fail-closed Python ctypes bridge to native Linux r65_spawn_linux.c."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from dataclasses import dataclass
from pathlib import Path


class NativeLauncherError(RuntimeError):
    """Raised when native r65_spawn cannot be loaded or fails; never falls back."""


@dataclass(frozen=True)
class SpawnedProcess:
    pid: int
    pidfd: int


class R65NativeLauncher:
    """Loads compiled r65_spawn_linux.so and invokes r65_spawn without fork+attach fallback."""

    def __init__(self, library_path: str | Path) -> None:
        if sys.platform != "linux":
            raise NativeLauncherError("R65_LINUX_ONLY")
        if os.geteuid() == 0:
            raise NativeLauncherError("R65_NON_ROOT_REQUIRED")
        path = Path(library_path)
        if not path.is_file():
            raise NativeLauncherError(f"R65_LIBRARY_NOT_FOUND:{path}")
        lib = ctypes.CDLL(str(path), use_errno=True)
        lib.r65_spawn.argtypes = [
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
        lib.r65_spawn.restype = ctypes.c_int
        self._lib = lib

    def spawn(
        self,
        *,
        cgroup_fd: int,
        executable_fd: int,
        workspace_fd: int,
        argv: list[bytes],
        engine_stdin: int,
        engine_stdout: int,
        engine_stderr: int,
    ) -> SpawnedProcess:
        if not argv:
            raise NativeLauncherError("R65_ARGV_REQUIRED")
        c_argv = (ctypes.c_char_p * (len(argv) + 1))(*argv, None)
        out_pid = ctypes.c_int(-1)
        out_pidfd = ctypes.c_int(-1)
        rc = self._lib.r65_spawn(
            cgroup_fd,
            executable_fd,
            workspace_fd,
            c_argv,
            engine_stdin,
            engine_stdout,
            engine_stderr,
            ctypes.byref(out_pid),
            ctypes.byref(out_pidfd),
        )
        if rc != 0:
            err = ctypes.get_errno()
            code = errno.errorcode.get(err, str(err))
            raise NativeLauncherError(f"R65_SPAWN_FAILED:{code}")
        return SpawnedProcess(pid=out_pid.value, pidfd=out_pidfd.value)
