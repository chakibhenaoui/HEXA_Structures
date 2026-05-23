"""Compatibility wrapper for building the temporary analysis model."""

from __future__ import annotations

from core.adapters.meshing import StructuredQuadPlateMesher
from core.application.use_cases.build_analysis_model import BuildAnalysisModel
from core.model_data import ProjectModel


def build_analysis_model(project: ProjectModel) -> ProjectModel:
    """Return a calculation-ready copy using the default plate mesher adapter."""
    return BuildAnalysisModel(StructuredQuadPlateMesher()).execute(project)
