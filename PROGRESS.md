# HEXA Structures - Suivi d'avancement

> Base de suivi redemarree avec la version 0.1.0 et mise a jour apres la
> premiere passe d'architecture ports/adaptateurs/plugins.

---

## Etat actuel

| Info | Valeur |
|---|---|
| Version applicative | 0.1.0 |
| Date de base | 23 mai 2026 |
| Moteur principal | PyNite |
| Moteur avance optionnel | OpenSeesPy |
| Etat global | Base publique propre, avec modelisation GUI, persistance SQLite, analyse statique, diagrammes, plaques macro, maillage automatique et architecture plugin progressive. |
| Validation courante | `pytest -q` : 460 tests passes |

---

## Termine

- Modele de donnees central et sauvegarde SQLite.
- Materiaux, sections, noeuds, barres, appuis, charges et combinaisons.
- PyNite comme moteur de calcul principal.
- OpenSeesPy comme moteur optionnel.
- Orientation locale 3D robuste des barres.
- Plaques utilisateur macro a 4 noeuds.
- Maillage interne invisible pour le calcul des plaques.
- Mode de maillage plaque automatique ou utilisateur.
- Charges surfaciques et appuis de bord propages au maillage plaque.
- Mapping des resultats plaques vers les objets utilisateur.
- Diagrammes de barres et cartes de resultats plaques.
- Tests de non-regression du noyau et de la GUI.
- Couche `core/application` avec ports, DTOs, cas d'usage et facade `ApplicationServices`.
- Adaptateurs solveurs PyNite/OpenSeesPy dans `core/adapters/solvers`.
- Adaptateur de maillage `StructuredQuadPlateMesher`.
- Registry de plugins internes pour les solveurs.
- Decouverte de plugins installes via `plugin.json` ou `hexa-plugin.json`.
- Loader externe `ImportlibPluginLoader`, actif uniquement lorsqu'il est explicitement injecte.
- Manifestes de plugins generiques avec `kind`, `extension_points`, `capabilities` et `tags`.
- Point d'extension `connections.design` et host applicatif pour les futurs plugins d'assemblages.

---

## A faire ensuite

1. Ajouter un exemple minimal de plugin externe `connections.ec3`.
2. Documenter le format de manifeste plugin et les points d'extension publics.
3. Ajouter une vue ou commande de diagnostic des plugins installes.
4. Ajouter une convergence adaptative optionnelle pour le maillage automatique.
5. Consolider les resultats de cisaillement plaques selon la formulation.
6. Ameliorer les exports CSV/PDF.
7. Poursuivre les validations analytiques et comparatives.
8. Ajouter progressivement les verifications EC2/EC3.
