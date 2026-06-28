"""PyNite solver backend."""

from __future__ import annotations

import math

import numpy as np

from config.eurocodes import CONCRETE_GRADES, REBAR_GRADES, STEEL_GRADES
from core.local_axes import local_axes_from_nodes
from core.materials import DENSITIES
from core.results import ElementResult, NodalResult
from core.sections import section_torsion_constant
from core.self_weight import (
    element_self_weight_kn_m,
    is_self_weight_load,
)
from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    CapabilityLevel,
)


def _require_pynite():
    try:
        from Pynite import FEModel3D
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "PyNiteFEA n'est pas installé. "
            "Installez-le avec 'pip install PyNiteFEA'."
        ) from exc
    return FEModel3D


class PyNiteBackend:
    """PyNite backend for common static and modal analyses."""

    engine_name = "pynite"
    supports_diagrams = True
    capabilities = {
        AnalysisFeature.STATIC_LINEAR: AnalysisCapability(
            feature=AnalysisFeature.STATIC_LINEAR,
            level=CapabilityLevel.READY,
            note="Disponible maintenant dans HEXA Structures via PyNite.",
        ),
        AnalysisFeature.MODAL: AnalysisCapability(
            feature=AnalysisFeature.MODAL,
            level=CapabilityLevel.READY,
            note="Disponible maintenant dans HEXA Structures via PyNite.",
        ),
        AnalysisFeature.PDELTA: AnalysisCapability(
            feature=AnalysisFeature.PDELTA,
            level=CapabilityLevel.ENGINE_ONLY,
            note="PyNite le supporte nativement ; raccordement backend/GUI à faire.",
        ),
        AnalysisFeature.RESPONSE_SPECTRUM: AnalysisCapability(
            feature=AnalysisFeature.RESPONSE_SPECTRUM,
            level=CapabilityLevel.PLANNED,
            note="Prévu via une surcouche interne HEXA Structures sur les modes PyNite.",
        ),
        AnalysisFeature.PUSHOVER: AnalysisCapability(
            feature=AnalysisFeature.PUSHOVER,
            level=CapabilityLevel.UNAVAILABLE,
            note="Pas de support cible à court terme côté PyNite.",
        ),
        AnalysisFeature.TIME_HISTORY: AnalysisCapability(
            feature=AnalysisFeature.TIME_HISTORY,
            level=CapabilityLevel.UNAVAILABLE,
            note="Pas de support cible à court terme côté PyNite.",
        ),
    }

    def __init__(self, project):
        self.project = project
        self.model = None
        self._node_names: dict[int, str] = {}
        self._member_names: dict[int, str] = {}
        self._material_names: dict[int, str] = {}
        self._section_names: dict[int, str] = {}
        self._load_case_names: dict[int, str] = {}
        self._combo_names: dict[int, str] = {}
        self._active_combo_name: str | None = None

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        del max_iter, tol  # Not used by PyNite linear analysis for now.

        if combo_tag is None and load_tag is None:
            return False, {"error": "Aucun cas de charge spécifié."}

        combo_name = self._prepare_model(load_tag=load_tag, combo_tag=combo_tag)
        assert self.model is not None

        try:
            self.model.analyze_linear(log=False, check_stability=True, sparse=True)
        except Exception as exc:
            return False, {"error": f"Échec de l'analyse PyNite : {exc}"}

        self._active_combo_name = combo_name
        return True, self._extract_static_results(combo_name)

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        self._prepare_model(load_tag=None, combo_tag=None)
        assert self.model is not None

        combo_name = self._ensure_modal_mass_combo()

        try:
            frequencies = self.model.analyze_modal(
                num_modes=num_modes,
                mass_combo_name=combo_name,
                mass_direction="Z",
                gravity=9.81,
                log=False,
                check_stability=True,
            )
        except Exception as exc:
            return False, {"error": f"Échec de l'analyse modale PyNite : {exc}"}

        if frequencies is None:
            frequencies = getattr(self.model, "frequencies", [])
        frequencies = list(frequencies)
        eigenvalues = [(2 * math.pi * freq) ** 2 for freq in frequencies]
        periods = [
            (1.0 / freq) if freq and freq > 0 else float("inf")
            for freq in frequencies
        ]

        mode_shapes: dict[int, dict[int, NodalResult]] = {}
        for mode_idx in range(1, len(frequencies) + 1):
            combo = f"Mode {mode_idx}"
            mode_shapes[mode_idx] = self._extract_displacements(combo)

        return True, {
            "eigenvalues": eigenvalues,
            "frequencies_hz": frequencies,
            "periods_s": periods,
            "num_modes": len(frequencies),
            "mode_shapes": mode_shapes,
        }

    def _ensure_modal_mass_combo(self) -> str:
        """Ensure modal mass combination."""
        assert self.model is not None
        combo_name = "MASS_AUTO"
        case_name = "MASS_AUTO"

        self.model.add_member_self_weight("FZ", -1.0, case_name)
        self.model.add_load_combo(combo_name, {case_name: 1.0})
        return combo_name

    def _prepare_model(
        self,
        load_tag: int | None,
        combo_tag: int | None,
    ) -> str:
        FEModel3D = _require_pynite()
        self.model = FEModel3D()
        self._node_names.clear()
        self._member_names.clear()
        self._material_names.clear()
        self._section_names.clear()
        self._load_case_names = {
            tag: f"LC{tag}" for tag in self.project.loads
        }
        self._combo_names = {
            tag: f"COMBO{tag}" for tag in self.project.combinations
        }

        self._build_nodes()
        self._build_materials()
        self._build_sections()
        self._build_members()
        self._build_loads()
        self._build_combinations()

        if load_tag is not None:
            combo_name = f"CASE_{load_tag}"
            case_name = self._load_case_names[load_tag]
            self.model.add_load_combo(combo_name, {case_name: 1.0})
            return combo_name
        if combo_tag is not None:
            return self._combo_names[combo_tag]

        if not self.model.load_combos:
            self.model.add_load_combo("Combo 1", {})
        return next(iter(self.model.load_combos.keys()))

    def _build_nodes(self) -> None:
        assert self.model is not None
        for tag, node in self.project.nodes.items():
            name = self._node_name(tag)
            self._node_names[tag] = name
            self.model.add_node(name, node.x, node.y, node.z)
            if node.is_fixed:
                fix = tuple(bool(v) for v in node.fixities[:6])
                self.model.def_support(
                    name,
                    support_DX=fix[0],
                    support_DY=fix[1],
                    support_DZ=fix[2],
                    support_RX=fix[3],
                    support_RY=fix[4],
                    support_RZ=fix[5],
                )

    def _build_materials(self) -> None:
        assert self.model is not None
        for tag, material in self.project.materials.items():
            name = self._material_name(tag)
            self._material_names[tag] = name
            props = self._material_properties(material)
            self.model.add_material(
                name,
                props["E"],
                props["G"],
                props["nu"],
                props["rho"],
                props.get("fy"),
            )

    def _build_sections(self) -> None:
        assert self.model is not None
        for tag, section in self.project.sections.items():
            name = self._section_name(tag)
            self._section_names[tag] = name
            area = section.area
            iy = section.inertia_y
            iz = section.inertia_z if section.inertia_z > 0 else iy
            j = section_torsion_constant(section, fallback_iz=iz)
            self.model.add_section(name, area, iy, iz, j)

    def _build_members(self) -> None:
        assert self.model is not None
        for tag, element in self.project.elements.items():
            if element.element_type != "beam":
                continue
            name = self._member_name(tag)
            self._member_names[tag] = name
            section = self.project.sections[element.section_tag]
            self.model.add_member(
                name,
                self._node_names[element.node_i],
                self._node_names[element.node_j],
                self._material_names[section.material_tag],
                self._section_names[element.section_tag],
                rotation=self._member_rotation_degrees(element),
            )

    def _build_loads(self) -> None:
        assert self.model is not None
        for load_tag, load_case in self.project.loads.items():
            if not is_self_weight_load(load_case):
                continue
            case_name = self._load_case_names.get(load_tag)
            if case_name is not None:
                self._add_self_weight_loads(case_name, factor=1.0)

        for load in self.project.nodal_loads:
            node_name = self._node_names.get(load.node_tag)
            case_name = self._load_case_names.get(load.load_tag)
            if node_name is None or case_name is None:
                continue
            for direction, value in (
                ("FX", load.fx),
                ("FY", load.fy),
                ("FZ", load.fz),
                ("MX", load.mx),
                ("MY", load.my),
                ("MZ", load.mz),
            ):
                if abs(value) > 1e-12:
                    self.model.add_node_load(node_name, direction, value, case_name)

        for load in self.project.element_loads:
            member_name = self._member_names.get(load.element_tag)
            case_name = self._load_case_names.get(load.load_tag)
            if member_name is None or case_name is None:
                continue
            coordinate_system = str(
                getattr(load, "coordinate_system", "local") or "local",
            ).strip().lower()
            if coordinate_system == "global":
                components = (
                    ("FX", load.wx),
                    ("FY", load.wy),
                    ("FZ", load.wz),
                )
            else:
                components = (
                    ("Fx", load.wx),
                    ("Fy", load.wy),
                    ("Fz", load.wz),
                )
            for direction, value in components:
                if abs(value) > 1e-12:
                    self.model.add_member_dist_load(
                        member_name,
                        direction,
                        value,
                        value,
                        case=case_name,
                    )

    def _add_self_weight_loads(self, case_name: str, factor: float) -> None:
        """Add self-weight loads."""
        assert self.model is not None
        for element in self.project.elements.values():
            member_name = self._member_names.get(element.tag)
            if member_name is None:
                continue
            weight = element_self_weight_kn_m(self.project, element) * factor
            if abs(weight) <= 1e-12:
                continue
            self.model.add_member_dist_load(
                member_name,
                "FZ",
                -weight,
                -weight,
                case=case_name,
            )

    def _build_combinations(self) -> None:
        assert self.model is not None
        for tag, combo in self.project.combinations.items():
            factors = {
                self._load_case_names[load_tag]: factor
                for load_tag, factor in combo.factors.items()
                if load_tag in self._load_case_names
            }
            self.model.add_load_combo(self._combo_names[tag], factors)

        if not self.project.combinations and self.project.loads:
            first_case = next(iter(self._load_case_names.values()))
            self.model.add_load_combo("Combo 1", {first_case: 1.0})

    def _extract_static_results(self, combo_name: str) -> dict:
        return {
            "displacements": self._extract_displacements(combo_name),
            "reactions": self._extract_reactions(combo_name),
            "element_forces": self._extract_element_forces(combo_name),
        }

    def _extract_displacements(self, combo_name: str) -> dict[int, NodalResult]:
        assert self.model is not None
        results: dict[int, NodalResult] = {}
        for tag, name in self._node_names.items():
            node = self.model.nodes[name]
            results[tag] = NodalResult(
                tag=tag,
                ux=float(node.DX.get(combo_name, 0.0)),
                uy=float(node.DY.get(combo_name, 0.0)),
                uz=float(node.DZ.get(combo_name, 0.0)),
                rx=float(node.RX.get(combo_name, 0.0)),
                ry=float(node.RY.get(combo_name, 0.0)),
                rz=float(node.RZ.get(combo_name, 0.0)),
            )
        return results

    def _extract_reactions(self, combo_name: str) -> dict[int, NodalResult]:
        assert self.model is not None
        results: dict[int, NodalResult] = {}
        for tag, data in self.project.nodes.items():
            if not data.is_fixed:
                continue
            node = self.model.nodes[self._node_names[tag]]
            results[tag] = NodalResult(
                tag=tag,
                fx_reaction=float(node.RxnFX.get(combo_name, 0.0)),
                fy_reaction=float(node.RxnFY.get(combo_name, 0.0)),
                fz_reaction=float(node.RxnFZ.get(combo_name, 0.0)),
                mx_reaction=float(node.RxnMX.get(combo_name, 0.0)),
                my_reaction=float(node.RxnMY.get(combo_name, 0.0)),
                mz_reaction=float(node.RxnMZ.get(combo_name, 0.0)),
            )
        return results

    def _extract_element_forces(self, combo_name: str) -> dict[int, ElementResult]:
        assert self.model is not None
        results: dict[int, ElementResult] = {}
        for tag, name in self._member_names.items():
            member = self.model.members[name]
            length = float(member.L())
            my_sign, mz_sign = self._moment_sign_map(tag)
            results[tag] = ElementResult(
                tag=tag,
                n_i=float(member.axial(0.0, combo_name)),
                vy_i=float(member.shear("Fy", 0.0, combo_name)),
                vz_i=float(member.shear("Fz", 0.0, combo_name)),
                t_i=float(member.torque(0.0, combo_name)),
                my_i=my_sign * float(member.moment("My", 0.0, combo_name)),
                mz_i=mz_sign * float(member.moment("Mz", 0.0, combo_name)),
                n_j=float(member.axial(length, combo_name)),
                vy_j=float(member.shear("Fy", length, combo_name)),
                vz_j=float(member.shear("Fz", length, combo_name)),
                t_j=float(member.torque(length, combo_name)),
                my_j=my_sign * float(member.moment("My", length, combo_name)),
                mz_j=mz_sign * float(member.moment("Mz", length, combo_name)),
            )
        return results

    def sample_diagram_component(
        self,
        element_tag: int,
        component: str,
        nep: int = 17,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Handle sample diagram component."""
        if self.model is None or not self._active_combo_name:
            return None

        member_name = self._member_names.get(element_tag)
        if member_name is None:
            return None

        member = self.model.members.get(member_name)
        if member is None:
            return None

        length = float(member.L())
        if length <= 1e-12:
            return None

        combo_name = self._active_combo_name
        x = np.linspace(0.0, length, nep)
        sign = self._diagram_sampling_sign(element_tag, component)

        if component == "N":
            values = np.array([float(member.axial(float(xi), combo_name)) for xi in x])
        elif component == "Vy":
            values = sign * np.array(
                [float(member.shear("Fy", float(xi), combo_name)) for xi in x]
            )
        elif component == "Vz":
            values = sign * np.array(
                [float(member.shear("Fz", float(xi), combo_name)) for xi in x]
            )
        elif component == "T":
            values = np.array([float(member.torque(float(xi), combo_name)) for xi in x])
        elif component == "My":
            values = sign * np.array(
                [float(member.moment("My", float(xi), combo_name)) for xi in x]
            )
        elif component == "Mz":
            values = sign * np.array(
                [float(member.moment("Mz", float(xi), combo_name)) for xi in x]
            )
        else:
            return None

        return x, values

    def _diagram_sampling_sign(self, element_tag: int, component: str) -> float:
        """Handle diagram sampling sign."""
        del element_tag
        if component == "Mz":
            return -1.0
        return 1.0

    def _moment_sign_map(self, element_tag: int) -> tuple[float, float]:
        """Handle moment sign map."""
        element = self.project.elements[element_tag]
        node_i = self.project.nodes[element.node_i]
        node_j = self.project.nodes[element.node_j]

        dx = node_j.x - node_i.x
        dy = node_j.y - node_i.y
        dz = node_j.z - node_i.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-12:
            return 1.0, 1.0

        return -1.0, 1.0

    def _member_rotation_degrees(self, element) -> float:
        """Handle member rotation degrees."""
        node_i = self.project.nodes[element.node_i]
        node_j = self.project.nodes[element.node_j]
        ecrd_3d = np.array(
            [
                [node_i.x, node_i.y, node_i.z],
                [node_j.x, node_j.y, node_j.z],
            ],
            dtype=float,
        )
        default_axes = self._pynite_default_local_axes(ecrd_3d)
        if default_axes is None:
            return 0.0

        _, default_y, default_z = default_axes
        try:
            axes = local_axes_from_nodes(
                (node_i.x, node_i.y, node_i.z),
                (node_j.x, node_j.y, node_j.z),
                reference_vector=getattr(element, "orientation_vector", None),
                roll_angle_deg=float(getattr(element, "roll_angle_deg", 0.0) or 0.0),
            )
        except ValueError:
            return 0.0
        desired_y = np.array(axes.y, dtype=float)
        cosine = float(np.dot(desired_y, default_y))
        sine = float(np.dot(desired_y, default_z))
        angle = math.degrees(math.atan2(sine, cosine))
        if not math.isfinite(angle):
            return 0.0
        return angle

    @staticmethod
    def _pynite_default_local_axes(
        ecrd_3d: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Handle PyNite default local axes."""
        p_i = ecrd_3d[0]
        p_j = ecrd_3d[1]
        x_vec = p_j - p_i
        length = float(np.linalg.norm(x_vec))
        if length <= 1e-12:
            return None

        local_x = x_vec / length
        xi, yi, zi = (float(value) for value in p_i)
        xj, yj, zj = (float(value) for value in p_j)

        if math.isclose(xi, xj) and math.isclose(zi, zj):
            local_y = (
                np.array([-1.0, 0.0, 0.0], dtype=float)
                if yj > yi else np.array([1.0, 0.0, 0.0], dtype=float)
            )
            local_z = np.array([0.0, 0.0, 1.0], dtype=float)
        elif math.isclose(yi, yj):
            local_y = np.array([0.0, 1.0, 0.0], dtype=float)
            local_z = np.cross(local_x, local_y)
            norm_z = float(np.linalg.norm(local_z))
            if norm_z <= 1e-12:
                return None
            local_z /= norm_z
        else:
            projection = np.array([xj - xi, 0.0, zj - zi], dtype=float)
            if yj > yi:
                local_z = np.cross(projection, local_x)
            else:
                local_z = np.cross(local_x, projection)
            norm_z = float(np.linalg.norm(local_z))
            if norm_z <= 1e-12:
                return None
            local_z /= norm_z
            local_y = np.cross(local_z, local_x)
            norm_y = float(np.linalg.norm(local_y))
            if norm_y <= 1e-12:
                return None
            local_y /= norm_y

        return local_x, local_y, local_z

    def _material_properties(self, material) -> dict[str, float]:
        if material.material_type == "concrete":
            grade = CONCRETE_GRADES.get(material.grade)
            e_mod = material.properties.get("E", grade.ecm if grade else 30_000_000.0)
            nu = float(material.properties.get("nu", 0.2))
            rho = float(material.properties.get("rho", DENSITIES["concrete"] / 1000.0))
            fy = None
        elif material.material_type == "rebar":
            grade = REBAR_GRADES.get(material.grade)
            e_mod = material.properties.get("E", grade.es if grade else 200_000_000.0)
            nu = float(material.properties.get("nu", 0.3))
            rho = float(material.properties.get("rho", DENSITIES["steel"] / 1000.0))
            fy = float(material.properties.get("fy", grade.fyd if grade else 500_000.0))
        else:
            grade = STEEL_GRADES.get(material.grade)
            e_mod = material.properties.get("E", grade.es if grade else 210_000_000.0)
            nu = float(material.properties.get("nu", 0.3))
            rho = float(material.properties.get("rho", DENSITIES["steel"] / 1000.0))
            fy = float(material.properties.get("fy", grade.fyd if grade else 355_000.0))

        g_mod = float(material.properties.get("G", e_mod / (2.0 * (1.0 + nu))))
        return {
            "E": float(e_mod),
            "G": g_mod,
            "nu": nu,
            "rho": rho,
            "fy": fy,
        }

    @staticmethod
    def _node_name(tag: int) -> str:
        return f"N{tag}"

    @staticmethod
    def _member_name(tag: int) -> str:
        return f"E{tag}"

    @staticmethod
    def _material_name(tag: int) -> str:
        return f"MAT{tag}"

    @staticmethod
    def _section_name(tag: int) -> str:
        return f"SEC{tag}"
