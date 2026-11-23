"""MOD-013: Research, Spreadsheet, and Obligation workflow templates and validators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class WorkType(str, Enum):
    RESEARCH = "RESEARCH"
    SPREADSHEET = "SPREADSHEET"
    OBLIGATION = "OBLIGATION"


@dataclass(frozen=True)
class WorkflowTemplateSpec:
    work_type: WorkType
    template_id: str
    version: str
    stages: tuple[str, ...]
    requires_citations: bool = False
    requires_post_commit_check: bool = False
    requires_time_uncertainty_bound: bool = False


RESEARCH_TEMPLATE = WorkflowTemplateSpec(
    work_type=WorkType.RESEARCH,
    template_id="WFT-RESEARCH-01",
    version="1.0.0",
    stages=("INTAKE", "SOURCE_COLLECTION", "SYNTHESIS", "CITATION_VERIFY", "ACCEPT"),
    requires_citations=True,
)

SPREADSHEET_TEMPLATE = WorkflowTemplateSpec(
    work_type=WorkType.SPREADSHEET,
    template_id="WFT-SPREADSHEET-01",
    version="1.0.0",
    stages=("INTAKE", "SCHEMA_BIND", "FORMULA_APPLY", "POST_COMMIT_VERIFY", "ACCEPT"),
    requires_post_commit_check=True,
)

OBLIGATION_TEMPLATE = WorkflowTemplateSpec(
    work_type=WorkType.OBLIGATION,
    template_id="WFT-OBLIGATION-01",
    version="1.0.0",
    stages=("INTAKE", "DEADLINE_EXTRACT", "UNCERTAINTY_BOUND", "VERIFY", "ACCEPT"),
    requires_time_uncertainty_bound=True,
)

TEMPLATES: dict[WorkType, WorkflowTemplateSpec] = {
    WorkType.RESEARCH: RESEARCH_TEMPLATE,
    WorkType.SPREADSHEET: SPREADSHEET_TEMPLATE,
    WorkType.OBLIGATION: OBLIGATION_TEMPLATE,
}


def validate_work_output(work_type: WorkType, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate MOD-013 work output against its template acceptance invariants."""
    spec = TEMPLATES[work_type]
    if spec.requires_citations:
        citations = payload.get("citations")
        if not isinstance(citations, list) or len(citations) == 0:
            raise ValueError("RESEARCH_CITATIONS_REQUIRED")
        if any(not isinstance(c, Mapping) or not c.get("source_uri") for c in citations):
            raise ValueError("RESEARCH_CITATION_URI_REQUIRED")

    if spec.requires_post_commit_check:
        if payload.get("post_commit_verified") is not True:
            raise ValueError("SPREADSHEET_POST_COMMIT_VERIFY_REQUIRED")
        if not payload.get("workbook_digest"):
            raise ValueError("SPREADSHEET_DIGEST_REQUIRED")

    if spec.requires_time_uncertainty_bound:
        uncertainty_ms = payload.get("uncertainty_ms")
        max_bound_ms = payload.get("max_uncertainty_ms")
        if not isinstance(uncertainty_ms, int) or uncertainty_ms < 0:
            raise ValueError("OBLIGATION_UNCERTAINTY_REQUIRED")
        if not isinstance(max_bound_ms, int) or uncertainty_ms > max_bound_ms:
            raise ValueError("OBLIGATION_UNCERTAINTY_EXCEEDED")

    return {
        "work_type": work_type.value,
        "template_id": spec.template_id,
        "version": spec.version,
        "validated": True,
    }
