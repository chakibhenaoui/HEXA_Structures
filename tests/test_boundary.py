"""Tests pour les conditions aux limites et les combinaisons EC0."""

import pytest
from core.boundary_conditions import (
    BoundaryCondition,
    BoundaryType,
    PREDEFINED_FIXITIES,
    SpringStiffness,
    create_boundary,
    detect_boundary_type,
)
from core.model_data import (
    CombinationData,
    LoadData,
    NodalLoad,
    NodeData,
    ProjectModel,
    save_project,
    load_project,
)
from core.loads import (
    auto_generate_combinations,
    combination_formula,
    generate_uls_fundamental,
    generate_sls_characteristic,
    generate_sls_frequent,
    generate_sls_quasi_permanent,
    get_psi,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests BoundaryCondition
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaryCondition:
    """Tests pour les conditions aux limites."""

    def test_encastrement(self):
        bc = create_boundary(BoundaryType.ENCASTREMENT)
        assert bc.fixities == (1, 1, 1, 1, 1, 1)
        assert bc.is_fixed
        assert not bc.is_free
        assert len(bc.blocked_dofs) == 6

    def test_rotule(self):
        bc = create_boundary(BoundaryType.ROTULE)
        assert bc.fixities == (1, 1, 1, 0, 0, 0)
        assert not bc.is_fixed  # pas encastrement total
        assert not bc.is_free   # pas libre non plus
        assert len(bc.blocked_dofs) == 3
        assert len(bc.free_dofs) == 3

    def test_libre(self):
        bc = create_boundary(BoundaryType.FREE)
        assert bc.fixities == (0, 0, 0, 0, 0, 0)
        assert bc.is_free
        assert not bc.is_fixed

    def test_custom(self):
        bc = create_boundary(
            BoundaryType.CUSTOM,
            custom_fixities=(1, 0, 1, 0, 1, 0),
        )
        assert bc.fixities == (1, 0, 1, 0, 1, 0)
        assert bc.bc_type == BoundaryType.CUSTOM
        assert len(bc.blocked_dofs) == 3

    def test_detect_type(self):
        assert detect_boundary_type((1, 1, 1, 1, 1, 1)) == BoundaryType.ENCASTREMENT
        assert detect_boundary_type((1, 1, 1, 0, 0, 0)) == BoundaryType.ROTULE
        assert detect_boundary_type((0, 0, 0, 0, 0, 0)) == BoundaryType.FREE
        assert detect_boundary_type((1, 0, 0, 1, 0, 0)) == BoundaryType.CUSTOM

    def test_serialization(self):
        bc = create_boundary(BoundaryType.ROTULE, name="Appui A")
        d = bc.to_dict()
        bc2 = BoundaryCondition.from_dict(d)
        assert bc2.fixities == bc.fixities
        assert bc2.bc_type == bc.bc_type
        assert bc2.name == "Appui A"

    def test_springs(self):
        springs = SpringStiffness(kx=1000, ky=2000, kz=3000, krz=500)
        assert springs.has_springs
        bc = create_boundary(BoundaryType.FREE, springs=springs)
        assert not bc.is_free  # a des ressorts

        d = bc.to_dict()
        bc2 = BoundaryCondition.from_dict(d)
        assert bc2.springs.kx == 1000
        assert bc2.springs.krz == 500

    def test_summary(self):
        bc = create_boundary(BoundaryType.ROTULE)
        summary = bc.summary()
        assert "Ux" in summary
        assert "Uy" in summary
        assert "Uz" in summary

    def test_all_predefined_types(self):
        """Vérifie que tous les types prédéfinis sont cohérents."""
        for bc_type in BoundaryType:
            fix = PREDEFINED_FIXITIES[bc_type]
            assert len(fix) == 6
            assert all(f in (0, 1) for f in fix)


# ═══════════════════════════════════════════════════════════════════════════
#  Tests NodeData 3D
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeData3D:
    """Tests pour le modèle de données 3D."""

    def test_node_6dof(self):
        node = NodeData(tag=1, x=1.0, y=2.0, z=3.0,
                        fixities=(1, 1, 1, 0, 0, 0))
        assert node.is_fixed
        assert node.is_support
        assert len(node.fixities) == 6

    def test_node_free(self):
        node = NodeData(tag=2, x=0.0, y=0.0, z=0.0)
        assert not node.is_fixed
        assert not node.is_support

    def test_nodal_load_3d(self):
        nl = NodalLoad(load_tag=1, node_tag=1,
                       fx=10.0, fy=-20.0, fz=5.0,
                       mx=1.0, my=2.0, mz=3.0)
        assert nl.as_tuple() == (10.0, -20.0, 5.0, 1.0, 2.0, 3.0)

    def test_save_load_3d(self, tmp_path):
        """Vérifie la persistance SQLite avec les données 3D."""
        project = ProjectModel(name="Test 3D")
        project.add_node(1.0, 2.0, 3.0, fixities=(1, 1, 1, 1, 1, 1))
        project.add_node(4.0, 5.0, 6.0)

        db_path = tmp_path / "test3d.db"
        save_project(project, db_path)

        loaded = load_project(db_path)
        assert len(loaded.nodes) == 2
        n1 = loaded.nodes[1]
        assert n1.z == 3.0
        assert n1.fixities == (1, 1, 1, 1, 1, 1)
        assert n1.is_fixed


# ═══════════════════════════════════════════════════════════════════════════
#  Tests Combinaisons EC0
# ═══════════════════════════════════════════════════════════════════════════


class TestCombinationsEC0:
    """Tests pour la génération automatique des combinaisons EC0."""

    @pytest.fixture
    def loads(self):
        """Cas de charge type : G + Q (bureau) + S (neige)."""
        return {
            1: LoadData(tag=1, name="G1", load_type="dead", category=""),
            2: LoadData(tag=2, name="Q1", load_type="live", category="B"),
            3: LoadData(tag=3, name="S1", load_type="snow", category="snow"),
        }

    def test_psi_coefficients(self):
        psi0, psi1, psi2 = get_psi("B")  # Bureaux
        assert psi0 == 0.7
        assert psi1 == 0.5
        assert psi2 == 0.3

    def test_psi_snow(self):
        psi0, psi1, psi2 = get_psi("snow")
        assert psi0 == 0.5
        assert psi1 == 0.2
        assert psi2 == 0.0

    def test_uls_fundamental(self, loads):
        """ELU : 2 combinaisons (Q dominant, S dominant)."""
        perm = [1]
        var = [loads[2], loads[3]]
        combos = generate_uls_fundamental(perm, var)

        assert len(combos) == 2

        # Q dominant : 1.35*G + 1.50*Q + 1.50*0.5*S
        c1 = combos[0]
        assert c1[1] == 1.35  # G
        assert c1[2] == 1.50  # Q dominant
        assert abs(c1[3] - 1.50 * 0.5) < 1e-10  # S accompagnement

        # S dominant : 1.35*G + 1.50*S + 1.50*0.7*Q
        c2 = combos[1]
        assert c2[1] == 1.35
        assert c2[3] == 1.50  # S dominant
        assert abs(c2[2] - 1.50 * 0.7) < 1e-10  # Q accompagnement

    def test_sls_characteristic(self, loads):
        perm = [1]
        var = [loads[2], loads[3]]
        combos = generate_sls_characteristic(perm, var)
        assert len(combos) == 2
        # G + Q + ψ₀*S
        assert combos[0][1] == 1.0  # G
        assert combos[0][2] == 1.0  # Q dominant

    def test_sls_frequent(self, loads):
        perm = [1]
        var = [loads[2], loads[3]]
        combos = generate_sls_frequent(perm, var)
        assert len(combos) == 2
        # G + ψ₁*Q + ψ₂*S
        assert combos[0][1] == 1.0  # G
        assert combos[0][2] == 0.5  # ψ₁ bureaux

    def test_sls_quasi_permanent(self, loads):
        perm = [1]
        var = [loads[2], loads[3]]
        combos = generate_sls_quasi_permanent(perm, var)
        assert len(combos) == 1
        # G + ψ₂*Q (neige ψ₂=0 donc pas de S)
        c = combos[0]
        assert c[1] == 1.0  # G
        assert c[2] == 0.3  # ψ₂ bureaux
        assert 3 not in c  # neige ψ₂=0

    def test_auto_generate(self, loads):
        """Génération automatique de toutes les combinaisons."""
        combos = auto_generate_combinations(loads)
        # 2 ELU + 2 ELS car. + 2 ELS fréq. + 1 ELS QP = 7
        assert len(combos) == 7
        # Vérifier les tags uniques
        tags = [c.tag for c in combos]
        assert len(set(tags)) == len(tags)

    def test_combination_formula(self, loads):
        combo = CombinationData(
            tag=1, name="ELU 1", combo_type="ELU",
            factors={1: 1.35, 2: 1.50, 3: 0.75},
        )
        formula = combination_formula(combo, loads)
        assert "1.35" in formula
        assert "G1" in formula
        assert "Q1" in formula

    def test_permanent_only(self):
        """Avec seulement des permanentes."""
        loads = {1: LoadData(tag=1, name="G", load_type="dead")}
        combos = auto_generate_combinations(loads)
        assert len(combos) >= 1
        # ELU : 1.35*G
        elu = [c for c in combos if c.combo_type == "ELU"]
        assert len(elu) == 1
        assert elu[0].factors[1] == 1.35
