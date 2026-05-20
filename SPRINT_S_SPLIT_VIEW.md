# HEXA Structures - Modèleur Structurel 2D/3D (Split View)

> **Sprint S? — Document d'implémentation**
> Objectif : passer d'un visualiseur 3D à un modèleur structurel interactif
> Durée estimée : 3 semaines

---

## 1. Vision

L'ingénieur BTP français pense en plans et en élévations. Il dessine ses portiques en coupe, place ses poteaux en plan, vérifie ses hauteurs d'étage en élévation. Le 3D est un outil de contrôle visuel, pas de saisie.

HEXA Structures adopte un flux métier classique : **dessin précis en 2D + prévisualisation 3D synchronisée**. L'utilisateur ne dessine jamais dans la vue 3D ; il orbite, zoome et pivote pour vérifier que son modèle est cohérent.

### 1.1 Pourquoi pas de dessin 3D interactif ?

Le raycasting sur un plan arbitraire dans l'espace 3D pose des problèmes de précision majeurs. Pour placer un nœud à (5.000, 3.000, 6.000) m en cliquant dans une vue 3D, il faut déterminer sur quel plan de travail l'utilisateur veut se positionner, résoudre l'intersection rayon-plan, et gérer l'accrochage — tout ça avec une caméra perspective qui déforme les distances. Stabileo (Svelte + Three.js + Rust WASM) l'a fait, mais c'est un développement très lourd.

En 2D, un clic à la position écran (px, py) se traduit directement en coordonnées monde (x, y) via la matrice de transformation inverse du QGraphicsView. La précision est parfaite, l'accrochage est trivial, et l'ingénieur retrouve son environnement habituel.

---

## 2. Interface Utilisateur

### 2.1 Layout Principal

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Menu  │  Toolbar (Fichier, Analyse...)  │  Toolbar Dessin 2D          │
├────────┴───────────┬────────────────────────────────────────────────────┤
│                    │                                                    │
│   Arbre du modèle  │  ┌─────────────────────────────┬────────────────┐ │
│   (QTreeView)      │  │                             │                │ │
│                    │  │   CANVAS 2D                 │   VUE 3D       │ │
│   ▸ Niveaux       │  │   (QGraphicsView)           │   (PyVista)    │ │
│     ▸ RDC         │  │                             │                │ │
│     ▸ R+1         │  │   Dessin interactif         │   Prévisua-    │ │
│     ▸ Toiture     │  │   Grille magnétique         │   lisation     │ │
│   ▸ Matériaux     │  │   Modes souris              │   synchronisée │ │
│   ▸ Sections      │  │                             │                │ │
│   ▸ Charges       │  │   ~70-80%                   │   ~20-30%      │ │
│                    │  │                             │                │ │
│                    │  └─────────────────────────────┴────────────────┘ │
├────────────────────┴────────────────────────────────────────────────────┤
│  Console Python │ Tableaux │ Résultats                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Technologie : QWidgets (pas QML)

Tout le code existant du projet (console, vue 3D PyVista, model_data) est en QWidgets. Mixer QML et QWidgets dans la même application PySide6 créerait une complexité d'intégration inutile : encapsulation via `QQuickWidget`, signaux qui ne se connectént pas naturellement entre les deux mondes, debugging plus difficile.

L'équivalent QWidgets du `SplitView` QML est un `QSplitter` qui fait exactement la même chose :

```python
# Deux zones redimensionnables avec une poignée de séparation
splitter = QSplitter(Qt.Horizontal)
splitter.addWidget(self.canvas_2d)      # QGraphicsView — 70-80%
splitter.addWidget(self.view_3d)        # PyVista QtInteractor — 20-30%
splitter.setSizes([800, 300])
splitter.setCollapsible(1, True)        # La 3D peut être réduite à 0
```

### 2.3 Toolbar de dessin 2D

```
┌────────────────────────────────────────────────────────────────────┐
│ [↖ Sélect.] [● Nœud] [/ Barre] [▣ Appui] │ Vue: [Plan▾] │       │
│                                             │ Niveau: [R+1▾]│      │
│ Grille: [0.50 m▾] [✓ Snap] [✓ Ortho]      │ [XY] [XZ] [YZ]│      │
└────────────────────────────────────────────────────────────────────┘
```

**Modes souris** (un seul actif à la fois, via QActionGroup) :

| Mode | Icône | Raccourci | Comportement souris |
|---|---|---|---|
| Sélection | ↖ | S | Clic = sélectionner, drag = boîte de sélection |
| Nœud | ● | N | Clic = placer un nœud (snappé à la grille) |
| Barre | / | B | Clic nœud 1, clic nœud 2 = créer une barre |
| Appui | ▣ | A | Clic sur nœud = assigner un type d'appui |

### 2.4 Les 3 vues 2D standards

| Vue | Axes affichés | Plan de coupe | Usage principal |
|---|---|---|---|
| **Plan (XY)** | X horizontal, Y profondeur | Z = élévation du niveau actif | Placer poteaux, murs, disposition en plan |
| **Élévation (XZ)** | X horizontal, Z vertical | Y = 0 (face principale) | Dessiner portiques, vérifier hauteurs |
| **Coupe (YZ)** | Y horizontal, Z vertical | X = 0 (coupe transversale) | Portiques perpendiculaires |

