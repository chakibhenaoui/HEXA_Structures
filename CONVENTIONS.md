# HEXA Structures - Conventions et Decisions Techniques

> Document de référence pour le développement. Toute contribution doit respecter ces conventions.

---

## 1. Langue

| Contexte | Langue | Exemple |
|---|---|---|
| Noms de variables, fonctions, classes | **Anglais** | `node`, `ElementData`, `run_static()` |
| Commentaires dans le code | **Français** | `# Calcul du moment fléchissant` |
| Docstrings | **Français** | `"""Vérification béton armé EC2."""` |
| Interface utilisateur (GUI) | **Français** | Menus, labels, messages |
| Documentation projet (README, etc.) | **Français** | Destiné aux ingénieurs FR |
| Noms de fichiers / modules | **Anglais** | `materials.py`, `solver_manager.py` |

---

## 2. Style Python

### 2.1 Règles générales
- **PEP 8** strict (vérifiable avec `ruff` ou `flake8`)
- **Type hints** obligatoires sur toutes les fonctions publiques
- **Docstrings** au format Google style, en français
- Longueur de ligne max : **100 caractères**
- Python recommandé : **3.12** pour le développement courant
- Python minimum visé : **3.10** tant que le code reste compatible

### 2.2 Nommage

| Élément | Convention | Exemple |
|---|---|---|
| Classes | `PascalCase` | `NodeData`, `OpsBuilder`, `MainWindow` |
| Fonctions / méthodes | `snake_case` | `run_static()`, `get_element_forces()` |
| Variables | `snake_case` | `node_tag`, `load_case` |
| Constantes | `UPPER_SNAKE` | `CONCRETE_GRADES`, `MAX_ITERATIONS` |
| Modules / fichiers | `snake_case` | `model_data.py`, `ec2_checks.py` |
| Signaux PySide6 | `snake_case` | `analysis_finished`, `node_selected` |
| Widgets PySide6 | préfixe descriptif | `self.tree_model`, `self.btn_analyze` |

### 2.3 Imports (ordre)
```python
# 1. Bibliothèque standard
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 2. Bibliothèques tierces
import numpy as np
from PySide6.QtWidgets import QMainWindow

# 3. Modules du projet
from core.model_data import ProjectModel
from core.application.services import ApplicationServices
```

### 2.4 Exemple de docstring
```python
def compute_moment_resistance(b: float, d: float, fcd: float, fyd: float, 
                               a_s: float) -> float:
    """Calcule le moment résistant d'une section rectangulaire en flexion simple.

    Méthode du diagramme rectangulaire simplifié (EC2 §3.1.7).

    Args:
        b: Largeur de la section (m).
        d: Hauteur utile (m).
        fcd: Résistance de calcul du béton en compression (kPa).
        fyd: Limite élastique de calcul de l'acier (kPa).
        a_s: Section d'armatures tendues (m²).

    Returns:
        Moment résistant M_Rd (kN·m).
    """
```

---

## 3. Système d'unités interne

**Système réténu : kN, m, kPa (génie civil courant)**

| Grandeur | Unité interne | Symbole |
|---|---|---|
| Longueur | mètre | m |
| Force | kilonewton | kN |
| Contrainte / pression | kilopascal | kPa |
| Moment | kilonewton·mètre | kN·m |
| Section | mètre carré | m² |
| Inertie | mètre puissance 4 | m⁴ |
| Masse linéique | kg/m | kg/m |
| Masse volumique | kg/m³ | kg/m³ |
| Accélération | m/s² | m/s² |

### Règles de conversion
- Les données d'entrée utilisateur peuvent être dans d'autres unités (mm, MPa, cm²)
- La conversion se fait **à l'entrée** (GUI → unités internes) et **à la sortie** (unités internes → affichage)
- Le module `utils/units.py` centralise toutes les conversions
- Les profilés du catalogue (en mm, cm², cm⁴) sont convertis à l'import

