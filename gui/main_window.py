"""Main PySide6 application window."""

from __future__ import annotations

import math
import unicodedata
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QFile, QIODevice, QEventLoop, QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from config.settings import APP_NAME, APP_VERSION, Settings
from core.geometry.plate_intersections import detect_plate_intersections
from core.model_data import (
    ElementLoad,
    NodeData,
    NodalLoad,
    PLATE_MESH_MODE_AUTO,
    PLATE_MESH_MODE_USER,
    ProjectModel,
    SurfaceLoad,
    normalize_plate_mesh_mode,
    surface_expected_node_count,
    load_project,
    save_project,
)
from core.plate_mesh_settings import effective_plate_mesh_divisions
from core.selection_copy import build_copy_instance_points, selection_anchor_point
from core.solvers import AnalysisFeature, SolverEngine, SolverManager
from gui.dialogs.plate_mesh_dlg import PlateMeshDialog
from gui.dialogs.plate_region_properties_dlg import PlateRegionPropertiesDialog
from gui.resources import app_resource_path
from gui.widgets.tree_model import ModelTree
from gui.widgets.property_panel import PropertyPanel
from gui.widgets.table_view import NodeTableWidget, CombinationTableWidget
from gui.widgets.results_panel import ResultsPanel
from gui.widgets.results_table_window import ResultsTableWindow
from gui.widgets.diagram_window import DiagramWindow


