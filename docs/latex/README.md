# Documentation LaTeX de HEXA Structures

Ce dossier contient la documentation utilisateur modulaire du logiciel.

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

## Structure

Le document est volontairement découpé en petits fichiers pour faciliter les
améliorations progressives.
