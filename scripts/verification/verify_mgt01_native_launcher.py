"""MOD-004 + MGT-01: Run MGT-TITLE-NORMALIZATION-01 worker inside native C r65_spawn_linux.c cgroup v2."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product/backend"))
sys.path.insert(0, str(ROOT / "contracts/source/python"))
sys.path.insert(0, str(ROOT / "verifier/src"))

from company_os.runtime.r65_native_launcher import R65NativeLauncher  # noqa: E402
from independent_verifier.verifier_runner import run_source_title_oracle  # noqa: E402

SRC = ROOT / "product/backend/native/linux/r65_spawn_linux.c"
ORACLE_PATH = ROOT / "verifier/public-fixtures/mgt01/check_title.py"

PATCHED_TASK_TITLE = '''"""MGT-TITLE-NORMALIZATION-01 normalized title helper."""


def normalize_title(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("title must be a str")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 120:
        raise ValueError("title must be 1..120 characters after normalization")
    return normalized
'''

WORKER_SCRIPT = (
    "import hashlib, json, pathlib, sys; "
    "src = sys.stdin.read(); "
    "out = pathlib.Path('task_title.py'); "
    "out.write_text(src, encoding='utf-8'); "
    "print(json.dumps({'written': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}))"
)


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root Linux account is required")

    env_cg = os.environ.get("AIPOF_CGROUP_PATH")
    if env_cg:
        cg_path = Path(env_cg)
    else:
        self_cg_rel = (
            Path("/proc/self/cgroup")
            .read_text(encoding="utf-8")
            .strip()
            .split("::", 1)[-1]
            .lstrip("/")
        )
        cg_path = Path("/sys/fs/cgroup") / self_cg_rel if self_cg_rel else Path("/sys/fs/cgroup")

    python_exe = Path(sys.executable).resolve()

    with tempfile.TemporaryDirectory(prefix="aipof-mgt01-r65-") as tmpdir:
        work = Path(tmpdir)
        so_path = work / "r65_spawn_linux.so"
        ws_dir = work / "workspace"
        ws_dir.mkdir(mode=0o700)

        compile_res = subprocess.run(
            ["gcc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC", "-o", str(so_path), str(SRC)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if compile_res.returncode != 0:
            raise RuntimeError(f"gcc failed: {compile_res.stderr}")

        launcher = R65NativeLauncher(so_path)
        cg_fd = os.open(str(cg_path), os.O_RDONLY | os.O_DIRECTORY)
        exe_fd = os.open(str(python_exe), os.O_RDONLY | os.O_CLOEXEC)
        ws_fd = os.open(str(ws_dir), os.O_RDONLY | os.O_DIRECTORY)
        in_r, in_w = os.pipe()
        out_r, out_w = os.pipe()
        err_r, err_w = os.pipe()
        try:
            proc = launcher.spawn(
                cgroup_fd=cg_fd,
                executable_fd=exe_fd,
                workspace_fd=ws_fd,
                argv=[str(python_exe).encode("utf-8"), b"-c", WORKER_SCRIPT.encode("utf-8")],
                engine_stdin=in_r,
                engine_stdout=out_w,
                engine_stderr=err_w,
            )
            os.close(in_r)
            os.close(out_w)
            os.close(err_w)
            in_r = out_w = err_w = -1

            os.write(in_w, PATCHED_TASK_TITLE.encode("utf-8"))
            os.close(in_w)
            in_w = -1

            stdout_chunks = []
            while chunk := os.read(out_r, 4096):
                stdout_chunks.append(chunk)
            stderr_chunks = []
            while chunk := os.read(err_r, 4096):
                stderr_chunks.append(chunk)

            _, status = os.waitpid(proc.pid, 0)
            exit_code = os.waitstatus_to_exitcode(status)
            os.close(proc.pidfd)
        finally:
            for fd in (cg_fd, exe_fd, ws_fd, in_r, in_w, out_r, out_w, err_r, err_w):
                if fd >= 0:
                    os.close(fd)

        if exit_code != 0:
            raise RuntimeError(
                f"Native worker exited with {exit_code}: {b''.join(stderr_chunks).decode('utf-8', 'replace')}"
            )

        worker_receipt = json.loads(b"".join(stdout_chunks).decode("utf-8").strip())
        candidate_path = ws_dir / "task_title.py"
        actual_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        if actual_sha != worker_receipt["sha256"]:
            raise RuntimeError("Worker receipt SHA256 mismatch")

        oracle_res = run_source_title_oracle(candidate_path, ORACLE_PATH)
        passed = sum(1 for c in oracle_res["checks"] if c["result"] == "PASS")
        total = len(oracle_res["checks"])
        if passed != 13 or total != 13 or oracle_res["outcome"] != "PASS":
            raise RuntimeError(f"Expected 13/13 PASS, got {passed}/{total} ({oracle_res['outcome']})")

    report = {
        "native_launcher": "r65_spawn_linux.c",
        "compiled_clean": True,
        "cgroup_path": str(cg_path),
        "child_pid": proc.pid,
        "child_exit_code": exit_code,
        "worker_receipt": worker_receipt,
        "oracle_id": oracle_res["oracle_id"],
        "oracle_outcome": oracle_res["outcome"],
        "oracle_passed": passed,
        "oracle_total": total,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
