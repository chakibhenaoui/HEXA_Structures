from core.model_data import ProjectModel
from core.self_weight import SELF_WEIGHT_LOAD_NAME, SELF_WEIGHT_LOAD_TYPE


def test_seed_default_library_populates_empty_project():
    project = ProjectModel()

    project.seed_default_library()

    assert len(project.materials) == 2
    assert len(project.sections) == 1
    assert len(project.loads) == 1

    concrete = next(
        mat for mat in project.materials.values()
        if mat.material_type == "concrete"
    )
    steel = next(
        mat for mat in project.materials.values()
        if mat.material_type == "steel"
    )
    section = next(iter(project.sections.values()))

    assert concrete.grade == "C30/37"
    assert steel.grade == "S355"
    assert section.name == "Section BA 30x30"
    assert section.material_tag == concrete.tag
    assert section.properties == {"b": 0.30, "h": 0.30}
    load = next(iter(project.loads.values()))
    assert load.name == SELF_WEIGHT_LOAD_NAME
    assert load.load_type == SELF_WEIGHT_LOAD_TYPE


def test_seed_default_library_does_not_duplicate_existing_library():
    project = ProjectModel()
    project.seed_default_library()

    project.seed_default_library()

    assert len(project.materials) == 2
    assert len(project.sections) == 1
    assert len(project.loads) == 1
