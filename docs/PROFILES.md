# Base de donnees des profiles acier

La base integree des profiles acier se trouve dans :

```text
resources/profiles/european_profiles.json
```

`core.sections` charge ce fichier au demarrage. Si le fichier est absent ou invalide,
HEXA revient au catalogue interne de secours afin de continuer a demarrer.

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

La base embarque plus de 200 entrees. Les familles CHS, SHS, RHS et cornieres
contiennent plusieurs epaisseurs courantes pour un meme format nominal, afin de
mieux correspondre aux catalogues de stock du marche.

## Limite actuelle

Les familles marquees `theoretical_geometry` sont calculees a partir d'une geometrie
idealisee sans rayons de raccordement. Elles conviennent pour alimenter les solveurs avec
A, Iy et Iz, mais ne remplacent pas une table de verification Eurocode 3.
