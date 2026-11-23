"""Bounded Linux Unix-seqpacket RPC; no listener/service is created on import.

Peer UID checks are necessary, not enrollment or namespace qualification. Both
ends additionally require current trusted peer/scope validation. No pickle,
dynamic method names, shell execution, reconnect or automatic retry.
"""

import array
import copy
import json
import math
import os
import socket
import stat
import struct
import sys
import time
from uuid import uuid4

from company_os.kernel.execution_protocol import Denied, Unknown, canonical

PROTOCOL = "company.supervisor-rpc/1"
MAX_PACKET = 65536
OPERATIONS = frozenset(
    (
        "launch.observe",
        "launch.validate",
        "stop.bind",
        "stop.observe",
        "stop.validate",
        "stop.close",
        "verification.run",
        "verification.validate",
    )
)
ONESHOT = frozenset(("stop.bind", "verification.run"))


def _remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("SUPERVISOR_RPC_DEADLINE")
    return value


def _deadline(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise Denied("FINITE_SUPERVISOR_RPC_DEADLINE_REQUIRED")
    return time.monotonic() + timeout


def _peer(connection, *, own_uid, expected_peer_uid):
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise Denied("LINUX_PEER_CREDENTIALS_REQUIRED")
    if (
        type(own_uid) is not int
        or own_uid <= 0
        or type(expected_peer_uid) is not int
        or expected_peer_uid <= 0
        or own_uid == expected_peer_uid
    ):
        raise Denied("DISTINCT_ROOTLESS_RPC_IDENTITIES_REQUIRED")
    if (
        connection.family != socket.AF_UNIX
        or connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
    ):
        raise Denied("UNIX_SEQPACKET_REQUIRED")
    pid, uid, gid = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    )
    if uid != expected_peer_uid or pid <= 0:
        raise Denied("SUPERVISOR_RPC_PEER_IDENTITY_MISMATCH")
    return dict(pid=pid, uid=uid, gid=gid)


def _decode(raw):
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise Denied("DUPLICATE_RPC_KEY")
            value[key] = item
        return value

    if not raw or len(raw) > MAX_PACKET:
        raise Denied("BOUNDED_RPC_PACKET_REQUIRED")
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(Denied("NONFINITE_RPC_VALUE")),
        )
    except ValueError, UnicodeError:
        raise Denied("INVALID_RPC_JSON") from None
    if type(result) is not dict:
        raise Denied("RPC_OBJECT_REQUIRED")
    return result


def _receive(connection, deadline):
    connection.settimeout(_remaining(deadline))
    raw, ancillary, flags, _ = connection.recvmsg(
        MAX_PACKET + 1, socket.CMSG_SPACE(4 * array.array("i").itemsize), socket.MSG_CMSG_CLOEXEC
    )
    descriptors = []
    try:
        invalid_ancillary = False
        for level, kind, content in ancillary:
            if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                invalid_ancillary = True
                continue
            values = array.array("i")
            if len(content) % values.itemsize:
                raise Denied("INVALID_RPC_DESCRIPTOR_ARRAY")
            values.frombytes(content)
            descriptors.extend(values)
        if invalid_ancillary:
            raise Denied("ONLY_RPC_DESCRIPTOR_RIGHTS_ALLOWED")
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or len(descriptors) > 1:
            raise Denied("TRUNCATED_OR_EXCESS_RPC_PACKET")
        if not raw:
            raise Unknown("RPC_EOF_OUTCOME_UNCONFIRMED_NO_RETRY")
        result = _decode(raw)
        return result, descriptors
    except Exception:
        for fd in descriptors:
            os.close(fd)
        raise


def _send(connection, packet, deadline, descriptors=()):
    raw = canonical(packet)
    if len(raw) > MAX_PACKET or len(descriptors) > 1:
        raise Denied("BOUNDED_RPC_PACKET_REQUIRED")
    connection.settimeout(_remaining(deadline))
    ancillary = (
        []
        if not descriptors
        else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", descriptors))]
    )
    if connection.sendmsg([raw], ancillary) != len(raw):
        raise Unknown("PARTIAL_RPC_SEND_NO_RETRY")


