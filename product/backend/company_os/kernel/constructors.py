"""Constructors adapter for objectives, plans, and tasks.

Maps to command_host.execute routes:
objectives.create -> r53_objectives_create
plans.create -> r54_plans_create
tasks.create -> r54_tasks_create
"""

from __future__ import annotations

import json
from typing import Any

from company_os.kernel import command_host


def create_objective(
    host: Any,
    auth: dict[str, Any],
    *,
    title: str,
    statement: str,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    constraints: list[str] | None = None,
    expected_outputs: list[str] | None = None,
) -> dict[str, Any]:
    project_id = auth.get("project_id") or auth.get("resource_id")
    idem = idempotency_key or auth.get("idempotency_key") or "idem-obj-default-01"
    corr = (
        correlation_id
        or request_id
        or auth.get("request_id")
        or "00000000-0000-4000-8000-000000000001"
    )
    payload: dict[str, Any] = {
        "idempotency_key": idem,
        "correlation_id": corr,
        "project_id": project_id,
        "goal": statement or title,
        "constraints": constraints if constraints is not None else [],
        "expected_outputs": expected_outputs if expected_outputs is not None else [],
    }
    args = [json.dumps(payload)]
    conn = getattr(host, "_conn", getattr(host, "conn", host))
    res = command_host.execute(conn, auth, "objectives.create", args)
    return res["result"]


def create_plan(
    host: Any,
    auth: dict[str, Any],
    *,
    objective_id: str,
    objective_revision: int,
    title: str,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    assumptions: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
) -> dict[str, Any]:
    project_id = auth.get("project_id") or auth.get("resource_id")
    idem = idempotency_key or auth.get("idempotency_key") or "idem-plan-default-01"
    corr = (
        correlation_id
        or request_id
        or auth.get("request_id")
        or "00000000-0000-4000-8000-000000000002"
    )
    payload: dict[str, Any] = {
        "idempotency_key": idem,
        "correlation_id": corr,
        "project_id": project_id,
        "objective_id": objective_id,
        "expected_revision": objective_revision,
        "assumptions": assumptions if assumptions is not None else [],
        "acceptance_criteria": acceptance_criteria if acceptance_criteria is not None else [],
    }
    args = [json.dumps(payload)]
    conn = getattr(host, "_conn", getattr(host, "conn", host))
    res = command_host.execute(conn, auth, "plans.create", args)
    return res["result"]


def create_task(
    host: Any,
    auth: dict[str, Any],
    *,
    plan_id: str,
    plan_revision: int,
    title: str,
    role_id: str,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    acceptance_criteria: list[str] | None = None,
) -> dict[str, Any]:
    project_id = auth.get("project_id") or auth.get("resource_id")
    idem = idempotency_key or auth.get("idempotency_key") or "idem-task-default-01"
    corr = (
        correlation_id
        or request_id
        or auth.get("request_id")
        or "00000000-0000-4000-8000-000000000003"
    )
    payload: dict[str, Any] = {
        "idempotency_key": idem,
        "correlation_id": corr,
        "project_id": project_id,
        "plan_id": plan_id,
        "title": title,
        "role_id": role_id,
        "acceptance_criteria": acceptance_criteria if acceptance_criteria is not None else [],
    }
    args = [json.dumps(payload)]
    conn = getattr(host, "_conn", getattr(host, "conn", host))
    res = command_host.execute(conn, auth, "tasks.create", args)
    return res["result"]
