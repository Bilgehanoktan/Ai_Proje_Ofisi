"""Minimum authenticated UI/readback ve kalıcı reload katmanı (10_UI).

Yetkiyi UI vermez. Her okuma r54_context_enter + r54_*_read ile aynı MVCC
statement içinde committed kaydı, source_digest, project_sequence,
authority_epoch ve access_audit_correlation alanlarını doğrular.

Canlı yerel önizleme için salt-okunur WSGI/HTTP sunucu desteği sunar.
"""

import html
import json
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from company_os.kernel import command_host as host
from company_os.kernel.command_host import Blocked
from company_os.projections.preview_generator import generate_preview_html
from company_os.projections.sse_stream import ProjectionEvent, stream_tenant_events
from company_os.workflows.templates import TEMPLATES

LIVE_EVENTS_HTML = Path(__file__).resolve().parents[4] / "frontend" / "live-events.html"

DETAIL_RESOURCES = (
    "attempts",
    "qualifications",
    "agent_runs",
    "tool_requests",
    "evidence",
    "acceptance_decisions",
)


def _require_auth(auth_map: dict, key: str) -> dict:
    if type(auth_map) is not dict or key not in auth_map:
        raise Blocked("UI_AUTH_REQUIRED")
    auth = auth_map[key]
    if (
        type(auth) is not dict
        or not auth.get("token")
        or not auth.get("project_id")
        or not auth.get("grant_id")
    ):
        raise Blocked("UI_AUTH_INCOMPLETE")
    return dict(auth)


class AuthenticatedReadbackApp:
    """Committed PostgreSQL kayıtlarını yetkili oturumlarla okuyan salt-okunur görünüm."""

    def __init__(self, *, connect):
        self.connect = connect

    def read_detail(
        self,
        auth: dict,
        resource: str,
        *,
        task_id: str,
        record_id: str,
        attempt_id: str | None = None,
        expected_digest: str | None = None,
        ui_generation: int = 0,
    ) -> dict:
        if resource not in DETAIL_RESOURCES:
            raise Blocked("UNSUPPORTED_DETAIL_RESOURCE")
        if type(auth) is not dict or not auth.get("token"):
            raise Blocked("UI_AUTH_REQUIRED")
        if type(ui_generation) is not int or ui_generation < 0:
            raise Blocked("INVALID_UI_GENERATION")
        req_auth = dict(
            token=auth["token"],
            project_id=auth["project_id"],
            kind="TASK",
            resource_id=str(task_id),
            task_id=str(task_id),
            grant_id=auth["grant_id"],
        )
        operation = f"candidate.r54.{resource}.read"
        args = [
            str(task_id),
            str(record_id),
            None if attempt_id is None else str(attempt_id),
            expected_digest,
            int(ui_generation),
        ]
        envelope = host.execute(self.connect(), req_auth, operation, args)
        res = envelope["result"]
        if (
            type(res) is not dict
            or "record" not in res
            or "source_digest" not in res
            or "project_sequence" not in res
            or "access_audit_correlation" not in res
        ):
            raise Blocked("CANONICAL_DETAIL_ENVELOPE_REQUIRED")
        return {
            "operation": operation,
            "envelope": res,
            "authorization_snapshot": envelope["snapshot"],
            "semantics": "COMMITTED_DB_READBACK_NOT_MEMORY_CACHE",
        }

    def load_workflow_view(
        self,
        auth_by_op: dict,
        *,
        task_id: str,
        attempt_id: str,
        qualification_id: str,
        process_run_id: str,
        tool_request_id: str,
        evidence_id: str,
        acceptance_id: str,
        ui_generation: int = 0,
        expected_digests: dict | None = None,
    ) -> dict:
        expected_digests = expected_digests or {}
        attempt_view = self.read_detail(
            _require_auth(auth_by_op, "attempts.read"),
            "attempts",
            task_id=task_id,
            record_id=attempt_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("attempts"),
            ui_generation=ui_generation,
        )
        qualification_view = self.read_detail(
            _require_auth(auth_by_op, "qualifications.read"),
            "qualifications",
            task_id=task_id,
            record_id=qualification_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("qualifications"),
            ui_generation=ui_generation,
        )
        agent_run_view = self.read_detail(
            _require_auth(auth_by_op, "agent_runs.read"),
            "agent_runs",
            task_id=task_id,
            record_id=process_run_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("agent_runs"),
            ui_generation=ui_generation,
        )
        tool_request_view = self.read_detail(
            _require_auth(auth_by_op, "tool_requests.read"),
            "tool_requests",
            task_id=task_id,
            record_id=tool_request_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("tool_requests"),
            ui_generation=ui_generation,
        )
        evidence_view = self.read_detail(
            _require_auth(auth_by_op, "evidence.read"),
            "evidence",
            task_id=task_id,
            record_id=evidence_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("evidence"),
            ui_generation=ui_generation,
        )
        acceptance_view = self.read_detail(
            _require_auth(auth_by_op, "acceptance_decisions.read"),
            "acceptance_decisions",
            task_id=task_id,
            record_id=acceptance_id,
            attempt_id=attempt_id,
            expected_digest=expected_digests.get("acceptance_decisions"),
            ui_generation=ui_generation,
        )
        return {
            "ui_generation": int(ui_generation),
            "semantics": "AUTHENTICATED_COMMITTED_KERNEL_READBACK",
            "task_id": str(task_id),
            "attempt": attempt_view,
            "qualification": qualification_view,
            "agent_run": agent_run_view,
            "tool_request": tool_request_view,
            "evidence": evidence_view,
            "acceptance_decision": acceptance_view,
            "digests": {
                "attempts": attempt_view["envelope"]["source_digest"],
                "qualifications": qualification_view["envelope"]["source_digest"],
                "agent_runs": agent_run_view["envelope"]["source_digest"],
                "tool_requests": tool_request_view["envelope"]["source_digest"],
                "evidence": evidence_view["envelope"]["source_digest"],
                "acceptance_decisions": acceptance_view["envelope"]["source_digest"],
            },
        }


