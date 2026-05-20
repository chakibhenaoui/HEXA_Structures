"""
Paramètres globaux de l'application : unités, chemins, préférences.

Ce module fournit la classe Settings qui centralise tous les réglages
de l'application HEXA Structures, avec sauvegarde/chargement JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ---------------------------------------------------------------------------
#  Constantes de l'application
# ---------------------------------------------------------------------------

APP_NAME: str = "HEXA Structures"
APP_VERSION: str = "0.1.0"
APP_AUTHOR: str = "HEXA Structures Contributors"

# Répertoire de configuration utilisateur
CONFIG_DIR: Path = Path.home() / ".hexa_structures"
SETTINGS_FILE: Path = CONFIG_DIR / "settings.json"
LEGACY_CONFIG_DIR: Path = Path.home() / ".opensees_fr"
LEGACY_SETTINGS_FILE: Path = LEGACY_CONFIG_DIR / "settings.json"

# Répertoire du projet (racine du package)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Ressources embarquées
RESOURCES_DIR: Path = PROJECT_ROOT / "resources"
ICONS_DIR: Path = RESOURCES_DIR / "icons"
PROFILES_DIR: Path = RESOURCES_DIR / "profiles"
TEMPLATES_DIR: Path = RESOURCES_DIR / "templates"

# Extensions de fichier
PROJECT_EXTENSION: str = ".osfr"
DB_EXTENSION: str = ".db"


# ---------------------------------------------------------------------------
#  Paramètres par défaut
# ---------------------------------------------------------------------------

@dataclass
class DisplayUnits:
    """Unités d'affichage choisies par l'utilisateur.

    Les unités internes restent toujours kN, m, kPa.
    Ces réglages contrôlent uniquement l'affichage dans la GUI.
    """

    length: str = "m"
    force: str = "kN"
    stress: str = "MPa"
    moment: str = "kN·m"
    area: str = "cm²"
    inertia: str = "cm⁴"


@dataclass
class AnalysisDefaults:
    """Paramètres par défaut pour les analyses."""

    ndm: int = 3          # nombre de dimensions du modèle
    ndf: int = 6          # nombre de degrés de liberté par nœud
    solver_engine: str = "pynite"  # moteur par défaut : PyNite intégré
    max_iterations: int = 100
    tolerance: float = 1e-6
    num_modes: int = 10   # nombre de modes pour l'analyse modale


@dataclass
class GuiPreferences:
    """Préférences de l'interface graphique."""

    theme: str = "dark"
    language: str = "fr"
    window_width: int = 1400
    window_height: int = 900
    diagram_window_width: int = 1100
    diagram_window_height: int = 760
    diagram_window_x: int = -1
    diagram_window_y: int = -1
    show_grid: bool = True
    grid_spacing: float = 1.0  # mètre
    snap_to_grid: bool = True
    font_size: int = 10
    recent_projects_max: int = 10
    show_node_tags: bool = True       # numéros des nœuds (visible par défaut)
    show_section_names: bool = False   # noms des sections sur les éléments
    show_extruded_sections: bool = False  # affichage 3D extrudé des sections


@dataclass
class Settings:
    """Paramètres globaux de l'application.

    Chargés au démarrage depuis ~/.opensees_fr/settings.json.
    Sauvegardés automatiquement à chaque modification.
    """

    display_units: DisplayUnits = field(default_factory=DisplayUnits)
    analysis: AnalysisDefaults = field(default_factory=AnalysisDefaults)
    gui: GuiPreferences = field(default_factory=GuiPreferences)
    recent_projects: list[str] = field(default_factory=list)
    last_project_dir: str = ""

    # --- Sérialisation ---

    def save(self, path: Path | None = None) -> None:
        """Sauvegarde les paramètres dans un fichier JSON.

        Args:
            path: Chemin du fichier. Par défaut : ~/.opensees_fr/settings.json.
        """
        target = path or SETTINGS_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        """Charge les paramètres depuis un fichier JSON.

        Si le fichier n'existe pas, retourne les paramètres par défaut.

        Args:
            path: Chemin du fichier. Par défaut : ~/.opensees_fr/settings.json.

        Returns:
            Instance Settings chargée.
        """
        target = path or SETTINGS_FILE
        if (
            not target.exists()
            and target == SETTINGS_FILE
            and LEGACY_SETTINGS_FILE.exists()
        ):
            target = LEGACY_SETTINGS_FILE
        if not target.exists():
            return cls()

        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)

        display_units_data = {
            key: value
            for key, value in data.get("display_units", {}).items()
            if key in DisplayUnits.__dataclass_fields__
        }
        analysis_data = {
            key: value
            for key, value in data.get("analysis", {}).items()
            if key in AnalysisDefaults.__dataclass_fields__
        }
        gui_data = {
            key: value
            for key, value in data.get("gui", {}).items()
            if key in GuiPreferences.__dataclass_fields__
        }

        return cls(
            display_units=DisplayUnits(**display_units_data),
            analysis=AnalysisDefaults(**analysis_data),
            gui=GuiPreferences(**gui_data),
            recent_projects=data.get("recent_projects", []),
            last_project_dir=data.get("last_project_dir", ""),
        )

    # --- Projets récents ---

    def add_recent_project(self, project_path: str) -> None:
        """Ajoute un projet à la liste des projets récents.

        Args:
            project_path: Chemin absolu du fichier projet.
        """
        if project_path in self.recent_projects:
            self.recent_projects.remove(project_path)
        self.recent_projects.insert(0, project_path)
        # Garder seulement les N plus récents
        self.recent_projects = self.recent_projects[
            : self.gui.recent_projects_max
        ]
