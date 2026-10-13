"""Run the Earth, Wind & Fire simulation without Rhino or Grasshopper.

Uses the same calculation functions as the Grasshopper definition. Defaults
describe the supplied example building; --config overrides its parameters.
Progress and results are printed to the console; --quiet limits it to the results.
"""

import argparse
import calendar
import json
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Optional, Union

ROOT = Path(__file__).resolve().parent
# The calculation modules live in src/ and are imported by bare name.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Third-party and project imports follow the sys.path setup above.
import numpy as np
import pandas as pd
from openpyxl.styles import Alignment

import climate_cascade
import energy
import occupancy
import over_pressure_room
import solar_chimney
import ventec_roof
import weather
from exceptions import EWFException


def example_parameters() -> dict[str, Any]:
    """Load example-building defaults from input/simulation_parameters_python.json.

    Values are in the units carried by their names.
    """
    return json.loads(
        (ROOT / "input" / "simulation_parameters_python.json").read_text(encoding="utf-8")
    )


def load_parameters(path: Union[str, Path]) -> dict[str, Any]:
    """Overlay a JSON parameter file on the example defaults; reject misspellings."""
    parameters = example_parameters()
    overrides = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(overrides, dict):
        raise TypeError("Configuration must be a JSON object grouped by component")
    for component, values in overrides.items():
        if component not in parameters or not isinstance(values, dict):
            raise ValueError(f"Unknown component or invalid parameter group: {component}")
        for name, value in values.items():
            if name not in parameters[component]:
                raise ValueError(f"Unknown parameter: {component}.{name}")
            # bool is a subclass of int, so it must be rejected explicitly.
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
                raise ValueError(f"Parameter must be a finite number: {component}.{name}")
            parameters[component][name] = value
    return parameters


def run_simulation(
    weather_path: Union[str, Path],
    occupancy_path: Union[str, Path],
    year: int,
    hours: Optional[int] = 24,
    start_row: int = 0,
    parameters: Optional[dict[str, Any]] = None,
    observe: Optional[Callable[..., Any]] = None,
) -> tuple[pd.DataFrame, float, float]:
    """Run the simulation and return (frame, mean power in W, energy in kWh).

    None hours selects the complete input year. Occupancy runs before slicing,
    preserving its original annual calendar logic. Slices receive a fresh
    RangeIndex for consistent exported row numbering. The core CSV readers own
    and clean up their temporary input copies.

    observe(name, calculation, *args, **kwargs) may wrap each stage call, e.g. for diagnostics.
    """
    if hours is not None and hours <= 0:
        raise ValueError("hours must be positive, or None for a full-year run")
    if start_row < 0:
        raise ValueError("start_row must be nonnegative")
    if hours is None and start_row:
        raise ValueError("A full-year run must start at row zero")
    parameters = example_parameters() if parameters is None else parameters
    # Without an observer each stage is called directly.
    stage = observe or (lambda name, calculation, *args, **kwargs: calculation(*args, **kwargs))

    # Stage order matters: each stage adds columns that the next one reads.
    frame = stage("weather", weather.retrieve_weather_data, str(Path(weather_path)))
    frame = stage(
        "occupancy", occupancy.calculate_occupancy,
        df=frame, jaar=year, pad=str(Path(occupancy_path)), **parameters["occupancy"]
    )
    # Select the requested hours only after occupancy has seen the whole year.
    stop_row = None if hours is None else start_row + hours
    frame = frame.iloc[start_row:stop_row].reset_index(drop=True)
    if frame.empty or (hours is not None and len(frame) != hours):
        raise ValueError("Requested slice is not fully available after occupancy alignment")
    frame = stage("solar_chimney", solar_chimney.calculate_solar_chimney,
                  frame, **parameters["solar_chimney"])
    frame = stage("ventec_roof", ventec_roof.calculate_ventec_roof,
                  frame, **parameters["ventec_roof"])
    frame = stage("over_pressure_room", over_pressure_room.calculate_overpressure_room,
                  frame, **parameters["over_pressure_room"])
    frame = stage("climate_cascade", climate_cascade.calculate_climate_cascade,
                  frame, **parameters["climate_cascade"])
    return stage("energy", energy.calculate_energy, frame)  # (frame, mean W, total kWh)


