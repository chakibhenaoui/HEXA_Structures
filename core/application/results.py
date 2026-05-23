"""Application-level analysis result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class AnalysisRunResult:
    """Typed wrapper around the legacy ``(success, dict)`` solver result.

    The payload intentionally remains a dict for now because the GUI and
    post-processing code already consume that shape. The wrapper gives future
    plugins a stable application contract without forcing an immediate rewrite
    of every result consumer.
    """

    success: bool
    payload: dict[str, Any] = field(default_factory=dict)
    analysis_type: str | None = None
    solver_id: str | None = None
    case_name: str | None = None

    @classmethod
    def from_legacy(
        cls,
        result: "AnalysisRunResult | tuple[bool, Mapping[str, Any] | dict]",
        *,
        analysis_type: str | None = None,
        solver_id: str | None = None,
        case_name: str | None = None,
    ) -> "AnalysisRunResult":
        """Normalize a legacy solver response into an application result."""
        if isinstance(result, cls):
            return replace(
                result,
                analysis_type=analysis_type or result.analysis_type,
                solver_id=solver_id or result.solver_id,
                case_name=case_name or result.case_name,
            )

        success, payload = result
        return cls(
            success=bool(success),
            payload=dict(payload or {}),
            analysis_type=analysis_type,
            solver_id=solver_id,
            case_name=case_name,
        )

    @property
    def error(self) -> str | None:
        """Return a normalized error message when available."""
        error = self.payload.get("error")
        return str(error) if error is not None else None

    def as_legacy(self) -> tuple[bool, dict[str, Any]]:
        """Return the legacy shape expected by existing GUI code."""
        return self.success, self.payload
