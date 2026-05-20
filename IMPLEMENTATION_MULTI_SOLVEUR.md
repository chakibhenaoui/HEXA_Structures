# HEXA Structures - Guide d'Implementation Multi-Solveur

> **Document de travail** — Mars 2026
> Objectif : implémenter l'architecture multi-solveur (PyNite par défaut + OpenSeesPy optionnel)

---

## 1. Vision et Stratégie

### 1.1 Pourquoi deux solveurs ?

Le logiciel HEXA Structures vise un double public. D'un côté les ingénieurs BTP qui font du dimensionnement courant (statique linéaire, vérifications EC2/EC3, descente de charges), de l'autre les ingénieurs spécialisés en sismique et non-linéaire. Le premier groupe n'a pas besoin d'OpenSeesPy et de ses complications de licence. Le second veut la puissance d'OpenSees pour le pushover, les sections fibrées, l'analyse temporelle.

La solution : **PyNite bundlé par défaut** (licence MIT, zéro installation supplémentaire), **OpenSeesPy en option** installé par l'utilisateur via `pip install openseespy`. On ne redistribue pas OpenSeesPy → on contourne proprement la restriction de licence UC Berkeley.

### 1.2 Principe architectural

```
┌─────────────────────────────────────────────────────────┐
│                    GUI (PySide6)                         │
│   ┌──────────────────────────────────────────┐          │
│   │ Paramètres > Moteur de calcul :          │          │
│   │  ● PyNite (intégré)                      │          │
│   │  ○ OpenSeesPy (optionnel)                │          │
│   └──────────────────────────────────────────┘          │
├─────────────────────────────────────────────────────────┤
│              core/solvers/solver_manager.py               │
│   detect() → quels solveurs disponibles ?                │
│   create_backend(model, engine) → SolverBackend          │
├────────────────────┬────────────────────────────────────┤
│  PyNiteBackend     │  OpenSeesBackend                    │
│  (pynite_backend)  │  (opensees_backend)                 │
│                    │                                     │
│  Lit ProjectModel  │  Délègue aux plugins existants      │
│  → API FEModel3D   │  (ops_builder + MaterialPlugin...)  │
│                    │  → commandes openseespy             │
├────────────────────┴────────────────────────────────────┤
│           StaticResult / ModalResult / SpectralResult     │
│           (format unique, indépendant du solveur)        │
├─────────────────────────────────────────────────────────┤
│  Post-traitement, vérifications EC2/EC3, Vue 3D PyVista  │
│  → Ne connaissent QUE les types standardisés             │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Règle d'or

> **Aucun module en dehors de `core/solvers/` ne doit importer `openseespy` ni `PyNite`.**
> Tout le code applicatif (GUI, post-traitement, vérifications, export) travaille
> exclusivement avec `StaticResult`, `ModalResult` et `SpectralResult`.

---

## 2. Arborescence des Fichiers

### 2.1 Nouveaux fichiers à créer

```
hexa_structures/
├── core/
│   ├── solvers/                          ← NOUVEAU PACKAGE
│   │   ├── __init__.py                   ← Expose les types publics
│   │   ├── base.py                       ← ABC SolverBackend + types résultats
│   │   ├── pynite_backend.py             ← Backend PyNite (défaut)
│   │   ├── opensees_backend.py           ← Backend OpenSees (optionnel)
│   │   └── solver_manager.py             ← Gestionnaire central
│   │
│   ├── spectral_ec8.py                   ← NOUVEAU — post-traitement spectral
│   │
│   ├── plugins/                          ← EXISTANT (inchangé)
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── materials/
│   │   ├── elements/
│   │   └── analyses/
│   │
│   ├── ops_builder.py                    ← EXISTANT (inchangé, utilisé par OpenSeesBackend)
│   ├── model_data.py                     ← EXISTANT (inchangé)
│   └── ...
│
├── gui/
│   ├── dialogs/
│   │   └── solver_settings_dlg.py        ← NOUVEAU — dialogue sélection solveur
│   └── ...
│
├── config/
│   └── settings.py                       ← MODIFIÉ — ajouter solver_engine
│
└── requirements.txt / pyproject.toml     ← MODIFIÉ — PyNite obligatoire, OpenSees optionnel
```

### 2.2 Fichiers existants à modifier

| Fichier | Modification | Effort |
|---------|-------------|--------|
| `config/settings.py` | Ajouter paramètre `solver_engine` (défaut: "pynite") | Faible |
| `gui/main_window.py` | Ajouter menu "Paramètres > Moteur de calcul" | Faible |
| `pyproject.toml` | Dépendance `PyNiteFEA` obligatoire, `openseespy` optionnel | Faible |
| Code d'analyse (future) | Utiliser `SolverManager` au lieu d'appeler `ops` directement | Moyen |

### 2.3 Fichiers existants NON modifiés

Le système de plugins (`base.py`, `registry.py`, `concrete_ec2.py`, `steel_ec3.py`, `beam_2d.py`, `static_linear.py`) et l'`ops_builder.py` restent **inchangés**. Le backend OpenSees les réutilise tels quels. C'est l'un des avantages de cette architecture : on ne casse rien de ce qui existe.

---

## 3. Étapes d'Implémentation

### Étape 1 — Créer le package `core/solvers/` (types et contrats)

**Fichier : `core/solvers/base.py` (~200 lignes)**

C'est la fondation. On y définit :

- `SolverEngine` : enum avec `PYNITE` et `OPENSEES`
- `StaticResult` : dataclass avec `displacements`, `reactions`, `element_forces`
- `ModalResult` : dataclass avec `eigenvalues`, `frequencies`, `periods`, `mode_shapes`
- `SpectralResult` : dataclass avec enveloppes de résultats et `base_shear`
- `SolverBackend` : ABC avec les méthodes `build_model()`, `run_static()`, `run_modal()`, `clear()`

**Points d'attention :**

- Les dataclasses utilisent `field(default_factory=dict)` pour éviter les problèmes de mutabilité
- `SolverBackend.__init__` prend un `ProjectModel` en paramètre — le backend ne le modifie jamais
- `get_capabilities()` retourne un dict de bools pour que la GUI sache griser les options non supportées
- Toutes les valeurs sont en **unités internes du projet** : kN, m, kPa

**Vérification :** Après cette étape, on peut importer `from core.solvers.base import StaticResult` sans erreur, même sans PyNite ni OpenSees installés.

---

### Étape 2 — Implémenter le backend PyNite

**Fichier : `core/solvers/pynite_backend.py` (~490 lignes)**

C'est le cœur du solveur par défaut. Il lit le `ProjectModel` et le traduit en appels `PyNite.FEModel3D`.

**Traduction des concepts :**

| ProjectModel | PyNite FEModel3D |
|---|---|
| `NodeData(tag=1, x=0, y=0)` | `add_node("N1", 0, 0, 0)` |
| `fixities=(1,1,1)` | `def_support("N1", True, True, True, True, True, True)` |
| `ElementData(tag=1, ni=1, nj=2)` | `add_member("E1", "N1", "N2", E, G, Iy, Iz, J, A)` |
| Charge nodale `(Fx, Fy, Mz)` | `add_node_load("N1", "FX", Fx)` |

**Points d'attention :**

- **Noms vs tags** : PyNite utilise des strings (`"N1"`, `"E3"`), le ProjectModel des ints. Conversion simple : `f"N{tag}"`.
- **6 DDL** : PyNite est toujours 3D (6 DDL/nœud). Pour un modèle 2D, on bloque les DDL hors-plan (Dz, Rx, Ry) et on ne garde que Dx, Dy, Rz.
- **Propriétés mécaniques** : PyNite ne connaît pas les classes EC2/EC3. On extrait E, G, A, I depuis le ProjectModel. Si les données manquent, on utilise des valeurs par défaut (acier S355, IPE 300) avec un warning.
- **Extraction des résultats** : PyNite stocke les résultats dans `Nodes[name].DX`, `Members[name].axial()`, etc. On les traduit dans le format `StaticResult` standardisé.

**Méthodes à implémenter :**

```python
class PyNiteBackend(SolverBackend):
    def build_model(self) -> list[str]:         # ~150 lignes
    def run_static(self, load_case) -> StaticResult:  # ~80 lignes
    def run_modal(self, n_modes) -> ModalResult:      # ~40 lignes
    def clear(self) -> None:                    # 2 lignes
    def get_capabilities(self) -> dict:         # 10 lignes
    # Utilitaires privés :
    def _build_loads(self, warnings) -> None:   # ~40 lignes
    def _get_member_properties(self, elem, materials, sections) -> dict  # ~60 lignes
    def _fixities_to_pynite(fixities) -> tuple  # ~15 lignes
    def _node_name(tag) -> str                  # 1 ligne
    def _elem_name(tag) -> str                  # 1 ligne