def render_workflow_html(view: dict) -> str:
    if type(view) is not dict or view.get("semantics") != "AUTHENTICATED_COMMITTED_KERNEL_READBACK":
        raise Blocked("VALIDATED_WORKFLOW_VIEW_REQUIRED")
    attempt = view["attempt"]["envelope"]["record"]
    qual = view["qualification"]["envelope"]["record"]
    run = view["agent_run"]["envelope"]["record"]
    tr = view["tool_request"]["envelope"]["record"]
    ev = view["evidence"]["envelope"]["record"]
    acc = view["acceptance_decision"]["envelope"]["record"]
    def esc(v):
        return html.escape(str(v), quote=True)
    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        "<title>AI Proje Ofisi — Committed Kernel Readback</title></head><body>"
        f'<main data-ui-generation="{esc(view["ui_generation"])}" '
        f'data-task-id="{esc(view["task_id"])}" '
        'data-semantics="AUTHENTICATED_COMMITTED_KERNEL_READBACK">'
        f'<section id="attempt"><h2>Attempt</h2><p data-id="{esc(attempt["id"])}" '
        f'data-state="{esc(attempt["state"])}" data-fence="{esc(attempt["fencing_epoch"])}" '
        f'data-digest="{esc(view["digests"]["attempts"])}"></p></section>'
        f'<section id="qualification"><h2>Qualification</h2><p data-id="{esc(qual["id"])}" '
        f'data-role="{esc(qual["role_id"])}" '
        f'data-digest="{esc(view["digests"]["qualifications"])}"></p></section>'
        f'<section id="agent-run"><h2>Process Run</h2><p data-id="{esc(run["id"])}" '
        f'data-state="{esc(run["state"])}" data-revision="{esc(run["revision"])}" '
        f'data-digest="{esc(view["digests"]["agent_runs"])}"></p></section>'
        f'<section id="tool-request"><h2>Tool Request</h2><p data-id="{esc(tr["request_id"])}" '
        f'data-receipt="{esc(tr["receipt_id"])}" '
        f'data-digest="{esc(view["digests"]["tool_requests"])}"></p></section>'
        f'<section id="evidence"><h2>Evidence</h2><p data-id="{esc(ev["id"])}" '
        f'data-artifact="{esc(ev["artifact_id"])}" '
        f'data-digest="{esc(view["digests"]["evidence"])}"></p></section>'
        f'<section id="acceptance"><h2>Acceptance Decision</h2><p data-id="{esc(acc["id"])}" '
        f'data-accepted-by="{esc(acc["accepted_by"])}" '
        f'data-digest="{esc(view["digests"]["acceptance_decisions"])}"></p></section>'
        "</main></body></html>"
    )


