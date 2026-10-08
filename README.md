# Earth, Wind & Fire (EWF) simulator

A modular Python-based simulator of the Earth-Wind-Fire (EWF) ventilation system, designed for integration with Rhino 8 and Grasshopper.
An optional standalone Python runner is also available. Both entry points use the same calculation modules.


## Table of contents
* [General info](#general-info)
* [Using Rhino & Grasshopper](#using-rhino--grasshopper)
* [Optional standalone Python simulator](#optional-standalone-python-simulator)
* [Developing](#developing) 
* [Features](#features)
* [Status](#status)
* [Contributing, security and citation](#contributing-security-and-citation)
* [License](#license)
* [Credits](#credits)

## General info
This repository contains the Rhino 8 and Grasshopper implementation of the **EWF Tech Simulator**, a modular and efficient simulation of the Earth, Wind & Fire (EWF) ventilation system. The model estimates yearly energy use with an hourly time step (60 minutes; other time steps are not supported), and simulates predefined airflows with specific temperature and humidity targets.

The recommended way to use the simulator is inside **Rhino 8** using **Grasshopper**, where each simulation component is embedded as a Python block on the Grasshopper canvas. Each component consists of two linked parts:

- the Grasshopper adapter, embedded in `ewf_tech_simulator.ghx` as a *Python 3 Script* component, which maps Grasshopper port names to simulation variables and calls the Python simulation core. The adapters are stored (base64-encoded) inside the `.ghx` file; there is no separate `./scripts/` folder.
- `./src/<component>.py` – the core simulation logic for each component.

This modular architecture improves transparency, testability, and reuse of each physical or logical subsystem within the EWF simulation.

## Using Rhino & Grasshopper

This section explains how to **use the software without modifying the source code**. You only need Rhino8 and Grasshopper, no separate Python installation or development setup.

### Prerequisites
To run this simulator, you need:

- **Rhino 8**, version SR20 or later, with **Grasshopper**  
  > Tested with:  
  > Rhino 8 SR20 (build 8.20.25157.13001, dated 2025-06-06)  
  > Grasshopper build 1.0.0008 (dated 2025-06-06)
  
- A valid Rhino 8 license or the **free 90-day trial**, available at:  
  [https://www.rhino3d.com/download/](https://www.rhino3d.com/download/)

Rhino includes its own embedded Python environment (CPython 3.9, `py39-rh8`). You do **not** need to install Python separately when using Grasshopper.

Grasshopper automatically installs required dependencies on first load, based on the `# venv:` and `# requirements:` directives included in each component. All components use the environment `ewf-tech` with these exact versions:

| Package | Version | Used for |
| --- | --- | --- |
| numpy | 1.24.4 | numerical calculations |
| pandas | 1.5.3 | time series data frames |
| scipy | 1.13.1 | solving the solar chimney heat balance |
| astral | 3.2 | solar position |
| pytz | 2025.2 | time zones |
| openpyxl | 3.1.5 | Excel export |

For exporting an IFC-model, a plugin is needed called 'IFChopper'. Search at www.food4rhino.com and put the ifchopperfiles in the plugin directory of Rhino, normally `c:/ProgramFiles/Rhino8/plugins`.

### Running the simulator in Grasshopper

1. Launch **Rhino 8**
2. Start **Grasshopper** by typing `Grasshopper` in the Rhino command line.
3. Open the file `ewf_tech_simulator.ghx`
4. Dependencies will install automatically on first load (this may take a few minutes the first time).
5. The simulation is now available through the Grasshopper canvas.

### Troubleshooting Grasshopper

#### Grasshopper complains about missing dependencies
Normally, dependencies install automatically. If something went wrong and Grasshopper shows error messages about missing packages, you may need to install them manually.

1. Close Rhino if it is running.
2. Open a terminal (e.g. PowerShell or Command Prompt).
3. Find the folder of the `ewf-tech` environment: `C:\Users\your-username\.rhinocode\py39-rh8\site-envs\ewf-tech-XXXXXXXX` (the last part is random and differs per computer).
4. Run the following command, replacing `your-username` with your own and `ewf-tech-XXXXXXXX` with the folder name you found, from the folder that contains `requirements.txt`:

   ```shell
   "C:\Users\your-username\.rhinocode\py39-rh8\python.exe" -m pip install --target "C:\Users\your-username\.rhinocode\py39-rh8\site-envs\ewf-tech-XXXXXXXX" -r requirements.txt
   ```

5. Start Rhino again.

#### Corrupted Python environment
If you opened the `.ghx` file before dependencies were installed, Rhino may have created a corrupted Python environment. Symptoms include:
- Error messages in Grasshopper Python components  
- Inability to import basic packages like `numpy`  
- Pip install commands that fail unexpectedly  

**Fix:**
1. Close Rhino and Grasshopper completely.  
2. Identify the exact `ewf-tech-XXXXXXXX` folder reported by the Bootstrap component. Do not delete the parent `site-envs` folder or any environment belonging to another project.
3. Move that one EWF environment to a backup location outside `site-envs`. If its identity is uncertain, stop and ask the maintainer before changing any environment.
4. Reopen the Grasshopper definition so Rhino can recreate its EWF environment. Use the targeted installation command above if necessary, with the newly reported folder name.
5. Retain the backup until the model has run successfully. If recreation fails, close Rhino before restoring that specific environment.

## Optional standalone Python simulator

The standalone Python runner is optional. Use it if you do not have Rhino, or if you need repeatable command-line, automated or headless simulations. This is not required for the normal Rhino/Grasshopper workflow.

### Quick start

**Python 3.9 is required.** Check your version with `python --version` before proceeding.

From the repository root in PowerShell or Command Prompt:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ewf_tech_simulator.py --hours 24
```

This creates a local virtual environment, installs dependencies, and runs the first 24 hours of the example. The output shows mean power in W and energy in kWh. Input files are not modified.

### Parameters and outputs

[input/simulation_parameters.json](input/simulation_parameters.json) lists the example parameters in component groups, using the same names and unit suffixes as the Python functions. Edit values for a different building; parameters omitted from a configuration retain their example defaults. Unknown names are rejected so a spelling mistake cannot silently change the intended run.

```powershell
.\.venv\Scripts\python.exe ewf_tech_simulator.py --config examples/simulation_parameters.json --full-year --xlsx data --report data/run_report.json
```

- `--xlsx [FOLDER]` writes `<YYYY-MM-DDTHHMM>-ewf-sim-data_total.xlsx` into an existing folder (default `data`), with sheets `Info`, `Inputdata` and `Outputdata`. `--auteur`, `--organisatie`, `--project`, `--omschrijving`, `--site` and `--gebouw` fill the `Info` sheet.
- `--report` writes effective parameters, source/input hashes, package versions, stage timings, warnings and summary results as JSON.
- Output files must be new and their parent directory must exist. Existing files are never overwritten. Generated files under `data/` are ignored by Git.
- `--year 2024` selects the supplied De Bilt weather and matching annual occupancy (`Occ<year>vac27to32and52.csv`) for 2024.
- `--weather` and `--occupancy` select other input CSVs; pass `--year` explicitly when selecting a different year. Relative paths are resolved from the terminal's working directory.
- `--hours 168 --start-row 3000` selects a week after occupancy/calendar processing. `--hours` and `--full-year` are mutually exclusive.
- `--compare-xlsx` compares against an existing Grasshopper `Outputdata` sheet. Historical exports may differ intentionally after bug fixes.

Use `python ewf_tech_simulator.py --help` for all options. The command exits with code `0` on success and `2` for invalid inputs, numerical failures, non-finite output or a comparison mismatch. Such errors are reported rather than replaced with plausible-looking results.

The runner can also be imported from Python:

```python
from ewf_tech_simulator import load_parameters, run_simulation

parameters = load_parameters("examples/simulation_parameters.json")
frame, report = run_simulation(
  "input/WeerData/De Bilt 2025.csv",
  "input/Occupancy Data/Occ2025vac27to32and52.csv",
  year=2025,
  hours=24,
  parameters=parameters,
)
```

## Developing
This section is for users who want to **extend or change the source code**.

### Getting the code
You can get the code from GitHub in several ways:
- **Clone the repository** (recommended):  
  ```
  git clone https://github.com/EWF-sim/tech-simulator.git
  ```
- **Download ZIP**: Click the green **Code** button on the repo’s GitHub page and choose **Download ZIP**.  

### Code structure
```text
ewf_tech_simulator.ghx     Grasshopper entry point (embedded adapters)
ewf_tech_simulator.py      Standalone command-line runner and Python API
src/                       Physical calculations, CSV loading, errors and logging
input/                     Supplied weather and occupancy CSVs and generator, example building
requirements.txt           Shared pinned runtime dependencies
```

Keep physical equations in `src/` and orchestration in the root runner.

### Reading the calculations

A pandas DataFrame is the calculation table: each row is one hour, and each column is a named engineering quantity. Component functions return a copy with extra columns; they do not change their input table. Read the required inputs and outputs in each function's docstring before tracing its equations.

The calculation order is weather, occupancy, solar chimney, Ventec roof, overpressure room, climate cascade, then energy.

| Name suffix | Meaning | Example |
| --- | --- | --- |
| `__degC` / `__K` | Celsius / kelvin | `temp_outdoor__degC` |
| `__Pa` | Pressure in pascals | `overpressure_room_delta__Pa` |
| `__m3_s_1` / `__kg_s_1` | Volume / mass flow per second | `air_flow_office__m3_s_1` |
| `__kg_m_3` | Mass per volume | `vapour_in__kg_m_3` |
| `__g_kg_1` / `__gr_kg_1` | Grams of water per kilogram of air | `humidity_abs_set__g_kg_1` |
| `__W` | Power, not energy | `e_fan_supply__W` |
| `__0` / `__W0` | Dimensionless values / ratios such as efficiency and COP | `eta_fan__W0` |


## Features
List of features ready and TODOs for future development. 

### Ready:
* read hourly Dutch weather data (KNMI format, CSV) and convert it to model units;
* simulate the over pressure room;
* simulate occupancy based on an occupancy pattern read from CSV (a generator script is included in `input/Occupancy Data/Occupancy Data Aanmaken/`);
* simulate the climate cascade;
* simulate the solar chimney;
* simulate the ventec roof;
* calculate the electricity used by all components
* export a resulting dataframe to Excel format.

## Status
Project is: _in progress_

## Contributing, security and citation
* Contributions are welcome, and you are free to fork this repository. See [CONTRIBUTING.md](CONTRIBUTING.md).
* Please report security problems privately, as described in [SECURITY.md](SECURITY.md).
* To cite this software, use the metadata in [CITATION.cff](CITATION.cff) (GitHub shows a *Cite this repository* button).

## License
This software is available under the [Apache 2.0 license](LICENSE), Copyright 2025 [Research group Energy Transition, Windesheim University of Applied Sciences](https://windesheim.nl/energietransitie)

## Credits
This software is a collaborative effort of:
* Oscar Somsen · [@OscarSomsen](https://github.com/OscarSomsen)
* Wiechert Eschbach · [@WiechertJ](https://github.com/WiechertJ)
* Frank de Kimpe · [@frankdekimpe](https://github.com/frankdekimpe)

We use and gratefully acknowlegde the efforts of the makers of the following source code and libraries:
* [needforheat-dutch-weather-software](https://github.com/energietransitie/needforheat-dutch-weather-software), by [@henriterhofte](https://github.com/henriterhofte) and contributors, licensed under [Apache 2.0](https://opensource.org/licenses/Apache-2.0)
* [numpy 1.24.4](https://pypi.org/project/numpy/1.24.4), by Travis Oliphant et al., licensed under [BSD](https://opensource.org/licenses/BSD-3-Clause)
* [pandas 1.5.3](https://pypi.org/project/pandas/1.5.3), by The pandas development team, licensed under [BSD](https://opensource.org/licenses/BSD-3-Clause)
* [scipy 1.13.1](https://pypi.org/project/scipy/1.13.1), by SciPy Developers, licensed under [BSD](https://opensource.org/licenses/BSD-3-Clause)
* [openpyxl 3.1.5](https://pypi.org/project/openpyxl/3.1.5), by Charlie Clark and contributors, licensed under [MIT](https://opensource.org/licenses/MIT)
* [pytz 2025.2](https://pypi.org/project/pytz/2025.2), by Stuart Bishop, licensed under [MIT](https://opensource.org/licenses/MIT)
* [astral 3.2](https://pypi.org/project/astral/3.2), by Simon Kennedy, licensed under [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
* Hourly weather data (`input/WeerData/`) from [KNMI](https://www.knmi.nl)
