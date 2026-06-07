from __future__ import annotations

import os
import sys
import types
import unicodedata

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMenu, QTabWidget, QWidget

from config.settings import Settings
from core.model_data import ProjectModel
from gui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _normalize_label(text: str) -> str:
    try:
        text = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def test_primary_toolbar_contains_main_actions() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)

    action_names = {
        "act_new": "Nouveau",
        "act_open": "Ouvrir",
        "act_save": "Enregistrer",
        "act_undo_model": "Annuler",
        "act_redo_model": "Rétablir",
        "act_copy_selection": "Copier",
        "act_define_grid": "Grille",
        "act_select_tool": "Sélection",
        "act_draw_node": "Nœud",
        "act_draw_bars": "Barres",
        "act_draw_surface": "Surface",
        "act_draw_orthogonal": "Orthogonal",
        "act_cancel_draw": "Annuler dessin",
        "act_add_node": "Ajouter un nœud",
        "act_add_element": "Ajouter barre",
        "act_run": "Analyser",
        "act_res_deformed": "Déformée",
        "act_view_iso": "Iso",
        "act_view_xy": "XY",
        "act_view_xz": "XZ",
        "act_view_yz": "YZ",
    }
    for attr, text in action_names.items():
        setattr(window, attr, QAction(text, window))

    window._setup_primary_toolbar()

    toolbar_texts = [action.text() for action in window.toolbar_primary.actions() if action.text()]
    assert toolbar_texts[:3] == ["Nouveau", "Ouvrir", "Enregistrer"]
    assert "Grille" in toolbar_texts
    assert "Barres" in toolbar_texts
    assert "Surface" in toolbar_texts
    assert "Analyser" in toolbar_texts
    assert "Déformée" in toolbar_texts
    assert "YZ" in toolbar_texts
    assert window.toolbar_primary.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert window.act_new.toolTip() == "Nouveau"
    assert window.act_draw_bars.toolTip() == "Barres"
    assert window.act_draw_surface.toolTip() == "Surface"
    assert not window.act_run.icon().isNull()


