# Documentation LaTeX de HEXA Structures

Ce dossier contient la documentation utilisateur modulaire du logiciel.

La documentation LaTeX doit rester alignée avec les documents racine :

- `README.md` pour la présentation utilisateur ;
- `PROJECT_PLAN.md` pour la feuille de route ;
- `PROGRESS.md` pour l'état courant ;
- `IMPLEMENTATION_MULTI_SOLVEUR.md` pour les choix multi-solveur et plugins.

## Compiler

Depuis `docs/latex` :

```powershell
latexmk -pdf main.tex
```

`latexmk` nécessite Perl avec MiKTeX. Si Perl n'est pas installé, utiliser la
méthode `pdflatex` ci-dessous.

Alternative :

```powershell
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Ajouter du contenu

- Ajouter les captures dans `figures/`.
- Ajouter ou modifier les chapitres dans `chapters/`.
- Ajouter les nouveaux chapitres dans `main.tex` avec `\input{chapters/nom}`.
- Utiliser `\todoDoc{...}` pour marquer les sections à enrichir plus tard.
- Documenter les plugins comme des extensions installables, pas seulement comme
  des solveurs. Le premier point d'extension métier est `connections.design`.

## Structure

Le document est volontairement découpé en petits fichiers pour faciliter les
améliorations progressives.

Etat courant à mentionner lors de la prochaine passe de rédaction :

- architecture applicative `core/application` avec ports et cas d'usage ;
- adaptateurs techniques dans `core/adapters` ;
- découverte de plugins par manifestes ;
- host applicatif pour les futurs plugins d'assemblages.
