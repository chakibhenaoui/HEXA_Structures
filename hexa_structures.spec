# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec pour HEXA Structures.

Genere un executable Windows autonome incluant :
- Python + toutes les dependances
- PySide6, PyVista, VTK
- Ressources (icones, profiles, templates)
- Traductions Qt (i18n/*.qm)

Important :
- OpenSeesPy n'est pas redistribue dans l'executable.
- S'il est installe dans le venv de build, il est explicitement exclu.
- L'utilisateur final doit l'installer separement s'il veut ce backend.

Usage : pyinstaller hexa_structures.spec
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Repertoire du projet
PROJECT_DIR = os.path.abspath(".")
APP_ICON = os.path.join(PROJECT_DIR, "resources", "icons", "hexa_structures.ico")

pyvista_datas = collect_data_files("pyvista")
qtpy_datas = collect_data_files("qtpy")
pyvistaqt_datas = collect_data_files("pyvistaqt")
pyvistaqt_hiddenimports = collect_submodules("pyvistaqt")

try:
    sectionproperties_datas = collect_data_files("sectionproperties")
    sectionproperties_hiddenimports = collect_submodules("sectionproperties")
except Exception:
    sectionproperties_datas = []
    sectionproperties_hiddenimports = []


def _qtpy_filter(name):
    return name in {
        "qtpy",
        "qtpy.QtCore",
        "qtpy.QtGui",
        "qtpy.QtWidgets",
    }


qtpy_hiddenimports = collect_submodules("qtpy", filter=_qtpy_filter)

a = Analysis(
    ["main.py"],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        ("resources", "resources"),
        ("i18n", "i18n"),
        ("gui/ui", "gui/ui"),
        *pyvista_datas,
        *qtpy_datas,
        *pyvistaqt_datas,
        *sectionproperties_datas,
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtOpenGLWidgets",
        "pyvista",
        "pyvistaqt",
        "vtkmodules",
        "vtkmodules.all",
        "typing_extensions",
        "scooby",
        "numpy",
        "scipy",
        "scipy.sparse",
        "scipy.sparse.linalg",
        "config",
        "config.settings",
        "config.eurocodes",
        "core",
        "core.model_data",
        "core.ops_builder",
        "core.materials",
        "core.sections",
        "core.analysis",
        "core.results",
        "gui",
        "gui.main_window",
        "gui.widgets",
        "gui.widgets.model_view",
        "utils",
        "utils.units",
        *qtpy_hiddenimports,
        *pyvistaqt_hiddenimports,
        *sectionproperties_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "test",
        "pytest",
        "ruff",
        "openseespy",
        "openseespy.opensees",
        "openseespywin",
        "openseespywin.opensees",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HEXA Structures",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=APP_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HEXA Structures",
)
