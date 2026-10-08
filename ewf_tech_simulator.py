"""Run the Earth, Wind & Fire simulation without Rhino or Grasshopper.

Uses the same calculation functions as the Grasshopper definition. Defaults
describe the supplied example building; --config overrides its parameters.
"""

import argparse
import calendar
import hashlib
import io
import json
import platform
import sys
import warnings
from collections import Counter
from collections.abc import Sequence
from contextlib import redirect_stdout
from datetime import date, datetime
from importlib import metadata
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

import climate_cascade
import energy
import occupancy
import over_pressure_room
import solar_chimney
import ventec_roof
import weather
from exceptions import EWFException


def example_parameters() -> Dict[str, Any]:
    """Load example-building defaults from input/simulation_parameters_python.json.

    Values are in the units carried by their names.
    """
    return json.loads(
        (ROOT / "input" / "simulation_parameters_python.json").read_text(encoding="utf-8")
    )


def load_parameters(path: Union[str, Path]) -> Dict[str, Any]:
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
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
                raise ValueError(f"Parameter must be a finite number: {component}.{name}")
            parameters[component][name] = value
    return parameters


def file_hash(path: Union[str, Path]) -> str:
    """SHA-256 identifies the exact source and data used by an observation."""
    with Path(path).open("rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def package_version(package: str) -> Optional[str]:
    """Report-only version lookup; None when the distribution is not installed."""
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def frame_summary(frame: pd.DataFrame) -> Dict[str, Any]:
    """Count invalid numerical values rather than silently dropping them."""
    numeric = frame.select_dtypes(include=[np.number])
    invalid = ~np.isfinite(numeric)
    return {
        "rows": len(frame),
        "columns": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "nonfinite": {
            name: int(count) for name, count in invalid.sum().items() if count
        },
        "memory_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
        "first_rows": json.loads(frame.head(3).to_json(orient="records", date_format="iso")),
    }


def run_simulation(
    weather_path: Union[str, Path],
    occupancy_path: Union[str, Path],
    year: int,
    hours: Optional[int] = 24,
    start_row: int = 0,
    parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run the real component order; None hours selects the complete input year.

    Occupancy runs before slicing, preserving its original annual calendar logic.
    Slices receive a fresh RangeIndex for consistent exported row numbering.
    The core CSV readers own and clean up their temporary input copies.
    """
    if hours is not None and hours <= 0:
        raise ValueError("hours must be positive, or None for a full-year run")
    if start_row < 0:
        raise ValueError("start_row must be nonnegative")
    if hours is None and start_row:
        raise ValueError("A full-year run must start at row zero")
    parameters = example_parameters() if parameters is None else parameters
    weather_path, occupancy_path = Path(weather_path), Path(occupancy_path)
    protected = list((ROOT / "src").glob("*.py")) + [
        weather_path, occupancy_path, Path(__file__), ROOT / "requirements.txt",
    ]
    before = {str(path.resolve()): file_hash(path) for path in protected}
    stages = {}

    def observe(name: str, calculation: Any, *args: Any, **kwargs: Any) -> Any:
        input_frame = args[0] if args else kwargs.get("df")
        original = input_frame.copy(deep=True) if isinstance(input_frame, pd.DataFrame) else None
        started = perf_counter()
        with warnings.catch_warnings(record=True) as caught, redirect_stdout(io.StringIO()):
            warnings.simplefilter("always")
            result = calculation(*args, **kwargs)
        elapsed = perf_counter() - started
        frame = result[0] if isinstance(result, tuple) else result
        if original is not None:
            pd.testing.assert_frame_equal(input_frame, original)
        stages[name] = frame_summary(frame)
        stages[name]["seconds"] = elapsed
        stages[name]["warnings"] = dict(Counter(str(item.message) for item in caught))
        print(f"{name}: {len(frame)} rows, {elapsed:.3f} s", file=sys.stderr, flush=True)
        return result

    try:
        frame = observe("weather", weather.retrieve_weather_data, str(weather_path))
        frame = observe(
            "occupancy", occupancy.calculate_occupancy,
            df=frame, jaar=year, pad=str(occupancy_path), **parameters["occupancy"]
        )
        stop_row = None if hours is None else start_row + hours
        frame = frame.iloc[start_row:stop_row].reset_index(drop=True)
        if frame.empty or (hours is not None and len(frame) != hours):
            raise ValueError("Requested slice is not fully available after occupancy alignment")
        frame = observe("solar_chimney", solar_chimney.calculate_solar_chimney,
                        frame, **parameters["solar_chimney"])
        frame = observe("ventec_roof", ventec_roof.calculate_ventec_roof,
                        frame, **parameters["ventec_roof"])
        frame = observe("over_pressure_room", over_pressure_room.calculate_overpressure_room,
                        frame, **parameters["over_pressure_room"])
        frame = observe("climate_cascade", climate_cascade.calculate_climate_cascade,
                        frame, **parameters["climate_cascade"])
        frame, mean, total = observe("energy", energy.calculate_energy, frame)
    finally:
        after = {str(path.resolve()): file_hash(path) for path in protected}
        if before != after:
            raise RuntimeError("A protected source/input changed during this run; discard the comparison")

    report = {
        "status": "observation only; no independent physics or Rhino parity certification",
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": {package: package_version(package) for package in (
            "numpy", "pandas", "scipy", "astral", "pytz", "openpyxl", "python-dateutil", "pydantic"
        )},
        "sha256": before,
        "parameters": parameters,
        "year": year,
        "start_row": start_row,
        "requested_hours": hours,
        "full_year_expected_rows": 8784 if calendar.isleap(year) else 8760,
        "stages": stages,
        "total_mean__W": float(mean) if np.isfinite(mean) else None,
        "total_sum__kWh": float(total) if np.isfinite(total) else None,
        "rows_with_nonfinite_total": int((~np.isfinite(frame["e__ewf_total__W"])).sum()),
    }
    return frame, report


def compare_export(frame: pd.DataFrame, export_path: Union[str, Path]) -> Dict[str, Any]:
    """Compare every output column, including matching NaN/infinity positions.

    Tolerances allow spreadsheet float serialization, not engineering error:
    relative 1e-10 and absolute 1e-8 in each column's stated units.
    """
    reference = pd.read_excel(export_path, sheet_name="Outputdata")
    comparison = {
        "path": str(Path(export_path).resolve()),
        "sha256": file_hash(export_path),
        "reference_rows": len(reference),
        "missing_columns": sorted(set(reference.columns) - set(frame.columns)),
        "extra_columns": sorted(set(frame.columns) - set(reference.columns)),
        "mismatches": {},
        "rtol": 1e-10,
        "atol": 1e-8,
    }
    if len(reference) != len(frame):
        comparison["matches"] = False
        return comparison
    for name in reference.columns.intersection(frame.columns):
        if pd.api.types.is_numeric_dtype(frame[name]):
            expected = pd.to_numeric(reference[name], errors="raise").to_numpy(dtype=float)
            actual = frame[name].to_numpy(dtype=float)
            matching = np.isclose(actual, expected, rtol=1e-10, atol=1e-8, equal_nan=True)
        else:
            matching = (frame[name].fillna("").astype(str).to_numpy() ==
                        reference[name].fillna("").astype(str).to_numpy())
        if not matching.all():
            comparison["mismatches"][name] = int((~matching).sum())
    comparison["matches"] = not any(comparison[key] for key in (
        "missing_columns", "extra_columns", "mismatches"
    ))
    return comparison


def export_xlsx(
    frame: pd.DataFrame,
    folder: Union[str, Path],
    parameters: Dict[str, Any],
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
    with path.open("xb") as stream:
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="Outputdata", index=False)
            workbook = writer.book
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
                        help="Write a timestamped Grasshopper-layout workbook into FOLDER (default: data)")
    for name in ("auteur", "organisatie", "project", "omschrijving", "site", "gebouw"):
        parser.add_argument(f"--{name}", default="", help=f"Info sheet field: {name.capitalize()}")
    parser.add_argument("--compare-xlsx", type=Path, help="Existing Outputdata export; read-only comparison")
    parser.add_argument("--report", type=Path, help="New JSON file in an existing directory; never overwritten")
    arguments = parser.parse_args(argv)
    if arguments.report and (arguments.report.exists() or not arguments.report.parent.is_dir()):
        parser.error(f"Output must be a new file in an existing directory: {arguments.report}")
    if arguments.xlsx and not arguments.xlsx.is_dir():
        parser.error(f"Export folder does not exist: {arguments.xlsx}")
    weather_path = arguments.weather or ROOT / f"input/WeerData/De Bilt {arguments.year}.csv"
    occupancy_name = f"Occ{arguments.year}vac27to32and52.csv"
    occupancy_path = arguments.occupancy or ROOT / "input/Occupancy Data" / occupancy_name
    try:
        config_hash = file_hash(arguments.config) if arguments.config else None
        parameters = load_parameters(arguments.config) if arguments.config else example_parameters()
        frame, report = run_simulation(
            weather_path, occupancy_path, arguments.year,
            hours=None if arguments.full_year else arguments.hours, start_row=arguments.start_row,
            parameters=parameters
        )
        if arguments.config:
            if file_hash(arguments.config) != config_hash:
                raise RuntimeError("Parameter file changed during this run; discard the comparison")
            report["sha256"][str(arguments.config.resolve())] = config_hash
        if arguments.compare_xlsx:
            report["export_comparison"] = compare_export(frame, arguments.compare_xlsx)
            print(json.dumps(report["export_comparison"], indent=2))
        if arguments.report:
            with arguments.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=True, allow_nan=False)
                stream.write("\n")
            print(f"Run report: {arguments.report}")
        if arguments.xlsx:
            exported = export_xlsx(
                frame, arguments.xlsx, parameters, arguments.year,
                report["total_mean__W"], report["total_sum__kWh"],
                auteur=arguments.auteur, organisatie=arguments.organisatie,
                project=arguments.project, omschrijving=arguments.omschrijving,
                site=arguments.site, gebouw=arguments.gebouw,
            )
            print(f"Excel export: {exported}")
    except (EWFException, OSError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(2, f"Simulation failed: {error}\n")
    print(json.dumps({
        "rows": len(frame),
        "total_mean__W": report["total_mean__W"],
        "total_sum__kWh": report["total_sum__kWh"],
        "nonfinite": report["stages"]["energy"]["nonfinite"],
        "warnings": {name: stage["warnings"] for name, stage in report["stages"].items() if stage["warnings"]},
    }, indent=2))
    incomplete_year = arguments.full_year and (
        report["stages"]["energy"]["rows"] != report["full_year_expected_rows"]
    )
    if report["stages"]["energy"]["nonfinite"] or incomplete_year:
        return 2
    if arguments.compare_xlsx and not report["export_comparison"]["matches"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())