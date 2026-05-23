# HEXA Structures - Plan de projet

> Application Python / PySide6 de calcul de structures, orientee usage bureau d'etudes, avec PyNite comme moteur par défaut, OpenSeesPy comme moteur optionnel avancé et une architecture plugin progressive.

---

## 1. Vision

### 1.1 Objectif

Construire un logiciel de calcul de structures exploitable progressivement en pratique :

- modélisation graphique claire,
- calculs fiables,
- résultats lisibles,
- conventions de signe explicites,
- workflow proche des habitudes métier structure,
- evolution future vers les vérifications Eurocodes et les exports professionnels.
- extensibilite par plugins installables pour les solveurs et modules metier.

### 1.2 Positionnement

HEXA Structures vise un compromis entre :

- la simplicite d'un outil graphique,
- la transparence d'un projet Python open source,
- la puissance de moteurs de calcul existants,
- une ergonomie adaptée aux portiques, poutres, poteaux et structures courantes du BTP.

Le logiciel doit d'abord devenir fonctionnel et cohérent. Les raffinements avancés viendront ensuite.

---

## 2. Decisions produit confirmees

### 2.1 Moteurs de calcul

Decision actuelle :

- PyNite est le moteur par défaut.
- OpenSeesPy reste disponible comme moteur optionnel.
- OpenSeesPy ne doit pas être obligatoire à l'installation de base.
- L'utilisateur pourra choisir OpenSeesPy s'il l'installe lui-même.
- L'executable Windows ne l'embarque pas, mais détecté une installation Python externe compatible.
- Le build public Python 3.12 / Qt 6 cible Windows 10/11 ; Windows 7 demanderait une branche legacy separee.

Raison :

- PyNite est plus simple à distribuer et mieux adapté au socle linéaire courant.
- OpenSeesPy reste tres interessant pour les analyses avancées et la validation.
- Le logiciel doit garder une architecture multi-solveur propre.
- Les solveurs sont exposes progressivement comme plugins internes via des adaptateurs.

### 2.2 Plugins metier

Decision actuelle :

- Les plugins ne sont pas reserves aux solveurs.
- Un plugin peut declarer un `kind` libre : `solver`, `design_module`, `exporter`, `reporting`, etc.
- Un plugin declare ses points d'extension avec `extension_points`.
- Le premier point d'extension metier reserve est `connections.design` pour les futurs calculs d'assemblages.
- Le chargement de code externe est opt-in : la decouverte lit les manifestes sans importer le plugin.

Raison :

- permettre l'ajout de solveurs sans modifier la GUI ;
- permettre des modules metier separes, par exemple les assemblages acier ;
- garder le noyau HEXA agile, testable et stable.

### 2.3 Strategie de calcul

Principe :

- calculer avec PyNite tout ce qui est supporte proprement,
- basculer vers OpenSeesPy pour ce qui demande des fonctions avancées,
- garder la même interface utilisateur quel que soit le moteur.

Priorite court terme :

- statique linéaire,
- poids propre automatique,
- cas de charge,
- combinaisons,
- résultats tabulaires,
- diagrammes N/V/T/M.

Non prioritaire immediat :

- P-Delta,
- analyse non linéaire,
- sismique avancé,
- coques/dalles/voiles.

---

## 3. Etat reel au 23 mai 2026

Le projet est au stade base applicative fonctionnelle en consolidation.

Fonctions déjà utilisables :

- création et édition de projet,
- gestion des matériaux,
- gestion des sections,
- gestion des nœuds et barres,
- dessin graphique sur grille,
- accrochage aux intersections,
- choix de section au dessin,
- sélection graphique additive,
- suppression de sélection,
- appuis et conditions aux limites,
- cas de charge et combinaisons,
- poids propre automatique,
- analyse avec moteur sélectionnable,
- résultats tabulaires,
- diagrammes 2D par plan/file,
- diagrammes mono-barre en repère local depuis le clic droit 3D,
- choix de cas/combinaison dans les résultats et diagrammes,
- stabilisation de la vue 3D pendant les éditions non géométriques,
- système caméra 3D stabilisé pour les passages 2D/3D,
- menu contextuel 3D sur les barres : modifier, supprimer, copier, propriétés, diagrammes,
- fenêtre de propriétés détaillée mono-barre orientee vérification métier,
- organisation plus claire des menus de modélisation et de charges,
- rendu extrudé plus lisible pour les profilés acier en I.
- architecture `core/application` avec ports et cas d'usage ;
- adaptateurs solveurs PyNite/OpenSeesPy dans `core/adapters/solvers` ;
- decouverte de plugins par manifestes `plugin.json` et `hexa-plugin.json` ;
- loader `ImportlibPluginLoader` optionnel pour charger explicitement un plugin externe ;
- host applicatif `connections.design` pour les futurs plugins d'assemblages ;
- tests d'architecture et de non-regression couvrant ces chemins.

