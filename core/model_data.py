"""
Modèle de données interne du projet.

Classes Python pures (dataclasses), indépendantes d'OpenSees.
Supporte la sérialisation SQLite, l'annuler/refaire et les tests unitaires.
"""

from __future__ import annotations

import sqlite3
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from core.material_properties import (
    build_material_properties,
    isotropic_material_properties,
)
from core.sections import RectangularSection
from core.self_weight import SELF_WEIGHT_LOAD_NAME, SELF_WEIGHT_LOAD_TYPE


SURFACE_FORMULATION_TYPES: dict[str, str] = {
    "ShellMITC4": "shell",
    "ShellDKGQ": "plate",
    "ShellNLDKGQ": "shell",
}

LEGACY_SURFACE_FORMULATION_TYPES: dict[str, str] = {
    # Tri31 reste reconnu pour diagnostiquer clairement les anciens projets,
    # mais il n'est plus propose dans l'interface tant que le backend ne le gere pas.
    "Tri31": "shell",
}

_KNOWN_SURFACE_FORMULATION_TYPES: dict[str, str] = {
    **SURFACE_FORMULATION_TYPES,
    **LEGACY_SURFACE_FORMULATION_TYPES,
}

SURFACE_FORMULATION_INFOS: dict[str, str] = {
    "ShellMITC4": "MITC4 : formulation mixte, valable pour dalles minces et épaisses.",
    "ShellDKGQ": "DKGQ : adaptée aux dalles minces (h/L < 1/10).",
    "ShellNLDKGQ": "NLDKGQ : variante avec non-linéarité géométrique.",
    "Tri31": "Tri31 : element triangulaire temporairement indisponible dans le solveur.",
}
PLATE_MESH_MODE_AUTO = "auto"
PLATE_MESH_MODE_USER = "user"
PLATE_MESH_MODES = {PLATE_MESH_MODE_AUTO, PLATE_MESH_MODE_USER}
DEFAULT_PLATE_MESH_DIVISIONS = 8


def normalize_surface_formulation(formulation: str | None) -> str:
    """Normalise une formulation de plaque connue."""
    value = str(formulation or "ShellMITC4").strip()
    return value if value in _KNOWN_SURFACE_FORMULATION_TYPES else "ShellMITC4"


def surface_type_from_formulation(formulation: str | None) -> str:
    """Retourne le type générique de surface associé à une formulation."""
    return _KNOWN_SURFACE_FORMULATION_TYPES[normalize_surface_formulation(formulation)]


def surface_expected_node_count(formulation: str | None) -> int:
    """Retourne le nombre de nœuds attendu pour la formulation."""
    return 3 if normalize_surface_formulation(formulation) == "Tri31" else 4


def normalize_plate_mesh_mode(mode: str | None) -> str:
    """Normalise le mode de maillage d'une plaque utilisateur."""
    value = str(mode or PLATE_MESH_MODE_AUTO).strip().lower()
    return value if value in PLATE_MESH_MODES else PLATE_MESH_MODE_AUTO


# ═══════════════════════════════════════════════════════════════════════════
#  Dataclasses du modèle
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NodeData:
    """Nœud du modèle structurel 3D (6 DDL)."""

    tag: int
    x: float
    y: float
    z: float = 0.0
    # Fixités 6 DDL : (Ux, Uy, Uz, Rx, Ry, Rz) — 1=bloqué, 0=libre
    fixities: tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    # Données de condition aux limites (type, ressorts, nom)
    boundary_data: dict = field(default_factory=dict)

    @property
    def is_fixed(self) -> bool:
        """Vrai si au moins un degré de liberté est bloqué."""
        return any(f == 1 for f in self.fixities)

    @property
    def is_support(self) -> bool:
        """Vrai si le nœud est un appui (au moins une translation bloquée)."""
        return any(f == 1 for f in self.fixities[:3])


@dataclass
class MaterialData:
    """Matériau du modèle."""

    tag: int
    name: str
    material_type: str  # "concrete" | "rebar" | "steel"
    grade: str          # ex. "C30/37", "B500B", "S355"
    properties: dict = field(default_factory=dict)


