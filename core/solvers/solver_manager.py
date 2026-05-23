"""Solver discovery and capability management."""

from __future__ import annotations

from core.adapters.solvers.registry import (
    get_solver_plugin_id_map,
    get_solver_plugin_map,
    get_solver_plugins,
    has_any_module,
    package_version,
)
from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    CapabilityLevel,
    SolverEngine,
    SolverInfo,
)


class SolverManager:
    """Solver manager."""

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

    _PLUGIN_MAP = get_solver_plugin_map()
    _PLUGIN_ID_MAP = get_solver_plugin_id_map()

    def detect_engines(self) -> list[SolverInfo]:
        """Detect engines."""
        return [plugin.detect() for plugin in get_solver_plugins()]

    def is_available(self, engine: SolverEngine | str) -> bool:
        """Return whether available."""
        normalized = self._normalize_engine(engine)
        return any(
            info.engine == normalized and info.available
            for info in self.detect_engines()
        )

    def resolve_engine(self, requested: SolverEngine | str | None) -> SolverEngine:
        """Handle resolve engine."""
        preferred = self._normalize_engine(requested)
        if self.is_available(preferred):
            return preferred
        for plugin in get_solver_plugins():
            if plugin.engine != preferred and plugin.detect().available:
                return plugin.engine
        return SolverEngine.PYNITE

    def get_display_info(self) -> list[dict[str, str | bool]]:
        """Return display info."""
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
                    "id": info.solver_id or info.engine.value,
                    "engine": info.engine.value,
                    "text": f"{info.label} ({state})",
                    "tooltip": " • ".join(
                        [part for part in [", ".join(suffix) if suffix else "", info.install_hint] if part]
                    ),
                    "enabled": info.available,
                }
            )
        return rows

    def resolve_solver_id(self, requested: SolverEngine | str | None) -> str:
        """Resolve the effective solver plugin id to use."""
        preferred = self._plugin_for_request(requested)
        if preferred is not None and preferred.detect().available:
            return preferred.plugin_id

        for plugin in get_solver_plugins():
            if preferred is not None and plugin.plugin_id == preferred.plugin_id:
                continue
            if plugin.detect().available:
                return plugin.plugin_id

        return self._PLUGIN_MAP[SolverEngine.PYNITE].plugin_id

    def create_solver(self, project, requested: SolverEngine | str | None):
        """Instantiate a solver adapter and return its stable plugin id."""
        solver_id = self.resolve_solver_id(requested)
        plugin = self._PLUGIN_ID_MAP.get(
            solver_id,
            self._PLUGIN_MAP[SolverEngine.PYNITE],
        )
        return plugin.create(project), plugin.plugin_id

    def create_backend(self, project, requested: SolverEngine | str | None):
        """Instantiate the backend for the resolved engine."""
        solver, solver_id = self.create_solver(project, requested)
        plugin = self._PLUGIN_ID_MAP.get(
            solver_id,
            self._PLUGIN_MAP[SolverEngine.PYNITE],
        )
        return solver, plugin.engine

    def get_capabilities(
        self,
        engine: SolverEngine | str,
    ) -> dict[AnalysisFeature, AnalysisCapability]:
        """Return capabilities."""
        plugin = self._plugin_for_request(engine)
        if plugin is None:
            plugin = self._PLUGIN_MAP[SolverEngine.PYNITE]
        return plugin.capabilities

    def get_capabilities_for_solver(
        self,
        solver_id: str,
    ) -> dict[AnalysisFeature, AnalysisCapability]:
        """Return capabilities for a solver plugin id."""
        plugin = self._PLUGIN_ID_MAP.get(solver_id)
        if plugin is None:
            plugin = self._PLUGIN_MAP[SolverEngine.PYNITE]
        return plugin.capabilities

    def get_capability_matrix(self) -> list[dict[str, str]]:
        """Return capability matrix."""
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
        """Handle best engine for feature."""
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
        """Handle feature label."""
        return self.FEATURE_LABELS[feature]

    def capability_label(self, level: CapabilityLevel) -> str:
        """Handle capability label."""
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

    @classmethod
    def _plugin_for_request(cls, requested: SolverEngine | str | None):
        if isinstance(requested, SolverEngine):
            return cls._PLUGIN_MAP.get(requested)
        if not requested:
            return cls._PLUGIN_MAP.get(SolverEngine.PYNITE)

        solver_id = str(requested).strip().lower()
        plugin = cls._PLUGIN_ID_MAP.get(solver_id)
        if plugin is not None:
            return plugin

        try:
            return cls._PLUGIN_MAP.get(SolverEngine(solver_id))
        except ValueError:
            return None

    @staticmethod
    def _has_any_module(*module_names: str) -> bool:
        return has_any_module(*module_names)

    @staticmethod
    def _package_version(*package_names: str) -> str | None:
        return package_version(*package_names)