def make_wsgi_app(
    *,
    static_view_fn=generate_preview_html,
    events_provider=None,
    catalog_provider=None,
    promotions_provider=None,
    effects_provider=None,
    live_snapshot_provider=None,
):
    """Returns a WSGI application serving dynamic read-only status, SSE stream, MOD-012..014 APIs, and live office snapshot."""

    def _json_response(start_response, payload: dict) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    def _require_tenant_id(environ, start_response) -> str | None:
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        tenant_id = (qs.get("tenant_id") or [""])[0].strip()
        if not tenant_id:
            start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
            return None
        return tenant_id

    def wsgi_app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET")

        if method != "GET":
            start_response(
                "405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8")]
            )
            return [b"Method Not Allowed: Read-only presentation service"]

        if path in ("/", "/index.html", "/preview"):
            content = static_view_fn().encode("utf-8")
            start_response(
                "200 OK",
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(content))),
                    ("Cache-Control", "no-cache, no-store, must-revalidate"),
                ],
            )
            return [content]

        if path == "/live-events":
            content = LIVE_EVENTS_HTML.read_bytes()
            start_response(
                "200 OK",
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(content))),
                    ("Cache-Control", "no-cache, no-store, must-revalidate"),
                ],
            )
            return [content]

        if path == "/api/status":
            from company_os.projections.preview_generator import parse_matrix_modules

            modules = parse_matrix_modules()
            body = json.dumps(
                {"status": "OK", "modules": modules}, ensure_ascii=False, indent=2
            ).encode("utf-8")
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        if path == "/api/work-types":
            specs = [
                {
                    "work_type": spec.work_type.value,
                    "template_id": spec.template_id,
                    "version": spec.version,
                    "stages": list(spec.stages),
                }
                for spec in TEMPLATES.values()
            ]
            body = json.dumps({"work_types": specs}, ensure_ascii=False).encode("utf-8")
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        if path == "/api/office-live":
            if live_snapshot_provider is not None:
                payload = live_snapshot_provider()
            else:
                payload = {"mode": "DEMO_SYNTHETIC", "connected": False}
            return _json_response(start_response, payload)

        if path == "/api/catalog":
            tenant_id = _require_tenant_id(environ, start_response)
            if tenant_id is None:
                return [b"tenant_id query parameter is required"]
            items = catalog_provider(tenant_id) if catalog_provider is not None else []
            return _json_response(start_response, {"tenant_id": tenant_id, "catalog": list(items)})

        if path == "/api/memory-promotions":
            tenant_id = _require_tenant_id(environ, start_response)
            if tenant_id is None:
                return [b"tenant_id query parameter is required"]
            items = promotions_provider(tenant_id) if promotions_provider is not None else []
            return _json_response(
                start_response, {"tenant_id": tenant_id, "promotions": list(items)}
            )

        if path == "/api/external-effects":
            tenant_id = _require_tenant_id(environ, start_response)
            if tenant_id is None:
                return [b"tenant_id query parameter is required"]
            items = effects_provider(tenant_id) if effects_provider is not None else []
            return _json_response(
                start_response, {"tenant_id": tenant_id, "external_effects": list(items)}
            )

        if path == "/api/events":
            qs = parse_qs(environ.get("QUERY_STRING", ""))
            tenant_id = (qs.get("tenant_id") or [""])[0].strip()
            if not tenant_id:
                start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
                return [b"tenant_id query parameter is required"]
            raw_last = environ.get("HTTP_LAST_EVENT_ID") or (qs.get("last_event_id") or ["0"])[0]
            try:
                last_event_id = int(raw_last)
            except ValueError:
                start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
                return [b"invalid last_event_id"]
            source_events = events_provider(tenant_id) if events_provider is not None else []
            frames = stream_tenant_events(
                source_events, tenant_id=tenant_id, last_event_id=last_event_id
            )
            body = "".join(frames).encode("utf-8")
            start_response(
                "200 OK",
                [
                    ("Content-Type", "text/event-stream; charset=utf-8"),
                    ("Cache-Control", "no-cache"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not Found"]

    return wsgi_app


def run_server(host_addr: str = "127.0.0.1", port: int = 8765):
    """Starts the local WSGI server for read-only preview."""
    app = make_wsgi_app()
    with make_server(host_addr, port, app) as httpd:
        print(f"AI Proje Ofisi V1 Sunucusu çalışıyor: http://{host_addr}:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nSunucu kapatıldı.")


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server("127.0.0.1", port)
