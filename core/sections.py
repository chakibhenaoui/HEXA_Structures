"""Structural section definitions and geometric properties."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from utils.units import CM2_TO_M2, CM4_TO_M4, MM_TO_M


STEEL_DENSITY_KG_M3 = 7850.0


# ═══════════════════════════════════════════════════════════════════════════
#  Rectangular section
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RectangularSection:
    """Rectangular section."""

    b: float
    h: float

    @property
    def area(self) -> float:
        """Return the section area."""
        return self.b * self.h

    @property
    def inertia_y(self) -> float:
        """Return the second moment of area about the local Y axis."""
        return self.b * self.h**3 / 12

    @property
    def inertia_z(self) -> float:
        """Return the second moment of area about the local Z axis."""
        return self.h * self.b**3 / 12

    @property
    def wel_y(self) -> float:
        """Return the elastic section modulus about the local Y axis."""
        return self.b * self.h**2 / 6

    @property
    def wpl_y(self) -> float:
        """Module plastique de flexion axe Y (m³)."""
        return self.b * self.h**2 / 4


# ═══════════════════════════════════════════════════════════════════════════
#  T-section
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TSection:
    """Tsection."""

    bw: float  # web width
    hw: float  # web height (below flange)
    bf: float  # largeur table
    hf: float  # flange thickness

    @property
    def h(self) -> float:
        """Hauteur totale (m)."""
        return self.hw + self.hf

    @property
    def area(self) -> float:
        """Return the section area."""
        return self.bw * self.hw + self.bf * self.hf

    @property
    def centroid_y(self) -> float:
        """Handle centroid y."""
        a_web = self.bw * self.hw
        a_flange = self.bf * self.hf
        y_web = self.hw / 2
        y_flange = self.hw + self.hf / 2
        return (a_web * y_web + a_flange * y_flange) / self.area

    @property
    def inertia_y(self) -> float:
        """Return the second moment of area about the local Y axis."""
        yg = self.centroid_y

        # Web
        iy_web = self.bw * self.hw**3 / 12
        d_web = yg - self.hw / 2
        iy_web += self.bw * self.hw * d_web**2

        # Table
        iy_flange = self.bf * self.hf**3 / 12
        d_flange = (self.hw + self.hf / 2) - yg
        iy_flange += self.bf * self.hf * d_flange**2

        return iy_web + iy_flange


# ═══════════════════════════════════════════════════════════════════════════
#  European steel profile
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SteelProfile:
    """Steel profile."""

    name: str
    family: str       # "IPE", "HEA", "HEB", "HEM", "UPN"
    h: float          # hauteur totale (m)
    b: float          # largeur semelle (m)
    tw: float         # web thickness (m)
    tf: float         # flange thickness (m)
    area: float       # aire (m²)
    inertia_y: float  # second moment of area about the major axis (m4)
    inertia_z: float  # second moment of area about the minor axis (m4)
    wel_y: float      # elastic modulus about the major axis (m3)
    wpl_y: float      # plastic modulus about the major axis (m3)
    mass: float       # linear mass (kg/m)
    shape: str = "i_section"
    standard: str = "EN 10365"
    source: str = "bundled"
    dimensions: dict[str, float] = field(default_factory=dict)
    wel_z: float = 0.0
    wpl_z: float = 0.0
    inertia_torsion: float = 0.0

    def dimension(self, key: str, default: float = 0.0) -> float:
        """Return a named geometric dimension in meters."""
        return float(self.dimensions.get(key, default))


@dataclass(frozen=True)
class ProfileFamilyInfo:
    """Metadata for a steel profile family."""

    code: str
    label: str
    shape: str
    standard: str
    source: str


PROFILE_FAMILY_ORDER: tuple[str, ...] = (
    "IPE",
    "HEA",
    "HEB",
    "HEM",
    "UPN",
    "UPE",
    "CHS",
    "SHS",
    "RHS",
    "L",
    "L unequal",
)

PROFILE_FAMILY_INFO: dict[str, ProfileFamilyInfo] = {
    "IPE": ProfileFamilyInfo("IPE", "IPE", "i_section", "EN 10365", "tabulated"),
    "HEA": ProfileFamilyInfo("HEA", "HEA", "i_section", "EN 10365", "tabulated"),
    "HEB": ProfileFamilyInfo("HEB", "HEB", "i_section", "EN 10365", "tabulated"),
    "HEM": ProfileFamilyInfo("HEM", "HEM", "i_section", "EN 10365", "theoretical_geometry"),
    "UPN": ProfileFamilyInfo("UPN", "UPN", "channel", "EN 10365", "theoretical_geometry"),
    "UPE": ProfileFamilyInfo("UPE", "UPE", "channel", "EN 10365", "theoretical_geometry"),
    "CHS": ProfileFamilyInfo("CHS", "CHS", "circular_hollow", "EN 10210/10219", "theoretical_geometry"),
    "SHS": ProfileFamilyInfo("SHS", "SHS", "rectangular_hollow", "EN 10210/10219", "theoretical_geometry"),
    "RHS": ProfileFamilyInfo("RHS", "RHS", "rectangular_hollow", "EN 10210/10219", "theoretical_geometry"),
    "L": ProfileFamilyInfo("L", "L egales", "angle_equal", "EN 10056", "theoretical_geometry"),
    "L unequal": ProfileFamilyInfo("L unequal", "L inegales", "angle_unequal", "EN 10056", "theoretical_geometry"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  Bundled profile catalog
# ═══════════════════════════════════════════════════════════════════════════

# Common IPE profiles — values from ArcelorMittal tables
# Dimensions in mm, areas in cm2, second moments in cm4, moduli in cm3, mass in kg/m
_IPE_RAW: list[tuple] = [
    # (name, h, b, tw, tf, A, Iy, Iz, Wel_y, Wpl_y, mass)
    ("IPE 100", 100, 55, 4.1, 5.7, 10.3, 171, 15.9, 34.2, 39.4, 8.1),
    ("IPE 120", 120, 64, 4.4, 6.3, 13.2, 318, 27.7, 53.0, 60.7, 10.4),
    ("IPE 140", 140, 73, 4.7, 6.9, 16.4, 541, 44.9, 77.3, 88.3, 12.9),
    ("IPE 160", 160, 82, 5.0, 7.4, 20.1, 869, 68.3, 109, 124, 15.8),
    ("IPE 180", 180, 91, 5.3, 8.0, 23.9, 1320, 101, 146, 166, 18.8),
    ("IPE 200", 200, 100, 5.6, 8.5, 28.5, 1940, 142, 194, 221, 22.4),
    ("IPE 220", 220, 110, 5.9, 9.2, 33.4, 2770, 205, 252, 285, 26.2),
    ("IPE 240", 240, 120, 6.2, 9.8, 39.1, 3890, 284, 324, 367, 30.7),
    ("IPE 270", 270, 135, 6.6, 10.2, 45.9, 5790, 420, 429, 484, 36.1),
    ("IPE 300", 300, 150, 7.1, 10.7, 53.8, 8360, 604, 557, 628, 42.2),
    ("IPE 330", 330, 160, 7.5, 11.5, 62.6, 11770, 788, 713, 804, 49.1),
    ("IPE 360", 360, 170, 8.0, 12.7, 72.7, 16270, 1040, 904, 1019, 57.1),
    ("IPE 400", 400, 180, 8.6, 13.5, 84.5, 23130, 1320, 1156, 1307, 66.3),
    ("IPE 450", 450, 190, 9.4, 14.6, 98.8, 33740, 1680, 1500, 1702, 77.6),
    ("IPE 500", 500, 200, 10.2, 16.0, 116, 48200, 2140, 1928, 2194, 90.7),
    ("IPE 550", 550, 210, 11.1, 17.2, 134, 67120, 2670, 2441, 2787, 106),
    ("IPE 600", 600, 220, 12.0, 19.0, 156, 92080, 3390, 3069, 3512, 122),
]

_HEA_RAW: list[tuple] = [
    ("HEA 100", 96, 100, 5.0, 8.0, 21.2, 349, 134, 72.8, 83.0, 16.7),
    ("HEA 120", 114, 120, 5.0, 8.0, 25.3, 606, 231, 106, 119, 19.9),
    ("HEA 140", 133, 140, 5.5, 8.5, 31.4, 1030, 389, 155, 174, 24.7),
    ("HEA 160", 152, 160, 6.0, 9.0, 38.8, 1670, 616, 220, 245, 30.4),
    ("HEA 180", 171, 180, 6.0, 9.5, 45.3, 2510, 925, 294, 325, 35.5),
    ("HEA 200", 190, 200, 6.5, 10.0, 53.8, 3690, 1340, 389, 430, 42.3),
    ("HEA 220", 210, 220, 7.0, 11.0, 64.3, 5410, 1950, 515, 569, 50.5),
    ("HEA 240", 230, 240, 7.5, 12.0, 76.8, 7760, 2770, 675, 745, 60.3),
    ("HEA 260", 250, 260, 7.5, 12.5, 86.8, 10450, 3670, 836, 920, 68.2),
    ("HEA 280", 270, 280, 8.0, 13.0, 97.3, 13670, 4760, 1010, 1110, 76.4),
    ("HEA 300", 290, 300, 8.5, 14.0, 113, 18260, 6310, 1260, 1383, 88.3),
    ("HEA 320", 310, 300, 9.0, 15.5, 124, 22930, 6990, 1479, 1628, 97.6),
    ("HEA 340", 330, 300, 9.5, 16.5, 133, 27690, 7440, 1678, 1850, 105),
    ("HEA 360", 350, 300, 10.0, 17.5, 143, 33090, 7890, 1891, 2088, 112),
    ("HEA 400", 390, 300, 11.0, 19.0, 159, 45070, 8560, 2311, 2562, 125),
]

_HEB_RAW: list[tuple] = [
    ("HEB 100", 100, 100, 6.0, 10.0, 26.0, 450, 167, 89.9, 104, 20.4),
    ("HEB 120", 120, 120, 6.5, 11.0, 34.0, 864, 318, 144, 165, 26.7),
    ("HEB 140", 140, 140, 7.0, 12.0, 43.0, 1510, 550, 216, 246, 33.7),
    ("HEB 160", 160, 160, 8.0, 13.0, 54.3, 2490, 889, 311, 354, 42.6),
    ("HEB 180", 180, 180, 8.5, 14.0, 65.3, 3830, 1360, 426, 481, 51.2),
    ("HEB 200", 200, 200, 9.0, 15.0, 78.1, 5700, 2000, 570, 642, 61.3),
    ("HEB 220", 220, 220, 9.5, 16.0, 91.0, 8090, 2840, 736, 827, 71.5),
    ("HEB 240", 240, 240, 10.0, 17.0, 106, 11260, 3920, 938, 1053, 83.2),
    ("HEB 260", 260, 260, 10.0, 17.5, 118, 14920, 5140, 1148, 1283, 93.0),
    ("HEB 280", 280, 280, 10.5, 18.0, 131, 19270, 6590, 1376, 1534, 103),
    ("HEB 300", 300, 300, 11.0, 19.0, 149, 25170, 8560, 1678, 1869, 117),
    ("HEB 320", 320, 300, 11.5, 20.5, 161, 30820, 9240, 1926, 2149, 127),
    ("HEB 340", 340, 300, 12.0, 21.5, 171, 36660, 9690, 2156, 2408, 134),
    ("HEB 360", 360, 300, 12.5, 22.5, 181, 43190, 10140, 2400, 2683, 142),
    ("HEB 400", 400, 300, 13.5, 24.0, 198, 57680, 10820, 2884, 3232, 155),
]


def _convert_raw(raw: list[tuple], family: str) -> list[SteelProfile]:
    """Convert raw."""
    profiles = []
    for row in raw:
        name, h, b, tw, tf, a, iy, iz, wel, wpl, mass = row
        profiles.append(SteelProfile(
            name=name,
            family=family,
            h=h * MM_TO_M,
            b=b * MM_TO_M,
            tw=tw * MM_TO_M,
            tf=tf * MM_TO_M,
            area=a * CM2_TO_M2,
            inertia_y=iy * CM4_TO_M4,
            inertia_z=iz * CM4_TO_M4,
            wel_y=wel * 1e-6,   # cm³ → m³
            wpl_y=wpl * 1e-6,   # cm³ → m³
            mass=mass,
        ))
    return profiles


# Catalogues convertis
IPE_PROFILES: list[SteelProfile] = _convert_raw(_IPE_RAW, "IPE")
HEA_PROFILES: list[SteelProfile] = _convert_raw(_HEA_RAW, "HEA")
HEB_PROFILES: list[SteelProfile] = _convert_raw(_HEB_RAW, "HEB")


# Extended catalogue ---------------------------------------------------------

def _m(value_mm: float) -> float:
    return float(value_mm) * MM_TO_M


def _mass_from_area(area: float) -> float:
    return area * STEEL_DENSITY_KG_M3


def _default_wpl(wel: float) -> float:
    return wel * 1.10 if wel > 0.0 else 0.0


def _family_info(family: str) -> ProfileFamilyInfo:
    return PROFILE_FAMILY_INFO[family]


def _profile(
    *,
    name: str,
    family: str,
    h: float,
    b: float,
    tw: float,
    tf: float,
    area: float,
    inertia_y: float,
    inertia_z: float,
    shape: str | None = None,
    standard: str | None = None,
    source: str | None = None,
    mass: float | None = None,
    wel_y: float | None = None,
    wpl_y: float | None = None,
    wel_z: float | None = None,
    wpl_z: float | None = None,
    inertia_torsion: float = 0.0,
    dimensions: dict[str, float] | None = None,
) -> SteelProfile:
    info = _family_info(family)
    effective_wel_y = wel_y if wel_y is not None else (inertia_y / (h / 2.0) if h > 0 else 0.0)
    effective_wel_z = wel_z if wel_z is not None else (inertia_z / (b / 2.0) if b > 0 else 0.0)
    dims = {"h": h, "b": b, "tw": tw, "tf": tf}
    if dimensions:
        dims.update(dimensions)
    return SteelProfile(
        name=name,
        family=family,
        h=h,
        b=b,
        tw=tw,
        tf=tf,
        area=area,
        inertia_y=inertia_y,
        inertia_z=inertia_z,
        wel_y=effective_wel_y,
        wpl_y=wpl_y if wpl_y is not None else _default_wpl(effective_wel_y),
        mass=mass if mass is not None else _mass_from_area(area),
        shape=shape or info.shape,
        standard=standard or info.standard,
        source=source or info.source,
        dimensions=dims,
        wel_z=effective_wel_z,
        wpl_z=wpl_z if wpl_z is not None else _default_wpl(effective_wel_z),
        inertia_torsion=inertia_torsion,
    )


def _tabulated_profile(profile: SteelProfile) -> SteelProfile:
    info = _family_info(profile.family)
    return _profile(
        name=profile.name,
        family=profile.family,
        h=profile.h,
        b=profile.b,
        tw=profile.tw,
        tf=profile.tf,
        area=profile.area,
        inertia_y=profile.inertia_y,
        inertia_z=profile.inertia_z,
        wel_y=profile.wel_y,
        wpl_y=profile.wpl_y,
        mass=profile.mass,
        shape=info.shape,
        standard=info.standard,
        source=info.source,
        dimensions={
            "h": profile.h,
            "b": profile.b,
            "tw": profile.tw,
            "tf": profile.tf,
        },
    )


def _i_shape_profile(
    family: str,
    size: int,
    h_mm: float,
    b_mm: float,
    tw_mm: float,
    tf_mm: float,
) -> SteelProfile:
    h = _m(h_mm)
    b = _m(b_mm)
    tw = _m(tw_mm)
    tf = _m(tf_mm)
    web_h = max(h - 2.0 * tf, 0.0)
    area = 2.0 * b * tf + web_h * tw
    inertia_y = (b * h**3 - (b - tw) * web_h**3) / 12.0
    inertia_z = 2.0 * (tf * b**3 / 12.0) + web_h * tw**3 / 12.0
    j = (2.0 * b * tf**3 + web_h * tw**3) / 3.0
    return _profile(
        name=f"{family} {size}",
        family=family,
        h=h,
        b=b,
        tw=tw,
        tf=tf,
        area=area,
        inertia_y=inertia_y,
        inertia_z=inertia_z,
        inertia_torsion=j,
    )


def _composite_rectangles(
    rectangles: Iterable[tuple[float, float, float, float, float]],
) -> tuple[float, float, float, float, float]:
    """Return area, centroid_y, centroid_z, Iy, Iz for signed rectangles."""
    items = tuple(rectangles)
    area = sum(sign * width * height for sign, _y, _z, width, height in items)
    if area <= 0.0:
        raise ValueError("Invalid steel profile geometry.")
    cy = sum(sign * width * height * y for sign, y, _z, width, height in items) / area
    cz = sum(sign * width * height * z for sign, _y, z, width, height in items) / area
    iy = 0.0
    iz = 0.0
    for sign, y, z, width, height in items:
        signed_area = sign * width * height
        iy += sign * width * height**3 / 12.0 + signed_area * (z - cz) ** 2
        iz += sign * height * width**3 / 12.0 + signed_area * (y - cy) ** 2
    return area, cy, cz, iy, iz


def _channel_profile(
    family: str,
    size: int,
    h_mm: float,
    b_mm: float,
    tw_mm: float,
    tf_mm: float,
) -> SteelProfile:
    h = _m(h_mm)
    b = _m(b_mm)
    tw = _m(tw_mm)
    tf = _m(tf_mm)
    web_h = max(h - 2.0 * tf, 0.0)
    area, cy, cz, iy, iz = _composite_rectangles(
        (
            (1.0, tw / 2.0, h / 2.0, tw, web_h),
            (1.0, b / 2.0, tf / 2.0, b, tf),
            (1.0, b / 2.0, h - tf / 2.0, b, tf),
        )
    )
    j = (2.0 * b * tf**3 + web_h * tw**3) / 3.0
    return _profile(
        name=f"{family} {size}",
        family=family,
        h=h,
        b=b,
        tw=tw,
        tf=tf,
        area=area,
        inertia_y=iy,
        inertia_z=iz,
        inertia_torsion=j,
        dimensions={"centroid_y": cy, "centroid_z": cz},
    )


def _chs_profile(d_mm: float, t_mm: float) -> SteelProfile:
    d = _m(d_mm)
    t = _m(t_mm)
    inner = max(d - 2.0 * t, 0.0)
    area = math.pi * (d**2 - inner**2) / 4.0
    inertia = math.pi * (d**4 - inner**4) / 64.0
    j = math.pi * (d**4 - inner**4) / 32.0
    return _profile(
        name=f"CHS {d_mm:g}x{t_mm:g}",
        family="CHS",
        h=d,
        b=d,
        tw=t,
        tf=t,
        area=area,
        inertia_y=inertia,
        inertia_z=inertia,
        inertia_torsion=j,
        dimensions={"d": d, "t": t},
    )


def _rhs_profile(family: str, h_mm: float, b_mm: float, t_mm: float) -> SteelProfile:
    h = _m(h_mm)
    b = _m(b_mm)
    t = _m(t_mm)
    inner_h = max(h - 2.0 * t, 0.0)
    inner_b = max(b - 2.0 * t, 0.0)
    area = b * h - inner_b * inner_h
    iy = (b * h**3 - inner_b * inner_h**3) / 12.0
    iz = (h * b**3 - inner_h * inner_b**3) / 12.0
    name = f"{family} {h_mm:g}x{b_mm:g}x{t_mm:g}"
    if family == "SHS":
        name = f"SHS {h_mm:g}x{t_mm:g}"
    return _profile(
        name=name,
        family=family,
        h=h,
        b=b,
        tw=t,
        tf=t,
        area=area,
        inertia_y=iy,
        inertia_z=iz,
        dimensions={"t": t},
    )


def _angle_profile(family: str, h_mm: float, b_mm: float, t_mm: float) -> SteelProfile:
    h = _m(h_mm)
    b = _m(b_mm)
    t = _m(t_mm)
    area, cy, cz, iy, iz = _composite_rectangles(
        (
            (1.0, t / 2.0, h / 2.0, t, h),
            (1.0, b / 2.0, t / 2.0, b, t),
            (-1.0, t / 2.0, t / 2.0, t, t),
        )
    )
    name = f"L {h_mm:g}x{t_mm:g}" if family == "L" else f"L {h_mm:g}x{b_mm:g}x{t_mm:g}"
    return _profile(
        name=name,
        family=family,
        h=h,
        b=b,
        tw=t,
        tf=t,
        area=area,
        inertia_y=iy,
        inertia_z=iz,
        dimensions={"t": t, "centroid_y": cy, "centroid_z": cz},
    )


_HEM_DIMENSIONS: list[tuple[int, float, float, float, float]] = [
    (100, 120, 106, 12.0, 20.0),
    (120, 140, 126, 12.5, 21.0),
    (140, 160, 146, 13.0, 22.0),
    (160, 180, 166, 14.0, 23.0),
    (180, 200, 186, 14.5, 24.0),
    (200, 220, 206, 15.0, 25.0),
    (220, 240, 226, 15.5, 26.0),
    (240, 270, 248, 18.0, 32.0),
    (260, 290, 268, 18.0, 32.5),
    (280, 310, 288, 18.5, 33.0),
    (300, 340, 310, 21.0, 39.0),
    (320, 359, 309, 21.0, 40.0),
    (340, 377, 309, 21.0, 40.0),
    (360, 395, 308, 21.0, 40.0),
    (400, 432, 307, 21.0, 40.0),
]

_UPN_DIMENSIONS: list[tuple[int, float, float, float, float]] = [
    (80, 80, 45, 6.0, 8.0),
    (100, 100, 50, 6.0, 8.5),
    (120, 120, 55, 7.0, 9.0),
    (140, 140, 60, 7.0, 10.0),
    (160, 160, 65, 7.5, 10.5),
    (180, 180, 70, 8.0, 11.0),
    (200, 200, 75, 8.5, 11.5),
    (220, 220, 80, 9.0, 12.5),
    (240, 240, 85, 9.5, 13.0),
    (260, 260, 90, 10.0, 14.0),
    (280, 280, 95, 10.0, 15.0),
    (300, 300, 100, 10.0, 16.0),
    (320, 320, 100, 14.0, 17.5),
    (350, 350, 100, 14.0, 16.0),
    (380, 380, 102, 13.5, 16.0),
    (400, 400, 110, 14.0, 18.0),
]

_UPE_DIMENSIONS: list[tuple[int, float, float, float, float]] = [
    (80, 80, 50, 4.5, 7.0),
    (100, 100, 55, 5.0, 7.5),
    (120, 120, 60, 5.5, 8.0),
    (140, 140, 65, 6.0, 9.0),
    (160, 160, 70, 6.5, 10.0),
    (180, 180, 75, 7.0, 10.5),
    (200, 200, 80, 7.5, 11.0),
    (220, 220, 85, 8.0, 12.0),
    (240, 240, 90, 8.5, 13.0),
    (270, 270, 95, 9.5, 14.0),
    (300, 300, 100, 10.0, 15.0),
    (330, 330, 105, 11.0, 16.0),
    (360, 360, 110, 12.0, 17.0),
    (400, 400, 115, 13.5, 18.0),
]

_CHS_DIMENSIONS: list[tuple[float, float]] = [
    (48.3, 3.2),
    (60.3, 3.2),
    (76.1, 3.6),
    (88.9, 4.0),
    (101.6, 4.0),
    (114.3, 5.0),
    (139.7, 5.0),
    (168.3, 6.3),
    (193.7, 6.3),
    (219.1, 8.0),
    (273.0, 8.0),
    (323.9, 10.0),
]

_SHS_DIMENSIONS: list[tuple[float, float]] = [
    (40, 3),
    (50, 3),
    (60, 4),
    (80, 5),
    (100, 5),
    (120, 6.3),
    (150, 8),
    (200, 10),
    (250, 10),
]

_RHS_DIMENSIONS: list[tuple[float, float, float]] = [
    (80, 40, 4),
    (100, 50, 4),
    (120, 60, 5),
    (140, 80, 5),
    (150, 100, 6.3),
    (200, 100, 6.3),
    (200, 150, 8),
    (250, 150, 8),
    (300, 200, 10),
]

_ANGLE_EQUAL_DIMENSIONS: list[tuple[float, float]] = [
    (40, 4),
    (50, 5),
    (60, 6),
    (70, 7),
    (80, 8),
    (90, 9),
    (100, 10),
    (120, 12),
    (150, 15),
]

_ANGLE_UNEQUAL_DIMENSIONS: list[tuple[float, float, float]] = [
    (60, 40, 5),
    (70, 50, 6),
    (80, 40, 6),
    (80, 60, 7),
    (100, 50, 8),
    (100, 75, 8),
    (120, 80, 10),
    (150, 90, 12),
    (200, 100, 14),
]


IPE_PROFILES = [_tabulated_profile(profile) for profile in IPE_PROFILES]
HEA_PROFILES = [_tabulated_profile(profile) for profile in HEA_PROFILES]
HEB_PROFILES = [_tabulated_profile(profile) for profile in HEB_PROFILES]
HEM_PROFILES: list[SteelProfile] = [
    _i_shape_profile("HEM", *row) for row in _HEM_DIMENSIONS
]
UPN_PROFILES: list[SteelProfile] = [
    _channel_profile("UPN", *row) for row in _UPN_DIMENSIONS
]
UPE_PROFILES: list[SteelProfile] = [
    _channel_profile("UPE", *row) for row in _UPE_DIMENSIONS
]
CHS_PROFILES: list[SteelProfile] = [_chs_profile(*row) for row in _CHS_DIMENSIONS]
SHS_PROFILES: list[SteelProfile] = [
    _rhs_profile("SHS", size, size, thickness)
    for size, thickness in _SHS_DIMENSIONS
]
RHS_PROFILES: list[SteelProfile] = [
    _rhs_profile("RHS", *row) for row in _RHS_DIMENSIONS
]
ANGLE_EQUAL_PROFILES: list[SteelProfile] = [
    _angle_profile("L", size, size, thickness)
    for size, thickness in _ANGLE_EQUAL_DIMENSIONS
]
ANGLE_UNEQUAL_PROFILES: list[SteelProfile] = [
    _angle_profile("L unequal", *row) for row in _ANGLE_UNEQUAL_DIMENSIONS
]

PROFILE_FAMILIES: dict[str, tuple[SteelProfile, ...]] = {
    "IPE": tuple(IPE_PROFILES),
    "HEA": tuple(HEA_PROFILES),
    "HEB": tuple(HEB_PROFILES),
    "HEM": tuple(HEM_PROFILES),
    "UPN": tuple(UPN_PROFILES),
    "UPE": tuple(UPE_PROFILES),
    "CHS": tuple(CHS_PROFILES),
    "SHS": tuple(SHS_PROFILES),
    "RHS": tuple(RHS_PROFILES),
    "L": tuple(ANGLE_EQUAL_PROFILES),
    "L unequal": tuple(ANGLE_UNEQUAL_PROFILES),
}

PROFILE_CATALOG = {
    profile.name: profile
    for family in PROFILE_FAMILY_ORDER
    for profile in PROFILE_FAMILIES.get(family, ())
}


def get_profile(name: str) -> SteelProfile:
    """Return a steel profile by catalogue name."""
    return PROFILE_CATALOG[name]


def list_profiles(family: str | None = None) -> list[str]:
    """List profile names, optionally filtered by family code."""
    if family is None:
        return list(PROFILE_CATALOG.keys())
    return [profile.name for profile in PROFILE_FAMILIES.get(family, ())]


def list_profile_families() -> list[str]:
    """List available steel profile family codes in GUI order."""
    return [family for family in PROFILE_FAMILY_ORDER if PROFILE_FAMILIES.get(family)]


def get_profile_family_info(family: str) -> ProfileFamilyInfo:
    """Return metadata for a profile family."""
    return PROFILE_FAMILY_INFO[family]
