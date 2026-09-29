# Earth, Wind & Fire (EWF) simulator

A modular Python-based simulator of the Earth-Wind-Fire (EWF) ventilation system, designed for integration with Rhino 8 and Grasshopper.


## Table of contents
* [General info](#general-info)
* [Deploying](#deploying)
* [Developing](#developing) 
* [Features](#features)
* [Status](#status)
* [Contributing, security and citation](#contributing-security-and-citation)
* [License](#license)
* [Credits](#credits)

## General info
This repository contains the Python implementation of the **EWF Tech Simulator**, a modular and efficient simulation of the Earth, Wind & Fire (EWF) ventilation system. The model estimates yearly energy use with an hourly time step (60 minutes; other time steps are not supported), and simulates predefined airflows with specific temperature and humidity targets.

The simulator runs inside **Rhino 8** using **Grasshopper**, where each simulation component is embedded as a Python block on the Grasshopper canvas. Each component consists of two linked parts:

- the Grasshopper adapter, embedded in `ewf_tech_simulator.ghx` as a *Python 3 Script* component, which maps Grasshopper port names to simulation variables and calls the Python simulation core. The adapters are stored (base64-encoded) inside the `.ghx` file; there is no separate `./scripts/` folder.
- `./src/<component>.py` – the core simulation logic for each component.

This modular architecture improves transparency, testability, and reuse of each physical or logical subsystem within the EWF simulation.

## Deploying
This section explains how to **use the software without modifying the source code**. You only need Rhino8 and Grasshopper, no separate Python installation or development setup.

### Prerequisites
To run this simulator, you need:

- **Rhino 8**, version SR20 or later, with **Grasshopper**  
  > Tested with:  
  > Rhino 8 SR20 (build 8.20.25157.13001, dated 2025-06-06)  
  > Grasshopper build 1.0.0008 (dated 2025-06-06)
  
- A valid Rhino 8 license or the **free 90-day trial**, available at:  
  [https://www.rhino3d.com/download/](https://www.rhino3d.com/download/)

Rhino includes its own embedded Python environment (CPython 3.9, `py39-rh8`). You do **not** need to install Python separately.  
Grasshopper automatically installs required dependencies on first load, based on the `# venv:` and `# requirements:` directives included in each component. All components use the environment `ewf-tech` with these exact versions:

| Package | Version | Used for |
| --- | --- | --- |
| numpy | 1.24.4 | numerical calculations |
| pandas | 1.5.3 | time series data frames |
| scipy | 1.13.1 | solving the solar chimney heat balance |
| astral | 3.2 | solar position |
| pytz | 2025.2 | time zones |
| openpyxl | 3.1.5 | Excel export |

The same list is available as [requirements.txt](./requirements.txt) for development outside Rhino.

For exporting an IFC-model, a plugin is needed called 'IFChopper'. search at www.food4rhino.com en put the ifchopperfiles in the plugindirectory of Rhino, normally c:/ProgramFiles/Rhino8/plugins

## Running the simulator

1. Launch **Rhino 8**
2. Start **Grasshopper** by typing `Grasshopper` in the Rhino command line.
3. Open the file `ewf_tech_simulator.ghx`
4. Dependencies will install automatically on first load (this may take a few minutes the very first time).
5. The simulation is now available through the Grasshopper canvas.

## Troubleshooting

### Grasshopper complains about missing dependencies
Normally, dependencies install automatically. If something went wrong and Grasshopper shows error messages about missing packages, you may need to install them manually.

1. Close Rhino if it is running.
2. Open a terminal (e.g. PowerShell or Command Prompt).
3. Find the folder of the `ewf-tech` environment: `C:\Users\your-username\.rhinocode\py39-rh8\site-envs\ewf-tech-XXXXXXXX` (the last part is random and differs per computer).
4. Run the following command, replacing `your-username` with your own and `ewf-tech-XXXXXXXX` with the folder name you found, from the folder that contains `requirements.txt`:

   ```shell
   "C:\Users\your-username\.rhinocode\py39-rh8\python.exe" -m pip install --target "C:\Users\your-username\.rhinocode\py39-rh8\site-envs\ewf-tech-XXXXXXXX" -r requirements.txt
   ```

5. Start Rhino again.

### Corrupted Python environment
If you opened the `.ghx` file before dependencies were installed, Rhino may have created a corrupted Python environment. Symptoms include:
- Error messages in Grasshopper Python components  
- Inability to import basic packages like `numpy`  
- Pip install commands that fail unexpectedly  

**Fix:**
1. Close Rhino and Grasshopper completely.  
2. Delete the entire contents of the following folder (but **not** the folder itself):  
   ```shell
   C:\Users\your-username\.rhinocode\py39-rh8\site-envs
   ```
3. Reopen Rhino, then Grasshopper.  
4. Re-run the pip install command above if needed (the `ewf-tech` folder is recreated when Grasshopper opens the file; use the new folder name).  

## Developing
This section is for users who want to **extend or change the source code**.

### Getting the code
You can get the code from GitHub in several ways:
- **Clone the repository** (recommended):  
  ```
  git clone https://github.com/EWF-sim/tech-simulator.git
  ```
- **Download ZIP**: Click the green **Code** button on the repo’s GitHub page and choose **Download ZIP**.  

GitHub provides several options; choose whichever feels easiest. If you are unfamiliar with Git, you can ask ChatGPT or another AI to guide you step-by-step.

### Code structure
The repository is deliberately split into two parts:

1. **Grasshopper adapters (inside `ewf_tech_simulator.ghx`)**  
   - Minimal “adapter” code that connects Grasshopper parameters (inputs/outputs) with the simulation core.  
   - The adapters live only in the Grasshopper file, as base64-encoded script text, so changes to them do not show up as readable diffs in Git.  
   - The `# venv:` and `# requirements:` lines of these components must stay identical to [requirements.txt](./requirements.txt).

2. **Simulation core (`./src/`)**  
   - Contains the thermodynamic simulation logic in standard Python functions.  
   - Can be edited with any full-fledged editor, e.g. **Visual Studio Code**.  
   - This setup allows engineers to work comfortably with larger software projects while keeping the Grasshopper interface clean and manageable.


This structure makes collaboration between building engineers and simulation developers much more efficient.  

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
* Contributions are welcome, and you are free to fork this repository. See [CONTRIBUTING.md](./CONTRIBUTING.md).
* Please report security problems privately, as described in [SECURITY.md](./SECURITY.md).
* To cite this software, use the metadata in [CITATION.cff](./CITATION.cff) (GitHub shows a *Cite this repository* button).

## License
This software is available under the [Apache 2.0 license](./LICENSE), Copyright 2025 [Research group Energy Transition, Windesheim University of Applied Sciences](https://windesheim.nl/energietransitie) 

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