Problemes principaux en cours de consolidation :

- harmonisation complète des diagrammes PyNite/OpenSeesPy,
- robustesse des conventions de signe,
- synthèse résultats encore absente,
- export CSV/PDF encore a lancer,
- contrôles de cohérence et avertissements utilisateur avant usage professionnel a renforcer,
- affectation et édition par lot depuis la sélection a consolider.

---

## 4. Architecture cible

### 4.1 Couches

1. GUI PySide6
   Interface utilisateur, modelisation, edition, lancement d'analyse, lecture des resultats.

2. Domaine metier
   Donnees structurelles, materiaux, sections, appuis, charges, combinaisons, plaques utilisateur.

3. Application
   Ports, DTOs, cas d'usage et facade `ApplicationServices`.

4. Adaptateurs techniques
   Solveurs, maillage, persistance, exports et futurs connecteurs.

5. Plugins
   Solveurs installables, modules metier et points d'extension comme `connections.design`.

### 4.2 Regle de separation

La GUI ne doit pas parler directement a PyNite, OpenSeesPy, SQLite ou Matplotlib.

Les solveurs et modules techniques doivent rester derriere des ports :

- `core/application/ports/solver_port.py`
- `core/application/ports/mesh_generator_port.py`
- `core/application/ports/plugin_loader_port.py`
- `core/application/ports/connection_design_port.py`
- adaptateurs dans `core/adapters/`

But :

- garder une GUI stable,
- pouvoir changer de moteur sans casser l'interface,
- tester PyNite et OpenSeesPy avec les mêmes cas,
- préparer les exports et checks Eurocodes sur une structure de résultats commune.
- permettre des plugins installables sans refonte de la GUI.

---

## 5. Structure fonctionnelle

### 5.1 Noyau métier

- `core/model_data.py` : modèle central et persistance.
- `core/materials.py` : matériaux.
- `core/sections.py` : sections.
- `core/boundary_conditions.py` : appuis.
- `core/loads.py` : charges et combinaisons.
- `core/self_weight.py` : poids propre automatique.
- `core/results.py` : résultats communs.
- `core/application/` : ports, DTOs, cas d'usage.
- `core/adapters/` : adaptateurs solveurs et maillage.
- `core/plugins/` : manifestes, registry, loaders.
- `core/solvers/` : backends historiques et compatibilite.

### 5.2 Interface graphique

- `gui/main_window.py` : orchestration generale.
- `gui/widgets/model_view.py` : vue graphique PyVista.
- `gui/widgets/plane_editor_view.py` : vues planes.
- `gui/widgets/tree_model.py` : arbre du modèle.
- `gui/widgets/property_panel.py` : propriétés.
- `gui/widgets/results_panel.py` : tableaux de résultats.
- `gui/widgets/diagram_renderer.py` : rendu diagrammes 2D.
- `gui/widgets/diagram_window.py` : fenêtre diagrammes.
- `gui/dialogs/*` : dialogues métier.

### 5.3 Résultats

Résultats a presenter de maniere unifiee :

- déplacements,
- réactions,
- efforts internes,
- diagrammes,
- enveloppes,
- synthèse,
- exports.

---

## 6. Roadmap