```

**Test de validation :**

```python
# Poutre bi-encastrée sous charge répartie
# Solution analytique : M_max = qL²/12 (appui), M_mid = qL²/24, V_max = qL/2
# Flèche max = qL⁴/(384EI)
# → Comparer avec les résultats PyNite
```

---

### Étape 3 — Implémenter le backend OpenSees

**Fichier : `core/solvers/opensees_backend.py` (~350 lignes)**

Ce backend réutilise le système de plugins existant. Il ne réinvente rien — il branche juste l'`OpsBuilder` sur le contrat `SolverBackend`.

**Points clés :**

- **Import conditionnel** : `openseespy` n'est jamais importé au niveau module. Chaque méthode fait `import openseespy.opensees as ops` localement. Ça permet d'instancier la classe même sans OpenSees (utile pour les tests).
- **Fonction `is_opensees_available()`** : vérifie `try: import openseespy` une seule fois. Utilisée par le `SolverManager`.
- **Réutilisation de l'OpsBuilder** : `build_model()` appelle `OpsBuilder(model).build()` qui déclenche toute la chaîne de plugins (matériaux, sections, éléments).
- **Extraction des résultats** : `ops.nodeDisp()`, `ops.eleForce()`, `ops.nodeReaction()` — traduits dans le format `StaticResult`.
- **Analyse modale** : `ops.eigen(n_modes)` + `ops.nodeEigenvector()` → `ModalResult`.

**Gestion d'erreur** : si OpenSees n'est pas installé et que l'utilisateur essaie quand même, `build_model()` lève une `ImportError` avec un message clair :

```
OpenSeesPy n'est pas installé.
Pour l'installer : pip install openseespy
Ou utilisez le solveur PyNite (par défaut).
```

---

### Étape 4 — Implémenter le SolverManager

**Fichier : `core/solvers/solver_manager.py` (~320 lignes)**

Le chef d'orchestre. C'est le seul point d'entrée que la GUI utilise.

**Responsabilités :**

1. **Détection au démarrage** : `detect()` scanne les solveurs installés et retourne leurs métadonnées (version, capacités, hint d'installation).
2. **Liste pour la GUI** : `get_engine_display_info()` retourne les données formatées pour un QComboBox (texte, tooltip, enabled/disabled).
3. **Instanciation** : `create_backend(model, engine)` crée le bon backend. Si OpenSees demandé mais absent → fallback PyNite + warning.
4. **Message d'aide** : `get_install_instructions()` retourne le texte d'aide pour l'installation d'OpenSees.

**Cache** : la détection d'OpenSees (qui fait un `import`) est mise en cache dans `_opensees_available` pour ne pas le refaire à chaque appel.

**Implémentation du sélecteur GUI :**

```python
# Dans un dialogue de paramètres ou la toolbar
from core.solvers import SolverManager, SolverEngine

