"""MOD-008/MOD-009/MOD-013: Auditable verifier calibration thresholds across work types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifierCalibrationProfile:
    """Explicit, auditable verification bounds for SOFTWARE, RESEARCH, SPREADSHEET, and OBLIGATION."""

    min_software_oracle_pass_ratio: float = 1.0
    min_research_receipt_count: int = 1
    min_spreadsheet_cell_count: int = 1
    max_obligation_uncertainty_ratio: float = 0.25

    def __post_init__(self) -> None:
        if not (0.0 < self.min_software_oracle_pass_ratio <= 1.0):
            raise ValueError("INVALID_SOFTWARE_ORACLE_RATIO")
        if self.min_research_receipt_count < 1:
            raise ValueError("INVALID_RESEARCH_RECEIPT_COUNT")
        if self.min_spreadsheet_cell_count < 1:
            raise ValueError("INVALID_SPREADSHEET_CELL_COUNT")
        if not (0.0 <= self.max_obligation_uncertainty_ratio <= 1.0):
            raise ValueError("INVALID_OBLIGATION_UNCERTAINTY_RATIO")

    def check_work_type(
        self,
        work_type: str,
        *,
        passed_checks: int = 0,
        total_checks: int = 0,
        receipt_count: int = 0,
        cell_count: int = 0,
        uncertainty_ratio: float = 0.0,
    ) -> dict[str, object]:
        wt = (work_type or "").strip().upper()
        if wt == "SOFTWARE":
            ratio = (passed_checks / total_checks) if total_checks > 0 else 0.0
            ok = total_checks > 0 and ratio >= self.min_software_oracle_pass_ratio
            return {"work_type": wt, "accepted": ok, "oracle_ratio": ratio}
        if wt == "RESEARCH":
            ok = receipt_count >= self.min_research_receipt_count
            return {"work_type": wt, "accepted": ok, "receipt_count": receipt_count}
        if wt == "SPREADSHEET":
            ok = cell_count >= self.min_spreadsheet_cell_count
            return {"work_type": wt, "accepted": ok, "cell_count": cell_count}
        if wt == "OBLIGATION":
            ok = 0.0 <= uncertainty_ratio <= self.max_obligation_uncertainty_ratio
            return {"work_type": wt, "accepted": ok, "uncertainty_ratio": uncertainty_ratio}
        raise ValueError(f"UNSUPPORTED_WORK_TYPE:{wt}")
