"""Helpers for test model data."""

import pytest

from core.model_data import (
    CombinationData,
    ElementLoad,
    LoadData,
    NodalLoad,
    NodeData,
    PlateEdgeSupportData,
    PlateSurfaceLoadData,
    ProjectModel,
    SurfaceLoad,
    load_project,
    save_project,
)


class TestNodeData:
    def test_fixities_free(self):
        node = NodeData(tag=1, x=0, y=0)
        assert node.fixities == (0, 0, 0, 0, 0, 0)
        assert not node.is_fixed

    def test_fixities_pinned(self):
        """Test fixities pinned."""
        node = NodeData(tag=1, x=0, y=0, fixities=(1, 1, 1, 0, 0, 0))
        assert node.is_fixed
        assert node.is_support

    def test_fixities_fixed(self):
        """Test fixities fixed."""
        node = NodeData(tag=1, x=0, y=0, fixities=(1, 1, 1, 1, 1, 1))
        assert node.is_fixed
        assert node.is_support

    def test_node_3d(self):
        node = NodeData(tag=1, x=1.0, y=2.0, z=3.0)
        assert node.z == 3.0


class TestProjectModel:
    def test_empty_project(self):
        p = ProjectModel()
        assert len(p.nodes) == 0
        assert p.stats["nodes"] == 0

    def test_add_node(self):
        p = ProjectModel()
        n = p.add_node(3.0, 5.0)
        assert n.tag == 1
        assert n.x == 3.0
        assert n.y == 5.0
        assert len(p.nodes) == 1

    def test_add_multiple_nodes(self):
        p = ProjectModel()
        p.add_node(0, 0)
        p.add_node(3, 0)
        p.add_node(6, 0)
        assert len(p.nodes) == 3
        assert p.next_node_tag() == 4

    def test_add_element(self):
        p = ProjectModel()
        p.add_node(0, 0)
        p.add_node(5, 0)
        p.add_section("Rect 30x50", "rectangular", 1)
        e = p.add_element(node_i=1, node_j=2, section_tag=1)
        assert e.tag == 1
        assert e.node_i == 1
        assert e.node_j == 2

    def test_add_element_rejects_surface_section(self):
        p = ProjectModel()
        p.add_node(0, 0)
        p.add_node(5, 0)
        p.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})

        with pytest.raises(ValueError, match="line/bar section"):
            p.add_element(node_i=1, node_j=2, section_tag=1)

    def test_add_material(self):
        p = ProjectModel()
        m = p.add_material("Béton C30", "concrete", "C30/37")
        assert m.tag == 1
        assert m.grade == "C30/37"

    def test_add_surface_element(self):
        p = ProjectModel()
        p.add_node(0, 0, 0)
        p.add_node(5, 0, 0)
        p.add_node(5, 4, 0)
        p.add_node(0, 4, 0)
        p.add_material("Béton C30", "concrete", "C30/37")
        p.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})

        surface = p.add_surface_element((1, 2, 3, 4), section_tag=1, surface_type="plate")

        assert surface.tag == 1
        assert surface.node_tags == (1, 2, 3, 4)
        assert surface.section_tag == 1
        assert surface.surface_type == "plate"
        assert surface.is_quad
        assert not surface.is_triangle
        assert p.sections[1].is_surface
        assert p.sections[1].thickness == pytest.approx(0.20)

    def test_add_surface_element_rejects_invalid_connectivity(self):
        p = ProjectModel()

        with pytest.raises(ValueError):
            p.add_surface_element((1, 2), section_tag=1)

        with pytest.raises(ValueError):
            p.add_surface_element((1, 2, 2), section_tag=1)

    def test_add_plate_region(self):
        p = ProjectModel()
        p.add_node(0, 0, 0)
        p.add_node(5, 0, 0)
        p.add_node(5, 4, 0)
        p.add_node(0, 4, 0)
        p.add_material("Beton C30", "concrete", "C30/37")
        p.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})

        plate = p.add_plate_region((1, 2, 3, 4), section_tag=1, mesh_nx=4, mesh_ny=3)

        assert plate.tag == 1
        assert plate.corner_node_tags == (1, 2, 3, 4)
        assert plate.mesh_nx == 4
        assert plate.mesh_ny == 3
        assert plate.mesh_mode == "user"
        assert plate.formulation == "ShellMITC4"
        assert p.next_plate_region_tag() == 2

    def test_add_plate_region_uses_section_formulation_by_default(self):
        p = ProjectModel()
        p.add_node(0, 0, 0)
        p.add_node(5, 0, 0)
        p.add_node(5, 4, 0)
        p.add_node(0, 4, 0)
        p.add_material("Beton C30", "concrete", "C30/37")
        p.add_section(
            "Dalle DKGQ",
            "surface",
            1,
            properties={"thickness": 0.20, "element_formulation": "ShellDKGQ"},
        )

        plate = p.add_plate_region((1, 2, 3, 4), section_tag=1)

        assert plate.formulation == "ShellDKGQ"
        assert plate.mesh_mode == "auto"

    def test_clear(self):
        p = ProjectModel()
        p.add_node(0, 0)
        p.add_node(5, 0)
        p.add_material("Acier", "steel", "S355")
        p.add_section("Dalle", "surface", 1, properties={"thickness": 0.20})
        p.add_node(5, 4)
        p.add_node(0, 4)
        p.add_plate_region((1, 2, 3, 4), section_tag=1)
        p.clear()
        assert len(p.nodes) == 0
        assert len(p.materials) == 0
        assert len(p.plate_regions) == 0

    def test_stats(self):
        p = ProjectModel()
        p.add_node(0, 0)
        p.add_node(5, 0)
        p.add_material("Acier", "steel", "S355")
        p.add_section("Dalle", "surface", 1, properties={"thickness": 0.20})
        p.add_node(5, 4)
        p.add_node(0, 4)
        p.add_plate_region((1, 2, 3, 4), section_tag=1)
        s = p.stats
        assert s["nodes"] == 4
        assert s["materials"] == 1
        assert s["elements"] == 0
        assert s["surface_elements"] == 0
        assert s["plate_regions"] == 1

    def test_copy_for_load_editing_isolates_loading_state(self):
        p = ProjectModel(name="Chargements")
        p.add_node(0, 0)
        p.add_node(5, 0)
        p.add_material("Acier", "steel", "S355")
        p.add_section("Rect 30x50", "rectangular", 1)
        p.add_element(node_i=1, node_j=2, section_tag=1)
        p.add_surface_element((1, 2, 3), section_tag=1)
        p.loads[1] = LoadData(tag=1, name="Exploitation", load_type="variable")
        p.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fy=-12.0))
        p.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-2.5))
        p.plate_surface_loads.append(PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-3.0))
        p.combinations[1] = CombinationData(
            tag=1,
            name="ELU",
            combo_type="ELU",
            factors={1: 1.5},
        )

        clone = p.copy_for_load_editing()

        assert clone is not p
        assert clone.nodes is p.nodes
        assert clone.elements is p.elements
        assert clone.surface_elements is p.surface_elements
        assert clone.plate_regions is p.plate_regions
        assert clone.materials is p.materials
        assert clone.sections is p.sections
        assert clone.loads is not p.loads
        assert clone.nodal_loads is not p.nodal_loads
        assert clone.surface_loads is not p.surface_loads
        assert clone.plate_surface_loads is not p.plate_surface_loads
        assert clone.combinations is not p.combinations

        clone.loads[1].name = "Copie"
        clone.nodal_loads[0].fy = -20.0
        clone.surface_loads[0].qz = -4.0
        clone.plate_surface_loads[0].qz = -6.0
        clone.combinations[1].factors[1] = 1.35

        assert p.loads[1].name == "Exploitation"
        assert p.nodal_loads[0].fy == -12.0
        assert p.surface_loads[0].qz == -2.5
        assert p.plate_surface_loads[0].qz == -3.0
        assert p.combinations[1].factors[1] == 1.5