@dataclass
class SectionData:
    """Section transversale."""

    tag: int
    name: str
    section_type: str  # "rectangular" | "T" | "I_profile"
    material_tag: int
    properties: dict = field(default_factory=dict)
    # Propriétés géométriques calculées (m, m², m⁴)
    area: float = 0.0
    inertia_y: float = 0.0
    inertia_z: float = 0.0

    @property
    def is_surface(self) -> bool:
        """Indique si la section represente un element surfacique."""
        return self.section_type == "surface"

    @property
    def thickness(self) -> float:
        """Retourne l'epaisseur associee a une section surfacique."""
        if not self.is_surface:
            return 0.0
        try:
            return float(self.properties.get("thickness", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @property
    def surface_formulation(self) -> str:
        """Retourne la formulation par défaut associee a une plaque."""
        if not self.is_surface:
            return ""
        return normalize_surface_formulation(
            self.properties.get("element_formulation", "ShellMITC4")
        )


@dataclass
class GridAxisEntry:
    """Repère et coordonnée d'une ligne de grille sur un axe."""

    marker: str = ""
    coordinate: float = 0.0


@dataclass(init=False)
class Grid3DData:
    """Définition d'une grille 3D de modélisation."""

    enabled: bool = False
    x_items: list[GridAxisEntry] = field(default_factory=list)
    y_items: list[GridAxisEntry] = field(default_factory=list)
    z_items: list[GridAxisEntry] = field(default_factory=list)

    def __init__(
        self,
        enabled: bool = False,
        *,
        x_items: list[GridAxisEntry | dict | tuple | list] | None = None,
        y_items: list[GridAxisEntry | dict | tuple | list] | None = None,
        z_items: list[GridAxisEntry | dict | tuple | list] | None = None,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        origin_z: float = 0.0,
        count_x: int = 0,
        count_y: int = 0,
        count_z: int = 0,
        spacing_x: float = 5.0,
        spacing_y: float = 5.0,
        spacing_z: float = 3.0,
    ):
        self.enabled = enabled
        self.x_items = self._build_axis("X", x_items, origin_x, count_x, spacing_x)
        self.y_items = self._build_axis("Y", y_items, origin_y, count_y, spacing_y)
        self.z_items = self._build_axis("Z", z_items, origin_z, count_z, spacing_z)

    @classmethod
    def from_dict(cls, data: dict | None) -> Grid3DData:
        """Construit une grille depuis un format serialise ancien ou nouveau."""
        payload = dict(data or {})
        if any(key in payload for key in ("x_items", "y_items", "z_items")):
            return cls(
                enabled=bool(payload.get("enabled", False)),
                x_items=payload.get("x_items"),
                y_items=payload.get("y_items"),
                z_items=payload.get("z_items"),
            )
        return cls(
            enabled=bool(payload.get("enabled", False)),
            origin_x=float(payload.get("origin_x", 0.0)),
            origin_y=float(payload.get("origin_y", 0.0)),
            origin_z=float(payload.get("origin_z", 0.0)),
            count_x=int(payload.get("count_x", 0)),
            count_y=int(payload.get("count_y", 0)),
            count_z=int(payload.get("count_z", 0)),
            spacing_x=float(payload.get("spacing_x", 5.0)),
            spacing_y=float(payload.get("spacing_y", 5.0)),
            spacing_z=float(payload.get("spacing_z", 3.0)),
        )

    @staticmethod
    def _build_regular_axis(
        axis: str,
        origin: float,
        count: int,
        spacing: float,
    ) -> list[GridAxisEntry]:
        total = max(int(count), 0) + 1
        start = float(origin)
        step = float(spacing)
        return [
            GridAxisEntry(marker=f"{axis}{idx + 1}", coordinate=start + idx * step)
            for idx in range(total)
        ]

    @classmethod
    def _build_axis(
        cls,
        axis: str,
        items: list[GridAxisEntry | dict | tuple | list] | None,
        origin: float,
        count: int,
        spacing: float,
    ) -> list[GridAxisEntry]:
        if items is None:
            return cls._build_regular_axis(axis, origin, count, spacing)
        normalized = cls._normalize_axis_items(axis, items)
        if normalized:
            return normalized
        return cls._build_regular_axis(axis, origin, 0, spacing)

    @staticmethod
    def _parse_axis_item(
        axis: str,
        index: int,
        raw: GridAxisEntry | dict | tuple | list,
    ) -> GridAxisEntry | None:
        if isinstance(raw, GridAxisEntry):
            marker = raw.marker.strip() or f"{axis}{index + 1}"
            return GridAxisEntry(marker=marker, coordinate=float(raw.coordinate))

        marker = ""
        coordinate_raw = None
        if isinstance(raw, dict):
            marker = str(raw.get("marker", raw.get("repère", ""))).strip()
            coordinate_raw = raw.get(
                "coordinate",
                raw.get("coordonnée", raw.get("coordonnée")),
            )
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            marker = str(raw[0]).strip()
            coordinate_raw = raw[1]
        else:
            return None

        try:
            coordinate = float(coordinate_raw)
        except (TypeError, ValueError):
            return None

        if not marker:
            marker = f"{axis}{index + 1}"
        return GridAxisEntry(marker=marker, coordinate=coordinate)

    @classmethod
    def _normalize_axis_items(
        cls,
        axis: str,
        items: list[GridAxisEntry | dict | tuple | list],
    ) -> list[GridAxisEntry]:
        normalized: list[GridAxisEntry] = []
        for index, raw in enumerate(items):
            entry = cls._parse_axis_item(axis, index, raw)
            if entry is not None:
                normalized.append(entry)
        normalized.sort(key=lambda entry: entry.coordinate)
        return normalized

    def _axis_items(self, axis: str) -> list[GridAxisEntry]:
        if axis == "X":
            return self.x_items
        if axis == "Y":
            return self.y_items
        if axis == "Z":
            return self.z_items
        raise ValueError(f"Axe inconnu: {axis}")

    def axis_entries(self, axis: str) -> list[GridAxisEntry]:
        """Retourne les lignes de l'axe demande."""
        return list(self._axis_items(axis))

    def axis_values(self, axis: str) -> list[float]:
        """Retourne les coordonnées triees de l'axe demande."""
        return [entry.coordinate for entry in self._axis_items(axis)]

    def axis_step(self, axis: str) -> float:
        """Retourne un pas representatif pour l'axe demande."""
        values = self.axis_values(axis)
        if len(values) < 2:
            return 0.0
        return max(
            abs(values[idx + 1] - values[idx])
            for idx in range(len(values) - 1)
        )

    def axis_span(self, axis: str) -> float:
        """Retourne la portee totale de l'axe demande."""
        values = self.axis_values(axis)
        if not values:
            return 0.0
        return max(values) - min(values)

    def to_dict(self) -> dict:
        """Retourne le format serialisable du nouveau schema de grille."""
        return {
            "enabled": self.enabled,
            "x_items": [
                {"marker": entry.marker, "coordinate": entry.coordinate}
                for entry in self.x_items
            ],
            "y_items": [
                {"marker": entry.marker, "coordinate": entry.coordinate}
                for entry in self.y_items
            ],
            "z_items": [
                {"marker": entry.marker, "coordinate": entry.coordinate}
                for entry in self.z_items
            ],
        }

    @property
    def origin_x(self) -> float:
        return self.x_items[0].coordinate if self.x_items else 0.0

    @property
    def origin_y(self) -> float:
        return self.y_items[0].coordinate if self.y_items else 0.0

    @property
    def origin_z(self) -> float:
        return self.z_items[0].coordinate if self.z_items else 0.0

    @property
    def count_x(self) -> int:
        return max(len(self.x_items) - 1, 0)

    @property
    def count_y(self) -> int:
        return max(len(self.y_items) - 1, 0)

    @property
    def count_z(self) -> int:
        return max(len(self.z_items) - 1, 0)

    @property
    def spacing_x(self) -> float:
        return self._axis_spacing("X")

    @property
    def spacing_y(self) -> float:
        return self._axis_spacing("Y")

    @property
    def spacing_z(self) -> float:
        return self._axis_spacing("Z")

    def _axis_spacing(self, axis: str) -> float:
        values = self.axis_values(axis)
        if len(values) < 2:
            return 0.0
        return values[1] - values[0]


@dataclass
class ElementData:
    """Élément poutre du modèle."""

    tag: int
    node_i: int
    node_j: int
    section_tag: int
    element_type: str = "beam"  # "beam" | "truss" | "spring"
    orientation_vector: tuple[float, float, float] | None = None
    roll_angle_deg: float = 0.0


@dataclass
class SurfaceElementData:
    """Élément surfacique du modèle.

    `node_tags` contient 3 nœuds pour un triangle ou 4 nœuds pour un quadrilatère.
    L'ordre devra rester cohérent pour les solveurs et le post-traitement.
    """

    tag: int
    node_tags: tuple[int, ...]
    section_tag: int
    surface_type: str = "shell"  # "shell" | "plate" | "membrane"
    formulation: str | None = None

    @property
    def is_triangle(self) -> bool:
        return len(self.node_tags) == 3

    @property
    def is_quad(self) -> bool:
        return len(self.node_tags) == 4


@dataclass
class PlateRegionData:
    """Plaque utilisateur macro, maillée automatiquement pour le calcul."""

    tag: int
    name: str
    corner_node_tags: tuple[int, int, int, int]
    section_tag: int
    mesh_nx: int = 8
    mesh_ny: int = 8
    mesh_mode: str = PLATE_MESH_MODE_AUTO
    formulation: str = "ShellMITC4"


@dataclass
class LoadData:
    """Charge individuelle."""

    tag: int
    name: str
    load_type: str      # "dead" | "live" | "snow" | "wind" | "seismic"
    category: str = ""  # catégorie EC1 (A, B, C…)


@dataclass
class NodalLoad:
    """Force/moment ponctuel sur un nœud (3D — 6 composantes)."""

    load_tag: int
    node_tag: int
    fx: float = 0.0    # kN (direction X)
    fy: float = 0.0    # kN (direction Y)
    fz: float = 0.0    # kN (direction Z)
    mx: float = 0.0    # kN·m (moment autour de X)
    my: float = 0.0    # kN·m (moment autour de Y)
    mz: float = 0.0    # kN·m (moment autour de Z)

    def as_tuple(self) -> tuple[float, ...]:
        """Retourne les 6 composantes sous forme de tuple."""
        return (self.fx, self.fy, self.fz, self.mx, self.my, self.mz)


@dataclass
class ElementLoad:
    """Charge répartie sur un élément (3D)."""

    load_tag: int
    element_tag: int
    wx: float = 0.0   # kN/m (direction X locale)
    wy: float = 0.0   # kN/m (direction Y locale)
    wz: float = 0.0   # kN/m (direction Z locale)
    coordinate_system: str = "local"  # "local" | "global"


@dataclass
class SurfaceLoad:
    """Charge surfacique uniforme sur une plaque (3D)."""

    load_tag: int
    surface_tag: int
    qx: float = 0.0   # kN/m² (direction X globale)
    qy: float = 0.0   # kN/m² (direction Y globale)
    qz: float = 0.0   # kN/m² (direction Z globale)


@dataclass
class PlateSurfaceLoadData:
    """Charge surfacique macro appliquee a une plaque utilisateur."""

    load_tag: int
    plate_tag: int
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0


@dataclass
class PlateEdgeSupportData:
    """Appui macro applique a un bord de plaque utilisateur."""

    plate_tag: int
    edge: str  # "12" | "23" | "34" | "41"
    fixities: tuple[int, int, int, int, int, int]


@dataclass
class CombinationData:
    """Combinaison de charges."""

    tag: int
    name: str
    combo_type: str  # "ULS" | "SLS_char" | "SLS_freq" | "SLS_perm" | "seismic"
    factors: dict[int, float] = field(default_factory=dict)
    # factors = {load_tag: facteur}


# ═══════════════════════════════════════════════════════════════════════════
#  Modèle de projet
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ProjectModel:
    """Modèle complet du projet structurel.

    Contient tous les objets du modèle (nœuds, éléments, matériaux, etc.).
    Indépendant d'OpenSees — c'est la source de vérité du projet.
    """

    name: str = "Nouveau projet"
    description: str = ""
    file_path: str = ""
    grid: Grid3DData = field(default_factory=Grid3DData)

    nodes: dict[int, NodeData] = field(default_factory=dict)
    materials: dict[int, MaterialData] = field(default_factory=dict)
    sections: dict[int, SectionData] = field(default_factory=dict)
    elements: dict[int, ElementData] = field(default_factory=dict)
    surface_elements: dict[int, SurfaceElementData] = field(default_factory=dict)
    plate_regions: dict[int, PlateRegionData] = field(default_factory=dict)
    loads: dict[int, LoadData] = field(default_factory=dict)
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    element_loads: list[ElementLoad] = field(default_factory=list)
    surface_loads: list[SurfaceLoad] = field(default_factory=list)
    plate_surface_loads: list[PlateSurfaceLoadData] = field(default_factory=list)
    plate_edge_supports: list[PlateEdgeSupportData] = field(default_factory=list)
    combinations: dict[int, CombinationData] = field(default_factory=dict)

    # --- Compteurs auto-incrémentaux ---

    def next_node_tag(self) -> int:
        """Retourne le prochain tag de nœud disponible."""
        return max(self.nodes.keys(), default=0) + 1

    def next_element_tag(self) -> int:
        """Retourne le prochain tag d'élément disponible."""
        return max(self.elements.keys(), default=0) + 1

    def next_surface_tag(self) -> int:
        """Retourne le prochain tag d'élément surfacique disponible."""
        return max(self.surface_elements.keys(), default=0) + 1

    def next_plate_region_tag(self) -> int:
        """Retourne le prochain tag de plaque utilisateur disponible."""
        return max(self.plate_regions.keys(), default=0) + 1

    def next_material_tag(self) -> int:
        """Retourne le prochain tag de matériau disponible."""
        return max(self.materials.keys(), default=0) + 1

    def next_section_tag(self) -> int:
        """Retourne le prochain tag de section disponible."""
        return max(self.sections.keys(), default=0) + 1

    def next_load_tag(self) -> int:
        """Retourne le prochain tag de cas de charge disponible."""
        return max(self.loads.keys(), default=0) + 1

    def self_weight_load_tag(self) -> int | None:
        """Retourne le tag du cas de poids propre automatique si present."""
        for tag, load in self.loads.items():
            if load.load_type == SELF_WEIGHT_LOAD_TYPE:
                return tag
        for tag, load in self.loads.items():
            if load.name.strip().lower() == SELF_WEIGHT_LOAD_NAME.lower():
                return tag
        return None

    def ensure_self_weight_load_case(self) -> LoadData:
        """Crée le cas de charge automatique de poids propre si nécessaire."""
        existing_tag = self.self_weight_load_tag()
        if existing_tag is not None:
            return self.loads[existing_tag]

        load = LoadData(
            tag=self.next_load_tag(),
            name=SELF_WEIGHT_LOAD_NAME,
            load_type=SELF_WEIGHT_LOAD_TYPE,
            category="G",
        )
        self.loads[load.tag] = load
        return load

    def next_combination_tag(self) -> int:
        """Retourne le prochain tag de combinaison disponible."""
        return max(self.combinations.keys(), default=0) + 1

    # --- Ajout d'objets ---

    def add_node(self, x: float, y: float, z: float = 0.0, **kwargs) -> NodeData:
        """Crée et ajoute un nœud au modèle.

        Args:
            x: Coordonnée X (m).
            y: Coordonnée Y (m).
            z: Coordonnée Z (m).

        Returns:
            Le nœud créé.
        """
        tag = self.next_node_tag()
        node = NodeData(tag=tag, x=x, y=y, z=z, **kwargs)
        self.nodes[tag] = node
        return node

    def add_element(
        self,
        node_i: int,
        node_j: int,
        section_tag: int,
        element_type: str = "beam",
        orientation_vector: tuple[float, float, float] | None = None,
        roll_angle_deg: float = 0.0,
    ) -> ElementData:
        """Crée et ajoute un élément au modèle.

        Args:
            node_i: Tag du nœud de début.
            node_j: Tag du nœud de fin.
            section_tag: Tag de la section assignée.
            element_type: Type d'élément.

        Returns:
            L'élément créé.
        """
        tag = self.next_element_tag()
        if int(node_i) not in self.nodes or int(node_j) not in self.nodes:
            raise ValueError("Element references missing node(s).")
        if int(node_i) == int(node_j):
            raise ValueError("Element end nodes must be distinct.")
        section = self.sections.get(int(section_tag))
        if section is not None and section.is_surface:
            raise ValueError("Element section must be a line/bar section.")
        if orientation_vector is not None:
            orientation_vector = tuple(float(value) for value in orientation_vector)
            if len(orientation_vector) != 3:
                raise ValueError("orientation_vector must contain exactly 3 values.")

        elem = ElementData(
            tag=tag, node_i=int(node_i), node_j=int(node_j),
            section_tag=int(section_tag), element_type=element_type,
            orientation_vector=orientation_vector,
            roll_angle_deg=float(roll_angle_deg),
        )
        self.elements[tag] = elem
        return elem

    def add_surface_element(
        self,
        node_tags: Iterable[int],
        section_tag: int,
        surface_type: str = "shell",
        formulation: str | None = None,
    ) -> SurfaceElementData:
        """Crée et ajoute un élément surfacique au modèle."""
        normalized_node_tags = tuple(int(tag) for tag in node_tags)
        if len(normalized_node_tags) not in (3, 4):
            raise ValueError("A surface element requires 3 or 4 nodes.")
        if len(set(normalized_node_tags)) != len(normalized_node_tags):
            raise ValueError("Surface element nodes must be unique.")
        section = self.sections.get(int(section_tag))
        if section is not None and section.is_surface:
            validation_formulation = (
                normalize_surface_formulation(formulation)
                if formulation else section.surface_formulation
            )
            if validation_formulation not in SURFACE_FORMULATION_TYPES:
                raise NotImplementedError(
                    f"La formulation plaque {validation_formulation} n'est pas disponible "
                    "pour les nouvelles surfaces."
                )
            expected_count = surface_expected_node_count(validation_formulation)
            if len(normalized_node_tags) != expected_count:
                raise ValueError(
                    f"La formulation plaque {validation_formulation} "
                    f"attend {expected_count} noeud(s)."
                )

        tag = self.next_surface_tag()
        surface = SurfaceElementData(
            tag=tag,
            node_tags=normalized_node_tags,
            section_tag=section_tag,
            surface_type=surface_type,
            formulation=normalize_surface_formulation(formulation) if formulation else None,
        )
        self.surface_elements[tag] = surface
        return surface

    def add_plate_region(
        self,
        corner_node_tags: Iterable[int],
        section_tag: int,
        name: str = "",
        mesh_nx: int | None = None,
        mesh_ny: int | None = None,
        formulation: str | None = None,
        mesh_mode: str | None = None,
    ) -> PlateRegionData:
        """Crée une plaque utilisateur macro à quatre noeuds."""
        corners = tuple(int(tag) for tag in corner_node_tags)
        if len(corners) != 4:
            raise ValueError("A plate region requires exactly 4 corner nodes.")
        if len(set(corners)) != 4:
            raise ValueError("Plate region corner nodes must be distinct.")
        missing_nodes = [tag for tag in corners if tag not in self.nodes]
        if missing_nodes:
            raise ValueError(f"Plate region references missing node(s): {missing_nodes}.")

        explicit_mesh = mesh_nx is not None or mesh_ny is not None
        mode = normalize_plate_mesh_mode(
            mesh_mode or (PLATE_MESH_MODE_USER if explicit_mesh else PLATE_MESH_MODE_AUTO)
        )
        nx = int(mesh_nx if mesh_nx is not None else DEFAULT_PLATE_MESH_DIVISIONS)
        ny = int(mesh_ny if mesh_ny is not None else DEFAULT_PLATE_MESH_DIVISIONS)
        if nx < 1 or ny < 1:
            raise ValueError("Plate region mesh_nx and mesh_ny must be >= 1.")

        section = self.sections.get(int(section_tag))
        if section is None:
            raise ValueError(f"Plate region references missing section T{section_tag}.")
        if not section.is_surface:
            raise ValueError("Plate region section must be a surface section.")

        normalized_formulation = normalize_surface_formulation(
            formulation or section.surface_formulation
        )
        if normalized_formulation not in SURFACE_FORMULATION_TYPES:
            raise NotImplementedError(
                f"La formulation plaque {formulation} n'est pas disponible "
                "pour les plaques utilisateur."
            )

        tag = self.next_plate_region_tag()
        plate = PlateRegionData(
            tag=tag,
            name=str(name or ""),
            corner_node_tags=corners,
            section_tag=int(section_tag),
            mesh_nx=nx,
            mesh_ny=ny,
            mesh_mode=mode,
            formulation=normalized_formulation,
        )
        self.plate_regions[tag] = plate
        return plate

    def add_material(self, name: str, material_type: str,
                     grade: str, **properties) -> MaterialData:
        """Crée et ajoute un matériau au modèle."""
        tag = self.next_material_tag()
        isotropic_props = isotropic_material_properties(
            material_type,
            grade,
            properties,
        )
        mat = MaterialData(
            tag=tag, name=name, material_type=material_type,
            grade=grade,
            properties=build_material_properties(
                unit_weight=isotropic_props["unit_weight"],
                young_modulus=isotropic_props["young_modulus"],
                poisson_ratio=isotropic_props["poisson_ratio"],
                base_properties=properties,
            ),
        )
        self.materials[tag] = mat
        return mat

    def add_section(self, name: str, section_type: str,
                    material_tag: int, **kwargs) -> SectionData:
        """Crée et ajoute une section au modèle."""
        tag = self.next_section_tag()
        sec = SectionData(
            tag=tag, name=name, section_type=section_type,
            material_tag=material_tag, **kwargs,
        )
        self.sections[tag] = sec
        return sec

    def seed_default_library(self) -> None:
        """Ajoute les matériaux/sections par défaut sur un projet vide.

        Le jeu par défaut contient :
        - un béton `C30/37`
        - un acier `S355`
        - une section rectangulaire béton `30x30`
        """
        self.ensure_self_weight_load_case()

        if self.materials or self.sections:
            return

        concrete = self.add_material(
            "Béton C30/37",
            "concrete",
            "C30/37",
        )
        self.add_material(
            "Acier S355",
            "steel",
            "S355",
        )

        rect = RectangularSection(b=0.30, h=0.30)
        self.add_section(
            name="Section BA 30x30",
            section_type="rectangular",
            material_tag=concrete.tag,
            properties={"b": 0.30, "h": 0.30},
            area=rect.area,
            inertia_y=rect.inertia_y,
            inertia_z=rect.inertia_z,
        )

    def clear(self) -> None:
        """Réinitialise le modèle (supprime tout)."""
        self.nodes.clear()
        self.materials.clear()
        self.sections.clear()
        self.elements.clear()
        self.surface_elements.clear()
        self.plate_regions.clear()
        self.loads.clear()
        self.nodal_loads.clear()
        self.element_loads.clear()
        self.surface_loads.clear()
        self.plate_surface_loads.clear()
        self.plate_edge_supports.clear()
        self.combinations.clear()

    def copy_for_load_editing(self) -> ProjectModel:
        """Retourne une copie légère pour l'édition des chargements.

        Les collections structurelles sont partagees en lecture seule pour
        éviter une copie profonde complète du projet. Les données de
        chargement sont dupliquées afin que les dialogues puissent être
        validés ou annulés sans modifier le modèle courant.
        """
        return ProjectModel(
            name=self.name,
            description=self.description,
            file_path=self.file_path,
            grid=deepcopy(self.grid),
            nodes=self.nodes,
            materials=self.materials,
            sections=self.sections,
            elements=self.elements,
            surface_elements=self.surface_elements,
            plate_regions=self.plate_regions,
            loads=deepcopy(self.loads),
            nodal_loads=deepcopy(self.nodal_loads),
            element_loads=deepcopy(self.element_loads),
            surface_loads=deepcopy(self.surface_loads),
            plate_surface_loads=deepcopy(self.plate_surface_loads),
            plate_edge_supports=self.plate_edge_supports,
            combinations=deepcopy(self.combinations),
        )

    # --- Statistiques ---

    @property
    def stats(self) -> dict[str, int]:
        """Résumé du modèle."""
        return {
            "nodes": len(self.nodes),
            "elements": len(self.elements),
            "surface_elements": len(self.surface_elements),
            "plate_regions": len(self.plate_regions),
            "materials": len(self.materials),
            "sections": len(self.sections),
            "loads": len(self.loads),
            "combinations": len(self.combinations),
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Sérialisation SQLite
# ═══════════════════════════════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS project (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS nodes (
    tag            INTEGER PRIMARY KEY,
    x              REAL NOT NULL,
    y              REAL NOT NULL,
    z              REAL NOT NULL DEFAULT 0.0,
    fix_ux         INTEGER NOT NULL DEFAULT 0,
    fix_uy         INTEGER NOT NULL DEFAULT 0,
    fix_uz         INTEGER NOT NULL DEFAULT 0,
    fix_rx         INTEGER NOT NULL DEFAULT 0,
    fix_ry         INTEGER NOT NULL DEFAULT 0,
    fix_rz         INTEGER NOT NULL DEFAULT 0,
    boundary_data  TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS materials (
    tag           INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    material_type TEXT NOT NULL,
    grade         TEXT NOT NULL,
    properties    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sections (
    tag          INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    section_type TEXT NOT NULL,
    material_tag INTEGER NOT NULL,
    properties   TEXT NOT NULL DEFAULT '{}',
    area         REAL NOT NULL DEFAULT 0.0,
    inertia_y    REAL NOT NULL DEFAULT 0.0,
    inertia_z    REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS elements (
    tag                INTEGER PRIMARY KEY,
    node_i             INTEGER NOT NULL,
    node_j             INTEGER NOT NULL,
    section_tag        INTEGER NOT NULL,
    element_type       TEXT NOT NULL DEFAULT 'beam',
    orientation_vector TEXT DEFAULT NULL,
    roll_angle_deg     REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS surface_elements (
    tag          INTEGER PRIMARY KEY,
    node_tags    TEXT NOT NULL,
    section_tag  INTEGER NOT NULL,
    surface_type TEXT NOT NULL DEFAULT 'shell',
    formulation  TEXT DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS plate_regions (
    tag              INTEGER PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    corner_node_tags TEXT NOT NULL,
    section_tag      INTEGER NOT NULL,
    mesh_nx          INTEGER NOT NULL DEFAULT 8,
    mesh_ny          INTEGER NOT NULL DEFAULT 8,
    mesh_mode        TEXT NOT NULL DEFAULT 'auto',
    formulation      TEXT NOT NULL DEFAULT 'ShellMITC4'
);
CREATE TABLE IF NOT EXISTS loads (
    tag       INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    load_type TEXT NOT NULL,
    category  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS nodal_loads (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    load_tag INTEGER NOT NULL,
    node_tag INTEGER NOT NULL,
    fx       REAL NOT NULL DEFAULT 0.0,
    fy       REAL NOT NULL DEFAULT 0.0,
    fz       REAL NOT NULL DEFAULT 0.0,
    mx       REAL NOT NULL DEFAULT 0.0,
    my       REAL NOT NULL DEFAULT 0.0,
    mz       REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS element_loads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    load_tag    INTEGER NOT NULL,
    element_tag INTEGER NOT NULL,
    wx          REAL NOT NULL DEFAULT 0.0,
    wy          REAL NOT NULL DEFAULT 0.0,
    wz          REAL NOT NULL DEFAULT 0.0,
    coordinate_system TEXT NOT NULL DEFAULT 'local'
);
CREATE TABLE IF NOT EXISTS surface_loads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    load_tag    INTEGER NOT NULL,
    surface_tag INTEGER NOT NULL,
    qx          REAL NOT NULL DEFAULT 0.0,
    qy          REAL NOT NULL DEFAULT 0.0,
    qz          REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS plate_surface_loads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    load_tag  INTEGER NOT NULL,
    plate_tag INTEGER NOT NULL,
    qx        REAL NOT NULL DEFAULT 0.0,
    qy        REAL NOT NULL DEFAULT 0.0,
    qz        REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS plate_edge_supports (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_tag INTEGER NOT NULL,
    edge      TEXT NOT NULL,
    fixities  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS combinations (
    tag        INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    combo_type TEXT NOT NULL,
    factors    TEXT NOT NULL DEFAULT '{}'
);
"""


def _ensure_schema_migrations(cur: sqlite3.Cursor) -> None:
    """Ajoute les colonnes manquantes aux anciens fichiers projet."""
    element_cols = {
        str(row[1])
        for row in cur.execute("PRAGMA table_info(elements)")
    }
    if "orientation_vector" not in element_cols:
        cur.execute("ALTER TABLE elements ADD COLUMN orientation_vector TEXT DEFAULT NULL")
    if "roll_angle_deg" not in element_cols:
        cur.execute(
            "ALTER TABLE elements "
            "ADD COLUMN roll_angle_deg REAL NOT NULL DEFAULT 0.0"
        )

    surface_cols = {
        str(row[1])
        for row in cur.execute("PRAGMA table_info(surface_elements)")
    }
    if "formulation" not in surface_cols:
        cur.execute("ALTER TABLE surface_elements ADD COLUMN formulation TEXT DEFAULT NULL")

    element_load_cols = {
        str(row[1])
        for row in cur.execute("PRAGMA table_info(element_loads)")
    }
    if "coordinate_system" not in element_load_cols:
        cur.execute(
            "ALTER TABLE element_loads "
            "ADD COLUMN coordinate_system TEXT NOT NULL DEFAULT 'local'"
        )

    plate_region_cols = {
        str(row[1])
        for row in cur.execute("PRAGMA table_info(plate_regions)")
    }
    if "mesh_mode" not in plate_region_cols:
        cur.execute(
            "ALTER TABLE plate_regions "
            "ADD COLUMN mesh_mode TEXT NOT NULL DEFAULT 'user'"
        )


def save_project(project: ProjectModel, path: str | Path) -> None:
    """Sauvegarde le projet dans un fichier SQLite.

    Args:
        project: Modèle du projet à sauvegarder.
        path: Chemin du fichier .db.
    """
    import json

    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.executescript(_SCHEMA_SQL)
        _ensure_schema_migrations(cur)

        # Vider les tables existantes
        for table in (
            "project", "nodes", "materials", "sections",
            "elements", "surface_elements", "plate_regions",
            "loads", "nodal_loads", "element_loads", "surface_loads",
            "plate_surface_loads", "plate_edge_supports", "combinations",
        ):
            cur.execute(f"DELETE FROM {table}")

        # Métadonnées projet
        cur.execute("INSERT INTO project VALUES (?, ?)", ("name", project.name))
        cur.execute("INSERT INTO project VALUES (?, ?)", ("description", project.description))
        cur.execute(
            "INSERT INTO project VALUES (?, ?)",
            ("grid", json.dumps(project.grid.to_dict())),
        )

        # Nœuds
        for n in project.nodes.values():
            fix = n.fixities if len(n.fixities) == 6 else (0, 0, 0, 0, 0, 0)
            cur.execute(
                "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (n.tag, n.x, n.y, n.z,
                 fix[0], fix[1], fix[2], fix[3], fix[4], fix[5],
                 json.dumps(n.boundary_data)),
            )

        # Matériaux
        for m in project.materials.values():
            cur.execute(
                "INSERT INTO materials VALUES (?, ?, ?, ?, ?)",
                (m.tag, m.name, m.material_type, m.grade, json.dumps(m.properties)),
            )

        # Sections
        for s in project.sections.values():
            cur.execute(
                "INSERT INTO sections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (s.tag, s.name, s.section_type, s.material_tag,
                 json.dumps(s.properties), s.area, s.inertia_y, s.inertia_z),
            )

        # Éléments
        for e in project.elements.values():
            cur.execute(
                "INSERT INTO elements VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    e.tag,
                    e.node_i,
                    e.node_j,
                    e.section_tag,
                    e.element_type,
                    json.dumps(list(e.orientation_vector)) if e.orientation_vector else None,
                    e.roll_angle_deg,
                ),
            )

        # Éléments surfaciques
        for surface in project.surface_elements.values():
            cur.execute(
                "INSERT INTO surface_elements VALUES (?, ?, ?, ?, ?)",
                (
                    surface.tag,
                    json.dumps(list(surface.node_tags)),
                    surface.section_tag,
                    surface.surface_type,
                    surface.formulation,
                ),
            )

        for plate in project.plate_regions.values():
            cur.execute(
                "INSERT INTO plate_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plate.tag,
                    plate.name,
                    json.dumps(list(plate.corner_node_tags)),
                    plate.section_tag,
                    plate.mesh_nx,
                    plate.mesh_ny,
                    normalize_plate_mesh_mode(getattr(plate, "mesh_mode", None)),
                    plate.formulation,
                ),
            )

        # Cas de charges
        for lc in project.loads.values():
            cur.execute(
                "INSERT INTO loads VALUES (?, ?, ?, ?)",
                (lc.tag, lc.name, lc.load_type, lc.category),
            )

        # Charges nodales
        for nl in project.nodal_loads:
            cur.execute(
                "INSERT INTO nodal_loads (load_tag, node_tag, fx, fy, fz, mx, my, mz) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (nl.load_tag, nl.node_tag, nl.fx, nl.fy, nl.fz,
                 nl.mx, nl.my, nl.mz),
            )

        # Charges réparties
        for el in project.element_loads:
            cur.execute(
                "INSERT INTO element_loads "
                "(load_tag, element_tag, wx, wy, wz, coordinate_system) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    el.load_tag,
                    el.element_tag,
                    el.wx,
                    el.wy,
                    el.wz,
                    el.coordinate_system,
                ),
            )

        for sl in project.surface_loads:
            cur.execute(
                "INSERT INTO surface_loads (load_tag, surface_tag, qx, qy, qz) "
                "VALUES (?, ?, ?, ?, ?)",
                (sl.load_tag, sl.surface_tag, sl.qx, sl.qy, sl.qz),
            )

        for pl in project.plate_surface_loads:
            cur.execute(
                "INSERT INTO plate_surface_loads (load_tag, plate_tag, qx, qy, qz) "
                "VALUES (?, ?, ?, ?, ?)",
                (pl.load_tag, pl.plate_tag, pl.qx, pl.qy, pl.qz),
            )

        for support in project.plate_edge_supports:
            cur.execute(
                "INSERT INTO plate_edge_supports (plate_tag, edge, fixities) "
                "VALUES (?, ?, ?)",
                (
                    support.plate_tag,
                    support.edge,
                    json.dumps(list(support.fixities)),
                ),
            )

        # Combinaisons
        for c in project.combinations.values():
            cur.execute(
                "INSERT INTO combinations VALUES (?, ?, ?, ?)",
                (c.tag, c.name, c.combo_type, json.dumps(c.factors)),
            )

        conn.commit()
    finally:
        conn.close()

    project.file_path = str(path)


def load_project(path: str | Path) -> ProjectModel:
    """Charge un projet depuis un fichier SQLite.

    Args:
        path: Chemin du fichier .db.

    Returns:
        Instance ProjectModel chargée.
    """
    import json

    path = Path(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.executescript(_SCHEMA_SQL)
        _ensure_schema_migrations(cur)

        project = ProjectModel(file_path=str(path))

        # Métadonnées
        for row in cur.execute("SELECT key, value FROM project"):
            if row["key"] == "name":
                project.name = row["value"]
            elif row["key"] == "description":
                project.description = row["value"]
            elif row["key"] == "grid":
                project.grid = Grid3DData.from_dict(json.loads(row["value"]))

        # Nœuds
        for row in cur.execute("SELECT * FROM nodes"):
            fixities = (
                row["fix_ux"], row["fix_uy"], row["fix_uz"],
                row["fix_rx"], row["fix_ry"], row["fix_rz"],
            )
            bd_raw = row["boundary_data"] if "boundary_data" in row.keys() else "{}"
            project.nodes[row["tag"]] = NodeData(
                tag=row["tag"], x=row["x"], y=row["y"], z=row["z"],
                fixities=fixities,
                boundary_data=json.loads(bd_raw),
            )

        # Matériaux
        for row in cur.execute("SELECT * FROM materials"):
            project.materials[row["tag"]] = MaterialData(
                tag=row["tag"], name=row["name"],
                material_type=row["material_type"], grade=row["grade"],
                properties=json.loads(row["properties"]),
            )

        # Sections
        for row in cur.execute("SELECT * FROM sections"):
            project.sections[row["tag"]] = SectionData(
                tag=row["tag"], name=row["name"],
                section_type=row["section_type"],
                material_tag=row["material_tag"],
                properties=json.loads(row["properties"]),
                area=row["area"], inertia_y=row["inertia_y"],
                inertia_z=row["inertia_z"],
            )

        # Éléments
        for row in cur.execute("SELECT * FROM elements"):
            raw_orientation = (
                row["orientation_vector"] if "orientation_vector" in row.keys() else None
            )
            orientation_vector = None
            if raw_orientation:
                orientation_vector = tuple(
                    float(value) for value in json.loads(raw_orientation)
                )
            project.elements[row["tag"]] = ElementData(
                tag=row["tag"], node_i=row["node_i"], node_j=row["node_j"],
                section_tag=row["section_tag"],
                element_type=row["element_type"],
                orientation_vector=orientation_vector,
                roll_angle_deg=(
                    float(row["roll_angle_deg"])
                    if "roll_angle_deg" in row.keys() else 0.0
                ),
            )

        # Éléments surfaciques
        for row in cur.execute("SELECT * FROM surface_elements"):
            project.surface_elements[row["tag"]] = SurfaceElementData(
                tag=row["tag"],
                node_tags=tuple(int(tag) for tag in json.loads(row["node_tags"])),
                section_tag=row["section_tag"],
                surface_type=row["surface_type"],
                formulation=(
                    row["formulation"] if "formulation" in row.keys() else None
                ),
            )

        for row in cur.execute("SELECT * FROM plate_regions"):
            section = project.sections.get(row["section_tag"])
            saved_formulation = normalize_surface_formulation(row["formulation"])
            effective_formulation = (
                section.surface_formulation
                if section is not None and section.is_surface
                else saved_formulation
            )
            project.plate_regions[row["tag"]] = PlateRegionData(
                tag=row["tag"],
                name=row["name"],
                corner_node_tags=tuple(
                    int(tag) for tag in json.loads(row["corner_node_tags"])
                ),
                section_tag=row["section_tag"],
                mesh_nx=row["mesh_nx"],
                mesh_ny=row["mesh_ny"],
                mesh_mode=normalize_plate_mesh_mode(
                    row["mesh_mode"] if "mesh_mode" in row.keys() else PLATE_MESH_MODE_USER
                ),
                formulation=effective_formulation,
            )

        # Cas de charges
        for row in cur.execute("SELECT * FROM loads"):
            project.loads[row["tag"]] = LoadData(
                tag=row["tag"], name=row["name"],
                load_type=row["load_type"], category=row["category"],
            )

        # Charges nodales
        for row in cur.execute("SELECT * FROM nodal_loads"):
            project.nodal_loads.append(NodalLoad(
                load_tag=row["load_tag"], node_tag=row["node_tag"],
                fx=row["fx"], fy=row["fy"],
                fz=row.get("fz", 0.0) if hasattr(row, 'get') else (row["fz"] if "fz" in row.keys() else 0.0),
                mx=row.get("mx", 0.0) if hasattr(row, 'get') else (row["mx"] if "mx" in row.keys() else 0.0),
                my=row.get("my", 0.0) if hasattr(row, 'get') else (row["my"] if "my" in row.keys() else 0.0),
                mz=row["mz"],
            ))

        # Charges réparties
        for row in cur.execute("SELECT * FROM element_loads"):
            project.element_loads.append(ElementLoad(
                load_tag=row["load_tag"], element_tag=row["element_tag"],
                wx=row["wx"], wy=row["wy"],
                wz=row.get("wz", 0.0) if hasattr(row, 'get') else (row["wz"] if "wz" in row.keys() else 0.0),
                coordinate_system=(
                    row["coordinate_system"]
                    if "coordinate_system" in row.keys()
                    else "local"
                ),
            ))

        for row in cur.execute("SELECT * FROM surface_loads"):
            project.surface_loads.append(SurfaceLoad(
                load_tag=row["load_tag"], surface_tag=row["surface_tag"],
                qx=row["qx"], qy=row["qy"],
                qz=row.get("qz", 0.0) if hasattr(row, 'get') else (row["qz"] if "qz" in row.keys() else 0.0),
            ))

        for row in cur.execute("SELECT * FROM plate_surface_loads"):
            project.plate_surface_loads.append(PlateSurfaceLoadData(
                load_tag=row["load_tag"], plate_tag=row["plate_tag"],
                qx=row["qx"], qy=row["qy"],
                qz=row["qz"],
            ))

        for row in cur.execute("SELECT * FROM plate_edge_supports"):
            fixities = tuple(int(value) for value in json.loads(row["fixities"]))
            project.plate_edge_supports.append(PlateEdgeSupportData(
                plate_tag=row["plate_tag"],
                edge=row["edge"],
                fixities=fixities,
            ))

        # Combinaisons
        for row in cur.execute("SELECT * FROM combinations"):
            factors = json.loads(row["factors"])
            # Convertir les clés string → int
            factors = {int(k): v for k, v in factors.items()}
            project.combinations[row["tag"]] = CombinationData(
                tag=row["tag"], name=row["name"],
                combo_type=row["combo_type"], factors=factors,
            )

        return project
    finally:
        conn.close()