La vue 2D filtre les entités visibles selon le plan actif. En vue Plan au niveau R+1 (Z=3.0m), on ne voit que les nœuds dont `z == 3.0` et les barres horizontales de ce niveau. Les poteaux apparaissent comme des points (leur projection sur le plan Z=3.0). En élévation XZ, on voit les poteaux et poutres dans le plan Y=0.

---

## 3. Modèle de Données

### 3.1 Principe : étendre le ProjectModel existant, pas le remplacer

Le `ProjectModel` dans `core/model_data.py` est déjà la source de vérité unique avec ses dataclasses (`NodeData`, `ElementData`), son `UndoStack`, sa persistance SQLite, et ses signaux Qt. PyVista n'est qu'une vue sur ces données. Le canvas 2D sera une deuxième vue sur les mêmes données.

Il ne faut pas créer un modèle `ModèleStructurel` séparé qui dupliquerait les nœuds et les barres. On ajoute le concept de **niveau** au ProjectModel existant.

### 3.2 Nouvelles dataclasses

```python
# Dans core/model_data.py — EXTENSION (pas remplacement)

@dataclass
class LevelData:
    """
    Niveau / étage du bâtiment.
    
    Un niveau est un plan horizontal à une altitude Z donnée.
    Les nœuds 'appartiennent' à un niveau si leur coordonnée z
    correspond à l'élévation du niveau (à une tolérance près).
    
    Pourquoi ne pas stocker les nœuds DANS le niveau ?
        → Un nœud peut être entre deux niveaux (poteau incliné,
          rampe, escalier). La relation nœud↔niveau est déduite
          de la coordonnée z, pas stockée en dur.
    """
    tag: int
    name: str              # "RDC", "R+1", "R+2", "Toiture"
    elevation: float       # Altitude Z en mètres
    height: float = 3.0    # Hauteur sous plafond (m) — pour le dessin

@dataclass
class GridData:
    """
    Grille de référence (files de poteaux).
    
    Les files sont les axes de la trame structurelle :
    files X (A, B, C...) et files Y (1, 2, 3...).
    Elles apparaissent dans la vue 2D comme des lignes de référence
    et servent de points d'accrochage.
    """
    x_files: list[tuple[str, float]]   # [("A", 0.0), ("B", 5.0), ("C", 10.0)]
    y_files: list[tuple[str, float]]   # [("1", 0.0), ("2", 4.0), ("3", 8.0)]
    
# Ajouts au ProjectModel :
class ProjectModel:
    # ... champs existants (nodes, éléments, materials, sections, loads) ...
    levels: dict[int, LevelData] = field(default_factory=dict)
    grid: GridData | None = None
    active_level_tag: int | None = None   # Niveau actuellement affiché en 2D
```

### 3.3 Relation nœud ↔ niveau

```python
# Méthode utilitaire dans ProjectModel
def nodes_at_level(self, level_tag: int, tolerance: float = 0.01) -> list[NodeData]:
    """Retourne les nœuds dont z correspond à l'élévation du niveau."""
    level = self.levels.get(level_tag)
    if level is None:
        return []
    return [
        n for n in self.nodes.values()
        if abs(n.z - level.elevation) < tolerance
    ]

def éléments_at_level(self, level_tag: int, tolerance: float = 0.01) -> list[ElementData]:
    """
    Retourne les éléments visibles à ce niveau.
    
    Un élément est visible si :
    - Ses deux nœuds sont au même niveau (poutre horizontale)
    - Un nœud est à ce niveau et l'autre au-dessus/dessous (poteau)
    """
    level = self.levels.get(level_tag)
    if level is None:
        return []
    elev = level.elevation
    result = []
    for elem in self.éléments.values():
        ni = self.nodes.get(elem.node_i)
        nj = self.nodes.get(elem.node_j)
        if ni is None or nj is None:
            continue
        ni_at = abs(ni.z - elev) < tolerance
        nj_at = abs(nj.z - elev) < tolerance
        if ni_at or nj_at:
            result.append(elem)
    return result
```

### 3.4 Flux de données (Single Source of Truth)

```
           ┌──────────────────────────────────────────┐
           │          ProjectModel (Python)            │
           │  nodes, éléments, levels, grid            │
           │  UndoStack, SQLite, Signaux Qt            │
           └────────┬──────────────┬──────────────────┘
                    │              │
          Signal: model_changed   Signal: model_changed
                    │              │
           ┌────────▼─────┐  ┌────▼──────────────────┐
           │  Canvas 2D   │  │  Vue 3D PyVista        │
           │  (lecture +  │  │  (lecture seule,        │
           │   écriture)  │  │   rafraîchissement     │
           │              │  │   debounced 100ms)      │
           └──────────────┘  └────────────────────────┘
```

Les deux vues lisent les mêmes données du ProjectModel. Seul le canvas 2D écrit (via les modes souris). La vue 3D est en lecture seule — elle observe les changements et se redessine.

---

## 4. Canvas 2D : `StructuralCanvas2D`

### 4.1 Architecture de la classe