| Sprint | Theme | Statut | Commentaire |
|---|---|---|---|
| S1 | Architecture et fondations | Terminé | Projet, settings, unités, SQLite. |
| S2 | Noyau OpenSees historique | Terminé | Builder, analyse, extraction. |
| S3 | Interface graphique de base | Terminé | Fenêtre, arbre, propriétés, dialogues. |
| S4 | Charges, appuis, combinaisons | Bien avancé | Gestionnaires GUI, poids propre automatique, édition et affectation a consolider. |
| S5 | Résultats et post-traitement | En cours avancé | Tableaux, diagrammes, cas/combis, signes, diagrammes locaux mono-barre ; synthèse et export CSV a finir. |
| S6 | Multi-solveur | En cours | PyNite par défaut, OpenSeesPy optionnel, parite en validation. |
| S7 | Éléments surfaciques | En cours | Plaques macro quadrangulaires, maillage interne et mapping résultats en place ; limites à documenter. |
| S8 | Vérifications EC2/EC3 | À faire | À lancer après stabilisation des résultats et des plugins métier. |
| S9 | Sismique | À faire | Modal spectral plus tard. |
| S10 | Exports et packaging | À faire | CSV/PDF/DXF, installateur Windows. |
| S11 | Modèleur graphique | En cours avancé | Grille, dessin, sélection, menu contextuel 3D, double vue, caméra et lisibilité en consolidation. |
| S12 | Productivite | À faire | Copier, deplacer, undo/redo, import DXF. |
| S13 | Architecture plugin | En cours | Ports/adaptateurs, manifestes, loader opt-in, host `connections.design`. |

---

## 7. Priorites produit immediates

### 7.1 Résultats utilisateur

Objectif : rendre la lecture des résultats fiable et agréable.

À faire :

1. Ajouter un onglet Synthèse.
2. Afficher les maxima/minima importants avec le cas/combinaison.
3. Ajouter l'export CSV des tableaux.
4. Harmoniser l'affichage entre PyNite et OpenSeesPy.
5. Ajouter des messages clairs quand un résultat dépend du moteur.

### 7.2 Diagrammes

Objectif : obtenir un rendu lisible, symétrique et cohérent avec la convention interne.

À faire :

1. Verrouiller les signes N/V/T/M.
2. Conserver l'affichage symétrique pour les portiques plans.
3. Afficher zero au lieu des residus numériques.
4. Stabiliser les diagrammes mono-barre en repère local.
5. Documenter la convention utilisée.
6. Ajouter des tests comparatifs PyNite / OpenSeesPy / references.

### 7.3 Modelisation graphique

Objectif : rendre la sélection productive.

À faire :

1. Affectation de sections à la sélection.
2. Affectation d'appuis à la sélection.
3. Affectation de charges à la sélection.
4. Edition par lot.
5. Finaliser les actions contextuelles sur les objets 3D.
6. Ameliorer les raccourcis clavier et la fluidité des refresh.

---

## 8. Priorites techniques

### 8.1 Architecture multi-solveur

Actions :

- garder les résultats dans un format commun,
- isoler les conversions specifiques PyNite,
- isoler les conversions specifiques OpenSeesPy,
- maintenir une suite de tests de parite.

### 8.1 bis Architecture plugin

Actions :

- garder les manifestes de plugins generiques (`kind`, `extension_points`, `capabilities`, `tags`) ;
- ne jamais executer de code externe pendant la simple decouverte ;
- charger les plugins uniquement via un loader explicite ;
- brancher progressivement les points d'extension applicatifs ;
- premier point actif : `connections.design` pour les assemblages.

### 8.2 Poids propre

état :

- le cas automatique existe,
- le poids propre est calculé à partir des sections et matériaux,
- l'utilisateur peut lancer une analyse avec seulement le poids propre.

A consolider :

- vérifier toutes les orientations d'éléments,
- vérifier les unités,
- afficher clairement le statut du cas poids propre dans l'interface.

### 8.3 Tests

Maintenir au minimum :

- tests modèle de données,
- tests charges/combinaisons,
- tests poids propre,
- tests PyNite,
- tests OpenSeesPy quand disponible,
- tests diagrammes.

---

## 9. Preparation de la prochaine release

Objectif : stabiliser le socle calcul/résultats/3D avant une nouvelle livraison publique.

### 9.1 Bloqueurs release P0

Actions a traiter en debut de prochaine session :

1. Corriger les échecs de parite OpenSeesPy/OpsVis dans `tests/test_results_vs_opsvis.py`.
2. Vérifier la cohérence des efforts locaux, longueurs d'éléments et diagrammes pour les barres horizontales, inclinées et verticales.
3. Valider les diagrammes mono-barre dans le repère local sans projection globale.
4. Rejouer les tests plaques : iso-valeurs, isolignes, charge ponctuelle, charge surfacique et plaque maillagee.
5. Lancer la suite complète `pytest -q` avant tout gel release.

