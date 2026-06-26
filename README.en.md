# HEXA Structures

[Version française](README.md)

> Open-source structural analysis application built with **PyNite** as the default solver, **OpenSeesPy** as an optional advanced solver, and **PySide6** for the desktop UI.

## Overview

HEXA Structures is a desktop modeling and analysis tool aimed at structural engineers. The project combines:

- **PyNite** as the default analysis engine
- **OpenSeesPy** as an optional advanced engine
- **PySide6** for the graphical user interface
- **PyVista / pyvistaqt** for interactive 3D visualization
- native integration of **Eurocodes (EC0 to EC8)** with the **French National Annexes**
- a progressive ports/adapters application architecture with installable plugin support

## Project Status

The project has moved beyond the prototype stage. The current codebase already includes:

- a multi-solver analysis core
- a `core/application/` layer with ports, use cases, DTOs, and an application facade
- a `core/adapters/` layer for solver and meshing adapters
- a `core/plugins/` layer for manifest-based plugin discovery without executing code by default
- a structured PySide6 interface
- management of materials, sections, boundary conditions, loads, and combinations
- result extraction and 2D diagram rendering for supported workflows
- an interactive 3D view connected to the model
- an integrated Section Builder for custom contours, holes, meshing, geometric
  properties, and section stresses
- a French and English user interface

Current work mainly focuses on:

- continuous UI and workflow improvements
- result post-processing and result tables
- result envelopes and multi-case / multi-combination workflows
- code checks and calculation note exports
- DXF import and composite sections in the Section Builder
- installable domain plugins, including future connection-design modules

## Available Features

- Basic structural modeling: nodes, beam elements, supports
- Concrete (EC2) and steel (EC3) material libraries
- Rectangular, T-shaped, I/H, channel, angle, and tube sections with live preview
- Built-in catalog of more than 200 European steel profiles (`IPE`, `HEA`, `HEB`, `HEM`, `UPN`, `UPE`, `CHS`, `SHS`, `RHS`, angles)
- Section Builder with contour and hole drawing, point editing, profile import,
  meshing, and calculation reports
- Optional section property, torsion, and stress calculations through
  `sectionproperties`
- PyVista 3D view with interactive selection and support symbols
- Hierarchical model tree synchronized with the 3D view
- Editable property panel for main model objects
- Creation dialogs for materials, sections, loads, combinations, and Eurocode settings
- Linear static analysis through PyNite and OpenSeesPy
- Experimental quadrilateral plates through an internal automatic OpenSeesPy mesh
- Installed plugin discovery through `plugin.json` / `hexa-plugin.json` manifests
- Initial application host for connection-design plugins exposing `connections.design`
- Result extraction: displacements, reactions, internal forces
- 2D `N / V / T / M` diagrams for supported cases
- Boundary-condition display directly on 2D diagrams
- Project save/load in SQLite format (`.db`)

## Roadmap

- More complete results workspace and post-processing tables
- Result envelopes and multi-case / multi-combination reading
- Automated EC2 / EC3 / EC8 checks
- External steel connection-design plugin installed separately
- More complete EC8 seismic setup
- Pushover and time-history analysis
- PDF calculation report export
- Finalized Windows packaging
- DXF import, composite sections, and multiple materials in the Section Builder

## Current Plate Limitations

Planar rectangular or quadrilateral plates are supported experimentally through
a regular quadrilateral mesh. Users manipulate a four-node macro plate; before
an OpenSeesPy analysis, HEXA generates an internal mesh that remains hidden from
the main model tree. Automatic and user-defined mesh divisions are available.
Openings, arbitrary contours, and triangular meshes are not supported yet.

## Architecture

The application is gradually moving toward a modular hybrid architecture:

- `gui/`: PySide6 interface, PyVista 3D view, widgets, and dialogs
- `core/model_data.py`: user-facing domain model and historical persistence entry point
- `core/application/`: ports, DTOs, use cases, and application facade
- `core/adapters/`: technical adapters, including solvers and meshing
- `core/plugins/`: installable plugin discovery through manifests
- `core/solvers/`: historical backends and multi-solver compatibility

The main rule is that domain and application use cases must not depend on
PySide6, OpenSeesPy, PyNite, SQLite, or Matplotlib. The GUI is gradually routed
through `ApplicationServices`, which orchestrates application ports.