```
gui/widgets/
├── structural_canvas.py          ← NOUVEAU — QGraphicsView + QGraphicsScene
├── canvas_items.py               ← NOUVEAU — Items graphiques (nœud, barre, appui)
├── canvas_modes.py               ← NOUVEAU — Machine à états des modes souris
├── model_view_3d.py              ← EXISTANT — Vue 3D PyVista (inchangée)
└── ...
```

### 4.2 QGraphicsView : le conteneur

```python
# gui/widgets/structural_canvas.py

class StructuralCanvas2D(QGraphicsView):
    """
    Planche à dessin 2D de l'ingénieur.
    
    Responsabilités :
        1. Afficher la scène 2D avec zoom/pan (molette + clic milieu)
        2. Déléguer les clics au mode actif (sélection, nœud, barre, appui)
        3. Dessiner la grille de fond et les lignes de référence
        4. Gérer l'axe Y inversé (Qt Y↓, structures Y↑)
    
    Ce widget ne connaît PAS le ProjectModel directement.
    Il travaille avec la QGraphicsScene qui contient les items.
    Les modifications passent par des signaux.
    """
```

**Axe Y inversé** : c'est un point technique critique. Qt a l'axe Y vers le bas (convention écran). En structures, on veut Y/Z vers le haut. Solution :

```python
def __init__(self):
    super().__init__()
    # Inverser l'axe Y pour que le haut = valeurs positives
    self.scale(1, -1)
    # Conséquence : tous les textes (labels) seront à l'envers.
    # Il faudra les ré-inverser individuellement :
    # text_item.setTransform(QTransform.fromScale(1, -1))
```

**Zoom/Pan** : molette pour zoomer, clic milieu + drag pour se déplacer.

```python
def wheelEvent(self, event):
    """Zoom centré sur la position de la souris."""
    factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
    self.scale(factor, factor)

def mousePressEvent(self, event):
    if event.button() == Qt.MiddleButton:
        self._pan_start = event.pos()
        self.setCursor(Qt.ClosedHandCursor)
        return
    # Sinon, déléguer au mode actif
    self._current_mode.on_press(event)

def mouseMoveEvent(self, event):
    if self._pan_start is not None:
        delta = event.pos() - self._pan_start
        self._pan_start = event.pos()
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - delta.x()
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - delta.y()
        )
        return
    self._current_mode.on_move(event)
```

### 4.3 Grille magnétique

La grille est dessinée en arrière-plan de la scène et fournit la fonction de snap.

```python
class GridOverlay:
    """
    Grille de fond avec accrochage magnétique.
    
    Deux niveaux de grille :
        - Grille principale (ex: 1.0 m) → lignes plus épaisses
        - Grille secondaire (ex: 0.25 m) → lignes fines
    
    Le snap arrondit la position du curseur à la grille secondaire.
    L'utilisateur peut changer la résolution via la toolbar.
    """
    
    def __init__(self, major: float = 1.0, minor: float = 0.25):
        self.major_spacing = major   # Espacement grille principale (m)
        self.minor_spacing = minor   # Espacement grille secondaire (m)
        self.snap_enabled = True
        self.ortho_enabled = False   # Contrainte orthogonale (H/V)
    
    def snap(self, pos: QPointF) -> QPointF:
        """Accroche une position scène à la grille la plus proche."""
        if not self.snap_enabled:
            return pos
        gs = self.minor_spacing
        x = round(pos.x() / gs) * gs
        y = round(pos.y() / gs) * gs
        return QPointF(x, y)
    
    def snap_ortho(self, pos: QPointF, origin: QPointF) -> QPointF:
        """
        Contrainte orthogonale : force le tracé horizontal ou vertical.
        
        Compare l'angle entre origin et pos. Si plus proche de
        l'horizontale → force Y = origin.Y. Si plus proche de
        la verticale → force X = origin.X.
        """
        if not self.ortho_enabled:
            return self.snap(pos)
        dx = abs(pos.x() - origin.x())
        dy = abs(pos.y() - origin.y())
        snapped = self.snap(pos)
        if dx >= dy:
            return QPointF(snapped.x(), origin.y())  # Horizontal
        else:
            return QPointF(origin.x(), snapped.y())  # Vertical
```

### 4.4 Machine à états des modes souris

Chaque mode est une classe avec les mêmes méthodes (`on_press`, `on_move`, `on_release`). Le canvas délègue les événements au mode actif. Pattern State Machine.