def test_create_view_widget_exists_and_configures_model_view(monkeypatch) -> None:
    _app()

    class FakeModelView(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.show_node_tags = None
            self.show_section_names = None
            self.show_extruded_sections = None
            self.show_local_axes = None

    fake_module = types.ModuleType("gui.widgets.model_view")
    fake_module.ModelView = FakeModelView
    monkeypatch.setitem(sys.modules, "gui.widgets.model_view", fake_module)

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.settings = Settings()
    window.settings.gui.show_node_tags = False
    window.settings.gui.show_section_names = True
    window.settings.gui.show_extruded_sections = False
    window.settings.gui.show_local_axes = True
    window.model_view = None

    widget = window._create_view_widget()

    assert isinstance(widget, FakeModelView)
    assert window.model_view is widget
    assert widget.show_node_tags is False
    assert widget.show_section_names is True
    assert widget.show_extruded_sections is False
    assert widget.show_local_axes is True


def test_window_title_uses_file_stem_when_project_name_is_default(tmp_path) -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.project = ProjectModel()
    window.project.file_path = str(tmp_path / "portique_test.db")
    window._modified = False

    window._update_title()

    assert "portique_test" in window.windowTitle()
    assert "Nouveau projet" not in window.windowTitle()


def test_context_roll_action_applies_to_selected_elements() -> None:
    _app()
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(10.0, 0.0, 0.0)
    project.add_section("IPE 300", "I_profile", 1)
    project.add_element(1, 2, section_tag=1)
    project.add_element(2, 3, section_tag=1)

    class DummyProperties:
        def __init__(self) -> None:
            self.cleared = False

        def clear_display(self) -> None:
            self.cleared = True

        def show_element(self, _tag: int) -> None:
            self.cleared = False

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.project = project
    window.properties = DummyProperties()
    window._selected_node_tags = []
    window._selected_element_tags = [1, 2]
    window._selected_surface_tags = []
    window._mark_project_modified = lambda: None
    window._refresh = lambda preserve_view=False: None
    window._log = lambda _message: None

    window._set_selected_elements_roll_angle(90.0, context_tag=1)

    assert project.elements[1].roll_angle_deg == 90.0
    assert project.elements[2].roll_angle_deg == 90.0
    assert project.sections[1].name == "IPE 300"
    assert window.properties.cleared is True


def test_window_title_keeps_custom_project_name_over_file_path(tmp_path) -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.project = ProjectModel(name="Projet client A")
    window.project.file_path = str(tmp_path / "portique_test.db")
    window._modified = True

    window._update_title()

    assert "Projet client A *" in window.windowTitle()
    assert "portique_test" not in window.windowTitle()


def test_menu_bar_order_and_model_boundary_action() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)

    menubar = window.menuBar()
    window.menu_file = QMenu("Fichier", menubar)
    window.menu_edit = None
    window.menu_model = QMenu("Modele", menubar)
    window.menu_view = QMenu("Vue", menubar)
    window.menu_charges = None
    window.menu_analysis = QMenu("Analyse", menubar)
    window.menu_results = QMenu("Resultats", menubar)
    window.menu_settings = None
    window.menu_help = QMenu("Aide", menubar)

    for menu in (
        window.menu_file,
        window.menu_model,
        window.menu_view,
        window.menu_analysis,
        window.menu_results,
        window.menu_help,
    ):
        menubar.addMenu(menu)

    action_names = {
        "act_undo_model": "Annuler",
        "act_redo_model": "Rétablir",
        "act_copy_selection": "Copier",
        "act_add_node": "Ajouter un nœud",
        "act_add_material": "Ajouter matériau",
        "act_add_section": "Ajouter section",
        "act_add_element": "Ajouter barre",
        "act_boundary": "Conditions aux limites",
        "act_add_load": "Cas de charge",
        "act_define_loads": "Définir charges",
        "act_gen_combos": "Combinaisons",
    }
    for attr, text in action_names.items():
        setattr(window, attr, QAction(text, window))

    window.project = ProjectModel()
    window._draw_start_point = None
    window._selected_existing_node_tags = lambda: []
    window._selected_existing_element_tags = lambda: []
    window.act_show_assigned_loads = QAction("Afficher charges", window)

    window._setup_menu_bar_structure()
    window._setup_edit_menu()
    window._setup_model_management_menus()
    window._setup_charges_menu()
    window._setup_menu_bar_structure()

    top_level_titles = [_normalize_label(action.text()) for action in menubar.actions()]
    assert top_level_titles == [
        "fichier",
        "edition",
        "modele",
        "vue",
        "charges",
        "analyse",
        "resultats",
        "parametres",
        "aide",
    ]

    model_action_titles = [
        _normalize_label(action.text())
        for action in window.menu_model.actions()
        if not action.isSeparator()
    ]
    assert "conditions aux limites" in model_action_titles
    assert any("section builder" in title for title in model_action_titles)
    assert not any("sectionproperties" in title for title in model_action_titles)
    assert any("surface" in title for title in model_action_titles)
    assert any("plaque" in title for title in model_action_titles)
    assert any(title.startswith("modifier la surface") for title in model_action_titles)
    assert not any(title.startswith("dupliquer la selection de surfaces") for title in model_action_titles)
    assert not any(title.startswith("supprimer la selection de surfaces") for title in model_action_titles)
    assert "édition" not in model_action_titles
    assert "chargements" not in model_action_titles

    charges_action_titles = [
        _normalize_label(action.text())
        for action in window.menu_charges.actions()
        if not action.isSeparator()
    ]
    assert "cas de charge" in charges_action_titles
    assert "combinaisons" in charges_action_titles


def test_view_menu_contains_local_axes_toggle() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.menu_view = QMenu("Vue", window)

    for attr, text in {
        "act_view_xy": "XY",
        "act_view_xz": "XZ",
        "act_view_yz": "YZ",
        "act_view_iso": "Iso",
        "act_show_node_tags": "Noeuds",
        "act_show_section_names": "Sections",
        "act_show_extruded_sections": "Sections 3D",
        "act_show_local_axes": "Repere local",
        "act_toggle_split_view": "Deux vues",
    }.items():
        action = QAction(text, window)
        if attr.startswith("act_show"):
            action.setCheckable(True)
        setattr(window, attr, action)

    window.dock_tree = QDockWidget("Arbre", window)
    window.dock_properties = QDockWidget("Proprietes", window)
    window.dock_bottom = QDockWidget("Infos", window)

    window._setup_view_menu()

    display_titles = [
        _normalize_label(action.text())
        for action in window.menu_view_display.actions()
        if not action.isSeparator()
    ]
    assert "repere local" in display_titles
    assert window.act_show_local_axes.isCheckable()


def test_toggle_local_axes_updates_model_views() -> None:
    _app()

    class DummyView:
        def __init__(self) -> None:
            self.show_local_axes = False
            self.selection_refreshes = 0

        def _update_selection_actors(self, render: bool = True) -> None:
            self.selection_refreshes += 1

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.settings = Settings()
    window.model_view = DummyView()
    window.secondary_view = DummyView()
    window.refresh_preserve_view = None
    window._refresh = lambda preserve_view=False: setattr(
        window,
        "refresh_preserve_view",
        preserve_view,
    )

    window._on_toggle_local_axes(True)

    assert window.settings.gui.show_local_axes is True
    assert window.model_view.show_local_axes is True
    assert window.secondary_view.show_local_axes is True
    assert window.model_view.selection_refreshes == 1
    assert window.secondary_view.selection_refreshes == 1
    assert window.refresh_preserve_view is True


