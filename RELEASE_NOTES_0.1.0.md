# HEXA Structures 0.1.0 - Notes de release

Date du tag initial `v0.1.0` : 20 mai 2026

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

Commande de validation :

```text
pytest tests/ -q
```

Validation du lot Windows/i18n du 29 mai 2026 :

```text
361 passed, 14 skipped
```

La validation du dépôt courant est suivie dans `PROGRESS.md` et ne doit pas être
confondue avec la validation historique de cette version.

## Évolutions engagées après la release

Depuis la base 0.1.0, le depot a commence une migration progressive vers une
architecture ports/adaptateurs/plugins :

- couche `core/application` avec ports, DTOs, cas d'usage et facade applicative ;
- adaptateurs solveurs PyNite/OpenSeesPy dans `core/adapters/solvers` ;
- decouverte de plugins par manifestes `plugin.json` / `hexa-plugin.json` ;
- loader externe opt-in via `ImportlibPluginLoader` ;
- manifestes generiques avec `kind`, `extension_points`, `capabilities` et `tags` ;
- premier point d'extension metier `connections.design` pour les futurs plugins d'assemblages.
- internationalisation française et anglaise ;
- catalogue de profils enrichi et sections paramétriques ;
- Section Builder avec contours, trous, maillage, contraintes et note de calcul.

Ces éléments sont post-release 0.1.0 : ils documentent l'évolution du dépôt,
mais ne changent pas le perimetre fonctionnel annonce pour la release publique
initiale.

## Limites connues

- Les resultats doivent rester verifies par un ingenieur structure qualifie.
- Les plaques sont limitees aux regions quadrangulaires regulieres.
- Les ouvertures, tremies, contours quelconques et maillages triangulaires ne
  sont pas encore pris en charge.
- Le maillage automatique est une regle deterministe de taille d'element, pas
  encore une convergence adaptative.
- Les exports CSV/PDF de resultats restent a finaliser.
- Les verifications EC2/EC3 automatiques restent hors scope de cette release.
- Les plugins externes sont prepares cote architecture, mais aucun plugin metier
  officiel n'est encore livre avec la version 0.1.0.
