"""Loopback task UI and bounded native command/readback transport.

No DB/session/model is created on import or by the default local server.
The enrolled supervisor supplies DB connections and session resolution. Native
context authorization and emission checks remain mandatory for every result.
"""

import base64
import copy
import hashlib
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

from packages.contracts.models import ObjectiveCreate, PlanCreate, TaskCreate

from company_os.api.http.app import DETAIL_RESOURCES
from company_os.kernel import command_host as host

ROOT = Path(__file__).resolve().parents[5] / "product/frontend"
MAX_BODY = 32768
CREATE_ROUTES = {
    "/api/objectives": (
        "objectives.create",
        ObjectiveCreate,
        frozenset({"goal", "constraints", "expected_outputs"}),
    ),
    "/api/plans": (
        "plans.create",
        PlanCreate,
        frozenset({"objective_id", "expected_revision", "assumptions", "acceptance_criteria"}),
    ),
    "/api/tasks": (
        "tasks.create",
        TaskCreate,
        frozenset({"plan_id", "title", "role_id", "acceptance_criteria", "depends_on"}),
    ),
}


class BadRequest(ValueError):
    pass


class SessionRequired(ValueError):
    pass


def canonical_id(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError()
    except TypeError, ValueError, AttributeError:
        raise BadRequest() from None
    return value


def decode_body(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BadRequest()
            result[key] = value
        return result

    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(BadRequest()),
        )
        if type(result) is not dict:
            raise BadRequest()
        return result
    except ValueError, UnicodeError, RecursionError:
        raise BadRequest() from None


class KernelTaskBackend:
    """No local task store; every operation goes through the existing Kernel."""

    def __init__(self, *, connect, resolve_session, emission_timeout, operations=()):
        if (
            not callable(connect)
            or not callable(resolve_session)
            or type(emission_timeout) not in (int, float)
            or not math.isfinite(emission_timeout)
            or not 0 < emission_timeout <= 5
        ):
            raise ValueError("BOUNDED_SUPERVISOR_BINDINGS_REQUIRED")
        self.connect = connect
        self.resolve_session = resolve_session
        self.emission_timeout = emission_timeout
        # Configuration describes available routes, never current user authority.
        self.operations = frozenset(operations)

    def connection_state(self):
        return dict(
            configured=True,
            execution_verified=False,
            can_create_objective="objectives.create" in self.operations,
            create_operations=sorted(self.operations & host.CONSTRUCTOR_OPERATIONS),
            detail_resources=sorted(
                resource
                for resource in DETAIL_RESOURCES
                if "candidate.r54." + resource + ".read" in self.operations
            ),
        )

    def prepare(self, bearer, path, body):
        read_command_id = None
        if path in CREATE_ROUTES:
            operation, model, fields = CREATE_ROUTES[path]
            if set(body) != fields | {"request_id"}:
                raise BadRequest()
            request_id = canonical_id(body["request_id"])
            for name in ("objective_id", "plan_id"):
                if name in body:
                    canonical_id(body[name])
        elif path == "/api/receipts":
            if set(body) != {"operation", "command_id", "request_id"}:
                raise BadRequest()
            operation = body["operation"]
            if type(operation) is not str or operation not in host.CONSTRUCTOR_OPERATIONS:
                raise BadRequest()
            read_command_id = canonical_id(body["command_id"])
            request_id = canonical_id(body["request_id"])
        elif path == "/api/details":
            if set(body) != {
                "resource",
                "task_id",
                "record_id",
                "attempt_id",
                "expected_digest",
                "ui_generation",
            }:
                raise BadRequest()
            if body["resource"] not in DETAIL_RESOURCES:
                raise BadRequest()
            for name in ("task_id", "record_id"):
                canonical_id(body[name])
            if body["attempt_id"] is not None:
                canonical_id(body["attempt_id"])
            digest = body["expected_digest"]
            if digest is not None and (
                type(digest) is not str
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise BadRequest()
            if (
                type(body["ui_generation"]) is not int
                or not 0 <= body["ui_generation"] <= 9007199254740991
            ):
                raise BadRequest()
            operation = "candidate.r54." + body["resource"] + ".read"
        else:
            raise BadRequest()
        if type(bearer) is not str or not 1 <= len(bearer) <= 8192:
            raise SessionRequired()
        auth = copy.deepcopy(self.resolve_session(bearer, operation))
        if (
            type(auth) is not dict
            or not auth.get("token")
            or not auth.get("grant_id")
            or not auth.get("project_id")
        ):
            raise SessionRequired()
        if path in CREATE_ROUTES or path == "/api/receipts":
            # Caller cannot select project/grant or submit arbitrary Kernel SQL.
            if auth.get("kind") != "PROJECT" or auth.get("resource_id") != auth["project_id"]:
                raise SessionRequired()
            args = []
            if read_command_id is None:
                try:
                    request = model(
                        project_id=auth["project_id"],
                        **{name: body[name] for name in fields},
                        idempotency_key="ui-"
                        + operation.split(".")[0].removesuffix("s")
                        + "-"
                        + request_id,
                        correlation_id=request_id,
                    )
                except ValueError:
                    raise BadRequest() from None
                args = [request.model_dump_json()]
        else:
            auth.update(kind="TASK", resource_id=body["task_id"], task_id=body["task_id"])
            args = [
                body["task_id"],
                body["record_id"],
                body["attempt_id"],
                body["expected_digest"],
                body["ui_generation"],
            ]
        if read_command_id is None:
            envelope = host.execute(self.connect(), auth, operation, args)
        else:
            envelope = host.execute(
                self.connect(), auth, operation, args, read_command_id=read_command_id
            )
            receipt = envelope.get("command_receipt")
            if type(receipt) is not dict or receipt.get("correlation_id") != request_id:
                raise host.Blocked("CONSTRUCTOR_CORRELATION_MISMATCH")
        if path == "/api/details":
            result = envelope.get("result")
            if type(result) is not dict or not {
                "record",
                "source_digest",
                "project_sequence",
                "authority_epoch",
                "access_audit_correlation",
            } <= set(result):
                raise host.Blocked("CANONICAL_DETAIL_ENVELOPE_REQUIRED")
        return auth, envelope

    def emit(self, prepared, socket):
        auth, envelope = prepared
        # Re-enter authority on a fresh connection and check before each bounded
        # send. Do not replace this with WSGI JSON serialization/cached results.
        return host.emit(
            self.connect(), auth, envelope, socket, self.emission_timeout, max_response_bytes=262144
        )


def create_project_backend(*, connect, project_id, grant_ids, emission_timeout):
    """Bind supervisor-owned scope refs; native Kernel validates every token.

    This creates no session/grant. A browser cannot choose the project or grant.
    The map contains existing grant IDs per operation, never grant permissions.
    """
    project_id = canonical_id(project_id)
    allowed = host.CONSTRUCTOR_OPERATIONS | {
        "candidate.r54." + resource + ".read" for resource in DETAIL_RESOURCES
    }
    if type(grant_ids) is not dict or not grant_ids or not set(grant_ids) <= allowed:
        raise ValueError("EXACT_UI_GRANT_BINDINGS_REQUIRED")
    pins = {operation: canonical_id(value) for operation, value in grant_ids.items()}

    def resolve(bearer, operation):
        if operation not in pins:
            raise SessionRequired()
        return dict(
            token=bearer,
            project_id=project_id,
            grant_id=pins[operation],
            kind="PROJECT",
            resource_id=project_id,
        )

    return KernelTaskBackend(
        connect=connect,
        resolve_session=resolve,
        emission_timeout=emission_timeout,
        operations=pins,
    )


def make_handler(backend=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # Never log bearer tokens or task bodies.

        def headers_for(self, code, content_type, csp=None):
            self.send_response(code)
            for key, value in [
                ("Content-Type", content_type),
                ("Cache-Control", "no-store"),
                ("Connection", "close"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
                (
                    "Content-Security-Policy",
                    csp
                    or "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                ),
            ]:
                self.send_header(key, value)
            self.end_headers()
            self.close_connection = True

        def error_json(self, code, error):
            self.headers_for(code, "application/json; charset=utf-8")
            self.wfile.write(json.dumps(dict(error=error), ensure_ascii=False).encode())

        def expected_host(self):
            return "127.0.0.1:" + str(self.server.server_port)

        def valid_host(self):
            return self.headers.get("Host") == self.expected_host()

        def do_GET(self):
            if not self.valid_host():
                return self.error_json(403, "ADDRESS_REJECTED")
            assets = {
                "/": "pages/tasks/index.html",
                "/tasks": "pages/tasks/index.html",
                "/tasks.js": "pages/tasks/tasks.js",
                "/tasks.css": "pages/tasks/tasks.css",
                "/progress.css": "assets/progress.css",
            }
            if self.path == "/progress":
                from company_os.projections.progress import render_progress_html

                self.headers_for(200, "text/html; charset=utf-8")
                self.wfile.write(render_progress_html().encode())
                return
            if self.path == "/api/connection":
                self.headers_for(200, "application/json; charset=utf-8")
                self.wfile.write(
                    json.dumps(
                        backend.connection_state()
                        if backend is not None
                        else dict(configured=False, execution_verified=False)
                    ).encode()
                )
                return
            if self.path == "/office":
                from company_os.projections.preview_generator import generate_preview_html

                # Existing source-aligned preview remains explicitly a preview.
                content = generate_preview_html().replace(
                    '<nav aria-label="Ana gezinme">',
                    '<nav aria-label="Ana gezinme"><a href="/tasks">Görevler</a><a href="/progress">İlerleme</a>',
                    1,
                )

                def hashes(tag):
                    return " ".join(
                        "'sha256-"
                        + base64.b64encode(hashlib.sha256(raw.encode()).digest()).decode()
                        + "'"
                        for raw in re.findall(
                            "<" + tag + r"[^>]*>(.*?)</" + tag + ">", content, re.S
                        )
                    )

                csp = (
                    "default-src 'self'; script-src 'self' "
                    + hashes("script")
                    + "; style-src 'self' "
                    + hashes("style")
                    + "; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
                )
                self.headers_for(200, "text/html; charset=utf-8", csp)
                self.wfile.write(content.encode())
                return
            if self.path not in assets:
                return self.error_json(404, "NOT_FOUND")
            name = assets[self.path]
            content_type = (
                "text/html"
                if name.endswith(".html")
                else ("text/css" if name.endswith(".css") else "text/javascript")
            )
            self.headers_for(200, content_type + "; charset=utf-8")
            self.wfile.write((ROOT / name).read_bytes())

        def do_POST(self):
            if (
                not self.valid_host()
                or self.headers.get("Origin") != "http://" + self.expected_host()
            ):
                return self.error_json(403, "ORIGIN_REJECTED")
            if self.path not in (*CREATE_ROUTES, "/api/details", "/api/receipts"):
                return self.error_json(404, "NOT_FOUND")
            if backend is None:
                # Closing with unread request bytes can reset the TCP stream on
                # Windows and hide the intended 503. Drain only a bounded,
                # unambiguous body; the connection already has a 5s timeout.
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") is None and len(lengths) == 1:
                    try:
                        length = int(lengths[0])
                        if 0 <= length <= MAX_BODY:
                            self.rfile.read(length)
                    except ValueError, OSError:
                        pass
                return self.error_json(503, "TASK_CONNECTION_NOT_CONFIGURED")
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return self.error_json(401, "SESSION_REQUIRED")
            if (
                self.headers.get("Transfer-Encoding") is not None
                or len(self.headers.get_all("Content-Length", [])) != 1
                or self.headers.get("Content-Type", "").lower() != "application/json"
            ):
                return self.error_json(400, "INVALID_REQUEST")
            try:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise BadRequest() from None
                if not 0 < length <= MAX_BODY:
                    raise BadRequest()
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise BadRequest()
                prepared = backend.prepare(auth_header[7:], self.path, decode_body(raw))
            except BadRequest:
                return self.error_json(400, "INVALID_REQUEST")
            except SessionRequired:
                return self.error_json(401, "SESSION_REQUIRED")
            except host.UnknownCommitOutcome:
                return self.error_json(409, "OUTCOME_UNKNOWN_DO_NOT_RESUBMIT")
            except host.Blocked:
                return self.error_json(403, "ACCESS_OR_COMMAND_REJECTED")
            except Exception:
                return self.error_json(503, "SERVICE_UNAVAILABLE")
            self.headers_for(200, "application/json; charset=utf-8")
            self.wfile.flush()
            try:
                backend.emit(prepared, self.connection)
            except Exception:
                # Headers or some bytes may already be sent. Close, never send a
                # second JSON result or retry the command/emission automatically.
                self.close_connection = True

    return Handler


def create_server(*, port=8766, backend=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("INVALID_LOCAL_PORT")
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(backend))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    with create_server(port=args.port) as server:
        print("Görev ekranı: http://127.0.0.1:" + str(server.server_port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
