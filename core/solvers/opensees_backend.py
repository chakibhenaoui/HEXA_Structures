"""OpenSees solver backend."""

from __future__ import annotations

import numpy as np

from core.analysis_model_builder import build_analysis_model
from core.optional_imports import ensure_external_module_search_paths
from core.ops_builder import OpsBuilder
from core.result_mapping import map_analysis_results_to_user_results
from core.results import ResultsExtractor
from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    CapabilityLevel,
)


def _require_opensees():
    try:
        ensure_external_module_search_paths("openseespy", "openseespywin")
        import openseespy.opensees as ops
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "OpenSeesPy n'est pas installé. "
            "Installez-le avec 'pip install openseespy'."
        ) from exc
    return ops


def _require_opsvis_section_force_distribution_3d():
    try:
        from opsvis.secforces import section_force_distribution_3d
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "opsvis n'est pas installé. "
            "Les diagrammes détaillés ne sont donc pas disponibles."
        ) from exc
    return section_force_distribution_3d


def _current_element_load_data() -> dict:
    try:
        from opsvis.model import get_Ew_data_from_ops_domain_3d
    except Exception:  # pragma: no cover - environment-dependent
        return {}
    if not callable(get_Ew_data_from_ops_domain_3d):
        return {}
    return get_Ew_data_from_ops_domain_3d()


_COMP_IDX: dict[str, int] = {
    "N": 0,
    "Vy": 1,
    "Vz": 2,
    "T": 3,
    "My": 4,
    "Mz": 5,
}


