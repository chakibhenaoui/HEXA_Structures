# Changelog

## Non publie

### Ajoute

- Catalogue acier enrichi avec plus de 200 profiles europeens courants : IPE, HEA, HEB, HEM, UPN, UPE, CHS, SHS, RHS et cornieres.
- Sections parametriques filaires dans la GUI : I/H, U, L, tube circulaire et tube rectangulaire.
- Section Builder HEXA : dessin 2D point par point sur grille, accrochage, fermeture de contour, analyse polygonale simple et insertion dans les sections du projet.
- Edition du contour dans le Section Builder : tableau de coordonnees modifiable, insertion/suppression de points et marqueur du centre de gravite.
- Validation du Section Builder contre les contours croises ou degeneres, avec affichage du perimetre calcule.
- Calcul optionnel des contours Section Builder par `sectionproperties`, avec generation et affichage du maillage triangule.
- Trous interieurs dans le Section Builder, calcules par `sectionproperties` et sauvegardes dans les sections personnalisees.
- Fusion de l'atelier `sectionproperties` dans le Section Builder : menus Fichier/sectionproperties, insertion de formes de bibliotheque, calcul et resultats dans un seul outil.
- Socle technique `sectionproperties` expose dans le Section Builder avec statut d'import, version, fonctions detectees et capacites branchees/prevues.
- Import de profils acier du catalogue dans le Section Builder.
- Calcul et affichage des contraintes elastiques de section avec `sectionproperties`.
- Enveloppes min/max de contraintes et note de calcul editable avec figures, regeneration depuis le calcul et export PDF direct.
- Apercu dynamique de section dans la boite de definition des sections.
- Extrusion 3D des nouvelles sections parametriques, avec tubes creux et couleur differente par section.
- Capture de l'interface 3D ajoutee aux README pour illustrer l'etat actuel du logiciel.
- Page de chargement au premier lancement du Section Builder pour rendre visible
  l'initialisation des profils et modules optionnels.
- Onglet Synthese des resultats avec valeurs critiques multi-cas : deplacements,
  reactions, efforts internes, plaques et cas/combinaisons associes.
- Export CSV de l'onglet actif des tableaux de resultats, avec prise en compte
  du filtre courant.

### Modifie

- Table des enveloppes etendue a toutes les composantes principales `N`, `Vy`,
  `Vz`, `T`, `My` et `Mz`.
- Calcul des enveloppes rendu robuste lorsque le premier cas analyse ne contient
  pas de resultats pour un element donne.
- Selection automatique du materiau coherent dans la boite de section : beton pour les sections rectangulaires, acier pour les profiles acier.
- Limites geometriques pendant la saisie : epaisseurs et ames bridees pour conserver des formes valides.
- Packaging PyInstaller inclut `sectionproperties` si la bibliotheque est installee, tout en gardant un demarrage possible sans elle.
- Catalogues i18n francais et anglais regeneres pour les nouveaux libelles de sections, de repere local et de validation.
- Documentation de suivi actualisee au 28 juin 2026.

### Validation

- `python -m pytest -q` : 603 tests passes le 19 juillet 2026.
- `python -m pytest -q` : 595 tests passes le 11 juillet 2026.
- `python -m pytest tests/test_section_builder_loading.py tests/test_main_window_toolbar.py -q` : 12 tests passes le 19 juillet 2026.
- `python -m pytest tests/test_section_builder.py tests/test_surface_sections_ui.py -q` : 50 tests passes le 19 juillet 2026.
- `python -m ruff check gui/main_window.py tests/test_section_builder_loading.py` : OK.
- `python -m pytest -q` : 594 tests passes le 1er juillet 2026.
- `python -m ruff check core/results.py gui/widgets/results_panel.py gui/main_window.py tests/test_results_panel.py tests/test_main_window_toolbar.py` : OK.
- `python -m pytest -q` : 585 tests passes le 26 juin 2026.
- `python -m pytest tests/test_i18n.py tests/test_section_builder.py tests/test_property_panel.py ...` : 42 tests cibles passes le 28 juin 2026.
- `pyside6-lrelease i18n\hexa_en.ts -qm i18n\hexa_en.qm` : 1388 traductions terminees.
- `pyside6-lrelease i18n\hexa_fr.ts -qm i18n\hexa_fr.qm` : 1388 traductions terminees.

## 0.1.0 - Build Windows i18n post-release

Date : 2026-05-29

Le tag initial `v0.1.0` date du 20 mai 2026. Cette section décrit le lot de
stabilisation i18n et de packaging réalisé après ce tag.

### Ajouté

- Architecture d'internationalisation Qt prête pour plusieurs langues.
- Menu `Paramètres > Langue` limité aux langues prêtes : Français et English.
- Catalogues `i18n/hexa_fr.*` et `i18n/hexa_en.*` inclus dans la build Windows.
- Squelettes `i18n/hexa_es.*` et `i18n/hexa_de.*` conservés pour les futures traductions.
- Smoke tests de build pour vérifier la langue anglaise et le repli français si un `.qm` manque.
- Script Inno Setup dans `installer/` pour produire un installateur Windows.

### Corrigé

- Résidus de traduction anglaise dans les diagrammes, exports, Eurocodes, sections, charges, panneaux et messages visibles.
- Tooltips et messages de résultats/diagrammes passés par `self.tr(...)`.
- Packaging PyInstaller vérifié avec le dossier `i18n/`.

### Validation

- `pytest` : 361 tests passés, 14 ignorés.
- `pyside6-lrelease i18n\hexa_en.ts -qm i18n\hexa_en.qm` : 1096 traductions terminées.
