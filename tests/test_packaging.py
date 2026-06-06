from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_spec_includes_i18n_data_dir() -> None:
    spec = (ROOT / "hexa_structures.spec").read_text(encoding="utf-8")

    assert '("i18n", "i18n")' in spec
    assert '("resources", "resources")' in spec
    assert '("gui/ui", "gui/ui")' in spec
    assert "sectionproperties_hiddenimports" in spec
    assert "sectionproperties_datas" in spec
    assert "*sectionproperties_hiddenimports" in spec
    assert "*sectionproperties_datas" in spec


def test_optional_requirements_declares_sectionproperties() -> None:
    optional = (ROOT / "requirements-optional.txt").read_text(encoding="utf-8")

    assert "sectionproperties" in optional


def test_installer_script_packages_build_tree_and_docs() -> None:
    script = (ROOT / "installer" / "hexa_structures.iss").read_text(encoding="utf-8")

    assert 'Source: "{#BuildSource}\\*"' in script
    assert "recursesubdirs" in script
    assert "CHANGELOG.md" in script
    assert "README.md" in script
    assert "LICENSE" in script


def test_build_scripts_validate_i18n_before_distribution() -> None:
    build_script = (ROOT / "build.bat").read_text(encoding="utf-8")
    installer_script = (ROOT / "build-installer.bat").read_text(encoding="utf-8")

    assert r"_internal\i18n" in build_script
    assert "hexa_fr.qm" in build_script
    assert "hexa_en.qm" in build_script
    assert "--smoke-test --smoke-language en" in build_script
    assert "--smoke-allow-language-fallback" in build_script
    assert r"_internal\i18n\hexa_fr.qm" in installer_script
    assert r"_internal\i18n\hexa_en.qm" in installer_script
