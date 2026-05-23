"""Use case for mapping analysis results back to the user model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.application.ports import GeneratedPlateMeshPort
from core.result_mapping import map_analysis_results_to_user_results

if TYPE_CHECKING:
    from core.model_data import ProjectModel


@dataclass(frozen=True)
class MapResults:
    """Map solver-level results to user-visible results."""

    def execute(
        self,
        user_project: "ProjectModel",
        analysis_project: "ProjectModel",
        raw_results: dict,
        generated_plate_meshes: dict[int, GeneratedPlateMeshPort],
    ) -> dict:
        """Return user-facing results from analysis-level data."""
        return map_analysis_results_to_user_results(
            user_project=user_project,
            analysis_project=analysis_project,
            raw_results=raw_results,
            generated_plate_meshes=generated_plate_meshes,
        )
