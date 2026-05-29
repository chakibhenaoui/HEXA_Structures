# Changelog

## 0.1.0 - Build Windows i18n

Date : 2026-05-29

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