def export_xlsx(
    frame: pd.DataFrame,
    folder: Union[str, Path],
    parameters: dict[str, Any],
    year: int,
    mean: float,
    total: float,
    auteur: str = "",
    organisatie: str = "",
    project: str = "",
    omschrijving: str = "",
    site: str = "",
    gebouw: str = "",
) -> Path:
    """Write <YYYY-MM-DDTHHMM>-ewf-sim-data_total.xlsx in folder.

    Sheets: Info, Inputdata, Outputdata. Returns the new file's path; never overwrites.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"Exportmap bestaat niet: {folder}")
    path = folder / f"{datetime.now().strftime('%Y-%m-%dT%H%M')}-ewf-sim-data_total.xlsx"
    solar = parameters["solar_chimney"]
    cascade = parameters["climate_cascade"]
    # Labels and units are Dutch to match the workbook written by the Grasshopper export component.
    rows = [
        ["Maximaal aantal aanwezigen:", parameters["occupancy"]["occupancy_mean__p"], "personen"],
        ["Doorsnede ejector:", parameters["ventec_roof"]["venturi_ejector_opening__m2"], "m²"],
        ["Breedtegraad:", solar["weather_location__degN"], "NB"],
        ["Lengtegraad:", solar["weather_location__degE"], "OL"],
        ["Oriëntatie zonneschoorsteen:", solar["solar_chimney_azimuth__degN"], "graden t.o.v. Noord"],
        ["Glaspercentage zonneschoorsteen", solar["glazing__pct"], "%"],
        ["zontoetredingsfactor glas zonneschoorsteen (g-waarde)", solar["glazing_transmittance__0"], "-"],
        ["Warmtedoorgangscoëfficiënt glas zonneschoorsteen (U-waarde)",
         solar["solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1"], "W/(m².K)"],
        ["Aantal rekensegmenten zonneschoorsteen", solar["solar_chimney_segments__0"], "stuks"],
        ["Hoogte overdrukruimte boven maaiveld",
         parameters["over_pressure_room"]["wind_overpressure_inflow_height__m"], "m"],
        ["Temperatuur water klimaatcascade", cascade["temp_water_cascade_in__degC"], "graden C"],
        ["Temperatuur drempelwaarde lucht ingaande de klimaatcascade",
         cascade["temp_air_in_threshold__degC"], "graden C"],
        ["Settemperatuur lucht uitkomende uit de klimaatcascade",
         cascade["temp_air_cascade_out_set__degC"], "graden C"],
        ["Absolute luchtvochtigheid uitkomende uit de klimaatcascade",
         cascade["humidity_abs_set__g_kg_1"], "gr/m³"],
        ["Minimum aantal sproeiers", cascade["nozzles_min__0"], "stuks"],
        ["Maximum aantal sproeiers", cascade["nozzles_max__0"], "stuks"],
        ["Waterdrukverschil sproeiers klimaatcascade", cascade["loss_cascade_water_nozzle__Pa"], "Pa"],
        ["Aantal rekensegmenten klimaatcascade", cascade["cascade_segments__0"], "stuks"],
        ["", "", ""],
        ["Berekende gemiddelde vermogen", mean, "W"],
        ["Berekende energieverbruik", total, "kWh"],
    ]
    info = [
        ["Datum:", date.today().strftime("%d-%m-%Y")],
        [None, None],
        ["Auteur:", auteur],
        ["Organisatie:", organisatie],
        ["Project:", project],
        ["Omschrijving:", omschrijving],
        ["Site:", site],
        ["Gebouw:", gebouw],
        ["Berekend jaar:", str(year)],
    ]
    # Mode "xb" fails instead of overwriting an existing workbook.
    with path.open("xb") as stream, pd.ExcelWriter(stream, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Outputdata", index=False)
        for cell in writer.sheets["Outputdata"][1]:
            cell.alignment = Alignment(text_rotation=45, horizontal="right", vertical="bottom")
        workbook = writer.book
        # Inserting at index 0 puts Info first, then Inputdata, then Outputdata.
        inputdata = workbook.create_sheet("Inputdata", 0)
        for row in [["Parameter", "Waarde", "Eenheid"]] + rows:
            inputdata.append(row)
        for column, width in zip("ABC", (55, 10, 20)):
            inputdata.column_dimensions[column].width = width
        sheet = workbook.create_sheet("Info", 0)
        for row in info:
            sheet.append(row)
        sheet.column_dimensions["A"].width = 20
        sheet.column_dimensions["B"].width = 55
    return path


STAGE_COUNT = 7  # number of stage() calls in run_simulation
RULE = "-" * 72


def display_path(path: Union[str, Path]) -> str:
    """Show paths inside the project relative to its root."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def stage_progress() -> Callable[..., Any]:
    """Return an observe hook that prints one line per finished stage."""
    finished = []

    def observe(name: str, calculation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        started = perf_counter()
        result = calculation(*args, **kwargs)
        frame = result[0] if isinstance(result, tuple) else result
        finished.append(name)
        print(f"  [{len(finished)}/{STAGE_COUNT}] {name:<20}{len(frame):>7} rows{perf_counter() - started:>9.2f} s",
              flush=True)
        return result

    return observe


def print_parameters(parameters: dict[str, Any], source: str) -> None:
    print(f"Parameters ({source})")
    for component, values in parameters.items():
        print(f"  {component}")
        for name, value in values.items():
            print(f"    {name:<48}{value}")


def format_number(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:,.1f}"


def print_results(frame: pd.DataFrame, mean_w: Optional[float], total_kwh: Optional[float]) -> None:
    power = frame["e__ewf_total__W"]
    peak = power.idxmax()
    # The timestamp column comes from the weather file; show it only when present.
    times = frame.get("tijd met tijdzone")
    print("Results")
    print(f"  Hourly rows      {len(frame)}")
    if times is not None:
        print(f"  Period           {times.iloc[0]}  to  {times.iloc[-1]}")
    print(f"  Mean power       {format_number(mean_w)} W")
    peak_time = "" if times is None else f"  ({times.iloc[peak]})"
    print(f"  Peak power       {format_number(float(power.iloc[peak]))} W{peak_time}")
    print(f"  Energy           {format_number(total_kwh)} kWh")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather", type=Path, help="Weather CSV; defaults to De Bilt for the chosen year")
    parser.add_argument("--occupancy", type=Path, help="Occupancy CSV; defaults to the example for the chosen year")
    parser.add_argument("--year", type=int, default=2025, help="Calendar year (default: 2025)")
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--hours", type=int, default=24, help="Number of hourly rows to simulate (default: 24)")
    duration.add_argument("--full-year", action="store_true", help="Simulate all input rows")
    parser.add_argument("--start-row", type=int, default=0, help="First hourly row of a short run (default: 0)")
    parser.add_argument("--config", type=Path, help="JSON component parameters; omitted values keep example defaults")
    parser.add_argument("--xlsx", type=Path, nargs="?", const=ROOT / "data", metavar="FOLDER",
                        help="Write a timestamped workbook into FOLDER (default: data)")
    for name in ("auteur", "organisatie", "project", "omschrijving", "site", "gebouw"):
        parser.add_argument(f"--{name}", default="", help=f"Info sheet field: {name.capitalize()}")
    parser.add_argument("--quiet", action="store_true", help="Print only the results, not inputs and progress")
    arguments = parser.parse_args(argv)
    # Fail on bad arguments before any calculation starts.
    if arguments.xlsx and not arguments.xlsx.is_dir():
        parser.error(f"Export folder does not exist: {arguments.xlsx}")
    # Default input files are chosen by year; --weather/--occupancy override them.
    weather_path = arguments.weather or ROOT / f"input/WeerData/De Bilt {arguments.year}.csv"
    occupancy_name = f"Occ{arguments.year}vac27to32and52.csv"
    occupancy_path = arguments.occupancy or ROOT / "input/Occupancy Data" / occupancy_name
    hours = None if arguments.full_year else arguments.hours  # None selects every row
    started = perf_counter()
    try:
        parameters = load_parameters(arguments.config) if arguments.config else example_parameters()
        if not arguments.quiet:
            selection = "full year" if hours is None else f"{hours} hours from row {arguments.start_row}"
            print(f"EWF Tech Simulator\n{RULE}")
            print(f"  Year             {arguments.year}")
            print(f"  Weather          {display_path(weather_path)}")
            print(f"  Occupancy        {display_path(occupancy_path)}")
            print(f"  Selection        {selection}\n")
            print_parameters(
                parameters, display_path(arguments.config) if arguments.config else "example defaults"
            )
            print("\nRunning simulation")
        frame, mean, total = run_simulation(
            weather_path, occupancy_path, arguments.year,
            hours=hours, start_row=arguments.start_row, parameters=parameters,
            observe=None if arguments.quiet else stage_progress(),
        )
        # Non-finite totals become None so they print as n/a and export as empty cells.
        mean_w = float(mean) if np.isfinite(mean) else None
        total_kwh = float(total) if np.isfinite(total) else None
        print(f"\n{RULE}")
        print_results(frame, mean_w, total_kwh)
        if arguments.xlsx:
            exported = export_xlsx(
                frame, arguments.xlsx, parameters, arguments.year, mean_w, total_kwh,
                auteur=arguments.auteur, organisatie=arguments.organisatie,
                project=arguments.project, omschrijving=arguments.omschrijving,
                site=arguments.site, gebouw=arguments.gebouw,
            )
            print(f"  Excel export     {display_path(exported)}")
    except (EWFException, OSError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(2, f"Simulation failed: {error}\n")
    # Exit code 2 signals unusable results even though the run itself finished.
    invalid = ~np.isfinite(frame.select_dtypes(include=[np.number]))
    nonfinite = {name: int(count) for name, count in invalid.sum().items() if count}
    full_year_rows = 8784 if calendar.isleap(arguments.year) else 8760
    incomplete_year = arguments.full_year and len(frame) != full_year_rows
    if nonfinite:
        print(f"Warning: non-finite values (column: count): {nonfinite}", file=sys.stderr)
    if incomplete_year:
        print(f"Warning: incomplete year, {len(frame)} rows instead of {full_year_rows}", file=sys.stderr)
    status = "completed with warnings" if nonfinite or incomplete_year else "completed"
    print(f"\nSimulation {status} in {perf_counter() - started:.1f} s")
    return 2 if nonfinite or incomplete_year else 0


if __name__ == "__main__":
    raise SystemExit(main())
