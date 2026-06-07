from __future__ import annotations

import pytest

import core.sectionproperties_adapter as adapter
from core.sectionproperties_adapter import (
    SectionPropertiesCalculationError,
    SectionPropertiesUnavailable,
    calculate_polygon_sectionproperties_section,
    calculate_sectionproperties_section,
    is_sectionproperties_available,
    list_sectionproperty_shapes,
    sectionproperties_backend_info,
    validate_sectionproperty_dimensions,
)


def test_sectionproperties_shapes_are_generic_and_extensible() -> None:
    keys = [shape.key for shape in list_sectionproperty_shapes()]

    assert keys[:3] == ["rectangular", "circle", "i"]
    assert {"channel", "tee", "angle", "chs", "rhs"}.issubset(keys)


def test_sectionproperties_backend_info_reports_capabilities() -> None:
    info = sectionproperties_backend_info()
    keys = {capability.key for capability in info.capabilities}

    assert {
        "geometry_library",
        "mesh",
        "geometric",
        "warping",
        "frame",
        "plastic",
        "stress",
    }.issubset(keys)
    assert any(capability.implemented for capability in info.capabilities)
    if info.available:
        assert info.version
        assert "sectionproperties.pre.library" in info.modules
        assert "rectangular_section" in info.library_functions


def test_sectionproperties_validation_rejects_invalid_hollow_section() -> None:
    assert (
        validate_sectionproperty_dimensions(
            "chs",
            {"d": 0.10, "t": 0.06},
        )
        == "hollow_too_thick"
    )


def test_sectionproperties_missing_package_is_graceful(monkeypatch) -> None:
    monkeypatch.setattr(adapter, "find_spec", lambda name: None)

    assert is_sectionproperties_available() is False
    with pytest.raises(SectionPropertiesUnavailable):
        calculate_sectionproperties_section("rectangular", {"d": 0.30, "b": 0.20})
    with pytest.raises(SectionPropertiesUnavailable):
        calculate_polygon_sectionproperties_section(
            [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)]
        )


def test_sectionproperties_calculates_rectangle_properties() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")

    result = calculate_sectionproperties_section(
        "rectangular",
        {"d": 0.30, "b": 0.20},
        mesh_area=1.0e-4,
    )

    assert result.area == pytest.approx(0.06)
    assert result.inertia_y == pytest.approx(0.20 * 0.30**3 / 12.0, rel=1e-6)
    assert result.inertia_z == pytest.approx(0.30 * 0.20**3 / 12.0, rel=1e-6)
    assert result.torsion_constant > 0.0
    assert result.properties["source"] == "sectionproperties"
    assert result.properties["display_type"] == "rectangular"


def test_sectionproperties_calculates_custom_polygon_mesh() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")

    result = calculate_polygon_sectionproperties_section(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        mesh_area=1.0e-3,
    )

    assert result.area == pytest.approx(0.06)
    assert result.inertia_y == pytest.approx(0.20 * 0.30**3 / 12.0, rel=1e-6)
    assert result.inertia_z == pytest.approx(0.30 * 0.20**3 / 12.0, rel=1e-6)
    assert result.mesh is not None
    assert len(result.mesh.vertices) > 4
    assert len(result.mesh.triangles) > 1
    assert result.properties["shape"] == "custom_polygon"


def test_sectionproperties_calculates_polygon_with_hole() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")

    result = calculate_polygon_sectionproperties_section(
        [(0.0, 0.0), (0.30, 0.0), (0.30, 0.30), (0.0, 0.30)],
        holes=[[(0.10, 0.10), (0.20, 0.10), (0.20, 0.20), (0.10, 0.20)]],
        mesh_area=1.0e-3,
    )

    assert result.area == pytest.approx(0.08, rel=1e-6)
    assert result.inertia_y == pytest.approx(
        0.30 * 0.30**3 / 12.0 - 0.10 * 0.10**3 / 12.0,
        rel=1e-5,
    )
    assert result.inertia_z == pytest.approx(
        0.30 * 0.30**3 / 12.0 - 0.10 * 0.10**3 / 12.0,
        rel=1e-5,
    )
    assert result.properties["holes"]
    assert result.mesh is not None


def test_sectionproperties_rejects_hole_outside_polygon() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")

    with pytest.raises(SectionPropertiesCalculationError):
        calculate_polygon_sectionproperties_section(
            [(0.0, 0.0), (0.30, 0.0), (0.30, 0.30), (0.0, 0.30)],
            holes=[[(0.40, 0.40), (0.50, 0.40), (0.50, 0.50), (0.40, 0.50)]],
            mesh_area=1.0e-3,
        )