manager = SolverManager()

# Remplir le QComboBox
for info in manager.get_engine_display_info():
    combo.addItem(info["text"], info["engine"])
    # Griser si non disponible
    idx = combo.count() - 1
    if not info["enabled"]:
        model = combo.model()
        item = model.item(idx)
        item.setEnabled(False)
    combo.setItemData(idx, info["tooltip"], Qt.ToolTipRole)
```

---

### Étape 5 — Créer le `__init__.py` du package

**Fichier : `core/solvers/__init__.py` (~25 lignes)**

Expose les types publics :

```python
from core.solvers.base import (
    SolverBackend, SolverEngine,
    StaticResult, ModalResult, SpectralResult,
)
from core.solvers.solver_manager import SolverManager
```

**Pourquoi ne pas exporter les backends ?** L'appelant ne devrait jamais instancier `PyNiteBackend` directement — il passe toujours par le `SolverManager`. Ça permet au manager de gérer le fallback et le logging.

---

### Étape 6 — Intégrer dans le flux d'analyse

**Fichier à modifier : le futur code d'analyse dans `gui/` ou `core/analysis.py`**

Avant l'architecture multi-solveur, le code d'analyse ressemblait à :

```python
# AVANT (couplé à OpenSees)
import openseespy.opensees as ops
builder = OpsBuilder(project)
builder.build()
ops.analyze(1)
disp = ops.nodeDisp(1)
```

Après :

```python
# APRÈS (découplé, multi-solveur)
from core.solvers import SolverManager, SolverEngine

