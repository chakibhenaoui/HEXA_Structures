from __future__ import annotations

from config.settings import Settings


def test_settings_roundtrip_preserves_extruded_sections(tmp_path) -> None:
    settings = Settings()
    settings.gui.show_extruded_sections = True
    settings.gui.show_local_axes = True
    target = tmp_path / "settings.json"

    settings.save(target)
    loaded = Settings.load(target)

    assert loaded.gui.show_extruded_sections is True
    assert loaded.gui.show_local_axes is True