### 9.2 Qualite code avant release

Actions :

1. Corriger le lint global `ruff check core gui tests`.
2. Nettoyer les imports inutilises et noms ambigus dans les tests.
3. Reduire les `except Exception` trop larges sur les chemins critiques calcul/rendu.
4. Ajouter des messages de log utiles quand un calcul, un rendu ou une extraction de résultats échoue.
5. Documenter les limites connues dans le README et les notes de version.

### 9.3 Refactor cible pour reduire la dette

Les fichiers les plus sensibles a decomposer progressivement :

- `gui/main_window.py` : orchestration generale trop volumineuse.
- `gui/widgets/model_view.py` : caméra, picking, scène 3D et interactions mélangées.
- `gui/widgets/diagram_renderer.py` : calcul des données et rendu Matplotlib encore trop couples.

Extractions recommandees :

1. `SélectionController` pour la sélection, le clic droit et les actions contextuelles.
2. `DiagramController` pour les fenêtres de diagrammes et le choix cas/composante.
3. `ResultController` pour la disponibilité des résultats, combinaisons et messages utilisateur.
4. `View3DController` pour les transitions 2D/3D, caméra et refresh.
5. `SceneCache` / `RenderScheduler` pour limiter les reconstructions de scène.

### 9.4 Optimisation calcul et rendu

Actions :

1. Mettre en cache la géométrie 3D statique et ne mettre à jour que les overlays de sélection/résultats.
2. Debouncer les refresh successifs lors des passages 2D/3D et des modifications non géométriques.
3. Cacher les diagrammes par cas/combinaison, element et composante.
4. Rendre la subdivision des plaques adaptative selon la taille du modèle.
5. Ajouter une progression claire et une possibilite d'annulation sur les calculs/rendus longs.
6. éviter les reconstructions complètes après édition de propriétés qui ne changent pas la topologie.

### 9.5 Fluidité d'usage

Actions :

1. Rendre la transition 2D/3D déterministe : orientation, cible et zoom doivent être prets avant affichage.
2. Unifier les menus contextuels 3D pour barres, nœuds, plaques, appuis et charges.
3. Garder un seul panneau de propriétés stable, sans duplication de widgets.
4. Ajouter des raccourcis clavier pour les actions fréquentes : supprimer, copier, modifier, zoom sélection.
5. Ajouter un panneau de statut calcul : moteur, cas, combinaison, avertissements et limites.
6. Préparer un mode "Release check" : unités, appuis, charges, combinaisons, résultats disponibles, disclaimer.

### 9.6 Checklist de gel release

Avant tag :

1. `pytest -q` vert.
2. `ruff check core gui tests` vert.
3. Tests manuels sur un portique, une poutre inclinée, une dalle simple et un modèle mixte.
4. Verification du README, disclaimer, plan de projet et changelog.
5. Build Windows teste sur une installation propre.
6. Notes de version avec limites connues et responsabilite utilisateur.

### 9.7 Progress au 23 mai 2026

Fait :

1. Les tests de parite OpenSeesPy/OpsVis sont corriges et forcent explicitement le moteur OpenSeesPy.
2. La chaine résultats -> diagrammes -> rendu est couverte par une passe dédiée :
   - barre horizontale,
   - barre inclinée,
   - barre verticale,
   - barre spatiale 3D,
   - plaque carree maillee,
   - plaque avec charge ponctuelle,
   - plaque avec charge surfacique.
3. Les diagrammes mono-barre sont verifies en repère local avec la vraie longueur 3D.
4. Les cartes de plaques sont verifiees jusqu'au rendu des champs et isolignes.
5. Le nettoyage `ruff check core gui tests` est termine.
6. Le panneau Informations est corrige :
   - suppression robuste des doublons d'onglets,
   - remplacement fiable des placeholders après reparentage,
   - dernière colonne des tableaux de résultats non étirée.
