# Etat d'avancement par rapport au planning

> Etat consolide le 1er juillet 2026 a partir de `PROJECT_PLAN.md`,
> `PROGRESS.md`, `CHANGELOG.md`, `README.md` et d'une validation locale.

## Synthese executive

Le projet HEXA Structures est au stade **application fonctionnelle en
consolidation avancee**. Le socle metier, la GUI, la persistence SQLite, le
multi-solveur, les plaques macro, l'internationalisation, l'architecture plugin
et le Section Builder sont deja en place.

Par rapport au planning, l'avancement est globalement bon sur les fondations et
les chantiers techniques structurants. Les principaux retards concernent les
fonctions de finition utilisateur attendues pour le jalon **"Resultats V1
utilisables"** : export PDF general, validations metier manuelles avant release
et consolidation ergonomique des tableaux de resultats.

Validation locale du 1er juillet 2026 :

```text
.\.venv\Scripts\python.exe -m pytest -q
594 passed in 61.35s
```

## Reference planning utilisee

Le depot ne contient pas de planning calendaire detaille avec dates de debut et
de fin par tache. La comparaison est donc faite par rapport a :

- la roadmap par sprints S1 a S14 de `PROJECT_PLAN.md` ;
- le jalon propose **"Resultats V1 utilisables"** ;
- les priorites immediates produit et techniques ;
- le suivi d'avancement du 28 juin 2026.

## Avancement par sprint

| Sprint | Theme | Etat planning | Etat constate au 1er juillet 2026 | Ecart / commentaire |
|---|---|---:|---|---|
| S1 | Architecture et fondations | Termine | Termine | Socle projet, settings, unites, SQLite et architecture applicative en place. |
| S2 | Noyau OpenSees historique | Termine | Termine | Backend historique conserve et OpenSeesPy reste optionnel. |
| S3 | Interface graphique de base | Termine | Termine | Fenetre principale, arbre modele, vues, proprietes et dialogues presents. |
| S4 | Charges, appuis, combinaisons | Bien avance | Bien avance | Fonctionnel, mais affectation/edition par lot depuis selection encore a consolider. |
| S5 | Resultats et post-traitement | En cours avance | En cours avance | Tableaux, diagrammes, plaques, synthese, enveloppes completes et export CSV sont presents ; export PDF et validation ergonomique restent prioritaires. |
| S6 | Multi-solveur | En cours | Tres avance | PyNite par defaut, OpenSeesPy optionnel, adaptateurs et registry plugins internes en place ; poursuivre la parite et la validation. |
| S7 | Elements surfaciques | En cours | En cours avance / experimental | Plaques macro, maillage interne, charges surfaciques et cartes resultats disponibles ; cisaillement, limites et convergence a stabiliser. |
| S8 | Verifications EC2/EC3 | A faire | A faire | Non lance fonctionnellement ; quelques bases Eurocodes et catalogues sont presentes. |
| S9 | Sismique | A faire | A faire | EC8 documente dans les constantes, mais analyse sismique complete repoussee. |
| S10 | Exports et packaging | A faire | Partiel | Packaging Windows, i18n et export CSV des tableaux sont en place ; export PDF general des resultats reste a faire. |
| S11 | Modeleur graphique | En cours avance | En cours avance | Vue 3D, selection, grille, menus contextuels et sections extrudees en place ; productivite a renforcer. |
| S12 | Productivite | A faire | A faire / partiel | Copier, deplacer, undo/redo, import DXF et edition multiple restent ouverts. |
| S13 | Architecture plugin | En cours | Tres avance | Manifestes, decouverte sans execution, loader opt-in et point `connections.design` en place ; exemple externe a creer. |
| S14 | Section Builder | En cours avance | Tres avance | Contours, trous, profils, maillage, contraintes, note de calcul et extrusion 3D en place ; DXF, sections composees et materiaux multiples restent a faire. |

## Jalon "Resultats V1 utilisables"

