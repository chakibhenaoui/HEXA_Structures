# HEXA Structures - Suivi d'avancement

> État vérifié le 26 septembre 2026 sur la branche `codex/polygonal-results-convergence`.

---

## Etat actuel

| Info | Valeur |
|---|---|
| Version applicative | 0.1.0 |
| Dernière mise à jour | 26 septembre 2026 |
| Dernier développement | PR3 de résultats et convergence des surfaces polygonales en cours |
| Moteur principal | PyNite |
| Moteur avancé optionnel | OpenSeesPy |
| État global | Application fonctionnelle en consolidation : modélisation GUI, persistance SQLite, calcul multi-solveur, plaques macro, résultats, i18n, plugins et Section Builder avancé. |
| Validation récente | `python -m pytest -q` : 635 réussis ; lint ciblé vert |

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
- Page de chargement au premier lancement du Section Builder.
- Onglet Synthèse des résultats avec maxima/minima critiques et cas/combinaisons associés.
- Enveloppes de barres affichées pour `N`, `Vy`, `Vz`, `T`, `My` et `Mz`.
- Export CSV de l'onglet actif des tableaux de résultats.
- Contours surfaciques plans convexes ou concaves, sauvegardés et affichés en 3D.
- Contrat de maillage générique commun aux cellules quadrangulaires et triangulaires.
- Mailleur triangulaire contraint des contours polygonaux, indépendant du solveur.
- Routage automatique entre maillage quadrangulaire structure et triangulation
  contrainte, y compris pour les quadrilateres concaves.
- Calcul OpenSeesPy des surfaces polygonales avec `ASDShellT3`, integration
  complete, cinematique lineaire et axe local commun a la macro-surface.
- Propagation des charges surfaciques et appuis de bord vers les triangles.
- Validation OpenSeesPy par equilibre des reactions et fleche analytique d'une
  plaque carree simplement appuyee.
- Extraction des efforts membranaires, moments et cisaillements des triangles
  `ASDShellT3`, avec extrapolation des points d'integration aux noeuds.
- Resultats polygonaux agreges dans les tableaux et syntheses, et cartes
  triangulaires avec lissage nodal pondere par aire.
- Etude de raffinement des fleches et moments sur une plaque carree simplement
  appuyee ; les pics de cisaillement aux coins restent sensibles au maillage.

---

## Plan du maillage polygonal

Décision technique : utiliser une triangulation de Delaunay contrainte par le
contour, fournie par `cytriangle`. Le maillage reste un adaptateur indépendant du
solveur et conserve explicitement la topologie des cellules et des bords. Les
surfaces polygonales sont reservees a OpenSeesPy. Les resultantes et les cartes
restent bloquees tant que leur extraction n'est pas validee de bout en bout.

1. **PR1 - Socle de maillage** : généraliser le contrat de maillage, produire des
   triangles contraints déterministes, préserver les bords partagés, les plans
   inclinés et l'orientation, sans activer le calcul polygonal.
2. **PR2 - Intégration OpenSeesPy** : construire des éléments `ASDShellT3` avec
   intégration complète et comportement linéaire, propager charges et appuis,
   imposer un repère local cohérent et ajouter des cas analytiques de référence.
3. **PR3 - Résultats et convergence** : mapper les résultats vers la macro-surface,
   expliciter les conventions de signes, puis ajouter les cartes, le lissage
   contrôlé et les études de convergence.

État actuel : PR1 fusionne dans `main` par la PR #7. PR2 implemente et valide
localement. PR3 demarree sur une branche issue de PR2 : extraction des
resultantes, cartes triangulaires et validation de raffinement implementees.
La convergence adaptative et la stabilisation des pics de cisaillement pres des
appuis restent a faire.

---

## À faire ensuite

1. Finaliser l'export PDF général des résultats et notes de calcul.
2. Poursuivre la validation ergonomique des tableaux, synthèses et enveloppes.
3. Finaliser et publier le PR2 d'intégration OpenSeesPy des triangles `ASDShellT3`.
4. Finaliser la revue et la publication du PR3 de résultats polygonaux.
5. Stabiliser les résultats de cisaillement des plaques selon la formulation.
6. Ajouter une convergence adaptative optionnelle pour le maillage des plaques.
7. Étendre le Section Builder : import DXF, sections composées et matériaux multiples.
8. Ajouter progressivement les vérifications EC2/EC3.
9. Fournir un exemple de plugin externe `connections.ec3` et un diagnostic des plugins.
10. Poursuivre les validations analytiques et comparatives des deux solveurs.