### Convention pour OpenSees
OpenSees n'a pas de système d'unités intégré. On lui envoie directement les valeurs dans notre système interne (kN, m, kPa). Toutes les commandes `ops.node()`, `ops.uniaxialMaterial()`, `ops.load()` reçoivent des valeurs en kN/m/kPa.

---

## 4. Décisions techniques

### 4.1 Framework GUI : PySide6
- **Raison** : licence LGPL (compatible MIT), API identique à PyQt6
- Version minimale : PySide6 >= 6.6

### 4.2 Vue graphique : PyVista (surcouche VTK)
- **Raison** : API pythonique, 5× moins de code que VTK pur, même puissance
- Intégration PySide6 via `pyvistaqt.QtInteractor`
- Bibliothèques : `pyvista` + `pyvistaqt` (installe `vtk` automatiquement)
- Accès VTK natif toujours possible si besoin via `.renderer`, `.mapper`

### 4.3 Format de sauvegarde : SQLite (.db)
- **Raison** : format unique, requêtes performantes, pas de parsing JSON volumineux
- Un fichier `.db` par projet
- Tables principales : `nodes`, `éléments`, `materials`, `sections`, `load_cases`, `combinations`, `results`
- Sérialisation/désérialisation dans `core/model_data.py`
- Possibilité d'export JSON pour interopérabilité

### 4.4 Licence : LGPL-3.0-only
- **Raison** : copyleft faible, modifications du projet partagees sans fermer l'interoperabilite avec les dependances BSD/LGPL
- Compatible avec OpenSeesPy (BSD), PySide6 (LGPL), VTK (BSD)

### 4.5 Architecture : ports / adaptateurs / plugins
- La GUI ne parle **jamais** directement à PyNite, OpenSeesPy, SQLite ou Matplotlib.
- Les nouveaux flux applicatifs passent par `core/application`.
- Les dépendances techniques sont placées derrière des ports dans `core/application/ports`.
- Les implémentations techniques vivent dans `core/adapters`.
- Les backends historiques restent dans `core/solvers` tant que leur migration progressive n'est pas terminée.
- Le modèle de données (`model_data.py`) doit rester indépendant des solveurs.
- Les plugins installables sont découverts par manifestes dans `core/plugins`.
- La découverte de manifestes ne doit pas importer ni exécuter de code externe.
- Le chargement de code externe passe uniquement par un loader explicite, par exemple `ImportlibPluginLoader`.

### 4.6 Points d'extension plugins
- Un plugin déclare un `kind` libre : `solver`, `design_module`, `exporter`, `reporting`, etc.
- Un plugin déclare ses points d'extension dans `extension_points`.
- Les capacités fonctionnelles vont dans `capabilities`.
- Les mots-clés d'aide au filtrage vont dans `tags`.
- Le point `connections.design` est réservé aux modules de calcul d'assemblages.
- Un plugin métier ne doit pas dépendre de la GUI HEXA.

### 4.7 Analyses longues : QThread
- Toute analyse OpenSees s'exécute dans un `QThread` dédié
- Communication avec la GUI via signaux `progress` et `finished`
- La GUI reste réactive pendant le calcul

---

## 5. Conventions PySide6

### 5.1 Structure d'un widget
```python
class MyWidget(QWidget):
    """Description du widget en français."""

    # Signaux en premier
    item_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Construit l'interface du widget."""
        ...

    def _connect_signals(self):
        """Connecte les signaux aux slots."""
        ...
```

### 5.2 Nommage des widgets
| Type | Préfixe | Exemple |
|---|---|---|
| QPushButton | `btn_` | `self.btn_analyze` |
| QLineEdit | `edit_` | `self.edit_node_x` |
| QComboBox | `combo_` | `self.combo_material` |
| QLabel | `lbl_` | `self.lbl_status` |
| QTreeView | `tree_` | `self.tree_model` |
| QTableView | `table_` | `self.table_results` |
| QAction | `act_` | `self.act_save` |
| QDockWidget | `dock_` | `self.dock_properties` |

---

## 6. Conventions OpenSees