```python
# gui/widgets/canvas_modes.py

class CanvasMode(ABC):
    """Interface commune pour tous les modes d'interaction."""
    
    def __init__(self, canvas: StructuralCanvas2D):
        self.canvas = canvas
    
    @abstractmethod
    def on_press(self, event: QMouseEvent) -> None: ...
    @abstractmethod
    def on_move(self, event: QMouseEvent) -> None: ...
    @abstractmethod
    def on_release(self, event: QMouseEvent) -> None: ...
    def on_key(self, event: QKeyEvent) -> None: pass
    def activate(self) -> None: pass    # Appelé quand on entre dans ce mode
    def deactivate(self) -> None: pass  # Appelé quand on quitte ce mode


class SelectionMode(CanvasMode):
    """
    Mode sélection (mode par défaut).
    
    - Clic sur un item → sélectionner (avec Shift = ajouter à la sélection)
    - Clic dans le vide → désélectionner tout
    - Drag → boîte de sélection rectangulaire
    - Delété → supprimer les items sélectionnés (via ProjectModel.remove_*)
    """


class NodeMode(CanvasMode):
    """
    Mode placement de nœuds.
    
    - Déplacement souris → croix de visée + position snappée affichée
    - Clic gauche → ProjectModel.add_node(tag, x, y, z)
      où z = élévation du niveau actif
    - Le tag est auto-incrémenté
    - Un feedback visuel (cercle vert temporaire) confirme le placement
    """


class BarMode(CanvasMode):
    """
    Mode dessin de barres (deux clics).
    
    Phase 1 : clic sur un nœud existant → mémorise nœud_i
              Affiche une ligne élastique entre nœud_i et le curseur
    Phase 2 : clic sur un nœud existant → mémorise nœud_j
              ProjectModel.add_element(tag, node_i, node_j, section, material)
              Revient en phase 1 pour enchaîner les barres
    
    Accrochage : la barre ne peut partir que d'un nœud existant.
    Si le clic est dans le vide → rien ne se passe (ou on crée un nœud auto).
    
    Touche Échap → annule la barre en cours et revient en phase 1.
    """


class SupportMode(CanvasMode):
    """
    Mode assignation d'appuis.
    
    - Clic sur un nœud → ouvre un mini-menu contextuel :
      [Encastrement] [Appui simple] [Rotule] [Personnalisé...]
    - Sélectionne le type → ProjectModel.update_node(tag, fixities=...)
    - Le symbole d'appui apparaît immédiatement sur le nœud
    """
```

### 4.5 Items graphiques (QGraphicsItem)

Chaque entité structurelle a sa représentation graphique dans la scène.

```python
# gui/widgets/canvas_items.py

class NodeItem(QGraphicsEllipseItem):
    """
    Représentation graphique d'un nœud dans la scène 2D.
    
    - Cercle de rayon fixe en pixels (pas en mètres) → taille constante quel que soit le zoom
    - Couleur : bleu par défaut, rouge si appui, vert si sélectionné
    - Label : numéro du tag affiché à côté
    - Double-clic : ouvre le panneau de propriétés
    
    Pourquoi QGraphicsEllipseItem et pas un item custom ?
        → QGraphicsEllipseItem hérite de QGraphicsItem et fournit
          le dessin d'ellipse, la bounding box, et la détection
          de collision gratuitement. Moins de code à écrire.
    """
    
    RADIUS = 5  # pixels (constant, indépendant du zoom)
    
    def __init__(self, node_data, parent=None):
        super().__init__(-self.RADIUS, -self.RADIUS, 
                         self.RADIUS*2, self.RADIUS*2, parent)
        self.node_tag = node_data.tag
        self.setPos(node_data.x, node_data.y)  # Coordonnées scène = mètres
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        # ↑ CRITIQUE : la taille du cercle reste constante en pixels
        #   même quand on zoome. Sans ce flag, les nœuds deviendraient
        #   énormes en zoomant et invisibles en dézoomant.


class BarItem(QGraphicsLineItem):
    """
    Représentation graphique d'une barre (poutre/poteau) en 2D.
    
    - Ligne entre les positions des deux nœuds
    - Couleur : gris = poutre, vert = poteau (distinction par orientation)
    - Épaisseur : proportionnelle à la hauteur de section (option)
    - Sélection : clic sur la ligne ou à proximité (tolérance ~5 pixels)
    - Label : numéro du tag au milieu de la barre
    """


class SupportItem(QGraphicsItemGroup):
    """
    Symbole d'appui dessiné sous un nœud.
    
    Types de symboles :
        - Encastrement : rectangle hachuré
        - Appui simple : triangle vers le bas
        - Rotule : cercle vide
        - Appui à rouleau : triangle + cercle
    
    Le symbole est un groupe d'items (lignes + polygones)
    attaché au nœud. Il se déplace avec le nœud.
    """


class GridItem(QGraphicsItem):
    """
    Grille de fond dessinée en arrière-plan.
    
    Optimisation : ne dessine que les lignes visibles dans le viewport
    actuel, pas toute la grille infinie. Recalcule à chaque changement
    de zoom/pan via paint().
    
    Deux niveaux :
        - Grille majeure (1m) : lignes gris moyen, épaisseur 1px
        - Grille mineure (0.25m) : lignes gris clair, épaisseur 0.5px
    """


class ReferenceLineItem(QGraphicsLineItem):
    """
    Ligne de référence (file de poteaux) avec label.
    
    Files X : lignes verticales nommées "A", "B", "C"...
    Files Y : lignes horizontales nommées "1", "2", "3"...
    
    Dessinées en trait mixte bleu clair, avec le nom dans un
    cercle aux extrémités (convention dessin technique français).
    """
```

---

## 5. Synchronisation 2D ↔ 3D

### 5.1 Mécanisme des signaux

