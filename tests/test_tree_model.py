import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.model_data import CombinationData, LoadData, ProjectModel
import gui.widgets.tree_model as tree_model_module
from gui.widgets.tree_model import ModelTree


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _project_with_tree_content() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    project.add_section("HEA 200", "rectangular", 1, properties={"b": 0.20, "h": 0.20})
    project.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})
    project.add_element(1, 2, section_tag=1, element_type="beam")
    project.add_surface_element((1, 2, 3, 4), section_tag=2)
    project.loads[1] = LoadData(tag=1, name="G", load_type="permanent", category="G")
    project.combinations[1] = CombinationData(
        tag=1,
        name="ELU",
        combo_type="ULS",
        factors={1: 1.35},
    )
    return project


def test_model_tree_collapses_dense_categories_by_default() -> None:
    _app()
    tree = ModelTree()
    tree.refresh(_project_with_tree_content())

    assert tree._root_nodes.isExpanded() is False
    assert tree._root_elements.isExpanded() is False
    assert tree._root_surfaces.isExpanded() is False
    assert tree._root_combos.isExpanded() is False

    assert tree._root_materials.isExpanded() is True
    assert tree._root_sections.isExpanded() is True
    assert tree._root_loads.isExpanded() is True


def test_model_tree_expands_parent_when_selecting_item_programmatically() -> None:
    _app()
    tree = ModelTree()
    tree.refresh(_project_with_tree_content())

    assert tree._root_surfaces.isExpanded() is False

    tree.select_surface(1)

    assert tree._root_surfaces.isExpanded() is True
    assert tree.currentItem() is not None
    assert tree.currentItem().text(0) == "S1"


def test_model_tree_surface_double_click_requests_edit() -> None:
    _app()
    tree = ModelTree()
    tree.refresh(_project_with_tree_content())
    edits: list[tuple[str, int]] = []
    tree.edit_requested.connect(lambda kind, tag: edits.append((kind, tag)))

    tree._on_item_double_clicked(tree._root_surfaces.child(0), 0)

    assert edits == [("surface", 1)]


def test_model_tree_surface_context_menu_can_request_delete(monkeypatch) -> None:
    _app()
    tree = ModelTree()
    tree.refresh(_project_with_tree_content())
    surface_item = tree._root_surfaces.child(0)
    deletes: list[tuple[str, int]] = []
    tree.delete_requested.connect(lambda kind, tag: deletes.append((kind, tag)))

    class _FakeSignal:
        def __init__(self) -> None:
            self.slot = None

        def connect(self, slot) -> None:
            self.slot = slot

    class _FakeAction:
        def __init__(self, text: str) -> None:
            self._text = text
            self.triggered = _FakeSignal()

        def text(self) -> str:
            return self._text

    class _FakeMenu:
        def __init__(self, _parent=None) -> None:
            self._actions: list[_FakeAction] = []

        def addAction(self, text: str) -> _FakeAction:
            action = _FakeAction(text)
            self._actions.append(action)
            return action

        def actions(self) -> list[_FakeAction]:
            return self._actions

        def exec(self, _pos) -> _FakeAction | None:
            for action in self._actions:
                if action.text().startswith("Supprimer"):
                    action.triggered.slot()
                    return action
            return None

    monkeypatch.setattr(tree_model_module, "QMenu", _FakeMenu)
    monkeypatch.setattr(ModelTree, "itemAt", lambda _self, _pos: surface_item)

    tree._on_context_menu(tree.visualItemRect(surface_item).center())

    assert deletes == [("surface", 1)]
