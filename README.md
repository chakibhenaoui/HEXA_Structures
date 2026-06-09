# HEXA Structures

[English version](README.en.md)

> Application open source de calcul de structures avec **PyNite** comme moteur par défaut, **OpenSeesPy** comme moteur avancé optionnel et **PySide6** pour l'interface graphique.

## Présentation

HEXA Structures est un logiciel desktop de modélisation et d'analyse destiné aux ingénieurs structure. Le projet combine :

- **PyNite** comme moteur de calcul par défaut
- **OpenSeesPy** comme moteur avancé optionnel
- **PySide6** pour l'interface graphique
- **PyVista / pyvistaqt** pour la visualisation 3D interactive
- une intégration native des **Eurocodes (EC0 à EC8)** avec les **annexes nationales françaises**
- une architecture applicative progressive de type ports/adaptateurs, avec support de plugins installables

## État du projet

Le projet a dépassé le stade du prototype. Aujourd'hui, la base applicative est en place avec :

- un noyau de calcul multi-solveur
- une couche `core/application/` avec ports, cas d'usage et façade applicative
- une couche `core/adapters/` pour les solveurs et le maillage
- une couche `core/plugins/` pour découvrir des plugins par manifeste sans exécuter de code par défaut
- une interface structurée
- la gestion des matériaux, sections, conditions aux limites, charges et combinaisons
- l'extraction de résultats et le rendu des diagrammes 2D pour les cas pris en charge
- une vue 3D interactive connectée au modèle

Les travaux en cours portent surtout sur :

- l'amélioration continue de l'ergonomie de l'interface
- le post-traitement et les tableaux de résultats
- les enveloppes de résultats et la lecture multi-cas / multi-combinaisons
- les vérifications normatives et les exports de note de calcul
- les plugins métier installables, notamment le futur calcul des assemblages

## Fonctionnalités disponibles

- Modélisation de base du projet : nœuds, éléments poutres, appuis
- Bibliothèque de matériaux béton (EC2) et acier (EC3)
- Sections rectangulaires, en T, I/H, U, L et tubes avec aperçu dynamique
- Catalogue embarqué de plus de 200 profilés européens (`IPE`, `HEA`, `HEB`, `HEM`, `UPN`, `UPE`, `CHS`, `SHS`, `RHS`, cornières)
- Vue 3D avec sélection interactive et symboles d'appui
- Arbre hiérarchique du modèle synchronisé avec la vue
- Panneau de propriétés éditable pour les principaux objets
- Dialogues de création : matériaux, sections, charges, combinaisons, réglages Eurocodes
- Analyses statiques linéaires via PyNite et OpenSeesPy
- Plaques quadrangulaires experimentales via maillage interne automatique OpenSeesPy
- Découverte de plugins installés par manifestes `plugin.json` / `hexa-plugin.json`
- Host applicatif initial pour les plugins d'assemblages exposant `connections.design`
- Extraction des résultats : déplacements, réactions, efforts internes
- Diagrammes 2D `N / V / T / M` sur les cas pris en charge
- Affichage des conditions aux limites sur les diagrammes 2D
- Sauvegarde et chargement des projets au format SQLite (`.db`)

## Feuille de route

- Vue résultats plus aboutie et tableaux complets de post-traitement
- Enveloppes de résultats et lecture multi-cas / multi-combinaisons
- Vérifications automatiques EC2 / EC3 / EC8
- Plugin externe de calcul des assemblages acier, installé séparément
- Paramétrage sismique EC8 plus complet
- Analyses pushover et temporelles
- Export PDF de note de calcul
- Packaging Windows finalisé

## Limites actuelles des plaques

Les plaques rectangulaires/quadrangulaires planes sont supportees de maniere
experimentale via un maillage quadrangulaire regulier. L'utilisateur manipule
une plaque macro a 4 noeuds ; avant calcul OpenSeesPy, HEXA genere un maillage
interne invisible dans l'arbre principal du modele. Le mode de maillage par
defaut est automatique : HEXA calcule une taille d'element cible selon les
dimensions de la plaque, son epaisseur et la formulation choisie. Un mode
utilisateur permet de figer explicitement `mesh_nx` et `mesh_ny`. Les ouvertures,
tremies, contours quelconques et maillages triangulaires ne sont pas pris en
charge a ce stade. Les cartes de contours plaque s'appuient sur ce maillage de
calcul interne, regroupe par plaque macro pour le post-traitement.

## Architecture

L'application évolue progressivement vers une architecture modulaire hybride :

- `gui/` : interface PySide6, vue 3D PyVista, widgets et dialogues
- `core/model_data.py` : modèle métier utilisateur et persistance historique
- `core/application/` : ports, DTOs, cas d'usage et façade applicative
- `core/adapters/` : adaptateurs techniques, notamment solveurs et maillage
- `core/plugins/` : découverte de plugins installables par manifeste
- `core/solvers/` : backends historiques et compatibilité multi-solveur

La règle principale est que le domaine et les cas d'usage ne dépendent pas de
PySide6, OpenSeesPy, PyNite, SQLite ou Matplotlib. La GUI passe progressivement
par `ApplicationServices`, qui orchestre les ports applicatifs.

Les solveurs PyNite et OpenSeesPy sont exposés comme plugins/adaptateurs internes.
Le même système prépare aussi des plugins non-solveurs : par exemple un module
externe d'assemblages acier peut déclarer l'extension `connections.design`.

## Prérequis

- **Windows 10 1809+ ou Windows 11** pour l'exécutable Windows publié
- **Python 3.12** recommandé
- `PySide6 >= 6.6`
- `pyvista` et `pyvistaqt` pour la visualisation 3D
- `PyNiteFEA` pour le moteur par défaut
- `OpenSeesPy >= 3.5` uniquement si vous souhaitez utiliser ce backend

