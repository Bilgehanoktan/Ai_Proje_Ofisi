"""Exercise the pinned native launcher in a disposable delegated Linux unit.

Run as the non-root test account with Delegate=yes. Requires apt download,
dpkg-deb, binutils, unshare and cgroup v2. Temporary packages are unpacked
without installation. The test runs a sealed copy of cat with fixture stdin.
"""

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
from contextlib import ExitStack


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("product/backend/native/linux/r65_spawn_linux.c")
NAMESPACES = ("pid", "user", "mnt", "net")
PACKAGES = (
    "gcc-15-x86-64-linux-gnu", "cpp-15-x86-64-linux-gnu", "libgcc-15-dev",
    "libc6-dev", "linux-libc-dev", "libisl23", "libmpc3",
)


def compile_library(work):
    pinned = json.loads((ROOT / "SOURCE_MANIFEST.json").read_bytes())["files"]
    source = ROOT / SOURCE
    if hashlib.sha256(source.read_bytes()).hexdigest() != pinned[SOURCE.as_posix()]:
        raise RuntimeError("Launcher source pin mismatch")
    subprocess.run(
        ["apt-get", "-o", "Acquire::Retries=0", "-o", "Acquire::http::Timeout=10",
         "download", *PACKAGES], cwd=work, check=True, timeout=100,
        stdout=subprocess.DEVNULL,
    )
    package_root = work / "packages"
    for package in sorted(work.glob("*.deb")):
        subprocess.run(["dpkg-deb", "-x", package, package_root], check=True, timeout=30)
    usr = package_root / "usr"
    library = work / "launcher.so"
    subprocess.run(
        [usr / "bin/x86_64-linux-gnu-gcc-15", "-std=c11", "-Wall", "-Wextra",
         "-Werror", "-O2", "-fPIC", "-nostdlib", "-shared",
         "-isystem", usr / "include/x86_64-linux-gnu", "-isystem", usr / "include",
         source, "-o", library],
        env=dict(os.environ, LD_LIBRARY_PATH=str(usr / "lib/x86_64-linux-gnu")),
        check=True, timeout=30,
    )
    print("SOURCE_PIN_AND_STRICT_BUILD_PASS", flush=True)
    return library


def cgroup_path():
    entry, = (line for line in Path("/proc/self/cgroup").read_text().splitlines()
              if line.startswith("0::"))
    return Path("/sys/fs/cgroup") / entry[3:].lstrip("/")


def namespace_ids():
    return [os.stat(f"/proc/self/ns/{name}").st_ino for name in NAMESPACES]


def open_fd(stack, fd):
    stack.callback(os.close, fd)
    return fd


def pipe(stack):
    return tuple(open_fd(stack, fd) for fd in os.pipe())


def test_launch(library, leaf, workspace):
    launch = ctypes.CDLL(str(library), use_errno=True).r65_spawn
    integer = ctypes.c_int
    launch.argtypes = [integer, integer, integer, ctypes.POINTER(ctypes.c_char_p),
                       integer, integer, integer, ctypes.POINTER(integer), ctypes.POINTER(integer)]
    launch.restype = integer
    argv = (ctypes.c_char_p * 2)(b"cat", None)
    with ExitStack() as files:
        group = open_fd(files, os.open(leaf, os.O_DIRECTORY | os.O_RDONLY))
        directory = open_fd(files, os.open(workspace, os.O_DIRECTORY | os.O_RDONLY))
        executable = open_fd(files, os.memfd_create("native-test-cat", os.MFD_ALLOW_SEALING))
        with os.fdopen(os.dup(executable), "wb") as image:
            image.write(Path("/usr/bin/cat").read_bytes())
        fcntl.fcntl(executable, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        stdin, stdout, stderr = pipe(files), pipe(files), pipe(files)
        def reject(cgroup, arguments, streams, expected):
            pid, handle = integer(-71), integer(-72)
            result = launch(cgroup, executable, directory, arguments, *streams,
                            ctypes.byref(pid), ctypes.byref(handle))
            assert (result, ctypes.get_errno(), pid.value, handle.value) == (-1, expected, -71, -72)
        reject(-1, None, (-1, -1, -1), errno.EPERM)
        reject(-1, argv, (-1, -1, -1), errno.EINVAL)
        reject(group, argv, (-1, -1, -1), errno.EINVAL)
        reject(group, argv, (stdin[1], stdout[1], stderr[1]), errno.EINVAL)
        reject(group, argv, (stdin[0], stdin[1], stderr[1]), errno.EINVAL)
        os.set_blocking(stderr[1], False)
        reject(group, argv, (stdin[0], stdout[1], stderr[1]), errno.EINVAL)
        os.set_blocking(stderr[1], True)
        print("SIX_INVALID_INPUT_REJECTIONS_PASS", flush=True)
        pid, handle = integer(-1), integer(-1)
        result = launch(group, executable, directory, argv, stdin[0], stdout[1], stderr[1],
                        ctypes.byref(pid), ctypes.byref(handle))
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, f"native clone3: {os.strerror(error)}")
        open_fd(files, handle.value)
        try:
            marker = b"r65-native-probe\n"
            os.write(stdin[1], marker)
            ready, _, _ = select.select([stdout[0], handle.value], [], [], 5)
            if stdout[0] not in ready or os.read(stdout[0], len(marker)) != marker:
                raise RuntimeError("Child did not echo the sealed cat marker")
            child = Path("/proc") / str(pid.value)
            status = dict(line.split(":\t", 1) for line in (child / "status").read_text().splitlines()
                          if ":\t" in line)
            assert status["NoNewPrivs"] == "1" and status["Seccomp"] == "2"
            assert (child / "cgroup").read_text().strip() == f"0::/{leaf.relative_to('/sys/fs/cgroup')}"
            assert all(os.stat(child / "ns" / name).st_ino == os.stat(f"/proc/self/ns/{name}").st_ino
                       for name in NAMESPACES)
            print("SEALED_EXEC_CGROUP_NAMESPACES_NO_NEW_PRIVS_SECCOMP_PASS", flush=True)
        finally:
            signal.pidfd_send_signal(handle.value, signal.SIGKILL)
            _, status = os.waitpid(pid.value, 0)
        assert os.waitstatus_to_exitcode(status) == -signal.SIGKILL
        assert "populated 0" in (leaf / "cgroup.events").read_text().splitlines()
        print("PIDFD_STOP_WAIT_AND_CGROUP_EMPTY_PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", nargs=4, metavar=("LIBRARY", "LEAF", "WORK", "PARENT_NS"))
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() == 0 or not __debug__:
        parser.error("Use non-root Linux without optimization")
    if args.inside:
        library, leaf, workspace, parent = args.inside
        if any(a == b for a, b in zip(namespace_ids(), json.loads(parent), strict=True)):
            raise RuntimeError("One or more isolation namespaces were not changed")
        test_launch(Path(library), Path(leaf), Path(workspace))
        return
    with tempfile.TemporaryDirectory(prefix="aipof-native-") as directory:
        work = Path(directory)
        library = compile_library(work)
        workspace = work / "workspace"
        workspace.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix="r65-worker-", dir=cgroup_path()) as leaf:
            subprocess.run(
                ["unshare", "--user", "--map-current-user", "--mount", "--net", "--pid",
                 "--fork", "--mount-proc", sys.executable, "-B", __file__, "--inside",
                 library, leaf, workspace, json.dumps(namespace_ids())],
                check=True, timeout=20,
            )


if __name__ == "__main__":
    main()