class OpenSeesBackend:
    """OpenSees backend."""

    engine_name = "opensees"
    supports_diagrams = True
    capabilities = {
        AnalysisFeature.STATIC_LINEAR: AnalysisCapability(
            feature=AnalysisFeature.STATIC_LINEAR,
            level=CapabilityLevel.READY,
            note="Disponible maintenant dans HEXA Structures via OpenSeesPy.",
        ),
        AnalysisFeature.MODAL: AnalysisCapability(
            feature=AnalysisFeature.MODAL,
            level=CapabilityLevel.READY,
            note="Disponible maintenant dans HEXA Structures via OpenSeesPy.",
        ),
        AnalysisFeature.PDELTA: AnalysisCapability(
            feature=AnalysisFeature.PDELTA,
            level=CapabilityLevel.ENGINE_ONLY,
            note="OpenSees le supporte ; raccordement HEXA Structures à faire.",
        ),
        AnalysisFeature.RESPONSE_SPECTRUM: AnalysisCapability(
            feature=AnalysisFeature.RESPONSE_SPECTRUM,
            level=CapabilityLevel.ENGINE_ONLY,
            note="Commande disponible côté OpenSees ; intégration HEXA Structures à faire.",
        ),
        AnalysisFeature.PUSHOVER: AnalysisCapability(
            feature=AnalysisFeature.PUSHOVER,
            level=CapabilityLevel.ENGINE_ONLY,
            note="OpenSees le supporte ; workflow HEXA Structures a implementer.",
        ),
        AnalysisFeature.TIME_HISTORY: AnalysisCapability(
            feature=AnalysisFeature.TIME_HISTORY,
            level=CapabilityLevel.ENGINE_ONLY,
            note="OpenSees le supporte ; workflow HEXA Structures a implementer.",
        ),
    }

    def __init__(self, project):
        self.project = project
        self.analysis_project = project
        self.builder = OpsBuilder(project)
        self.generated_plate_meshes = {}

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        ops = _require_opensees()

        self._prepare_analysis_model()
        self.builder.build(ndm=3, ndf=6)

        if combo_tag is not None:
            self.builder.apply_combination(combo_tag)
        elif load_tag is not None:
            self.builder.apply_loads(load_tag)
        else:
            return False, {"error": "Aucun cas de charge spécifié."}

        ops.constraints("Transformation")
        ops.numberer("Plain")
        ops.system("UmfPack")
        ops.test("NormDispIncr", tol, max_iter)
        ops.algorithm("Newton")
        ops.integrator("LoadControl", 1.0)
        ops.analysis("Static")

        result = ops.analyze(1)
        success = result == 0

        if success:
            extractor = ResultsExtractor(self.analysis_project)
            raw_results = extractor.get_all()
            self._attach_analysis_context(raw_results)
            results = map_analysis_results_to_user_results(
                user_project=self.project,
                analysis_project=self.analysis_project,
                raw_results=raw_results,
                generated_plate_meshes=self.generated_plate_meshes,
            )
        else:
            results = {"error": "L'analyse n'a pas convergé."}

        return success, results

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        ops = _require_opensees()

        self._prepare_analysis_model()
        self.builder.build(ndm=3, ndf=6)

        n_free_dof = sum(6 - sum(n.fixities) for n in self.analysis_project.nodes.values())
        num_modes = min(num_modes, n_free_dof)

        if num_modes <= 0:
            return False, {"error": "Aucun degré de liberté libre."}

        try:
            eigenvalues = ops.eigen(num_modes)
        except Exception as exc:
            return False, {"error": f"Échec de l'analyse modale : {exc}"}

        import math

        periods = []
        frequencies = []
        for ev in eigenvalues:
            if ev > 0:
                omega = math.sqrt(ev)
                freq = omega / (2 * math.pi)
                period = 1.0 / freq if freq > 0 else float("inf")
            else:
                freq = 0.0
                period = float("inf")
            frequencies.append(freq)
            periods.append(period)

        return True, {
            "eigenvalues": eigenvalues,
            "frequencies_hz": frequencies,
            "periods_s": periods,
            "num_modes": num_modes,
        }

    def _prepare_analysis_model(self) -> None:
        """Handle prepare analysis model."""
        self.analysis_project = build_analysis_model(self.project)
        self.generated_plate_meshes = getattr(
            self.analysis_project,
            "generated_plate_meshes",
            {},
        )
        self.builder = OpsBuilder(self.analysis_project)

    def _attach_analysis_context(self, results: dict) -> None:
        """Handle attach analysis context."""
        results["analysis_project"] = self.analysis_project
        results["generated_plate_meshes"] = self.generated_plate_meshes
        context = results.setdefault("result_context", {})
        context["user_node_count"] = len(self.project.nodes)
        context["analysis_node_count"] = len(self.analysis_project.nodes)
        context["user_surface_count"] = len(self.project.surface_elements)
        context["analysis_surface_count"] = len(self.analysis_project.surface_elements)
        context["plate_region_count"] = len(getattr(self.project, "plate_regions", {}))
        context["generated_plate_count"] = len(self.generated_plate_meshes)
        context["generated_plate_surface_count"] = sum(
            len(mesh.surface_tags) for mesh in self.generated_plate_meshes.values()
        )
        context["generated_plate_node_count"] = len(
            {
                int(node_tag)
                for mesh in self.generated_plate_meshes.values()
                for node_tag in mesh.node_tags.values()
            }
        )
        context["generated_plate_mesh_sizes"] = {
            int(plate_tag): (
                int(getattr(mesh, "mesh_nx", 0)),
                int(getattr(mesh, "mesh_ny", 0)),
            )
            for plate_tag, mesh in self.generated_plate_meshes.items()
        }

    def sample_diagram_component(
        self,
        element_tag: int,
        component: str,
        nep: int = 17,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Handle sample diagram component."""
        component_idx = _COMP_IDX.get(component)
        if component_idx is None:
            return None

        ops = _require_opensees()
        try:
            end_nodes = ops.eleNodes(element_tag)
        except Exception:
            return None
        if len(end_nodes) != 2:
            return None

        try:
            c1 = np.array(ops.nodeCoord(end_nodes[0]), dtype=float)
            c2 = np.array(ops.nodeCoord(end_nodes[1]), dtype=float)
            local_force = ops.eleResponse(element_tag, "localForce")
        except Exception:
            return None
        if len(local_force) != 12:
            return None
        if c1.size < 3:
            c1 = np.concatenate([c1, np.zeros(3 - c1.size)])
            c2 = np.concatenate([c2, np.zeros(3 - c2.size)])

        ecrd_3d = np.vstack([c1, c2])
        element_loads = _current_element_load_data().get(
            element_tag,
            [["-beamUniform", 0.0, 0.0, 0.0]],
        )
        try:
            section_force_distribution_3d = (
                _require_opsvis_section_force_distribution_3d()
            )
            sampled_forces, x, _ = section_force_distribution_3d(
                ecrd_3d,
                local_force,
                nep,
                element_loads,
            )
        except Exception:
            return None

        values = np.asarray(sampled_forces[:, component_idx], dtype=float)
        if component in {"N", "T"}:
            values = -values
        return np.asarray(x, dtype=float), values