```python
# Dans ProjectModel (model_data.py) — signaux existants ou à ajouter :
class ProjectModel(QObject):
    # Signaux émis après chaque modification
    node_added = Signal(int)          # tag du nœud ajouté
    node_removed = Signal(int)        # tag du nœud supprimé
    node_updated = Signal(int)        # tag du nœud modifié
    element_added = Signal(int)       # tag de l'élément ajouté
    element_removed = Signal(int)     # tag de l'élément supprimé
    model_changed = Signal()          # signal générique (toute modif)
    level_changed = Signal(int)       # changement de niveau actif
```

### 5.2 Connexion dans la fenêtre principale

```python
# Dans main_window.py
def _setup_connections(self):
    model = self.project
    
    # Canvas 2D : mise à jour immédiate (item par item)
    model.node_added.connect(self.canvas_2d.on_node_added)
    model.node_removed.connect(self.canvas_2d.on_node_removed)
    model.element_added.connect(self.canvas_2d.on_element_added)
    model.element_removed.connect(self.canvas_2d.on_element_removed)
    
    # Vue 3D : mise à jour debounced (reconstruction complète)
    # On accumule les changements et on rafraîchit après 100ms de pause
    self._3d_timer = QTimer()
    self._3d_timer.setSingleShot(True)
    self._3d_timer.setInterval(100)  # 100ms de debounce
    self._3d_timer.timeout.connect(self.view_3d.rebuild_mesh)
    model.model_changed.connect(self._3d_timer.start)
```

### 5.3 Pourquoi le debounce pour la 3D ?

Quand l'ingénieur dessine un portique, il place 6 nœuds et 5 barres en quelques secondes. Sans debounce, la vue 3D se reconstruirait 11 fois (6 nœuds + 5 barres). Avec le debounce de 100ms, elle se reconstruit une seule fois, 100ms après le dernier clic. Le canvas 2D, lui, se met à jour immédiatement (ajout/suppression d'items individuels, pas de reconstruction globale).

### 5.4 Rebuild incrémental vs complet

| Vue | Stratégie de mise à jour | Raison |
|---|---|---|
| Canvas 2D | **Incrémental** : ajouter/supprimer un item | Rapide, pas de scintillement |
| Vue 3D | **Complet** : reconstruire tout le mesh PyVista | PyVista n'a pas d'API d'ajout incrémental efficace |

Pour la vue 3D, le rebuild complet est acceptable parce que PyVista reconstruit un mesh de 1000 éléments en <50ms. Le debounce évite juste les reconstructions inutiles.

---

## 6. Niveaux et Filtrage

### 6.1 Concept de niveau

Un bâtiment est découpé en niveaux horizontaux. Chaque niveau correspond à une altitude Z. L'utilisateur travaille sur un niveau à la fois dans la vue 2D.

```
Toiture  ─── Z = 9.0 m ──── Niveau 3
                │
   R+2    ─── Z = 6.0 m ──── Niveau 2
                │
   R+1    ─── Z = 3.0 m ──── Niveau 1
                │
   RDC    ─── Z = 0.0 m ──── Niveau 0
```

### 6.2 Sélecteur de niveau dans la toolbar

```python
class LevelSelector(QComboBox):
    """
    ComboBox de sélection du niveau actif.
    
    Affiche : "R+1 (Z = 3.00 m)"
    Quand l'utilisateur change de niveau :
        → ProjectModel.active_level_tag = nouveau_tag
        → Canvas 2D filtre les items visibles
        → En vue Plan : affiche les nœuds à Z = élévation
        → En vue Élévation/Coupe : met en surbrillance le niveau actif
    """
```

### 6.3 Filtrage des entités dans le canvas 2D

```python
# Dans StructuralCanvas2D
def apply_level_filter(self, level_tag: int | None):
    """
    Filtre les items visibles selon le niveau actif et la vue courante.
    
    Vue Plan (XY) :
        - Affiche les nœuds dont z ≈ élévation du niveau
        - Affiche les barres horizontales entre ces nœuds
        - Les poteaux apparaissent comme des points (section vue du dessus)
    
    Vue Élévation (XZ) :
        - Affiche TOUS les niveaux (c'est une coupe verticale)
        - Le niveau actif est en surbrillance (barres plus épaisses)
        - Les nœuds hors-plan (Y ≠ 0) sont grisés ou masqués
    
    Vue Coupe (YZ) :
        - Idem élévation mais dans l'autre direction
    """
    if level_tag is None:
        # Pas de filtre : tout afficher
        for item in self.scene().items():
            item.setVisible(True)
        return
    
    level = self._project.levels.get(level_tag)
    if level is None:
        return
    
    tolerance = 0.01  # 1 cm de tolérance
    
    if self._current_view == ViewType.PLAN_XY:
        for item in self.scene().items():
            if isinstance(item, NodeItem):
                node = self._project.nodes.get(item.node_tag)
                item.setVisible(
                    node is not None 
                    and abs(node.z - level.elevation) < tolerance
                )
            elif isinstance(item, BarItem):
                # Visible si au moins un nœud est à ce niveau
                item.setVisible(self._bar_visible_at_level(item, level, tolerance))
```

### 6.4 Copie d'étage

Fonctionnalité très demandée : copier un étage entier et le coller au niveau du dessus.