manager = SolverManager()
engine = settings.solver_engine  # Depuis les paramètres du projet

backend = manager.create_backend(project, engine=engine)
warnings = backend.build_model()
# Afficher les warnings dans la console si nécessaire

result = backend.run_static()

if result.success:
    # result.displacements, result.reactions, result.element_forces
    # → exactement le même format quel que soit le solveur
    self.results_view.display(result)
else:
    QMessageBox.warning(self, "Erreur", result.message)
```

**Ce qui change pour le reste de l'application : rien.** Les vues de résultats, les vérifications EC2/EC3, l'export PDF — tout reçoit un `StaticResult` ou `ModalResult` et ne sait pas quel solveur l'a produit.

---

### Étape 7 — Post-traitement spectral EC8 (indépendant du solveur)

**Fichier : `core/spectral_ec8.py` (~200 lignes estimées)**

L'analyse modale spectrale n'est PAS une fonctionnalité du solveur — c'est un post-traitement mathématique. Le flux est :

```
Solveur (PyNite ou OpenSees)
    → run_modal(n_modes)
    → ModalResult (fréquences, déformées modales)
        ↓
spectral_ec8.py
    + spectre EC8 (ag, S, TB, TC, TD, q)
    → Pour chaque mode : Sd(Ti) → accélération spectrale
    → Réponses modales : Ri = Γi × Sd(Ti) × φi
    → Combinaison CQC ou SRSS
        ↓
    SpectralResult (enveloppes)
```

**Fonctions à implémenter :**

```python
def spectre_ec8(T, ag, S, TB, TC, TD, q, beta=0.2) -> float:
    """Spectre de calcul EC8 §3.2.2.5 — Sd(T)."""

def combinaison_cqc(reponses, frequencies, xi=0.05) -> ndarray:
    """Combinaison CQC (Complete Quadratic Combination) EC8 §4.3.3.3.2."""

def combinaison_srss(reponses) -> ndarray:
    """Combinaison SRSS (Square Root of Sum of Squares)."""

def analyse_spectrale(
    modal_result: ModalResult,
    spectre_params: dict,
    combination: str = "CQC",
) -> SpectralResult:
    """Analyse modale spectrale complète."""
```

**Point important :** Ce module ne dépend d'AUCUN solveur. Il prend un `ModalResult` (qui peut venir de PyNite ou d'OpenSees) et retourne un `SpectralResult`. C'est de l'algèbre linéaire pure (numpy/scipy).

---

### Étape 8 — Dialogue de sélection du solveur (GUI)

**Fichier : `gui/dialogs/solver_settings_dlg.py` (~150 lignes estimées)**

Un dialogue simple avec :

- Un QComboBox pour choisir le moteur (PyNite / OpenSees)
- Un tableau des capacités (checkmarks vert/rouge)
- Un bouton "Aide à l'installation" si OpenSees n'est pas détecté
- Un bouton "Vérifier la disponibilité" pour re-détecter

**Maquette :**

```
╔══════════════════════════════════════════════════╗
║  Moteur de calcul                                ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  Solveur : [▼ PyNite (intégré)              ]   ║
║                                                  ║
║  Capacités du solveur sélectionné :              ║
║  ┌──────────────────────┬────────┬─────────┐    ║
║  │ Fonctionnalité       │ PyNite │ OpenSees│    ║
║  ├──────────────────────┼────────┼─────────┤    ║
║  │ Statique linéaire    │   ✓    │    ✓    │    ║
║  │ Analyse modale       │   ✓    │    ✓    │    ║
║  │ Effets P-Δ           │   ✓    │    ✓    │    ║
║  │ Non-linéaire matériau│   ✗    │    ✓    │    ║
║  │ Pushover             │   ✗    │    ✓    │    ║
║  │ Analyse temporelle   │   ✗    │    ✓    │    ║
║  │ Sections fibrées     │   ✗    │    ✓    │    ║
║  └──────────────────────┴────────┴─────────┘    ║
║                                                  ║
║  ⓘ OpenSeesPy non détecté.                      ║
║    Pour l'installer : pip install openseespy     ║
║                                                  ║
║            [Annuler]  [Appliquer]                ║
╚══════════════════════════════════════════════════╝
```

---

### Étape 9 — Mettre à jour les dépendances

**Fichier : `pyproject.toml`**

```toml
[project]
name = "hexa-structures"
version = "0.1.0"
license = {text = "GPL-3.0-only"}
requires-python = ">=3.10"