def test_remove_duplicate_bottom_tabs_keeps_single_combinations_tab() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)

    window.tab_bottom = QTabWidget()
    console = QWidget()
    result_placeholder = QWidget()
    node_placeholder = QWidget()
    combo_placeholder = QWidget()
    window.results_panel = QWidget()
    window.node_table = QWidget()
    window.combo_table = QWidget()

    window.tab_bottom.addTab(console, "Console")
    window.tab_bottom.addTab(result_placeholder, "Resultats")
    window.tab_bottom.addTab(window.results_panel, "Resultats")
    window.tab_bottom.addTab(node_placeholder, "Noeuds")
    window.tab_bottom.addTab(window.node_table, "Noeuds")
    window.tab_bottom.addTab(combo_placeholder, "Combinaisons")
    window.tab_bottom.addTab(window.combo_table, "Combinaisons")

    window._remove_duplicate_bottom_tabs()

    titles = [window.tab_bottom.tabText(i) for i in range(window.tab_bottom.count())]
    assert titles.count("Resultats") == 1
    assert titles.count("Noeuds") == 1
    assert titles.count("Combinaisons") == 1
    assert window.tab_bottom.indexOf(window.combo_table) >= 0


def test_bottom_placeholder_replacement_handles_reparented_tabs_and_accents() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)

    window.ui = QWidget()
    window.tab_bottom = QTabWidget()
    console = QWidget()
    result_placeholder = QWidget()
    result_placeholder.setObjectName("results_tab_placeholder")
    node_placeholder = QWidget()
    node_placeholder.setObjectName("nodes_tab_placeholder")
    combo_placeholder = QWidget()
    combo_placeholder.setObjectName("combos_tab_placeholder")
    window.results_panel = QWidget()
    window.node_table = QWidget()
    window.combo_table = QWidget()

    window.tab_bottom.addTab(console, "Console")
    window.tab_bottom.addTab(result_placeholder, "Résultats")
    window.tab_bottom.addTab(node_placeholder, "Noeuds")
    window.tab_bottom.addTab(combo_placeholder, "Combinaisons")

    window._replace_bottom_placeholder(
        "results_tab_placeholder",
        window.results_panel,
        "Résultats",
        fallback_index=1,
    )
    window._replace_bottom_placeholder(
        "nodes_tab_placeholder",
        window.node_table,
        "Nœuds",
        fallback_index=2,
    )
    window._replace_bottom_placeholder(
        "combos_tab_placeholder",
        window.combo_table,
        "Combinaisons",
        fallback_index=3,
    )
    window._remove_duplicate_bottom_tabs()

    titles = [window.tab_bottom.tabText(i) for i in range(window.tab_bottom.count())]
    assert titles == ["Console", "Résultats", "Nœuds", "Combinaisons"]
    assert window.tab_bottom.indexOf(result_placeholder) == -1
    assert window.tab_bottom.indexOf(node_placeholder) == -1
    assert window.tab_bottom.indexOf(combo_placeholder) == -1


def test_results_menu_contains_plate_entries() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)

    menubar = window.menuBar()
    window.menu_results = QMenu("Resultats", menubar)

    for attr, text in {
        "act_res_displacements": "Déplacements",
        "act_res_reactions": "Réactions",
        "act_res_forces": "Efforts internes",
        "act_res_surfaces": "Résultats plaques",
        "act_envelopes": "Enveloppes",
        "act_diagram_N": "Diagramme N",
        "act_diagram_Vy": "Diagramme Vy",
        "act_diagram_Vz": "Diagramme Vz",
        "act_diagram_My": "Diagramme My",
        "act_diagram_Mz": "Diagramme Mz",
        "act_diagram_T": "Diagramme T",
        "act_hide_diagrams": "Masquer diagrammes",
        "act_surface_map": "Cartes plaques...",
        "act_res_deformed": "Déformée",
    }.items():
        setattr(window, attr, QAction(text, window))

    window._setup_results_menu()

    submenu_titles = [
        _normalize_label(action.text())
        for action in window.menu_results.actions()
        if action.menu() is not None
    ]
    assert "tableaux" in submenu_titles
    assert "diagrammes" in submenu_titles
    assert "plaques" in submenu_titles

    submenus = { _normalize_label(menu.title()): menu for menu in window.menu_results.findChildren(QMenu) }
    table_menu = submenus["tableaux"]
    table_titles = [
        _normalize_label(action.text())
        for action in table_menu.actions()
        if not action.isSeparator()
    ]
    assert "resultats plaques" in table_titles

    plate_menu = submenus["plaques"]
    plate_titles = [
        _normalize_label(action.text())
        for action in plate_menu.actions()
        if not action.isSeparator()
    ]
    assert "cartes plaques..." in plate_titles