```python
def copy_level(self, source_level_tag: int, target_elevation: float) -> int:
    """
    Copie tous les nœuds et barres d'un niveau vers une nouvelle élévation.
    
    Retourne le tag du nouveau niveau créé.
    
    Algorithme :
        1. Récupérer les nœuds du niveau source
        2. Pour chaque nœud : créer un nouveau nœud à (x, y, target_z)
        3. Construire un mapping ancien_tag → nouveau_tag
        4. Pour chaque barre horizontale du niveau source :
           créer une barre entre les nouveaux nœuds correspondants
        5. Pour chaque nœud, créer un poteau vertical entre
           l'ancien nœud et le nouveau
    """
```

---

## 7. Arbre du Modèle (QTreeView)

### 7.1 Structure de l'arbre

```
📁 Modèle — Portique 2×3 niveaux
├── 📐 Niveaux
│   ├── RDC (Z = 0.00 m) — 6 nœuds
│   ├── R+1 (Z = 3.00 m) — 6 nœuds ← ACTIF
│   └── Toiture (Z = 6.00 m) — 6 nœuds
├── ⬤ Nœuds (18)
│   ├── N1 (0.00, 0.00, 0.00) [Encastrement]
│   ├── N2 (5.00, 0.00, 0.00) [Encastrement]
│   └── ...
├── ─ Éléments (25)
│   ├── E1 : N1→N4 — IPE 300 — S355
│   ├── E2 : N2→N5 — IPE 300 — S355
│   └── ...
├── 🔷 Matériaux
│   ├── Béton C25/30 (fcd = 16.7 MPa)
│   └── Acier S355 (fyd = 355 MPa)
├── ▭ Sections
│   ├── Rect. 30×50 cm (béton)
│   └── IPE 300 (acier)
└── ⬇ Charges
    ├── G — Permanentes
    └── Q — Exploitation
```

### 7.2 Interaction arbre ↔ canvas

- **Double-clic sur un niveau** dans l'arbre → change le niveau actif dans la vue 2D
- **Clic sur un nœud** → le sélectionne dans le canvas 2D et centre la vue
- **Clic sur un élément** → le met en surbrillance dans les deux vues
- **Clic droit** → menu contextuel (supprimer, propriétés, dupliquer)

---

## 8. Étapes d'Implémentation

### Étape 1 — Items graphiques (1-2 jours)

**Fichier : `gui/widgets/canvas_items.py`**

Créer les classes `NodeItem`, `BarItem`, `SupportItem`, `GridItem`, `ReferenceLineItem`.

Chaque item doit :
- Se positionner en coordonnées monde (mètres)
- Être sélectionnable (`ItemIsSelectable`)
- Avoir une taille constante en pixels pour les nœuds (`ItemIgnoresTransformations`)
- Porter un label (tag) inversé en Y pour être lisible malgré le `scale(1, -1)`
- Avoir un code couleur cohérent avec la vue 3D existante

**Vérification** : Créer une scène de test avec 5 nœuds et 4 barres. Zoomer/dézoomer. Les nœuds gardent la même taille, les barres s'allongent.

---

### Étape 2 — Canvas 2D de base (2-3 jours)

**Fichier : `gui/widgets/structural_canvas.py`**

Créer `StructuralCanvas2D(QGraphicsView)` avec :
- Inversion de l'axe Y
- Zoom molette centré sur le curseur
- Pan par clic milieu
- Dessin de la grille de fond (via `drawBackground()` ou un `GridItem`)
- Méthodes `on_node_added(tag)`, `on_node_removed(tag)` pour la synchronisation

**Vérification** : Le canvas affiche un portique simple (nœuds + barres) lu depuis le ProjectModel. Le zoom et le pan fonctionnent. La grille est visible et se redessine correctement à chaque niveau de zoom.

---

### Étape 3 — Modes souris (2-3 jours)

**Fichier : `gui/widgets/canvas_modes.py`**

Implémenter les 4 modes : `SelectionMode`, `NodeMode`, `BarMode`, `SupportMode`.

Le canvas a un attribut `_current_mode` et les événements souris sont délégués :

```python
def mousePressEvent(self, event):
    if event.button() == Qt.MiddleButton:
        # Pan — toujours actif
        ...
    elif event.button() == Qt.LeftButton:
        self._current_mode.on_press(event)

def set_mode(self, mode_class: type[CanvasMode]):
    if self._current_mode:
        self._current_mode.deactivate()
    self._current_mode = mode_class(self)
    self._current_mode.activate()
```

**Vérification** : En mode Nœud, cliquer place un nœud snappé à la grille. En mode Barre, deux clics créent une barre entre deux nœuds. Les nœuds apparaissent aussi dans la vue 3D après le debounce. L'UndoStack capture chaque action (Ctrl+Z annule le dernier nœud ou la dernière barre).

---

### Étape 4 — Split View et synchronisation (1 jour)

**Fichier : `gui/main_window.py` (modification)**

Intégrer le canvas 2D et la vue 3D existante dans un `QSplitter` horizontal.

