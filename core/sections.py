"""
Définition des sections structurelles.

Sections rectangulaires béton armé, en T, profilés acier européens.
Calcul des propriétés géométriques (A, Iy, Iz, Wel, Wpl).
Toutes les dimensions en mètres, surfaces en m², inerties en m⁴.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.units import CM2_TO_M2, CM4_TO_M4, MM_TO_M


# ═══════════════════════════════════════════════════════════════════════════
#  Section rectangulaire
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RectangularSection:
    """Section rectangulaire pleine (béton armé).

    Args:
        b: Largeur (m).
        h: Hauteur (m).
    """

    b: float
    h: float

    @property
    def area(self) -> float:
        """Aire de la section (m²)."""
        return self.b * self.h

    @property
    def inertia_y(self) -> float:
        """Moment d'inertie autour de l'axe fort Y (m⁴)."""
        return self.b * self.h**3 / 12

    @property
    def inertia_z(self) -> float:
        """Moment d'inertie autour de l'axe faible Z (m⁴)."""
        return self.h * self.b**3 / 12

    @property
    def wel_y(self) -> float:
        """Module élastique de flexion axe Y (m³)."""
        return self.b * self.h**2 / 6

    @property
    def wpl_y(self) -> float:
        """Module plastique de flexion axe Y (m³)."""
        return self.b * self.h**2 / 4


# ═══════════════════════════════════════════════════════════════════════════
#  Section en T
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TSection:
    """Section en T (poutre de plancher béton armé).

    Args:
        bw: Largeur de l'âme (m).
        hw: Hauteur de l'âme (m).
        bf: Largeur de la table (m).
        hf: Épaisseur de la table (m).
    """

    bw: float  # largeur âme
    hw: float  # hauteur âme (sous la table)
    bf: float  # largeur table
    hf: float  # épaisseur table

    @property
    def h(self) -> float:
        """Hauteur totale (m)."""
        return self.hw + self.hf

    @property
    def area(self) -> float:
        """Aire de la section (m²)."""
        return self.bw * self.hw + self.bf * self.hf

    @property
    def centroid_y(self) -> float:
        """Position du centre de gravité depuis la base (m)."""
        a_web = self.bw * self.hw
        a_flange = self.bf * self.hf
        y_web = self.hw / 2
        y_flange = self.hw + self.hf / 2
        return (a_web * y_web + a_flange * y_flange) / self.area

    @property
    def inertia_y(self) -> float:
        """Moment d'inertie autour de l'axe Y passant par le CDG (m⁴)."""
        yg = self.centroid_y

        # Âme
        iy_web = self.bw * self.hw**3 / 12
        d_web = yg - self.hw / 2
        iy_web += self.bw * self.hw * d_web**2

        # Table
        iy_flange = self.bf * self.hf**3 / 12
        d_flange = (self.hw + self.hf / 2) - yg
        iy_flange += self.bf * self.hf * d_flange**2

        return iy_web + iy_flange


# ═══════════════════════════════════════════════════════════════════════════
#  Profilé acier européen
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SteelProfile:
    """Profilé acier européen (IPE, HEA, HEB, HEM, UPN…).

    Toutes les dimensions en unités internes (m, m², m⁴).
    """

    name: str
    family: str       # "IPE", "HEA", "HEB", "HEM", "UPN"
    h: float          # hauteur totale (m)
    b: float          # largeur semelle (m)
    tw: float         # épaisseur âme (m)
    tf: float         # épaisseur semelle (m)
    area: float       # aire (m²)
    inertia_y: float  # moment d'inertie axe fort (m⁴)
    inertia_z: float  # moment d'inertie axe faible (m⁴)
    wel_y: float      # module élastique axe fort (m³)
    wpl_y: float      # module plastique axe fort (m³)
    mass: float       # masse linéique (kg/m)


# ═══════════════════════════════════════════════════════════════════════════
#  Catalogue de profilés embarqué
# ═══════════════════════════════════════════════════════════════════════════

# Profilés IPE courants — valeurs issues des tables ArcelorMittal
# Dimensions en mm, surfaces en cm², inerties en cm⁴, modules en cm³, masse en kg/m
_IPE_RAW: list[tuple] = [
    # (nom, h, b, tw, tf, A, Iy, Iz, Wel_y, Wpl_y, masse)
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
    """Convertit les données brutes (mm, cm², cm⁴) en unités internes."""
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

# Index par nom pour recherche rapide
PROFILE_CATALOG: dict[str, SteelProfile] = {}
for _profiles in (IPE_PROFILES, HEA_PROFILES, HEB_PROFILES):
    for _p in _profiles:
        PROFILE_CATALOG[_p.name] = _p


def get_profile(name: str) -> SteelProfile:
    """Recherche un profilé par son nom.

    Args:
        name: Nom du profilé (ex. "IPE 300", "HEB 200").

    Returns:
        Le profilé correspondant.

    Raises:
        KeyError: Si le profilé n'est pas trouvé.
    """
    return PROFILE_CATALOG[name]


def list_profiles(family: str | None = None) -> list[str]:
    """Liste les noms de profilés disponibles.

    Args:
        family: Filtrer par famille ("IPE", "HEA", "HEB"). None = tous.

    Returns:
        Liste de noms de profilés.
    """
    if family is None:
        return list(PROFILE_CATALOG.keys())
    return [p.name for p in PROFILE_CATALOG.values() if p.family == family]
