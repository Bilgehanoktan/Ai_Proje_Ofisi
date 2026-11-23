"""Fixed observer/verifier service handlers and canonical workflow client ports.

Trusted supervisor must run the handler under the enrolled distinct OS identity
and provide current authority readbacks/isolated launcher. No default approval,
candidate subprocess, service installation or port exposure exists here.
"""

import copy
import hashlib
import os
import sqlite3
import stat
import sys
import threading

from company_os.kernel.execution_protocol import Denied, Unknown, canonical
from company_os.verification.runtime_verification import validate_expected


class VerificationReceiptStore:
    """Private, append-only local evidence; never canonical domain/acceptance."""

    def __init__(self, *, directory_fd, owner_uid, name="verification-receipts.sqlite"):
        if sys.platform != "linux" or os.geteuid() != owner_uid:
            raise Denied("ENROLLED_LINUX_RECEIPT_CUSTODIAN_REQUIRED")
        parent = os.fstat(directory_fd)
        if (
            type(owner_uid) is not int
            or owner_uid <= 0
            or parent.st_uid != owner_uid
            or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700
            or type(name) is not str
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
        ):
            raise Denied("PRIVATE_VERIFIER_RECEIPT_DIRECTORY_REQUIRED")
        self.directory = directory_fd
        self.uid = owner_uid
        self.name = name
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        except FileExistsError:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            value = os.fstat(fd)
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_uid != owner_uid
                or value.st_nlink != 1
                or stat.S_IMODE(value.st_mode) != 0o600
            ):
                raise Denied("PRIVATE_VERIFIER_RECEIPT_FILE_REQUIRED")
            self.identity = (value.st_dev, value.st_ino)
        finally:
            os.close(fd)
        self.path = "/proc/self/fd/" + str(directory_fd) + "/" + name
        with self._connect() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS receipts (expected_digest TEXT PRIMARY KEY, expected_json TEXT NOT NULL, report_json TEXT NOT NULL)"
            )

    def _connect(self):
        parent = os.fstat(self.directory)
        value = os.stat(self.name, dir_fd=self.directory, follow_symlinks=False)
        if (
            (value.st_dev, value.st_ino) != self.identity
            or value.st_nlink != 1
            or value.st_uid != self.uid
            or stat.S_IMODE(value.st_mode) != 0o600
            or parent.st_uid != self.uid
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise Denied("VERIFIER_RECEIPT_FILE_CHANGED")
        database = sqlite3.connect(self.path, timeout=2)
        try:
            database.execute("PRAGMA synchronous=FULL")
            after = os.stat(self.name, dir_fd=self.directory, follow_symlinks=False)
            if (after.st_dev, after.st_ino) != self.identity:
                raise Denied("VERIFIER_RECEIPT_FILE_CHANGED")
        except Exception:
            database.close()
            raise

        # sqlite Connection context managers do not close automatically.
        class Owned:
            def __enter__(self):
                return database

            def __exit__(self, kind, value, trace):
                try:
                    if kind is None:
                        database.commit()
                    else:
                        database.rollback()
                finally:
                    database.close()

        return Owned()

    def append(self, *, expected, report):
        validate_expected(expected)
        binding = canonical(expected)
        raw = canonical(report)
        if len(raw) > 65536 or report.get("expected") != expected:
            raise Denied("EXACT_BOUND_VERIFIER_REPORT_REQUIRED")
        try:
            with self._connect() as database:
                database.execute(
                    "INSERT INTO receipts VALUES(?,?,?)",
                    (hashlib.sha256(binding).hexdigest(), binding.decode(), raw.decode()),
                )
        except Exception:
            raise Unknown("VERIFIER_RECEIPT_COMMIT_UNCONFIRMED_NO_RETRY") from None

    def matches(self, *, expected, report):
        validate_expected(expected)
        binding = canonical(expected)
        with self._connect() as database:
            row = database.execute(
                "SELECT expected_json,report_json FROM receipts WHERE expected_digest=?",
                (hashlib.sha256(binding).hexdigest(),),
            ).fetchone()
        return row is not None and row == (binding.decode(), canonical(report).decode())


class SupervisorServiceHandler:
    def __init__(
        self,
        *,
        launch_observer,
        launch_validator,
        stop_observer,
        stop_validator,
        runtime_verifier,
        receipt_store,
        receipt_qualification,
    ):
        self.launch = launch_observer
        self.launch_validator = launch_validator
        self.stop = stop_observer
        self.stop_validator = stop_validator
        self.verifier = runtime_verifier
        self.store = receipt_store
        self.qualification = receipt_qualification
        self.launch_handle = None
        self.launch_close_failed = False
        self.lock = threading.Lock()

    def _observation(self, payload, descriptors):
        if set(payload) != {"observation"} or len(descriptors) != 1:
            raise Denied("EXACT_SERVICE_OBSERVATION_REQUIRED")
        observation = copy.deepcopy(payload["observation"])
        if type(observation) is not dict or set(observation) != {
            "pid",
            "host_boot_id",
            "cgroup_inode",
            "state",
        }:
            raise Denied("EXACT_SERVICE_OBSERVATION_REQUIRED")
        observation["pidfd"] = descriptors[0]
        return observation

    def _close_launch(self):
        if self.launch_close_failed:
            raise Unknown("SERVICE_LAUNCH_CLOSE_UNCONFIRMED_NO_RETRY")
        if self.launch_handle is not None:
            fd, self.launch_handle = self.launch_handle, None
            try:
                os.close(fd)
            except OSError:
                self.launch_close_failed = True
                raise Unknown("SERVICE_LAUNCH_CLOSE_UNCONFIRMED_NO_RETRY") from None

    def handle(self, operation, *, expected, payload, descriptors, deadline):
        with self.lock:
            if operation == "launch.observe":
                observation = self._observation(payload, descriptors)
                if self.launch_handle is not None:
                    raise Unknown("EXISTING_SERVICE_LAUNCH_OBSERVATION_NO_RETRY")
                self.launch_handle = os.dup(observation["pidfd"])
                observation["pidfd"] = self.launch_handle
                try:
                    return self.launch.observe(expected=expected, observation=observation)
                except Exception:
                    self._close_launch()
                    raise
            if operation == "launch.validate":
                if set(payload) != {"measured"}:
                    raise Denied("EXACT_SERVICE_VALIDATION_REQUIRED")
                try:
                    return dict(
                        valid=self.launch_validator.validate(payload["measured"], expected=expected)
                        is True
                    )
                finally:
                    self._close_launch()
            if operation == "stop.bind":
                self.stop.bind(
                    expected=expected, observation=self._observation(payload, descriptors)
                )
                return dict(bound=True)
            if operation == "stop.observe":
                if payload:
                    raise Denied("EMPTY_SERVICE_PAYLOAD_REQUIRED")
                return self.stop.observe(expected=expected)
            if operation == "stop.validate":
                if set(payload) != {"measured"}:
                    raise Denied("EXACT_SERVICE_VALIDATION_REQUIRED")
                return dict(
                    valid=self.stop_validator.validate(payload["measured"], expected=expected)
                    is True
                )
            if operation == "stop.close":
                if payload:
                    raise Denied("EMPTY_SERVICE_PAYLOAD_REQUIRED")
                self.stop.close()
                return dict(closed=True)
            if operation == "verification.run":
                if payload:
                    raise Denied("EMPTY_SERVICE_PAYLOAD_REQUIRED")
                report = self.verifier.verify(expected=expected, deadline=deadline)
                self.store.append(expected=expected, report=report)
                return report
            if operation == "verification.validate":
                if set(payload) != {"report"} or self.qualification is None:
                    raise Denied("ENROLLED_RECEIPT_READBACK_REQUIRED")
                report = payload["report"]
                validate_expected(expected)
                if (
                    self.qualification.validate(
                        expected=copy.deepcopy(expected),
                        phase="RECEIPT_READBACK",
                        candidate_digest=report.get("candidate_sha256"),
                        oracle_digest=report.get("oracle_sha256"),
                    )
                    is not True
                ):
                    raise Denied("RECEIPT_ENROLLMENT_BINDING_REJECTED")
                return dict(valid=self.store.matches(expected=expected, report=report))
            raise Denied("SERVICE_OPERATION_NOT_REGISTERED")

    def close(self):
        try:
            self._close_launch()
        finally:
            self.stop.close()


def _wire_observation(observation):
    return {key: observation[key] for key in ("pid", "host_boot_id", "cgroup_inode", "state")}


def _confirmed(value, key):
    return type(value) is dict and set(value) == {key} and value[key] is True


class RemoteLaunchObserver:
    def __init__(self, rpc):
        self.rpc = rpc

    def observe(self, *, expected, observation):
        return self.rpc.call(
            "launch.observe",
            expected=expected,
            payload=dict(observation=_wire_observation(observation)),
            descriptors=(observation["pidfd"],),
        )


class RemoteLaunchValidator:
    def __init__(self, rpc):
        self.rpc = rpc

    def validate(self, measured, *, expected):
        return _confirmed(
            self.rpc.call("launch.validate", expected=expected, payload=dict(measured=measured)),
            "valid",
        )


class RemoteStopObserver:
    def __init__(self, rpc):
        self.rpc = rpc
        self.expected = None
        self.closed = False
        self.close_failed = False

    def bind(self, *, expected, observation):
        if self.expected is not None or self.closed:
            raise Denied("REMOTE_STOP_ALREADY_BOUND_OR_CLOSED")
        self.expected = copy.deepcopy(expected)  # Retain scope even if the reply is lost.
        if not _confirmed(
            self.rpc.call(
                "stop.bind",
                expected=expected,
                payload=dict(observation=_wire_observation(observation)),
                descriptors=(observation["pidfd"],),
            ),
            "bound",
        ):
            raise Unknown("REMOTE_STOP_BIND_UNCONFIRMED")

    def observe(self, *, expected):
        if self.closed or self.expected != expected:
            raise Denied("REMOTE_STOP_SCOPE_MISMATCH")
        return self.rpc.call("stop.observe", expected=expected)

    def close(self):
        if self.close_failed:
            raise Unknown("REMOTE_STOP_CLOSE_UNCONFIRMED_NO_RETRY")
        if self.closed:
            return
        self.closed = True
        if self.expected is not None:
            try:
                if not _confirmed(self.rpc.call("stop.close", expected=self.expected), "closed"):
                    raise Unknown("REMOTE_STOP_CLOSE_UNCONFIRMED")
            except Exception:
                self.close_failed = True
                raise Unknown("REMOTE_STOP_CLOSE_UNCONFIRMED_NO_RETRY") from None


class RemoteStopValidator:
    def __init__(self, rpc):
        self.rpc = rpc

    def validate(self, measured, *, expected):
        return _confirmed(
            self.rpc.call("stop.validate", expected=expected, payload=dict(measured=measured)),
            "valid",
        )


class RemoteRuntimeVerifier:
    def __init__(self, rpc):
        self.rpc = rpc

    def verify(self, *, expected):
        validate_expected(expected)
        report = self.rpc.call("verification.run", expected=expected)
        if type(report) is not dict or report.get("expected") != expected:
            raise Denied("REMOTE_VERIFIER_BINDING_MISMATCH")
        return report


class RemoteReceiptValidator:
    def __init__(self, rpc):
        self.rpc = rpc

    def validate(self, report, *, expected):
        validate_expected(expected)
        return _confirmed(
            self.rpc.call("verification.validate", expected=expected, payload=dict(report=report)),
            "valid",
        )


def service_workflow(
    *,
    rpc,
    dispatcher,
    activation,
    reconciler,
    verification_pipeline,
    lease_registry,
    pilot_ports,
    expected_host_boot_id,
    expected_cgroup_inode,
    close_observation=None,
):
    """Explicit supervisor composition; construction opens no socket or process."""
    from company_os.composition.workflow import PilotWorkflow

    activation.observer = RemoteLaunchObserver(rpc)
    activation.validator = RemoteLaunchValidator(rpc)
    reconciler.observer = RemoteStopObserver(rpc)
    reconciler.validator = RemoteStopValidator(rpc)
    verification_pipeline.receipt_validator = RemoteReceiptValidator(rpc)
    return PilotWorkflow(
        dispatcher=dispatcher,
        activation=activation,
        reconciler=reconciler,
        verification_pipeline=verification_pipeline,
        runtime_verifier=RemoteRuntimeVerifier(rpc),
        lease_registry=lease_registry,
        pilot_ports=pilot_ports,
        expected_host_boot_id=expected_host_boot_id,
        expected_cgroup_inode=expected_cgroup_inode,
        close_observation=close_observation,
    )
