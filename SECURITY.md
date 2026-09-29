# Security policy

## Supported versions

Only the latest version on the `main` branch receives fixes.

## Reporting a vulnerability

Please **do not** report security problems in a public issue.

Report them privately, using one of these options:

- GitHub's private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability**.
- Email: [EWF-sim@windesheim.nl](mailto:EWF-sim@windesheim.nl)

Please include what you found, how to reproduce it, and which version (commit) you tested. We will acknowledge your report as soon as possible and keep you informed about the fix.

## Scope

This software is a simulation that runs locally inside Rhino/Grasshopper. Relevant reports include, for example:

- a crafted input file (CSV weather or occupancy data, `.ghx` file) that leads to unwanted code execution or file access;
- a vulnerable version of a dependency listed in [requirements.txt](./requirements.txt).

Incorrect simulation results are not security issues; please report those as a normal issue.
