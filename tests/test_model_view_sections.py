from __future__ import annotations

import math
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from core.sections import TSection, get_profile

pytest.importorskip("pyvista")
pytest.importorskip("pyvistaqt")

from gui.widgets.model_view import ModelView


def test_rectangular_section_polygon_uses_real_dimensions() -> None:
    polygon = ModelView._section_polygon_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert polygon is not None
    assert polygon.shape == (4, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.30)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), 0.50)


def test_t_section_polygon_uses_web_and_flange_dimensions() -> None:
    polygon = ModelView._section_polygon_points(
        "T",
        {"bw": 0.25, "hw": 0.40, "bf": 0.80, "hf": 0.12},
    )

    assert polygon is not None
    t_section = TSection(bw=0.25, hw=0.40, bf=0.80, hf=0.12)
    assert polygon.shape == (8, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.80)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), t_section.h)
    assert np.isclose(polygon[:, 1].min(), -t_section.centroid_y)


def test_i_profile_polygon_uses_catalog_dimensions() -> None:
    profile = get_profile("IPE 300")
    polygon = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert polygon is not None
    assert polygon.shape == (12, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), profile.b)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), profile.h)

    half_web = profile.tw / 2.0
    assert np.isclose(np.abs(polygon[:, 0]), half_web).any()


def test_i_profile_guide_points_use_web_flange_corners() -> None:
    profile = get_profile("IPE 300")
    guides = ModelView._section_guide_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert guides.shape == (4, 2)
    assert np.allclose(np.unique(np.abs(guides[:, 0])), [profile.tw / 2.0])
    assert np.allclose(np.unique(np.abs(guides[:, 1])), [profile.h / 2.0 - profile.tf])


def test_i_profile_fillet_guides_are_offset_from_web_knees() -> None:
    profile = get_profile("IPE 300")
    guides = ModelView._section_fillet_guide_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert guides.shape == (4, 2)
    assert np.all(np.abs(guides[:, 0]) > profile.tw / 2.0)
    assert np.all(np.abs(guides[:, 1]) < (profile.h / 2.0 - profile.tf))


def test_non_i_profile_has_no_section_guides() -> None:
    guides = ModelView._section_guide_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert guides.shape == (0, 2)

    fillet_guides = ModelView._section_fillet_guide_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert fillet_guides.shape == (0, 2)


def test_section_rgb_scalars_match_merged_cell_count() -> None:
    mesh = SimpleNamespace(n_cells=5, cell_data={})
    colors = [
        np.tile(np.array([10, 20, 30], dtype=np.uint8), (2, 1)),
        np.tile(np.array([40, 50, 60], dtype=np.uint8), (1, 1)),
    ]

    ModelView._ensure_section_rgb_scalars(mesh, colors)

    assert mesh.cell_data["section_rgb"].shape == (5, 3)