| Critere du jalon | Etat | Commentaire |
|---|---|---|
| PyNite par defaut | Fait | Moteur principal confirme. |
| Poids propre automatique | Fait | Disponible et teste dans le flux courant. |
| Cas et combinaisons selectionnables | Fait | Presents dans les resultats et diagrammes. |
| Tableaux de resultats | Fait / a consolider | Disponibles, mais lecture multi-cas et consolidation UX a poursuivre. |
| Diagrammes avec conventions coherentes | Fait / a surveiller | Couverture de tests renforcee ; continuer les comparaisons PyNite/OpenSeesPy. |
| Diagrammes mono-barre en repere local | Fait | Valides dans le suivi projet. |
| Synthese des valeurs critiques | Fait | Onglet Synthese multi-cas avec maxima/minima et cas/combinaisons associes. |
| Export CSV simple | Fait | Export de l'onglet actif des tableaux, avec filtre courant. |

Conclusion : le jalon est **majoritairement atteint techniquement**, mais pas
encore clos cote release car l'export PDF general, les tests manuels metier et
la validation ergonomique restent a terminer.

## Avancees recentes au-dela du plan du 19 juin

- Passage de la validation globale documentee de 423 tests a 590 tests passes
  localement.
- Section Builder fortement enrichi : trous, import de profils, maillage,
  contraintes elastiques, enveloppes min/max et note de calcul.
- Catalogue acier enrichi avec plus de 200 profiles europeens courants.
- Sections parametriques et personnalisees extrudees dans la vue 3D.
- Documentation README illustree avec capture de l'interface 3D.
- Internationalisation francaise et anglaise consolidee.
- Architecture plugin generalisee avec `kind`, `extension_points`,
  `capabilities`, `tags` et point `connections.design`.

## Points de retard ou risques

1. **Post-traitement resultats incomplet**
   - export PDF general non livre ;
   - validation ergonomique des tableaux et syntheses a poursuivre ;
   - export CSV simple disponible, mais export de note complete a preparer.

2. **Validation metier avant release**
   - tests automatiques verts, mais tests manuels release encore a faire sur
     portique, poutre inclinee, dalle simple et modele mixte ;
   - build Windows a retester sur installation propre.

3. **Plaques encore experimentales**
   - cisaillement et formulation a stabiliser ;
   - convergence adaptative non disponible ;
   - limites a garder visibles dans la documentation.

4. **Productivite de modelisation**
   - affectation par lot, edition multiple, undo/redo, copier/deplacer et import
     DXF restent en attente.

5. **Fonctions metier de verification**
   - EC2/EC3/EC8 encore hors jalon court terme ;
   - plugin externe `connections.ec3` non encore fourni.

## Priorites recommandees

### Priorite 1 - Cloturer le jalon Resultats V1

1. Fait - Ajouter l'onglet de synthese des resultats.
2. Fait - Afficher les maxima/minima avec cas ou combinaison associe.
3. Fait - Ajouter l'export CSV simple des tableaux.
4. Fait - Consolider les enveloppes.
5. Fait - Documenter explicitement les conventions de signe visibles par l'utilisateur.

### Priorite 2 - Preparer une release propre

1. Executer les tests manuels release.
2. Tester le build Windows sur une installation propre.
3. Mettre a jour README, changelog et notes de version avec les limites connues.
4. Ajouter des logs contextualises sur calcul, extraction de resultats et rendu.

### Priorite 3 - Ameliorer la productivite

1. Affectation par lot des sections, appuis et charges.
2. Edition multiple depuis selection.
3. Copier/deplacer et raccourcis clavier.
4. Import DXF, d'abord pour le Section Builder puis pour le modele.

## Position globale

Le projet est **en avance sur l'architecture** et a rattrape une partie
importante du retard sur les resultats utilisateur. La base technique est
solide et validee par une suite de tests verte. La prochaine decision
structurante consiste a concentrer l'effort sur un petit nombre de livrables
visibles : export PDF general, tests manuels metier, build propre et validation
release.
