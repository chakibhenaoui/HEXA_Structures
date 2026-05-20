"""
Conditions aux limites pour les nœuds structurels.

Modèle nativement 3D : 6 DDL par nœud (Ux, Uy, Uz, Rx, Ry, Rz).
Appuis prédéfinis + mode personnalisé + appuis élastiques (ressorts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DOF(Enum):
    """Degrés de liberté d'un nœud 3D."""
    UX = 0   # Translation selon X
    UY = 1   # Translation selon Y
    UZ = 2   # Translation selon Z
    RX = 3   # Rotation autour de X
    RY = 4   # Rotation autour de Y
    RZ = 5   # Rotation autour de Z


# Noms français pour l'affichage GUI
DOF_LABELS: dict[DOF, str] = {
    DOF.UX: "Translation X (Ux)",
    DOF.UY: "Translation Y (Uy)",
    DOF.UZ: "Translation Z (Uz)",
    DOF.RX: "Rotation X (Rx)",
    DOF.RY: "Rotation Y (Ry)",
    DOF.RZ: "Rotation Z (Rz)",
}

# Noms courts pour la barre de statut / tableaux
DOF_SHORT: dict[DOF, str] = {
    DOF.UX: "Ux", DOF.UY: "Uy", DOF.UZ: "Uz",
    DOF.RX: "Rx", DOF.RY: "Ry", DOF.RZ: "Rz",
}


class BoundaryType(Enum):
    """Types d'appuis prédéfinis."""
    FREE = "free"                     # Libre (aucun blocage)
    ENCASTREMENT = "encastrement"     # Tout bloqué
    ROTULE = "rotule"                 # Translations bloquées, rotations libres
    GLISSANT_X = "glissant_x"        # Libre en X, bloqué en Y et Z
    GLISSANT_Y = "glissant_y"        # Libre en Y, bloqué en X et Z
    GLISSANT_Z = "glissant_z"        # Libre en Z, bloqué en X et Y
    APPUI_VERTICAL = "appui_vertical" # Seul Uz bloqué
    APPUI_PLAN_XY = "appui_plan_xy"  # Uz + Rx + Ry bloqués (dalle)
    ROTULE_GLISSIERE = "rotule_glissiere"  # Guidé en X, tout bloqué sauf Ux
    BLOCAGE_ROTATION = "blocage_rotation"  # Rotations bloquées, translations libres
    CUSTOM = "custom"                 # Personnalisé


# Fixités prédéfinies : tuple de 6 valeurs (1=bloqué, 0=libre)
# Ordre : (Ux, Uy, Uz, Rx, Ry, Rz)
PREDEFINED_FIXITIES: dict[BoundaryType, tuple[int, ...]] = {
    BoundaryType.FREE:              (0, 0, 0, 0, 0, 0),
    BoundaryType.ENCASTREMENT:      (1, 1, 1, 1, 1, 1),
    BoundaryType.ROTULE:            (1, 1, 1, 0, 0, 0),
    BoundaryType.GLISSANT_X:        (0, 1, 1, 0, 0, 0),
    BoundaryType.GLISSANT_Y:        (1, 0, 1, 0, 0, 0),
    BoundaryType.GLISSANT_Z:        (1, 1, 0, 0, 0, 0),
    BoundaryType.APPUI_VERTICAL:    (0, 0, 1, 0, 0, 0),
    BoundaryType.APPUI_PLAN_XY:     (0, 0, 1, 1, 1, 0),
    BoundaryType.ROTULE_GLISSIERE:  (0, 1, 1, 1, 1, 1),
    BoundaryType.BLOCAGE_ROTATION:  (0, 0, 0, 1, 1, 1),
    BoundaryType.CUSTOM:            (0, 0, 0, 0, 0, 0),  # défaut libre
}

# Noms français pour l'affichage GUI
BOUNDARY_LABELS: dict[BoundaryType, str] = {
    BoundaryType.FREE:              "Libre",
    BoundaryType.ENCASTREMENT:      "Encastrement",
    BoundaryType.ROTULE:            "Rotule (appui simple)",
    BoundaryType.GLISSANT_X:        "Appui glissant X",
    BoundaryType.GLISSANT_Y:        "Appui glissant Y",
    BoundaryType.GLISSANT_Z:        "Appui glissant Z",
    BoundaryType.APPUI_VERTICAL:    "Appui vertical (Uz)",
    BoundaryType.APPUI_PLAN_XY:     "Appui plan XY (dalle)",
    BoundaryType.ROTULE_GLISSIERE:  "Rotule sur glissière (X)",
    BoundaryType.BLOCAGE_ROTATION:  "Blocage rotation seule",
    BoundaryType.CUSTOM:            "Personnalisé",
}

# Icônes/symboles pour la vue 3D
BOUNDARY_SYMBOLS: dict[BoundaryType, str] = {
    BoundaryType.FREE:              "",
    BoundaryType.ENCASTREMENT:      "▬",
    BoundaryType.ROTULE:            "△",
    BoundaryType.GLISSANT_X:        "○→",
    BoundaryType.GLISSANT_Y:        "○↑",
    BoundaryType.GLISSANT_Z:        "○↕",
    BoundaryType.APPUI_VERTICAL:    "△↕",
    BoundaryType.APPUI_PLAN_XY:     "▽",
    BoundaryType.ROTULE_GLISSIERE:  "○",
    BoundaryType.BLOCAGE_ROTATION:  "⊗",
    BoundaryType.CUSTOM:            "⚙",
}


