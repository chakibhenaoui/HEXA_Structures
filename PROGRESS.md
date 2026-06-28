# HEXA Structures - Suivi d'avancement

> État vérifié le 28 juin 2026 sur la branche `main`.

---

## Etat actuel

| Info | Valeur |
|---|---|
| Version applicative | 0.1.0 |
| Dernière mise à jour | 28 juin 2026 |
| Dernier développement | Documentation illustrée de l'interface 3D et intégration consolidée des sections utilisateur Section Builder |
| Moteur principal | PyNite |
| Moteur avancé optionnel | OpenSeesPy |
| État global | Application fonctionnelle en consolidation : modélisation GUI, persistance SQLite, calcul multi-solveur, plaques macro, résultats, i18n, plugins et Section Builder avancé. |
| Validation récente | `python -m pytest tests/test_i18n.py tests/test_section_builder.py tests/test_property_panel.py ...` : 42 réussis |

---

## Terminé

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
- Interface française et anglaise avec catalogues Qt validés.
- Catalogue de plus de 200 profilés acier et sections paramétriques I/H, U, L et tubes.
- Section Builder intégré avec contours extérieurs, trous, édition tabulaire et
  import de profils.
- Analyse polygonale de secours pour les sections pleines.
- Intégration optionnelle de `sectionproperties` pour le maillage, les propriétés
  géométriques, la torsion et les contraintes.
- Affichage des contraintes de section et génération d'une note de calcul.
- Extrusion 3D des sections paramétriques et personnalisées.
- Documentation README illustrée avec une capture de l'interface 3D.

---

## À faire ensuite

1. Consolider les tableaux, synthèses et enveloppes de résultats.
2. Ajouter les exports CSV et PDF généraux.
3. Stabiliser les résultats de cisaillement des plaques selon la formulation.
4. Ajouter une convergence adaptative optionnelle pour le maillage des plaques.
5. Étendre le Section Builder : import DXF, sections composées et matériaux multiples.
6. Ajouter progressivement les vérifications EC2/EC3.
7. Fournir un exemple de plugin externe `connections.ec3` et un diagnostic des plugins.
8. Poursuivre les validations analytiques et comparatives des deux solveurs.
