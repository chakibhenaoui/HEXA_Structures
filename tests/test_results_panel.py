from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from core.results import (
    ElementEnvelope,
    ElementResult,
    NodalResult,
    SurfaceResult,
)
from core.result_mapping import PlateRegionResult
from gui.widgets.results_panel import ResultsPanel
from gui.widgets.results_table_window import ResultsTableWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sample_results() -> dict[str, dict]:
    return {
        "ELU": {
            "displacements": {
                1: NodalResult(tag=1, ux=0.001, uy=0.0, uz=0.2),
                2: NodalResult(tag=2, ux=0.003, uy=0.0, uz=1.5),
            },
            "reactions": {
                1: NodalResult(tag=1, fx_reaction=10.0, fz_reaction=25.0),
            },
            "element_forces": {
                1: ElementResult(tag=1, n_i=5.0, n_j=-5.0, my_i=2.0, my_j=-2.0),
                2: ElementResult(tag=2, n_i=30.0, n_j=-30.0, my_i=12.0, my_j=-12.0),
            },
            "surface_results": {
                1: SurfaceResult(tag=1, mxx=4.5, myy=3.0, qx=1.2, qy=-1.2),
            },
            "result_context": {
                "surface_count": 1,
                "all_nodes_fixed": False,
                "surface_results_available": True,
            },
        },
    }


def _sample_envelopes() -> dict[int, ElementEnvelope]:
    return {
        1: ElementEnvelope(tag=1, n_min=-5.0, n_min_case="ELU", n_max=5.0, n_max_case="ELU"),
        2: ElementEnvelope(tag=2, n_min=-30.0, n_min_case="ELU", n_max=30.0, n_max_case="ELU"),
    }


def test_results_panel_sorts_numeric_columns() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(_sample_results())
    panel.show_result_type("displacements")

    table = panel.ui.tbl_displacements
    table.sortItems(3, Qt.DescendingOrder)

    assert table.item(0, 0).text() == "N2"
    assert table.item(1, 0).text() == "N1"


def test_results_panel_filters_current_table() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(_sample_results())
    panel.show_result_type("element_forces")
    panel._filter_edit.setText("E2")

    table = panel.ui.tbl_forces
    visible_rows = [row for row in range(table.rowCount()) if not table.isRowHidden(row)]

    assert visible_rows == [2, 3]
    assert table.item(2, 0).text() == "E2"
    assert table.item(3, 0).text() == "E2"


def test_results_panel_populates_surface_results_table() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(_sample_results())
    panel.show_result_type("surface_results")

    table = panel.ui.tbl_surface_results
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "S1"
    assert float(table.item(0, 4).data(Qt.UserRole)) == 4.5


def test_results_panel_populates_plate_region_results_table() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(
        {
            "Plaque": {
                "displacements": {},
                "reactions": {},
                "element_forces": {},
                "surface_results": {},
                "plate_results": {
                    1: PlateRegionResult(
                        tag=1,
                        uz_min=-0.012,
                        uz_max=0.001,
                        uz_min_node=5,
                        uz_max_node=1,
                        mxx_min=-3.0,
                        mxx_max=4.0,
                        fz_reaction_total=12.5,
                    )
                },
                "result_context": {"plate_region_count": 1},
            }
        }
    )
    panel.show_result_type("surface_results")

    table = panel.ui.tbl_surface_results
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "P1"
    assert float(table.item(0, 1).data(Qt.UserRole)) == -0.012
    assert "Noeud" not in [
        table.horizontalHeaderItem(index).text()
        for index in range(table.columnCount())
    ]
    assert float(table.item(0, 8).data(Qt.UserRole)) == 12.5


def test_results_tables_do_not_stretch_last_column() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(_sample_results())
    panel.show_result_type("displacements")

    table = panel.ui.tbl_displacements
    header = table.horizontalHeader()

    assert header.stretchLastSection() is False
    assert header.sectionResizeMode(table.columnCount() - 1) == QHeaderView.ResizeToContents


def test_results_window_wraps_panel_state() -> None:
    _app()
    window = ResultsTableWindow()
    window.set_all_results(_sample_results())
    window.set_envelopes(_sample_envelopes())
    window.set_current_case("ELU")
    window.show_result_type("envelopes")

    assert window.current_case() == "ELU"
    assert window.panel.ui.tbl_envelopes.rowCount() == 2


def test_results_panel_shows_context_message_for_surface_only_case() -> None:
    _app()
    panel = ResultsPanel()
    panel.set_all_results(
        {
            "Plaque": {
                "displacements": {
                    1: NodalResult(tag=1),
                    2: NodalResult(tag=2),
                    3: NodalResult(tag=3),
                    4: NodalResult(tag=4),
                },
                "reactions": {
                    1: NodalResult(tag=1, fz_reaction=5.0),
                },
                "element_forces": {},
                "surface_results": {},
                "result_context": {
                    "surface_count": 1,
                    "all_nodes_fixed": True,
                    "surface_results_available": False,
                },
            },
        }
    )

    assert panel._info_label.isHidden() is False
    info_text = panel._info_label.text().lower()
    assert "plaques" in info_text
    assert "déplacements nodaux peuvent donc être nuls" in info_text
