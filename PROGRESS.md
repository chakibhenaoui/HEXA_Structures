# HEXA Structures - Suivi d'avancement

> Base de suivi redemarree avec la version 0.1.0.

---

## Etat actuel

| Info | Valeur |
|---|---|
| Version applicative | 0.1.0 |
| Date de base | 20 mai 2026 |
| Moteur principal | PyNite |
| Moteur avance optionnel | OpenSeesPy |
| Etat global | Base publique initiale propre, avec modelisation GUI, persistance SQLite, analyse statique, diagrammes, plaques macro et maillage automatique. |

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

---

## A faire ensuite

1. Ajouter une convergence adaptative optionnelle pour le maillage automatique.
2. Consolider les resultats de cisaillement plaques selon la formulation.
3. Ameliorer les exports CSV/PDF.
4. Poursuivre les validations analytiques et comparatives.
5. Ajouter progressivement les verifications EC2/EC3.