dependencies = [
    "PySide6>=6.6",
    "PyNiteFEA",          # Solveur par défaut — TOUJOURS installé
    "pyvista",
    "pyvistaqt",
    "numpy",
    "scipy",
]

[project.optional-dependencies]
opensees = ["openseespy>=3.5"]
# Installation : pip install hexa-structures[opensees]

dev = [
    "pytest",
    "pytest-qt",
]
```

**Fichier : `requirements.txt` (si utilisé)**

```
# Dépendances obligatoires
PySide6>=6.6
PyNiteFEA
pyvista
pyvistaqt
numpy
scipy

# Optionnel — décommenter pour activer OpenSees :
# openseespy>=3.5
```

---

### Étape 10 — Écrire les tests

**Fichier : `tests/test_solvers.py`**

**Tests prioritaires :**

```python
# 1. Test unitaire : StaticResult est bien un dataclass valide
def test_static_result_creation():
    r = StaticResult(success=True, message="OK")
    assert r.success
    assert r.displacements == {}

# 2. Test unitaire : SolverManager détecte PyNite
def test_pynite_always_available():
    manager = SolverManager()
    engines = manager.available_engines()
    assert SolverEngine.PYNITE in engines

# 3. Test unitaire : Fallback si OpenSees absent
def test_fallback_to_pynite():
    manager = SolverManager()
    backend = manager.create_backend(mock_model, engine=SolverEngine.OPENSEES)
    # Si OpenSees n'est pas installé → on reçoit un PyNiteBackend
    if not manager.is_available(SolverEngine.OPENSEES):
        assert backend.engine == SolverEngine.PYNITE

# 4. Test d'intégration : Poutre bi-encastrée PyNite
def test_pynite_cantilever():
    """Poutre console sous charge ponctuelle — solution analytique."""
    model = create_test_cantilever()  # Helper
    backend = PyNiteBackend(model)
    backend.build_model()
    result = backend.run_static()
    assert result.success
    # δ_max = PL³/(3EI) — vérifier à 1% près
    expected_disp = ...
    assert abs(result.displacements[2][1] - expected_disp) / expected_disp < 0.01

# 5. Test d'intégration : Mêmes résultats PyNite vs OpenSees
def test_cross_validation():
    """Vérifie que les deux solveurs donnent les mêmes résultats
    sur un cas simple (portique statique linéaire)."""
    model = create_test_portal_frame()
    
    pynite = PyNiteBackend(model)
    pynite.build_model()
    r1 = pynite.run_static()
    
    if is_opensees_available():
        opensees = OpenSeesBackend(model)
        opensees.build_model()
        r2 = opensees.run_static()
        
        # Comparer les déplacements (tolérance 2%)
        for tag in r1.displacements:
            for i in range(3):
                if abs(r1.displacements[tag][i]) > 1e-10:
                    ratio = r2.displacements[tag][i] / r1.displacements[tag][i]
                    assert 0.98 < ratio < 1.02
```

---

## 4. Cas Tests de Validation

### 4.1 Poutre sur deux appuis — Charge répartie

```
    q = 10 kN/m
    ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    ══════════════════
    △                △
    A                B
    |←── L = 6 m ──→|

Solution analytique :
    R_A = R_B = qL/2 = 30 kN
    M_max = qL²/8 = 45 kN·m (à mi-portée)
    V_max = qL/2 = 30 kN (aux appuis)
    δ_max = 5qL⁴/(384EI)
```

### 4.2 Portique simple — Charge latérale

```
    F = 10 kN
    ──→ ●───────────●
        |           |
   3m   |           |
        |           |
        ■           ■  (encastrements)
        |←── 5m ──→|

Solution analytique :
    Les appuis reprennent F en cisaillement et moment
    Vérifier δ_horizontal au sommet
```

### 4.3 Portique 2×2 niveaux (cas de référence du projet)

```
    F2=10kN ●────────●────────●
    ──→     |        |        |
     3m     |        |        |
            |        |        |
    F1=5kN  ●────────●────────●
    ──→     |        |        |
     3m     |        |        |
            |        |        |
            ■        ■        ■
            |← 5m →|← 5m →|

