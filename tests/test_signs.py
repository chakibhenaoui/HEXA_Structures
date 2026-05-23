"""Helpers for test signs."""
import pytest

ops = pytest.importorskip("openseespy.opensees")


def test_cantilever():
    """Test cantilever."""
    print("=" * 60)
    print("TEST 1 : Console encastrée, charge ponctuelle P = 10 kN ↓")
    print("=" * 60)

    ops.wipe()
    ops.model('basic', '-ndm', 3, '-ndf', 6)

    # Nodes: horizontal cantilever along X, Z = vertical
    ops.node(1, 0.0, 0.0, 0.0)  # encastrement
    ops.node(2, 3.0, 0.0, 0.0)  # free end

    ops.fix(1, 1, 1, 1, 1, 1, 1)

    # Material and section
    E = 210e6  # kN/m²
    A = 0.01   # m²
    Iz = 1e-4  # m⁴
    Iy = 1e-4
    G = 80e6
    J = 2e-4

    ops.geomTransf('Linear', 1, 0.0, 0.0, 1.0)  # vecxz = Z
    ops.element('elasticBeamColumn', 1, 1, 2, A, E, G, J, Iy, Iz, 1)

    # Load: P = 10 kN downward at node 2
    ops.timeSeries('Linear', 1)
    ops.pattern('Plain', 1, 1)
    ops.load(2, 0.0, 0.0, -10.0, 0.0, 0.0, 0.0)

    ops.system('BandGeneral')
    ops.numberer('RCM')
    ops.constraints('Plain')
    ops.integrator('LoadControl', 1.0)
    ops.algorithm('Linear')
    ops.analysis('Static')
    ops.analyze(1)

    # --- Results ---
    print("\n--- eleForce (GLOBAL) ---")
    ef = ops.eleForce(1)
    print(f"  Node I (6 val) : {[f'{v:+.4f}' for v in ef[:6]]}")
    print(f"  Node J (6 val) : {[f'{v:+.4f}' for v in ef[6:]]}")

    print("\n--- eleResponse localForce (LOCAL) ---")
    lf = ops.eleResponse(1, 'localForce')
    print(f"  Node I (6 val) : {[f'{v:+.4f}' for v in lf[:6]]}")
    print(f"  Node J (6 val) : {[f'{v:+.4f}' for v in lf[6:]]}")

    print("\n--- eleResponse basicForce (BASIC, 6 val) ---")
    bf = ops.eleResponse(1, 'basicForce')
    print(f"  basicForce : {[f'{v:+.4f}' for v in bf]}")

    print("\n--- Réactions ---")
    ops.reactions()
    r1 = ops.nodeReaction(1)
    print(f"  Réaction nœud 1 : {[f'{v:+.4f}' for v in r1]}")

    print("\n--- Solution analytique ---")
    print("  Réaction: Fz=+10, My=+30 (hogging = retient la console)")
    print("  Forces internes (convention RDM) :")
    print("    N  = 0 partout")
    print("    Vz = +10 kN (positif)")
    print("    My(0) = +30 kN·m (hogging)")
    print("    My(L) = 0")

    print("\n--- Interprétation localForce ---")
    print(f"  N_i  = lf[0] = {lf[0]:+.4f}  (attendu: ~0)")
    print(f"  Vy_i = lf[1] = {lf[1]:+.4f}  (attendu: ~0)")
    print(f"  Vz_i = lf[2] = {lf[2]:+.4f}  (signe: +10 ou -10 ?)")
    print(f"  T_i  = lf[3] = {lf[3]:+.4f}  (attendu: ~0)")
    print(f"  My_i = lf[4] = {lf[4]:+.4f}  (signe: +30 ou -30 ?)")
    print(f"  Mz_i = lf[5] = {lf[5]:+.4f}  (attendu: ~0)")
    print(f"  N_j  = lf[6] = {lf[6]:+.4f}")
    print(f"  Vy_j = lf[7] = {lf[7]:+.4f}")
    print(f"  Vz_j = lf[8] = {lf[8]:+.4f}")
    print(f"  T_j  = lf[9] = {lf[9]:+.4f}")
    print(f"  My_j = lf[10]= {lf[10]:+.4f}")
    print(f"  Mz_j = lf[11]= {lf[11]:+.4f}")

    ops.wipe()


