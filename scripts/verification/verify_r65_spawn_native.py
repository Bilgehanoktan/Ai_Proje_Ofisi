"""Compile and smoke-test product/backend/native/linux/r65_spawn_linux.c with cgroup v2."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product/backend"))
SRC = ROOT / "product/backend/native/linux/r65_spawn_linux.c"

from company_os.runtime.r65_native_launcher import NativeLauncherError, R65NativeLauncher  # noqa: E402


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root Linux account is required")

    with tempfile.TemporaryDirectory(prefix="aipof-r65-") as tmpdir:
        so_path = Path(tmpdir) / "r65_spawn_linux.so"
        compile_res = subprocess.run(
            ["gcc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC", "-o", str(so_path), str(SRC)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_res.returncode != 0:
            raise RuntimeError(f"gcc failed: {compile_res.stderr}")

        launcher = R65NativeLauncher(so_path)
        tmp_fd = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY)
        r_in, r_out = os.pipe()
        w1_in, w1_out = os.pipe()
        w2_in, w2_out = os.pipe()

        # 1. Negative test: non-cgroup fd must be rejected with EINVAL.
        neg_error = None
        try:
            launcher.spawn(
                cgroup_fd=tmp_fd, executable_fd=tmp_fd, workspace_fd=tmp_fd,
                argv=[b"/bin/true"], engine_stdin=r_in, engine_stdout=w1_out, engine_stderr=w2_out,
            )
        except NativeLauncherError as exc:
            neg_error = str(exc)

        # 2. Positive test: real cgroup2fs leaf directory + /bin/true via R65NativeLauncher.
        env_cg = os.environ.get("AIPOF_CGROUP_PATH")
        if env_cg:
            cg_path = Path(env_cg)
        else:
            self_cg_rel = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip().split("::", 1)[-1].lstrip("/")
            cg_path = Path("/sys/fs/cgroup") / self_cg_rel if self_cg_rel else Path("/sys/fs/cgroup")
        cg_fd = os.open(str(cg_path), os.O_RDONLY | os.O_DIRECTORY)
        exe_fd = os.open("/bin/true", os.O_RDONLY | os.O_CLOEXEC)
        proc = launcher.spawn(
            cgroup_fd=cg_fd, executable_fd=exe_fd, workspace_fd=tmp_fd,
            argv=[b"/bin/true"], engine_stdin=r_in, engine_stdout=w1_out, engine_stderr=w2_out,
        )
        _, status = os.waitpid(proc.pid, 0)
        exit_status = os.waitstatus_to_exitcode(status)
        os.close(proc.pidfd)

        for fd in (tmp_fd, cg_fd, exe_fd, r_in, r_out, w1_in, w1_out, w2_in, w2_out):
            os.close(fd)

    print(
        json.dumps(
            {
                "compiled_clean": True,
                "bridge_used": True,
                "neg_non_cgroup_error": neg_error,
                "child_pid": proc.pid,
                "child_exit_code": exit_status,
            }
        )
    )


if __name__ == "__main__":
    main()
