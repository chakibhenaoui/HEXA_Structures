# Base de donnees des profiles acier et sections parametriques

La base integree des profiles acier se trouve dans :

```text
resources/profiles/european_profiles.json
```

`core.sections` charge ce fichier au demarrage. Si le fichier est absent ou invalide,
HEXA revient au catalogue interne de secours afin de continuer a demarrer.

La GUI utilise deux voies complementaires :

- les profiles de catalogue, selectionnes par famille et par designation ;
- les sections parametriques creees manuellement dans la boite de definition des sections.

Une rotation de section reste une propriete de l'element (`roll_angle_deg`) et ne cree
jamais un nouveau profile du type `IPE 300 tourne`.

## Structure

Le fichier JSON contient :

- `schema_version` : version du schema de la base.
- `units` : unites attendues dans les lignes de donnees.
- `families` : liste ordonnee des familles visibles dans la GUI.

Chaque famille definit :

- `code` : code stable utilise par l'application, par exemple `IPE`, `CHS`, `L unequal`.
- `label` : libelle utilisateur.
- `shape` : forme geometrique, par exemple `i_section`, `channel`, `circular_hollow`.
- `standard` : reference indicative.
- `source` : `tabulated` ou `theoretical_geometry`.
- `method` : methode de lecture/calcul.
- `columns` et `rows` : donnees compactes sous forme tabulaire.

## Methodes disponibles

- `tabulated` : proprietes A, Iy, Iz, Wel, Wpl et masse lues directement.
- `i_shape` : profile I/H idealise a partir de `h`, `b`, `tw`, `tf`.
- `channel` : profile U idealise a partir de `h`, `b`, `tw`, `tf`.
- `chs` : tube circulaire a partir de `d`, `t`.
- `shs` : tube carre a partir de `size`, `t`.
- `rhs` : tube rectangulaire a partir de `h`, `b`, `t`.
- `angle_equal` : corniere egale a partir de `size`, `t`.
- `angle_unequal` : corniere inegale a partir de `h`, `b`, `t`.

## Sections disponibles dans la GUI

La boite de definition des sections expose actuellement :

- beton rectangulaire ;
- section en T ;
- I / H parametrique ;
- U / Channel parametrique ;
- corniere L parametrique ;
- tube circulaire parametrique ;
- tube rectangulaire parametrique ;
- profile acier de catalogue.

Le panneau de gauche affiche un schema dynamique de la section courante. Pour un profile
de catalogue, la geometrie est affichee mais les dimensions ne sont pas modifiables :
l'utilisateur choisit un autre profile s'il veut une autre geometrie.

Pour les sections parametriques, les proprietes `area`, `inertia_y`, `inertia_z` et
`properties` sont recalculees a partir des dimensions saisies.

## Section Builder HEXA

Le menu `Modele > Section Builder...` ouvre l'atelier intégré de sections
personnalisées.

Cette version utilise uniquement PySide6 pour l'edition 2D :

- `QGraphicsView` ;
- `QGraphicsScene` ;
- items graphiques de grille, de contour et de points ;
- zoom molette ;
- accrochage a la grille.

La version actuelle permet :

- barre de menus interne `Fichier` avec nouveau, ouvrir, importer forme,
  enregistrer, enregistrer sous, note de calcul et quitter ;
- menu interne `sectionproperties` avec insertion depuis la bibliotheque,
  calcul, résultats et affichage des contraintes ;
- affichage du repere local y/z ;
- affichage d'une grille ;
- accrochage au pas de grille ;
- dessin point par point du contour exterieur ;
- dessin point par point de trous interieurs ;
- edition des coordonnees dans un tableau ;
- insertion et suppression de points ;
- fermeture du contour par clic pres du premier point, clic droit ou bouton ;
- refus des contours croises ou degeneres ;
- analyse geometrique simple par formules polygonales ;
- analyse optionnelle par `sectionproperties` si la bibliotheque est installee ;
- insertion de formes parametriques depuis `sectionproperties.pre.library`
  directement dans le canevas du Section Builder ;
- generation et affichage du maillage triangule ;
- calcul et affichage de plusieurs composantes de contraintes élastiques ;
- enveloppes min/max de contraintes avec localisation des extrema ;
- génération d'une note de calcul éditable avec figures et avertissements ;
- affichage du centre de gravite apres analyse ;
- insertion dans la bibliotheque des sections du projet.

Le calcul fournit :

- aire `area` ;
- perimetre `perimeter` ;
- inertie forte `inertia_y` ;
- inertie faible `inertia_z` ;
- centre de gravite local `centroid_y`, `centroid_z`.

Une section issue de cette voie est sauvegardee comme :

```text
section_type = "custom_polygon"
properties["source"] = "section_builder"
properties["analysis_engine"] = "polygonal" | "sectionproperties"
properties["points"] = [...]
properties["holes"] = [...]
properties["hole_count"] = ...
properties["perimeter"] = ...
properties["centroid_y"] = ...
properties["centroid_z"] = ...
```

Une forme inseree depuis la bibliotheque `sectionproperties` reste creee depuis le
Section Builder, mais elle est sauvegardee avec le type historique compatible :