def test_portal_frame():
    """Test portal frame."""
    print("\n" + "=" * 60)
    print("TEST 2 : Portique plan 3x3m, encastré, w=10 kN/m sur poutre")
    print("=" * 60)

    ops.wipe()
    ops.model('basic', '-ndm', 3, '-ndf', 6)

    # Nodes
    ops.node(1, 0.0, 0.0, 0.0)  # pied gauche
    ops.node(2, 0.0, 0.0, 3.0)  # left top node
    ops.node(3, 3.0, 0.0, 3.0)  # right top node
    ops.node(4, 3.0, 0.0, 0.0)  # pied droit

    ops.fix(1, 1, 1, 1, 1, 1, 1)
    ops.fix(4, 1, 1, 1, 1, 1, 1)

    E = 210e6
    A = 0.01
    Iz = 1e-4
    Iy = 1e-4
    G = 80e6
    J = 2e-4

    # GeomTransf: columns (vertical, vecxz=X), beam (horizontal, vecxz=Z)
    ops.geomTransf('Linear', 1, 1.0, 0.0, 0.0)  # columns
    ops.geomTransf('Linear', 2, 0.0, 0.0, 1.0)  # beam

    ops.element('elasticBeamColumn', 1, 1, 2, A, E, G, J, Iy, Iz, 1)  # left column
    ops.element('elasticBeamColumn', 2, 2, 3, A, E, G, J, Iy, Iz, 2)  # beam
    ops.element('elasticBeamColumn', 3, 4, 3, A, E, G, J, Iy, Iz, 1)  # right column

    # Distributed load 10 kN/m downward on beam E2
    ops.timeSeries('Linear', 1)
    ops.pattern('Plain', 1, 1)
    ops.eleLoad('-ele', 2, '-type', '-beamUniform', 0.0, -10.0)
    # beamUniform: wy, wz in local coordinates
    # For a horizontal beam: local z ~ global Z, wz = -10 = downward

    ops.system('BandGeneral')
    ops.numberer('RCM')
    ops.constraints('Plain')
    ops.integrator('LoadControl', 1.0)
    ops.algorithm('Linear')
    ops.analysis('Static')
    ops.analyze(1)

    # --- Results ---
    print("\n--- Réactions ---")
    ops.reactions()
    r1 = ops.nodeReaction(1)
    r4 = ops.nodeReaction(4)
    print(f"  Nœud 1 : {[f'{v:+.4f}' for v in r1]}")
    print(f"  Nœud 4 : {[f'{v:+.4f}' for v in r4]}")

    for etag, name in [(1, "Colonne gauche E1 (1→2)"),
                        (2, "Poutre E2 (2→3)"),
                        (3, "Colonne droite E3 (4→3)")]:
        print(f"\n--- {name} ---")

        ef = ops.eleForce(etag)
        print(f"  eleForce (global) I: {[f'{v:+.3f}' for v in ef[:6]]}")
        print(f"  eleForce (global) J: {[f'{v:+.3f}' for v in ef[6:]]}")

        lf = ops.eleResponse(etag, 'localForce')
        print(f"  localForce       I: {[f'{v:+.3f}' for v in lf[:6]]}")
        print(f"  localForce       J: {[f'{v:+.3f}' for v in lf[6:]]}")

        print("  Interprétation localForce I:")
        print(f"    N_i={lf[0]:+.3f}  Vy_i={lf[1]:+.3f}  Vz_i={lf[2]:+.3f}")
        print(f"    T_i={lf[3]:+.3f}  My_i={lf[4]:+.3f}  Mz_i={lf[5]:+.3f}")

    ops.wipe()


if __name__ == "__main__":
    test_cantilever()
    test_portal_frame()
