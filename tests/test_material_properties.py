import math

from core.material_properties import (
    compute_shear_modulus,
    isotropic_material_properties,
)
from core.model_data import ProjectModel
from core.ops_builder import OpsBuilder
from core.self_weight import total_self_weight_kn


def test_seed_default_library_materials_receive_isotropic_properties() -> None:
    project = ProjectModel()
    project.seed_default_library()

    concrete = next(
        mat for mat in project.materials.values()
        if mat.material_type == "concrete"
    )
    props = isotropic_material_properties(
        concrete.material_type,
        concrete.grade,
        concrete.properties,
    )

    assert math.isclose(props["unit_weight"], 25.0, rel_tol=1e-12)
    assert props["young_modulus"] == 33_000_000.0
    assert props["poisson_ratio"] == 0.2


def test_legacy_density_and_moduli_are_normalized() -> None:
    props = isotropic_material_properties(
        "steel",
        "S355",
        {"rho": 7.85, "E": 205_000_000.0, "nu": 0.28},
    )

    assert math.isclose(props["unit_weight"], 77.0085, rel_tol=1e-9)
    assert props["young_modulus"] == 205_000_000.0
    assert props["poisson_ratio"] == 0.28


def test_self_weight_uses_unit_weight_property() -> None:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5.0, 0.0, 0.0)
    material = project.add_material(
        "Acier custom",
        "steel",
        "S355",
        unit_weight=50.0,
        young_modulus=210_000_000.0,
        poisson_ratio=0.3,
    )
    project.add_section(
        "Section test",
        "rectangular",
        material_tag=material.tag,
        area=0.01,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    project.add_element(1, 2, section_tag=1)

    assert math.isclose(total_self_weight_kn(project), 2.5, rel_tol=1e-12)


def test_ops_builder_uses_material_isotropic_properties() -> None:
    project = ProjectModel()
    material = project.add_material(
        "Beton custom",
        "concrete",
        "C30/37",
        unit_weight=23.0,
        young_modulus=31_500_000.0,
        poisson_ratio=0.22,
    )
    builder = OpsBuilder(project)

    assert builder._get_elastic_modulus(material.tag) == 31_500_000.0
    assert math.isclose(
        builder._get_shear_modulus(material.tag),
        compute_shear_modulus(31_500_000.0, 0.22),
        rel_tol=1e-12,
    )