class UnixEndpoint:
    """Connect under a trusted, pre-opened server-owned directory descriptor."""

    def __init__(self, *, directory_fd, name, server_uid):
        if (
            type(directory_fd) is not int
            or directory_fd < 3
            or type(name) is not str
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
        ):
            raise Denied("EXACT_RPC_ENDPOINT_SLOT_REQUIRED")
        self.directory = directory_fd
        self.name = name
        self.uid = server_uid

    def connect(self, *, timeout):
        parent = os.fstat(self.directory)
        entry = os.stat(self.name, dir_fd=self.directory, follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != self.uid
            or parent.st_mode & 0o022
            or not stat.S_ISSOCK(entry.st_mode)
            or entry.st_uid != self.uid
            or entry.st_mode & 0o007
        ):
            raise Denied("PRIVATE_ENROLLED_RPC_ENDPOINT_REQUIRED")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            connection.settimeout(timeout)
            connection.connect("/proc/self/fd/" + str(self.directory) + "/" + self.name)
            current = os.stat(self.name, dir_fd=self.directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (entry.st_dev, entry.st_ino):
                raise Denied("RPC_ENDPOINT_CHANGED")
            return connection
        except Exception:
            connection.close()
            raise


class PeerRpcClient:
    def __init__(
        self,
        *,
        endpoint,
        server_uid,
        peer_validator,
        timeout=10,
        uid_reader=os.geteuid if hasattr(os, "geteuid") else None,
    ):
        _deadline(timeout)
        self.endpoint = endpoint
        self.uid = server_uid
        self.validator = peer_validator
        self.timeout = timeout
        self.uid_reader = uid_reader
        self.last_peer = None

    def call(self, operation, *, expected, payload=None, descriptors=()):
        if operation not in OPERATIONS or self.validator is None or self.uid_reader is None:
            raise Denied("ENROLLED_RPC_OPERATION_REQUIRED")
        if type(expected) is not dict:
            raise Denied("EXACT_RPC_SCOPE_REQUIRED")
        deadline = _deadline(self.timeout)
        connection = self.endpoint.connect(timeout=_remaining(deadline))
        try:
            peer = _peer(connection, own_uid=self.uid_reader(), expected_peer_uid=self.uid)
            self.last_peer = copy.deepcopy(peer)
            if (
                self.validator.validate(
                    peer=copy.deepcopy(peer), operation=operation, expected=copy.deepcopy(expected)
                )
                is not True
            ):
                raise Denied("CURRENT_RPC_PEER_ENROLLMENT_REQUIRED")
            request_id = str(uuid4())
            _send(
                connection,
                dict(
                    protocol=PROTOCOL,
                    request_id=request_id,
                    operation=operation,
                    expected=expected,
                    payload={} if payload is None else payload,
                ),
                deadline,
                descriptors,
            )
            response, received = _receive(connection, deadline)
            try:
                if (
                    received
                    or set(response) != {"protocol", "request_id", "status", "result"}
                    or response["protocol"] != PROTOCOL
                    or response["request_id"] != request_id
                ):
                    raise Denied("EXACT_RPC_RESPONSE_REQUIRED")
                if (
                    self.validator.validate(
                        peer=copy.deepcopy(peer),
                        operation=operation,
                        expected=copy.deepcopy(expected),
                    )
                    is not True
                ):
                    raise Denied("RPC_PEER_ENROLLMENT_CHANGED")
                _remaining(deadline)
                if response["status"] != "OK":
                    raise Unknown("RPC_OPERATION_DENIED_OR_UNCERTAIN_NO_RETRY")
                return response["result"]
            finally:
                for fd in received:
                    os.close(fd)
        except TimeoutError, OSError:
            raise Unknown("RPC_OUTCOME_UNCONFIRMED_NO_RETRY") from None
        finally:
            connection.close()


class PeerRpcService:
    """Serve one accepted connection, under a separately configured OS identity.

    The supervisor owns socket creation, file permissions and process lifecycle.
    The service authenticates both current peer/scope and one-shot durable intent
    before invoking the fixed handler. It never imports client-selected code.
    """

    def __init__(
        self,
        *,
        client_uid,
        peer_validator,
        handler,
        journal,
        timeout=10,
        uid_reader=os.geteuid if hasattr(os, "geteuid") else None,
    ):
        _deadline(timeout)
        self.uid = client_uid
        self.validator = peer_validator
        self.handler = handler
        self.journal = journal
        self.timeout = timeout
        self.uid_reader = uid_reader

    def serve_connection(self, connection, *, deadline=None):
        deadline = (
            min(_deadline(self.timeout), deadline)
            if deadline is not None
            else _deadline(self.timeout)
        )
        descriptors = []
        try:
            if self.validator is None or self.uid_reader is None:
                raise Denied("CURRENT_RPC_PEER_ENROLLMENT_REQUIRED")
            peer = _peer(connection, own_uid=self.uid_reader(), expected_peer_uid=self.uid)
            request, descriptors = _receive(connection, deadline)
            if (
                set(request) != {"protocol", "request_id", "operation", "expected", "payload"}
                or request["protocol"] != PROTOCOL
                or request["operation"] not in OPERATIONS
                or type(request["expected"]) is not dict
                or type(request["payload"]) is not dict
            ):
                raise Denied("EXACT_RPC_REQUEST_REQUIRED")
            operation = request["operation"]
            expected = request["expected"]
            from uuid import UUID

            if (
                type(request["request_id"]) is not str
                or str(UUID(request["request_id"])) != request["request_id"]
            ):
                raise Denied("CANONICAL_RPC_REQUEST_ID_REQUIRED")
            if len(descriptors) != (1 if operation in {"launch.observe", "stop.bind"} else 0):
                raise Denied("EXACT_RPC_HANDLE_COUNT_REQUIRED")
            if (
                self.validator.validate(
                    peer=copy.deepcopy(peer), operation=operation, expected=copy.deepcopy(expected)
                )
                is not True
            ):
                raise Denied("CURRENT_RPC_PEER_ENROLLMENT_REQUIRED")
            if operation in ONESHOT:
                import hashlib

                identity = hashlib.sha256(canonical(expected)).hexdigest()
                self.journal.reserve(
                    "supervisor-rpc:" + operation,
                    identity,
                    dict(request_id=request["request_id"], expected=expected),
                )
            result = self.handler.handle(
                operation,
                expected=copy.deepcopy(expected),
                payload=copy.deepcopy(request["payload"]),
                descriptors=descriptors,
                deadline=deadline,
            )
            if (
                self.validator.validate(
                    peer=copy.deepcopy(peer), operation=operation, expected=copy.deepcopy(expected)
                )
                is not True
            ):
                raise Denied("RPC_PEER_ENROLLMENT_CHANGED")
            _send(
                connection,
                dict(
                    protocol=PROTOCOL, request_id=request["request_id"], status="OK", result=result
                ),
                deadline,
            )
        finally:
            # Received SCM_RIGHTS descriptors are owned by this request; handlers
            # retaining a pidfd must explicitly dup it (LinuxStopObserver does).
            failed = False
            for fd in descriptors:
                try:
                    os.close(fd)
                except OSError:
                    failed = True
            connection.close()
            if failed:
                raise Unknown("RPC_RECEIVED_HANDLE_CLOSE_UNCONFIRMED")

    def serve(self, listener, *, max_requests=32, total_timeout=30):
        if type(max_requests) is not int or not 1 <= max_requests <= 64:
            raise Denied("FINITE_RPC_REQUEST_COUNT_REQUIRED")
        deadline = _deadline(total_timeout)
        count = 0
        try:
            while count < max_requests:
                listener.settimeout(_remaining(deadline))
                connection, _ = listener.accept()
                self.serve_connection(connection, deadline=deadline)
                count += 1
            return dict(requests=count, outcome="REQUEST_LIMIT_REACHED_NOT_RUNTIME_ACCEPTANCE")
        finally:
            self.handler.close()