### 6.1 Tags
- Tags de nœuds : à partir de **1**, incrémentaux
- Tags d'éléments : à partir de **1**, incrémentaux
- Tags de matériaux : à partir de **1**
- Tags de sections : à partir de **1**
- Tags de timeSeries / patterns : gérés automatiquement par `ops_builder.py`

### 6.2 Repère global et gravité
- **Convention : Z vertical, gravité = -Z**
- Plan horizontal : XY (plan de plancher)
- Axe vertical : Z (hauteur)
- Compatible avec les conventions usuelles de calcul de structures

### 6.3 Degrés de liberté (3D natif)
- NDM = 3, NDF = 6
- DOF 1 = Ux (translation X, horizontal)
- DOF 2 = Uy (translation Y, horizontal)
- DOF 3 = Uz (translation Z, vertical)
- DOF 4 = Rx (rotation autour de X)
- DOF 5 = Ry (rotation autour de Y)
- DOF 6 = Rz (rotation autour de Z)

### 6.4 Convention de signe
- Efforts positifs : traction (N), cisaillement montant (V), moment horaire (M)
- Cohérent avec la convention OpenSees `eleForce()`

### 6.5 Orientation locale des barres 3D
- Axe local `x` : du nœud i vers le nœud j
- Axe local `z` : projection du vecteur de référence dans le plan normal à `x`
- Axe local `y` : `z × x`
- Le repère local est orthonormé et direct (`x × y = z`)
- La rotation de section positive suit la règle de la main droite autour de `x`
- Par défaut, la référence est le Z global `(0, 0, 1)`
- Pour les barres quasi verticales, la référence bascule automatiquement sur X global,
  puis sur Y global si nécessaire
- OpenSees reçoit `vecxz = z_local` pour `geomTransf`

### 6.6 Plaques utilisateur et maillage de calcul
- Les plaques sont modélisées par l’utilisateur comme des objets surfaciques à 4 nœuds.
- Avant calcul, HEXA génère automatiquement un maillage quadrangulaire interne.
- Les nœuds et éléments générés sont des objets de calcul et ne font pas partie
  du modèle utilisateur visible.
- Les appuis de bord et charges surfaciques appliqués à la plaque macro sont
  propagés automatiquement au maillage de calcul.
- `SurfaceElementData` reste l’élément fini surfacique transmis au solveur.
- Les plaques macro utilisent un mode de maillage `auto` par defaut. Le nombre
  de divisions transmis au solveur est calcule a partir des dimensions de la
  plaque, de l'epaisseur et de la formulation.
- Le mode `user` conserve explicitement les divisions `mesh_nx × mesh_ny`
  saisies par l'utilisateur.
- Le maillage automatique utilise une taille maximale d'element reguliere :
  au moins 8 divisions sur la petite portee pour les plaques minces courantes,
  et un raffinement plus strict pour `ShellMITC4` lorsque la plaque est mince.
- Les valeurs de maillage stockees dans la plaque macro restent des reglages
  utilisateur; le maillage effectif du modele de calcul est porte par
  `GeneratedPlateMesh`.
- Les cartes de résultats plaque utilisent le modèle de calcul enrichi et regroupent
  les résultats des surfaces générées sous la plaque macro d'origine.
- Ces vues de contours ne rendent pas les nœuds ou surfaces générés permanents
  dans le modèle utilisateur.

### 6.7 Plugins d'assemblages
- Le contrat applicatif de base est `ConnectionDesignPort`.
- L'entrée applicative est `RunConnectionDesign`.
- La façade publique expose `ApplicationServices.design_connection(...)`.
- Les plugins d'assemblages doivent déclarer `connections.design`.
- Une réponse plugin doit être normalisable en `ConnectionDesignResult`.

---

## 7. Gestion de version

- **Git** avec des commits en français
- Format de commit : `type: description courte`
  - `feat:` nouvelle fonctionnalité
  - `fix:` correction de bug
  - `refactor:` refactorisation sans changement fonctionnel
  - `docs:` documentation
  - `test:` ajout/modification de tests
- Branche principale : `main`
- Branches de feature : `feature/nom-court`

---

*Dernière mise à jour : 19 juin 2026*
