"""
Traducteur : modèle de données Python → commandes OpenSeesPy.

Traduit un ProjectModel complet en appels openseespy pour construire
le modèle éléments finis 3D (ndm=3, ndf=6), appliquer les charges
et lancer l'analyse. Dépend d'openseespy.opensees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.optional_imports import ensure_external_module_search_paths
from core.local_axes import local_axes_from_nodes, opensees_vecxz_from_axes
from core.material_properties import (
    material_elastic_modulus,
    material_mass_density_kg_m3,
    material_poisson_ratio,
)
from core.self_weight import (
    element_load_local_components,
    element_self_weight_local_components,
    is_self_weight_load,
    surface_area_m2,
    surface_self_weight_global_components,
)

if TYPE_CHECKING:
    from core.model_data import (
        ProjectModel,
    )


def _require_opensees():
    """Import différé d'OpenSeesPy."""
    try:
        ensure_external_module_search_paths("openseespy", "openseespywin")
        import openseespy.opensees as _ops
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise ImportError(
            "OpenSeesPy n'est pas installé. "
            "Installez-le avec 'pip install openseespy' pour utiliser ce backend."
        ) from exc
    return _ops


class _OpenSeesProxy:
    def __getattr__(self, name: str):
        return getattr(_require_opensees(), name)


ops = _OpenSeesProxy()


