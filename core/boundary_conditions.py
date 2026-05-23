"""Boundary condition models for structural nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DOF(Enum):
    """DOF."""
    UX = 0   # Translation along X
    UY = 1   # Translation along Y
    UZ = 2   # Translation along Z
    RX = 3   # Rotation autour X
    RY = 4   # Rotation autour Y
    RZ = 5   # Rotation around Z


# French names for GUI display
DOF_LABELS: dict[DOF, str] = {
    DOF.UX: "Translation X (Ux)",
    DOF.UY: "Translation Y (Uy)",
    DOF.UZ: "Translation Z (Uz)",
    DOF.RX: "Rotation X (Rx)",
    DOF.RY: "Rotation Y (Ry)",
    DOF.RZ: "Rotation Z (Rz)",
}

# Short names for the status bar / tables
DOF_SHORT: dict[DOF, str] = {
    DOF.UX: "Ux", DOF.UY: "Uy", DOF.UZ: "Uz",
    DOF.RX: "Rx", DOF.RY: "Ry", DOF.RZ: "Rz",
}


class BoundaryType(Enum):
    """Enumeration of boundary type."""
    FREE = "free"                     # Free (no restraint)
    ENCASTREMENT = "encastrement"     # Fully restrained
    ROTULE = "rotule"                 # Translations restrained, rotations free
    GLISSANT_X = "glissant_x"        # Free in X, restrained in Y and Z
    GLISSANT_Y = "glissant_y"        # Free in Y, restrained in X and Z
    GLISSANT_Z = "glissant_z"        # Free in Z, restrained in X and Y
    APPUI_VERTICAL = "appui_vertical" # Only Uz restrained
    APPUI_PLAN_XY = "appui_plan_xy"  # Uz + Rx + Ry restrained (slab)
    ROTULE_GLISSIERE = "rotule_glissiere"  # Guided in X, all restrained except Ux
    BLOCAGE_ROTATION = "blocage_rotation"  # Rotations restrained, translations free
    CUSTOM = "custom"                 # Custom


# Predefined fixities: tuple of 6 values (1=restrained, 0=free)
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
    BoundaryType.CUSTOM:            (0, 0, 0, 0, 0, 0),  # default is free
}

# French names for GUI display
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

# Icons/symbols for the 3D view
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
    """Spring stiffness."""
    kx: float = 0.0   # Raideur translation X (kN/m)
    ky: float = 0.0   # Raideur translation Y (kN/m)
    kz: float = 0.0   # Raideur translation Z (kN/m)
    krx: float = 0.0  # Raideur rotation X (kN·m/rad)
    kry: float = 0.0  # Raideur rotation Y (kN·m/rad)
    krz: float = 0.0  # Raideur rotation Z (kN·m/rad)

    @property
    def has_springs(self) -> bool:
        """Return whether springs."""
        return any(k > 0.0 for k in self.as_tuple())

    def as_tuple(self) -> tuple[float, ...]:
        """Return the values as a tuple."""
        return (self.kx, self.ky, self.kz, self.krx, self.kry, self.krz)

    def to_dict(self) -> dict[str, float]:
        """Return a serializable dictionary."""
        return {
            "kx": self.kx, "ky": self.ky, "kz": self.kz,
            "krx": self.krx, "kry": self.kry, "krz": self.krz,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> SpringStiffness:
        """Build an instance from serialized data."""
        return cls(
            kx=d.get("kx", 0.0), ky=d.get("ky", 0.0), kz=d.get("kz", 0.0),
            krx=d.get("krx", 0.0), kry=d.get("kry", 0.0), krz=d.get("krz", 0.0),
        )


@dataclass
class BoundaryCondition:
    """Boundary condition."""
    bc_type: BoundaryType = BoundaryType.FREE
    fixities: tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    springs: SpringStiffness = field(default_factory=SpringStiffness)
    name: str = ""  # Optional custom name

    @property
    def is_free(self) -> bool:
        """Return whether free."""
        return all(f == 0 for f in self.fixities) and not self.springs.has_springs

    @property
    def is_fixed(self) -> bool:
        """Return whether fixed."""
        return all(f == 1 for f in self.fixities)

    @property
    def blocked_dofs(self) -> list[DOF]:
        """Handle blocked DOFs."""
        return [DOF(i) for i, f in enumerate(self.fixities) if f == 1]

    @property
    def free_dofs(self) -> list[DOF]:
        """Handle free DOFs."""
        return [DOF(i) for i, f in enumerate(self.fixities) if f == 0]

    @property
    def label(self) -> str:
        """Return the display label."""
        if self.name:
            return self.name
        return BOUNDARY_LABELS.get(self.bc_type, "Inconnu")

    @property
    def symbol(self) -> str:
        """Return the display symbol."""
        return BOUNDARY_SYMBOLS.get(self.bc_type, "")

    def summary(self) -> str:
        """Return a short textual summary."""
        blocked = [DOF_SHORT[d] for d in self.blocked_dofs]
        if not blocked:
            return "Libre"
        return "Bloqué : " + ", ".join(blocked)

    def to_dict(self) -> dict:
        """Return a serializable dictionary."""
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
        """Build an instance from serialized data."""
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
    """Create boundary."""
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
    """Detect boundary type."""
    fix = tuple(fixities[:6])
    for bc_type, predefined in PREDEFINED_FIXITIES.items():
        if bc_type == BoundaryType.CUSTOM:
            continue
        if fix == predefined:
            return bc_type
    return BoundaryType.CUSTOM