Vérification croisée PyNite vs OpenSees
9 nœuds, 10 éléments
Comparer : déplacements, réactions, M/V/N
```

---

## 5. Ordre de Développement Recommandé

| Ordre | Tâche | Fichier(s) | Dépend de | Durée estimée |
|---|---|---|---|---|
| **1** | Types de résultats + ABC | `core/solvers/base.py` | Rien | 1h |
| **2** | `__init__.py` du package | `core/solvers/__init__.py` | Étape 1 | 10 min |
| **3** | Backend PyNite | `core/solvers/pynite_backend.py` | Étapes 1-2 | 3-4h |
| **4** | SolverManager | `core/solvers/solver_manager.py` | Étapes 1-3 | 1-2h |
| **5** | Tests PyNite | `tests/test_solvers.py` | Étapes 1-4 | 2h |
| **6** | Backend OpenSees | `core/solvers/opensees_backend.py` | Étapes 1-2 + plugins existants | 2h |
| **7** | Tests croisés | Compléter `tests/test_solvers.py` | Étapes 5-6 | 1h |
| **8** | Dialogue GUI solveur | `gui/dialogs/solver_settings_dlg.py` | Étape 4 | 2h |
| **9** | Intégration main_window | `gui/main_window.py` modifié | Étapes 4+8 | 1h |
| **10** | Dépendances | `pyproject.toml` | — | 15 min |
| **11** | Module spectral EC8 | `core/spectral_ec8.py` | Étape 1 (ModalResult) | 3h |

**Durée totale estimée : ~2 jours de développement**

---

## 6. Détail du Code — Points Critiques

### 6.1 Import conditionnel d'OpenSeesPy

```python
# ✗ JAMAIS ça (crash si openseespy absent)
import openseespy.opensees as ops

# ✓ TOUJOURS ça (dans une méthode, pas au niveau module)
def run_static(self):
    import openseespy.opensees as ops
    ops.analyze(1)

# ✓ Pour la détection
def is_opensees_available() -> bool:
    try:
        import openseespy.opensees
        return True
    except ImportError:
        return False
```

### 6.2 Conversion fixités 2D → 3D (pour PyNite)

PyNite est toujours en 3D (6 DDL/nœud). Notre ProjectModel est en 2D (3 DDL). Il faut convertir :

```python
# ProjectModel 2D : (Dx, Dy, Rz) — 1=bloqué, 0=libre
fixities_2d = (1, 1, 1)  # encastrement 2D

# PyNite 3D : (Dx, Dy, Dz, Rx, Ry, Rz) — True=bloqué
# On bloque les DDL hors-plan (Dz, Rx, Ry) pour modéliser du 2D
support_3d = (True, True, True, True, True, True)
#              Dx    Dy    Dz    Rx    Ry    Rz
#              ↑     ↑     ↑     ↑     ↑     ↑
#             2D    2D   PLAN  PLAN  PLAN   2D
```

### 6.3 Tags vs Noms

```python
# ProjectModel utilise des tags (int)
node.tag = 1
elem.tag = 3

# PyNite utilise des noms (str)
fem.add_node("N1", ...)
fem.add_member("E3", ...)

# Conversion simple et réversible
def _node_name(tag: int) -> str: return f"N{tag}"
def _elem_name(tag: int) -> str: return f"E{tag}"
```

### 6.4 Propriétés mécaniques : d'où elles viennent

PyNite a besoin de E, G, A, Iy, Iz, J pour chaque membre. Le ProjectModel stocke des références vers matériaux et sections. La traduction :

```
ProjectModel                    PyNite
────────────                    ──────
elem.material_tag = 1           E = 210 000 000 kPa (acier)
  → materials[1].type = "steel" G = 80 769 000 kPa
  → materials[1].params.nuance  
                                
elem.section_tag = 1            A = 53.8e-4 m²
  → sections[1].params.b = 0.3  Iy = 8356e-8 m⁴
  → sections[1].params.h = 0.5  Iz = 604e-8 m⁴
                                J = 20.1e-8 m⁴