## Installation

```bash
git clone https://github.com/chakibhenaoui/HEXA_Structures.git
cd HEXA_Structures

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1  # PowerShell
.venv\Scripts\activate.bat    # CMD
# source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
python main.py
```

## Activer OpenSeesPy (optionnel)

OpenSeesPy n'est pas installé par défaut et n'est pas redistribué dans l'exécutable Windows. Si vous souhaitez utiliser ce moteur, installez-le vous-même :

```bash
pip install openseespy
```

L'exécutable Windows le détecte ensuite dans les installations Python compatibles de la machine, y compris l'installation utilisateur Python 3.12 et le `.venv` du projet pendant les tests de build. Si OpenSeesPy est installé dans un dossier personnalisé, définissez `HEXA_PYTHON_SITE_PACKAGES` vers le dossier `site-packages` concerné.

## Construire l'exécutable Windows

```bash
pip install pyinstaller
build.bat
```

Sortie attendue :

```text
dist\HEXA Structures\HEXA Structures.exe
```

Compatibilité : l'exécutable Windows publié cible Windows 10/11. Windows 7 n'est pas supporté par le build Python 3.12 / Qt 6 ; l'erreur `api-ms-win-core-path-l1-1-0.dll` indique cette limite de plateforme, pas une dépendance HEXA manquante.

L'exécutable produit n'embarque pas OpenSeesPy. Si l'utilisateur final souhaite ce solveur, il doit l'installer séparément sur sa machine.

## Structure du projet

```text
.
|-- main.py
|-- config/
|   |-- settings.py
|   `-- eurocodes.py
|-- core/
|   |-- application/
|   |   |-- ports/
|   |   `-- use_cases/
|   |-- adapters/
|   |   |-- meshing/
|   |   `-- solvers/
|   |-- plugins/
|   |-- solvers/
|   |-- model_data.py
|   |-- boundary_conditions.py
|   |-- loads.py
|   |-- materials.py
|   |-- sections.py
|   |-- analysis.py
|   |-- results.py
|   `-- checks/
|-- gui/
|   |-- main_window.py
|   |-- widgets/
|   `-- dialogs/
|-- utils/
|   `-- units.py
|-- tests/
|-- resources/
|-- build.bat
|-- hexa_structures.spec
|-- CONVENTIONS.md
`-- README.md
```

## Unités internes

Le système interne utilise **kN, m, kPa**. Les conversions depuis et vers d'autres unités (`mm`, `MPa`, `cm2`, etc.) sont gérées dans `utils/units.py`.

## Normes intégrées

| Norme | Contenu | Statut |
|---|---|---|
| NF EN 1990 (EC0) | Combinaisons de charges, coefficients psi | Constantes |
| NF EN 1991 (EC1) | Charges d'exploitation, vent (AN FR), neige (AN FR) | Constantes |
| NF EN 1992 (EC2) | Matériaux béton, classes C20 à C50, armatures B500 | Matériaux |
| NF EN 1993 (EC3) | Acier S235 à S460, profils IPE/HEA/HEB/HEM, UPN/UPE, tubes CHS/SHS/RHS et cornières | Matériaux + catalogue |
| NF EN 1998 (EC8) | Spectres de réponse, zonage France, classes de sol | Constantes |

## Tests

Exécuter la suite principale :

```bash
pytest -q
```

Notes utiles :

- `requirements.txt` couvre les dépendances de base de l'application et des tests courants
- certains tests de rendu nécessitent `matplotlib`
- les tests d'architecture couvrent les ports applicatifs, la découverte de plugins et le host `connections.design`
- les comparaisons avancées avec `opsvis` demandent une installation complémentaire :

```bash
pip install opsvis
```

## Documentation complémentaire

- `CONVENTIONS.md` : conventions de code et de contribution
- `PROGRESS.md` : suivi d'avancément
- `PROJECT_PLAN.md` : plan de projet
- `RELEASE_NOTES_0.1.0.md` : notes de release de la version 0.1.0
- `IMPLEMENTATION_MULTI_SOLVEUR.md` : notes historiques et état actuel de l'architecture multi-solveur/plugin

## Contribuer

Les contributions sont les bienvenues. Avant de proposer un changement, consultez `CONVENTIONS.md` pour respecter les conventions du projet.

## Licence

Ce projet est distribué sous licence **LGPL-3.0-only**. Voir [LICENSE](LICENSE) pour le texte LGPL et [COPYING](COPYING) pour le texte GNU GPL v3 référencé par cette licence.

## Avertissement sur l'utilisation

HEXA Structures est un logiciel de modélisation et d'aide au calcul en développement actif. Les résultats produits par le logiciel, y compris les déplacements, réactions, efforts internes, diagrammes, enveloppes et futures vérifications normatives, ne constituent pas à eux seuls une note de calcul certifiée ni une validation réglementaire d'un ouvrage.

Toute utilisation pour la conception, la vérification, la modification ou l'exécution d'une structure réelle doit être contrôlée, validée et signée par un ingénieur structure qualifié, avec vérification indépendante des hypothèses, charges, combinaisons, unités, conventions de signe, paramètres de calcul, modèles numériques et normes applicables. L'utilisateur reste seul responsable de l'interprétation des résultats et de leur usage dans un contexte professionnel ou réglementaire.

Dans les limites autorisées par la loi, les auteurs et contributeurs du projet ne peuvent être tenus responsables des dommages, erreurs de conception, pertes d'exploitation ou conséquences directes ou indirectes résultant de l'utilisation du logiciel ou de ses résultats.

---

Projet en développement actif.