class MainWindow(QMainWindow):
    """Main application window."""

    _DIAGRAM_COMPONENTS = ["N", "Vy", "Vz", "My", "Mz", "T"]
    _SURFACE_RESULT_COMPONENTS = ["Mxx", "Myy", "Mxy", "Qx", "Qy", "Nxx", "Nyy", "Nxy"]
    _MAX_HISTORY_ACTIONS = 10

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        self.project = ProjectModel()
        self.project.seed_default_library()
        self._solver_manager = SolverManager()
        self._modified = False
        self._pending_project_change = False
        self._all_results: dict[str, dict] = {}
        self._result_envelopes: dict[int, object] = {}
        self._current_case: str | None = None
        self._deformed_visible: bool = False
        self._current_diagram: str | None = None
        self._current_surface_component: str | None = None
        self._runner = None  # AnalysisRunner (kept to rerun the analysis)
        self._case_tags: dict[str, tuple[int | None, int | None]] = {}
        self._diagram_window: DiagramWindow | None = None
        self._element_diagram_window: DiagramWindow | None = None
        self._surface_diagram_window: DiagramWindow | None = None
        self._load_diagram_window: DiagramWindow | None = None
        self._results_window: ResultsTableWindow | None = None
        self._diagram_files: list[dict] = []
        self._element_diagram_files: list[dict] = []
        self._surface_result_files: list[dict] = []
        self._load_diagram_files: list[dict] = []
        self._diagram_support_reason: str = ""
        self._surface_result_support_reason: str = ""
        self._current_file_idx: int = 0
        self._current_element_diagram_tag: int | None = None
        self._current_element_diagram: str | None = None
        self._current_element_file_idx: int = 0
        self._current_surface_result_tag: int | None = None
        self._current_surface_file_idx: int = 0
        self._current_load_file_idx: int = 0
        self._current_load_case_tag: int | None = None
        self._load_case_labels: dict[str, int] = {}
        self._draw_start_point: tuple[float, float, float] | None = None
        self._draw_surface_points: list[tuple[float, float, float]] = []
        self._draw_surface_section_tag: int | None = None
        self._surface_draw_saved_orthogonal_state: bool | None = None
        self._draw_mode_kind: str | None = None
        self._selection_mode_active: bool = True
        self._selected_node_tags: list[int] = []
        self._selected_element_tags: list[int] = []
        self._selected_surface_tags: list[int] = []
        self._active_parallel_plane: str = "3D"
        self._active_parallel_value: float | None = None
        self._secondary_parallel_plane: str = "3D"
        self._secondary_parallel_value: float | None = None
        self._pick_plane_override: str | None = None
        self._undo_history: list[ProjectModel] = []
        self._redo_history: list[ProjectModel] = []
        self._history_restoring = False
        self._last_history_project = deepcopy(self.project)
        self._saved_project_snapshot = deepcopy(self.project)
        self._last_scene_signature: tuple | None = None

        self._setup_ui()
        self._connect_signals()
        self._update_title()

    # -- Interface construction ------------------------------------------------

    def _setup_ui(self) -> None:
        """Set up UI."""

        # --- Load the .ui file ---
        ui_path = app_resource_path("gui", "ui", "main_window.ui")
        loader = QUiLoader()
        file = QFile(ui_path)
        if not file.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Unable to open/read ui device: {ui_path}")
        self.ui = loader.load(file)
        file.close()

        # --- Copy window properties ---
        self.resize(
            self.settings.gui.window_width,
            self.settings.gui.window_height,
        )
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")

        # --- Retrieve actions from the .ui file ---
        self.act_new = self.ui.findChild(QAction, "act_new")
        self.act_open = self.ui.findChild(QAction, "act_open")
        self.act_save = self.ui.findChild(QAction, "act_save")
        self.act_save_as = self.ui.findChild(QAction, "act_save_as")
        self.act_quit = self.ui.findChild(QAction, "act_quit")

        self.act_add_node = self.ui.findChild(QAction, "act_add_node")
        self.act_add_material = self.ui.findChild(QAction, "act_add_material")
        self.act_add_section = self.ui.findChild(QAction, "act_add_section")
        self.act_add_element = self.ui.findChild(QAction, "act_add_element")
        self.act_boundary = self.ui.findChild(QAction, "act_boundary")
        self.act_add_load = self.ui.findChild(QAction, "act_add_load")
        self.act_define_loads = self.ui.findChild(QAction, "act_define_loads")
        self.act_gen_combos = self.ui.findChild(QAction, "act_gen_combos")
        if self.act_add_load is not None:
            self.act_add_load.setText("Cas de charge...")
        if self.act_gen_combos is not None:
            self.act_gen_combos.setText("Combinaisons...")

        self.act_run = self.ui.findChild(QAction, "act_run")
        self.act_eurocode_settings = self.ui.findChild(QAction, "act_eurocode_settings")

        self.act_res_displacements = self.ui.findChild(QAction, "act_res_displacements")
        self.act_res_reactions = self.ui.findChild(QAction, "act_res_reactions")
        self.act_res_forces = self.ui.findChild(QAction, "act_res_forces")
        self.act_res_deformed = self.ui.findChild(QAction, "act_res_deformed")
        if self.act_res_deformed is not None:
            self.act_res_deformed.setCheckable(True)
            self.act_res_deformed.setChecked(False)

        self.act_diagram_N = self.ui.findChild(QAction, "act_diagram_N")
        self.act_diagram_Vy = self.ui.findChild(QAction, "act_diagram_Vy")
        self.act_diagram_Vz = self.ui.findChild(QAction, "act_diagram_Vz")
        self.act_diagram_My = self.ui.findChild(QAction, "act_diagram_My")
        self.act_diagram_Mz = self.ui.findChild(QAction, "act_diagram_Mz")
        self.act_diagram_T = self.ui.findChild(QAction, "act_diagram_T")
        self.act_hide_diagrams = self.ui.findChild(QAction, "act_hide_diagrams")
        self.act_envelopes = self.ui.findChild(QAction, "act_envelopes")
        self.act_res_surfaces = QAction("Résultats plaques", self)
        self.act_surface_map = QAction("Cartes plaques...", self)

        self.act_view_xy = self.ui.findChild(QAction, "act_view_xy")
        self.act_view_xz = self.ui.findChild(QAction, "act_view_xz")
        self.act_view_yz = self.ui.findChild(QAction, "act_view_yz")
        self.act_view_iso = self.ui.findChild(QAction, "act_view_iso")
        self.act_show_node_tags = self.ui.findChild(QAction, "act_show_node_tags")
        self.act_show_section_names = self.ui.findChild(QAction, "act_show_section_names")
        self.act_show_extruded_sections = QAction("Sections 3D extrudées", self)
        self.act_show_extruded_sections.setCheckable(True)
        self.act_show_assigned_loads = QAction("Afficher charges...", self)
        self.menu_file = self.ui.findChild(QMenu, "menu_file")
        self.menu_edit = self.ui.findChild(QMenu, "menu_edit")
        self.menu_model = self.ui.findChild(QMenu, "menu_model")
        self.menu_charges = self.ui.findChild(QMenu, "menu_charges")
        self.menu_analysis = self.ui.findChild(QMenu, "menu_analysis")
        self.menu_results = self.ui.findChild(QMenu, "menu_results")
        self.menu_view = self.ui.findChild(QMenu, "menu_view")
        self.menu_help = self.ui.findChild(QMenu, "menu_help")

        self.act_about = self.ui.findChild(QAction, "act_about")
        self.act_undo_model = QAction("Annuler", self)
        self.act_undo_model.setShortcut("Ctrl+Z")
        self.act_redo_model = QAction("Rétablir", self)
        self.act_redo_model.setShortcut("Ctrl+Y")
        self.act_copy_selection = QAction("Copier...", self)
        self.act_copy_selection.setShortcut("Ctrl+C")
        self.act_copy_selection.setEnabled(False)

        # --- Transfer the menu bar ---
        mb = self.ui.menuBar()
        mb.setParent(self)
        self.setMenuBar(mb)
        self._setup_menu_bar_structure()

        # --- Transfer toolbars ---
        for tb in self.ui.findChildren(QToolBar):
            tb.setParent(None)
            self.addToolBar(tb)
        self.toolbar_main = self.findChildren(QToolBar)[0] if self.findChildren(QToolBar) else None
        if self.toolbar_main is not None:
            self.toolbar_main.hide()

        # --- Barre de statut ---
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        self._view_widget = self._create_view_widget()
        if self.model_view is not None:
            from gui.widgets.model_view import ModelView

            self.secondary_view = ModelView()
            self.secondary_view.show_node_tags = self.settings.gui.show_node_tags
            self.secondary_view.show_section_names = self.settings.gui.show_section_names
            self.secondary_view.show_extruded_sections = self.settings.gui.show_extruded_sections
        else:
            self.secondary_view = QLabel("Vue dupliquée indisponible")
            self.secondary_view.setAlignment(Qt.AlignCenter)
        self._view_splitter = QSplitter(Qt.Horizontal, self)
        self._view_splitter.addWidget(self._view_widget)
        self._view_splitter.addWidget(self.secondary_view)
        self._view_splitter.setStretchFactor(0, 2)
        self._view_splitter.setStretchFactor(1, 1)
        self._view_controls_widget = QWidget(self)
        self._view_controls_layout = QHBoxLayout(self._view_controls_widget)
        self._view_controls_layout.setContentsMargins(10, 8, 10, 8)
        self._view_controls_layout.setSpacing(8)

        self._central_views_widget = QWidget(self)
        self._central_views_layout = QVBoxLayout(self._central_views_widget)
        self._central_views_layout.setContentsMargins(0, 0, 0, 0)
        self._central_views_layout.setSpacing(0)
        self._central_views_layout.addWidget(self._view_controls_widget)
        self._central_views_layout.addWidget(self._view_splitter, 1)
        self.setCentralWidget(self._central_views_widget)

        # --- Left dock: model tree ---
        self.dock_tree = QDockWidget("Arbre du modèle", self)
        self.dock_tree.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.tree = ModelTree()
        self.tree.refresh(self.project)
        self.dock_tree.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_tree)

        # --- Right dock: properties ---
        self.dock_properties = QDockWidget("Propriétés", self)
        self.dock_properties.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.properties = PropertyPanel()
        self.properties.set_project(self.project)
        self.dock_properties.setWidget(self.properties)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_properties)

        # --- Bottom dock: results / console tabs ---
        self.dock_bottom = QDockWidget("Informations", self)
        self.dock_bottom.setAllowedAreas(Qt.BottomDockWidgetArea)

        # Retrieve the QTabWidget and console from the .ui file
        self.tab_bottom = self.ui.findChild(QTabWidget, "tab_bottom")
        self.console = self.ui.findChild(QPlainTextEdit, "console")

        # Reparent tab_bottom to use it in our dock
        self.tab_bottom.setParent(None)

        # Replace placeholder tabs with the real widgets
        # Results tab (index 1)
        self.results_panel = ResultsPanel()
        self.results_panel.case_changed.connect(self._on_case_changed)
        self._replace_bottom_placeholder(
            "results_tab_placeholder",
            self.results_panel,
            "Résultats",
            fallback_index=1,
        )

        # Nodes tab (index 2)
        self.node_table = NodeTableWidget()
        self._replace_bottom_placeholder(
            "nodes_tab_placeholder",
            self.node_table,
            "Nœuds",
            fallback_index=2,
        )

        # Combinations tab (index 3)
        self.combo_table = CombinationTableWidget()
        self._replace_bottom_placeholder(
            "combos_tab_placeholder",
            self.combo_table,
            "Combinaisons",
            fallback_index=3,
        )
        self._remove_duplicate_bottom_tabs()

        self.tab_bottom.setCurrentIndex(0)
        self.dock_bottom.setWidget(self.tab_bottom)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_bottom)

        # --- Add dock toggles to the View menu ---
        menu_view = self.menu_view
        if menu_view is not None:
            self.act_toggle_split_view = QAction("Afficher 2 fenêtres", self)
            self.act_toggle_split_view.setCheckable(True)
            self.act_toggle_split_view.toggled.connect(self._toggle_split_view)
            menu_view.addAction(self.act_toggle_split_view)
            menu_view.addSeparator()
            menu_view.addAction(self.dock_tree.toggleViewAction())
            menu_view.addAction(self.dock_properties.toggleViewAction())
            menu_view.addAction(self.dock_bottom.toggleViewAction())

        # --- Apply View menu checkbox settings ---
        if self.settings.gui.show_extruded_sections:
            self.settings.gui.show_section_names = False
        self.act_show_node_tags.setChecked(self.settings.gui.show_node_tags)
        self.act_show_section_names.setChecked(self.settings.gui.show_section_names)
        self.act_show_extruded_sections.setChecked(self.settings.gui.show_extruded_sections)

        self._update_statusbar()
        self._setup_edit_menu()
        self._setup_model_management_menus()
        self._setup_charges_menu()
        self._setup_analysis_menu()
        self._setup_results_menu()
        self._refresh_result_actions()
        self._setup_view_menu()
        self._setup_menu_bar_structure()
        self._setup_primary_toolbar()
        self._setup_parallel_view_controls()
        self._toggle_split_view(False)
        self._log("HEXA Structures initialisé. Prêt.")

    def _replace_bottom_placeholder(
        self,
        placeholder_name: str,
        widget: QWidget,
        title: str,
        *,
        fallback_index: int,
    ) -> None:
        """Handle replace bottom placeholder."""
        placeholder = self.tab_bottom.findChild(QWidget, placeholder_name)
        if placeholder is None:
            placeholder = self.ui.findChild(QWidget, placeholder_name)
        idx = self.tab_bottom.indexOf(placeholder) if placeholder is not None else -1
        if idx >= 0:
            self.tab_bottom.removeTab(idx)
        else:
            idx = min(fallback_index, self.tab_bottom.count())

        current_idx = self.tab_bottom.indexOf(widget)
        if current_idx >= 0:
            self.tab_bottom.removeTab(current_idx)
            if current_idx < idx:
                idx -= 1

        self.tab_bottom.insertTab(idx, widget, title)

    @staticmethod
    def _bottom_tab_key(title: str) -> str:
        """Handle bottom tab key."""
        text = title.replace("&", "").strip()
        for _ in range(2):
            try:
                repaired = text.encode("cp1252").decode("utf-8")
            except UnicodeError:
                break
            if repaired == text:
                break
            text = repaired
        text = text.casefold().replace("œ", "oe")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in text if not unicodedata.combining(char))
        return "".join(char for char in text if char.isalnum())

    def _remove_duplicate_bottom_result_tabs(self) -> None:
        """Remove duplicate bottom result tabs."""
        keep_idx = self.tab_bottom.indexOf(self.results_panel)
        for idx in range(self.tab_bottom.count() - 1, -1, -1):
            if idx == keep_idx:
                continue
            title = self._bottom_tab_key(self.tab_bottom.tabText(idx))
            if title == "resultats":
                self.tab_bottom.removeTab(idx)

    def _remove_duplicate_bottom_tabs(self) -> None:
        """Remove duplicate bottom tabs."""
        keep_by_title = {
            "resultats": self.tab_bottom.indexOf(self.results_panel),
            "noeuds": self.tab_bottom.indexOf(self.node_table),
            "combinaisons": self.tab_bottom.indexOf(self.combo_table),
        }
        for idx in range(self.tab_bottom.count() - 1, -1, -1):
            title = self._bottom_tab_key(self.tab_bottom.tabText(idx))
            keep_idx = keep_by_title.get(title)
            if keep_idx is not None and keep_idx >= 0 and idx != keep_idx:
                self.tab_bottom.removeTab(idx)

    def _create_view_widget(self) -> QWidget:
        """Create view widget."""
        try:
            from gui.widgets.model_view import ModelView

            self.model_view = ModelView()
            self.model_view.show_node_tags = self.settings.gui.show_node_tags
            self.model_view.show_section_names = self.settings.gui.show_section_names
            self.model_view.show_extruded_sections = self.settings.gui.show_extruded_sections
            return self.model_view
        except Exception as exc:
            self.model_view = None
            detail = str(exc).strip() or exc.__class__.__name__
            placeholder = QLabel(
                "Vue 3D indisponible\n\n"
                f"Chargement du module 3D impossible :\n{detail}"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(
                "QLabel { background-color: #ffffff; color: #5f6b73; "
                "font-size: 14px; border: 1px solid #c8d0d6; }"
            )
            return placeholder

    def _connect_signals(self) -> None:
        """Handle connect signals."""

        # Tree -> Properties + 3D view
        self.tree.node_selected.connect(self._on_tree_node_selected)
        self.tree.element_selected.connect(self._on_tree_element_selected)
        self.tree.surface_selected.connect(self._on_tree_surface_selected)
        self.tree.material_selected.connect(self.properties.show_material)
        self.tree.section_selected.connect(self.properties.show_section)
        self.tree.load_selected.connect(self.properties.show_load)
        self.tree.combination_selected.connect(self.properties.show_combination)

        # Tree -> Add / Delete / Edit
        self.tree.add_requested.connect(self._on_add_requested)
        self.tree.edit_requested.connect(self._on_edit_requested)
        self.tree.delete_requested.connect(self._on_delete_requested)
        self.tree.load_double_clicked.connect(self._edit_load_case)

        # 3D view -> Tree + Properties
        if self.model_view is not None:
            self.model_view.node_picked.connect(self._on_view_node_picked)
            self.model_view.element_picked.connect(self._on_view_element_picked)
            if hasattr(self.model_view, "element_context_requested"):
                self.model_view.element_context_requested.connect(
                    self._show_element_context_menu
                )
            if hasattr(self.model_view, "surface_context_requested"):
                self.model_view.surface_context_requested.connect(
                    self._show_surface_context_menu
                )
            self.model_view.selection_mode_requested.connect(
                self._activate_selection_tool
            )
            self.model_view.selection_changed.connect(self._on_view_selection_changed)
            self.model_view.selection_delete_requested.connect(
                self._on_view_delete_selection_requested
            )
            self.model_view.grid_point_picked.connect(
                lambda x, y, z: self._on_grid_point_picked_from_view("primary", x, y, z)
            )
            self.model_view.draw_finalize_requested.connect(
                self._on_draw_finalize_requested
            )
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "node_picked"):
            self.secondary_view.node_picked.connect(self._on_view_node_picked)
            self.secondary_view.element_picked.connect(self._on_view_element_picked)
            if hasattr(self.secondary_view, "element_context_requested"):
                self.secondary_view.element_context_requested.connect(
                    self._show_element_context_menu
                )
            if hasattr(self.secondary_view, "surface_context_requested"):
                self.secondary_view.surface_context_requested.connect(
                    self._show_surface_context_menu
                )
            self.secondary_view.selection_mode_requested.connect(
                self._activate_selection_tool
            )
            self.secondary_view.selection_changed.connect(self._on_view_selection_changed)
            self.secondary_view.selection_delete_requested.connect(
                self._on_view_delete_selection_requested
            )
            self.secondary_view.grid_point_picked.connect(
                lambda x, y, z: self._on_grid_point_picked_from_view("secondary", x, y, z)
            )
            self.secondary_view.draw_finalize_requested.connect(
                self._on_draw_finalize_requested
            )

        # Properties / Tables -> Refresh
        self.properties.model_changed.connect(self._on_model_changed)
        self.node_table.model_changed.connect(self._on_model_changed)
        self.combo_table.model_changed.connect(self._on_model_changed)

        # --- File menu actions ---
        self.act_new.triggered.connect(self._on_new_project)
        self.act_open.triggered.connect(self._on_open_project)
        self.act_save.triggered.connect(self._on_save_project)
        self.act_save_as.triggered.connect(self._on_save_as)
        self.act_quit.triggered.connect(self.close)

        # --- Model menu actions ---
        self.act_add_node.triggered.connect(lambda: self._on_add_requested("node"))
        self.act_add_material.triggered.connect(lambda: self._on_add_requested("material"))
        self.act_add_section.triggered.connect(lambda: self._on_add_requested("section"))
        self.act_add_element.triggered.connect(lambda: self._on_add_requested("element"))
        self.act_undo_model.triggered.connect(self._undo_last_action)
        self.act_redo_model.triggered.connect(self._redo_last_action)
        self.act_copy_selection.triggered.connect(self._copy_selected_objects)
        self.act_boundary.triggered.connect(self._edit_boundary)
        self.act_add_load.triggered.connect(self._manage_load_cases)
        self.act_define_loads.triggered.connect(self._define_loads)
        self.act_gen_combos.triggered.connect(self._manage_combinations)

        # --- Analysis menu actions ---
        self.act_run.triggered.connect(self._run_analysis)
        self.act_eurocode_settings.triggered.connect(self._open_eurocode_settings)

        # --- Results menu actions ---
        self.act_res_displacements.triggered.connect(
            lambda: self._show_result_table("displacements")
        )
        self.act_res_reactions.triggered.connect(
            lambda: self._show_result_table("reactions")
        )
        self.act_res_forces.triggered.connect(
            lambda: self._show_result_table("element_forces")
        )
        self.act_res_surfaces.triggered.connect(
            lambda: self._show_result_table("surface_results")
        )
        self.act_res_deformed.triggered.connect(self._show_deformed_menu)
        self.act_surface_map.triggered.connect(self._show_surface_result_map)

        self.act_diagram_N.triggered.connect(lambda: self._show_diagram("N"))
        self.act_diagram_Vy.triggered.connect(lambda: self._show_diagram("Vy"))
        self.act_diagram_Vz.triggered.connect(lambda: self._show_diagram("Vz"))
        self.act_diagram_My.triggered.connect(lambda: self._show_diagram("My"))
        self.act_diagram_Mz.triggered.connect(lambda: self._show_diagram("Mz"))
        self.act_diagram_T.triggered.connect(lambda: self._show_diagram("T"))
        self.act_hide_diagrams.triggered.connect(self._clear_diagrams)
        self.act_envelopes.triggered.connect(
            lambda: self._show_result_table("envelopes")
        )

        # --- View menu actions ---
        self.act_view_xy.triggered.connect(self._on_view_xy)
        self.act_view_xz.triggered.connect(self._on_view_xz)
        self.act_view_yz.triggered.connect(self._on_view_yz)
        self.act_view_iso.triggered.connect(self._on_view_iso)
        self.act_show_node_tags.toggled.connect(self._on_toggle_node_tags)
        self.act_show_section_names.toggled.connect(self._on_toggle_section_names)
        self.act_show_extruded_sections.toggled.connect(self._on_toggle_extruded_sections)
        self.act_show_assigned_loads.triggered.connect(self._show_load_diagram)

        # --- Help menu actions ---
        self.act_about.triggered.connect(self._on_about)

    def _setup_menu_bar_structure(self) -> None:
        """Set up menu bar structure."""
        menubar = self.menuBar()
        if menubar is None:
            return

        if self.menu_edit is None:
            self.menu_edit = QMenu("Édition", menubar)
            self.menu_edit.setObjectName("menu_edit")
        if self.menu_charges is None:
            self.menu_charges = QMenu("Charges", menubar)
            self.menu_charges.setObjectName("menu_charges")

        menu_specs = (
            (self.menu_file, "Fichier"),
            (self.menu_edit, "Édition"),
            (self.menu_model, "Modèle"),
            (self.menu_view, "Vue"),
            (self.menu_charges, "Charges"),
            (self.menu_analysis, "Analyse"),
            (self.menu_results, "Résultats"),
            (self.menu_help, "Aide"),
        )
        for menu, title in menu_specs:
            if menu is not None:
                menu.setTitle(title)

        for action in list(menubar.actions()):
            menubar.removeAction(action)
        for menu, _title in menu_specs:
            if menu is not None:
                menubar.addMenu(menu)

    def _setup_edit_menu(self) -> None:
        """Set up edit menu."""
        if self.menu_edit is None:
            return

        self._clear_menu_structure(self.menu_edit)
        self.menu_edit.addAction(self.act_undo_model)
        self.menu_edit.addAction(self.act_redo_model)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.act_copy_selection)

    def _setup_model_management_menus(self) -> None:
        """Set up model management menus."""
        self.act_define_grid = QAction("Définir la grille 3D...", self)
        self.act_define_grid.triggered.connect(self._define_grid)
        self.act_select_tool = QAction("Sélection", self)
        self.act_select_tool.setCheckable(True)
        self.act_select_tool.setChecked(True)
        self.act_select_tool.toggled.connect(self._toggle_selection_tool)
        self.act_draw_node = QAction("Dessiner un nœud", self)
        self.act_draw_node.setCheckable(True)
        self.act_draw_node.toggled.connect(self._toggle_draw_nodes)
        self.act_draw_bars = QAction("Dessiner des barres", self)
        self.act_draw_bars.setCheckable(True)
        self.act_draw_bars.toggled.connect(self._toggle_draw_bars)
        self.act_draw_surface = QAction("Dessiner une surface", self)
        self.act_draw_surface.setCheckable(True)
        self.act_draw_surface.toggled.connect(self._toggle_draw_surface)
        self.act_draw_orthogonal = QAction("Tracé orthogonal", self)
        self.act_draw_orthogonal.setCheckable(True)
        self.act_draw_orthogonal.setChecked(False)
        self.act_cancel_draw = QAction("Annuler le dessin", self)
        self.act_cancel_draw.triggered.connect(self._cancel_bar_drawing)
        self.act_add_surface = QAction("Ajouter une surface depuis la sélection", self)
        self.act_add_surface.triggered.connect(lambda: self._on_add_requested("surface"))
        self.act_edit_surface = QAction("Modifier la surface sélectionnée...", self)
        self.act_edit_surface.triggered.connect(self._edit_surface)
        self.act_add_plate_section = QAction("Nouvelle section plaque...", self)
        self.act_add_plate_section.triggered.connect(self._add_plate_section)

        self.act_manage_materials = QAction("Matériaux...", self)
        self.act_manage_materials.triggered.connect(self._manage_materials)
        self.act_manage_sections = QAction("Sections...", self)
        self.act_manage_sections.triggered.connect(self._manage_sections)
        self.act_manage_plate_sections = QAction("Sections plaque...", self)
        self.act_manage_plate_sections.triggered.connect(self._manage_plate_sections)
        self.act_assign_load_selection = QAction("Affecter charges à la sélection...", self)
        self.act_assign_load_selection.triggered.connect(self._assign_loads_to_selection)

        if self.menu_model is not None:
            self._clear_menu_structure(self.menu_model)

            self.menu_model.addAction(self.act_define_grid)
            self.menu_model.addSeparator()
            self.menu_model.addAction(self.act_add_node)
            self.menu_model.addAction(self.act_add_element)
            self.menu_model.addAction(self.act_add_surface)
            self.menu_model.addAction(self.act_edit_surface)
            self.menu_model.addSeparator()
            self.menu_model.addAction(self.act_add_material)
            self.menu_model.addAction(self.act_add_section)
            self.menu_model.addAction(self.act_add_plate_section)
            self.menu_model.addAction(self.act_manage_materials)
            self.menu_model.addAction(self.act_manage_sections)
            self.menu_model.addAction(self.act_manage_plate_sections)
            self.menu_model.addSeparator()
            self.menu_model.addAction(self.act_boundary)
            self.menu_model.addSeparator()
            self.menu_model.addAction(self.act_select_tool)
            self.menu_model.addAction(self.act_draw_node)
            self.menu_model.addAction(self.act_draw_bars)
            self.menu_model.addAction(self.act_draw_surface)
            self.menu_model.addAction(self.act_draw_orthogonal)
            self.menu_model.addAction(self.act_cancel_draw)

        self._refresh_model_management_menus()

    def _setup_charges_menu(self) -> None:
        """Set up charges menu."""
        if self.menu_charges is None:
            return

        self._clear_menu_structure(self.menu_charges)
        self.menu_charges.addAction(self.act_add_load)
        self.menu_charges.addAction(self.act_define_loads)
        self.menu_charges.addAction(self.act_assign_load_selection)
        self.menu_charges.addAction(self.act_show_assigned_loads)
        self.menu_charges.addSeparator()
        self.menu_charges.addAction(self.act_gen_combos)

    def _setup_results_menu(self) -> None:
        """Set up results menu."""
        if self.menu_results is None:
            return

        self._clear_menu_structure(self.menu_results)

        menu_tables = self.menu_results.addMenu("Tableaux")
        menu_tables.addAction(self.act_res_displacements)
        menu_tables.addAction(self.act_res_reactions)
        menu_tables.addAction(self.act_res_forces)
        if getattr(self, "act_res_surfaces", None) is not None:
            menu_tables.addAction(self.act_res_surfaces)
        menu_tables.addSeparator()
        menu_tables.addAction(self.act_envelopes)

        menu_diagrams = self.menu_results.addMenu("Diagrammes")
        menu_diagrams.addAction(self.act_diagram_N)
        menu_diagrams.addAction(self.act_diagram_Vy)
        menu_diagrams.addAction(self.act_diagram_Vz)
        menu_diagrams.addAction(self.act_diagram_My)
        menu_diagrams.addAction(self.act_diagram_Mz)
        menu_diagrams.addAction(self.act_diagram_T)
        menu_diagrams.addSeparator()
        menu_diagrams.addAction(self.act_hide_diagrams)

        if getattr(self, "act_surface_map", None) is not None:
            menu_surfaces = self.menu_results.addMenu("Plaques")
            menu_surfaces.addAction(self.act_surface_map)

        self.menu_results.addSeparator()
        self.menu_results.addAction(self.act_res_deformed)

    def _setup_analysis_menu(self) -> None:
        """Set up analysis menu."""
        if self.menu_analysis is None:
            return

        self._clear_menu_structure(self.menu_analysis)
        self.menu_analysis.addAction(self.act_run)
        self.menu_analysis.addSeparator()

        self.menu_solver = self.menu_analysis.addMenu("Moteur de calcul")
        self.solver_action_group = QActionGroup(self)
        self.solver_action_group.setExclusive(True)

        self.act_solver_pynite = QAction(self)
        self.act_solver_pynite.setCheckable(True)
        self.act_solver_pynite.triggered.connect(
            lambda checked=False: self._on_solver_engine_selected(SolverEngine.PYNITE)
        )
        self.solver_action_group.addAction(self.act_solver_pynite)
        self.menu_solver.addAction(self.act_solver_pynite)

        self.act_solver_opensees = QAction(self)
        self.act_solver_opensees.setCheckable(True)
        self.act_solver_opensees.triggered.connect(
            lambda checked=False: self._on_solver_engine_selected(SolverEngine.OPENSEES)
        )
        self.solver_action_group.addAction(self.act_solver_opensees)
        self.menu_solver.addAction(self.act_solver_opensees)

        self.menu_solver.addSeparator()
        self.act_solver_help = QAction("Aide installation des solveurs...", self)
        self.act_solver_help.triggered.connect(self._show_solver_install_help)
        self.menu_solver.addAction(self.act_solver_help)
        self.act_solver_capabilities = QAction("Capacités des moteurs...", self)
        self.act_solver_capabilities.triggered.connect(
            self._show_solver_capabilities
        )
        self.menu_solver.addAction(self.act_solver_capabilities)

        self.menu_analysis.addSeparator()
        self.menu_analysis.addAction(self.act_eurocode_settings)
        self._refresh_analysis_menu()
        self._refresh_diagram_actions()

    def _refresh_analysis_menu(self) -> None:
        """Refresh analysis menu."""
        if not hasattr(self, "act_solver_pynite"):
            return

        info_by_engine = {
            SolverEngine(row["engine"]): row
            for row in self._solver_manager.get_display_info()
        }
        requested = self._normalize_solver_engine(self.settings.analysis.solver_engine)

        for engine, action in (
            (SolverEngine.PYNITE, self.act_solver_pynite),
            (SolverEngine.OPENSEES, self.act_solver_opensees),
        ):
            row = info_by_engine.get(engine)
            if row is None:
                continue
            action.blockSignals(True)
            action.setText(str(row["text"]))
            action.setToolTip(str(row["tooltip"]))
            action.setStatusTip(str(row["tooltip"]))
            action.setChecked(engine == requested)
            action.blockSignals(False)
        self._refresh_diagram_actions()

    def _normalize_solver_engine(self, value: str | SolverEngine | None) -> SolverEngine:
        """Normalize solver engine."""
        if isinstance(value, SolverEngine):
            return value
        try:
            return SolverEngine(str(value).strip().lower())
        except ValueError:
            return SolverEngine.PYNITE

    def _solver_label(self, engine: SolverEngine) -> str:
        """Handle solver label."""
        return {
            SolverEngine.PYNITE: "PyNite",
            SolverEngine.OPENSEES: "OpenSeesPy",
        }[engine]

    def _resolved_solver_engine(self) -> SolverEngine:
        """Handle resolved solver engine."""
        settings = getattr(self, "settings", None)
        solver_manager = getattr(self, "_solver_manager", None)
        if settings is None or solver_manager is None:
            return SolverEngine.OPENSEES
        requested = self._normalize_solver_engine(
            getattr(settings.analysis, "solver_engine", SolverEngine.PYNITE.value)
        )
        return solver_manager.resolve_engine(requested)

    def _surface_features_enabled(self) -> bool:
        """Handle surface features enabled."""
        return self._resolved_solver_engine() == SolverEngine.OPENSEES

    def _surface_features_disabled_reason(self) -> str:
        """Handle surface features disabled reason."""
        if self._surface_features_enabled():
            return ""
        settings = getattr(self, "settings", None)
        requested_raw = (
            getattr(getattr(settings, "analysis", None), "solver_engine", SolverEngine.PYNITE.value)
            if settings is not None
            else SolverEngine.PYNITE.value
        )
        requested = self._normalize_solver_engine(requested_raw)
        resolved = self._resolved_solver_engine()
        if requested != resolved:
            return (
                "Les plaques sont disponibles uniquement avec OpenSeesPy. "
                f"Le moteur effectif est actuellement {self._solver_label(resolved)} "
                f"(repli depuis {self._solver_label(requested)})."
            )
        return (
            "Les plaques sont disponibles uniquement avec OpenSeesPy. "
            f"Le moteur courant est actuellement {self._solver_label(resolved)}."
        )

    def _ensure_surface_features_available(
        self,
        title: str = "Plaques indisponibles",
    ) -> bool:
        """Ensure surface features available."""
        if self._surface_features_enabled():
            return True
        QMessageBox.information(
            self,
            title,
            self._surface_features_disabled_reason(),
        )
        return False

    def _sync_plate_editing_state(self) -> None:
        """Synchronize plate editing state."""
        if getattr(self, "properties", None) is not None and hasattr(self.properties, "set_plate_editing_enabled"):
            self.properties.set_plate_editing_enabled(
                self._surface_features_enabled(),
                self._surface_features_disabled_reason(),
            )

    def _on_solver_engine_selected(self, engine: SolverEngine) -> None:
        """Handle solver engine selected."""
        if not self._solver_manager.is_available(engine):
            if hasattr(self, "menu_solver"):
                self._refresh_analysis_menu()
            install_hint = {
                row["engine"]: row["tooltip"]
                for row in self._solver_manager.get_display_info()
            }.get(engine.value, "")
            QMessageBox.information(
                self,
                "Solveur non disponible",
                f"{self._solver_label(engine)} n'est pas installé.\n\n"
                f"{install_hint}\n\n"
                "Le logiciel reste sur le moteur actuellement disponible.",
            )
            return

        previous = self._normalize_solver_engine(self.settings.analysis.solver_engine)
        if engine == previous:
            self._refresh_analysis_menu()
            return

        self.settings.analysis.solver_engine = engine.value
        self.settings.save()
        self._refresh_analysis_menu()
        self._refresh_model_management_menus()
        self._update_statusbar()
        self._sync_plate_editing_state()
        if (
            not self._surface_features_enabled()
            and getattr(self, "act_draw_surface", None) is not None
            and self.act_draw_surface.isChecked()
        ):
            self.act_draw_surface.setChecked(False)
        if not self._diagram_support_is_available():
            self._clear_diagrams()
        self._log(f"Moteur de calcul sélectionné : {self._solver_label(engine)}.")

    def _show_solver_install_help(self) -> None:
        """Show solver install help."""
        info_by_engine = {
            SolverEngine(row["engine"]): row
            for row in self._solver_manager.get_display_info()
        }
        pynite = info_by_engine.get(SolverEngine.PYNITE, {})
        opensees = info_by_engine.get(SolverEngine.OPENSEES, {})
        QMessageBox.information(
            self,
            "Moteurs de calcul",
            "PyNite est le moteur recommandé et par défaut pour le logiciel.\n"
            "OpenSeesPy reste disponible comme moteur avancé optionnel.\n\n"
            f"- {self._solver_label(SolverEngine.PYNITE)} : {pynite.get('tooltip', '')}\n"
            f"- {self._solver_label(SolverEngine.OPENSEES)} : {opensees.get('tooltip', '')}",
        )

    def _show_solver_capabilities(self) -> None:
        """Show solver capabilities."""
        rows = self._solver_manager.get_capability_matrix()
        lines = [
            "Prêt = disponible maintenant dans HEXA Structures",
            "Moteur capable = support natif du moteur, raccordement logiciel à faire",
            "Prévu = cible dans HEXA Structures, souvent via une surcouche interne",
            "Non prévu = hors cible à court terme",
            "",
        ]
        for row in rows:
            lines.append(
                f"{row['label']}\n"
                f"PyNite : {row['pynite']} - {row['pynite_note']}\n"
                f"OpenSeesPy : {row['opensees']} - {row['opensees_note']}\n"
            )

        requested = self._normalize_solver_engine(self.settings.analysis.solver_engine)
        spectral_engine = self._solver_manager.best_engine_for_feature(
            AnalysisFeature.RESPONSE_SPECTRUM,
            requested=requested,
        )
        lines.extend(
            [
                "",
                "Orientation cible :",
                f"- Calcul courant : {self._solver_label(requested)} si disponible",
                "- Fallback automatique selon capacité par type d'analyse",
                (
                    "- Sismique modal spectral : "
                    f"{self._solver_label(spectral_engine)} à court terme, "
                    "puis surcouche interne HEXA Structures a moyen terme"
                ),
            ]
        )

        QMessageBox.information(
            self,
            "Capacités des moteurs",
            "\n".join(lines).strip(),
        )

    def _diagram_actions(self) -> tuple[QAction, ...]:
        """Handle diagram actions."""
        return tuple(
            action
            for action in (
                self.act_diagram_N,
                self.act_diagram_Vy,
                self.act_diagram_Vz,
                self.act_diagram_My,
                self.act_diagram_Mz,
                self.act_diagram_T,
                self.act_hide_diagrams,
            )
            if action is not None
        )

    def _result_actions(self) -> tuple[QAction, ...]:
        return tuple(
            action
            for action in (
                self.act_res_displacements,
                self.act_res_reactions,
                self.act_res_forces,
                self.act_res_deformed,
                self.act_envelopes,
            )
            if action is not None
        )

    def _has_surface_results(self) -> bool:
        return any(
            bool(
                case_results.get("surface_results")
                or case_results.get("plate_results")
                or (case_results.get("internal_results", {}) or {}).get("surface_results")
            )
            for case_results in self._all_results.values()
        )

    def _surface_result_project_for_results(self, case_results: dict | None = None):
        """Handle surface result project for results."""
        if isinstance(case_results, dict):
            analysis_project = case_results.get("analysis_project")
            if analysis_project is not None:
                return analysis_project
        if self._runner is not None:
            analysis_project = getattr(self._runner.backend, "analysis_project", None)
            if analysis_project is not None:
                return analysis_project
        return self.project

    def _current_surface_result_case_results(self) -> dict | None:
        if not self._all_results:
            return None
        case_name = self._current_case if self._current_case in self._all_results else None
        if case_name is None:
            case_name = next(iter(self._all_results), None)
        return self._all_results.get(case_name or "")

    def _refresh_result_actions(self) -> None:
        has_results = bool(self._all_results)
        tip = (
            "Afficher les résultats du cas courant."
            if has_results
            else "Aucun résultat disponible. Lancez d'abord une analyse (F5)."
        )
        for action in self._result_actions():
            action.setEnabled(has_results)
            action.setToolTip(tip)
            action.setStatusTip(tip)
        self._refresh_deformed_action()
        self._refresh_surface_result_actions()

    def _refresh_deformed_action(self) -> None:
        """Refresh deformed action."""
        if getattr(self, "act_res_deformed", None) is None:
            return

        has_results = bool(self._all_results)
        if not has_results:
            self._deformed_visible = False

        blocked = self.act_res_deformed.blockSignals(True)
        self.act_res_deformed.setChecked(has_results and self._deformed_visible)
        self.act_res_deformed.blockSignals(blocked)
        self.act_res_deformed.setEnabled(has_results)

        if not has_results:
            tip = "Aucun résultat disponible. Lancez d'abord une analyse (F5)."
        elif self._deformed_visible:
            tip = "Masquer la déformée du cas courant."
        else:
            tip = "Afficher la déformée du cas courant."
        self.act_res_deformed.setToolTip(tip)
        self.act_res_deformed.setStatusTip(tip)

    def _diagram_support_is_available(self) -> bool:
        """Handle diagram support is available."""
        if not self.project.elements:
            self._diagram_support_reason = "Aucun élément n'est disponible dans le modèle."
            return False
        try:
            from gui.widgets.diagram_renderer import detect_files
        except Exception as exc:
            self._diagram_support_reason = (
                "Le moteur de rendu des diagrammes n'a pas pu être chargé : "
                f"{exc}"
            )
            return False

        try:
            files = detect_files(project=self.project)
        except Exception as exc:
            self._diagram_support_reason = (
                "La détection des files de diagrammes a échoué : "
                f"{exc}"
            )
            return False

        if files:
            self._diagram_support_reason = ""
            return True

        self._diagram_support_reason = (
            "Les diagrammes actuels sont disponibles uniquement "
            "sur les plans verticaux XZ et YZ."
        )
        return False

    def _surface_result_support_is_available(self) -> bool:
        """Handle surface result support is available."""
        render_project = self._surface_result_project_for_results(
            self._current_surface_result_case_results()
        )
        if not render_project.surface_elements:
            self._surface_result_support_reason = (
                "Aucun élément surfacique n'est disponible dans le modèle."
            )
            return False
        try:
            from matplotlib.figure import Figure as _Figure  # noqa: F401
        except Exception as exc:
            self._surface_result_support_reason = (
                "matplotlib est indisponible pour les cartes plaques : "
                f"{exc}"
            )
            return False
        try:
            from gui.widgets.surface_result_renderer import detect_surface_result_views
        except Exception as exc:
            self._surface_result_support_reason = (
                "Le moteur de rendu des cartes plaques n'a pas pu être chargé : "
                f"{exc}"
            )
            return False

        try:
            files = detect_surface_result_views(render_project)
        except Exception as exc:
            self._surface_result_support_reason = (
                "La détection des plans de plaques a échoué : "
                f"{exc}"
            )
            return False

        if files:
            self._surface_result_support_reason = ""
            return True

        self._surface_result_support_reason = (
            "Les cartes plaques necessitent des surfaces coplanaires XY, XZ ou YZ."
        )
        return False

    def _refresh_surface_result_actions(self) -> None:
        """Refresh surface result actions."""
        has_surface_results = self._has_surface_results()
        support_available = self._surface_result_support_is_available()

        if not has_surface_results:
            table_tip = "Aucun résultat plaque disponible. Lancez d'abord une analyse de plaques."
            map_tip = table_tip
        else:
            table_tip = "Afficher les résultats plaques du cas courant."
            map_tip = (
                "Afficher une carte de contours des résultats plaques."
                if support_available
                else self._surface_result_support_reason
            )

        if getattr(self, "act_res_surfaces", None) is not None:
            self.act_res_surfaces.setEnabled(has_surface_results)
            self.act_res_surfaces.setToolTip(table_tip)
            self.act_res_surfaces.setStatusTip(table_tip)
        if getattr(self, "act_surface_map", None) is not None:
            self.act_surface_map.setEnabled(has_surface_results and support_available)
            self.act_surface_map.setToolTip(map_tip)
            self.act_surface_map.setStatusTip(map_tip)
        if (
            not has_surface_results
            and getattr(self, "_surface_diagram_window", None) is not None
        ):
            self._surface_diagram_window.hide()

    def _refresh_diagram_actions(self) -> None:
        """Refresh diagram actions."""
        has_results = bool(self._all_results)
        diagrams_supported = self._diagram_support_is_available()
        enabled = has_results

        if not has_results:
            tip = "Aucun résultat disponible. Lancez d'abord une analyse (F5)."
        elif diagrams_supported:
            tip = "Afficher les diagrammes d'efforts internes pour le cas courant."
        else:
            tip = self._diagram_support_reason or (
                "Afficher les diagrammes. "
                "Si aucune vue compatible n'est disponible, la fenêtre l'indiquera."
            )

        for action in self._diagram_actions():
            action.setEnabled(enabled)
            action.setToolTip(tip)
            action.setStatusTip(tip)

        if not has_results and self._diagram_window is not None:
            self._diagram_window.hide()

    def _setup_view_menu(self) -> None:
        """Set up view menu."""
        if self.menu_view is None:
            return

        self._clear_menu_structure(self.menu_view)

        menu_orientation = self.menu_view.addMenu("Orientation")
        menu_orientation.addAction(self.act_view_xy)
        menu_orientation.addAction(self.act_view_xz)
        menu_orientation.addAction(self.act_view_yz)
        menu_orientation.addAction(self.act_view_iso)

        menu_display = self.menu_view.addMenu("Affichage")
        menu_display.addAction(self.act_show_node_tags)
        menu_display.addAction(self.act_show_section_names)
        menu_display.addAction(self.act_show_extruded_sections)

        menu_windows = self.menu_view.addMenu("Fenêtres")
        if getattr(self, "act_toggle_split_view", None) is not None:
            menu_windows.addAction(self.act_toggle_split_view)
            menu_windows.addSeparator()
        menu_windows.addAction(self.dock_tree.toggleViewAction())
        menu_windows.addAction(self.dock_properties.toggleViewAction())
        menu_windows.addAction(self.dock_bottom.toggleViewAction())

    def _clear_menu_structure(self, menu: QMenu) -> None:
        """Clear menu structure."""
        for action in list(menu.actions()):
            menu.removeAction(action)

    def _setup_primary_toolbar(self) -> None:
        """Set up primary toolbar."""
        existing_toolbar = getattr(self, "toolbar_primary", None)
        if existing_toolbar is not None:
            self.removeToolBar(existing_toolbar)

        toolbar = QToolBar("Outils principaux", self)
        toolbar.setObjectName("toolbar_primary")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(30, 30))
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)

        self._apply_primary_toolbar_icons()

        self.addToolBar(Qt.TopToolBarArea, toolbar)
        self.toolbar_primary = toolbar

        toolbar.addAction(self.act_new)
        toolbar.addAction(self.act_open)
        toolbar.addAction(self.act_save)
        toolbar.addSeparator()
        toolbar.addAction(self.act_undo_model)
        toolbar.addAction(self.act_redo_model)
        toolbar.addAction(self.act_copy_selection)
        toolbar.addSeparator()
        toolbar.addAction(self.act_define_grid)
        toolbar.addAction(self.act_select_tool)
        toolbar.addAction(self.act_draw_node)
        toolbar.addAction(self.act_draw_bars)
        toolbar.addAction(self.act_draw_surface)
        toolbar.addAction(self.act_draw_orthogonal)
        toolbar.addAction(self.act_cancel_draw)
        toolbar.addSeparator()
        toolbar.addAction(self.act_add_node)
        toolbar.addAction(self.act_add_element)
        toolbar.addSeparator()
        toolbar.addAction(self.act_run)
        toolbar.addAction(self.act_res_deformed)
        toolbar.addSeparator()
        toolbar.addAction(self.act_view_iso)
        toolbar.addAction(self.act_view_xy)
        toolbar.addAction(self.act_view_xz)
        toolbar.addAction(self.act_view_yz)
        optional_show_loads = getattr(self, "act_show_assigned_loads", None)
        if optional_show_loads is not None:
            toolbar.addAction(optional_show_loads)

        for action in toolbar.actions():
            if action.isSeparator() or not action.text():
                continue
            action.setToolTip(action.text())
            action.setStatusTip(action.text())

    def _apply_primary_toolbar_icons(self) -> None:
        """Apply primary toolbar icons."""
        icon_map = {
            self.act_new: "new",
            self.act_open: "open",
            self.act_save: "save",
            self.act_undo_model: "undo",
            self.act_redo_model: "redo",
            self.act_copy_selection: "copy",
            self.act_define_grid: "grid",
            self.act_select_tool: "select",
            self.act_draw_node: "draw_node",
            self.act_draw_bars: "draw_bars",
            self.act_draw_surface: "draw_surface",
            self.act_draw_orthogonal: "orthogonal",
            self.act_cancel_draw: "cancel",
            self.act_add_node: "add_node",
            self.act_add_element: "add_element",
            self.act_run: "run",
            self.act_res_deformed: "deformed",
            self.act_view_iso: "view_iso",
            self.act_view_xy: "view_xy",
            self.act_view_xz: "view_xz",
            self.act_view_yz: "view_yz",
        }
        optional_show_loads = getattr(self, "act_show_assigned_loads", None)
        if optional_show_loads is not None:
            icon_map[optional_show_loads] = "show_loads"
        for action, glyph_name in icon_map.items():
            if action is not None:
                action.setIcon(self._build_toolbar_icon(glyph_name))

    @staticmethod
    def _toolbar_pen(color: QColor, width: float = 1.8) -> QPen:
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _build_toolbar_icon(self, glyph_name: str) -> QIcon:
        icon = QIcon()
        icon.addPixmap(
            self._render_toolbar_icon_pixmap(glyph_name, enabled=True),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        icon.addPixmap(
            self._render_toolbar_icon_pixmap(glyph_name, enabled=False),
            QIcon.Mode.Disabled,
            QIcon.State.Off,
        )
        return icon

    def _render_toolbar_icon_pixmap(self, glyph_name: str, enabled: bool) -> QPixmap:
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_toolbar_glyph(
            painter,
            QRectF(1.0, 1.0, size - 2.0, size - 2.0),
            glyph_name,
            enabled,
        )
        painter.end()
        return pixmap

    def _paint_toolbar_glyph(
        self,
        painter: QPainter,
        rect: QRectF,
        glyph_name: str,
        enabled: bool,
    ) -> None:
        outline = QColor("#23445a")
        accent = QColor("#d97828")
        accent_alt = QColor("#1d8f7a")
        soft = QColor("#d8e4ea")
        danger = QColor("#cf4c4c")

        if not enabled:
            for color in (outline, accent, accent_alt, soft, danger):
                color.setAlpha(105)

        def p(x: float, y: float) -> QPointF:
            return QPointF(
                rect.left() + (rect.width() * x / 24.0),
                rect.top() + (rect.height() * y / 24.0),
            )

        def s(value: float) -> float:
            return rect.width() * value / 24.0

        def draw_plus(cx: float, cy: float, color: QColor, size_hint: float = 2.7) -> None:
            painter.setPen(self._toolbar_pen(color, 2.0))
            painter.drawLine(p(cx - size_hint, cy), p(cx + size_hint, cy))
            painter.drawLine(p(cx, cy - size_hint), p(cx, cy + size_hint))

        def draw_node(cx: float, cy: float, fill: QColor = accent_alt, radius: float = 1.9) -> None:
            center = p(cx, cy)
            node_radius = s(radius)
            painter.setPen(self._toolbar_pen(outline, 1.1))
            painter.setBrush(fill)
            painter.drawEllipse(
                QRectF(
                    center.x() - node_radius,
                    center.y() - node_radius,
                    node_radius * 2.0,
                    node_radius * 2.0,
                )
            )

        def draw_cube(highlight: str | None = None) -> None:
            top = QPolygonF([p(6, 9), p(10, 5), p(17, 5), p(13, 9)])
            front = QPolygonF([p(6, 9), p(13, 9), p(13, 17), p(6, 17)])
            side = QPolygonF([p(13, 9), p(17, 5), p(17, 13), p(13, 17)])
            fills = {
                "top": QColor(soft),
                "front": QColor(soft),
                "side": QColor(soft),
            }
            for name, color in fills.items():
                color.setAlpha(60)
                if highlight == name:
                    color = QColor(accent)
                    color.setAlpha(90)
                fills[name] = color

            painter.setPen(self._toolbar_pen(outline, 1.35))
            painter.setBrush(fills["front"])
            painter.drawPolygon(front)
            painter.setBrush(fills["side"])
            painter.drawPolygon(side)
            painter.setBrush(fills["top"])
            painter.drawPolygon(top)

        painter.setPen(self._toolbar_pen(outline))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if glyph_name == "new":
            painter.setBrush(soft)
            painter.drawRoundedRect(QRectF(p(5, 4).x(), p(5, 4).y(), s(11), s(14)), s(1.4), s(1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(p(12, 4), p(16, 8))
            painter.drawLine(p(12, 4), p(12, 8))
            painter.drawLine(p(12, 8), p(16, 8))
            draw_plus(17.2, 16.2, accent)
        elif glyph_name == "open":
            folder = QPolygonF([p(4, 9), p(8, 9), p(10, 7), p(20, 7), p(18.5, 17), p(5, 17)])
            painter.setBrush(soft)
            painter.drawPolygon(folder)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self._toolbar_pen(accent, 2.0))
            painter.drawLine(p(11, 10), p(15.5, 14.5))
            painter.drawLine(p(15.5, 14.5), p(15.5, 11.7))
            painter.drawLine(p(15.5, 14.5), p(12.7, 14.5))
        elif glyph_name == "save":
            painter.setBrush(soft)
            painter.drawRoundedRect(QRectF(p(5, 4).x(), p(5, 4).y(), s(14), s(15)), s(1.4), s(1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(p(8, 5.5).x(), p(8, 5.5).y(), s(7.5), s(4.0)))
            painter.drawRect(QRectF(p(8, 12).x(), p(8, 12).y(), s(8.0), s(5.0)))
            painter.setPen(self._toolbar_pen(accent, 1.8))
            painter.drawLine(p(17.5, 5.8), p(17.5, 9.2))
        elif glyph_name == "undo":
            painter.setPen(self._toolbar_pen(outline, 2.1))
            painter.drawPolyline(QPolygonF([p(17.5, 7), p(10, 7), p(6.5, 10.5), p(10, 14), p(17.5, 14)]))
            painter.setPen(self._toolbar_pen(accent, 2.1))
            painter.drawLine(p(6.5, 10.5), p(9.7, 7.3))
            painter.drawLine(p(6.5, 10.5), p(9.7, 13.7))
        elif glyph_name == "redo":
            painter.setPen(self._toolbar_pen(outline, 2.1))
            painter.drawPolyline(QPolygonF([p(6.5, 7), p(14, 7), p(17.5, 10.5), p(14, 14), p(6.5, 14)]))
            painter.setPen(self._toolbar_pen(accent, 2.1))
            painter.drawLine(p(17.5, 10.5), p(14.3, 7.3))
            painter.drawLine(p(17.5, 10.5), p(14.3, 13.7))
        elif glyph_name == "copy":
            painter.drawRoundedRect(QRectF(p(8, 5).x(), p(8, 5).y(), s(9), s(10.5)), s(1.2), s(1.2))
            painter.setBrush(soft)
            painter.drawRoundedRect(QRectF(p(5, 8).x(), p(5, 8).y(), s(9), s(10.5)), s(1.2), s(1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif glyph_name == "grid":
            painter.drawRect(QRectF(p(5, 5).x(), p(5, 5).y(), s(14), s(14)))
            for coord in (9.7, 14.3):
                painter.drawLine(p(coord, 5), p(coord, 19))
                painter.drawLine(p(5, coord), p(19, coord))
            draw_node(9.7, 9.7, accent)
            draw_node(14.3, 9.7, accent)
            draw_node(9.7, 14.3, accent)
            draw_node(14.3, 14.3, accent)
        elif glyph_name == "select":
            pointer = QPolygonF([p(6, 4), p(14, 13), p(10.8, 13.4), p(13.3, 18), p(11.2, 19), p(8.8, 14.2), p(6, 16)])
            painter.setPen(self._toolbar_pen(outline, 1.2))
            painter.setBrush(accent)
            painter.drawPolygon(pointer)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif glyph_name == "draw_node":
            painter.setPen(self._toolbar_pen(outline, 1.4))
            painter.drawLine(p(6, 12), p(18, 12))
            painter.drawLine(p(12, 6), p(12, 18))
            draw_node(12, 12, accent, 2.3)
            painter.setPen(self._toolbar_pen(accent_alt, 1.8))
            painter.drawLine(p(15.5, 7), p(18.3, 9.8))
            painter.drawLine(p(14.7, 8.7), p(16.6, 6.8))
        elif glyph_name == "draw_bars":
            painter.setPen(self._toolbar_pen(accent, 2.2))
            painter.drawLine(p(6, 17), p(18, 7))
            draw_node(6, 17)
            draw_node(18, 7)
        elif glyph_name == "draw_surface":
            painter.setPen(self._toolbar_pen(accent, 2.0))
            quad = QPolygonF([p(6, 16), p(17, 16), p(19, 8), p(8, 8)])
            painter.setBrush(QColor(216, 228, 234, 80))
            painter.drawPolygon(quad)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            draw_node(6, 16)
            draw_node(17, 16)
            draw_node(19, 8)
            draw_node(8, 8)
        elif glyph_name == "orthogonal":
            painter.setPen(self._toolbar_pen(accent, 2.2))
            painter.drawLine(p(6, 17), p(6, 8))
            painter.drawLine(p(6, 8), p(17, 8))
            draw_node(6, 17)
            draw_node(6, 8)
            draw_node(17, 8)
        elif glyph_name == "cancel":
            painter.drawEllipse(QRectF(p(5, 5).x(), p(5, 5).y(), s(14), s(14)))
            painter.setPen(self._toolbar_pen(danger, 2.2))
            painter.drawLine(p(8, 8), p(16, 16))
            painter.drawLine(p(16, 8), p(8, 16))
        elif glyph_name == "add_node":
            draw_node(10, 13, accent, 2.4)
            draw_plus(16.8, 8.6, accent_alt)
        elif glyph_name == "add_element":
            painter.setPen(self._toolbar_pen(accent, 2.2))
            painter.drawLine(p(6, 17), p(14, 9))
            draw_node(6, 17)
            draw_node(14, 9)
            draw_plus(17.3, 7.8, accent_alt, 2.4)
        elif glyph_name == "run":
            painter.setBrush(soft)
            painter.drawEllipse(QRectF(p(4.8, 4.8).x(), p(4.8, 4.8).y(), s(14.4), s(14.4)))
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([p(10, 8.2), p(10, 15.8), p(16.5, 12)]))
        elif glyph_name == "deformed":
            painter.setPen(self._toolbar_pen(outline, 1.8))
            painter.drawLine(p(5.5, 16.5), p(18.5, 16.5))
            painter.setPen(self._toolbar_pen(accent, 2.1))
            painter.drawPolyline(
                QPolygonF([p(5.5, 16.5), p(9.5, 14.0), p(13.5, 9.2), p(18.5, 7.5)])
            )
            draw_node(5.5, 16.5, accent_alt, 1.4)
            draw_node(18.5, 7.5, accent_alt, 1.4)
        elif glyph_name == "view_iso":
            draw_cube()
            painter.setPen(self._toolbar_pen(accent, 1.8))
            painter.drawLine(p(10, 5), p(10, 13))
            painter.drawLine(p(10, 13), p(17, 13))
        elif glyph_name == "view_xy":
            draw_cube("top")
        elif glyph_name == "view_xz":
            draw_cube("front")
        elif glyph_name == "view_yz":
            draw_cube("side")
        elif glyph_name == "show_loads":
            painter.setPen(self._toolbar_pen(outline, 2.1))
            painter.drawLine(p(5.5, 16.5), p(18.5, 16.5))
            draw_node(6.8, 16.5, accent_alt, 1.5)
            draw_node(17.2, 16.5, accent_alt, 1.5)
            painter.setPen(self._toolbar_pen(accent, 1.8))
            for x in (8.0, 12.0, 16.0):
                painter.drawLine(p(x, 6.0), p(x, 13.5))
                painter.drawLine(p(x, 13.5), p(x - 1.3, 11.7))
                painter.drawLine(p(x, 13.5), p(x + 1.3, 11.7))

    def _setup_parallel_view_controls(self) -> None:
        """Set up parallel view controls."""
        if self.toolbar_main is None or self.model_view is None:
            return

        self.lbl_draw_section = QLabel("Section :", self)
        self.combo_draw_section = QComboBox(self)
        self.combo_draw_section.setMinimumWidth(180)
        self.lbl_draw_section.hide()
        self.combo_draw_section.hide()

        self.lbl_plane = QLabel("Vue A :", self)
        self.combo_plane = QComboBox(self)
        self.combo_plane.addItems(["3D", "XY", "XZ", "YZ"])
        self.combo_plane.currentTextChanged.connect(self._on_parallel_plane_changed)
        self.lbl_plane.hide()
        self.combo_plane.hide()

        self.lbl_file = QLabel("Z =", self)
        self.combo_parallel_value = QComboBox(self)
        self.combo_parallel_value.setMinimumWidth(140)
        self.combo_parallel_value.currentIndexChanged.connect(
            self._on_parallel_value_changed
        )
        self.lbl_file.hide()
        self.combo_parallel_value.hide()
        self.act_prev_parallel = QAction("File précédente", self)
        self.act_prev_parallel.triggered.connect(lambda: self._step_parallel_value(-1))
        self.act_next_parallel = QAction("File suivante", self)
        self.act_next_parallel.triggered.connect(lambda: self._step_parallel_value(1))

        self.lbl_secondary_plane = QLabel("Vue B :", self)
        self.combo_secondary_plane = QComboBox(self)
        self.combo_secondary_plane.addItems(["3D", "XY", "XZ", "YZ"])
        self.combo_secondary_plane.setCurrentText("3D")
        self.combo_secondary_plane.currentTextChanged.connect(
            self._on_secondary_parallel_plane_changed
        )
        self.lbl_secondary_plane.hide()
        self.combo_secondary_plane.hide()

        self.lbl_secondary_file = QLabel("Z =", self)
        self.combo_secondary_value = QComboBox(self)
        self.combo_secondary_value.setMinimumWidth(140)
        self.combo_secondary_value.currentIndexChanged.connect(
            self._on_secondary_parallel_value_changed
        )
        self.lbl_secondary_file.hide()
        self.combo_secondary_value.hide()

        self._refresh_draw_section_controls()
        self._refresh_parallel_view_controls(apply_view=False)

    def _refresh_model_management_menus(self) -> None:
        """Refresh model management menus."""
        surface_features_enabled = self._surface_features_enabled()
        surface_features_reason = self._surface_features_disabled_reason()
        selected_surface_tags = self._selected_existing_surface_tags()
        selected_surface_count = len(selected_surface_tags)
        self._sync_plate_editing_state()
        if hasattr(self, "act_manage_materials"):
            self.act_manage_materials.setText(
                f"Matériaux... ({len(self.project.materials)})"
            )
        if hasattr(self, "act_manage_sections"):
            self.act_manage_sections.setText(
                f"Sections... ({len(self._line_section_items())})"
            )
        if hasattr(self, "act_manage_plate_sections"):
            self.act_manage_plate_sections.setText(
                f"Sections plaque... ({len(self._surface_section_items())})"
            )
            self.act_manage_plate_sections.setEnabled(surface_features_enabled)
            self.act_manage_plate_sections.setToolTip(
                self.act_manage_plate_sections.text()
                if surface_features_enabled
                else surface_features_reason
            )
            self.act_manage_plate_sections.setStatusTip(self.act_manage_plate_sections.toolTip())
        if hasattr(self, "act_cancel_draw"):
            self.act_cancel_draw.setEnabled(
                self._draw_start_point is not None
                or bool(getattr(self, "_draw_surface_points", []))
            )
        if hasattr(self, "act_assign_load_selection"):
            selected_count = (
                len(self._selected_existing_node_tags())
                + len(self._selected_existing_element_tags())
            )
            self.act_assign_load_selection.setText(
                f"Affecter charges à la sélection... ({selected_count})"
                if selected_count
                else "Affecter charges à la sélection..."
            )
            self.act_assign_load_selection.setEnabled(selected_count > 0)
        if hasattr(self, "act_add_surface"):
            selected_node_count = len(self._selected_existing_node_tags())
            surface_section_count = len(self._surface_section_items())
            self.act_add_surface.setText(
                f"Ajouter une surface depuis la sélection... ({selected_node_count})"
                if selected_node_count
                else "Ajouter une surface depuis la sélection..."
            )
            self.act_add_surface.setEnabled(
                surface_features_enabled
                and selected_node_count in (3, 4)
                and surface_section_count > 0
            )
            self.act_add_surface.setToolTip(
                self.act_add_surface.text()
                if surface_features_enabled
                else surface_features_reason
            )
            self.act_add_surface.setStatusTip(self.act_add_surface.toolTip())
        if hasattr(self, "act_edit_surface"):
            selected_surface_tag = selected_surface_tags[0] if selected_surface_count == 1 else None
            self.act_edit_surface.setText(
                f"Modifier la surface S{selected_surface_tag}..."
                if selected_surface_tag is not None
                else "Modifier la surface sélectionnée..."
            )
            edit_surface_enabled = surface_features_enabled and selected_surface_count == 1
            edit_surface_reason = (
                self.act_edit_surface.text()
                if edit_surface_enabled
                else (
                    surface_features_reason
                    if not surface_features_enabled
                    else "Sélectionnez une seule surface pour la modifier."
                )
            )
            self.act_edit_surface.setEnabled(edit_surface_enabled)
            self.act_edit_surface.setToolTip(edit_surface_reason)
            self.act_edit_surface.setStatusTip(edit_surface_reason)
        if hasattr(self, "act_add_plate_section"):
            self.act_add_plate_section.setEnabled(surface_features_enabled)
            self.act_add_plate_section.setToolTip(
                self.act_add_plate_section.text()
                if surface_features_enabled
                else surface_features_reason
            )
            self.act_add_plate_section.setStatusTip(self.act_add_plate_section.toolTip())
        if hasattr(self, "act_draw_surface"):
            self.act_draw_surface.setEnabled(
                surface_features_enabled and len(self._surface_section_items()) > 0
            )
            self.act_draw_surface.setToolTip(
                self.act_draw_surface.text()
                if surface_features_enabled
                else surface_features_reason
            )
            self.act_draw_surface.setStatusTip(self.act_draw_surface.toolTip())
        if hasattr(self, "act_copy_selection"):
            can_copy = (
                bool(self._selected_existing_node_tags())
                or bool(self._selected_existing_element_tags())
                or (surface_features_enabled and bool(selected_surface_tags))
            )
            self.act_copy_selection.setEnabled(can_copy)
            if hasattr(self, "btn_copy_selection"):
                self.btn_copy_selection.setEnabled(can_copy)

    def _refresh_parallel_view_controls(self, apply_view: bool = True) -> None:
        """Refresh parallel view controls."""
        if self.model_view is None or not hasattr(self, "combo_plane"):
            return

        plane = self.combo_plane.currentText() or "3D"
        if plane == "3D":
            self.lbl_file.setText("File =")
            self.combo_parallel_value.blockSignals(True)
            self.combo_parallel_value.clear()
            self.combo_parallel_value.blockSignals(False)
            self.combo_parallel_value.setEnabled(False)
            if hasattr(self, "act_prev_parallel"):
                self.act_prev_parallel.setEnabled(False)
            if hasattr(self, "act_next_parallel"):
                self.act_next_parallel.setEnabled(False)
            self._active_parallel_plane = "3D"
            self._active_parallel_value = None
            if apply_view:
                self._apply_parallel_view()
            self._refresh_secondary_parallel_controls(apply_view=apply_view)
            return

        axis_label = self.model_view.plane_axis_label(plane)
        self.lbl_file.setText(f"{axis_label} =")

        values = self.model_view.plane_values(self.project.grid, plane)
        self.combo_parallel_value.blockSignals(True)
        self.combo_parallel_value.clear()
        for value in values:
            self.combo_parallel_value.addItem(f"{value:.3f} m", value)
        self.combo_parallel_value.blockSignals(False)
        self.combo_parallel_value.setEnabled(bool(values))

        if not values:
            self._active_parallel_value = None
            if hasattr(self, "act_prev_parallel"):
                self.act_prev_parallel.setEnabled(False)
            if hasattr(self, "act_next_parallel"):
                self.act_next_parallel.setEnabled(False)
            self._refresh_secondary_parallel_controls(apply_view=apply_view)
            return

        target_idx = 0
        if self._active_parallel_plane == plane and self._active_parallel_value is not None:
            for idx, value in enumerate(values):
                if abs(value - self._active_parallel_value) <= 1e-9:
                    target_idx = idx
                    break

        self.combo_parallel_value.setCurrentIndex(target_idx)
        self._active_parallel_plane = plane
        self._active_parallel_value = float(values[target_idx])
        if hasattr(self, "act_prev_parallel"):
            self.act_prev_parallel.setEnabled(target_idx > 0)
        if hasattr(self, "act_next_parallel"):
            self.act_next_parallel.setEnabled(target_idx < len(values) - 1)
        if apply_view:
            self._apply_parallel_view()
        self._refresh_secondary_parallel_controls(apply_view=apply_view)

    def _refresh_draw_section_controls(self) -> None:
        """Refresh draw section controls."""
        if not hasattr(self, "combo_draw_section"):
            return

        current = self.combo_draw_section.currentData()
        self.combo_draw_section.blockSignals(True)
        self.combo_draw_section.clear()
        for tag, sec in self._line_section_items():
            self.combo_draw_section.addItem(f"{sec.name} (T{tag})", tag)
        self.combo_draw_section.blockSignals(False)

        if self.combo_draw_section.count() == 0:
            return

        idx = self.combo_draw_section.findData(current)
        if idx < 0:
            idx = 0
        self.combo_draw_section.setCurrentIndex(idx)

    def _apply_parallel_view(self, refresh_scene: bool = True) -> None:
        """Apply parallel view."""
        if self.model_view is not None:
            if self._active_parallel_plane == "3D" or self._active_parallel_value is None:
                self.model_view.set_parallel_plane(None, None, refresh_scene=refresh_scene)
            else:
                self.model_view.set_parallel_plane(
                    self._active_parallel_plane,
                    self._active_parallel_value,
                    refresh_scene=refresh_scene,
                )

    def _on_parallel_plane_changed(self, plane: str) -> None:
        """Handle parallel plane changed."""
        self._active_parallel_plane = plane
        self._active_parallel_value = None
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._refresh_parallel_view_controls(apply_view=True)

    def _on_parallel_value_changed(self, idx: int) -> None:
        """Handle parallel value changed."""
        if idx < 0 or not hasattr(self, "combo_parallel_value"):
            return
        value = self.combo_parallel_value.itemData(idx)
        if value is None:
            return
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._active_parallel_value = float(value)
        if hasattr(self, "act_prev_parallel"):
            self.act_prev_parallel.setEnabled(idx > 0)
        if hasattr(self, "act_next_parallel"):
            self.act_next_parallel.setEnabled(idx < self.combo_parallel_value.count() - 1)
        self._apply_parallel_view()

    def _step_parallel_value(self, delta: int) -> None:
        """Handle step parallel value."""
        if not hasattr(self, "combo_parallel_value"):
            return
        count = self.combo_parallel_value.count()
        if count <= 0:
            return
        current = self.combo_parallel_value.currentIndex()
        if current < 0:
            current = 0
        new_index = max(0, min(count - 1, current + delta))
        if new_index != current:
            self.combo_parallel_value.setCurrentIndex(new_index)

    def _refresh_secondary_parallel_controls(self, apply_view: bool = True) -> None:
        """Refresh secondary parallel controls."""
        if self.model_view is None or not hasattr(self, "combo_secondary_plane"):
            return

        plane = self.combo_secondary_plane.currentText() or "3D"
        if plane == "3D":
            self.lbl_secondary_file.setText("File =")
            self.combo_secondary_value.blockSignals(True)
            self.combo_secondary_value.clear()
            self.combo_secondary_value.blockSignals(False)
            self.combo_secondary_value.setEnabled(False)
            self._secondary_parallel_plane = "3D"
            self._secondary_parallel_value = None
            if apply_view:
                self._apply_secondary_parallel_view()
            return

        axis_label = self.model_view.plane_axis_label(plane)
        self.lbl_secondary_file.setText(f"{axis_label} =")

        values = self.model_view.plane_values(self.project.grid, plane)
        self.combo_secondary_value.blockSignals(True)
        self.combo_secondary_value.clear()
        for value in values:
            self.combo_secondary_value.addItem(f"{value:.3f} m", value)
        self.combo_secondary_value.blockSignals(False)
        self.combo_secondary_value.setEnabled(bool(values))

        if not values:
            self._secondary_parallel_plane = plane
            self._secondary_parallel_value = None
            if apply_view:
                self._apply_secondary_parallel_view()
            return

        target_idx = 0
        if self._secondary_parallel_plane == plane and self._secondary_parallel_value is not None:
            for idx, value in enumerate(values):
                if abs(value - self._secondary_parallel_value) <= 1e-9:
                    target_idx = idx
                    break

        self.combo_secondary_value.setCurrentIndex(target_idx)
        self._secondary_parallel_plane = plane
        self._secondary_parallel_value = float(values[target_idx])
        if apply_view:
            self._apply_secondary_parallel_view()

    def _apply_secondary_parallel_view(self, refresh_scene: bool = True) -> None:
        """Apply secondary parallel view."""
        if getattr(self, "secondary_view", None) is None or not hasattr(self.secondary_view, "set_parallel_plane"):
            return
        if self._secondary_parallel_plane == "3D" or self._secondary_parallel_value is None:
            self.secondary_view.set_parallel_plane(None, None, refresh_scene=refresh_scene)
            return
        self.secondary_view.set_parallel_plane(
            self._secondary_parallel_plane,
            self._secondary_parallel_value,
            refresh_scene=refresh_scene,
        )

    def _on_secondary_parallel_plane_changed(self, plane: str) -> None:
        """Handle secondary parallel plane changed."""
        self._secondary_parallel_plane = plane
        self._secondary_parallel_value = None
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._refresh_secondary_parallel_controls()

    def _on_secondary_parallel_value_changed(self, idx: int) -> None:
        """Handle secondary parallel value changed."""
        if idx < 0 or not hasattr(self, "combo_secondary_value"):
            return
        value = self.combo_secondary_value.itemData(idx)
        if value is None:
            return
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._secondary_parallel_value = float(value)
        self._apply_secondary_parallel_view()

    def _define_grid(self) -> None:
        """Handle define grid."""
        from gui.dialogs.grid_dlg import GridDialog

        default_enabled = (
            not self.project.grid.enabled
            and self.project.grid == ProjectModel().grid
            and not self.project.file_path
        )
        dlg = GridDialog(
            self,
            grid=self.project.grid,
            default_enabled=default_enabled,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self.project.grid = dlg.result()
        self._apply_grid_working_views()
        self._mark_project_modified()
        self._refresh()
        axis_summary = ", ".join(
            f"{axis}={len(self.project.grid.axis_entries(axis))} axes"
            for axis in ("X", "Y", "Z")
        )
        self._log(
            "Grille 3D mise à jour : "
            f"{axis_summary}"
        )

    def _toggle_split_view(self, enabled: bool) -> None:
        """Toggle split view."""
        if getattr(self, "secondary_view", None) is not None:
            self.secondary_view.setVisible(enabled)
        if getattr(self, "_view_splitter", None) is not None:
            self._view_splitter.handle(1).setEnabled(enabled)
            if enabled:
                self._view_splitter.setSizes([1, 1])
            else:
                self._view_splitter.setSizes([0, 1])

        for name in (
            "lbl_secondary_plane",
            "combo_secondary_plane",
            "lbl_secondary_file",
            "combo_secondary_value",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(enabled)

    def _set_interactive_drawing_enabled(self, enabled: bool) -> None:
        """Set interactive drawing enabled."""
        if self.model_view is not None:
            self.model_view.set_drawing_mode(enabled)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_drawing_mode"):
            self.secondary_view.set_drawing_mode(enabled)

    def _set_selection_mode_enabled(self, enabled: bool) -> None:
        """Set selection mode enabled."""
        self._selection_mode_active = enabled
        if self.model_view is not None and hasattr(self.model_view, "set_selection_mode"):
            self.model_view.set_selection_mode(enabled)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selection_mode"):
            self.secondary_view.set_selection_mode(enabled)

    def _toggle_selection_tool(self, enabled: bool) -> None:
        """Toggle selection tool."""
        draw_tool_active = (
            (getattr(self, "act_draw_node", None) is not None and self.act_draw_node.isChecked())
            or (getattr(self, "act_draw_bars", None) is not None and self.act_draw_bars.isChecked())
            or (getattr(self, "act_draw_surface", None) is not None and self.act_draw_surface.isChecked())
        )
        if not enabled and self._draw_mode_kind is None and not draw_tool_active:
            self.act_select_tool.setChecked(True)
            return
        if enabled:
            if getattr(self, "act_draw_node", None) is not None and self.act_draw_node.isChecked():
                self.act_draw_node.setChecked(False)
            if getattr(self, "act_draw_bars", None) is not None and self.act_draw_bars.isChecked():
                self.act_draw_bars.setChecked(False)
            if getattr(self, "act_draw_surface", None) is not None and self.act_draw_surface.isChecked():
                self.act_draw_surface.setChecked(False)
            self._draw_mode_kind = None
            self._set_interactive_drawing_enabled(False)
        self._set_selection_mode_enabled(enabled)

    def _activate_selection_tool(self) -> None:
        """Handle activate selection tool."""
        if getattr(self, "act_select_tool", None) is not None:
            self.act_select_tool.setChecked(True)

    def _interactive_drawing_enabled(self) -> bool:
        """Return whether an interactive drawing mode is active."""
        return (
            (getattr(self, "act_draw_bars", None) is not None and self.act_draw_bars.isChecked())
            or (getattr(self, "act_draw_node", None) is not None and self.act_draw_node.isChecked())
            or (getattr(self, "act_draw_surface", None) is not None and self.act_draw_surface.isChecked())
        )

    def _toggle_draw_nodes(self, enabled: bool) -> None:
        """Toggle draw nodes."""
        if self.model_view is None:
            self.act_draw_node.setChecked(False)
            return

        if enabled and not self.project.grid.enabled:
            QMessageBox.information(
                self,
                "Dessin sur grille",
                "Définissez d'abord une grille active avant de dessiner.",
            )
            self.act_draw_node.setChecked(False)
            return

        if enabled and getattr(self, "act_draw_bars", None) is not None and self.act_draw_bars.isChecked():
            self.act_draw_bars.setChecked(False)
        if enabled and getattr(self, "act_draw_surface", None) is not None and self.act_draw_surface.isChecked():
            self.act_draw_surface.setChecked(False)
        if enabled and getattr(self, "act_select_tool", None) is not None and self.act_select_tool.isChecked():
            self.act_select_tool.setChecked(False)
        if enabled:
            self._ensure_work_plane_for_drawing()

        self._draw_mode_kind = "node" if enabled else None
        if not enabled and getattr(self, "act_select_tool", None) is not None:
            self.act_select_tool.setChecked(True)
        self._set_selection_mode_enabled(not enabled)
        self._set_interactive_drawing_enabled(enabled)
        self._cancel_bar_drawing()
        if enabled:
            self._log("Mode dessin de nœuds activé : cliquez une intersection de grille.")
        else:
            self._log("Mode dessin de nœuds désactivé.")

    def _prompt_draw_section_tag(self) -> int | None:
        """Handle prompt draw section tag."""
        tag = self._choose_section_tag(
            "Section de dessin",
            "Choisissez la section à dessiner :",
            include_surface=False,
        )
        if tag is None:
            return None
        if hasattr(self, "combo_draw_section") and self.combo_draw_section.count():
            idx = self.combo_draw_section.findData(tag)
            if idx >= 0:
                self.combo_draw_section.setCurrentIndex(idx)
        return tag

    def _toggle_draw_bars(self, enabled: bool) -> None:
        """Toggle draw bars."""
        if self.model_view is None:
            self.act_draw_bars.setChecked(False)
            return

        if enabled and not self.project.grid.enabled:
            QMessageBox.information(
                self,
                "Dessin sur grille",
                "Définissez d'abord une grille active avant de dessiner.",
            )
            self.act_draw_bars.setChecked(False)
            return
        if enabled and self._default_draw_section_tag() is None:
            QMessageBox.information(
                self,
                "Dessin sur grille",
                "Créez ou choisissez d'abord une section pour dessiner des barres.",
            )
            self.act_draw_bars.setChecked(False)
            return

        if enabled:
            section_tag = self._prompt_draw_section_tag()
            if section_tag is None:
                self.act_draw_bars.setChecked(False)
                return
        else:
            section_tag = self._default_draw_section_tag()

        if enabled and getattr(self, "act_draw_node", None) is not None and self.act_draw_node.isChecked():
            self.act_draw_node.setChecked(False)
        if enabled and getattr(self, "act_draw_surface", None) is not None and self.act_draw_surface.isChecked():
            self.act_draw_surface.setChecked(False)
        if enabled and getattr(self, "act_select_tool", None) is not None and self.act_select_tool.isChecked():
            self.act_select_tool.setChecked(False)
        if enabled:
            self._ensure_work_plane_for_drawing()

        self._draw_mode_kind = "bar" if enabled else None
        if not enabled and getattr(self, "act_select_tool", None) is not None:
            self.act_select_tool.setChecked(True)
        self._set_selection_mode_enabled(not enabled)
        self._set_interactive_drawing_enabled(enabled)
        if not enabled:
            self._cancel_bar_drawing()
            self._log("Mode dessin de barres désactivé.")
        else:
            section_name = (
                self.project.sections[section_tag].name
                if section_tag in self.project.sections
                else "inconnue"
            )
            self._log(
                "Mode dessin de barres activé : "
                f"section « {section_name} », cliquez deux intersections de la file active. "
                "Les diagonales sont autorisées tant que le tracé orthogonal reste désactivé."
            )

    def _toggle_draw_surface(self, enabled: bool) -> None:
        """Toggle draw surface."""
        if self.model_view is None:
            self.act_draw_surface.setChecked(False)
            return
        if enabled and not self._ensure_surface_features_available():
            self.act_draw_surface.setChecked(False)
            return

        if enabled and not self.project.grid.enabled:
            QMessageBox.information(
                self,
                "Dessin sur grille",
                "Définissez d'abord une grille active avant de dessiner.",
            )
            self.act_draw_surface.setChecked(False)
            return

        if enabled:
            section_tag = self._choose_surface_section_tag()
            if section_tag is None:
                self.act_draw_surface.setChecked(False)
                return
            sec = self.project.sections.get(section_tag)
            if sec is None or not sec.is_surface or not self._supports_rectangular_surface_drawing(sec):
                self._restore_surface_draw_orthogonal_mode()
                self.act_draw_surface.setChecked(False)
                return
        else:
            section_tag = None
            sec = None

        if enabled and getattr(self, "act_draw_node", None) is not None and self.act_draw_node.isChecked():
            self.act_draw_node.setChecked(False)
        if enabled and getattr(self, "act_draw_bars", None) is not None and self.act_draw_bars.isChecked():
            self.act_draw_bars.setChecked(False)
        if enabled and getattr(self, "act_select_tool", None) is not None and self.act_select_tool.isChecked():
            self.act_select_tool.setChecked(False)
        self._cancel_bar_drawing()
        self._draw_surface_section_tag = section_tag
        self._draw_mode_kind = "surface" if enabled else None
        if not enabled and getattr(self, "act_select_tool", None) is not None:
            self.act_select_tool.setChecked(True)
        self._set_selection_mode_enabled(not enabled)
        self._set_interactive_drawing_enabled(enabled)
        if not enabled:
            self._log("Mode dessin de surfaces désactivé.")
            return

        sec = self.project.sections.get(section_tag)
        formulation = sec.surface_formulation if sec is not None else "ShellMITC4"
        self._log(
            "Mode dessin de surfaces activé : "
            f"section « {sec.name if sec is not None else f'T{section_tag}'} », "
            f"formulation {formulation}, cliquez 4 coins coplanaires, même sur un plan incliné. "
            "Clic droit annule un contour incomplet ; après 3 coins, il ferme automatiquement "
            "la plaque en parallélogramme."
        )

    def _cancel_bar_drawing(self) -> None:
        """Handle cancel bar drawing."""
        self._draw_start_point = None
        self._draw_surface_points = []
        self._draw_surface_section_tag = None
        if self.model_view is not None:
            self.model_view.clear_drawing_state()
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "clear_drawing_state"):
            self.secondary_view.clear_drawing_state()
        self._refresh_model_management_menus()

    def _reset_bar_draw_origin(self) -> None:
        """Reset bar draw origin."""
        self._draw_start_point = None
        if self.model_view is not None:
            self.model_view.set_preview_start(None)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_preview_start"):
            self.secondary_view.set_preview_start(None)
        self._refresh_model_management_menus()

    def _reset_surface_draw_points(self) -> None:
        """Reset surface draw points."""
        self._draw_surface_points = []
        self._draw_start_point = None
        if self.model_view is not None:
            self.model_view.set_preview_start(None)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_preview_start"):
            self.secondary_view.set_preview_start(None)
        self._refresh_model_management_menus()

    def _lock_surface_draw_orthogonal_mode(self) -> None:
        """Lock surface draw orthogonal mode."""
        action = getattr(self, "act_draw_orthogonal", None)
        if action is None:
            return
        if getattr(self, "_surface_draw_saved_orthogonal_state", None) is None:
            self._surface_draw_saved_orthogonal_state = bool(action.isChecked())
        action.setChecked(True)
        action.setEnabled(False)

    def _restore_surface_draw_orthogonal_mode(self) -> None:
        """Restore surface draw orthogonal mode."""
        action = getattr(self, "act_draw_orthogonal", None)
        if action is None:
            self._surface_draw_saved_orthogonal_state = None
            return
        saved_state = getattr(self, "_surface_draw_saved_orthogonal_state", None)
        action.setEnabled(True)
        if saved_state is not None:
            action.setChecked(bool(saved_state))
        self._surface_draw_saved_orthogonal_state = None

    def _supports_rectangular_surface_drawing(self, section) -> bool:
        """Return whether rectangular surface drawing."""
        formulation = section.surface_formulation
        if surface_expected_node_count(formulation) == 4:
            return True
        QMessageBox.information(
            self,
            "Dessin plaque temporairement limité",
            "Le dessin interactif des plaques est provisoirement limité aux dalles et voiles "
            "quadrangulaires. Choisissez une section de type ShellMITC4, "
            "ShellDKGQ ou ShellNLDKGQ.",
        )
        return False

    @staticmethod
    def _surface_sub(
        p1: tuple[float, float, float],
        p0: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return (
            float(p1[0] - p0[0]),
            float(p1[1] - p0[1]),
            float(p1[2] - p0[2]),
        )

    @staticmethod
    def _surface_cross(
        v1: tuple[float, float, float],
        v2: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0],
        )

    @staticmethod
    def _surface_dot(
        v1: tuple[float, float, float],
        v2: tuple[float, float, float],
    ) -> float:
        return float(v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2])

    @classmethod
    def _surface_norm(cls, vector: tuple[float, float, float]) -> float:
        return math.sqrt(cls._surface_dot(vector, vector))

    @classmethod
    def _surface_normal_for_points(
        cls,
        points: list[tuple[float, float, float]],
        tol: float = 1e-9,
    ) -> tuple[float, float, float] | None:
        """Handle surface normal for points."""
        if len(points) < 3:
            return None

        origin = points[0]
        normal: tuple[float, float, float] | None = None
        for i in range(1, len(points) - 1):
            v1 = cls._surface_sub(points[i], origin)
            if cls._surface_norm(v1) <= tol:
                continue
            for j in range(i + 1, len(points)):
                v2 = cls._surface_sub(points[j], origin)
                candidate = cls._surface_cross(v1, v2)
                norm = cls._surface_norm(candidate)
                if norm > tol:
                    normal = (
                        candidate[0] / norm,
                        candidate[1] / norm,
                        candidate[2] / norm,
                    )
                    break
            if normal is not None:
                break
        if normal is None:
            return None

        for point in points:
            distance = abs(cls._surface_dot(cls._surface_sub(point, origin), normal))
            if distance > tol:
                return None
        return normal

    @classmethod
    def _surface_projection_basis(
        cls,
        points: list[tuple[float, float, float]],
        tol: float = 1e-9,
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ] | None:
        """Handle surface projection basis."""
        normal = cls._surface_normal_for_points(points, tol=tol)
        if normal is None:
            return None

        origin = points[0]
        u_axis: tuple[float, float, float] | None = None
        for point in points[1:]:
            candidate = cls._surface_sub(point, origin)
            norm = cls._surface_norm(candidate)
            if norm > tol:
                u_axis = (
                    candidate[0] / norm,
                    candidate[1] / norm,
                    candidate[2] / norm,
                )
                break
        if u_axis is None:
            return None

        v_axis = cls._surface_cross(normal, u_axis)
        v_norm = cls._surface_norm(v_axis)
        if v_norm <= tol:
            return None
        v_axis = (
            v_axis[0] / v_norm,
            v_axis[1] / v_norm,
            v_axis[2] / v_norm,
        )
        return origin, u_axis, v_axis

    @classmethod
    def _surface_project_on_basis(
        cls,
        point: tuple[float, float, float],
        origin: tuple[float, float, float],
        u_axis: tuple[float, float, float],
        v_axis: tuple[float, float, float],
    ) -> tuple[float, float]:
        relative = cls._surface_sub(point, origin)
        return cls._surface_dot(relative, u_axis), cls._surface_dot(relative, v_axis)

    @staticmethod
    def _surface_point_on_plane(
        point: tuple[float, float, float],
        plane: str,
    ) -> tuple[float, float]:
        """Handle surface point on plane."""
        if plane == "XY":
            return float(point[0]), float(point[1])
        if plane == "XZ":
            return float(point[0]), float(point[2])
        return float(point[1]), float(point[2])

    @staticmethod
    def _surface_point_from_plane(
        uv: tuple[float, float],
        plane: str,
        reference: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        """Handle surface point from plane."""
        if plane == "XY":
            return float(uv[0]), float(uv[1]), float(reference[2])
        if plane == "XZ":
            return float(uv[0]), float(reference[1]), float(uv[1])
        return float(reference[0]), float(uv[0]), float(uv[1])

    @staticmethod
    def _surface_axis_for_segment(
        start: tuple[float, float],
        end: tuple[float, float],
        tol: float = 1e-9,
    ) -> int | None:
        """Handle surface axis for segment."""
        du = float(end[0] - start[0])
        dv = float(end[1] - start[1])
        if abs(du) <= tol and abs(dv) <= tol:
            return None
        if abs(dv) <= tol and abs(du) > tol:
            return 0
        if abs(du) <= tol and abs(dv) > tol:
            return 1
        return None

    def _surface_rectangle_closing_point(
        self,
        points: list[tuple[float, float, float]],
        plane: str | None = None,
    ) -> tuple[float, float, float] | None:
        """Handle surface rectangle closing point."""
        del plane
        if len(points) != 3:
            return None
        if self._surface_normal_for_points(points) is None:
            return None
        p0, p1, p2 = points
        return (
            float(p0[0] + p2[0] - p1[0]),
            float(p0[1] + p2[1] - p1[1]),
            float(p0[2] + p2[2] - p1[2]),
        )

    @staticmethod
    def _surface_distinct_coordinates(
        values: list[float],
        tol: float = 1e-9,
    ) -> list[float]:
        """Handle surface distinct coordinates."""
        groups: list[float] = []
        for value in sorted(float(v) for v in values):
            if not groups or abs(value - groups[-1]) > tol:
                groups.append(value)
        return groups

    def _surface_is_axis_aligned_rectangle(
        self,
        node_tags: list[int] | tuple[int, ...],
        plane: str,
    ) -> bool:
        """Handle surface is axis aligned rectangle."""
        if len(node_tags) != 4:
            return False
        projected = [
            self._surface_point_on_plane(
                (
                    float(self.project.nodes[tag].x),
                    float(self.project.nodes[tag].y),
                    float(self.project.nodes[tag].z),
                ),
                plane,
            )
            for tag in node_tags
        ]
        u_values = [point[0] for point in projected]
        v_values = [point[1] for point in projected]
        return (
            len(self._surface_distinct_coordinates(u_values)) == 2
            and len(self._surface_distinct_coordinates(v_values)) == 2
        )

    def _finalize_surface_drawing(self) -> bool:
        """Finalize surface drawing."""
        if self._draw_mode_kind != "surface":
            return False
        if not self._surface_features_enabled():
            self._reset_surface_draw_points()
            return False

        section_tag = self._draw_surface_section_tag
        sec = self.project.sections.get(section_tag)
        if sec is None or not sec.is_surface:
            QMessageBox.warning(
                self,
                "Section plaque requise",
                "Choisissez d'abord une section plaque valide avant de dessiner.",
            )
            if getattr(self, "act_draw_surface", None) is not None:
                self.act_draw_surface.setChecked(False)
            return False

        if not self._supports_rectangular_surface_drawing(sec):
            if getattr(self, "act_draw_surface", None) is not None:
                self.act_draw_surface.setChecked(False)
            return False

        pending_points = list(self._draw_surface_points)
        if len(pending_points) < 3:
            self._log("Ajoutez au moins 3 points avant de créer la plaque.")
            return False

        expected_count = surface_expected_node_count(sec.surface_formulation)
        if expected_count == 4 and len(pending_points) == 3:
            plane = self._surface_plane_for_points(pending_points)
            closing_point = (
                self._surface_rectangle_closing_point(pending_points, plane)
                if plane is not None
                else None
            )
            if closing_point is None:
                self._log(
                    "Les 3 premiers points doivent définir un plan pour fermer "
                    "automatiquement la plaque."
                )
                return False
            pending_points.append(closing_point)
        if len(pending_points) < expected_count:
            self._log(
                f"La formulation {sec.surface_formulation} attend {expected_count} point(s) : "
                f"il en manque {expected_count - len(pending_points)}."
            )
            return False
        if len(pending_points) > expected_count:
            self._log(
                f"La formulation {sec.surface_formulation} ne prend actuellement en charge "
                f"que {expected_count} point(s)."
            )
            return False

        node_tags = [self._ensure_node_at_point(draw_point) for draw_point in pending_points]
        validation = self._validate_surface_definition(node_tags, section_tag)
        if validation is None:
            self._reset_surface_draw_points()
            return False

        ordered_node_tags, plane, existing_surface_tag = validation
        if existing_surface_tag is not None:
            QMessageBox.information(
                self,
                "Surface existante",
                f"Une surface S{existing_surface_tag} utilise déjà ces nœuds.",
            )
            self._reset_surface_draw_points()
            self._select_surface_after_change(existing_surface_tag)
            return False

        existing_plate_tag = self._find_plate_region_by_node_tags(ordered_node_tags)
        if existing_plate_tag is not None:
            QMessageBox.information(
                self,
                "Plaque existante",
                f"Une plaque P{existing_plate_tag} utilise deja ces noeuds.",
            )
            self._reset_surface_draw_points()
            return False

        plate = self._add_user_plate_region(ordered_node_tags, section_tag, plane)
        if plate is None:
            self._reset_surface_draw_points()
            return False
        self._mark_project_modified()
        self._reset_surface_draw_points()
        self._refresh(preserve_view=True)
        self._select_surface_after_change(plate.tag)
        return True

    def _on_surface_draw_finalize_requested(self) -> None:
        """Handle surface draw finalize requested."""
        if self._draw_mode_kind != "surface":
            return
        pending_count = len(getattr(self, "_draw_surface_points", []))
        if pending_count == 0:
            return
        if pending_count < 3:
            self._reset_surface_draw_points()
            self._log(
                "Dessin de plaque en cours annule. Choisissez un nouveau premier point."
            )
            return
        self._finalize_surface_drawing()

    def _on_draw_finalize_requested(self) -> None:
        """Handle right-click finalization in the active drawing mode."""
        if self._draw_mode_kind == "surface":
            self._on_surface_draw_finalize_requested()
            return
        if self._draw_mode_kind == "bar" and self._draw_start_point is not None:
            self._reset_bar_draw_origin()
            self._log(
                "Point de depart de barre annule. Choisissez un nouveau depart."
            )

    def _on_grid_point_picked_from_view(
        self,
        view_name: str,
        x: float,
        y: float,
        z: float,
    ) -> None:
        """Handle grid point picked from view."""
        if view_name == "secondary":
            plane = self._secondary_parallel_plane
        else:
            plane = self._active_parallel_plane
        self._pick_plane_override = None if plane == "3D" else plane
        try:
            self._on_grid_point_picked(x, y, z)
        finally:
            self._pick_plane_override = None

    def _on_grid_point_picked(self, x: float, y: float, z: float) -> None:
        """Handle grid point picked."""
        if self.model_view is None:
            return
        if self._draw_mode_kind not in {"node", "bar", "surface"}:
            return

        point = (float(x), float(y), float(z))
        if self._draw_mode_kind == "node":
            existing_tag = self._find_node_at_point(point)
            if existing_tag is not None:
                self.properties.show_node(existing_tag)
                self.model_view.highlight_node(existing_tag)
                if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "highlight_node"):
                    self.secondary_view.highlight_node(existing_tag)
                self._log(f"Le nœud N{existing_tag} existe déjà sur cette intersection.")
                return

            node = self.project.add_node(x=point[0], y=point[1], z=point[2])
            self._mark_project_modified()
            self._refresh(preserve_view=True)
            self.properties.show_node(node.tag)
            if self.model_view is not None:
                self.model_view.highlight_node(node.tag)
            if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "highlight_node"):
                self.secondary_view.highlight_node(node.tag)
            self._log(
                f"Nœud N{node.tag} créé à ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})."
            )
            return
        if self._draw_mode_kind == "surface":
            self._handle_surface_draw_point(point)
            return

        point = self._constrain_draw_point(point)
        if self._draw_start_point is None:
            self._draw_start_point = point
            self.model_view.set_preview_start(point)
            if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_preview_start"):
                self.secondary_view.set_preview_start(point)
            self._refresh_model_management_menus()
            self._log(
                f"Départ barre sélectionné : ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})"
            )
            return

        if self._points_equal(self._draw_start_point, point):
            self._log("Point identique au départ : choisissez une autre intersection.")
            return

        section_tag = self._default_draw_section_tag()
        if section_tag is None:
            QMessageBox.warning(
                self,
                "Section requise",
                "Aucune section disponible pour créer une barre.",
            )
            self.act_draw_bars.setChecked(False)
            return

        node_i = self._ensure_node_at_point(self._draw_start_point)
        node_j = self._ensure_node_at_point(point)
        if node_i == node_j:
            return

        if self._find_element_between_nodes(node_i, node_j) is not None:
            self._log("Une barre existe déjà entre ces deux nœuds.")
            self._reset_bar_draw_origin()
            return

        try:
            elem = self.project.add_element(node_i, node_j, section_tag=section_tag)
        except ValueError as exc:
            QMessageBox.warning(self, "Barre invalide", str(exc))
            self._reset_bar_draw_origin()
            return
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        if self.model_view is not None:
            self.model_view.highlight_element(elem.tag)
        if getattr(self, "secondary_view", None) is not None:
            if hasattr(self.secondary_view, "highlight_element"):
                self.secondary_view.highlight_element(elem.tag)
        self._reset_bar_draw_origin()
        self.properties.show_element(elem.tag)
        self._log(
            f"Barre E{elem.tag} créée entre N{node_i} et N{node_j} avec la section T{section_tag}. "
            "Choisissez maintenant librement le premier point de la barre suivante."
        )

    def _constrain_draw_point(
        self,
        point: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        """Handle constrain draw point."""
        if self._draw_start_point is None:
            return point
        if not getattr(self, "act_draw_orthogonal", None):
            return point
        if not self.act_draw_orthogonal.isChecked():
            return point

        start = self._draw_start_point
        x, y, z = point
        sx, sy, sz = start

        active_plane = (
            getattr(self, "_pick_plane_override", None)
            or getattr(self, "_active_parallel_plane", "3D")
        )

        if active_plane == "XY":
            if abs(x - sx) >= abs(y - sy):
                return (x, sy, z)
            return (sx, y, z)
        if active_plane == "XZ":
            if abs(x - sx) >= abs(z - sz):
                return (x, y, sz)
            return (sx, y, z)
        if active_plane == "YZ":
            if abs(y - sy) >= abs(z - sz):
                return (x, y, sz)
            return (x, sy, z)
        return point

    def _default_draw_section_tag(self) -> int | None:
        """Return the default draw section tag."""
        line_sections = self._line_section_items()
        if not line_sections:
            return None
        if hasattr(self, "combo_draw_section") and self.combo_draw_section.count():
            tag = self.combo_draw_section.currentData()
            if tag in self.project.sections:
                return tag
        return line_sections[0][0]

    def _ensure_node_at_point(self, point: tuple[float, float, float]) -> int:
        """Ensure node at point."""
        for tag, node in self.project.nodes.items():
            if self._points_equal((node.x, node.y, node.z), point):
                return tag

        node = self.project.add_node(x=point[0], y=point[1], z=point[2])
        return node.tag

    def _find_node_at_point(self, point: tuple[float, float, float]) -> int | None:
        """Find node at point."""
        for tag, node in self.project.nodes.items():
            if self._points_equal((node.x, node.y, node.z), point):
                return tag
        return None

    def _find_other_node_at_point(
        self,
        point: tuple[float, float, float],
        *,
        exclude_tag: int | None = None,
    ) -> int | None:
        """Find other node at point."""
        for tag, node in self.project.nodes.items():
            if exclude_tag is not None and tag == exclude_tag:
                continue
            if self._points_equal((node.x, node.y, node.z), point):
                return tag
        return None

    def _find_element_between_nodes(self, node_i: int, node_j: int) -> int | None:
        """Find element between nodes."""
        for tag, elem in self.project.elements.items():
            pair = {elem.node_i, elem.node_j}
            if pair == {node_i, node_j}:
                return tag
        return None

    @staticmethod
    def _points_equal(
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        tol: float = 1e-9,
    ) -> bool:
        """Handle points equal."""
        return (
            abs(p1[0] - p2[0]) <= tol
            and abs(p1[1] - p2[1]) <= tol
            and abs(p1[2] - p2[2]) <= tol
        )

    def _line_section_items(self):
        """Handle line section items."""
        return [
            (tag, sec)
            for tag, sec in sorted(self.project.sections.items())
            if not getattr(sec, "is_surface", False)
        ]

    def _surface_section_items(self):
        """Handle surface section items."""
        return [
            (tag, sec)
            for tag, sec in sorted(self.project.sections.items())
            if getattr(sec, "is_surface", False)
        ]

    def _choose_material_tag(self, title: str, prompt: str) -> int | None:
        """Choose material tag."""
        if not self.project.materials:
            QMessageBox.information(self, title, "Aucun matériau disponible.")
            return None

        tags = sorted(self.project.materials.keys())
        items = [
            f"{self.project.materials[tag].name} ({self.project.materials[tag].grade}) [T{tag}]"
            for tag in tags
        ]
        choice, ok = QInputDialog.getItem(self, title, prompt, items, 0, False)
        if not ok:
            return None
        return tags[items.index(choice)]

    def _choose_section_tag(
        self,
        title: str,
        prompt: str,
        *,
        include_surface: bool = True,
    ) -> int | None:
        """Choose section tag."""
        section_items = (
            sorted(self.project.sections.items())
            if include_surface
            else self._line_section_items()
        )
        if not section_items:
            message = (
                "Aucune section disponible."
                if include_surface
                else "Aucune section de barre disponible."
            )
            QMessageBox.information(self, title, message)
            return None

        tags = [tag for tag, _sec in section_items]
        items = [f"{self.project.sections[tag].name} [T{tag}]" for tag in tags]
        choice, ok = QInputDialog.getItem(self, title, prompt, items, 0, False)
        if not ok:
            return None
        return tags[items.index(choice)]

    def _choose_surface_section_tag(self) -> int | None:
        """Choose surface section tag."""
        section_items = self._surface_section_items()
        if not section_items:
            QMessageBox.information(
                self,
                "Section plaque requise",
                "Créez d'abord une section plaque.",
            )
            return None
        if len(section_items) == 1:
            return section_items[0][0]

        tags = [tag for tag, _sec in section_items]
        items = [
            (
                f"{self.project.sections[tag].name} [T{tag}] — "
                f"{self.project.sections[tag].surface_formulation}"
            )
            for tag in tags
        ]
        choice, ok = QInputDialog.getItem(
            self,
            "Section plaque",
            "Choisissez la section plaque à affecter :",
            items,
            0,
            False,
        )
        if not ok:
            return None
        return tags[items.index(choice)]

    def _surface_plane_for_node_tags(
        self,
        node_tags: list[int] | tuple[int, ...],
        tol: float = 1e-9,
    ) -> str | None:
        """Handle surface plane for node tags."""
        nodes = [self.project.nodes.get(tag) for tag in node_tags]
        if any(node is None for node in nodes):
            return None
        points = [
            (float(node.x), float(node.y), float(node.z))
            for node in nodes
            if node is not None
        ]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        zs = [point[2] for point in points]
        if max(zs) - min(zs) <= tol:
            return "XY"
        if max(ys) - min(ys) <= tol:
            return "XZ"
        if max(xs) - min(xs) <= tol:
            return "YZ"
        if self._surface_normal_for_points(points, tol=tol) is not None:
            return "3D"
        return None

    def _order_surface_node_tags(
        self,
        node_tags: list[int] | tuple[int, ...],
        plane: str,
    ) -> list[int]:
        """Handle order surface node tags."""
        points_3d = {
            int(tag): (
                float(self.project.nodes[int(tag)].x),
                float(self.project.nodes[int(tag)].y),
                float(self.project.nodes[int(tag)].z),
            )
            for tag in node_tags
        }
        basis = (
            self._surface_projection_basis(list(points_3d.values()))
            if plane == "3D"
            else None
        )

        def project(node_tag: int) -> tuple[float, float]:
            node = self.project.nodes[int(node_tag)]
            if plane == "XY":
                return float(node.x), float(node.y)
            if plane == "XZ":
                return float(node.x), float(node.z)
            if plane == "YZ":
                return float(node.y), float(node.z)
            if basis is None:
                return 0.0, 0.0
            origin, u_axis, v_axis = basis
            return self._surface_project_on_basis(
                points_3d[int(node_tag)],
                origin,
                u_axis,
                v_axis,
            )

        projected = {tag: project(tag) for tag in node_tags}
        center_u = sum(point[0] for point in projected.values()) / len(projected)
        center_v = sum(point[1] for point in projected.values()) / len(projected)
        return sorted(
            [int(tag) for tag in node_tags],
            key=lambda tag: math.atan2(
                projected[tag][1] - center_v,
                projected[tag][0] - center_u,
            ),
        )

    def _surface_area_on_plane(
        self,
        node_tags: list[int] | tuple[int, ...],
        plane: str,
    ) -> float:
        """Handle surface area on plane."""
        ordered_tags = self._order_surface_node_tags(node_tags, plane)
        points_3d = [
            (
                float(self.project.nodes[tag].x),
                float(self.project.nodes[tag].y),
                float(self.project.nodes[tag].z),
            )
            for tag in ordered_tags
        ]
        if plane == "3D":
            basis = self._surface_projection_basis(points_3d)
            if basis is None:
                return 0.0
            origin, u_axis, v_axis = basis
            points = [
                self._surface_project_on_basis(point, origin, u_axis, v_axis)
                for point in points_3d
            ]
        else:
            points = []
            for point in points_3d:
                if plane == "XY":
                    points.append((point[0], point[1]))
                elif plane == "XZ":
                    points.append((point[0], point[2]))
                else:
                    points.append((point[1], point[2]))

        area = 0.0
        for idx, point in enumerate(points):
            next_point = points[(idx + 1) % len(points)]
            area += point[0] * next_point[1] - next_point[0] * point[1]
        return abs(area) * 0.5

    def _find_surface_by_node_tags(
        self,
        node_tags: list[int] | tuple[int, ...],
        exclude_surface_tag: int | None = None,
    ) -> int | None:
        """Find surface by node tags."""
        target = tuple(sorted(int(tag) for tag in node_tags))
        for tag, surface in self.project.surface_elements.items():
            if exclude_surface_tag is not None and int(tag) == int(exclude_surface_tag):
                continue
            if tuple(sorted(surface.node_tags)) == target:
                return tag
        return None

    def _find_plate_region_by_node_tags(
        self,
        node_tags: list[int] | tuple[int, ...],
    ) -> int | None:
        """Find plate region by node tags."""
        target = tuple(sorted(int(tag) for tag in node_tags))
        for tag, plate in self.project.plate_regions.items():
            if tuple(sorted(int(node_tag) for node_tag in plate.corner_node_tags)) == target:
                return int(tag)
        return None

    def _add_user_plate_region(
        self,
        node_tags: list[int] | tuple[int, ...],
        section_tag: int,
        plane: str,
    ):
        """Add user plate region."""
        sec = self.project.sections.get(int(section_tag))
        if sec is None or not getattr(sec, "is_surface", False):
            QMessageBox.warning(
                self,
                "Section plaque requise",
                "La plaque doit utiliser une section plaque/surface, pas une section de barre. "
                "Creez ou choisissez une section plaque avant de continuer.",
            )
            return None

        formulation = sec.surface_formulation
        plate_tag = self.project.next_plate_region_tag()
        try:
            plate = self.project.add_plate_region(
                corner_node_tags=tuple(int(tag) for tag in node_tags),
                section_tag=int(section_tag),
                name=f"Plaque P{plate_tag}",
                mesh_nx=8,
                mesh_ny=8,
                mesh_mode="auto",
                formulation=formulation,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Plaque invalide", str(exc))
            return None
        self._log(
            f"Plaque P{plate.tag} creee sur {plane} avec "
            f"{len(plate.corner_node_tags)} noeud(s), section T{section_tag}, "
            "maillage automatique."
        )
        self._log_plate_intersection_diagnostic(plate)
        return plate

    def _log_plate_intersection_diagnostic(self, plate) -> None:
        """Log non-blocking plate intersection diagnostics."""
        try:
            report = detect_plate_intersections(self.project, plate)
        except ValueError as exc:
            self._log(f"Diagnostic plaque P{plate.tag} indisponible : {exc}")
            return

        message = (
            f"Plaque P{plate.tag} : {len(report.node_hits)} noeud(s) existant(s) "
            f"detecte(s), {len(report.bar_hits)} barre(s) intersectee(s)."
        )
        self._log(message)
        try:
            status_bar = self.statusBar()
        except RuntimeError:
            status_bar = None
        if status_bar is not None:
            status_bar.showMessage(message, 5000)
        for warning in report.warnings:
            self._log(f"Diagnostic plaque P{plate.tag} : {warning}")

    def _log_analysis_mesh_diagnostic(self) -> None:
        """Log analysis-only mesh enrichment diagnostics."""
        contexts = [
            results.get("result_context", {})
            for results in (getattr(self, "_all_results", {}) or {}).values()
            if isinstance(results, dict)
        ]
        if not contexts:
            return

        def _safe_int(value) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        generated_bar_count = max(
            _safe_int(context.get("generated_bar_count"))
            for context in contexts
        )
        generated_bar_segment_count = max(
            _safe_int(context.get("generated_bar_segment_count"))
            for context in contexts
        )
        if generated_bar_count <= 0:
            return

        self._log(
            "Maillage d'analyse : "
            f"{generated_bar_count} barre(s) coplanaire(s) integree(s) "
            f"en {generated_bar_segment_count} segment(s) interne(s)."
        )

    def _validate_surface_definition(
        self,
        node_tags: list[int] | tuple[int, ...],
        section_tag: int,
        *,
        exclude_surface_tag: int | None = None,
    ) -> tuple[list[int], str, int | None] | None:
        """Validate surface definition."""
        sec = self.project.sections.get(section_tag)
        if sec is None or not sec.is_surface:
            QMessageBox.warning(
                self,
                "Section plaque requise",
                "Choisissez une section plaque valide avant de créer ou modifier la surface.",
            )
            return None

        normalized_node_tags = [int(tag) for tag in node_tags if int(tag) in self.project.nodes]
        expected_count = surface_expected_node_count(sec.surface_formulation)
        if len(normalized_node_tags) != expected_count:
            QMessageBox.warning(
                self,
                "Formulation incompatible",
                f"La section {sec.surface_formulation} attend {expected_count} nœud(s).",
            )
            return None

        if len(set(normalized_node_tags)) != len(normalized_node_tags):
            QMessageBox.warning(
                self,
                "Surface invalide",
                "Chaque nœud d'une plaque doit être unique.",
            )
            return None

        plane = self._surface_plane_for_node_tags(normalized_node_tags)
        if plane is None:
            QMessageBox.warning(
                self,
                "Plan invalide",
                "Les nœuds choisis doivent rester dans un même plan.",
            )
            return None

        ordered_node_tags = self._order_surface_node_tags(normalized_node_tags, plane)
        area = self._surface_area_on_plane(ordered_node_tags, plane)
        if area <= 1e-9:
            QMessageBox.warning(
                self,
                "Surface invalide",
                "Les nœuds choisis sont alignes ou ne définissent pas une plaque valide.",
            )
            return None

        existing_surface_tag = self._find_surface_by_node_tags(
            ordered_node_tags,
            exclude_surface_tag=exclude_surface_tag,
        )
        return ordered_node_tags, plane, existing_surface_tag

    def _surface_section_compatibility_issues(
        self,
        sections: dict[int, object] | None = None,
    ) -> list[tuple[int, str]]:
        """Handle surface section compatibility issues."""
        active_sections = sections or self.project.sections
        issues: list[tuple[int, str]] = []
        for surface in sorted(self.project.surface_elements.values(), key=lambda value: value.tag):
            sec = active_sections.get(surface.section_tag)
            if sec is None:
                issues.append(
                    (
                        surface.tag,
                        f"S{surface.tag} reference une section absente T{surface.section_tag}.",
                    )
                )
                continue
            if not getattr(sec, "is_surface", False):
                issues.append(
                    (
                        surface.tag,
                        f"S{surface.tag} reference la section T{surface.section_tag}, qui n'est plus une section plaque.",
                    )
                )
                continue
            expected_count = surface_expected_node_count(sec.surface_formulation)
            actual_count = len(surface.node_tags)
            if actual_count != expected_count:
                issues.append(
                    (
                        surface.tag,
                        f"S{surface.tag} a {actual_count} nœud(s), mais {sec.surface_formulation} attend {expected_count} nœud(s).",
                    )
                )
        for plate in sorted(self.project.plate_regions.values(), key=lambda value: value.tag):
            sec = active_sections.get(plate.section_tag)
            if sec is None:
                issues.append(
                    (
                        plate.tag,
                        f"P{plate.tag} reference une section absente T{plate.section_tag}.",
                    )
                )
                continue
            if not getattr(sec, "is_surface", False):
                issues.append(
                    (
                        plate.tag,
                        f"P{plate.tag} reference la section T{plate.section_tag}, qui n'est pas une section plaque.",
                    )
                )
                continue
            expected_count = surface_expected_node_count(sec.surface_formulation)
            actual_count = len(plate.corner_node_tags)
            if actual_count != expected_count:
                issues.append(
                    (
                        plate.tag,
                        f"P{plate.tag} a {actual_count} noeud(s), mais {sec.surface_formulation} attend {expected_count} noeud(s).",
                    )
                )
        return issues

    def _element_section_compatibility_issues(
        self,
        sections: dict[int, object] | None = None,
    ) -> list[tuple[int, str]]:
        """Handle element section compatibility issues."""
        active_sections = sections or self.project.sections
        issues: list[tuple[int, str]] = []
        for elem in sorted(self.project.elements.values(), key=lambda value: value.tag):
            sec = active_sections.get(elem.section_tag)
            if sec is None:
                issues.append(
                    (
                        elem.tag,
                        f"E{elem.tag} reference une section absente T{elem.section_tag}.",
                    )
                )
                continue
            if getattr(sec, "is_surface", False):
                issues.append(
                    (
                        elem.tag,
                        f"E{elem.tag} reference la section plaque T{elem.section_tag}; une barre doit utiliser une section barre.",
                    )
                )
                continue
            if float(getattr(sec, "area", 0.0) or 0.0) <= 0.0:
                issues.append(
                    (
                        elem.tag,
                        f"E{elem.tag} utilise T{elem.section_tag}, dont l'aire de section est nulle.",
                    )
                )
                continue
            if str(getattr(elem, "element_type", "beam")) != "truss" and float(getattr(sec, "inertia_y", 0.0) or 0.0) <= 0.0:
                issues.append(
                    (
                        elem.tag,
                        f"E{elem.tag} utilise T{elem.section_tag}, dont l'inertie Iy est nulle.",
                    )
                )
        return issues

    def _surface_plane_for_points(
        self,
        points: list[tuple[float, float, float]],
        tol: float = 1e-9,
    ) -> str | None:
        """Handle surface plane for points."""
        if len(points) < 3:
            return None
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        zs = [float(point[2]) for point in points]
        if max(zs) - min(zs) <= tol:
            return "XY"
        if max(ys) - min(ys) <= tol:
            return "XZ"
        if max(xs) - min(xs) <= tol:
            return "YZ"
        if self._surface_normal_for_points(points, tol=tol) is not None:
            return "3D"
        return None

    def _handle_surface_draw_point(
        self,
        point: tuple[float, float, float],
    ) -> None:
        """Handle surface draw point."""
        if not self._surface_features_enabled():
            self._reset_surface_draw_points()
            return
        section_tag = self._draw_surface_section_tag
        sec = self.project.sections.get(section_tag)
        if sec is None or not sec.is_surface:
            QMessageBox.warning(
                self,
                "Section plaque requise",
                "Choisissez d'abord une section plaque valide avant de dessiner.",
            )
            if getattr(self, "act_draw_surface", None) is not None:
                self.act_draw_surface.setChecked(False)
            return

        if not self._supports_rectangular_surface_drawing(sec):
            if getattr(self, "act_draw_surface", None) is not None:
                self.act_draw_surface.setChecked(False)
            return

        point = self._constrain_draw_point(point)
        if any(self._points_equal(existing, point) for existing in self._draw_surface_points):
            self._log("Point déjà sélectionné pour la plaque en cours : choisissez une autre intersection.")
            return

        expected_count = surface_expected_node_count(sec.surface_formulation)
        pending_points = [*self._draw_surface_points, point]
        plane = self._surface_plane_for_points(pending_points) if len(pending_points) >= 3 else None
        if len(pending_points) >= 3 and plane is None:
            self._log("Les points de la plaque doivent rester dans un même plan.")
            return

        self._draw_surface_points = pending_points
        self._draw_start_point = point
        if self.model_view is not None:
            self.model_view.set_preview_start(point)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_preview_start"):
            self.secondary_view.set_preview_start(point)

        if len(pending_points) < expected_count:
            self._refresh_model_management_menus()
            if len(pending_points) == 3 and expected_count == 4:
                self._log(
                    "3 coins de plaque enregistres : faites un 4e clic ou un clic droit "
                    "pour fermer automatiquement en parallelogramme."
                )
                return
            self._log(
                f"Point plaque {len(pending_points)}/{expected_count} enregistré : "
                f"({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})."
            )
            return
        self._finalize_surface_drawing()

    def _on_tree_node_selected(self, tag: int) -> None:
        """Handle tree node selected."""
        self._selected_node_tags = [tag]
        self._selected_element_tags = []
        self._selected_surface_tags = []
        self.properties.show_node(tag)
        if self.model_view is not None:
            self.model_view.set_selected_objects([tag], [], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "highlight_node"):
            self.secondary_view.set_selected_objects([tag], [], [], emit_signal=False)
        self._refresh_model_management_menus()

    def _on_tree_element_selected(self, tag: int) -> None:
        """Handle tree element selected."""
        self._selected_node_tags = []
        self._selected_element_tags = [tag]
        self._selected_surface_tags = []
        self.properties.show_element(tag)
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [tag], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "highlight_element"):
            self.secondary_view.set_selected_objects([], [tag], [], emit_signal=False)
        self._refresh_model_management_menus()

    def _on_tree_surface_selected(self, tag: int) -> None:
        """Handle tree surface selected."""
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = [tag]
        self.properties.show_surface(tag)
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [tag], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [tag], emit_signal=False)
        self._refresh_model_management_menus()

    def _on_view_node_picked(self, tag: int) -> None:
        """Handle view node picked."""
        self.tree.select_node(tag)
        self.properties.show_node(tag)

    def _on_view_element_picked(self, tag: int) -> None:
        """Handle view element picked."""
        self.tree.select_element(tag)
        self.properties.show_element(tag)

    def _select_element_for_context(self, tag: int) -> bool:
        """Handle select element for context."""
        if tag not in self.project.elements:
            return False
        panel_already_current = (
            getattr(self.properties, "_current_kind", "") == "element"
            and getattr(self.properties, "_current_tag", -1) == tag
        )
        self._selected_node_tags = []
        self._selected_element_tags = [tag]
        self._selected_surface_tags = []
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [tag], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [tag], [], emit_signal=False)
        self.tree.select_element(tag)
        if not panel_already_current:
            self.properties.show_element(tag)
        self._refresh_model_management_menus()
        return True

    def _select_surface_for_context(self, tag: int) -> bool:
        """Handle select surface for context."""
        if tag not in self.project.surface_elements and tag not in self.project.plate_regions:
            return False
        panel_already_current = (
            getattr(self.properties, "_current_kind", "") == "surface"
            and getattr(self.properties, "_current_tag", -1) == tag
        )
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = [tag]
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [tag], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [tag], emit_signal=False)
        self.tree.select_surface(tag)
        if not panel_already_current:
            self.properties.show_surface(tag)
        self._refresh_model_management_menus()
        return True

    def _show_element_context_menu(self, tag: int, global_pos: QPoint) -> None:
        """Show element context menu."""
        if not self._select_element_for_context(int(tag)):
            return

        menu = QMenu(self)
        act_edit = menu.addAction("Modifier")
        act_delete = menu.addAction("Supprimer")
        act_copy = menu.addAction("Copier")
        menu.addSeparator()
        act_diagrams = menu.addAction("Afficher diagrammes")
        has_results = self._element_diagram_available(tag)
        act_diagrams.setEnabled(has_results)
        if not has_results:
            act_diagrams.setToolTip("Lancez d'abord une analyse pour afficher les diagrammes.")
        menu.addSeparator()
        act_properties = menu.addAction("Propriétés")

        chosen = menu.exec(global_pos)
        if chosen is act_edit:
            self._edit_element(tag)
        elif chosen is act_delete:
            self._delete_selected_objects([], [tag], [])
        elif chosen is act_copy:
            self._copy_selected_objects()
        elif chosen is act_diagrams:
            self._show_element_diagram(tag)
        elif chosen is act_properties:
            self._show_element_properties(tag)

    def _show_surface_context_menu(self, tag: int, global_pos: QPoint) -> None:
        """Show surface context menu."""
        tag = int(tag)
        if not self._select_surface_for_context(tag):
            return

        menu = QMenu(self)
        act_edit = menu.addAction("Modifier")
        act_delete = menu.addAction("Supprimer")
        act_copy = menu.addAction("Copier")
        menu.addSeparator()
        act_diagrams = menu.addAction("Afficher diagrammes")
        has_results = self._surface_diagram_available(tag)
        act_diagrams.setEnabled(has_results)
        if not has_results:
            act_diagrams.setToolTip(
                "Lancez d'abord une analyse de plaques pour afficher les diagrammes."
            )
        is_plate_surface = (
            tag in getattr(self.project, "plate_regions", {})
            or tag in getattr(self.project, "surface_elements", {})
        )
        plate_actions: dict[str, QAction] = {}
        if is_plate_surface:
            menu.addSeparator()
            plate_actions = self._add_plate_context_menu(menu, tag)
        menu.addSeparator()
        act_properties = menu.addAction("Propriétés")

        chosen = menu.exec(global_pos)
        if chosen is act_edit:
            self._edit_surface(tag)
        elif chosen is act_delete:
            self._delete_selected_objects([], [], [tag])
        elif chosen is act_copy:
            self._copy_selected_objects()
        elif chosen is act_diagrams:
            self._show_surface_result_map(surface_tag=tag)
        elif chosen is not None and chosen is plate_actions.get("mesh_auto"):
            self._set_plate_mesh_auto(tag)
        elif chosen is not None and chosen is plate_actions.get("mesh_user"):
            self._set_plate_mesh_user_from_menu(tag)
        elif chosen is act_properties:
            self._show_surface_properties(tag)

    def _add_plate_context_menu(self, menu: QMenu, tag: int) -> dict[str, QAction]:
        """Add plate actions to a context menu."""
        is_macro_plate = int(tag) in self.project.plate_regions
        if is_macro_plate:
            plate = self.project.plate_regions[int(tag)]
            mesh_nx, mesh_ny = effective_plate_mesh_divisions(self.project, plate)
            mesh_mode = normalize_plate_mesh_mode(getattr(plate, "mesh_mode", None))
            menu_plate = menu.addMenu("Plaque macro")
        else:
            mesh_nx, mesh_ny = 1, 1
            mesh_mode = ""
            menu_plate = menu.addMenu("Plaque")

        act_mesh_auto = menu_plate.addAction("Maillage automatique")
        act_mesh_auto.setCheckable(True)
        act_mesh_auto.setChecked(mesh_mode == PLATE_MESH_MODE_AUTO)
        act_mesh_user = menu_plate.addAction("Nombre de mailles...")
        act_mesh_user.setCheckable(True)
        act_mesh_user.setChecked(mesh_mode == PLATE_MESH_MODE_USER)
        if not is_macro_plate:
            for action in (act_mesh_auto, act_mesh_user):
                action.setEnabled(False)
                action.setToolTip("Disponible uniquement pour une plaque macro.")
        menu_plate.addSeparator()
        act_mesh_info = menu_plate.addAction(f"Maillage retenu : {mesh_nx} x {mesh_ny}")
        act_mesh_info.setEnabled(False)
        menu_plate.addSeparator()

        disabled_actions = [
            menu_plate.addAction("Integrer une barre diagonale..."),
            menu_plate.addAction("Creer un noeud a l'intersection..."),
            menu_plate.addAction("Decouper une barre traversante..."),
            menu_plate.addAction("Maillage non structure..."),
        ]
        for action in disabled_actions:
            action.setEnabled(False)
            action.setToolTip("Fonction a venir.")

        return {
            "mesh_auto": act_mesh_auto,
            "mesh_user": act_mesh_user,
        }

    def _set_plate_mesh_auto(self, tag: int) -> None:
        """Set plate mesh auto."""
        tag = int(tag)
        plate = self.project.plate_regions.get(tag)
        if plate is None:
            return
        plate.mesh_mode = PLATE_MESH_MODE_AUTO
        mesh_nx, mesh_ny = effective_plate_mesh_divisions(self.project, plate)
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        properties = getattr(self, "properties", None)
        if properties is not None:
            properties.show_surface(tag)
        self._log(f"Plaque P{tag} : maillage automatique ({mesh_nx} x {mesh_ny}).")

    def _set_plate_mesh_user_from_menu(self, tag: int) -> None:
        """Set plate mesh user from menu."""
        tag = int(tag)
        plate = self.project.plate_regions.get(tag)
        if plate is None:
            return
        dlg = PlateMeshDialog(
            self,
            mesh_nx=int(plate.mesh_nx),
            mesh_ny=int(plate.mesh_ny),
            plate_tag=tag,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        nx, ny = dlg.values()
        plate.mesh_mode = PLATE_MESH_MODE_USER
        plate.mesh_nx = int(nx)
        plate.mesh_ny = int(ny)
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        properties = getattr(self, "properties", None)
        if properties is not None:
            properties.show_surface(tag)
        self._log(f"Plaque P{tag} : maillage utilisateur ({nx} x {ny}).")

    def _on_view_selection_changed(
        self,
        node_tags: list[int],
        element_tags: list[int],
        surface_tags: list[int],
    ) -> None:
        """Handle view selection changed."""
        self._selected_node_tags = list(node_tags)
        self._selected_element_tags = list(element_tags)
        self._selected_surface_tags = list(surface_tags)
        if self.model_view is not None:
            self.model_view.set_selected_objects(
                node_tags,
                element_tags,
                surface_tags,
                emit_signal=False,
            )
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects(
                node_tags,
                element_tags,
                surface_tags,
                emit_signal=False,
            )
        self._refresh_model_management_menus()

        if len(node_tags) == 1 and not element_tags and not surface_tags:
            self.tree.select_node(node_tags[0])
            self.properties.show_node(node_tags[0])
            self._refresh_model_management_menus()
            return
        if len(element_tags) == 1 and not node_tags and not surface_tags:
            self.tree.select_element(element_tags[0])
            self.properties.show_element(element_tags[0])
            self._refresh_model_management_menus()
            return
        if len(surface_tags) == 1 and not node_tags and not element_tags:
            self.tree.select_surface(surface_tags[0])
            self.properties.show_surface(surface_tags[0])
            self._refresh_model_management_menus()
            return
        if not node_tags and not element_tags and not surface_tags:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
            self.tree.blockSignals(False)
            self.properties.clear_display()
            self._log("Sélection vide.")
            return

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.properties.clear_display()
        self._log(
            f"Sélection multiple : {len(node_tags)} nœud(s), {len(element_tags)} élément(s)."
        )

    def _on_view_delete_selection_requested(
        self,
        node_tags: list[int],
        element_tags: list[int],
        surface_tags: list[int],
    ) -> None:
        """Handle view delete selection requested."""
        self._delete_selected_objects(node_tags, element_tags, surface_tags)

    def _delete_selected_objects(
        self,
        node_tags: list[int] | set[int] | tuple[int, ...],
        element_tags: list[int] | set[int] | tuple[int, ...],
        surface_tags: list[int] | set[int] | tuple[int, ...] | None = None,
    ) -> None:
        """Delete selected objects."""
        selected_nodes = {
            int(tag) for tag in node_tags
            if int(tag) in self.project.nodes
        }
        selected_elements = {
            int(tag) for tag in element_tags
            if int(tag) in self.project.elements
        }
        selected_surfaces = {
            int(tag) for tag in (surface_tags or [])
            if (
                int(tag) in self.project.surface_elements
                or int(tag) in self.project.plate_regions
            )
        }

        if not selected_nodes and not selected_elements and not selected_surfaces:
            return

        connected_elements = {
            tag for tag, elem in self.project.elements.items()
            if elem.node_i in selected_nodes or elem.node_j in selected_nodes
        }
        connected_surfaces = {
            tag
            for tag, surface in self.project.surface_elements.items()
            if any(node_tag in selected_nodes for node_tag in surface.node_tags)
        }
        connected_surfaces.update(
            tag
            for tag, plate in self.project.plate_regions.items()
            if any(node_tag in selected_nodes for node_tag in plate.corner_node_tags)
        )
        all_elements = selected_elements | connected_elements
        all_surfaces = selected_surfaces | connected_surfaces
        auto_deleted = all_elements - selected_elements

        msg = (
            "Supprimer la sélection courante ?\n\n"
            f"- Nœuds : {len(selected_nodes)}\n"
            f"- Éléments : {len(all_elements)}\n"
            f"- Surfaces : {len(all_surfaces)}"
        )
        if auto_deleted:
            msg += (
                f"\n\n{len(auto_deleted)} élément(s) connecté(s) "
                "aux nœuds sélectionnés seront aussi supprimé(s)."
            )
        if connected_surfaces:
            msg += (
                f"\n\n{len(connected_surfaces)} surface(s) connectée(s) "
                "aux nœuds sélectionnés seront aussi supprimée(s)."
            )

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for tag in sorted(all_elements):
            self.project.elements.pop(tag, None)
        self._delete_surface_elements_by_tags(sorted(all_surfaces))
        for tag in sorted(selected_nodes):
            self.project.nodes.pop(tag, None)

        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [], emit_signal=False)
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = []

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.properties.clear_display()

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        log_message = (
            f"Suppression effectuée : {len(selected_nodes)} nœud(s), "
            f"{len(all_elements)} Élément(s), "
            f"{len(all_surfaces)} surface(s)"
        )
        self._log(f"{log_message}.")

    def _invalidate_results_after_model_change(self) -> None:
        """Handle invalidate results after model change."""
        had_results = bool(getattr(self, "_all_results", {}))
        if not had_results:
            return
        self._clear_results_state()
        self._log(
            "Résultats effacés : le modèle a été modifié. "
            "Relancez l'analyse pour obtenir des résultats à jour."
        )

    def _on_model_changed(self) -> None:
        """Handle model changed."""
        self._mark_project_modified()
        self._refresh(preserve_view=True)

    # ── Barre de statut ─────────────────────────────────────────────────

    def _update_statusbar(self) -> None:
        """Update statusbar."""
        s = self.project.stats
        requested = self._normalize_solver_engine(self.settings.analysis.solver_engine)
        resolved = self._solver_manager.resolve_engine(requested)
        solver_part = f"Moteur : {self._solver_label(resolved)}"
        if requested != resolved:
            solver_part += f" (repli depuis {self._solver_label(requested)})"
        self.statusbar.showMessage(
            f"Nœuds : {s['nodes']}  |  "
            f"Éléments : {s['elements']}  |  "
            f"Surfaces : {s['surface_elements']}  |  "
            f"Matériaux : {s['materials']}  |  "
            f"Sections : {s['sections']}  |  "
            f"Charges : {s['loads']}  |  "
            f"Combinaisons : {s['combinations']}  |  "
            f"{solver_part}"
        )

    # -- Add actions ----------------------------------------------------------

    def _on_add_requested(self, obj_type: str) -> None:
        """Handle add requested."""
        if obj_type == "node":
            self._add_node()
        elif obj_type == "material":
            self._add_material()
        elif obj_type == "section":
            self._add_section()
        elif obj_type == "element":
            self._add_element()
        elif obj_type == "surface":
            self._add_surface()
        elif obj_type == "load":
            self._manage_load_cases()
        elif obj_type == "combination":
            self._manage_combinations()

    def _add_node(self) -> None:
        """Add node."""
        from gui.dialogs.node_dlg import NodeDialog

        dlg = NodeDialog(
            self,
            node_tag=self.project.next_node_tag(),
            allow_tag_edit=True,
            forbidden_tags=set(self.project.nodes),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.result()
        duplicate_tag = self._find_other_node_at_point(
            (float(data["x"]), float(data["y"]), float(data["z"]))
        )
        if duplicate_tag is not None:
            QMessageBox.warning(
                self,
                "Coordonnées déjà utilisées",
                (
                    f"Un nœud N{duplicate_tag} existe déjà en "
                    f"({float(data['x']):.3f}, {float(data['y']):.3f}, {float(data['z']):.3f})."
                ),
            )
            self._select_node_after_change(duplicate_tag)
            return
        try:
            node = self._insert_node_with_tag(
                tag=int(data["tag"]),
                x=float(data["x"]),
                y=float(data["y"]),
                z=float(data["z"]),
            )
        except ValueError:
            QMessageBox.warning(
                self,
                "Nœud existant",
                f"Le numéro N{int(data['tag'])} existe déjà. Choisissez un autre numéro.",
            )
            return

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._select_node_after_change(node.tag)
        self._log(
            f"Nœud N{node.tag} ajouté en "
            f"({node.x:.3f}, {node.y:.3f}, {node.z:.3f})."
        )

    def _insert_node_with_tag(
        self,
        *,
        tag: int,
        x: float,
        y: float,
        z: float,
        fixities: tuple[int, ...] = (0, 0, 0, 0, 0, 0),
        boundary_data: dict | None = None,
    ) -> NodeData:
        """Handle insert node with tag."""
        if tag in self.project.nodes:
            raise ValueError(f"Le nœud N{tag} existe déjà.")
        node = NodeData(
            tag=tag,
            x=x,
            y=y,
            z=z,
            fixities=tuple(fixities[:6]),
            boundary_data=deepcopy(boundary_data or {}),
        )
        self.project.nodes[tag] = node
        return node

    def _connected_element_tags_for_node(self, node_tag: int) -> list[int]:
        """Handle connected element tags for node."""
        return sorted(
            tag
            for tag, elem in self.project.elements.items()
            if elem.node_i == node_tag or elem.node_j == node_tag
        )

    def _connected_surface_tags_for_node(self, node_tag: int) -> list[int]:
        """Handle connected surface tags for node."""
        return sorted(
            set(
                tag
                for tag, surface in self.project.surface_elements.items()
                if node_tag in surface.node_tags
            )
            | set(
                tag
                for tag, plate in self.project.plate_regions.items()
                if node_tag in plate.corner_node_tags
            )
        )

    def _delete_elements_by_tags(self, element_tags: list[int]) -> None:
        """Delete elements by tags."""
        if not element_tags:
            return
        element_tag_set = set(element_tags)
        for tag in sorted(element_tag_set):
            self.project.elements.pop(tag, None)
        self.project.element_loads = [
            load
            for load in self.project.element_loads
            if load.element_tag not in element_tag_set
        ]

    def _delete_surface_elements_by_tags(self, surface_tags: list[int]) -> None:
        """Delete surface elements by tags."""
        if not surface_tags:
            return
        surface_tag_set = set(surface_tags)
        for tag in sorted(surface_tag_set):
            self.project.surface_elements.pop(tag, None)
            self.project.plate_regions.pop(tag, None)
        self.project.surface_loads = [
            load
            for load in self.project.surface_loads
            if load.surface_tag not in surface_tag_set
        ]
        self.project.plate_surface_loads = [
            load
            for load in self.project.plate_surface_loads
            if load.plate_tag not in surface_tag_set
        ]
        self.project.plate_edge_supports = [
            support
            for support in self.project.plate_edge_supports
            if support.plate_tag not in surface_tag_set
        ]

    def _select_objects_after_change(
        self,
        node_tags: list[int] | tuple[int, ...],
        element_tags: list[int] | tuple[int, ...],
        surface_tags: list[int] | tuple[int, ...] | None = None,
    ) -> None:
        """Handle select objects after change."""
        self._selected_node_tags = list(node_tags)
        self._selected_element_tags = list(element_tags)
        self._selected_surface_tags = list(surface_tags or [])
        if self.model_view is not None:
            self.model_view.set_selected_objects(
                self._selected_node_tags,
                self._selected_element_tags,
                self._selected_surface_tags,
                emit_signal=False,
            )
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects(
                self._selected_node_tags,
                self._selected_element_tags,
                self._selected_surface_tags,
                emit_signal=False,
            )

        if len(self._selected_node_tags) == 1 and not self._selected_element_tags and not self._selected_surface_tags:
            self.tree.select_node(self._selected_node_tags[0])
            self.properties.show_node(self._selected_node_tags[0])
            self._refresh_model_management_menus()
            return
        if len(self._selected_element_tags) == 1 and not self._selected_node_tags and not self._selected_surface_tags:
            self.tree.select_element(self._selected_element_tags[0])
            self.properties.show_element(self._selected_element_tags[0])
            self._refresh_model_management_menus()
            return
        if len(self._selected_surface_tags) == 1 and not self._selected_node_tags and not self._selected_element_tags:
            self.tree.select_surface(self._selected_surface_tags[0])
            self.properties.show_surface(self._selected_surface_tags[0])
            self._refresh_model_management_menus()
            return

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.properties.clear_display()
        self._refresh_model_management_menus()

    def _select_node_after_change(self, tag: int) -> None:
        """Handle select node after change."""
        self._select_objects_after_change([tag], [])

    def _select_surface_after_change(self, tag: int) -> None:
        """Handle select surface after change."""
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = [tag]
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [tag], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [tag], emit_signal=False)
        self.tree.select_surface(tag)
        self.properties.show_surface(tag)
        self._refresh_model_management_menus()

    def _copy_source_node_tags(
        self,
        node_tags: list[int] | tuple[int, ...],
        element_tags: list[int] | tuple[int, ...],
        surface_tags: list[int] | tuple[int, ...] | None = None,
    ) -> list[int]:
        """Copy source node tags."""
        source_tags = {int(tag) for tag in node_tags if int(tag) in self.project.nodes}
        for element_tag in element_tags:
            element = self.project.elements.get(int(element_tag))
            if element is None:
                continue
            source_tags.add(element.node_i)
            source_tags.add(element.node_j)
        for surface_tag in surface_tags or []:
            surface = self.project.surface_elements.get(int(surface_tag))
            if surface is None:
                continue
            source_tags.update(int(tag) for tag in surface.node_tags)
        return sorted(source_tags)

    def _check_copy_coordinate_conflicts(
        self,
        copy_instances: list[dict[int, tuple[float, float, float]]],
    ) -> tuple[str, int | None, tuple[float, float, float] | None]:
        """Handle check copy coordinate conflicts."""
        planned_points: list[tuple[float, float, float]] = []
        for instance in copy_instances:
            for point in instance.values():
                existing_tag = self._find_other_node_at_point(point)
                if existing_tag is not None:
                    return ("existing", existing_tag, point)
                for planned_point in planned_points:
                    if self._points_equal(planned_point, point):
                        return ("planned", None, point)
                planned_points.append(point)
        return ("", None, None)

    def _reuse_or_insert_copied_node(
        self,
        *,
        source_node: NodeData,
        point: tuple[float, float, float],
        allow_reuse_existing: bool,
    ) -> tuple[int, bool]:
        """Handle reuse or insert copied node."""
        if allow_reuse_existing:
            existing_tag = self._find_other_node_at_point(point)
            if existing_tag is not None:
                return existing_tag, False

        copied_node = self._insert_node_with_tag(
            tag=self.project.next_node_tag(),
            x=float(point[0]),
            y=float(point[1]),
            z=float(point[2]),
            fixities=tuple(source_node.fixities[:6]),
            boundary_data=source_node.boundary_data,
        )
        return copied_node.tag, True

    def _pick_copy_origin_point(self) -> tuple[float, float, float] | None:
        """Handle pick copy origin point."""
        candidate_views = [
            view
            for view in (self.model_view, getattr(self, "secondary_view", None))
            if view is not None and hasattr(view, "set_cursor_pick_mode")
        ]
        if not candidate_views:
            return None

        picked_point: dict[str, tuple[float, float, float] | None] = {"value": None}
        loop = QEventLoop(self)
        connections: list[tuple[object, str, object]] = []

        def _finish(point: tuple[float, float, float] | None) -> None:
            if picked_point["value"] is None:
                picked_point["value"] = point
            if loop.isRunning():
                loop.quit()

        self.statusbar.showMessage(
            "Choisissez l'origine de copie dans une vue. Échap pour annuler."
        )
        self._log("Choix d'origine de copie : cliquez dans une vue. Échap pour annuler.")

        try:
            for view in candidate_views:
                view.set_cursor_pick_mode(True, snap_to_grid=True)

                def _on_point_picked(x: float, y: float, z: float, _finish=_finish) -> None:
                    _finish((float(x), float(y), float(z)))

                def _on_pick_cancelled(_finish=_finish) -> None:
                    _finish(None)

                view.cursor_point_picked.connect(_on_point_picked)
                view.cursor_pick_cancelled.connect(_on_pick_cancelled)
                connections.append((view.cursor_point_picked, "disconnect", _on_point_picked))
                connections.append((view.cursor_pick_cancelled, "disconnect", _on_pick_cancelled))

            loop.exec()
        finally:
            for view in candidate_views:
                view.set_cursor_pick_mode(False)
            for signal, _action, slot in connections:
                try:
                    signal.disconnect(slot)
                except Exception:
                    pass
            self._update_statusbar()

        if picked_point["value"] is not None:
            x, y, z = picked_point["value"]
            self._log(f"Origine de copie choisie : ({x:.3f}, {y:.3f}, {z:.3f}).")
        else:
            self._log("Choix d'origine de copie annulé.")
        return picked_point["value"]

    def _copy_selected_objects(self) -> None:
        """Copy selected objects."""
        from gui.dialogs.copy_selection_dlg import CopySelectionDialog

        selected_node_tags = self._selected_existing_node_tags()
        selected_element_tags = self._selected_existing_element_tags()
        selected_surface_tags = self._selected_existing_surface_tags()
        if selected_surface_tags and not self._surface_features_enabled():
            if not selected_node_tags and not selected_element_tags:
                self._ensure_surface_features_available("Plaques indisponibles")
                return
            self._log(
                "Les surfaces sélectionnées sont ignorées car les plaques sont indisponibles avec le solveur courant."
            )
            selected_surface_tags = []

        if not selected_node_tags and not selected_element_tags and not selected_surface_tags:
            QMessageBox.information(
                self,
                "Copier la sélection",
                "Sélectionnez au moins un nœud, une barre ou une surface avant de copier.",
            )
            return

        source_node_tags = self._copy_source_node_tags(
            selected_node_tags,
            selected_element_tags,
            selected_surface_tags,
        )
        if not source_node_tags:
            QMessageBox.warning(
                self,
                "Copier la sélection",
                "Impossible de déterminer les nœuds à copier.",
            )
            return

        source_points = {
            tag: (
                float(self.project.nodes[tag].x),
                float(self.project.nodes[tag].y),
                float(self.project.nodes[tag].z),
            )
            for tag in source_node_tags
        }
        base_point = selection_anchor_point(source_points.values())

        params: dict[str, float | int | str] = {
            "mode": "coordinates",
            "target_x": float(base_point[0]),
            "target_y": float(base_point[1]),
            "target_z": float(base_point[2]),
            "dx": 0.0,
            "dy": 0.0,
            "dz": 0.0,
            "copies": 1,
        }

        while True:
            dlg = CopySelectionDialog(
                self,
                base_point=base_point,
                node_count=len(source_node_tags),
                element_count=len(selected_element_tags),
                surface_count=len(selected_surface_tags),
                initial_values=params,
            )
            status = dlg.exec()
            params = dlg.values()

            if status == CopySelectionDialog.PICK_ORIGIN_CODE:
                picked_origin = self._pick_copy_origin_point()
                if picked_origin is not None:
                    params["mode"] = "coordinates"
                    params["target_x"] = float(picked_origin[0])
                    params["target_y"] = float(picked_origin[1])
                    params["target_z"] = float(picked_origin[2])
                    params["dx"] = float(picked_origin[0] - base_point[0])
                    params["dy"] = float(picked_origin[1] - base_point[1])
                    params["dz"] = float(picked_origin[2] - base_point[2])
                continue

            if status != QDialog.Accepted:
                return
            break

        dx = float(params["dx"])
        dy = float(params["dy"])
        dz = float(params["dz"])
        allow_reuse_existing_nodes = bool(selected_element_tags or selected_surface_tags)
        copy_instances = build_copy_instance_points(
            source_points,
            dx=dx,
            dy=dy,
            dz=dz,
            copy_count=int(params["copies"]),
        )
        if not allow_reuse_existing_nodes:
            conflict_kind, conflict_tag, conflict_point = self._check_copy_coordinate_conflicts(
                copy_instances
            )
            if conflict_kind == "existing" and conflict_tag is not None and conflict_point is not None:
                QMessageBox.warning(
                    self,
                    "Coordonnées déjà utilisées",
                    (
                        f"La copie créerait un nœud aux mêmes coordonnées que N{conflict_tag} :\n"
                        f"({conflict_point[0]:.3f}, {conflict_point[1]:.3f}, {conflict_point[2]:.3f}).\n\n"
                        "Modifiez la cible, le delta ou le nombre de copies."
                    ),
                )
                self._select_node_after_change(conflict_tag)
                return
            if conflict_kind == "planned" and conflict_point is not None:
                QMessageBox.warning(
                    self,
                    "Copies superposées",
                    (
                        "La configuration saisie crée plusieurs nœuds copiés au même point :\n"
                        f"({conflict_point[0]:.3f}, {conflict_point[1]:.3f}, {conflict_point[2]:.3f}).\n\n"
                        "Modifiez le delta ou réduisez le nombre de copies."
                    ),
                )
                return

        explicit_node_tag_set = set(selected_node_tags)
        nodal_loads_by_node: dict[int, list[NodalLoad]] = {}
        for load in list(self.project.nodal_loads):
            nodal_loads_by_node.setdefault(load.node_tag, []).append(load)

        element_loads_by_element: dict[int, list[ElementLoad]] = {}
        for load in list(self.project.element_loads):
            element_loads_by_element.setdefault(load.element_tag, []).append(load)

        surface_loads_by_surface: dict[int, list[SurfaceLoad]] = {}
        for load in list(self.project.surface_loads):
            surface_loads_by_surface.setdefault(load.surface_tag, []).append(load)

        created_node_count = 0
        reused_node_count = 0
        skipped_existing_element_count = 0
        skipped_existing_surface_count = 0
        copied_node_tags: list[int] = []
        copied_element_tags: list[int] = []
        copied_surface_tags: list[int] = []

        for instance in copy_instances:
            node_tag_map: dict[int, int] = {}
            for source_tag in source_node_tags:
                source_node = self.project.nodes[source_tag]
                target_point = (
                    float(instance[source_tag][0]),
                    float(instance[source_tag][1]),
                    float(instance[source_tag][2]),
                )
                target_node_tag, created = self._reuse_or_insert_copied_node(
                    source_node=source_node,
                    point=target_point,
                    allow_reuse_existing=allow_reuse_existing_nodes,
                )
                node_tag_map[source_tag] = target_node_tag
                if created:
                    created_node_count += 1
                else:
                    reused_node_count += 1

                if source_tag in explicit_node_tag_set:
                    copied_node_tags.append(target_node_tag)

                for nodal_load in nodal_loads_by_node.get(source_tag, []):
                    self.project.nodal_loads.append(
                        NodalLoad(
                            load_tag=nodal_load.load_tag,
                            node_tag=target_node_tag,
                            fx=nodal_load.fx,
                            fy=nodal_load.fy,
                            fz=nodal_load.fz,
                            mx=nodal_load.mx,
                            my=nodal_load.my,
                            mz=nodal_load.mz,
                        )
                    )

            for source_element_tag in selected_element_tags:
                source_element = self.project.elements.get(source_element_tag)
                if source_element is None:
                    continue
                node_i = node_tag_map[source_element.node_i]
                node_j = node_tag_map[source_element.node_j]
                if self._find_element_between_nodes(node_i, node_j) is not None:
                    skipped_existing_element_count += 1
                    continue
                copied_element = self.project.add_element(
                    node_i,
                    node_j,
                    section_tag=source_element.section_tag,
                    element_type=source_element.element_type,
                )
                copied_element_tags.append(copied_element.tag)

                for element_load in element_loads_by_element.get(source_element_tag, []):
                    self.project.element_loads.append(
                        ElementLoad(
                            load_tag=element_load.load_tag,
                            element_tag=copied_element.tag,
                            wx=element_load.wx,
                            wy=element_load.wy,
                            wz=element_load.wz,
                        )
                    )

            for source_surface_tag in selected_surface_tags:
                source_surface = self.project.surface_elements.get(source_surface_tag)
                if source_surface is None:
                    continue
                mapped_node_tags = [
                    node_tag_map[int(source_node_tag)]
                    for source_node_tag in source_surface.node_tags
                ]
                validation = self._validate_surface_definition(
                    mapped_node_tags,
                    source_surface.section_tag,
                )
                if validation is None:
                    continue
                ordered_node_tags, _plane, existing_surface_tag = validation
                if existing_surface_tag is not None:
                    skipped_existing_surface_count += 1
                    continue
                copied_surface = self.project.add_surface_element(
                    ordered_node_tags,
                    section_tag=source_surface.section_tag,
                    surface_type=source_surface.surface_type,
                )
                copied_surface_tags.append(copied_surface.tag)
                for surface_load in surface_loads_by_surface.get(source_surface_tag, []):
                    self.project.surface_loads.append(
                        SurfaceLoad(
                            load_tag=surface_load.load_tag,
                            surface_tag=copied_surface.tag,
                            qx=surface_load.qx,
                            qy=surface_load.qy,
                            qz=surface_load.qz,
                        )
                    )

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._select_objects_after_change(
            sorted(set(copied_node_tags)),
            sorted(set(copied_element_tags)),
            sorted(set(copied_surface_tags)),
        )

        log_message = (
            "Copie effectuée : "
            f"{len(copy_instances)} copie(s), "
            f"{created_node_count} nœud(s) créé(s), "
            f"{reused_node_count} nœud(s) reutilise(s), "
            f"{len(set(copied_node_tags))} nœud(s) explicitement sélectionné(s) duplique(s), "
            f"{len(copied_element_tags)} barre(s) dupliquee(s), "
            f"{len(copied_surface_tags)} surface(s) dupliquee(s)."
        )
        if skipped_existing_element_count:
            log_message += (
                f" {skipped_existing_element_count} barre(s) déjà presente(s) "
                "sur le même span ont été ignorée(s)."
            )
        if skipped_existing_surface_count:
            log_message += (
                f" {skipped_existing_surface_count} surface(s) déjà presente(s) "
                "sur les mêmes nœuds ont été ignorée(s)."
            )
        self._log(log_message)

    def _replace_selected_node(
        self,
        *,
        original_tag: int,
        new_tag: int,
        x: float,
        y: float,
        z: float,
    ) -> None:
        """Handle replace selected node."""
        node = self.project.nodes.get(original_tag)
        if node is None:
            return

        if new_tag != original_tag and new_tag in self.project.nodes:
            QMessageBox.warning(
                self,
                "Nœud existant",
                f"Le numéro N{new_tag} existe déjà. Choisissez un autre numéro.",
            )
            return

        duplicate_tag = self._find_other_node_at_point(
            (x, y, z),
            exclude_tag=original_tag,
        )
        if duplicate_tag is not None:
            QMessageBox.warning(
                self,
                "Coordonnées déjà utilisées",
                (
                    f"Les coordonnées saisies correspondent déjà au nœud N{duplicate_tag}.\n\n"
                    "Deux nœuds ne peuvent pas partager les mêmes coordonnées."
                ),
            )
            self._select_node_after_change(duplicate_tag)
            return

        coords_changed = not self._points_equal((node.x, node.y, node.z), (x, y, z))
        tag_changed = new_tag != original_tag
        if not coords_changed and not tag_changed:
            self._select_node_after_change(original_tag)
            self._log(f"Nœud N{original_tag} inchangé.")
            return

        connected_elements = self._connected_element_tags_for_node(original_tag)
        connected_surfaces = self._connected_surface_tags_for_node(original_tag)
        if connected_elements or connected_surfaces:
            extra_lines = []
            if connected_elements:
                extra_lines.append(
                    f"Le nœud N{original_tag} est relié à {len(connected_elements)} barre(s)."
                )
            if connected_surfaces:
                extra_lines.append(
                    f"Le nœud N{original_tag} est relié à {len(connected_surfaces)} surface(s)."
                )
            ret = QMessageBox.warning(
                self,
                "Éléments connectés",
                "\n".join(extra_lines)
                + "\n\nSi vous confirmez, ces éléments connectés seront supprimés.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._delete_elements_by_tags(connected_elements)
            self._delete_surface_elements_by_tags(connected_surfaces)

        if tag_changed:
            self.project.nodes.pop(original_tag, None)
            node.tag = new_tag
            self.project.nodes[new_tag] = node
            for load in self.project.nodal_loads:
                if load.node_tag == original_tag:
                    load.node_tag = new_tag
            for elem in self.project.elements.values():
                if elem.node_i == original_tag:
                    elem.node_i = new_tag
                if elem.node_j == original_tag:
                    elem.node_j = new_tag
            for surface in self.project.surface_elements.values():
                if original_tag in surface.node_tags:
                    surface.node_tags = tuple(
                        new_tag if tag == original_tag else tag
                        for tag in surface.node_tags
                    )

        node.x = x
        node.y = y
        node.z = z

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._select_node_after_change(new_tag)

        deleted_details: list[str] = []
        if connected_elements:
            deleted_details.append(f"{len(connected_elements)} barre(s)")
        if connected_surfaces:
            deleted_details.append(f"{len(connected_surfaces)} surface(s)")
        deleted_part = ""
        if deleted_details:
            deleted_part = " Éléments connectés supprimés : " + ", ".join(deleted_details) + "."
        self._log(
            f"Nœud N{original_tag} remplacé par N{new_tag} en "
            f"({x:.3f}, {y:.3f}, {z:.3f}).{deleted_part}"
        )

    def _add_material(self) -> None:
        """Add material."""
        from gui.dialogs.material_dlg import MaterialDialog

        dlg = MaterialDialog(self)
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        mat = self.project.add_material(
            data["name"],
            data["material_type"],
            data["grade"],
            **data["properties"],
        )
        self._mark_project_modified()
        self._refresh(preserve_view=True, refresh_scene=False)
        self._log(f"Matériau « {mat.name} » ({mat.grade}) ajouté.")

    def _manage_materials(self) -> None:
        """Handle manage materials."""
        from gui.dialogs.library_manager_dlg import MaterialManagerDialog

        dlg = MaterialManagerDialog(
            self,
            materials=self.project.materials,
            sections=self.project.sections,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self.project.materials = dlg.result_materials()
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log("Bibliothèque de matériaux mise à jour.")

    def _edit_material(self, tag: int | None = None) -> None:
        """Edit material."""
        from gui.dialogs.material_dlg import MaterialDialog

        if tag is None:
            tag = self._choose_material_tag(
                "Modifier un matériau",
                "Matériau :",
            )
        if tag is None:
            return

        mat = self.project.materials.get(tag)
        if mat is None:
            return

        dlg = MaterialDialog(
            self,
            name=mat.name,
            material_type=mat.material_type,
            grade=mat.grade,
            properties=mat.properties,
        )
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        mat.name = data["name"]
        mat.material_type = data["material_type"]
        mat.grade = data["grade"]
        mat.properties = data["properties"]

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log(f"Matériau « {mat.name} » (T{tag}) mis à jour.")

    def _add_section(self) -> None:
        """Add section."""
        from gui.dialogs.section_dlg import SectionDialog

        if not self.project.materials:
            QMessageBox.warning(
                self, "Attention",
                "Créez d'abord un matériau avant d'ajouter une section.",
            )
            return

        dlg = SectionDialog(
            self,
            materials=self.project.materials,
            allowed_types=("rectangular", "T", "I_profile"),
        )
        if dlg.exec() != SectionDialog.Accepted:
            return

        data = dlg.result()
        sec = self.project.add_section(
            name=data["name"],
            section_type=data["section_type"],
            material_tag=data["material_tag"],
            properties=data.get("properties", {}),
            area=data.get("area", 0.0),
            inertia_y=data.get("inertia_y", 0.0),
            inertia_z=data.get("inertia_z", 0.0),
        )
        self._mark_project_modified()
        self._refresh(preserve_view=True, refresh_scene=False)
        self._log(f"Section « {sec.name} » ajoutée (A={sec.area:.4e} m²).")

    def _add_plate_section(self) -> None:
        """Add plate section."""
        from gui.dialogs.plate_section_dlg import PlateSectionDialog
        if not self._ensure_surface_features_available():
            return

        dlg = PlateSectionDialog(self, materials=self.project.materials)
        if dlg.exec() != PlateSectionDialog.Accepted:
            return

        data = dlg.result()
        self.project.materials = dlg.result_materials()
        sec = self.project.add_section(
            name=data["name"],
            section_type="surface",
            material_tag=data["material_tag"],
            properties=data.get("properties", {}),
            area=0.0,
            inertia_y=0.0,
            inertia_z=0.0,
        )
        self._mark_project_modified()
        self._refresh(preserve_view=True, refresh_scene=False)
        self._log(
            f"Section plaque « {sec.name} » ajoutée ({sec.surface_formulation}, e={sec.thickness:.3f} m)."
        )

    def _manage_sections(self) -> None:
        """Open the section manager."""
        from gui.dialogs.library_manager_dlg import SectionManagerDialog

        dlg = SectionManagerDialog(
            self,
            sections={tag: sec for tag, sec in self.project.sections.items() if not sec.is_surface},
            materials=self.project.materials,
            element_section_tags={
                elem.section_tag for elem in self.project.elements.values()
            } | {
                plate.section_tag for plate in self.project.plate_regions.values()
            },
            allowed_types=("rectangular", "T", "I_profile"),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        self.project.sections = {
            tag: sec for tag, sec in self.project.sections.items() if sec.is_surface
        }
        self.project.sections.update(dlg.result_sections())
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log("Bibliothèque de sections mise à jour.")

    def _manage_plate_sections(self) -> None:
        """Handle manage plate sections."""
        from gui.dialogs.plate_section_manager_dlg import PlateSectionManagerDialog
        if not self._ensure_surface_features_available():
            return

        dlg = PlateSectionManagerDialog(
            self,
            sections=self.project.sections,
            materials=self.project.materials,
            used_section_tags={
                surface.section_tag for surface in self.project.surface_elements.values()
            } | {
                plate.section_tag for plate in self.project.plate_regions.values()
            },
        )
        if dlg.exec() != QDialog.Accepted:
            return

        candidate_sections = {
            tag: sec for tag, sec in self.project.sections.items() if not sec.is_surface
        }
        candidate_sections.update(dlg.result_sections())
        compatibility_issues = self._surface_section_compatibility_issues(candidate_sections)
        if compatibility_issues:
            details = "\n".join(
                f"- {message}" for _surface_tag, message in compatibility_issues[:5]
            )
            if len(compatibility_issues) > 5:
                details += f"\n- ... et {len(compatibility_issues) - 5} autre(s)."
            QMessageBox.warning(
                self,
                "Sections plaque incompatibles",
                "Les modifications proposees rendent certaines plaques incompatibles :\n\n"
                + details,
            )
            self._select_surface_after_change(compatibility_issues[0][0])
            return

        self.project.materials = dlg.result_materials()
        self.project.sections = candidate_sections
        for plate in self.project.plate_regions.values():
            sec = self.project.sections.get(int(plate.section_tag))
            if sec is not None and sec.is_surface:
                plate.formulation = sec.surface_formulation
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log("Bibliothèque des sections plaque mise à jour.")

    def _edit_section(self, tag: int | None = None) -> None:
        """Edit section."""
        if tag is None:
            tag = self._choose_section_tag(
                "Modifier une section",
                "Section :",
            )
        if tag is None:
            return

        sec = self.project.sections.get(tag)
        if sec is None:
            return
        if sec.is_surface and not self._ensure_surface_features_available():
            return

        if sec.is_surface:
            from gui.dialogs.plate_section_dlg import PlateSectionDialog

            dlg = PlateSectionDialog(
                self,
                materials=self.project.materials,
                name=sec.name,
                material_tag=sec.material_tag,
                properties=sec.properties,
            )
            if dlg.exec() != PlateSectionDialog.Accepted:
                return
            self.project.materials = dlg.result_materials()
            data = dlg.result()
        else:
            from gui.dialogs.section_dlg import SectionDialog

            dlg = SectionDialog(
                self,
                materials=self.project.materials,
                name=sec.name,
                section_type=sec.section_type,
                material_tag=sec.material_tag,
                properties=sec.properties,
                allowed_types=("rectangular", "T", "I_profile"),
            )
            if dlg.exec() != SectionDialog.Accepted:
                return
            data = dlg.result()

        if sec.is_surface:
            new_formulation = data.get("properties", {}).get("element_formulation", "ShellMITC4")
            expected_count = surface_expected_node_count(new_formulation)
            incompatible_surfaces = [
                surface.tag
                for surface in self.project.surface_elements.values()
                if surface.section_tag == tag and len(surface.node_tags) != expected_count
            ]
            if incompatible_surfaces:
                QMessageBox.warning(
                    self,
                    "Formulation incompatible",
                    (
                        f"La formulation {new_formulation} attend {expected_count} nœud(s), "
                        f"mais la surface S{incompatible_surfaces[0]} en a "
                        f"{len(self.project.surface_elements[incompatible_surfaces[0]].node_tags)}."
                    ),
                )
                self._select_surface_after_change(incompatible_surfaces[0])
                return

        sec.name = data["name"]
        sec.section_type = data["section_type"]
        sec.material_tag = data["material_tag"]
        sec.properties = data.get("properties", {})
        sec.area = data.get("area", 0.0)
        sec.inertia_y = data.get("inertia_y", 0.0)
        sec.inertia_z = data.get("inertia_z", 0.0)

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log(f"Section « {sec.name} » (T{tag}) mise à jour.")

    def _add_element(self) -> None:
        """Add element."""
        if len(self.project.nodes) < 2:
            QMessageBox.warning(
                self, "Attention",
                "Il faut au moins 2 nœuds pour créer un élément.",
            )
            return
        line_sections = self._line_section_items()
        if not line_sections:
            QMessageBox.warning(
                self, "Attention",
                "Créez d'abord une section de barre avant d'ajouter un élément.",
            )
            return

        node_tags = sorted(self.project.nodes.keys())
        items_i = [f"N{t}" for t in node_tags]

        ni_str, ok = QInputDialog.getItem(
            self, "Ajouter un élément", "Nœud de début :", items_i, 0, False,
        )
        if not ok:
            return
        ni_tag = int(ni_str[1:])

        items_j = [f"N{t}" for t in node_tags if t != ni_tag]
        nj_str, ok = QInputDialog.getItem(
            self, "Ajouter un élément", "Nœud de fin :", items_j, 0, False,
        )
        if not ok:
            return
        nj_tag = int(nj_str[1:])

        sec_tags = [tag for tag, _sec in line_sections]
        items_s = [f"{self.project.sections[t].name} (T{t})" for t in sec_tags]
        sec_str, ok = QInputDialog.getItem(
            self, "Ajouter un élément", "Section :", items_s, 0, False,
        )
        if not ok:
            return
        sec_tag = sec_tags[items_s.index(sec_str)]

        try:
            elem = self.project.add_element(ni_tag, nj_tag, section_tag=sec_tag)
        except ValueError as exc:
            QMessageBox.warning(self, "Barre invalide", str(exc))
            return
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log(f"Élément E{elem.tag} ajouté (N{ni_tag} → N{nj_tag}).")

    def _add_surface(self) -> None:
        """Add surface."""
        if not self._ensure_surface_features_available():
            return
        selected_node_tags = self._selected_existing_node_tags()
        if len(selected_node_tags) not in (3, 4):
            QMessageBox.information(
                self,
                "Création de surface",
                "Sélectionnez d'abord 3 ou 4 nœuds d'une même file.",
            )
            return

        section_tag = self._choose_surface_section_tag()
        if section_tag is None:
            return
        sec = self.project.sections.get(section_tag)
        if sec is None or not sec.is_surface:
            return
        validation = self._validate_surface_definition(selected_node_tags, section_tag)
        if validation is None:
            return
        ordered_node_tags, plane, existing_surface_tag = validation
        if existing_surface_tag is not None:
            QMessageBox.information(
                self,
                "Surface existante",
                f"Une surface S{existing_surface_tag} utilise déjà ces nœuds.",
            )
            self._select_surface_after_change(existing_surface_tag)
            return
        existing_plate_tag = self._find_plate_region_by_node_tags(ordered_node_tags)
        if existing_plate_tag is not None:
            QMessageBox.information(
                self,
                "Plaque existante",
                f"Une plaque P{existing_plate_tag} utilise deja ces noeuds.",
            )
            return

        plate = self._add_user_plate_region(ordered_node_tags, section_tag, plane)
        if plate is None:
            return
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._select_surface_after_change(plate.tag)
        return

    def _edit_element(self, tag: int | None = None) -> None:
        """Edit element."""
        if tag is None:
            selected_element_tags = self._selected_existing_element_tags()
            if len(selected_element_tags) != 1:
                QMessageBox.information(
                    self,
                    "Modifier une barre",
                    "Sélectionnez une seule barre avant de la modifier.",
                )
                return
            tag = selected_element_tags[0]

        element = self.project.elements.get(tag)
        if element is None:
            return

        self._select_element_for_context(element.tag)
        if getattr(self, "dock_properties", None) is not None:
            self.dock_properties.show()
            if hasattr(self.dock_properties, "raise_"):
                self.dock_properties.raise_()
        self.properties.show_element(element.tag)
        if hasattr(self.properties, "setFocus"):
            self.properties.setFocus(Qt.OtherFocusReason)
        self._log(f"Barre E{element.tag} prête à être modifiée dans le panneau Propriétés.")

    def _show_element_properties(self, tag: int) -> None:
        """Show element properties."""
        if tag not in self.project.elements:
            return
        from gui.dialogs.element_properties_dlg import ElementPropertiesDialog

        case_name = self._current_case if self._current_case in self._all_results else None
        if case_name is None and self._all_results:
            case_name = next(iter(self._all_results))
        case_results = self._all_results.get(case_name or "", None)
        dlg = ElementPropertiesDialog(
            self,
            self.project,
            tag,
            case_name=case_name,
            case_results=case_results,
        )
        dlg.exec()

    def _show_surface_properties(self, tag: int) -> None:
        """Show surface properties."""
        tag = int(tag)
        if not self._select_surface_for_context(tag):
            return

        case_name = self._current_case if self._current_case in self._all_results else None
        if self._all_results:
            case_name = case_name or next(
                (
                    name
                    for name, results in self._all_results.items()
                    if tag in results.get("surface_results", {})
                ),
                next(iter(self._all_results)),
            )
        case_results = self._all_results.get(case_name or "", None)
        if tag in self.project.plate_regions and tag not in self.project.surface_elements:
            dlg = PlateRegionPropertiesDialog(
                self,
                self.project,
                tag,
                case_name=case_name,
                case_results=case_results,
            )
            dlg.exec()
            return

        from gui.dialogs.surface_properties_dlg import SurfacePropertiesDialog

        dlg = SurfacePropertiesDialog(
            self,
            self.project,
            tag,
            case_name=case_name,
            case_results=case_results,
        )
        dlg.exec()

    def _edit_surface(self, tag: int | None = None) -> None:
        """Edit surface."""
        if not self._ensure_surface_features_available():
            return
        if tag is None:
            selected_surface_tags = self._selected_existing_surface_tags()
            if len(selected_surface_tags) != 1:
                QMessageBox.information(
                    self,
                    "Modifier une surface",
                    "Sélectionnez une seule surface avant de la modifier.",
                )
                return
            tag = selected_surface_tags[0]

        surface = self.project.surface_elements.get(tag)
        if surface is None:
            return

        self._select_surface_after_change(surface.tag)
        if getattr(self, "dock_properties", None) is not None:
            self.dock_properties.show()
            if hasattr(self.dock_properties, "raise_"):
                self.dock_properties.raise_()
        self.properties.show_surface(surface.tag)
        if hasattr(self.properties, "setFocus"):
            self.properties.setFocus(Qt.OtherFocusReason)
        self._log(f"Surface S{surface.tag} prête à être modifiée dans le panneau Propriétés.")

    def _on_edit_requested(self, kind: str, tag: int) -> None:
        """Handle edit requested."""
        if kind == "element":
            self._edit_element(tag)
            return
        if kind == "surface":
            self._edit_surface(tag)
            return
        if kind == "material":
            self._edit_material(tag)
            return
        if kind == "section":
            self._edit_section(tag)
            return
        if kind == "load":
            self._edit_load_case(tag)

    def _on_delete_requested(self, kind: str, tag: int) -> None:
        """Handle delete requested."""
        if kind == "material":
            self._delete_material_from_menu(tag)
            return
        if kind == "section":
            self._delete_section_from_menu(tag)
            return
        if kind == "node":
            self._delete_selected_objects([tag], [])
            return
        if kind == "element":
            self._delete_selected_objects([], [tag])
            return
        if kind == "surface":
            self._delete_surface_from_menu(tag)
            return

        name_map = {
            "node": f"le nœud N{tag}",
            "element": f"l'élément E{tag}",
            "surface": f"la surface S{tag}",
            "material": f"le matériau T{tag}",
            "section": f"la section T{tag}",
            "load": f"le cas de charge T{tag}",
            "combination": f"la combinaison T{tag}",
        }
        label = name_map.get(kind, f"l'objet {tag}")

        reply = QMessageBox.question(
            self, "Confirmer la suppression",
            f"Supprimer {label} ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        collection_map = {
            "node": self.project.nodes,
            "element": self.project.elements,
            "surface": self.project.surface_elements,
            "material": self.project.materials,
            "section": self.project.sections,
            "load": self.project.loads,
            "combination": self.project.combinations,
        }
        collection = collection_map.get(kind)
        if collection and tag in collection:
            del collection[tag]
            self._mark_project_modified()
            self.properties.clear_display()
            self._refresh(preserve_view=True)
            self._log(f"Supprimé : {label}.")

    def _delete_material_from_menu(self, tag: int | None = None) -> None:
        """Delete material from menu."""
        if tag is None:
            tag = self._choose_material_tag(
                "Supprimer un matériau",
                "Matériau :",
            )
        if tag is None:
            return

        mat = self.project.materials.get(tag)
        if mat is None:
            return

        used_by = [
            sec.tag for sec in self.project.sections.values()
            if sec.material_tag == tag
        ]
        if used_by:
            QMessageBox.warning(
                self,
                "Suppression impossible",
                "Ce matériau est encore utilisé par une ou plusieurs sections.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer le matériau « {mat.name} » (T{tag}) ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self.project.materials[tag]
        self._mark_project_modified()
        self.properties.clear_display()
        self._refresh(preserve_view=True)
        self._log(f"Matériau « {mat.name} » supprimé.")

    def _delete_section_from_menu(self, tag: int | None = None) -> None:
        """Delete section from menu."""
        if tag is None:
            tag = self._choose_section_tag(
                "Supprimer une section",
                "Section :",
            )
        if tag is None:
            return

        sec = self.project.sections.get(tag)
        if sec is None:
            return

        used_by = [
            elem.tag for elem in self.project.elements.values()
            if elem.section_tag == tag
        ]
        used_by_surfaces = [
            surface.tag for surface in self.project.surface_elements.values()
            if surface.section_tag == tag
        ]
        used_by_surfaces.extend(
            plate.tag for plate in self.project.plate_regions.values()
            if plate.section_tag == tag
        )
        if used_by or used_by_surfaces:
            QMessageBox.warning(
                self,
                "Suppression impossible",
                "Cette section est encore utilisée par un ou plusieurs éléments ou surfaces.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer la section « {sec.name} » (T{tag}) ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self.project.sections[tag]
        self._mark_project_modified()
        self.properties.clear_display()
        self._refresh(preserve_view=True)
        self._log(f"Section « {sec.name} » supprimée.")

    def _delete_surface_from_menu(self, tag: int | None = None) -> None:
        """Delete surface from menu."""
        if tag is None:
            QMessageBox.information(
                self,
                "Supprimer une surface",
                "Sélectionnez une surface dans l'arbre pour la supprimer.",
            )
            return

        is_surface = tag in self.project.surface_elements
        is_plate = tag in self.project.plate_regions
        if not is_surface and not is_plate:
            return
        label = f"Plaque P{tag}" if is_plate and not is_surface else f"Surface S{tag}"

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer {label} ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._delete_surface_elements_by_tags([tag])
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = []
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [], emit_signal=False)
        self._mark_project_modified()
        self.properties.clear_display()
        self._refresh(preserve_view=True)
        self._log(f"{label} supprimée.")

    # -- File actions ---------------------------------------------------------

    def _on_new_project(self) -> None:
        """Handle new project."""
        if self._modified and not self._confirm_discard():
            return
        self.project = ProjectModel()
        self.project.grid.enabled = False
        self.project.seed_default_library()
        self.properties.set_project(self.project)
        self._active_parallel_plane = "3D"
        self._active_parallel_value = None
        self._secondary_parallel_plane = "3D"
        self._secondary_parallel_value = None
        self._selection_mode_active = True
        if hasattr(self, "act_select_tool"):
            self.act_select_tool.setChecked(True)
        if hasattr(self, "act_draw_node"):
            self.act_draw_node.setChecked(False)
        if hasattr(self, "act_draw_bars"):
            self.act_draw_bars.setChecked(False)
        self._clear_project_runtime_state()
        self._reset_project_history(mark_saved=True)
        self._refresh()
        self._log("Nouveau projet créé.")

    def _on_open_project(self) -> None:
        """Handle open project."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet",
            self.settings.last_project_dir,
            "Projets HEXA Structures (*.db);;Tous les fichiers (*)",
        )
        if not path:
            return
        try:
            self.project = load_project(path)
            self.project.ensure_self_weight_load_case()
            self.properties.set_project(self.project)
            self._clear_project_runtime_state()
            self._apply_grid_working_views()
            self._reset_project_history(mark_saved=True)
            self._refresh()
            self._log(f"Projet ouvert : {path}")
            self.settings.add_recent_project(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le projet :\n{e}")
            self._log(f"ERREUR : {e}")

    def _on_save_project(self) -> None:
        """Handle save project."""
        if not self.project.file_path:
            self._on_save_as()
            return
        self._save_to(self.project.file_path)

    def _on_save_as(self) -> None:
        """Handle save as."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le projet",
            self.settings.last_project_dir,
            "Projets HEXA Structures (*.db);;Tous les fichiers (*)",
        )
        if not path:
            return
        if not path.endswith(".db"):
            path += ".db"
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        """Save to."""
        try:
            save_project(self.project, path)
            self._propagate_project_path_to_history(path)
            self._saved_project_snapshot = deepcopy(self.project)
            self._last_history_project = deepcopy(self.project)
            self._pending_project_change = False
            self._sync_modified_with_saved_state(force_compare=True)
            self._update_history_actions()
            self._update_title()
            self._log(f"Projet sauvegardé : {path}")
            self.settings.add_recent_project(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder :\n{e}")
            self._log(f"ERREUR : {e}")

    # -- View actions ---------------------------------------------------------

    def _on_view_xy(self) -> None:
        if self.model_view:
            if hasattr(self, "combo_plane"):
                self.combo_plane.setCurrentText("XY")
            self.model_view.set_view_xy()

    def _on_view_xz(self) -> None:
        if self.model_view:
            if hasattr(self, "combo_plane"):
                self.combo_plane.setCurrentText("XZ")
            self.model_view.set_view_xz()

    def _on_view_yz(self) -> None:
        if self.model_view:
            if hasattr(self, "combo_plane"):
                self.combo_plane.setCurrentText("YZ")
            self.model_view.set_view_yz()

    def _on_view_iso(self) -> None:
        if self.model_view:
            if hasattr(self, "combo_plane"):
                self.combo_plane.setCurrentText("3D")

    def _on_toggle_node_tags(self, checked: bool) -> None:
        """Handle toggle node tags."""
        self.settings.gui.show_node_tags = checked
        preserve_view = True
        if self._deformed_visible and self._current_case:
            self._show_deformed(self._current_case, preserve_view=preserve_view, log_message=False)
        else:
            self._display_primary_model_view(preserve_view=preserve_view)
        self._display_secondary_model_view(preserve_view=preserve_view)

    def _on_toggle_section_names(self, checked: bool) -> None:
        """Handle toggle section names."""
        self.settings.gui.show_section_names = checked
        preserve_view = True
        if self._deformed_visible and self._current_case:
            self._show_deformed(self._current_case, preserve_view=preserve_view, log_message=False)
        else:
            self._display_primary_model_view(preserve_view=preserve_view)
        self._display_secondary_model_view(preserve_view=preserve_view)

    def _on_about(self) -> None:
        """Handle about."""
        QMessageBox.about(
            self,
            f"À propos de {APP_NAME}",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>Application open source de calcul de structures "
            "par éléments finis avec OpenSeesPy.</p>"
            "<p>Normes : Eurocodes + Annexes Nationales françaises.</p>"
            "<p>Licence LGPL-3.0-only</p>",
        )

    # -- Boundary conditions --------------------------------------------------

    def _edit_boundary(self) -> None:
        """Edit boundary."""
        from gui.dialogs.boundary_dlg import BoundaryDialog
        from core.boundary_conditions import BoundaryCondition, detect_boundary_type

        if not self.project.nodes:
            QMessageBox.warning(self, "Attention", "Aucun nœud dans le modèle.")
            return

        # Select the node
        node_tags = sorted(self.project.nodes.keys())
        items = [f"N{t}" for t in node_tags]
        sel, ok = QInputDialog.getItem(
            self, "Conditions aux limites", "Nœud :", items, 0, False,
        )
        if not ok:
            return
        tag = int(sel[1:])
        node = self.project.nodes[tag]

        # Charger la BC existante
        current = None
        if node.boundary_data:
            current = BoundaryCondition.from_dict(node.boundary_data)
        elif any(node.fixities):
            current = BoundaryCondition(
                bc_type=detect_boundary_type(node.fixities),
                fixities=tuple(node.fixities[:6]),
            )

        dlg = BoundaryDialog(self, current=current)
        if dlg.exec() != BoundaryDialog.Accepted:
            return

        bc = dlg.result()
        node.fixities = bc.fixities
        node.boundary_data = bc.to_dict()

        self._mark_project_modified()
        self._refresh()
        self._log(f"Appui N{tag} : {bc.summary()}")

    # -- Loads and combinations -----------------------------------------------

    def _selected_existing_node_tags(self) -> list[int]:
        """Return the selected existing node tags."""
        return sorted({tag for tag in self._selected_node_tags if tag in self.project.nodes})

    def _selected_existing_element_tags(self) -> list[int]:
        """Return the selected existing element tags."""
        return sorted(
            {tag for tag in self._selected_element_tags if tag in self.project.elements}
        )

    def _selected_existing_surface_tags(self) -> list[int]:
        """Return the selected existing surface tags."""
        return sorted(
            {
                tag
                for tag in getattr(self, "_selected_surface_tags", [])
                if tag in self.project.surface_elements
                or tag in getattr(self.project, "plate_regions", {})
            }
        )

    def _editable_load_cases(self):
        """Handle editable load cases."""
        from core.self_weight import is_self_weight_load

        return [
            (tag, load)
            for tag, load in sorted(self.project.loads.items())
            if not is_self_weight_load(load)
        ]

    def _choose_editable_load_case(self, title: str, prompt: str) -> int | None:
        """Choose editable load case."""
        editable_loads = self._editable_load_cases()
        if not editable_loads:
            reply = QMessageBox.question(
                self,
                title,
                "Aucun cas de charge manuel disponible. Créez d'abord un cas "
                "de charge autre que 'Poids propre'.\n\n"
                "Ouvrir le gestionnaire des cas de charge ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._manage_load_cases()
            return None

        items = [f"{lc.name} (T{tag})" for tag, lc in editable_loads]
        tags = [tag for tag, _lc in editable_loads]
        choice, ok = QInputDialog.getItem(self, title, prompt, items, 0, False)
        if not ok:
            return None
        return tags[items.index(choice)]

    def _node_boundary_condition(self, tag: int):
        """Handle node boundary condition."""
        from core.boundary_conditions import BoundaryCondition, detect_boundary_type

        node = self.project.nodes[tag]
        if node.boundary_data:
            return BoundaryCondition.from_dict(node.boundary_data)
        if any(node.fixities):
            return BoundaryCondition(
                bc_type=detect_boundary_type(node.fixities),
                fixities=tuple(node.fixities[:6]),
            )
        return BoundaryCondition()

    def _common_boundary_condition(self, node_tags: list[int]):
        """Handle common boundary condition."""
        if not node_tags:
            return None
        current = self._node_boundary_condition(node_tags[0])
        reference = current.to_dict()
        for current_tag in node_tags[1:]:
            if self._node_boundary_condition(current_tag).to_dict() != reference:
                return None
        return current

    def _edit_boundary(self) -> None:
        """Edit boundary."""
        from gui.dialogs.boundary_dlg import BoundaryDialog

        if not self.project.nodes:
            QMessageBox.warning(self, "Attention", "Aucun nœud dans le modèle.")
            return

        target_tags = self._selected_existing_node_tags()
        if not target_tags:
            node_tags = sorted(self.project.nodes.keys())
            items = [f"N{t}" for t in node_tags]
            sel, ok = QInputDialog.getItem(
                self, "Conditions aux limites", "Nœud :", items, 0, False,
            )
            if not ok:
                return
            target_tags = [int(sel[1:])]

        current = self._common_boundary_condition(target_tags)
        dlg = BoundaryDialog(self, current=current)
        if len(target_tags) == 1:
            dlg.setWindowTitle(f"Conditions aux limites - N{target_tags[0]}")
        else:
            dlg.setWindowTitle(f"Conditions aux limites - {len(target_tags)} nœuds")
        if dlg.exec() != BoundaryDialog.Accepted:
            return

        bc = dlg.result()
        for current_tag in target_tags:
            node = self.project.nodes[current_tag]
            node.fixities = bc.fixities
            node.boundary_data = bc.to_dict()

        self._mark_project_modified()
        self._selected_node_tags = list(target_tags)
        self._selected_element_tags = []
        self._selected_surface_tags = []
        self._refresh(preserve_view=True)
        if self.model_view is not None:
            self.model_view.set_selected_objects(target_tags, [], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects(target_tags, [], [], emit_signal=False)

        if len(target_tags) == 1:
            self.tree.select_node(target_tags[0])
            self.properties.show_node(target_tags[0])
            self._log(f"Appui N{target_tags[0]} : {bc.summary()}")
            return

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.properties.clear_display()
        self._log(
            f"Conditions aux limites appliquées a {len(target_tags)} nœuds : {bc.summary()}"
        )

    def _manage_load_cases(self) -> None:
        """Handle manage load cases."""
        self._manage_loads_and_combinations(start_page="loads")

    def _add_load_case(self) -> None:
        """Add load case."""
        self._manage_load_cases()

    def _create_load_case(self) -> None:
        """Create load case."""
        from gui.dialogs.load_dlg import LoadCaseDialog

        dlg = LoadCaseDialog(self, project=self.project)
        if dlg.exec() != LoadCaseDialog.Accepted:
            return

        tag = dlg.load_tag()
        self._mark_project_modified()
        self._refresh(preserve_view=True)
        lc = self.project.loads.get(tag)
        name = lc.name if lc else f"T{tag}"
        self._log(f"Cas de charge '{name}' créé (T{tag}).")

    def _edit_load_case(self, load_tag: int) -> None:
        """Edit load case."""
        from gui.dialogs.load_dlg import LoadEntryDialog
        from core.self_weight import is_self_weight_load

        load_case = self.project.loads.get(load_tag)
        if load_case is not None and is_self_weight_load(load_case):
            QMessageBox.information(
                self,
                "Poids propre automatique",
                "Le cas 'Poids propre' est calculé automatiquement à partir "
                "des sections et matériaux. Il ne se saisit pas manuellement.",
            )
            return

        if len(self.project.nodes) == 0:
            QMessageBox.warning(
                self, "Attention",
                "Ajoutez au moins un nœud avant de définir des charges.",
            )
            return

        dlg = LoadEntryDialog(
            self,
            project=self.project,
            load_tag=load_tag,
            selected_node_tags=self._selected_existing_node_tags(),
            selected_element_tags=self._selected_existing_element_tags(),
            selected_surface_tags=self._selected_existing_surface_tags(),
        )
        if dlg.exec() != LoadEntryDialog.Accepted:
            return

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        lc = self.project.loads.get(load_tag)
        name = lc.name if lc else f"T{load_tag}"
        self._log(f"Charges du cas '{name}' mises à jour.")

    def _define_loads(self) -> None:
        """Handle define loads."""
        from gui.dialogs.load_dlg import LoadEntryDialog

        if not self.project.loads:
            QMessageBox.warning(
                self, "Attention",
                "Créez d'abord un cas de charge (Modèle > Ajouter un cas de charge).",
            )
            return

        if len(self.project.nodes) == 0:
            QMessageBox.warning(
                self, "Attention",
                "Ajoutez au moins un nœud avant de définir des charges.",
            )
            return

        load_tag = self._choose_editable_load_case(
            "Définir les charges",
            "Cas de charge :",
        )
        if load_tag is None:
            return

        dlg = LoadEntryDialog(
            self,
            project=self.project,
            load_tag=load_tag,
            selected_node_tags=self._selected_existing_node_tags(),
            selected_element_tags=self._selected_existing_element_tags(),
            selected_surface_tags=self._selected_existing_surface_tags(),
        )
        if dlg.exec() != LoadEntryDialog.Accepted:
            return

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        lc = self.project.loads.get(load_tag)
        name = lc.name if lc else f"T{load_tag}"
        self._log(f"Charges du cas '{name}' mises à jour.")

    def _assign_loads_to_selection(self) -> None:
        """Handle assign loads to selection."""
        from gui.dialogs.load_dlg import LoadEntryDialog

        node_tags = self._selected_existing_node_tags()
        element_tags = self._selected_existing_element_tags()
        surface_tags = self._selected_existing_surface_tags()
        if not node_tags and not element_tags and not surface_tags:
            QMessageBox.information(
                self,
                "Affecter charges à la sélection",
                "Sélectionnez d'abord un ou plusieurs nœuds, éléments ou surfaces.",
            )
            return

        if len(self.project.nodes) == 0:
            QMessageBox.warning(
                self,
                "Attention",
                "Ajoutez au moins un nœud avant de définir des charges.",
            )
            return

        load_tag = self._choose_editable_load_case(
            "Affecter charges à la sélection",
            "Cas de charge :",
        )
        if load_tag is None:
            return

        dlg = LoadEntryDialog(
            self,
            project=self.project,
            load_tag=load_tag,
            selected_node_tags=node_tags,
            selected_element_tags=element_tags,
            selected_surface_tags=surface_tags,
            selection_only=True,
        )
        if dlg.exec() != LoadEntryDialog.Accepted:
            return

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        lc = self.project.loads.get(load_tag)
        name = lc.name if lc else f"T{load_tag}"
        self._log(
            f"Charges du cas '{name}' affectées à la sélection "
            f"({len(node_tags)} nœud(s), {len(element_tags)} Élément(s), {len(surface_tags)} surface(s))."
        )

    def _open_eurocode_settings(self) -> None:
        """Open eurocode settings."""
        from gui.dialogs.eurocode_dlg import EurocodeSettingsDialog

        dlg = EurocodeSettingsDialog(self)
        if dlg.exec() == EurocodeSettingsDialog.Accepted:
            self._log("Paramètres Eurocodes mis à jour.")

    def _manage_combinations(self) -> None:
        """Handle manage combinations."""
        self._manage_loads_and_combinations(start_page="combinations")

    def _generate_combinations(self) -> None:
        """Handle generate combinations."""
        self._manage_combinations()

    def _manage_loads_and_combinations(self, *, start_page: str) -> None:
        """Handle manage loads and combinations."""
        from gui.dialogs.combo_dlg import CombinationManagerDialog
        from gui.dialogs.load_dlg import LoadCaseManagerDialog

        self.project.ensure_self_weight_load_case()
        work_project = self.project.copy_for_load_editing()
        page = start_page
        final_message = "Données de chargement mises à jour."

        while True:
            if page == "loads":
                dlg = LoadCaseManagerDialog(
                    self,
                    project=work_project,
                    selected_node_tags=self._selected_existing_node_tags(),
                    selected_element_tags=self._selected_existing_element_tags(),
                    selected_surface_tags=self._selected_existing_surface_tags(),
                )
                if dlg.exec() != LoadCaseManagerDialog.Accepted:
                    return

                work_project.loads = dlg.result_loads()
                work_project.nodal_loads = dlg.result_nodal_loads()
                work_project.element_loads = dlg.result_element_loads()
                work_project.surface_loads = dlg.result_surface_loads()
                if hasattr(dlg, "result_plate_surface_loads"):
                    work_project.plate_surface_loads = dlg.result_plate_surface_loads()
                work_project.combinations = dlg.result_combinations()
                work_project.ensure_self_weight_load_case()

                if dlg.switch_to_combinations_requested():
                    page = "combinations"
                    continue

                final_message = "Cas de charge mis à jour."
                break

            dlg = CombinationManagerDialog(
                self,
                loads=work_project.loads,
                combinations=work_project.combinations,
            )
            if dlg.exec() != CombinationManagerDialog.Accepted:
                return

            work_project.combinations = dlg.result_combinations()

            if dlg.switch_to_load_cases_requested():
                page = "loads"
                continue

            final_message = "Combinaisons mises à jour."
            break

        self.project.loads = work_project.loads
        self.project.nodal_loads = work_project.nodal_loads
        self.project.element_loads = work_project.element_loads
        self.project.surface_loads = work_project.surface_loads
        self.project.plate_surface_loads = work_project.plate_surface_loads
        self.project.combinations = work_project.combinations
        self.project.ensure_self_weight_load_case()

        self._mark_project_modified()
        self._refresh(preserve_view=True)
        self._log(final_message)

    # ── Analyse ──────────────────────────────────────────────────────────

    def _load_tags_with_applied_loads(self) -> set[int]:
        """Load tags with applied loads."""
        from core.self_weight import is_self_weight_load

        nodal_tags = {nl.load_tag for nl in self.project.nodal_loads}
        element_tags = {el.load_tag for el in self.project.element_loads}
        surface_tags = {sl.load_tag for sl in self.project.surface_loads}
        plate_surface_tags = {sl.load_tag for sl in self.project.plate_surface_loads}
        self_weight_tags = {
            tag for tag, load in self.project.loads.items()
            if is_self_weight_load(load)
        }
        return nodal_tags | element_tags | surface_tags | plate_surface_tags | self_weight_tags

    def _has_meaningful_analysis_loading(self) -> bool:
        """Return whether meaningful analysis loading."""
        return bool(self._load_tags_with_applied_loads())

    def _run_analysis(self) -> None:
        """Run analysis."""
        from core.analysis import AnalysisRunner

        # Check the model
        if len(self.project.nodes) < 2 or (
            not self.project.elements
            and not self.project.surface_elements
            and not self.project.plate_regions
        ):
            QMessageBox.warning(self, "Attention", "Le modèle est incomplet.")
            return

        has_supports = any(n.is_fixed for n in self.project.nodes.values())
        if not has_supports:
            QMessageBox.warning(
                self, "Attention",
                "Aucun appui défini. Ajoutez des conditions aux limites.",
            )
            return

        # Analyze ALL cases and combinations
        if not self.project.loads and not self.project.combinations:
            QMessageBox.warning(
                self, "Attention",
                "Aucune charge ni combinaison définie.",
            )
            return
        if not self._has_meaningful_analysis_loading():
            QMessageBox.warning(
                self, "Attention",
                "Aucune charge affectée aux nœuds, aux éléments ou aux surfaces. "
                "Définissez d'abord des charges avant de lancer l'analyse.",
            )
            return
        if (
            self.project.surface_elements or self.project.plate_regions
        ) and not self._surface_features_enabled():
            QMessageBox.warning(
                self,
                "Plaques indisponibles",
                self._surface_features_disabled_reason()
                + "\n\n"
                + "Les éléments surfaciques ne peuvent être calculés qu'avec OpenSeesPy.",
            )
            return

        element_issues = self._element_section_compatibility_issues()
        if element_issues:
            details = "\n".join(
                f"- {message}" for _element_tag, message in element_issues[:6]
            )
            if len(element_issues) > 6:
                details += f"\n- ... et {len(element_issues) - 6} autre(s)."
            QMessageBox.warning(
                self,
                "Barres incompatibles",
                "Certaines barres ne peuvent pas etre calculees :\n\n"
                + details
                + "\n\nCorrigez-les avec une section barre avant de relancer l'analyse.",
            )
            self._log("ERREUR configuration barres : " + element_issues[0][1])
            self._select_element_for_context(element_issues[0][0])
            return

        compatibility_issues = self._surface_section_compatibility_issues()
        if compatibility_issues:
            details = "\n".join(
                f"- {message}" for _surface_tag, message in compatibility_issues[:6]
            )
            if len(compatibility_issues) > 6:
                details += f"\n- ... et {len(compatibility_issues) - 6} autre(s)."
            QMessageBox.warning(
                self,
                "Plaques incompatibles",
                "Certaines plaques ne peuvent pas etre maillees pour le calcul :\n\n"
                + details
                + "\n\nCorrigez-les avec une section plaque/surface avant de relancer l'analyse.",
            )
            self._log("ERREUR configuration plaques : " + compatibility_issues[0][1])
            self._select_surface_after_change(compatibility_issues[0][0])
            return

        self.act_run.setEnabled(False)
        self._log("═══ Analyse statique — tous les cas ═══")

        try:
            runner = AnalysisRunner(
                self.project,
                engine=self.settings.analysis.solver_engine,
            )
            self._runner = runner
            self._log(f"Moteur de calcul : {runner.engine.value}")
            self._refresh_diagram_actions()

            # Rebuild the map (case_name -> (load_tag, combo_tag))
            self._case_tags.clear()
            for tag, lc in self.project.loads.items():
                self._case_tags[f"{lc.name} (cas {tag})"] = (tag, None)
            for tag, combo in self.project.combinations.items():
                self._case_tags[f"{combo.name} (combo {tag})"] = (None, tag)

            def _on_progress(name, idx, total):
                self._log(f"  [{idx + 1}/{total}] {name}...")

            all_raw = runner.run_all(callback=_on_progress)

            # Store successful results
            self._all_results.clear()
            n_ok = 0
            n_fail = 0
            for name, (success, res) in all_raw.items():
                if success:
                    self._all_results[name] = res
                    n_ok += 1
                else:
                    err = res.get("error", "Inconnue")
                    self._log(f"  ERREUR {name} : {err}")
                    n_fail += 1

            self._log(f"═══ Terminé : {n_ok} réussi(s), {n_fail} échoué(s) ═══")
            self._log_analysis_mesh_diagnostic()

            self._refresh_result_actions()

            if self._all_results:
                # Send to the results panel
                self.results_panel.set_all_results(self._all_results)

                # Calculer les enveloppes
                from core.results import compute_envelopes
                self._result_envelopes = compute_envelopes(
                    self._all_results,
                    list(self.project.elements.keys()),
                )
                self.results_panel.set_envelopes(self._result_envelopes)
                if self._results_window is not None:
                    self._results_window.set_all_results(self._all_results)
                    self._results_window.set_envelopes(self._result_envelopes)

                # Select the first case
                self._current_case = next(iter(self._all_results))
                if self._results_window is not None:
                    self._results_window.set_current_case(self._current_case)

                # Switch to the Results tab
                idx = self.tab_bottom.indexOf(self.results_panel)
                if idx >= 0:
                    self.tab_bottom.setCurrentIndex(idx)

                # Display the deformed shape for the first case
                self._show_deformed(self._current_case)
                self._refresh_diagram_actions()
            else:
                self._log("Aucun cas n'a convergé.")
                self._refresh_diagram_actions()

        except Exception as e:
            self._log(f"ERREUR : {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            self.act_run.setEnabled(True)

    def _on_case_changed(self, case_name: str) -> None:
        """Handle case changed."""
        self._current_case = case_name
        sender = self.sender()
        if self.results_panel is not sender and self.results_panel.current_case() != case_name:
            self.results_panel.set_current_case(case_name)
        if (
            self._results_window is not None
            and self._results_window.panel is not sender
            and self._results_window.current_case() != case_name
        ):
            self._results_window.set_current_case(case_name)
        if self._deformed_visible:
            self._show_deformed(case_name)
        # Redisplay the active diagram if needed
        if self._current_diagram:
            self._show_diagram(self._current_diagram)
        if (
            self._element_diagram_window is not None
            and self._element_diagram_window.isVisible()
        ):
            try:
                use_solver_state = (
                    self._runner is not None and bool(self._runner.supports_diagrams)
                )
                if use_solver_state and not self._restore_case_state():
                    self._log(f"Impossible de restaurer l'état pour {case_name}.")
                else:
                    self._render_current_element_diagram()
            except Exception as e:
                self._log(f"Erreur diagramme barre : {e}")
                import traceback
                self._log(traceback.format_exc())
        if (
            self._surface_diagram_window is not None
            and self._surface_diagram_window.isVisible()
        ):
            try:
                self._render_current_surface_result_map()
            except Exception as e:
                self._log(f"Erreur cartes plaques : {e}")
                import traceback
                self._log(traceback.format_exc())

    def _display_primary_model_view(self, preserve_view: bool = True) -> None:
        """Display primary model view."""
        if self.model_view is None:
            return

        primary_view_state = None
        if preserve_view and hasattr(self.model_view, "capture_view_state"):
            primary_view_state = self.model_view.capture_view_state()

        self.model_view._last_support_error = None
        self.model_view.show_node_tags = self.settings.gui.show_node_tags
        self.model_view.show_section_names = self.settings.gui.show_section_names
        self.model_view.show_grid = self.settings.gui.show_grid
        self.model_view.show_extruded_sections = self.settings.gui.show_extruded_sections
        self.model_view.display_model(self.project, preserve_camera=preserve_view)
        self.model_view.set_selection_mode(self._selection_mode_active)
        self.model_view.set_drawing_mode(self._interactive_drawing_enabled())
        if preserve_view and primary_view_state is not None:
            self.model_view.restore_view_state(primary_view_state)
        else:
            self._apply_parallel_view(refresh_scene=False)
        if self._draw_start_point is not None:
            self.model_view.set_preview_start(self._draw_start_point)
        if getattr(self.model_view, "_last_support_error", None):
            self._log(f"Erreur symboles d'appui : {self.model_view._last_support_error}")
        if not preserve_view:
            QTimer.singleShot(50, self._force_render)

    def _display_secondary_model_view(self, preserve_view: bool = True) -> None:
        """Display secondary model view."""
        if getattr(self, "secondary_view", None) is None or not hasattr(self.secondary_view, "display_model"):
            return
        if not self._secondary_view_visible():
            return

        secondary_view_state = None
        if preserve_view and hasattr(self.secondary_view, "capture_view_state"):
            secondary_view_state = self.secondary_view.capture_view_state()

        self.secondary_view._last_support_error = None
        self.secondary_view.show_node_tags = self.settings.gui.show_node_tags
        self.secondary_view.show_section_names = self.settings.gui.show_section_names
        self.secondary_view.show_grid = self.settings.gui.show_grid
        self.secondary_view.show_extruded_sections = self.settings.gui.show_extruded_sections
        self.secondary_view.display_model(self.project, preserve_camera=preserve_view)
        self.secondary_view.set_selection_mode(self._selection_mode_active)
        self.secondary_view.set_drawing_mode(self._interactive_drawing_enabled())
        if preserve_view and secondary_view_state is not None:
            self.secondary_view.restore_view_state(secondary_view_state)
        else:
            self._apply_secondary_parallel_view(refresh_scene=False)
        if self._draw_start_point is not None:
            self.secondary_view.set_preview_start(self._draw_start_point)
        else:
            self.secondary_view.clear_drawing_state()

    def _set_deformed_visible(self, visible: bool) -> None:
        """Set deformed visible."""
        self._deformed_visible = bool(visible)
        self._refresh_deformed_action()

    def _hide_deformed(self, *, preserve_view: bool = True, log_message: bool = True) -> None:
        """Handle hide deformed."""
        self._display_primary_model_view(preserve_view=preserve_view)
        self._set_deformed_visible(False)
        if log_message:
            self._log("Affichage de la déformée desactive.")

    def _show_deformed(
        self,
        case_name: str,
        *,
        preserve_view: bool = True,
        log_message: bool = True,
    ) -> bool:
        """Show deformed."""
        if not self._all_results or case_name not in self._all_results or self.model_view is None:
            self._set_deformed_visible(False)
            return False

        results = self._all_results[case_name]
        disps = results.get("displacements", {})
        if not disps:
            self._hide_deformed(preserve_view=preserve_view, log_message=False)
            return False

        max_disp = max(
            max(abs(r.ux), abs(r.uy), abs(r.uz))
            for r in disps.values()
        ) if disps else 0.0

        if max_disp <= 1e-10:
            self._hide_deformed(preserve_view=preserve_view, log_message=False)
            if log_message:
                self._log(
                    f"[{case_name}] Déplacements nodaux nuls - "
                    "ajoutez des nœuds intermédiaires ou libérez des DDL."
                )
            return False

        import numpy as _np

        pts = [[n.x, n.y, n.z] for n in self.project.nodes.values()]
        if len(pts) >= 2:
            _pts = _np.array(pts)
            model_size = _np.linalg.norm(
                _pts.max(axis=0) - _pts.min(axis=0),
            )
            auto_scale = max(1.0, (model_size * 0.05) / max_disp)
        else:
            auto_scale = 10.0

        primary_view_state = None
        if preserve_view and hasattr(self.model_view, "capture_view_state"):
            primary_view_state = self.model_view.capture_view_state()

        self.model_view.show_grid = self.settings.gui.show_grid
        self.model_view.display_deformed(
            self.project,
            disps,
            scale=auto_scale,
            preserve_camera=preserve_view,
        )
        self.model_view.set_selection_mode(self._selection_mode_active)
        self.model_view.set_drawing_mode(self._interactive_drawing_enabled())
        if preserve_view and primary_view_state is not None:
            self.model_view.restore_view_state(primary_view_state)
        else:
            self._apply_parallel_view(refresh_scene=False)
        if self._draw_start_point is not None:
            self.model_view.set_preview_start(self._draw_start_point)
        self._set_deformed_visible(True)
        if log_message:
            self._log(
                f"Déformée [{case_name}] - depl. max = {max_disp:.6f} m, "
                f"echelle x{auto_scale:.0f}."
            )
        return True

    def _ensure_diagram_window(self) -> None:
        """Ensure diagram window."""
        if self._diagram_window is not None:
            return

        self._diagram_window = DiagramWindow(
            self,
            width=self.settings.gui.diagram_window_width,
            height=self.settings.gui.diagram_window_height,
        )
        if (
            self.settings.gui.diagram_window_x >= 0
            and self.settings.gui.diagram_window_y >= 0
        ):
            self._diagram_window.move(
                self.settings.gui.diagram_window_x,
                self.settings.gui.diagram_window_y,
            )
        self._diagram_window.set_components(
            self._DIAGRAM_COMPONENTS,
            self._current_diagram or self._DIAGRAM_COMPONENTS[0],
        )
        self._diagram_window.file_index_changed.connect(
            self._on_diagram_file_changed
        )
        self._diagram_window.component_changed.connect(
            self._on_diagram_component_changed
        )
        self._diagram_window.case_changed.connect(
            self._on_diagram_case_changed
        )

    def _ensure_surface_diagram_window(self) -> None:
        """Ensure surface diagram window."""
        if self._surface_diagram_window is not None:
            return

        self._surface_diagram_window = DiagramWindow(
            self,
            width=self.settings.gui.diagram_window_width,
            height=self.settings.gui.diagram_window_height,
            window_title="Cartes plaques",
            case_label="Cas / combinaison :",
            component_label="Composante :",
            file_label="Plan :",
            export_basename="plaques",
        )
        if (
            self.settings.gui.diagram_window_x >= 0
            and self.settings.gui.diagram_window_y >= 0
        ):
            self._surface_diagram_window.move(
                self.settings.gui.diagram_window_x,
                self.settings.gui.diagram_window_y,
            )
        self._surface_diagram_window.set_components(
            self._SURFACE_RESULT_COMPONENTS,
            self._current_surface_component or self._SURFACE_RESULT_COMPONENTS[0],
        )
        self._surface_diagram_window.file_index_changed.connect(
            self._on_surface_result_file_changed
        )
        self._surface_diagram_window.component_changed.connect(
            self._on_surface_result_component_changed
        )
        self._surface_diagram_window.case_changed.connect(
            self._on_surface_result_case_changed
        )

    def _restore_case_state(self) -> bool:
        """Restore case state."""
        if self._runner is None or not self._current_case:
            return False
        load_tag, combo_tag = self._case_tags.get(
            self._current_case, (None, None),
        )
        if load_tag is None and combo_tag is None:
            return False
        success, _ = self._runner.run_static(
            load_tag=load_tag, combo_tag=combo_tag,
        )
        return bool(success)

    def _refresh_diagram_files(self) -> None:
        """Refresh diagram files."""
        if self._diagram_window is None:
            return
        from gui.widgets.diagram_renderer import detect_files

        use_opensees_pipeline = (
            self._runner is not None and self._runner.engine == SolverEngine.OPENSEES
        )
        if use_opensees_pipeline:
            self._diagram_files = detect_files()
        else:
            self._diagram_files = detect_files(project=self.project)
        if self._diagram_files:
            self._current_file_idx = min(
                self._current_file_idx,
                len(self._diagram_files) - 1,
            )
        else:
            self._current_file_idx = 0
        self._diagram_window.set_files(
            self._diagram_files,
            self._current_file_idx,
        )

    def _refresh_diagram_cases(self) -> None:
        """Refresh diagram cases."""
        if self._diagram_window is None:
            return
        cases = list(self._all_results.keys())
        if cases and self._current_case not in cases:
            self._current_case = cases[0]
        self._diagram_window.set_cases(cases, self._current_case)

    def _element_diagram_available(self, tag: int) -> bool:
        """Handle element diagram available."""
        return tag in self.project.elements and bool(self._all_results)

    def _surface_diagram_available(self, tag: int) -> bool:
        """Handle surface diagram available."""
        if tag in self.project.plate_regions:
            return any(
                int(tag) in case_results.get("plate_results", {})
                for case_results in self._all_results.values()
            )
        return tag in self.project.surface_elements and any(
            int(tag) in case_results.get("surface_results", {})
            for case_results in self._all_results.values()
        )

    def _single_element_diagram_file_info(self, tag: int) -> dict | None:
        """Handle single element diagram file info."""
        element = self.project.elements.get(tag)
        if element is None:
            return None
        ni = self.project.nodes.get(element.node_i)
        nj = self.project.nodes.get(element.node_j)
        if ni is None or nj is None:
            return None

        return {
            "label": f"E{tag} seul (repère local)",
            "local_element": True,
            "element_tag": tag,
            "plane": None,
            "ele_tags": [tag],
            "axis": None,
            "value": None,
        }

    def _ensure_element_diagram_window(self) -> None:
        """Ensure element diagram window."""
        if self._element_diagram_window is not None:
            return

        self._element_diagram_window = DiagramWindow(
            self,
            width=self.settings.gui.diagram_window_width,
            height=self.settings.gui.diagram_window_height,
            window_title="Diagramme de barre",
            case_label="Cas / combinaison :",
            component_label="Diagramme :",
            file_label="Barre :",
            export_basename="diagramme_barre",
        )
        if (
            self.settings.gui.diagram_window_x >= 0
            and self.settings.gui.diagram_window_y >= 0
        ):
            self._element_diagram_window.move(
                self.settings.gui.diagram_window_x,
                self.settings.gui.diagram_window_y,
            )
        self._element_diagram_window.set_components(
            self._DIAGRAM_COMPONENTS,
            self._current_element_diagram or self._DIAGRAM_COMPONENTS[0],
        )
        self._element_diagram_window.file_index_changed.connect(
            self._on_element_diagram_file_changed
        )
        self._element_diagram_window.component_changed.connect(
            self._on_element_diagram_component_changed
        )
        self._element_diagram_window.case_changed.connect(
            self._on_element_diagram_case_changed
        )

    def _refresh_element_diagram_cases(self) -> None:
        """Refresh element diagram cases."""
        if self._element_diagram_window is None:
            return
        cases = list(self._all_results.keys())
        if cases and self._current_case not in cases:
            self._current_case = cases[0]
        self._element_diagram_window.set_cases(cases, self._current_case)

    def _refresh_element_diagram_files(self) -> None:
        """Refresh element diagram files."""
        if self._element_diagram_window is None:
            return
        file_info = (
            self._single_element_diagram_file_info(self._current_element_diagram_tag)
            if self._current_element_diagram_tag is not None
            else None
        )
        self._element_diagram_files = [file_info] if file_info is not None else []
        self._current_element_file_idx = 0
        self._element_diagram_window.set_files(
            self._element_diagram_files,
            self._current_element_file_idx,
        )

    def _render_current_element_diagram(self) -> None:
        """Render current element diagram."""
        if self._element_diagram_window is None:
            return
        component = self._current_element_diagram or self._DIAGRAM_COMPONENTS[0]
        if not self._element_diagram_files:
            from matplotlib.figure import Figure

            fig = Figure(figsize=(10, 7))
            ax = fig.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                "Aucune barre compatible pour ce diagramme.",
                ha="center",
                va="center",
                fontsize=11,
            )
            ax.axis("off")
            self._element_diagram_window.set_figure(
                fig,
                component=component,
                case_name=self._current_case,
                file_label="Aucune barre compatible",
            )
            return

        from gui.widgets.diagram_renderer import build_figure_2d

        file_info = self._element_diagram_files[0]
        use_opensees_pipeline = (
            self._runner is not None and self._runner.engine == SolverEngine.OPENSEES
        )
        if use_opensees_pipeline:
            fig = build_figure_2d(
                component,
                file_info,
                project=self.project,
            )
        else:
            case_results = self._all_results.get(self._current_case or "")
            load_tag, combo_tag = self._case_tags.get(
                self._current_case or "",
                (None, None),
            )
            fig = build_figure_2d(
                component,
                file_info,
                project=self.project,
                backend=(self._runner.backend if self._runner is not None else None),
                results=case_results,
                load_tag=load_tag,
                combo_tag=combo_tag,
            )
        self._element_diagram_window.set_figure(
            fig,
            component=component,
            case_name=self._current_case,
            file_label=file_info["label"],
        )

    def _on_element_diagram_file_changed(self, idx: int) -> None:
        """Handle element diagram file changed."""
        if idx < 0 or idx >= len(self._element_diagram_files):
            return
        self._current_element_file_idx = idx
        try:
            self._render_current_element_diagram()
        except Exception as e:
            self._log(f"Erreur diagramme barre : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_element_diagram_component_changed(self, component: str) -> None:
        """Handle element diagram component changed."""
        if not component or component == self._current_element_diagram:
            return
        self._current_element_diagram = component
        try:
            self._render_current_element_diagram()
        except Exception as e:
            self._log(f"Erreur diagramme barre : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_element_diagram_case_changed(self, case_name: str) -> None:
        """Handle element diagram case changed."""
        if not case_name or case_name not in self._all_results:
            return
        if case_name == self._current_case:
            return

        self._current_case = case_name
        if self.results_panel.current_case() != case_name:
            self.results_panel.set_current_case(case_name)
        if (
            self._results_window is not None
            and self._results_window.current_case() != case_name
        ):
            self._results_window.set_current_case(case_name)
        if self._deformed_visible:
            self._show_deformed(case_name)
        try:
            use_solver_state = (
                self._runner is not None and bool(self._runner.supports_diagrams)
            )
            if use_solver_state and not self._restore_case_state():
                self._log(f"Impossible de restaurer l'état pour {case_name}.")
                return
            self._render_current_element_diagram()
        except Exception as e:
            self._log(f"Erreur diagramme barre : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _show_element_diagram(self, tag: int, component: str | None = None) -> None:
        """Show element diagram."""
        if not self._element_diagram_available(tag):
            QMessageBox.information(
                self,
                "Diagrammes",
                "Aucun résultat disponible.\nLancez d'abord une analyse (F5).",
            )
            return

        self._current_element_diagram_tag = int(tag)
        self._current_element_diagram = (
            component
            or self._current_element_diagram
            or self._DIAGRAM_COMPONENTS[0]
        )
        if self._current_case not in self._all_results:
            self._current_case = next(iter(self._all_results))

        use_opensees_pipeline = (
            self._runner is not None and bool(self._runner.supports_diagrams)
        )
        try:
            if use_opensees_pipeline and not self._restore_case_state():
                self._log(
                    f"Impossible de restaurer l'état pour {self._current_case}."
                )
                return
            self._ensure_element_diagram_window()
            self._refresh_element_diagram_cases()
            self._element_diagram_window.set_components(
                self._DIAGRAM_COMPONENTS,
                self._current_element_diagram,
            )
            self._refresh_element_diagram_files()
            self._render_current_element_diagram()

            self._element_diagram_window.show()
            self._element_diagram_window.raise_()
            self._element_diagram_window.activateWindow()

            self._log(
                f"Diagramme {self._current_element_diagram} de E{tag} [{self._current_case}]."
            )
        except Exception as e:
            self._log(f"Erreur diagramme barre : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _refresh_surface_result_cases(self) -> None:
        """Refresh surface result cases."""
        if self._surface_diagram_window is None:
            return
        cases = list(self._all_results.keys())
        if cases and self._current_case not in cases:
            self._current_case = cases[0]
        self._surface_diagram_window.set_cases(cases, self._current_case)

    def _render_current_diagram(self) -> None:
        """Render current diagram."""
        if not self._current_diagram:
            return
        if not self._diagram_files:
            from matplotlib.figure import Figure

            fig = Figure(figsize=(10, 7))
            ax = fig.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                "Aucune vue de diagramme compatible.\n\n"
                "Les diagrammes actuels sont limites aux plans verticaux XZ et YZ.",
                ha="center",
                va="center",
                fontsize=11,
            )
            ax.axis("off")
            self._diagram_window.set_figure(
                fig,
                component=self._current_diagram,
                case_name=self._current_case,
                file_label="Aucune vue compatible",
            )
            return

        from gui.widgets.diagram_renderer import build_figure_2d

        idx = max(0, min(self._current_file_idx, len(self._diagram_files) - 1))
        file_info = self._diagram_files[idx]
        use_opensees_pipeline = (
            self._runner is not None and self._runner.engine == SolverEngine.OPENSEES
        )

        if use_opensees_pipeline:
            fig = build_figure_2d(
                self._current_diagram,
                file_info,
                project=self.project,
            )
        else:
            case_results = self._all_results.get(self._current_case or "")
            load_tag, combo_tag = self._case_tags.get(
                self._current_case or "",
                (None, None),
            )
            fig = build_figure_2d(
                self._current_diagram,
                file_info,
                project=self.project,
                backend=(self._runner.backend if self._runner is not None else None),
                results=case_results,
                load_tag=load_tag,
                combo_tag=combo_tag,
            )
        self._diagram_window.set_figure(
            fig,
            component=self._current_diagram,
            case_name=self._current_case,
            file_label=file_info["label"],
        )

    def _refresh_surface_result_files(self) -> None:
        """Refresh surface result files."""
        if self._surface_diagram_window is None:
            return
        from gui.widgets.surface_result_renderer import (
            detect_plate_result_files,
            detect_surface_result_views,
            surface_result_file_for_surface,
        )

        case_results = self._current_surface_result_case_results()
        render_project = self._surface_result_project_for_results(case_results)
        surface_tag = getattr(self, "_current_surface_result_tag", None)
        if surface_tag is not None:
            if int(surface_tag) in getattr(render_project, "plate_regions", {}):
                file_info = next(
                    (
                        item for item in detect_plate_result_files(render_project)
                        if int(item.get("plate_tag", -1)) == int(surface_tag)
                    ),
                    None,
                )
            else:
                file_info = surface_result_file_for_surface(render_project, int(surface_tag))
            self._surface_result_files = [file_info] if file_info is not None else []
        else:
            self._surface_result_files = detect_surface_result_views(render_project)
        if self._surface_result_files:
            self._current_surface_file_idx = min(
                self._current_surface_file_idx,
                len(self._surface_result_files) - 1,
            )
        else:
            self._current_surface_file_idx = 0
        self._surface_diagram_window.set_files(
            self._surface_result_files,
            self._current_surface_file_idx,
        )

    def _render_current_surface_result_map(self) -> None:
        """Render current surface result map."""
        if self._surface_diagram_window is None:
            return

        from gui.widgets.surface_result_renderer import build_surface_result_figure

        case_name = self._current_case or next(iter(self._all_results), None)
        if case_name is None:
            return
        component = (
            self._current_surface_component or self._SURFACE_RESULT_COMPONENTS[0]
        )
        file_info = None
        file_label = "Aucune vue compatible"
        if self._surface_result_files:
            idx = max(
                0,
                min(
                    self._current_surface_file_idx,
                    len(self._surface_result_files) - 1,
                ),
            )
            file_info = self._surface_result_files[idx]
            file_label = file_info["label"]
        case_results = self._all_results.get(case_name, {})
        render_project = self._surface_result_project_for_results(case_results)
        fig = build_surface_result_figure(
            component,
            file_info,
            render_project,
            case_results,
        )
        self._surface_diagram_window.set_figure(
            fig,
            component=component,
            case_name=case_name,
            file_label=file_label,
        )

    def _on_diagram_file_changed(self, idx: int) -> None:
        """Handle diagram file changed."""
        if idx < 0 or idx >= len(self._diagram_files):
            return
        self._current_file_idx = idx
        # Rerender without rerunning the analysis (the domain is still active)
        try:
            self._render_current_diagram()
        except Exception as e:
            self._log(f"Erreur diagramme : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_diagram_component_changed(self, component: str) -> None:
        """Handle diagram component changed."""
        if not component or component == self._current_diagram:
            return
        self._show_diagram(component)

    def _on_diagram_case_changed(self, case_name: str) -> None:
        """Handle diagram case changed."""
        if not case_name or case_name not in self._all_results:
            return
        if case_name == self._current_case:
            return

        self._current_case = case_name
        if self._deformed_visible:
            self._show_deformed(case_name)
        if not self._current_diagram:
            return

        try:
            use_solver_state = (
                self._runner is not None and bool(self._runner.supports_diagrams)
            )
            if use_solver_state and not self._restore_case_state():
                self._log(f"Impossible de restaurer l'état pour {case_name}.")
                return
            self._render_current_diagram()
            self._log(f"Diagramme {self._current_diagram} [{case_name}].")
        except Exception as e:
            self._log(f"Erreur diagramme : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_surface_result_file_changed(self, idx: int) -> None:
        """Handle surface result file changed."""
        if idx < 0 or idx >= len(self._surface_result_files):
            return
        self._current_surface_file_idx = idx
        try:
            self._render_current_surface_result_map()
        except Exception as e:
            self._log(f"Erreur cartes plaques : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_surface_result_component_changed(self, component: str) -> None:
        """Handle surface result component changed."""
        if not component or component == self._current_surface_component:
            return
        self._current_surface_component = component
        try:
            self._render_current_surface_result_map()
        except Exception as e:
            self._log(f"Erreur cartes plaques : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_surface_result_case_changed(self, case_name: str) -> None:
        """Handle surface result case changed."""
        if not case_name or case_name not in self._all_results:
            return
        if case_name == self._current_case:
            return

        self._current_case = case_name
        if self.results_panel.current_case() != case_name:
            self.results_panel.set_current_case(case_name)
        if (
            self._results_window is not None
            and self._results_window.current_case() != case_name
        ):
            self._results_window.set_current_case(case_name)
        if self._deformed_visible:
            self._show_deformed(case_name)
        if self._current_diagram:
            self._show_diagram(self._current_diagram)
        try:
            self._render_current_surface_result_map()
        except Exception as e:
            self._log(f"Erreur cartes plaques : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _show_diagram(self, component: str) -> None:
        """Show diagram."""
        self._current_diagram = component
        if not self._current_case or not self._all_results:
            return
        use_opensees_pipeline = (
            self._runner is not None and bool(self._runner.supports_diagrams)
        )
        try:
            if use_opensees_pipeline and not self._restore_case_state():
                self._log(
                    f"Impossible de restaurer l'état pour {self._current_case}."
                )
                return
            self._ensure_diagram_window()
            self._refresh_diagram_cases()
            self._diagram_window.set_components(
                self._DIAGRAM_COMPONENTS,
                component,
            )
            self._refresh_diagram_files()
            self._render_current_diagram()

            self._diagram_window.show()
            self._diagram_window.raise_()
            self._diagram_window.activateWindow()

            self._log(f"Diagramme {component} [{self._current_case}].")
            return
        except Exception as e:
            self._log(f"Erreur diagramme : {e}")
            import traceback
            self._log(traceback.format_exc())
            return
        if self._runner is None:
            self._log("Aucune analyse disponible pour les diagrammes.")
            return
        if not self._runner.supports_diagrams:
            self._log(
                "Les diagrammes détaillés sont actuellement disponibles "
                "uniquement avec le moteur OpenSeesPy."
            )
            return

        try:
            if not self._restore_case_state():
                self._log(
                    f"Impossible de restaurer l'état pour {self._current_case}."
                )
                return

            self._ensure_diagram_window()
            self._refresh_diagram_cases()
            self._diagram_window.set_components(
                self._DIAGRAM_COMPONENTS,
                component,
            )
            self._refresh_diagram_files()
            self._render_current_diagram()

            self._diagram_window.show()
            self._diagram_window.raise_()
            self._diagram_window.activateWindow()

            self._log(f"Diagramme {component} [{self._current_case}].")
        except Exception as e:
            self._log(f"Erreur diagramme : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _clear_diagrams(self) -> None:
        """Clear diagrams."""
        self._current_diagram = None
        self._current_element_diagram = None
        self._current_surface_result_tag = None
        if self._diagram_window is not None:
            self._diagram_window.hide()
        if self._element_diagram_window is not None:
            self._element_diagram_window.hide()

    def _show_surface_result_map(
        self,
        component: str | None = None,
        surface_tag: int | None = None,
    ) -> None:
        """Show surface result map."""
        if not self._all_results:
            QMessageBox.information(
                self,
                "Résultats plaques",
                "Aucun résultat disponible.\nLancez d'abord une analyse (F5).",
            )
            return
        if not self._has_surface_results():
            QMessageBox.information(
                self,
                "Résultats plaques",
                "Aucun résultat plaque exploitable n'est disponible pour le cas courant.",
            )
            return

        self._current_surface_result_tag = (
            int(surface_tag) if surface_tag is not None else None
        )
        if self._current_surface_result_tag is not None:
            matching_case = next(
                (
                    case_name
                    for case_name, case_results in self._all_results.items()
                    if (
                        self._current_surface_result_tag
                        in case_results.get("surface_results", {})
                        or self._current_surface_result_tag
                        in case_results.get("plate_results", {})
                    )
                ),
                None,
            )
            if matching_case is None:
                QMessageBox.information(
                    self,
                    "Résultats plaques",
                    "Aucun résultat exploitable n'est disponible pour "
                    f"la surface S{self._current_surface_result_tag}.",
                )
                return
            if (
                self._current_case not in self._all_results
                or self._current_surface_result_tag
                not in self._all_results[self._current_case].get("surface_results", {})
                and self._current_surface_result_tag
                not in self._all_results[self._current_case].get("plate_results", {})
            ):
                self._current_case = matching_case

        self._current_surface_component = (
            component
            or self._current_surface_component
            or self._SURFACE_RESULT_COMPONENTS[0]
        )
        try:
            self._ensure_surface_diagram_window()
            self._refresh_surface_result_cases()
            self._surface_diagram_window.set_components(
                self._SURFACE_RESULT_COMPONENTS,
                self._current_surface_component,
            )
            self._refresh_surface_result_files()
            self._render_current_surface_result_map()

            self._surface_diagram_window.show()
            self._surface_diagram_window.raise_()
            self._surface_diagram_window.activateWindow()

            self._log(
                f"Carte plaque {self._current_surface_component} [{self._current_case}]."
            )
        except Exception as e:
            self._log(f"Erreur cartes plaques : {e}")
            import traceback
            self._log(traceback.format_exc())

    # -- Results menu ---------------------------------------------------------

    def _current_load_case_label(self) -> str | None:
        """Return load case label."""
        for label, tag in self._load_case_labels.items():
            if tag == self._current_load_case_tag:
                return label
        return None

    def _ensure_load_diagram_window(self) -> None:
        """Ensure load diagram window."""
        if self._load_diagram_window is not None:
            return

        self._load_diagram_window = DiagramWindow(
            self,
            width=self.settings.gui.diagram_window_width,
            height=self.settings.gui.diagram_window_height,
            window_title="Charges affectées",
            case_label="Cas de charge :",
            component_label="Affichage :",
            file_label="File / plan :",
            export_basename="charges",
        )
        if (
            self.settings.gui.diagram_window_x >= 0
            and self.settings.gui.diagram_window_y >= 0
        ):
            self._load_diagram_window.move(
                self.settings.gui.diagram_window_x,
                self.settings.gui.diagram_window_y,
            )
        self._load_diagram_window.set_components(["Charges"], "Charges")
        self._load_diagram_window.file_index_changed.connect(
            self._on_load_diagram_file_changed
        )
        self._load_diagram_window.case_changed.connect(
            self._on_load_diagram_case_changed
        )

    def _refresh_load_diagram_cases(self) -> None:
        """Refresh load diagram cases."""
        if self._load_diagram_window is None:
            return

        self._load_case_labels = {
            f"{load.name} (T{tag})": tag
            for tag, load in sorted(self.project.loads.items())
        }
        labels = list(self._load_case_labels.keys())
        if labels and self._current_load_case_tag not in self.project.loads:
            self._current_load_case_tag = self._load_case_labels[labels[0]]
        if not labels:
            self._current_load_case_tag = None
        self._load_diagram_window.set_cases(
            labels,
            self._current_load_case_label(),
        )

    def _refresh_load_diagram_files(self) -> None:
        """Refresh load diagram files."""
        if self._load_diagram_window is None:
            return
        from gui.widgets.diagram_renderer import detect_load_files

        self._load_diagram_files = detect_load_files(self.project)
        if self._load_diagram_files:
            self._current_load_file_idx = min(
                self._current_load_file_idx,
                len(self._load_diagram_files) - 1,
            )
        else:
            self._current_load_file_idx = 0
        self._load_diagram_window.set_files(
            self._load_diagram_files,
            self._current_load_file_idx,
        )

    def _render_current_load_diagram(self) -> None:
        """Render current load diagram."""
        if self._load_diagram_window is None:
            return
        from gui.widgets.diagram_renderer import build_load_figure_2d

        file_info = None
        file_label = "Aucune vue compatible"
        if self._load_diagram_files:
            idx = max(
                0,
                min(self._current_load_file_idx, len(self._load_diagram_files) - 1),
            )
            file_info = self._load_diagram_files[idx]
            file_label = file_info["label"]

        fig = build_load_figure_2d(
            file_info,
            self.project,
            self._current_load_case_tag,
            self.settings.display_units,
        )
        self._load_diagram_window.set_figure(
            fig,
            component="Charges",
            case_name=self._current_load_case_label(),
            file_label=file_label,
        )

    def _on_load_diagram_file_changed(self, idx: int) -> None:
        """Handle load diagram file changed."""
        if idx < 0 or idx >= len(self._load_diagram_files):
            return
        self._current_load_file_idx = idx
        try:
            self._render_current_load_diagram()
        except Exception as e:
            self._log(f"Erreur affichage charges : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _on_load_diagram_case_changed(self, case_label: str) -> None:
        """Handle load diagram case changed."""
        tag = self._load_case_labels.get(case_label)
        if tag is None or tag == self._current_load_case_tag:
            return
        self._current_load_case_tag = tag
        try:
            self._render_current_load_diagram()
            self._log(f"Charges [{case_label}].")
        except Exception as e:
            self._log(f"Erreur affichage charges : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _refresh_element_diagram_if_open(self) -> None:
        """Refresh element diagram if open."""
        if (
            self._element_diagram_window is None
            or not self._element_diagram_window.isVisible()
        ):
            return
        if (
            self._current_element_diagram_tag is None
            or self._current_element_diagram_tag not in self.project.elements
        ):
            self._element_diagram_window.hide()
            self._current_element_diagram_tag = None
            self._element_diagram_files = []
            return
        self._refresh_element_diagram_cases()
        self._refresh_element_diagram_files()
        self._render_current_element_diagram()

    def _refresh_load_diagram_if_open(self) -> None:
        """Refresh load diagram if open."""
        if self._load_diagram_window is None or not self._load_diagram_window.isVisible():
            return
        self._refresh_load_diagram_cases()
        self._refresh_load_diagram_files()
        self._render_current_load_diagram()

    def _show_load_diagram(self) -> None:
        """Show load diagram."""
        if not self.project.loads:
            QMessageBox.information(
                self,
                "Charges",
                "Aucun cas de charge n'est disponible.",
            )
            return

        if self._current_load_case_tag not in self.project.loads:
            self._current_load_case_tag = sorted(self.project.loads.keys())[0]

        try:
            self._ensure_load_diagram_window()
            self._refresh_load_diagram_cases()
            self._refresh_load_diagram_files()
            self._render_current_load_diagram()

            self._load_diagram_window.show()
            self._load_diagram_window.raise_()
            self._load_diagram_window.activateWindow()

            label = self._current_load_case_label() or "cas de charge"
            self._log(f"Affichage des charges [{label}].")
        except Exception as e:
            self._log(f"Erreur affichage charges : {e}")
            import traceback
            self._log(traceback.format_exc())

    def _ensure_results_window(self) -> ResultsTableWindow:
        """Create the detached results window on first use."""
        if self._results_window is None:
            self._results_window = ResultsTableWindow(self)
            self._results_window.panel.case_changed.connect(self._on_case_changed)
        return self._results_window

    def _show_result_table(self, result_type: str) -> None:
        """Show result table."""
        if not self._all_results:
            QMessageBox.information(
                self, "Résultats",
                "Aucun résultat disponible.\nLancez d'abord une analyse (F5).",
            )
            return

        # Switch to the Results tab in the dock
        window = self._ensure_results_window()
        window.set_all_results(self._all_results)
        window.set_envelopes(self._result_envelopes)
        if self._current_case:
            window.set_current_case(self._current_case)
        window.show_result_type(result_type)
        window.show()
        window.raise_()
        window.activateWindow()

    def _show_deformed_menu(self) -> None:
        """Show deformed menu."""
        if getattr(self, "act_res_deformed", None) is None:
            return
        if not self.act_res_deformed.isChecked():
            self._hide_deformed()
            return
        if not self._all_results:
            QMessageBox.information(
                self, "Résultats",
                "Aucun résultat disponible.\nLancez d'abord une analyse (F5).",
            )
            self._set_deformed_visible(False)
            return
        case = self._current_case or next(iter(self._all_results))
        self._show_deformed(case)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _setup_parallel_view_controls(self) -> None:
        """Set up parallel view controls."""
        if self.model_view is None or not hasattr(self, "_view_controls_layout"):
            return

        bar = self._view_controls_layout

        self.lbl_plane = QLabel("Vue A :", self._view_controls_widget)
        self.combo_plane = QComboBox(self._view_controls_widget)
        self.combo_plane.addItems(["3D", "XY", "XZ", "YZ"])
        self.combo_plane.currentTextChanged.connect(self._on_parallel_plane_changed)

        self.lbl_file = QLabel("Z =", self._view_controls_widget)
        self.btn_prev_parallel = QPushButton("<", self._view_controls_widget)
        self.btn_prev_parallel.setFixedWidth(32)
        self.btn_prev_parallel.clicked.connect(lambda: self._step_parallel_value(-1))
        self.combo_parallel_value = QComboBox(self._view_controls_widget)
        self.combo_parallel_value.setMinimumWidth(140)
        self.combo_parallel_value.currentIndexChanged.connect(
            self._on_parallel_value_changed
        )
        self.btn_next_parallel = QPushButton(">", self._view_controls_widget)
        self.btn_next_parallel.setFixedWidth(32)
        self.btn_next_parallel.clicked.connect(lambda: self._step_parallel_value(1))

        self.lbl_draw_section = QLabel("Section :", self._view_controls_widget)
        self.combo_draw_section = QComboBox(self._view_controls_widget)
        self.combo_draw_section.setMinimumWidth(180)
        self.lbl_draw_section.hide()
        self.combo_draw_section.hide()

        self.lbl_secondary_plane = QLabel("Vue B :", self._view_controls_widget)
        self.combo_secondary_plane = QComboBox(self._view_controls_widget)
        self.combo_secondary_plane.addItems(["3D", "XY", "XZ", "YZ"])
        self.combo_secondary_plane.setCurrentText("3D")
        self.combo_secondary_plane.currentTextChanged.connect(
            self._on_secondary_parallel_plane_changed
        )

        self.lbl_secondary_file = QLabel("Z =", self._view_controls_widget)
        self.btn_prev_secondary_parallel = QPushButton("<", self._view_controls_widget)
        self.btn_prev_secondary_parallel.setFixedWidth(32)
        self.btn_prev_secondary_parallel.clicked.connect(
            lambda: self._step_secondary_parallel_value(-1)
        )
        self.combo_secondary_value = QComboBox(self._view_controls_widget)
        self.combo_secondary_value.setMinimumWidth(140)
        self.combo_secondary_value.currentIndexChanged.connect(
            self._on_secondary_parallel_value_changed
        )
        self.btn_next_secondary_parallel = QPushButton(">", self._view_controls_widget)
        self.btn_next_secondary_parallel.setFixedWidth(32)
        self.btn_next_secondary_parallel.clicked.connect(
            lambda: self._step_secondary_parallel_value(1)
        )

        self.btn_undo_history = QPushButton("Annuler", self._view_controls_widget)
        self.btn_undo_history.clicked.connect(self._undo_last_action)
        self.btn_redo_history = QPushButton("Rétablir", self._view_controls_widget)
        self.btn_redo_history.clicked.connect(self._redo_last_action)
        self.btn_copy_selection = QPushButton("Copier", self._view_controls_widget)
        self.btn_copy_selection.clicked.connect(self._copy_selected_objects)
        self.btn_copy_selection.setEnabled(False)

        spacer = QWidget(self._view_controls_widget)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        bar.addWidget(self.lbl_plane)
        bar.addWidget(self.combo_plane)
        bar.addWidget(self.lbl_file)
        bar.addWidget(self.btn_prev_parallel)
        bar.addWidget(self.combo_parallel_value)
        bar.addWidget(self.btn_next_parallel)
        bar.addSpacing(16)
        bar.addWidget(self.lbl_draw_section)
        bar.addWidget(self.combo_draw_section)
        bar.addSpacing(16)
        bar.addWidget(self.btn_undo_history)
        bar.addWidget(self.btn_redo_history)
        bar.addWidget(self.btn_copy_selection)
        bar.addWidget(spacer)
        bar.addWidget(self.lbl_secondary_plane)
        bar.addWidget(self.combo_secondary_plane)
        bar.addWidget(self.lbl_secondary_file)
        bar.addWidget(self.btn_prev_secondary_parallel)
        bar.addWidget(self.combo_secondary_value)
        bar.addWidget(self.btn_next_secondary_parallel)

        self._refresh_draw_section_controls()
        self._refresh_parallel_view_controls(apply_view=False)
        self._update_history_actions()

    @staticmethod
    def _plane_grid_axis(plane: str) -> str | None:
        """Handle plane grid axis."""
        return {
            "XY": "Z",
            "XZ": "Y",
            "YZ": "X",
        }.get(plane)

    def _plane_grid_entries(self, plane: str) -> list:
        """Handle plane grid entries."""
        axis = self._plane_grid_axis(plane)
        if axis is None:
            return []
        return self.project.grid.axis_entries(axis)

    @staticmethod
    def _format_grid_plane_entry(marker: str, coordinate: float) -> str:
        """Format grid plane entry."""
        coordinate_text = f"{coordinate:.2f}".replace(".", ",")
        clean_marker = marker.strip()
        if clean_marker:
            return f"{clean_marker} - {coordinate_text} m"
        return f"{coordinate_text} m"

    def _refresh_parallel_view_controls(self, apply_view: bool = True) -> None:
        """Refresh parallel view controls."""
        if self.model_view is None or not hasattr(self, "combo_plane"):
            return

        plane = self.combo_plane.currentText() or "3D"
        if plane == "3D":
            self.lbl_file.setText("File =")
            self.combo_parallel_value.blockSignals(True)
            self.combo_parallel_value.clear()
            self.combo_parallel_value.blockSignals(False)
            self.combo_parallel_value.setEnabled(False)
            self.btn_prev_parallel.setEnabled(False)
            self.btn_next_parallel.setEnabled(False)
            self._active_parallel_plane = "3D"
            self._active_parallel_value = None
            if apply_view:
                self._apply_parallel_view()
            self._refresh_secondary_parallel_controls(apply_view=apply_view)
            return

        axis_label = self.model_view.plane_axis_label(plane)
        self.lbl_file.setText(f"{axis_label} =")

        entries = self._plane_grid_entries(plane)
        values = [entry.coordinate for entry in entries]
        self.combo_parallel_value.blockSignals(True)
        self.combo_parallel_value.clear()
        for entry in entries:
            self.combo_parallel_value.addItem(
                self._format_grid_plane_entry(entry.marker, entry.coordinate),
                entry.coordinate,
            )
        self.combo_parallel_value.blockSignals(False)
        self.combo_parallel_value.setEnabled(bool(values))

        if not values:
            self._active_parallel_plane = plane
            self._active_parallel_value = None
            self.btn_prev_parallel.setEnabled(False)
            self.btn_next_parallel.setEnabled(False)
            self._refresh_secondary_parallel_controls(apply_view=apply_view)
            return

        target_idx = 0
        if self._active_parallel_plane == plane and self._active_parallel_value is not None:
            for idx, value in enumerate(values):
                if abs(value - self._active_parallel_value) <= 1e-9:
                    target_idx = idx
                    break

        self.combo_parallel_value.setCurrentIndex(target_idx)
        self._active_parallel_plane = plane
        self._active_parallel_value = float(values[target_idx])
        self.btn_prev_parallel.setEnabled(target_idx > 0)
        self.btn_next_parallel.setEnabled(target_idx < len(values) - 1)
        if apply_view:
            self._apply_parallel_view()
        self._refresh_secondary_parallel_controls(apply_view=apply_view)

    def _on_parallel_plane_changed(self, plane: str) -> None:
        """Handle parallel plane changed."""
        self._active_parallel_plane = plane
        self._active_parallel_value = None
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._refresh_parallel_view_controls(apply_view=True)

    def _on_parallel_value_changed(self, idx: int) -> None:
        """Handle parallel value changed."""
        if idx < 0 or not hasattr(self, "combo_parallel_value"):
            return
        value = self.combo_parallel_value.itemData(idx)
        if value is None:
            return
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._active_parallel_value = float(value)
        self.btn_prev_parallel.setEnabled(idx > 0)
        self.btn_next_parallel.setEnabled(idx < self.combo_parallel_value.count() - 1)
        self._apply_parallel_view()

    def _step_parallel_value(self, delta: int) -> None:
        """Handle step parallel value."""
        count = self.combo_parallel_value.count() if hasattr(self, "combo_parallel_value") else 0
        if count <= 0:
            return
        current = max(self.combo_parallel_value.currentIndex(), 0)
        new_index = max(0, min(count - 1, current + delta))
        if new_index != current:
            self.combo_parallel_value.setCurrentIndex(new_index)

    def _refresh_secondary_parallel_controls(self, apply_view: bool = True) -> None:
        """Refresh secondary parallel controls."""
        if self.model_view is None or not hasattr(self, "combo_secondary_plane"):
            return

        plane = self.combo_secondary_plane.currentText() or "3D"
        if plane == "3D":
            self.lbl_secondary_file.setText("File =")
            self.combo_secondary_value.blockSignals(True)
            self.combo_secondary_value.clear()
            self.combo_secondary_value.blockSignals(False)
            self.combo_secondary_value.setEnabled(False)
            self.btn_prev_secondary_parallel.setEnabled(False)
            self.btn_next_secondary_parallel.setEnabled(False)
            self._secondary_parallel_plane = "3D"
            self._secondary_parallel_value = None
            if apply_view:
                self._apply_secondary_parallel_view()
            return

        axis_label = self.model_view.plane_axis_label(plane)
        self.lbl_secondary_file.setText(f"{axis_label} =")

        entries = self._plane_grid_entries(plane)
        values = [entry.coordinate for entry in entries]
        self.combo_secondary_value.blockSignals(True)
        self.combo_secondary_value.clear()
        for entry in entries:
            self.combo_secondary_value.addItem(
                self._format_grid_plane_entry(entry.marker, entry.coordinate),
                entry.coordinate,
            )
        self.combo_secondary_value.blockSignals(False)
        self.combo_secondary_value.setEnabled(bool(values))

        if not values:
            self._secondary_parallel_plane = plane
            self._secondary_parallel_value = None
            self.btn_prev_secondary_parallel.setEnabled(False)
            self.btn_next_secondary_parallel.setEnabled(False)
            if apply_view:
                self._apply_secondary_parallel_view()
            return

        target_idx = 0
        if self._secondary_parallel_plane == plane and self._secondary_parallel_value is not None:
            for idx, value in enumerate(values):
                if abs(value - self._secondary_parallel_value) <= 1e-9:
                    target_idx = idx
                    break

        self.combo_secondary_value.setCurrentIndex(target_idx)
        self._secondary_parallel_plane = plane
        self._secondary_parallel_value = float(values[target_idx])
        self.btn_prev_secondary_parallel.setEnabled(target_idx > 0)
        self.btn_next_secondary_parallel.setEnabled(target_idx < len(values) - 1)
        if apply_view:
            self._apply_secondary_parallel_view()

    def _apply_secondary_parallel_view(self, refresh_scene: bool = True) -> None:
        """Apply secondary parallel view."""
        if getattr(self, "secondary_view", None) is None or not hasattr(self.secondary_view, "set_parallel_plane"):
            return
        if self._secondary_parallel_plane == "3D" or self._secondary_parallel_value is None:
            self.secondary_view.set_parallel_plane(None, None, refresh_scene=refresh_scene)
            return
        self.secondary_view.set_parallel_plane(
            self._secondary_parallel_plane,
            self._secondary_parallel_value,
            refresh_scene=refresh_scene,
        )

    def _on_secondary_parallel_plane_changed(self, plane: str) -> None:
        """Handle secondary parallel plane changed."""
        self._secondary_parallel_plane = plane
        self._secondary_parallel_value = None
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._refresh_secondary_parallel_controls(apply_view=True)

    def _on_secondary_parallel_value_changed(self, idx: int) -> None:
        """Handle secondary parallel value changed."""
        if idx < 0 or not hasattr(self, "combo_secondary_value"):
            return
        value = self.combo_secondary_value.itemData(idx)
        if value is None:
            return
        if self._draw_start_point is not None:
            self._cancel_bar_drawing()
        self._secondary_parallel_value = float(value)
        self.btn_prev_secondary_parallel.setEnabled(idx > 0)
        self.btn_next_secondary_parallel.setEnabled(idx < self.combo_secondary_value.count() - 1)
        self._apply_secondary_parallel_view()

    def _step_secondary_parallel_value(self, delta: int) -> None:
        """Handle step secondary parallel value."""
        count = self.combo_secondary_value.count() if hasattr(self, "combo_secondary_value") else 0
        if count <= 0:
            return
        current = max(self.combo_secondary_value.currentIndex(), 0)
        new_index = max(0, min(count - 1, current + delta))
        if new_index != current:
            self.combo_secondary_value.setCurrentIndex(new_index)

    def _toggle_split_view(self, enabled: bool) -> None:
        """Toggle split view."""
        if getattr(self, "secondary_view", None) is not None:
            self.secondary_view.setVisible(enabled)
        if getattr(self, "_view_splitter", None) is not None:
            self._view_splitter.handle(1).setEnabled(enabled)
            if enabled:
                self._view_splitter.setSizes([1, 1])
            else:
                self._view_splitter.setSizes([1, 0])

        for name in (
            "lbl_secondary_plane",
            "combo_secondary_plane",
            "lbl_secondary_file",
            "btn_prev_secondary_parallel",
            "combo_secondary_value",
            "btn_next_secondary_parallel",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(enabled)

        if enabled:
            self._display_secondary_model_view(preserve_view=True)

    def _set_primary_view_plane(self, plane: str) -> None:
        """Set primary view plane."""
        if self.model_view is None or not hasattr(self, "combo_plane"):
            return
        self.combo_plane.blockSignals(True)
        self.combo_plane.setCurrentText(plane)
        self.combo_plane.blockSignals(False)
        self._active_parallel_plane = plane
        if plane == "3D":
            self._active_parallel_value = None
        self._refresh_parallel_view_controls(apply_view=True)

    def _recommended_grid_plane(self) -> str | None:
        """Handle recommended grid plane."""
        grid = self.project.grid
        zero_axes = []
        if grid.count_x == 0:
            zero_axes.append("X")
        if grid.count_y == 0:
            zero_axes.append("Y")
        if grid.count_z == 0:
            zero_axes.append("Z")
        if len(zero_axes) != 1:
            return None
        return {
            "X": "YZ",
            "Y": "XZ",
            "Z": "XY",
        }[zero_axes[0]]

    def _apply_grid_working_views(self) -> None:
        """Apply grid working views."""
        recommended_plane = self._recommended_grid_plane()
        if not self.project.grid.enabled:
            self._active_parallel_plane = "3D"
            self._active_parallel_value = None
            self._secondary_parallel_plane = "3D"
            self._secondary_parallel_value = None
            if hasattr(self, "combo_plane"):
                self.combo_plane.blockSignals(True)
                self.combo_plane.setCurrentText("3D")
                self.combo_plane.blockSignals(False)
            if hasattr(self, "combo_secondary_plane"):
                self.combo_secondary_plane.blockSignals(True)
                self.combo_secondary_plane.setCurrentText("3D")
                self.combo_secondary_plane.blockSignals(False)
            return

        if recommended_plane is None:
            return

        self._active_parallel_plane = recommended_plane
        values = []
        if self.model_view is not None:
            values = self.model_view.plane_values(self.project.grid, recommended_plane)
        self._active_parallel_value = float(values[0]) if values else None
        self._secondary_parallel_plane = "3D"
        self._secondary_parallel_value = None
        if hasattr(self, "combo_plane"):
            self.combo_plane.blockSignals(True)
            self.combo_plane.setCurrentText(recommended_plane)
            self.combo_plane.blockSignals(False)
        if hasattr(self, "combo_secondary_plane"):
            self.combo_secondary_plane.blockSignals(True)
            self.combo_secondary_plane.setCurrentText("3D")
            self.combo_secondary_plane.blockSignals(False)

    def _ensure_work_plane_for_drawing(self) -> None:
        """Switch automatically to the recommended 2D work plane before drawing."""
        recommended_plane = self._recommended_grid_plane()
        if recommended_plane is None:
            return
        if self._active_parallel_plane != recommended_plane:
            self._set_primary_view_plane(recommended_plane)
            self._log(
                f"Vue de travail basculee automatiquement sur le plan {recommended_plane}."
            )

    def _on_view_xy(self) -> None:
        self._set_primary_view_plane("XY")

    def _on_view_xz(self) -> None:
        self._set_primary_view_plane("XZ")

    def _on_view_yz(self) -> None:
        self._set_primary_view_plane("YZ")

    def _on_view_iso(self) -> None:
        if self.model_view is None:
            return
        self._set_primary_view_plane("3D")

    def _on_toggle_node_tags(self, checked: bool) -> None:
        """Handle toggle node tags."""
        self.settings.gui.show_node_tags = checked
        if self.model_view is not None:
            self.model_view.show_node_tags = checked
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "show_node_tags"):
            self.secondary_view.show_node_tags = checked
        self._refresh(preserve_view=True)

    def _on_toggle_section_names(self, checked: bool) -> None:
        """Handle toggle section names."""
        if checked and self.act_show_extruded_sections.isChecked():
            self.act_show_extruded_sections.blockSignals(True)
            self.act_show_extruded_sections.setChecked(False)
            self.act_show_extruded_sections.blockSignals(False)
            self.settings.gui.show_extruded_sections = False
            if self.model_view is not None:
                self.model_view.show_extruded_sections = False
            if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "show_extruded_sections"):
                self.secondary_view.show_extruded_sections = False

        self.settings.gui.show_section_names = checked
        if self.model_view is not None:
            self.model_view.show_section_names = checked
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "show_section_names"):
            self.secondary_view.show_section_names = checked
        self._refresh(preserve_view=True)

    def _on_toggle_extruded_sections(self, checked: bool) -> None:
        """Handle toggle extruded sections."""
        if checked and self.act_show_section_names.isChecked():
            self.act_show_section_names.blockSignals(True)
            self.act_show_section_names.setChecked(False)
            self.act_show_section_names.blockSignals(False)
            self.settings.gui.show_section_names = False
            if self.model_view is not None:
                self.model_view.show_section_names = False
            if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "show_section_names"):
                self.secondary_view.show_section_names = False

        self.settings.gui.show_extruded_sections = checked
        if self.model_view is not None:
            self.model_view.show_extruded_sections = checked
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "show_extruded_sections"):
            self.secondary_view.show_extruded_sections = checked
        self._refresh(preserve_view=True)

    def _clear_results_state(self) -> None:
        """Clear results state."""
        self._all_results.clear()
        self._result_envelopes.clear()
        self._case_tags.clear()
        self._runner = None
        self._current_case = None
        self._current_surface_component = None
        self._current_element_diagram = None
        self._current_element_diagram_tag = None
        self._current_surface_result_tag = None
        self._clear_diagrams()
        self._diagram_files = []
        self._element_diagram_files = []
        self._current_file_idx = 0
        self._current_element_file_idx = 0
        self._surface_result_files = []
        self._current_surface_file_idx = 0
        if self._element_diagram_window is not None:
            self._element_diagram_window.hide()
        if self._surface_diagram_window is not None:
            self._surface_diagram_window.hide()
        self._refresh_result_actions()
        self.results_panel.clear_results()
        if self._results_window is not None:
            self._results_window.clear_results()
            self._results_window.hide()

    def _clear_selection_state(self) -> None:
        """Clear selection state."""
        self._selected_node_tags = []
        self._selected_element_tags = []
        self._selected_surface_tags = []
        if self.model_view is not None:
            self.model_view.set_selected_objects([], [], [], emit_signal=False)
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "set_selected_objects"):
            self.secondary_view.set_selected_objects([], [], [], emit_signal=False)

        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.properties.clear_display()

    def _clear_project_runtime_state(self) -> None:
        """Clear project runtime state."""
        self._draw_start_point = None
        self._draw_surface_points = []
        self._draw_surface_section_tag = None
        self._draw_mode_kind = None
        self._clear_selection_state()
        if self.model_view is not None and hasattr(self.model_view, "clear_drawing_state"):
            self.model_view.clear_drawing_state()
        if getattr(self, "secondary_view", None) is not None and hasattr(self.secondary_view, "clear_drawing_state"):
            self.secondary_view.clear_drawing_state()
        self._clear_results_state()

    def _sync_modified_with_saved_state(self) -> None:
        """Synchronize modified with saved state."""
        self._modified = self.project != self._saved_project_snapshot

    def _mark_project_modified(self) -> None:
        """Handle mark project modified."""
        self._invalidate_results_after_model_change()
        self._modified = True
        self._pending_project_change = True

    def _sync_modified_with_saved_state(self, *, force_compare: bool = False) -> None:
        """Synchronize modified with saved state."""
        if self._modified and not force_compare:
            return
        self._modified = self.project != self._saved_project_snapshot

    def _update_history_actions(self) -> None:
        """Update history actions."""
        can_undo = bool(self._undo_history)
        can_redo = bool(self._redo_history)
        self.act_undo_model.setEnabled(can_undo)
        self.act_redo_model.setEnabled(can_redo)
        if hasattr(self, "btn_undo_history"):
            self.btn_undo_history.setEnabled(can_undo)
        if hasattr(self, "btn_redo_history"):
            self.btn_redo_history.setEnabled(can_redo)

    def _reset_project_history(self, *, mark_saved: bool = False) -> None:
        """Reset project history."""
        self._undo_history.clear()
        self._redo_history.clear()
        self._last_history_project = deepcopy(self.project)
        if mark_saved:
            self._saved_project_snapshot = deepcopy(self.project)
        self._sync_modified_with_saved_state()
        self._update_history_actions()

    def _record_history_snapshot_if_needed(self) -> None:
        """Handle record history snapshot if needed."""
        if self._history_restoring or self.project == self._last_history_project:
            return

        self._undo_history.append(deepcopy(self._last_history_project))
        if len(self._undo_history) > self._MAX_HISTORY_ACTIONS:
            self._undo_history = self._undo_history[-self._MAX_HISTORY_ACTIONS :]
        self._redo_history.clear()
        self._last_history_project = deepcopy(self.project)

    def _propagate_project_path_to_history(self, path: str) -> None:
        """Handle propagate project path to history."""
        normalized_path = str(path)
        self.project.file_path = normalized_path
        self._last_history_project.file_path = normalized_path
        self._saved_project_snapshot.file_path = normalized_path
        for snapshot in self._undo_history:
            snapshot.file_path = normalized_path
        for snapshot in self._redo_history:
            snapshot.file_path = normalized_path

    def _restore_project_history_state(self, snapshot: ProjectModel, *, preserve_view: bool = True) -> None:
        """Restore project history state."""
        self._history_restoring = True
        try:
            self.project = deepcopy(snapshot)
            self.project.ensure_self_weight_load_case()
            self.properties.set_project(self.project)
            self._clear_project_runtime_state()
            self._last_history_project = deepcopy(self.project)
            self._refresh(preserve_view=preserve_view)
        finally:
            self._history_restoring = False

        self._sync_modified_with_saved_state()
        self._update_history_actions()

    def _undo_last_action(self) -> None:
        """Handle undo last action."""
        if not self._undo_history:
            return

        self._redo_history.append(deepcopy(self.project))
        if len(self._redo_history) > self._MAX_HISTORY_ACTIONS:
            self._redo_history = self._redo_history[-self._MAX_HISTORY_ACTIONS :]
        snapshot = self._undo_history.pop()
        self._restore_project_history_state(snapshot)
        self._log("Annulation de la dernière action.")

    def _redo_last_action(self) -> None:
        """Handle redo last action."""
        if not self._redo_history:
            return

        self._undo_history.append(deepcopy(self.project))
        if len(self._undo_history) > self._MAX_HISTORY_ACTIONS:
            self._undo_history = self._undo_history[-self._MAX_HISTORY_ACTIONS :]
        snapshot = self._redo_history.pop()
        self._restore_project_history_state(snapshot)
        self._log("Rétablissement de l'action.")

    def _reset_project_history(self, *, mark_saved: bool = False) -> None:
        """Reset project history."""
        self._undo_history.clear()
        self._redo_history.clear()
        self._pending_project_change = False
        self._last_history_project = deepcopy(self.project)
        if mark_saved:
            self._saved_project_snapshot = deepcopy(self.project)
        self._sync_modified_with_saved_state(force_compare=True)
        self._update_history_actions()

    def _record_history_snapshot_if_needed(self) -> None:
        """Handle record history snapshot if needed."""
        pending_change = self._pending_project_change
        self._pending_project_change = False

        if self._history_restoring:
            return
        if not pending_change and self.project == self._last_history_project:
            return

        self._undo_history.append(deepcopy(self._last_history_project))
        if len(self._undo_history) > self._MAX_HISTORY_ACTIONS:
            self._undo_history = self._undo_history[-self._MAX_HISTORY_ACTIONS :]
        self._redo_history.clear()
        self._last_history_project = deepcopy(self.project)

    def _restore_project_history_state(
        self,
        snapshot: ProjectModel,
        *,
        preserve_view: bool = True,
    ) -> None:
        """Restore project history state."""
        self._history_restoring = True
        try:
            self.project = deepcopy(snapshot)
            self.project.ensure_self_weight_load_case()
            self.properties.set_project(self.project)
            self._clear_project_runtime_state()
            self._pending_project_change = False
            self._last_history_project = deepcopy(self.project)
            self._refresh(preserve_view=preserve_view)
        finally:
            self._history_restoring = False

        self._sync_modified_with_saved_state(force_compare=True)
        self._update_history_actions()

    @staticmethod
    def _scene_signature_value(value):
        """Handle scene signature value."""
        if isinstance(value, dict):
            return tuple(
                (key, MainWindow._scene_signature_value(item_value))
                for key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(MainWindow._scene_signature_value(item) for item in value)
        if isinstance(value, set):
            return tuple(
                sorted(
                    (MainWindow._scene_signature_value(item) for item in value),
                    key=repr,
                )
            )
        if isinstance(value, float):
            return round(value, 12)
        return value

    @staticmethod
    def _axis_signature(items) -> tuple:
        return tuple(
            (
                getattr(item, "marker", ""),
                round(float(getattr(item, "coordinate", 0.0)), 12),
            )
            for item in items
        )

    def _project_scene_signature(self) -> tuple:
        """Project scene signature."""
        project = self.project
        grid = project.grid
        gui = self.settings.gui

        nodes = tuple(
            (
                tag,
                round(float(node.x), 12),
                round(float(node.y), 12),
                round(float(node.z), 12),
                tuple(node.fixities),
                self._scene_signature_value(node.boundary_data),
            )
            for tag, node in sorted(project.nodes.items())
        )
        elements = tuple(
            (
                tag,
                elem.node_i,
                elem.node_j,
                elem.section_tag,
                elem.element_type,
            )
            for tag, elem in sorted(project.elements.items())
        )
        surfaces = tuple(
            (
                tag,
                tuple(surface.node_tags),
                surface.section_tag,
                surface.surface_type,
            )
            for tag, surface in sorted(project.surface_elements.items())
        )
        used_section_tags = {
            elem.section_tag for elem in project.elements.values()
        } | {
            surface.section_tag for surface in project.surface_elements.values()
        }
        sections = tuple(
            (
                tag,
                section.name,
                section.section_type,
                self._scene_signature_value(section.properties),
                round(float(section.area), 12),
                round(float(section.inertia_y), 12),
                round(float(section.inertia_z), 12),
            )
            for tag, section in sorted(project.sections.items())
            if tag in used_section_tags
        )
        return (
            bool(gui.show_grid),
            bool(gui.show_node_tags),
            bool(gui.show_section_names),
            bool(gui.show_extruded_sections),
            getattr(self, "_active_parallel_plane", "3D"),
            round(float(getattr(self, "_active_parallel_value", None)), 12)
            if getattr(self, "_active_parallel_value", None) is not None
            else None,
            getattr(self, "_secondary_parallel_plane", "3D"),
            round(float(getattr(self, "_secondary_parallel_value", None)), 12)
            if getattr(self, "_secondary_parallel_value", None) is not None
            else None,
            bool(grid.enabled),
            self._axis_signature(getattr(grid, "x_items", [])),
            self._axis_signature(getattr(grid, "y_items", [])),
            self._axis_signature(getattr(grid, "z_items", [])),
            nodes,
            elements,
            surfaces,
            sections,
        )

    def _secondary_view_visible(self) -> bool:
        """Handle secondary view visible."""
        secondary_view = getattr(self, "secondary_view", None)
        if secondary_view is None or not hasattr(secondary_view, "display_model"):
            return False
        action = getattr(self, "act_toggle_split_view", None)
        if action is not None and hasattr(action, "isChecked") and not action.isChecked():
            return False
        if hasattr(secondary_view, "isVisible"):
            try:
                return bool(secondary_view.isVisible())
            except Exception:
                return True
        return True

    def _refresh(self, preserve_view: bool = False, refresh_scene: bool = True) -> None:
        """Handle refresh."""
        self.tree.refresh(self.project)
        self.node_table.refresh(self.project)
        self.combo_table.refresh(self.project)
        self._refresh_model_management_menus()
        self._refresh_diagram_actions()
        self._refresh_draw_section_controls()
        self._refresh_parallel_view_controls(apply_view=not preserve_view)
        self._record_history_snapshot_if_needed()
        self._sync_modified_with_saved_state()
        self._update_history_actions()
        self._update_statusbar()
        self._update_title()
        scene_signature = self._project_scene_signature() if refresh_scene else None
        scene_changed = (
            refresh_scene
            and scene_signature != getattr(self, "_last_scene_signature", None)
        )

        if scene_changed:
            if self._deformed_visible and self._current_case in self._all_results:
                self._show_deformed(
                    self._current_case,
                    preserve_view=preserve_view,
                    log_message=False,
                )
            else:
                self._display_primary_model_view(preserve_view=preserve_view)
            if self._secondary_view_visible():
                self._display_secondary_model_view(preserve_view=preserve_view)
            self._last_scene_signature = scene_signature

        self._refresh_load_diagram_if_open()
        self._refresh_element_diagram_if_open()

        # Enable the analysis button when the model has elements and supports
        has_model = (
            len(self.project.nodes) >= 2
            and bool(
                self.project.elements
                or self.project.surface_elements
                or self.project.plate_regions
            )
            and any(n.is_fixed for n in self.project.nodes.values())
        )
        has_surface_model = bool(self.project.surface_elements or self.project.plate_regions)
        surfaces_allowed = self._surface_features_enabled() or not has_surface_model
        self.act_run.setEnabled(has_model and surfaces_allowed)
        if has_surface_model and not surfaces_allowed:
            self.act_run.setToolTip(self._surface_features_disabled_reason())
            self.act_run.setStatusTip(self.act_run.toolTip())
        else:
            self.act_run.setToolTip(self.act_run.text())
            self.act_run.setStatusTip(self.act_run.text())

    def _force_render(self) -> None:
        """Handle force render."""
        if self.model_view is not None:
            try:
                self.model_view.plotter.render()
                self.model_view.update()
            except Exception:
                pass

    def _window_project_name(self) -> str:
        """Handle window project name."""
        project_name = (self.project.name or "").strip()
        if project_name and project_name.casefold() != "nouveau projet":
            return project_name

        if self.project.file_path:
            file_stem = Path(self.project.file_path).stem.strip()
            if file_stem:
                return file_stem

        return project_name or "Nouveau projet"

    def _update_title(self) -> None:
        """Update title."""
        name = self._window_project_name()
        modified = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{modified} — {APP_NAME} v{APP_VERSION}")

    def _log(self, message: str) -> None:
        """Handle log."""
        self.console.appendPlainText(message)

    def _confirm_discard(self) -> bool:
        """Handle confirm discard."""
        reply = QMessageBox.question(
            self, "Modifications non enregistrées",
            "Le projet a été modifié. Voulez-vous continuer sans enregistrer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def closeEvent(self, event) -> None:
        """Handle the Qt close event."""
        if self._modified and not self._confirm_discard():
            event.ignore()
            return
        self.settings.gui.window_width = self.width()
        self.settings.gui.window_height = self.height()
        window_for_geometry = None
        if self._surface_diagram_window is not None and self._surface_diagram_window.isVisible():
            window_for_geometry = self._surface_diagram_window
        elif self._element_diagram_window is not None and self._element_diagram_window.isVisible():
            window_for_geometry = self._element_diagram_window
        elif self._load_diagram_window is not None and self._load_diagram_window.isVisible():
            window_for_geometry = self._load_diagram_window
        elif self._diagram_window is not None and self._diagram_window.isVisible():
            window_for_geometry = self._diagram_window
        else:
            window_for_geometry = (
                self._surface_diagram_window
                or self._element_diagram_window
                or self._diagram_window
                or self._load_diagram_window
            )
        if window_for_geometry is not None:
            self.settings.gui.diagram_window_width = window_for_geometry.width()
            self.settings.gui.diagram_window_height = window_for_geometry.height()
            self.settings.gui.diagram_window_x = window_for_geometry.x()
            self.settings.gui.diagram_window_y = window_for_geometry.y()
        if self._diagram_window is not None:
            self._diagram_window.close()
        if self._element_diagram_window is not None:
            self._element_diagram_window.close()
        if self._surface_diagram_window is not None:
            self._surface_diagram_window.close()
        if self._load_diagram_window is not None:
            self._load_diagram_window.close()
        self.settings.save()
        if self.model_view is not None:
            self.model_view.close()
        event.accept()