```

Si les données manquent, on utilise des **valeurs par défaut raisonnables** (acier S355, IPE 300) avec un warning dans le rapport de construction. L'utilisateur voit le warning dans la console et peut corriger.

### 6.5 Analyse modale : masses nodales

Pour l'analyse modale, il faut des masses. Deux approches :

**OpenSees** : `ops.mass(nodeTag, mx, my, mz)` — explicite
**PyNite** : Les masses viennent du poids propre des membres. PyNite les assemble automatiquement si on fournit le `self_wt` (poids propre par mètre linéaire).

Le calcul de la masse linéique est le même dans les deux cas :

```python
# ρ (kg/m³) × A (m²) = masse linéique (kg/m)
# Pour OpenSees : on divise par 2 et on assigne aux nœuds extrêmes
# Pour PyNite : on passe le self_wt directement
```

---

## 7. Licence et Redistribution

### 7.1 Ce qu'on redistribue

| Composant | Licence | Redistribué ? | Dans le package ? |
|---|---|---|---|
| HEXA Structures (notre code) | GPL v3 + exception §7 | Oui | Oui |
| PyNite (PyNiteFEA) | MIT | Oui (via pip dependency) | Oui (installé auto) |
| PySide6 | LGPL | Oui (via pip dependency) | Oui |
| OpenSeesPy | UC Berkeley custom | **NON** | Non (l'utilisateur installe) |

### 7.2 Le message à l'utilisateur

Dans la documentation et le dialogue d'installation :

> HEXA Structures utilise PyNite comme solveur par defaut.
> Pour les analyses avancées (non-linéaire, sismique, pushover),
> vous pouvez installer OpenSeesPy : `pip install openseespy`
>
> Note : OpenSeesPy est distribué sous licence UC Berkeley.
> Son installation et son utilisation relèvent de votre responsabilité.
> HEXA Structures ne redistribue pas OpenSeesPy.

---

## 8. Évolutions Futures

### 8.1 Ajouter un troisième solveur

Pour ajouter un solveur (ex: Code_Aster via Salome-Meca) :

1. Créer `core/solvers/codeaster_backend.py`
2. Implémenter `SolverBackend` (build_model, run_static, run_modal)
3. Ajouter `CODEASTER = auto()` dans `SolverEngine`
4. Ajouter la détection dans `SolverManager.detect()`
5. Aucune modification du reste de l'application

### 8.2 Solveur Rust/PyO3

Si on décide d'écrire un solveur en Rust pour les performances :

1. Créer un crate Rust avec PyO3 + maturin
2. Le packager comme une wheel Python (ex: `opensees_fr_solver`)
3. Créer `core/solvers/rust_backend.py`
4. L'ajouter comme dépendance optionnelle dans pyproject.toml

L'architecture est prête pour ça sans aucune modification structurelle.

### 8.3 Calcul en processus séparé

Quand on passera au `multiprocessing` pour isoler le solveur :

```python
# Le SolverManager pourra gérer ça de manière transparente
def create_backend(self, model, engine, isolated=False):
    if isolated:
        return IsolatedBackend(backend)  # Wrapper multiprocessing
    return backend
```

Le format de résultats (`StaticResult`, `ModalResult`) étant des dataclasses sérialisables, ils passent naturellement entre processus via `pickle` ou une `Queue`.

---

## 9. Checklist de Validation

Avant de considérer l'implémentation multi-solveur comme terminée, vérifier :

- [ ] `pip install .` installe PyNite automatiquement
- [ ] L'application démarre sans OpenSeesPy installé (aucune erreur d'import)
- [ ] Le ComboBox de sélection affiche les deux solveurs avec le bon état
- [ ] OpenSees est grisé si non installé, avec un tooltip explicatif
- [ ] L'analyse statique PyNite donne des résultats corrects sur les 3 cas tests
- [ ] L'analyse modale PyNite extrait les fréquences correctement
- [ ] Le fallback PyNite ← OpenSees fonctionne si OpenSees absent
- [ ] Le backend OpenSees réutilise bien les plugins existants
- [ ] Les résultats statiques PyNite et OpenSees concordent à <2% sur le cas portique
- [ ] Le post-traitement (déformée, M/V/N, vérifications) fonctionne identiquement avec les deux solveurs
- [ ] Le `SpectralResult` se calcule correctement à partir d'un `ModalResult`
- [ ] Les tests passent dans la CI (avec et sans OpenSees)
- [ ] La documentation mentionne comment installer OpenSees en option

---

*Document genere le 22 mars 2026 - HEXA Structures v0.1*
