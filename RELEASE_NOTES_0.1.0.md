# HEXA Structures 0.1.0 - Notes de release

Date cible : 20 mai 2026

## Type de release

Base initiale propre pour le depot public.

Cette version consolide :

- le modele de donnees SQLite ;
- la modelisation des noeuds, barres, sections, materiaux, appuis et charges ;
- PyNite comme moteur principal ;
- OpenSeesPy comme moteur optionnel avance ;
- l'orientation locale 3D robuste des barres ;
- les plaques utilisateur macro avec maillage de calcul interne ;
- le mode de maillage plaque automatique ou utilisateur ;
- le mapping des resultats plaques vers les objets utilisateur ;
- les tableaux, diagrammes et cartes de resultats actuellement supportes.

## Validation

Validation courante :

```text
pytest tests/ -q
```

Etat actuel :

```text
274 passed, 14 skipped
```

## Limites connues

- Les resultats doivent rester verifies par un ingenieur structure qualifie.
- Les plaques sont limitees aux regions quadrangulaires regulieres.
- Les ouvertures, tremies, contours quelconques et maillages triangulaires ne
  sont pas encore pris en charge.
- Le maillage automatique est une regle deterministe de taille d'element, pas
  encore une convergence adaptative.
- Les exports CSV/PDF de resultats restent a finaliser.
- Les verifications EC2/EC3 automatiques restent hors scope de cette release.