```text
section_type = "sectionproperties"
properties["source"] = "sectionproperties"
properties["source_tool"] = "section_builder"
properties["shape"] = "rectangular" | "i" | "channel" | "tee" | "angle" | "chs" | "rhs"
properties["display_type"] = ...
properties["dimensions"] = {...}
properties["points"] = [...]
properties["holes"] = [...]
```

Quand `sectionproperties` est disponible, le Section Builder utilise le contour
exterieur ferme et les trous fermes pour creer une geometrie `sectionproperties`,
generer un maillage et recalculer les proprietes. Les informations avancees sont
conservees sous :

```text
properties["sectionproperties"]["mesh_area"] = ...
properties["sectionproperties"]["ixy"] = ...
properties["sectionproperties"]["torsion_constant"] = ...
properties["sectionproperties"]["mesh_node_count"] = ...
properties["sectionproperties"]["mesh_triangle_count"] = ...
```

Si la bibliotheque n'est pas installee, ou si le maillage echoue, HEXA conserve le
calcul polygonal simple pour les sections pleines. Les sections avec trous exigent
`sectionproperties`, car le calcul polygonal simple ne soustrait pas encore les
contours interieurs.

La vue 3D reutilise directement les points du contour pour l'affichage/extrusion.
Les solveurs continuent a lire les valeurs numeriques `area`, `inertia_y` et
`inertia_z` sans connaitre PySide6.

Limites volontaires de cette étape :

- pas de sections composees ;
- pas d'import DXF ;
- pas de verification EC3 ;
- `sectionproperties` reste optionnel et peut etre installe via `requirements-optional.txt`.

L'objectif produit reste de construire ensuite un vrai atelier comparable aux outils de
Robot ou SAP2000 : contours multiples, trous, import DXF, maillage visible et calculs
avances.

## Backend sectionproperties

Il n'y a plus d'atelier `sectionproperties` separe dans le menu principal. Les fonctions
de cette bibliotheque sont exposees dans `Modele > Section Builder...`, via le menu
interne `sectionproperties`.

Installation optionnelle :

```powershell
pip install -r requirements-optional.txt
```

La couche `core.sectionproperties_adapter` reste independante de PySide6. Elle expose :

- statut d'import et version installee ;
- modules detectes ;
- fonctions de la bibliotheque `sectionproperties.pre.library` ;
- capacites branchees ou prevues.

Capacites deja branchees dans HEXA :

- bibliotheque de sections parametriques ;
- generation du maillage ;
- analyse geometrique ;
- analyse de torsion / gauchissement pour recuperer `J` quand possible.
- analyse et tracé des contraintes élastiques ;
- synthèse min/max des contraintes pour la note de calcul.

Capacites preparees pour les prochaines etapes :

- analyse `frame` ;
- analyse plastique ;
- post-traitement avancé ;
- import DXF ;
- contours multiples plus avances ;
- sections composees et materiaux multiples.

Le packaging PyInstaller inclut `sectionproperties` seulement si la bibliotheque est
installee dans l'environnement de build. Une build sans `sectionproperties` doit donc
continuer a demarrer normalement.

## Limites geometriques dans la GUI

Le dialogue de section bride les dimensions dependantes afin de conserver une geometrie
physiquement possible :

- I / H : `tw < b` et `2 * tf < h` ;
- U / Channel : `tw < b` et `2 * tf < h` ;
- corniere L : `t < min(h, b)` ;
- tube circulaire : `2 * t < d` ;
- tube rectangulaire : `2 * t < min(h, b)` ;
- T : `bw < bf`.

Ces limites sont appliquees pendant la saisie et verifiees a nouveau lors de la validation
du dialogue. Si une ancienne section chargee depuis un projet viole ces regles, les calculs
de proprietes retournent zero et le dialogue affiche un message de geometrie invalide.

## Materiau par defaut

La GUI choisit automatiquement un materiau coherent quand c'est possible :

- `rectangular` selectionne le premier materiau beton disponible ;
- les sections acier parametriques et les profiles de catalogue selectionnent le premier
  materiau acier disponible.

Ce choix automatique ne modifie pas le core metier et reste surchargeable par l'utilisateur.

## Ajouter un profile

1. Choisir la famille existante dans `families`.
2. Ajouter une ligne dans `rows` en respectant exactement l'ordre de `columns`.
3. Lancer les tests :

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ops_builder.py
```

Pour une famille nouvelle, ajouter une entree dans `families`. Les familles connues sont
affichees dans l'ordre du JSON, puis exposees par `list_profile_families()`.

## Couverture actuelle

La base embarque plus de 200 entrees. Les familles IPE, HEA, HEB, HEM, UPN, UPE,
CHS, SHS, RHS et cornieres
contiennent plusieurs epaisseurs courantes pour un meme format nominal, afin de
mieux correspondre aux catalogues de stock du marche.

## Limite actuelle

Les familles marquees `theoretical_geometry` sont calculees a partir d'une geometrie
idealisee sans rayons de raccordement. Elles conviennent pour alimenter les solveurs avec
A, Iy et Iz, mais ne remplacent pas une table de verification Eurocode 3.
