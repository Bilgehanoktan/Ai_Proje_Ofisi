"""Linux enrolled directory descriptor üzerinden 32-byte anahtar okuma.

Directory fd ve owner UID güvenilir supervisor tarafından sağlanır. Anahtar
oluşturmaz; dosya izin kontrolü tek başına bağımsız custody kanıtı değildir.
"""

import os
import stat
import sys


class SecretUnavailable(RuntimeError):
    pass


def read_enrolled_key(directory_fd, name, *, owner_uid):
    if sys.platform != "linux":
        raise SecretUnavailable("LINUX_SECRET_ADAPTER_REQUIRED")
    if (
        type(owner_uid) is not int
        or owner_uid < 0
        or type(name) is not str
        or name in {"", ".", ".."}
        or "/" in name
        or "\\" in name
    ):
        raise SecretUnavailable("EXACT_KEY_SLOT_REQUIRED")
    directory = os.dup(directory_fd)
    fd = None
    try:
        parent = os.fstat(directory)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != owner_uid
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise SecretUnavailable("PRIVATE_ENROLLED_DIRECTORY_REQUIRED")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != owner_uid
            or before.st_nlink != 1
            or before.st_size != 32
            or stat.S_IMODE(before.st_mode) != 0o400
        ):
            raise SecretUnavailable("EXACT_PRIVATE_KEY_FILE_REQUIRED")
        raw = os.read(fd, 33)
        after = os.fstat(fd)
        if len(raw) != 32 or (
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise SecretUnavailable("KEY_CHANGED_DURING_READ")
        return raw
    except SecretUnavailable:
        raise
    except OSError:
        raise SecretUnavailable("ENROLLED_KEY_UNAVAILABLE") from None
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def read_secret_bytes(directory_fd, name, *, owner_uid):
    """Compatibility name with the exact enrolled-key boundary; no path bypass."""
    if type(directory_fd) is not int:
        raise SecretUnavailable("ENROLLED_DIRECTORY_DESCRIPTOR_REQUIRED")
    return read_enrolled_key(directory_fd, name, owner_uid=owner_uid)
