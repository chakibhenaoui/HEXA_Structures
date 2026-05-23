"""Port for project persistence adapters."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from core.model_data import ProjectModel


class ProjectRepositoryPort(Protocol):
    """Persistence contract for loading and saving project models."""

    def load(self, path: "str | Path") -> "ProjectModel":
        """Load a project from storage."""

    def save(self, project: "ProjectModel", path: "str | Path") -> None:
        """Persist a project to storage."""