class TestSQLitePersistence:
    def test_save_and_load(self, tmp_path):
        """Test save and load."""
        db_path = tmp_path / "test_project.db"

        # Create a project with 6-DOF fixities
        p = ProjectModel(name="Test projet")
        p.add_node(0, 0, fixities=(1, 1, 1, 1, 1, 1))  # encastrement
        p.add_node(5, 0)
        p.add_node(10, 0, fixities=(1, 1, 1, 0, 0, 0))  # rotule
        p.add_node(0, 4, 0)
        p.add_node(5, 4, 0)
        p.add_material("Acier S355", "steel", "S355")
        p.add_section("IPE 300", "I_profile", material_tag=1, area=0.00538, inertia_y=8.36e-5)
        p.add_section("Dalle 20 cm", "surface", material_tag=1, properties={"thickness": 0.20})
        p.add_element(
            1,
            2,
            section_tag=1,
            orientation_vector=(0.0, 0.0, 1.0),
            roll_angle_deg=15.0,
        )
        p.add_element(2, 3, section_tag=1)
        p.add_surface_element((1, 2, 5, 4), section_tag=2)
        p.add_plate_region(
            (1, 2, 5, 4),
            section_tag=2,
            name="Dalle macro",
            mesh_nx=4,
            mesh_ny=3,
        )
        p.loads[1] = LoadData(tag=1, name="Charges dalle", load_type="variable")
        p.element_loads.append(
            ElementLoad(
                load_tag=1,
                element_tag=1,
                wz=-10.0,
                coordinate_system="global",
            )
        )
        p.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-3.5))
        p.plate_surface_loads.append(PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.5))
        p.plate_edge_supports.append(
            PlateEdgeSupportData(
                plate_tag=1,
                edge="12",
                fixities=(1, 1, 1, 0, 0, 0),
            )
        )

        # Sauvegarder
        save_project(p, db_path)
        assert db_path.exists()

        # Recharger
        p2 = load_project(db_path)
        assert p2.name == "Test projet"
        assert len(p2.nodes) == 5
        assert len(p2.elements) == 2
        assert len(p2.surface_elements) == 1
        assert len(p2.plate_regions) == 1
        assert len(p2.materials) == 1
        assert len(p2.sections) == 2
        assert len(p2.surface_loads) == 1
        assert len(p2.plate_surface_loads) == 1
        assert len(p2.plate_edge_supports) == 1

        # Check 6-DOF fixities
        assert p2.nodes[1].fixities == (1, 1, 1, 1, 1, 1)
        assert p2.nodes[2].fixities == (0, 0, 0, 0, 0, 0)
        assert p2.nodes[3].fixities == (1, 1, 1, 0, 0, 0)
        assert p2.nodes[1].is_fixed
        assert not p2.nodes[2].is_fixed
        assert p2.elements[1].node_i == 1
        assert p2.elements[1].node_j == 2
        assert p2.elements[1].orientation_vector == (0.0, 0.0, 1.0)
        assert p2.elements[1].roll_angle_deg == pytest.approx(15.0)
        assert p2.elements[2].orientation_vector is None
        assert p2.element_loads[0].coordinate_system == "global"
        assert p2.element_loads[0].wz == -10.0
        assert p2.surface_elements[1].node_tags == (1, 2, 5, 4)
        assert p2.surface_elements[1].is_quad
        assert p2.plate_regions[1].corner_node_tags == (1, 2, 5, 4)
        assert p2.plate_regions[1].mesh_nx == 4
        assert p2.plate_regions[1].mesh_ny == 3
        assert p2.plate_regions[1].mesh_mode == "user"
        assert p2.surface_loads[0].surface_tag == 1
        assert p2.surface_loads[0].qz == -3.5
        assert p2.plate_surface_loads[0].plate_tag == 1
        assert p2.plate_surface_loads[0].qz == -2.5
        assert p2.plate_edge_supports[0].edge == "12"
        assert p2.materials[1].grade == "S355"
        assert abs(p2.sections[1].area - 0.00538) < 1e-8

    def test_save_empty_project(self, tmp_path):
        db_path = tmp_path / "empty.db"
        p = ProjectModel(name="Vide")
        save_project(p, db_path)
        p2 = load_project(db_path)
        assert p2.name == "Vide"
        assert len(p2.nodes) == 0

    def test_load_syncs_plate_region_formulation_with_surface_section(self, tmp_path):
        db_path = tmp_path / "plate_formulation.db"
        p = ProjectModel(name="Formulation sync")
        p.add_node(0, 0, 0)
        p.add_node(2, 0, 0)
        p.add_node(2, 2, 0)
        p.add_node(0, 2, 0)
        p.add_material("Beton C30", "concrete", "C30/37")
        p.add_section(
            "Dalle DKGQ",
            "surface",
            material_tag=1,
            properties={"thickness": 0.20, "element_formulation": "ShellDKGQ"},
        )
        plate = p.add_plate_region(
            (1, 2, 3, 4),
            section_tag=1,
            formulation="ShellMITC4",
        )
        assert plate.formulation == "ShellMITC4"

        save_project(p, db_path)
        loaded = load_project(db_path)

        assert loaded.plate_regions[1].formulation == "ShellDKGQ"
