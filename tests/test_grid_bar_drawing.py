from __future__ import annotations

from gui.main_window import MainWindow


class _DummyToggle:
    def __init__(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:  # noqa: N802 - Qt-style name
        return self._checked


class _DummyView:
    def __init__(self) -> None:
        self.preview_start = None

    def set_preview_start(self, point) -> None:
        self.preview_start = point


def test_constrain_draw_point_allows_diagonal_when_orthogonal_is_disabled() -> None:
    window = MainWindow.__new__(MainWindow)
    window._draw_start_point = (0.0, 0.0, 0.0)
    window.act_draw_orthogonal = _DummyToggle(False)
    window._pick_plane_override = None
    window._active_parallel_plane = "XY"

    assert window._constrain_draw_point((4.0, 3.0, 0.0)) == (4.0, 3.0, 0.0)


def test_constrain_draw_point_snaps_when_orthogonal_is_enabled() -> None:
    window = MainWindow.__new__(MainWindow)
    window._draw_start_point = (0.0, 0.0, 0.0)
    window.act_draw_orthogonal = _DummyToggle(True)
    window._pick_plane_override = None
    window._active_parallel_plane = "XY"

    assert window._constrain_draw_point((4.0, 3.0, 0.0)) == (4.0, 0.0, 0.0)


def test_right_click_resets_pending_bar_start() -> None:
    window = MainWindow.__new__(MainWindow)
    window.model_view = _DummyView()
    window.secondary_view = None
    window._draw_mode_kind = "bar"
    window._draw_start_point = (0.0, 0.0, 0.0)

    logs: list[str] = []
    refresh_menu_calls: list[bool] = []
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)

    window._on_draw_finalize_requested()

    assert window._draw_start_point is None
    assert window.model_view.preview_start is None
    assert refresh_menu_calls == [True]
    assert any("barre" in message.lower() and "annule" in message.lower() for message in logs)