```python
# Dans MainWindow._setup_central_widget()
self.canvas_2d = StructuralCanvas2D(self.project)
self.view_3d = ModelView3D(self.project)  # Existant

self.splitter = QSplitter(Qt.Horizontal)
self.splitter.addWidget(self.canvas_2d)
self.splitter.addWidget(self.view_3d)
self.splitter.setSizes([800, 300])
self.splitter.setCollapsible(1, True)

self.setCentralWidget(self.splitter)
```

Connecter les signaux du ProjectModel aux deux vues (immédiat pour le 2D, debounced pour le 3D).

**Vérification** : Dessiner un portique dans le canvas 2D. La vue 3D se met à jour en temps réel (avec un léger délai de 100ms). Redimensionner le splitter fonctionne. Réduire la vue 3D à 0 ne provoque pas de crash.

---

### Étape 5 — Niveaux et vues (2-3 jours)

**Fichier : `core/model_data.py` (extension) + `gui/widgets/structural_canvas.py` (modification)**

Ajouter `LevelData` et `GridData` au ProjectModel. Ajouter le sélecteur de niveau et les boutons Plan/Élévation/Coupe à la toolbar.

Implémenter le filtrage :
- Vue Plan : n'affiche que les entités du niveau actif
- Vue Élévation : affiche tous les niveaux, surligne l'actif
- Changement de vue : repositionne et recadre le canvas

Implémenter la copie d'étage : sélectionner un niveau, Ctrl+C, choisir l'élévation cible, Ctrl+V.

**Vérification** : Créer un bâtiment de 3 niveaux. Basculer entre les niveaux. En plan, seuls les nœuds du niveau actif sont visibles. En élévation, on voit les poteaux et poutres de tous les niveaux. Copier le RDC crée un R+1 identique avec les poteaux automatiques.

---

### Étape 6 — Arbre du modèle (2 jours)

**Fichier : `gui/widgets/tree_model.py` (implémentation)**

Créer un `QStandardItemModel` ou un `QAbstractItemModel` personnalisé qui reflète le ProjectModel. L'arbre se met à jour via les signaux du ProjectModel.

Implémenter les interactions arbre ↔ canvas ↔ 3D :
- Sélection dans l'arbre → sélection dans le canvas
- Sélection dans le canvas → sélection dans l'arbre
- Double-clic niveau → changement de niveau actif

**Vérification** : L'arbre reflète fidèlement le modèle. Ajouter un nœud dans le canvas → il apparaît dans l'arbre. Supprimer un élément dans l'arbre → il disparaît du canvas et de la 3D.

---

### Étape 7 — Toolbar de dessin et polish (1-2 jours)

Créer la toolbar avec les boutons de mode, le sélecteur de grille, les boutons de vue, et le raccourci clavier. Ajouter les curseurs personnalisés par mode (croix pour nœud, trait pour barre, etc.).

Ajouter le feedback visuel :
- Croix de visée en mode nœud (suit le curseur, snappé à la grille)
- Ligne élastique en mode barre (du nœud i au curseur)
- Coordonnées affichées dans la barre de statut : `X: 5.000 m  Y: 3.000 m  Grille: 0.25 m`

**Vérification** : L'interface est fluide et intuitive. Un ingenieur structure peut dessiner un portique sans lire de documentation.

---

## 9. Ordre de Développement et Dépendances

```
Étape 1          Étape 2           Étape 3
canvas_items ──→ structural    ──→ canvas_modes
                 canvas             │
                     │              │
                     ▼              ▼
                 Étape 4        Étape 5
                 split_view ──→ niveaux +
                 + synchro      filtrage
                     │              │
                     ▼              ▼
                 Étape 6        Étape 7
                 tree_model     toolbar +
                                polish
```

| Étape | Fichiers | Durée | Prérequis |
|---|---|---|---|
| 1 | `canvas_items.py` | 1-2j | Rien |
| 2 | `structural_canvas.py` | 2-3j | Étape 1 |
| 3 | `canvas_modes.py` | 2-3j | Étapes 1-2 |
| 4 | `main_window.py` modifié | 1j | Étapes 2-3 |
| 5 | `model_data.py` étendu + canvas modifié | 2-3j | Étape 4 |
| 6 | `tree_model.py` | 2j | Étape 4 |
| 7 | Toolbar + curseurs + feedback | 1-2j | Étapes 3-6 |
| **Total** | | **~15 jours** | |

---

## 10. Points Techniques Critiques

### 10.1 Performance de la grille

La grille ne doit pas dessiner 10 000 lignes quand l'utilisateur est dézoomé sur un modèle de 100m × 30m avec une grille de 0.25m. Deux solutions :

**Solution A (recommandée)** : dessiner la grille dans `QGraphicsView.drawBackground()` en ne traçant que les lignes visibles dans le viewport actuel.

```python
def drawBackground(self, painter, rect):
    """Ne dessine que les lignes de grille visibles."""
    left = rect.left()
    right = rect.right()
    top = rect.top()
    bottom = rect.bottom()
    
    # Grille mineure
    x = math.floor(left / self.grid.minor) * self.grid.minor
    while x <= right:
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        x += self.grid.minor
    # ... idem pour Y
```

**Solution B** : adapter la résolution de grille au zoom. Quand on est très dézoomé, passer de 0.25m à 1m ou 5m automatiquement.

