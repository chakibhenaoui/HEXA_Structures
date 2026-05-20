from __future__ import annotations

import sys

from config.settings import Settings
from core.solvers import (
    AnalysisFeature,
    CapabilityLevel,
    SolverEngine,
    SolverManager,
)


def test_default_solver_engine_is_pynite() -> None:
    assert Settings().analysis.solver_engine == "pynite"


def test_settings_roundtrip_preserves_solver_engine(tmp_path) -> None:
    settings = Settings()
    settings.analysis.solver_engine = "opensees"
    target = tmp_path / "settings.json"

    settings.save(target)
    loaded = Settings.load(target)

    assert loaded.analysis.solver_engine == "opensees"


def test_solver_manager_lists_supported_engines() -> None:
    manager = SolverManager()

    detected = manager.detect_engines()
    engines = [info.engine for info in detected]

    assert engines == [SolverEngine.PYNITE, SolverEngine.OPENSEES]


def test_solver_manager_resolves_to_available_engine() -> None:
    manager = SolverManager()

    resolved = manager.resolve_engine("pynite")

    assert resolved in {SolverEngine.PYNITE, SolverEngine.OPENSEES}


def test_solver_manager_detects_external_user_site_package(monkeypatch, tmp_path) -> None:
    module_name = "fake_hexa_external_solver"
    version_tag = f"Python{sys.version_info.major}{sys.version_info.minor}"
    site_packages = (
        tmp_path
        / "Programs"
        / "Python"
        / version_tag
        / "Lib"
        / "site-packages"
    )
    package_dir = site_packages / module_name
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    old_path = list(sys.path)
    sys.modules.pop(module_name, None)
    try:
        assert str(site_packages.resolve()) not in sys.path
        assert SolverManager._has_any_module(module_name) is True
        assert str(site_packages.resolve()) in sys.path

        imported = __import__(module_name)
        assert imported.VALUE == 42
    finally:
        sys.path[:] = old_path
        sys.modules.pop(module_name, None)


def test_solver_manager_creates_backend_for_resolved_engine() -> None:
    from core.model_data import ProjectModel

    manager = SolverManager()
    backend, engine = manager.create_backend(ProjectModel(), "pynite")

    assert engine in {SolverEngine.PYNITE, SolverEngine.OPENSEES}
    assert hasattr(backend, "run_static")


def test_capability_matrix_includes_modal_spectral_roadmap() -> None:
    manager = SolverManager()

    matrix = manager.get_capability_matrix()
    spectral = next(
        row for row in matrix
        if row["feature"] == AnalysisFeature.RESPONSE_SPECTRUM.value
    )

    assert spectral["pynite"] == manager.capability_label(CapabilityLevel.PLANNED)
    assert spectral["opensees"] == manager.capability_label(CapabilityLevel.ENGINE_ONLY)


def test_best_engine_prefers_opensees_for_pushover_if_requested_from_pynite() -> None:
    manager = SolverManager()

    engine = manager.best_engine_for_feature(
        AnalysisFeature.PUSHOVER,
        requested=SolverEngine.PYNITE,
    )

    assert engine == SolverEngine.OPENSEES
