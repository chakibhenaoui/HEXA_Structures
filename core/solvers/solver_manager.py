"""
Gestionnaire central de détection des solveurs.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from core.optional_imports import ensure_external_module_search_paths
from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    CapabilityLevel,
    SolverEngine,
    SolverInfo,
)
from core.solvers.opensees_backend import OpenSeesBackend
from core.solvers.pynite_backend import PyNiteBackend


class SolverManager:
    """Détecte les solveurs installés et résout le moteur à utiliser."""

    FEATURE_LABELS = {
        AnalysisFeature.STATIC_LINEAR: "Statique linéaire",
        AnalysisFeature.MODAL: "Modale",
        AnalysisFeature.PDELTA: "P-Delta",
        AnalysisFeature.RESPONSE_SPECTRUM: "Sismique modal spectral",
        AnalysisFeature.PUSHOVER: "Pushover",
        AnalysisFeature.TIME_HISTORY: "Temps-histoire",
    }

    CAPABILITY_LABELS = {
        CapabilityLevel.READY: "Prêt",
        CapabilityLevel.ENGINE_ONLY: "Moteur capable",
        CapabilityLevel.PLANNED: "Prévu",
        CapabilityLevel.UNAVAILABLE: "Non prévu",
    }

    def detect_engines(self) -> list[SolverInfo]:
        """Retourne l'état des solveurs connus."""
        pynite_available = self._has_any_module("Pynite", "PyniteFEA")
        opensees_available = self._has_any_module("openseespy")

        return [
            SolverInfo(
                engine=SolverEngine.PYNITE,
                label="PyNite",
                available=pynite_available,
                version=self._package_version("PyNiteFEA", "pynitefea"),
                install_hint="pip install PyNiteFEA",
                is_default=True,
            ),
            SolverInfo(
                engine=SolverEngine.OPENSEES,
                label="OpenSeesPy",
                available=opensees_available,
                version=self._package_version("openseespy"),
                install_hint="pip install openseespy",
                is_default=False,
            ),
        ]

    def is_available(self, engine: SolverEngine | str) -> bool:
        """Indique si un solveur demande est disponible."""
        normalized = self._normalize_engine(engine)
        return any(
            info.engine == normalized and info.available
            for info in self.detect_engines()
        )

    def resolve_engine(self, requested: SolverEngine | str | None) -> SolverEngine:
        """Resout le moteur effectif à utiliser."""
        preferred = self._normalize_engine(requested)
        if self.is_available(preferred):
            return preferred
        if self.is_available(SolverEngine.PYNITE):
            return SolverEngine.PYNITE
        if self.is_available(SolverEngine.OPENSEES):
            return SolverEngine.OPENSEES
        return SolverEngine.PYNITE

    def get_display_info(self) -> list[dict[str, str | bool]]:
        """Retourne des metadonnées prétés pour la GUI."""
        rows: list[dict[str, str | bool]] = []
        for info in self.detect_engines():
            suffix = []
            if info.is_default:
                suffix.append("par défaut")
            if info.version:
                suffix.append(f"v{info.version}")
            state = "disponible" if info.available else "non installé"
            rows.append(
                {
                    "engine": info.engine.value,
                    "text": f"{info.label} ({state})",
                    "tooltip": " • ".join(
                        [part for part in [", ".join(suffix) if suffix else "", info.install_hint] if part]
                    ),
                    "enabled": info.available,
                }
            )
        return rows

    def create_backend(self, project, requested: SolverEngine | str | None):
        """Instancie le backend correspondant au moteur resolu."""
        engine = self.resolve_engine(requested)
        if engine == SolverEngine.PYNITE:
            return PyNiteBackend(project), engine
        return OpenSeesBackend(project), engine

    def get_capabilities(
        self,
        engine: SolverEngine | str,
    ) -> dict[AnalysisFeature, AnalysisCapability]:
        """Retourne la table des capacités connues pour un moteur."""
        normalized = self._normalize_engine(engine)
        if normalized == SolverEngine.PYNITE:
            return dict(PyNiteBackend.capabilities)
        return dict(OpenSeesBackend.capabilities)

    def get_capability_matrix(self) -> list[dict[str, str]]:
        """Retourne une matrice lisible des capacités par moteur."""
        rows: list[dict[str, str]] = []
        pynite_caps = self.get_capabilities(SolverEngine.PYNITE)
        opensees_caps = self.get_capabilities(SolverEngine.OPENSEES)

        for feature in AnalysisFeature:
            py_cap = pynite_caps[feature]
            os_cap = opensees_caps[feature]
            rows.append(
                {
                    "feature": feature.value,
                    "label": self.feature_label(feature),
                    "pynite": self.capability_label(py_cap.level),
                    "opensees": self.capability_label(os_cap.level),
                    "pynite_note": py_cap.note,
                    "opensees_note": os_cap.note,
                }
            )
        return rows

    def best_engine_for_feature(
        self,
        feature: AnalysisFeature,
        requested: SolverEngine | str | None = None,
    ) -> SolverEngine:
        """Retourne le meilleur moteur à utiliser pour une famille d'analyse."""
        preferred = self.resolve_engine(requested)
        preferred_cap = self.get_capabilities(preferred)[feature].level
        if preferred_cap in {CapabilityLevel.READY, CapabilityLevel.ENGINE_ONLY}:
            return preferred

        fallback = (
            SolverEngine.OPENSEES
            if preferred == SolverEngine.PYNITE
            else SolverEngine.PYNITE
        )
        fallback_cap = self.get_capabilities(fallback)[feature].level
        if fallback_cap in {CapabilityLevel.READY, CapabilityLevel.ENGINE_ONLY}:
            return fallback
        return preferred

    def feature_label(self, feature: AnalysisFeature) -> str:
        """Libellé utilisateur d'une famille d'analyse."""
        return self.FEATURE_LABELS[feature]

    def capability_label(self, level: CapabilityLevel) -> str:
        """Libellé utilisateur d'un niveau de capacité."""
        return self.CAPABILITY_LABELS[level]

    @staticmethod
    def _normalize_engine(engine: SolverEngine | str | None) -> SolverEngine:
        if isinstance(engine, SolverEngine):
            return engine
        if not engine:
            return SolverEngine.PYNITE
        try:
            return SolverEngine(str(engine).strip().lower())
        except ValueError:
            return SolverEngine.PYNITE

    @staticmethod
    def _has_any_module(*module_names: str) -> bool:
        return ensure_external_module_search_paths(*module_names)

    @staticmethod
    def _package_version(*package_names: str) -> str | None:
        for package_name in package_names:
            try:
                return version(package_name)
            except PackageNotFoundError:
                continue
        return None
