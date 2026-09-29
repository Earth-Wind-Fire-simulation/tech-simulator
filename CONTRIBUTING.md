# Contributing

Thank you for your interest in the EWF Tech Simulator. Contributions of all kinds are welcome: bug reports, questions, documentation, and code.

This project is released under the [Apache 2.0 license](./LICENSE). By submitting a contribution you agree that it is licensed under the same terms. You are also free to fork this repository to develop your own version.

## Reporting bugs and asking questions

- Search the existing [issues](../../issues) first.
- For a bug, please use the bug report form and include your Rhino version, the package versions that the *Bootstrap* component prints, and the full message of the error.
- For a change to the simulation model (formulas, parameters, numerical results), open an issue first so it can be discussed before you spend time on it.
- Security problems: see [SECURITY.md](./SECURITY.md).

## Setting up for development

The simulation core in `./src/` is plain Python 3.9 and can be edited in any editor. The Grasshopper adapters live inside `ewf_tech_simulator.ghx` (see the README).

To run the core outside Grasshopper, install the pinned dependencies in a Python 3.9 environment and put `src` on the Python path:

```shell
pip install -r requirements.txt
```

## Rules of the road

- **Keep the dependency lines identical.** The `# requirements:` line at the top of every module in `./src/`, the file `requirements.txt`, and the script components in the `.ghx` must list exactly the same packages and versions.
- **Follow the naming convention.** Variables carry their unit as a suffix, for example `wind__m_s_1`, `temp_outdoor__degC`, `air_flow_office__m3_s_1` (`__0` for dimensionless quantities).
- **Use the custom exceptions.** Raise the errors from `src/exceptions.py` (`create_data_validation_error`, `create_configuration_error`, ...) so users get clear messages.
- **Model changes need evidence.** If a change alters the numerical results, explain why in the pull request and give the before and after numbers (for example the yearly energy use in kWh). Keep such changes separate from refactoring.
- **Changes to the `.ghx` file.** The scripts in the `.ghx` are stored base64-encoded, so Git cannot show or merge them properly. Describe in the pull request what you changed on the canvas, and coordinate with the maintainers so that two people do not edit the file at the same time.
- Comments and documentation are currently in Dutch and English; either language is fine in issues and pull requests.

## Submitting a pull request

1. Fork the repository and create a branch from `main`.
2. Make your change, and test it in Rhino/Grasshopper where it touches the simulation.
3. Open a pull request against `main` and fill in the template.
4. A maintainer will review it. Please respond to review comments; the pull request is merged once it is approved.