class OpsBuilder:
    """Construit un modèle OpenSees 3D à partir d'un ProjectModel.

    Usage typique :
        builder = OpsBuilder(project)
        builder.build()
        builder.apply_loads(load_tag=1)
    """

    def __init__(self, project: ProjectModel):
        self.project = project
        self._ts_tag = 1    # compteur timeSeries
        self._pat_tag = 1   # compteur pattern
        self._transf_tag = 1  # compteur geomTransf
        self._transf_cache: dict[tuple[float, float, float], int] = {}
        self._element_transf_tags: dict[int, int] = {}
        self._surface_ops_tag_offset = max(self.project.elements.keys(), default=0)

    def build(self, ndm: int = 3, ndf: int = 6) -> None:
        """Construit le modèle complet dans OpenSees.

        Args:
            ndm: Nombre de dimensions (3 par défaut).
            ndf: Nombre de DDL par nœud (6 par défaut).
        """
        ops.wipe()
        ops.model("basic", "-ndm", ndm, "-ndf", ndf)

        self._ndm = ndm
        self._ndf = ndf
        self._build_nodes()
        self._build_materials()
        self._build_sections()
        self._build_transforms()
        self._build_elements()

    def _build_nodes(self) -> None:
        """Crée les nœuds et les conditions d'appui (6 DDL)."""
        for node in self.project.nodes.values():
            if self._ndm == 3:
                ops.node(node.tag, node.x, node.y, node.z)
            else:
                ops.node(node.tag, node.x, node.y)

            if node.is_fixed:
                fix = node.fixities
                if self._ndm == 3 and len(fix) == 6:
                    ops.fix(node.tag, *fix)
                elif self._ndm == 2 and len(fix) >= 3:
                    ops.fix(node.tag, fix[0], fix[1], fix[5])
                else:
                    ops.fix(node.tag, *fix)

    def _build_materials(self) -> None:
        """Crée les matériaux uniaxiaux dans OpenSees."""
        for mat in self.project.materials.values():
            ops.uniaxialMaterial(
                "Elastic",
                mat.tag,
                material_elastic_modulus(mat),
            )

    def _build_sections(self) -> None:
        """Crée les sections dans OpenSees.

        Utilise des sections élastiques.
        Les sections fibrées seront ajoutées ultérieurement.
        """
        for sec in self.project.sections.values():
            if sec.is_surface:
                thickness = sec.thickness
                if thickness <= 0.0:
                    raise ValueError(
                        f"La section plaque T{sec.tag} a une épaisseur invalide."
                    )
                e_mod = self._get_elastic_modulus(sec.material_tag)
                nu = self._get_poisson_ratio(sec.material_tag)
                rho = self._get_mass_density(sec.material_tag)
                ops.section(
                    "ElasticMembranePlateSection",
                    sec.tag,
                    e_mod,
                    nu,
                    thickness,
                    rho,
                )
                continue
            if sec.area > 0 and sec.inertia_y > 0:
                e_mod = self._get_elastic_modulus(sec.material_tag)
                g_mod = self._get_shear_modulus(sec.material_tag)
                iz = sec.inertia_z if sec.inertia_z > 0 else sec.inertia_y
                # Section élastique 3D : E, A, Iz, Iy, G, J
                j_torsion = self._torsion_constant(sec, iz)
                if self._ndm == 3:
                    ops.section("Elastic", sec.tag,
                                e_mod, sec.area, iz, sec.inertia_y,
                                g_mod, j_torsion)
                else:
                    ops.section("Elastic", sec.tag, e_mod, sec.area, sec.inertia_y)

    def _get_elastic_modulus(self, material_tag: int) -> float:
        """Retourne le module d'Young d'un matériau (kPa)."""
        mat = self.project.materials.get(material_tag)
        return material_elastic_modulus(mat)

    def _get_shear_modulus(self, material_tag: int) -> float:
        """Retourne le module de cisaillement d'un matériau (kPa)."""
        from core.material_properties import material_shear_modulus

        mat = self.project.materials.get(material_tag)
        return material_shear_modulus(mat)

    def _get_poisson_ratio(self, material_tag: int) -> float:
        """Retourne le coefficient de Poisson d'un matériau."""
        mat = self.project.materials.get(material_tag)
        return material_poisson_ratio(mat)

    def _get_mass_density(self, material_tag: int) -> float:
        """Retourne une masse volumique cohérente avec les unités kN-m-s d'OpenSees."""
        mat = self.project.materials.get(material_tag)
        return material_mass_density_kg_m3(mat) / 1000.0

    def _ops_surface_tag(self, surface_tag: int) -> int:
        """Retourne un tag OpenSees unique pour une surface du projet."""
        return self._surface_ops_tag_offset + int(surface_tag)

    @staticmethod
    def _torsion_constant(sec, iz: float) -> float:
        """Retourne J si disponible, sinon une approximation provisoire."""
        for key in ("torsion_constant", "J"):
            try:
                value = float(sec.properties.get(key, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value

        # Approximation provisoire lorsque la bibliotheque de sections ne fournit
        # pas encore de constante de torsion dediee.
        return sec.inertia_y + iz

    def _build_transforms(self) -> None:
        """Crée les transformations géométriques nécessaires aux poutres."""
        self._transf_cache.clear()
        self._element_transf_tags.clear()
        self._transf_tag = 1

        if self._ndm != 3:
            ops.geomTransf("Linear", 1)
            self._transf_tag = 2
            return

        for elem in self.project.elements.values():
            if elem.element_type == "truss":
                continue
            if elem.section_tag not in self.project.sections:
                continue
            self._get_transf_tag(elem)

    def _get_transf_tag(self, elem) -> int:
        """Retourne le tag geomTransf calculé pour un élément poutre."""
        if self._ndm == 2:
            return 1

        existing = self._element_transf_tags.get(elem.tag)
        if existing is not None:
            return existing

        axes = self._local_axes_for_element(elem)
        vecxz = opensees_vecxz_from_axes(axes)
        key = self._transf_key(vecxz)
        transf_tag = self._transf_cache.get(key)
        if transf_tag is None:
            transf_tag = self._transf_tag
            self._transf_tag += 1
            self._transf_cache[key] = transf_tag
            ops.geomTransf("Linear", transf_tag, *key)

        self._element_transf_tags[elem.tag] = transf_tag
        return transf_tag

    def _local_axes_for_element(self, elem):
        """Construit les axes locaux HEXA d'un élément à partir de ses noeuds."""
        ni = self.project.nodes.get(elem.node_i)
        nj = self.project.nodes.get(elem.node_j)
        if ni is None or nj is None:
            raise ValueError(
                f"L'élément E{elem.tag} référence un noeud absent "
                f"({elem.node_i}, {elem.node_j})."
            )

        return local_axes_from_nodes(
            (ni.x, ni.y, ni.z),
            (nj.x, nj.y, nj.z),
            reference_vector=getattr(elem, "orientation_vector", None),
            roll_angle_deg=float(getattr(elem, "roll_angle_deg", 0.0) or 0.0),
        )

    @staticmethod
    def _transf_key(vecxz: tuple[float, float, float]) -> tuple[float, float, float]:
        """Normalise une clé de réutilisation geomTransf stable numériquement."""
        return tuple(round(float(value), 12) for value in vecxz)

    def _build_elements(self) -> None:
        """Crée les éléments dans OpenSees (3D)."""
        for elem in self.project.elements.values():
            sec = self.project.sections.get(elem.section_tag)
            if sec is None:
                raise ValueError(
                    f"L'element E{elem.tag} reference une section absente T{elem.section_tag}."
                )
            if sec.is_surface:
                raise ValueError(
                    f"L'element E{elem.tag} reference T{elem.section_tag}, qui est une section plaque. "
                    "Une barre doit utiliser une section barre."
                )
            if sec.area <= 0.0:
                raise ValueError(
                    f"La section barre T{sec.tag} utilisee par E{elem.tag} a une aire nulle."
                )
            if elem.element_type != "truss" and sec.inertia_y <= 0.0:
                raise ValueError(
                    f"La section barre T{sec.tag} utilisee par E{elem.tag} a une inertie Iy nulle."
                )

            if elem.element_type == "truss":
                ops.element(
                    "Truss", elem.tag,
                    elem.node_i, elem.node_j,
                    sec.area, sec.material_tag,
                )
            else:
                e_mod = self._get_elastic_modulus(sec.material_tag)
                transf_tag = self._get_transf_tag(elem)
                if self._ndm == 3:
                    g_mod = self._get_shear_modulus(sec.material_tag)
                    iz = sec.inertia_z if sec.inertia_z > 0 else sec.inertia_y
                    j_torsion = self._torsion_constant(sec, iz)
                    # elasticBeamColumn 3D : tag, ni, nj, A, E, G, J, Iy, Iz, transfTag
                    ops.element(
                        "elasticBeamColumn", elem.tag,
                        elem.node_i, elem.node_j,
                        sec.area, e_mod, g_mod, j_torsion,
                        sec.inertia_y, iz, transf_tag,
                    )
                else:
                    ops.element(
                        "elasticBeamColumn", elem.tag,
                        elem.node_i, elem.node_j,
                        sec.area, e_mod, sec.inertia_y, 1,
                    )

        for surface in self.project.surface_elements.values():
            sec = self.project.sections.get(surface.section_tag)
            if sec is None:
                raise ValueError(
                    f"La surface S{surface.tag} référence une section absente T{surface.section_tag}."
                )
            if not sec.is_surface:
                raise ValueError(
                    f"La surface S{surface.tag} référence T{surface.section_tag}, qui n'est pas une section plaque."
                )
            formulation = getattr(surface, "formulation", None) or sec.surface_formulation
            if formulation not in {"ShellMITC4", "ShellDKGQ", "ShellNLDKGQ"}:
                raise NotImplementedError(
                    f"La formulation plaque {formulation} n'est pas encore prise en charge par le solveur OpenSees."
                )
            if len(surface.node_tags) != 4:
                raise NotImplementedError(
                    "Cette version du solveur plaque OpenSees est limitée aux surfaces quadrangulaires."
                )

            ops.element(
                formulation,
                self._ops_surface_tag(surface.tag),
                *surface.node_tags,
                sec.tag,
            )

    @staticmethod
    def _accumulate_nodal_load(
        nodal_loads: dict[int, list[float]],
        node_tag: int,
        *,
        fx: float = 0.0,
        fy: float = 0.0,
        fz: float = 0.0,
        mx: float = 0.0,
        my: float = 0.0,
        mz: float = 0.0,
    ) -> None:
        """Cumule des composantes nodales pour un même nœud."""
        values = nodal_loads.setdefault(int(node_tag), [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        values[0] += fx
        values[1] += fy
        values[2] += fz
        values[3] += mx
        values[4] += my
        values[5] += mz

    def _surface_uniform_nodal_forces(
        self,
        surface,
        qx: float,
        qy: float,
        qz: float,
    ) -> dict[int, tuple[float, float, float]]:
        """Retourne les forces nodales équivalentes d'une charge surfacique uniforme."""
        area = surface_area_m2(self.project, surface)
        node_count = len(surface.node_tags)
        if area <= 1e-12 or node_count <= 0:
            return {}

        nodal_factor = area / float(node_count)
        return {
            int(node_tag): (qx * nodal_factor, qy * nodal_factor, qz * nodal_factor)
            for node_tag in surface.node_tags
        }

    def _accumulate_surface_load(
        self,
        nodal_loads: dict[int, list[float]],
        surface,
        qx: float,
        qy: float,
        qz: float,
        *,
        factor: float = 1.0,
    ) -> None:
        """Projette une charge surfacique uniforme en efforts nodaux équivalents."""
        for node_tag, (fx, fy, fz) in self._surface_uniform_nodal_forces(surface, qx, qy, qz).items():
            self._accumulate_nodal_load(
                nodal_loads,
                node_tag,
                fx=fx * factor,
                fy=fy * factor,
                fz=fz * factor,
            )

    def _accumulate_surface_self_weight_loads(
        self,
        nodal_loads: dict[int, list[float]],
        *,
        factor: float = 1.0,
    ) -> None:
        """Ajoute le poids propre des plaques comme charges nodales équivalentes."""
        for surface in self.project.surface_elements.values():
            qx, qy, qz = surface_self_weight_global_components(self.project, surface)
            if abs(qx) <= 1e-12 and abs(qy) <= 1e-12 and abs(qz) <= 1e-12:
                continue
            self._accumulate_surface_load(
                nodal_loads,
                surface,
                qx,
                qy,
                qz,
                factor=factor,
            )

    def _emit_nodal_loads(self, nodal_loads: dict[int, list[float]]) -> None:
        """Émet les charges nodales agrégées dans le pattern courant."""
        for node_tag, values in nodal_loads.items():
            if self._ndf == 6:
                ops.load(node_tag, *values)
            else:
                ops.load(node_tag, values[0], values[1], values[5])

    def apply_loads(self, load_tag: int) -> None:
        """Applique un cas de charge au modèle OpenSees.

        Args:
            load_tag: Tag du cas de charge à appliquer.
        """
        ts = self._ts_tag
        self._ts_tag += 1
        ops.timeSeries("Linear", ts)

        pat = self._pat_tag
        self._pat_tag += 1
        ops.pattern("Plain", pat, ts)

        load_case = self.project.loads.get(load_tag)
        nodal_loads: dict[int, list[float]] = {}
        if load_case is not None and is_self_weight_load(load_case):
            self._apply_self_weight_loads(factor=1.0)
            self._accumulate_surface_self_weight_loads(nodal_loads, factor=1.0)

        # Charges nodales (6 composantes en 3D)
        for nl in self.project.nodal_loads:
            if nl.load_tag == load_tag:
                self._accumulate_nodal_load(
                    nodal_loads,
                    nl.node_tag,
                    fx=nl.fx,
                    fy=nl.fy,
                    fz=nl.fz,
                    mx=nl.mx,
                    my=nl.my,
                    mz=nl.mz,
                )

        # Charges surfaciques uniformes
        for sl in self.project.surface_loads:
            if sl.load_tag != load_tag:
                continue
            surface = self.project.surface_elements.get(sl.surface_tag)
            if surface is None:
                continue
            self._accumulate_surface_load(
                nodal_loads,
                surface,
                sl.qx,
                sl.qy,
                sl.qz,
            )

        self._emit_nodal_loads(nodal_loads)

        # Charges réparties sur éléments
        for el in self.project.element_loads:
            if el.load_tag == load_tag:
                element = self.project.elements.get(el.element_tag)
                if element is None:
                    continue
                wx, wy, wz = element_load_local_components(self.project, element, el)
                if wy != 0.0 or wx != 0.0 or wz != 0.0:
                    if self._ndf == 6:
                        ops.eleLoad(
                            "-ele", el.element_tag,
                            "-type", "-beamUniform",
                            wy, wz, wx,
                        )
                    else:
                        ops.eleLoad(
                            "-ele", el.element_tag,
                            "-type", "-beamUniform", wy, wx,
                        )

    def _apply_self_weight_loads(self, factor: float) -> None:
        """Applique le poids propre automatique comme charge répartie locale."""
        for element in self.project.elements.values():
            wx, wy, wz = element_self_weight_local_components(self.project, element)
            wx *= factor
            wy *= factor
            wz *= factor
            if abs(wx) <= 1e-12 and abs(wy) <= 1e-12 and abs(wz) <= 1e-12:
                continue

            if self._ndf == 6:
                ops.eleLoad(
                    "-ele", element.tag,
                    "-type", "-beamUniform",
                    wy, wz, wx,
                )
            else:
                ops.eleLoad(
                    "-ele", element.tag,
                    "-type", "-beamUniform",
                    wy, wx,
                )

    def apply_combination(self, combo_tag: int) -> None:
        """Applique une combinaison de charges.

        Crée un pattern par cas de charge avec les facteurs de la combinaison.

        Args:
            combo_tag: Tag de la combinaison.
        """
        combo = self.project.combinations.get(combo_tag)
        if combo is None:
            return

        for load_tag, factor in combo.factors.items():
            if factor == 0.0:
                continue

            ts = self._ts_tag
            self._ts_tag += 1
            ops.timeSeries("Linear", ts)

            pat = self._pat_tag
            self._pat_tag += 1
            ops.pattern("Plain", pat, ts)

            load_case = self.project.loads.get(load_tag)
            nodal_loads: dict[int, list[float]] = {}
            if load_case is not None and is_self_weight_load(load_case):
                self._apply_self_weight_loads(factor=factor)
                self._accumulate_surface_self_weight_loads(nodal_loads, factor=factor)

            # Charges nodales factorisées
            for nl in self.project.nodal_loads:
                if nl.load_tag == load_tag:
                    self._accumulate_nodal_load(
                        nodal_loads,
                        nl.node_tag,
                        fx=nl.fx * factor,
                        fy=nl.fy * factor,
                        fz=nl.fz * factor,
                        mx=nl.mx * factor,
                        my=nl.my * factor,
                        mz=nl.mz * factor,
                    )

            # Charges surfaciques uniformes factorisées
            for sl in self.project.surface_loads:
                if sl.load_tag != load_tag:
                    continue
                surface = self.project.surface_elements.get(sl.surface_tag)
                if surface is None:
                    continue
                self._accumulate_surface_load(
                    nodal_loads,
                    surface,
                    sl.qx,
                    sl.qy,
                    sl.qz,
                    factor=factor,
                )

            self._emit_nodal_loads(nodal_loads)

            # Charges réparties factorisées
            for el in self.project.element_loads:
                if el.load_tag == load_tag:
                    element = self.project.elements.get(el.element_tag)
                    if element is None:
                        continue
                    wx, wy, wz = element_load_local_components(self.project, element, el)
                    if wy != 0.0 or wx != 0.0 or wz != 0.0:
                        if self._ndf == 6:
                            ops.eleLoad(
                                "-ele", el.element_tag,
                                "-type", "-beamUniform",
                                wy * factor, wz * factor, wx * factor,
                            )
                        else:
                            ops.eleLoad(
                                "-ele", el.element_tag,
                                "-type", "-beamUniform",
                                wy * factor, wx * factor,
                            )