7. Le titre de fenêtre est corrigé après ouverture/enregistrement d'un fichier.
8. La version applicative est preparee en `0.1.0`.
9. Les notes de release `RELEASE_NOTES_0.1.0.md` sont ajoutees.
10. La détection d'OpenSeesPy externe est corrigee sans embarquer le solveur dans le bundle.
11. Validation courante : `pytest -q` OK avec 460 tests passes.
12. Build Windows relance avec succes et executable teste au démarrage.
13. Compatibilité Windows clarifiée après test VM : Windows 10/11 cible, Windows 7 hors support.
14. Architecture applicative progressive ajoutee : ports, use cases, facade `ApplicationServices`.
15. Registry solveurs de type plugin interne ajoute pour PyNite et OpenSeesPy.
16. Decouverte de plugins installes par manifeste sans execution de code externe.
17. Loader `ImportlibPluginLoader` opt-in ajoute pour les plugins explicitement actives.
18. Port et host `connections.design` ajoutes pour les futurs modules d'assemblages.

Reste à faire avant release :

1. Reduire les `except Exception` trop larges sur les chemins critiques calcul/rendu.
2. Ajouter des logs contextualises pour les échecs de calcul, extraction de résultats et rendu.
3. Implementer la synthèse résultats.
4. Implementer l'export CSV simple.
5. Faire les tests manuels release sur portique, poutre inclinée, dalle simple et modèle mixte.
6. Tester le build Windows sur une installation propre.

---

## 10. Ordre de travail recommande

### Étape 1 - Architecture plugin utilisable

- Ajouter un exemple minimal de plugin externe `connections.ec3`.
- Documenter le format de manifeste.
- Ajouter une petite vue/commande de diagnostic des plugins installes.
- Garder le chargement externe opt-in.

### Étape 2 - Résultats propres

- Onglet Synthèse.
- Export CSV.
- Nettoyage tableaux.
- Cas/combinaisons partout.

### Étape 3 - Affectation par lot

- Sections sur sélection.
- Appuis sur sélection.
- Charges sur sélection.
- Edition multiple.

### Étape 4 - Validation calcul

- Cas analytiques simples.
- Comparaison PyNite / OpenSeesPy.
- Comparaison avec references type OpsVis.
- Documentation des conventions.

### Étape 5 - Premiers checks métier

- EC2 flexion simple.
- EC2 effort normal/flexion simplifie.
- EC3 contraintes simples.
- Ratios d'utilisation dans l'interface.

### Étape 6 - Exports

- CSV résultats.
- PDF rapport simple.
- Images de diagrammes.
- DXF/import plus tard.

---

## 11. Ce qui est volontairement reporte

- P-Delta.
- Non linéaire.
- Sismique complet EC8.
- Coques/dalles/voiles.
- Maillage avancé.
- Packaging final.

Ces sujets sont importants, mais ils doivent venir après un flux poutres/poteaux fiable.

---

## 12. Définition du prochain jalon

Jalon propose : "Résultats V1 utilisables".

Le jalon est atteint quand :

- l'utilisateur lance PyNite par défaut,
- le poids propre fonctionne sans saisie manuelle,
- les cas et combinaisons sont sélectionnables,
- les tableaux affichent les bonnes données,
- les diagrammes affichent les bonnes conventions,
- les diagrammes mono-barre affichent les résultats dans le repère local,
- une synthèse donne les valeurs critiques,
- un export CSV simple est disponible.

Etat au 23 mai 2026 :

- PyNite par défaut : en place,
- poids propre automatique : en place,
- cas et combinaisons sélectionnables : en place,
- tableaux et diagrammes : en place, avec couverture de non-régression renforcée,
- diagrammes mono-barre en repère local : en place,
- menu contextuel 3D barre : en place,
- cartes de résultats plaques : en place et testées sur charge ponctuelle et charge surfacique,
- panneau Informations : corrige pour éviter les doublons d'onglets et les colonnes étirées,
- titre de fenêtre : corrigé après ouverture/enregistrement,
- version cible : 0.1.0,
- lint global `ruff` : vert,
- suite de tests : `pytest -q` vert avec 460 tests passes,
- architecture plugin : en place pour les solveurs internes et le point `connections.design`,
- plugin assemblages : contrat applicatif pret, implementation externe a creer,
- synthèse résultats : à faire,
- export CSV simple : à faire.

---

## 13. Licence

Projet open source sous licence LGPL-3.0-only.

---

*Dernière mise à jour : 23 mai 2026*