PyNite and OpenSeesPy are exposed as internal solver plugins/adapters. The same
runtime also prepares non-solver plugins: for example, a future external steel
connection-design module can declare the `connections.design` extension point.

New application results are normalized through `AnalysisRunResult`. The legacy
payload remains dictionary-based for now to preserve compatibility with the
existing GUI and post-processing code.

## Requirements

- **Windows 10 1809+ or Windows 11** for the published Windows executable
- **Python 3.12** recommended
- `PySide6 >= 6.6`
- `pyvista` and `pyvistaqt` for 3D visualization
- `PyNiteFEA` for the default solver
- `OpenSeesPy >= 3.5` only if you want to use that backend
- `sectionproperties` only for advanced Section Builder features

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

To enable the advanced Section Builder features:

```bash
pip install -r requirements-optional.txt
```

## Enable OpenSeesPy (Optional)

OpenSeesPy is not installed by default and is not bundled inside the Windows executable. If you want to use this engine, install it manually:

```bash
pip install openseespy
```

The Windows executable then detects it in compatible Python installations on the machine, including the Python 3.12 user install and the project `.venv` during build QA. If OpenSeesPy is installed in a custom folder, set `HEXA_PYTHON_SITE_PACKAGES` to the relevant `site-packages` directory.

## Build the Windows Executable

```bash
pip install pyinstaller
build.bat
```

Expected output:

```text
dist\HEXA Structures\HEXA Structures.exe
```

Compatibility: the published Windows executable targets Windows 10/11. Windows 7 is not supported by the Python 3.12 / Qt 6 build; the `api-ms-win-core-path-l1-1-0.dll` error indicates that platform limit, not a missing HEXA dependency.

The generated executable does not bundle OpenSeesPy. End users must install it separately if they need that solver.

## Project Structure

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

## Internal Units

The internal unit system uses **kN, m, kPa**. Conversions to and from other units (`mm`, `MPa`, `cm2`, and others) are handled in `utils/units.py`.

## Integrated Standards

| Standard | Content | Status |
|---|---|---|
| NF EN 1990 (EC0) | Load combinations, psi coefficients | Constants |
| NF EN 1991 (EC1) | Imposed loads, wind (French NA), snow (French NA) | Constants |
| NF EN 1992 (EC2) | Concrete materials, C20 to C50 classes, B500 reinforcement | Materials |
| NF EN 1993 (EC3) | Steel S235 to S460, IPE/HEA/HEB/HEM, UPN/UPE, CHS/SHS/RHS tubes and angles | Materials + catalog |
| NF EN 1998 (EC8) | Response spectra, French seismic zoning, soil classes | Constants |

## Tests

Run the main test suite with:

```bash
pytest -q
```

Useful notes:

- `requirements.txt` covers the base application dependencies and the most common test dependencies
- local validation on June 19, 2026: **423 passed, 14 skipped**
- some rendering-related tests require `matplotlib`
- architecture tests cover application ports, plugin discovery, and the `connections.design` host
- advanced comparison tests against `opsvis` require an additional install:

```bash
pip install opsvis
```

## Additional Documentation

- `CONVENTIONS.md`: coding and contribution conventions
- `PROGRESS.md`: progress tracking
- `PROJECT_PLAN.md`: project plan
- `RELEASE_NOTES_0.1.0.md`: release notes for version 0.1.0
- `IMPLEMENTATION_MULTI_SOLVEUR.md`: historical notes and current multi-solver/plugin architecture status
- `docs/PROFILES.md`: steel profiles, parametric sections, and the Section Builder
- `docs/I18N.md`: French and English internationalization

## Contributing

Contributions are welcome. Before opening a change, read `CONVENTIONS.md` to follow the project's coding conventions.

## License

This project is distributed under the **LGPL-3.0-only** license. See [LICENSE](LICENSE) for the LGPL text and [COPYING](COPYING) for the GNU GPL v3 text referenced by that license.

## Usage Warning

HEXA Structures is under active development. Its results do not constitute a
certified calculation report or regulatory approval. Any use on a real
structure must be independently checked, validated, and signed by a qualified
structural engineer.

---

Project under active development.
