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