@dataclass
class SpringStiffness:
    """Raideurs élastiques pour appuis sur ressorts.

    Unités internes : kN/m (translations), kN·m/rad (rotations).
    """
    kx: float = 0.0   # Raideur translation X (kN/m)
    ky: float = 0.0   # Raideur translation Y (kN/m)
    kz: float = 0.0   # Raideur translation Z (kN/m)
    krx: float = 0.0  # Raideur rotation X (kN·m/rad)
    kry: float = 0.0  # Raideur rotation Y (kN·m/rad)
    krz: float = 0.0  # Raideur rotation Z (kN·m/rad)

    @property
    def has_springs(self) -> bool:
        """Vérifie si au moins un ressort est défini."""
        return any(k > 0.0 for k in self.as_tuple())

    def as_tuple(self) -> tuple[float, ...]:
        """Retourne les 6 raideurs sous forme de tuple."""
        return (self.kx, self.ky, self.kz, self.krx, self.kry, self.krz)

    def to_dict(self) -> dict[str, float]:
        """Sérialisation pour SQLite/JSON."""
        return {
            "kx": self.kx, "ky": self.ky, "kz": self.kz,
            "krx": self.krx, "kry": self.kry, "krz": self.krz,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> SpringStiffness:
        """Désérialisation depuis dict."""
        return cls(
            kx=d.get("kx", 0.0), ky=d.get("ky", 0.0), kz=d.get("kz", 0.0),
            krx=d.get("krx", 0.0), kry=d.get("kry", 0.0), krz=d.get("krz", 0.0),
        )


@dataclass
class BoundaryCondition:
    """Condition aux limites complète d'un nœud.

    Combine un type prédéfini (ou personnalisé), les fixités 6 DDL,
    et des raideurs élastiques optionnelles (ressorts).
    """
    bc_type: BoundaryType = BoundaryType.FREE
    fixities: tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    springs: SpringStiffness = field(default_factory=SpringStiffness)
    name: str = ""  # Nom personnalisé optionnel

    @property
    def is_free(self) -> bool:
        """Le nœud est-il entièrement libre ?"""
        return all(f == 0 for f in self.fixities) and not self.springs.has_springs

    @property
    def is_fixed(self) -> bool:
        """Le nœud est-il entièrement bloqué (encastrement) ?"""
        return all(f == 1 for f in self.fixities)

    @property
    def blocked_dofs(self) -> list[DOF]:
        """Liste des DDL bloqués."""
        return [DOF(i) for i, f in enumerate(self.fixities) if f == 1]

    @property
    def free_dofs(self) -> list[DOF]:
        """Liste des DDL libres."""
        return [DOF(i) for i, f in enumerate(self.fixities) if f == 0]

    @property
    def label(self) -> str:
        """Label pour l'affichage (nom personnalisé ou type prédéfini)."""
        if self.name:
            return self.name
        return BOUNDARY_LABELS.get(self.bc_type, "Inconnu")

    @property
    def symbol(self) -> str:
        """Symbole pour la vue 3D."""
        return BOUNDARY_SYMBOLS.get(self.bc_type, "")

    def summary(self) -> str:
        """Résumé textuel des DDL bloqués."""
        blocked = [DOF_SHORT[d] for d in self.blocked_dofs]
        if not blocked:
            return "Libre"
        return "Bloqué : " + ", ".join(blocked)

    def to_dict(self) -> dict:
        """Sérialisation pour SQLite/JSON."""
        d = {
            "bc_type": self.bc_type.value,
            "fixities": list(self.fixities),
            "name": self.name,
        }
        if self.springs.has_springs:
            d["springs"] = self.springs.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> BoundaryCondition:
        """Désérialisation depuis dict."""
        springs = SpringStiffness()
        if "springs" in d:
            springs = SpringStiffness.from_dict(d["springs"])
        return cls(
            bc_type=BoundaryType(d.get("bc_type", "free")),
            fixities=tuple(d.get("fixities", (0, 0, 0, 0, 0, 0))),
            springs=springs,
            name=d.get("name", ""),
        )


def create_boundary(bc_type: BoundaryType,
                     name: str = "",
                     custom_fixities: tuple[int, ...] | None = None,
                     springs: SpringStiffness | None = None) -> BoundaryCondition:
    """Crée une condition aux limites.

    Args:
        bc_type: Type d'appui prédéfini ou CUSTOM.
        name: Nom personnalisé optionnel.
        custom_fixities: Fixités pour le mode CUSTOM (6 valeurs 0/1).
        springs: Raideurs élastiques optionnelles.

    Returns:
        BoundaryCondition configurée.
    """
    if bc_type == BoundaryType.CUSTOM and custom_fixities is not None:
        fixities = tuple(custom_fixities[:6])
    else:
        fixities = PREDEFINED_FIXITIES[bc_type]

    return BoundaryCondition(
        bc_type=bc_type,
        fixities=fixities,
        springs=springs or SpringStiffness(),
        name=name,
    )


def detect_boundary_type(fixities: tuple[int, ...]) -> BoundaryType:
    """Détecte le type d'appui à partir des fixités.

    Cherche une correspondance dans les types prédéfinis.
    Retourne CUSTOM si aucune correspondance.
    """
    fix = tuple(fixities[:6])
    for bc_type, predefined in PREDEFINED_FIXITIES.items():
        if bc_type == BoundaryType.CUSTOM:
            continue
        if fix == predefined:
            return bc_type
    return BoundaryType.CUSTOM
