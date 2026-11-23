"""Live PostgreSQL 18.6 + HTTP WSGI E2E verification for MOD-011..MOD-014."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product/backend"))
sys.path.insert(0, str(ROOT / "contracts/source/python/packages"))

from company_os.api.http.app import make_wsgi_app  # noqa: E402
from company_os.budget.ledger import BudgetAndEffectLedger  # noqa: E402
from company_os.catalog.memory_promotion import (  # noqa: E402
    CatalogEntry,
    CatalogKind,
    ProductMemoryPromotionPipeline,
    TenantCatalogRegistry,
)
from company_os.projections.sse_stream import ProjectionEvent  # noqa: E402
from company_os.workflows.templates import WorkType, validate_work_output  # noqa: E402

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS mod_eval;
CREATE TABLE mod_eval.catalog_entries (
    tenant_id text NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    version text NOT NULL,
    digest text NOT NULL,
    PRIMARY KEY (tenant_id, kind, name, version)
);
CREATE TABLE mod_eval.memory_promotions (
    tenant_id text NOT NULL,
    record_id text NOT NULL,
    summary text NOT NULL,
    evidence_digest text NOT NULL,
    state text NOT NULL,
    verified_by text,
    promoted_by text,
    PRIMARY KEY (tenant_id, record_id)
);
CREATE TABLE mod_eval.work_validations (
    id serial PRIMARY KEY,
    work_type text NOT NULL,
    template_id text NOT NULL,
    validated boolean NOT NULL
);
CREATE TABLE mod_eval.budget_ledger (
    reservation_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    reserved_minor bigint NOT NULL CHECK (reserved_minor > 0),
    settled_minor bigint NOT NULL DEFAULT 0,
    state text NOT NULL
);
CREATE TABLE mod_eval.external_effects (
    idempotency_key text PRIMARY KEY,
    effect_id text NOT NULL,
    tenant_id text NOT NULL,
    provider text NOT NULL,
    status text NOT NULL
);
"""


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root Linux account is required")

    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool: str, *args: object, query: str | None = None) -> str:
        res = subprocess.run(
            [pg / "lib/postgresql/18/bin" / tool, *args],
            input=query,
            text=True,
            capture_output=True,
            timeout=60,
            env=env,
        )
        if res.returncode != 0:
            raise RuntimeError(f"{tool} failed: {res.stderr[-800:]}")
        return res.stdout.strip()

    @contextmanager
    def started(data: Path, socket: Path):
        socket.mkdir(mode=0o700)
        opts = f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700"
        try:
            run("pg_ctl", "-D", data, "-l", socket / "pg.log", "-o", opts, "-w", "start")
            yield
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

    def sql(socket: Path, query: str) -> str:
        return run("psql", "-X", "-h", socket, "-d", "postgres", "-Atq", "-v", "ON_ERROR_STOP=1", "-f", "-", query=query)

    # 1. Domain execution (MOD-012, MOD-013, MOD-014)
    reg = TenantCatalogRegistry()
    entry = CatalogEntry("t1", CatalogKind.MODEL, "qwen2.5-coder", "3b", "sha256:model3b")
    reg.register(entry)
    pipe = ProductMemoryPromotionPipeline()
    pipe.submit_candidate("t1", "mem-01", "Normalized title rule", "sha256:ev01")
    pipe.verify("t1", "mem-01", "verifier-1")
    promoted = pipe.promote("t1", "mem-01", "approver-1")

    validations = [
        validate_work_output(WorkType.RESEARCH, {"citations": [{"source_uri": "https://example.org/r1"}]}),
        validate_work_output(WorkType.SPREADSHEET, {"post_commit_verified": True, "workbook_digest": "sha256:wb1"}),
        validate_work_output(WorkType.OBLIGATION, {"uncertainty_ms": 25, "max_uncertainty_ms": 100}),
    ]

    ledger = BudgetAndEffectLedger(tenant_id="t1", budget_limit_minor=1000)
    r1 = ledger.reserve("res-1", 400)
    ledger.mark_unknown("res-1")
    ledger.settle("res-1", 320)
    eff = ledger.record_external_effect("eff-1", "idem-1", "webhook", "COMMITTED")

    # 2. Persist and readback on live PostgreSQL 18.6
    with tempfile.TemporaryDirectory(prefix="aipof-mod1214-") as tmpdir:
        work = Path(tmpdir)
        data, sock = work / "data", work / "sock"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(data, sock):
            sql(sock, SCHEMA_SQL)
            insert_sql = f"""
            INSERT INTO mod_eval.catalog_entries VALUES ('{entry.tenant_id}','{entry.kind.value}','{entry.name}','{entry.version}','{entry.digest}');
            INSERT INTO mod_eval.memory_promotions VALUES ('{promoted.tenant_id}','{promoted.record_id}','{promoted.summary}','{promoted.evidence_digest}','{promoted.state.value}','{promoted.verified_by}','{promoted.promoted_by}');
            INSERT INTO mod_eval.work_validations(work_type,template_id,validated) VALUES
                ('{validations[0]["work_type"]}','{validations[0]["template_id"]}',true),
                ('{validations[1]["work_type"]}','{validations[1]["template_id"]}',true),
                ('{validations[2]["work_type"]}','{validations[2]["template_id"]}',true);
            INSERT INTO mod_eval.budget_ledger VALUES ('{r1.reservation_id}','{r1.tenant_id}',{r1.reserved_minor},{r1.settled_minor},'{r1.state.value}');
            INSERT INTO mod_eval.external_effects VALUES ('{eff.idempotency_key}','{eff.effect_id}','{eff.tenant_id}','{eff.provider}','{eff.status}');
            """
            sql(sock, insert_sql)
            counts = json.loads(
                sql(
                    sock,
                    """SELECT json_build_object(
                        'catalog_entries', (SELECT count(*) FROM mod_eval.catalog_entries),
                        'memory_promotions', (SELECT count(*) FROM mod_eval.memory_promotions WHERE state='PROMOTED'),
                        'work_validations', (SELECT count(*) FROM mod_eval.work_validations WHERE validated=true),
                        'budget_settled_minor', (SELECT settled_minor FROM mod_eval.budget_ledger WHERE reservation_id='res-1'),
                        'external_effects', (SELECT count(*) FROM mod_eval.external_effects WHERE status='COMMITTED')
                    )::text;""",
                )
            )

    # 3. Live HTTP WSGI E2E for MOD-011 SSE + MOD-013 /api/work-types
    events = [
        ProjectionEvent(1, "t1", "MemoryPromoted", {"record_id": promoted.record_id}),
        ProjectionEvent(2, "t2", "SecretOtherTenant", {"record_id": "x"}),
        ProjectionEvent(3, "t1", "BudgetSettled", {"settled_minor": r1.settled_minor}),
    ]
    app = make_wsgi_app(events_provider=lambda _tid: events)
    httpd = make_server("127.0.0.1", 0, app)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/events?tenant_id=t1",
            headers={"Last-Event-ID": "1"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            sse_ct = resp.headers.get("Content-Type", "")
            sse_body = resp.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/work-types", timeout=5) as resp:
            wt_json = json.loads(resp.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert "text/event-stream" in sse_ct
    assert "event: BudgetSettled" in sse_body
    assert "SecretOtherTenant" not in sse_body
    assert len(wt_json["work_types"]) == 3

    print(
        json.dumps(
            {
                "pg_readback": counts,
                "http_sse_e2e": True,
                "http_work_types_count": len(wt_json["work_types"]),
                "G0": "OPEN",
                "first13": "0/13",
            }
        )
    )


if __name__ == "__main__":
    main()
