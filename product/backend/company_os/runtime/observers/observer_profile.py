"""Pinned measurement-profile subset of the runtime profile; never enrollment."""

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path, PurePosixPath
from uuid import UUID

from company_os.kernel.execution_protocol import Denied

NAMESPACES = frozenset(("user", "mnt", "net", "pid"))
FIELDS = frozenset(
    (
        "version",
        "canonical_workspace",
        "host_boot_id",
        "worker_uid",
        "observer_uid",
        "controller_uid",
        "namespace_inodes",
        "host_namespace_inodes",
        "cgroup_inode",
        "cgroup_path",
        "resource_limits",
        "executable_digest",
        "native_library_digest",
        "source_digest",
        "enrollment_digest",
        "not_after_boottime_ns",
    )
)


def _digest(value):
    if type(value) is not str or re.fullmatch("[a-f0-9]{64}", value) is None:
        raise Denied("EXACT_OBSERVER_DIGEST_REQUIRED")
    return value


class ObserverProfile:
    """Exact externally pinned bytes, not a caller-controlled verified flag."""

    def __init__(self, raw, *, expected_sha256, canonical_workspace):
        _digest(expected_sha256)
        if type(raw) is not bytes or len(raw) > 32768:
            raise Denied("BOUNDED_OBSERVER_PROFILE_REQUIRED")
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256):
            raise Denied("OBSERVER_PROFILE_PIN_MISMATCH")

        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise Denied("DUPLICATE_OBSERVER_PROFILE_KEY")
                value[key] = item
            return value

        try:
            data = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    Denied("NONFINITE_OBSERVER_PROFILE")
                ),
            )
        except (ValueError, UnicodeError) as exc:
            raise Denied("INVALID_OBSERVER_PROFILE_JSON") from exc
        if type(data) is not dict or set(data) != FIELDS:
            raise Denied("EXACT_OBSERVER_PROFILE_FIELDS_REQUIRED")
        if (
            data["version"] != "company.linux-observer-profile/1"
            or type(canonical_workspace) is not str
            or not canonical_workspace
            or data["canonical_workspace"] != canonical_workspace
        ):
            raise Denied("OBSERVER_PROFILE_SCOPE_MISMATCH")
        try:
            if (
                type(data["host_boot_id"]) is not str
                or str(UUID(data["host_boot_id"])) != data["host_boot_id"]
            ):
                raise ValueError()
        except ValueError, TypeError, AttributeError:
            raise Denied("CANONICAL_OBSERVER_BOOT_ID_REQUIRED") from None
        for key in (
            "worker_uid",
            "observer_uid",
            "controller_uid",
            "cgroup_inode",
            "not_after_boottime_ns",
        ):
            if type(data[key]) is not int or data[key] <= 0:
                raise Denied("POSITIVE_OBSERVER_PROFILE_VALUE_REQUIRED")
        if data["observer_uid"] in {data["worker_uid"], data["controller_uid"]}:
            raise Denied("DISTINCT_OBSERVER_OS_IDENTITY_REQUIRED")
        for key in ("namespace_inodes", "host_namespace_inodes"):
            ns = data[key]
            if (
                type(ns) is not dict
                or set(ns) != NAMESPACES
                or any(type(v) is not int or v <= 0 for v in ns.values())
            ):
                raise Denied("EXACT_OBSERVER_NAMESPACE_PINS_REQUIRED")
        if any(
            data["namespace_inodes"][name] == data["host_namespace_inodes"][name]
            for name in NAMESPACES
        ):
            raise Denied("WORKER_HOST_NAMESPACE_ALIAS_REJECTED")
        path = data["cgroup_path"]
        if (
            type(path) is not str
            or path == "/"
            or not path.startswith("/")
            or "\x00" in path
            or "\\" in path
            or ".." in PurePosixPath(path).parts
            or str(PurePosixPath(path)) != path
        ):
            raise Denied("EXACT_DEDICATED_CGROUP_PATH_REQUIRED")
        limits = data["resource_limits"]
        if type(limits) is not dict or set(limits) != {"memory.max", "pids.max", "cpu.max"}:
            raise Denied("EXACT_OBSERVER_RESOURCE_LIMITS_REQUIRED")
        for name, value in limits.items():
            pattern = "[1-9][0-9]* [1-9][0-9]*" if name == "cpu.max" else "[1-9][0-9]*"
            if type(value) is not str or len(value) > 64 or re.fullmatch(pattern, value) is None:
                raise Denied("FINITE_OBSERVER_RESOURCE_LIMIT_REQUIRED")
        for key in (
            "executable_digest",
            "native_library_digest",
            "source_digest",
            "enrollment_digest",
        ):
            _digest(data[key])
        self._data = copy.deepcopy(data)
        self.sha256 = expected_sha256

    @property
    def data(self):
        return copy.deepcopy(self._data)


def load_observer_profile(path, *, expected_sha256, canonical_workspace):
    with Path(path).open("rb") as source:
        raw = source.read(32769)
    return ObserverProfile(
        raw, expected_sha256=expected_sha256, canonical_workspace=canonical_workspace
    )