### 10.2 Taille constante des nœuds

Le flag `ItemIgnoresTransformations` fait que l'item est dessiné en coordonnées écran (pixels), pas scène (mètres). Ça veut dire que sa `pos()` est en coordonnées scène (pour le positionnement) mais son `paint()` est en pixels (pour le dessin). C'est exactement ce qu'on veut : le nœud est au bon endroit mais garde une taille constante.

Attention : ce flag affecte aussi la détection de collision et la bounding box. Pour la sélection par boîte, il faudra peut-être ajuster la logique.

### 10.3 Labels inversés

Avec `scale(1, -1)` sur le view, tous les textes sont à l'envers. Pour chaque `QGraphicsTextItem` :

```python
label = QGraphicsTextItem(str(node.tag))
label.setTransform(QTransform.fromScale(1, -1))
# Positionner le label légèrement au-dessus et à droite du nœud
label.setPos(node.x + 0.15, node.y + 0.15)
```

Alternative : ne pas inverser le view globalement, et inverser les coordonnées Y dans le mapping scène ↔ monde. C'est plus de travail mais évite le problème des labels.

### 10.4 Accrochage aux nœuds existants (mode Barre)

En mode Barre, le clic doit accrocher au nœud le plus proche dans un rayon de ~10 pixels :

```python
def find_nearest_node(self, scene_pos: QPointF, radius_px: float = 10) -> int | None:
    """
    Trouve le nœud le plus proche de la position en scène.
    
    Le rayon est en pixels (constant quel que soit le zoom).
    On convertit le rayon pixel en distance scène via la matrice inverse.
    """
    # Convertir le rayon pixel en distance scène
    view_transform = self.canvas.transform()
    scale_x = view_transform.m11()
    radius_scene = radius_px / abs(scale_x)
    
    best_tag = None
    best_dist = float('inf')
    
    for node in self._project.nodes.values():
        dx = node.x - scene_pos.x()
        dy = node.y - scene_pos.y()
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < radius_scene and dist < best_dist:
            best_dist = dist
            best_tag = node.tag
    
    return best_tag
```

### 10.5 Undo/Redo intégré

Chaque action dans le canvas 2D passe par le ProjectModel qui gère l'UndoStack. L'utilisateur fait Ctrl+Z → le dernier nœud/barre est supprimé du ProjectModel → le signal model_changed est émis → le canvas 2D retire l'item correspondant → la vue 3D se reconstruit.

La chaîne est déjà en place dans `model_data.py`. Les modes souris n'ont qu'à appeler les méthodes du ProjectModel (`add_node`, `remove_node`, `add_element`, `remove_element`) qui poussent automatiquement sur l'UndoStack.

---

## 11. Checklist de Validation Sprint S?

### Canvas 2D
- [ ] Grille de fond visible et performante (pas de lag au zoom)
- [ ] Zoom molette centré sur le curseur
- [ ] Pan par clic milieu + drag
- [ ] Axe Y orienté vers le haut
- [ ] Les nœuds ont une taille constante quel que soit le zoom
- [ ] Les labels de nœuds sont lisibles (pas à l'envers)
- [ ] Le snap à la grille fonctionne (coordonnées arrondies)
- [ ] Le mode ortho contraint les tracés H/V

### Modes souris
- [ ] Mode Sélection : clic sélectionne, drag = boîte de sélection
- [ ] Mode Nœud : clic place un nœud, feedback visuel (croix de visée)
- [ ] Mode Barre : deux clics = une barre, ligne élastique entre les deux
- [ ] Mode Appui : clic sur nœud = menu de types d'appuis
- [ ] Échap annule l'action en cours dans tous les modes
- [ ] Les raccourcis S/N/B/A changent de mode

### Synchronisation
- [ ] Ajouter un nœud dans le canvas → il apparaît dans la vue 3D
- [ ] Supprimer un élément dans le canvas → il disparaît de la vue 3D
- [ ] Le debounce empêche les reconstructions 3D excessives
- [ ] Ctrl+Z annule la dernière action dans les deux vues
- [ ] Ctrl+Y refait l'action annulée

### Niveaux
- [ ] Créer un niveau (nom, élévation) depuis l'arbre ou un dialogue
- [ ] Le sélecteur de niveau filtre les entités en vue Plan
- [ ] En vue Élévation, tous les niveaux sont visibles
- [ ] Copier un étage crée le niveau cible avec nœuds + barres + poteaux
- [ ] Basculer Plan ↔ Élévation ↔ Coupe repositionne la caméra 2D

### Arbre du modèle
- [ ] L'arbre reflète fidèlement le ProjectModel
- [ ] Double-clic sur un niveau change le niveau actif
- [ ] Sélection dans l'arbre → sélection dans le canvas (et inversement)
- [ ] Menu contextuel (clic droit) : supprimer, propriétés

### Intégration
- [ ] Le QSplitter 2D/3D est redimensionnable
- [ ] La vue 3D peut être réduite à 0 sans crash
- [ ] La barre de statut affiche les coordonnées du curseur en temps réel
- [ ] Les performances restent fluides avec 200 nœuds et 300 barres

---

*Document généré le 22 mars 2026 - HEXA Structures Sprint S?*
