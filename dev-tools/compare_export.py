"""Diagnostics for the standalone simulator: run report and Grasshopper export comparison.

Runs the simulator with per-stage observation (timings, warnings, non-finite counts,
input-mutation checks, source/input hashes). Optionally writes a JSON run report and
compares every output column with an existing Grasshopper Outputdata export.
Exit code 0 = success/match, 2 = mismatch, non-finite output or failure.
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
from importlib import metadata
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import numpy as np
import pandas as pd

import ewf_tech_simulator
from exceptions import EWFException


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


def run_observed(
    weather_path: Union[str, Path],
    occupancy_path: Union[str, Path],
    year: int,
    hours: Optional[int] = 24,
    start_row: int = 0,
    parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run the simulator with per-stage observation; returns (frame, report)."""
    parameters = ewf_tech_simulator.example_parameters() if parameters is None else parameters
    protected = list((ROOT / "src").glob("*.py")) + [
        Path(weather_path), Path(occupancy_path),
        Path(ewf_tech_simulator.__file__), ROOT / "requirements.txt",
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
        frame, mean, total = ewf_tech_simulator.run_simulation(
            weather_path, occupancy_path, year, hours=hours, start_row=start_row,
            parameters=parameters, observe=observe,
        )
    finally:
        after = {str(path.resolve()): file_hash(path) for path in protected}
        if before != after:
            raise RuntimeError("A protected source/input changed during this run; discard the results")

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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, nargs="?", help="Existing Outputdata export (.xlsx) to compare with; read-only")
    parser.add_argument("--report", type=Path, help="New JSON file in an existing directory; never overwritten")
    parser.add_argument("--weather", type=Path, help="Weather CSV; defaults to De Bilt for the chosen year")
    parser.add_argument("--occupancy", type=Path, help="Occupancy CSV; defaults to the example for the chosen year")
    parser.add_argument("--year", type=int, default=2025, help="Calendar year (default: 2025)")
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--hours", type=int, default=24, help="Number of hourly rows to simulate (default: 24)")
    duration.add_argument("--full-year", action="store_true", help="Simulate all input rows")
    parser.add_argument("--start-row", type=int, default=0, help="First hourly row of a short run (default: 0)")
    parser.add_argument("--config", type=Path, help="JSON component parameters; omitted values keep example defaults")
    arguments = parser.parse_args(argv)
    if not (arguments.reference or arguments.report):
        parser.error("Give a reference workbook to compare with, --report, or both")
    if arguments.report and (arguments.report.exists() or not arguments.report.parent.is_dir()):
        parser.error(f"Output must be a new file in an existing directory: {arguments.report}")
    weather_path = arguments.weather or ROOT / f"input/WeerData/De Bilt {arguments.year}.csv"
    occupancy_path = arguments.occupancy or (
        ROOT / "input/Occupancy Data" / f"Occ{arguments.year}vac27to32and52.csv"
    )
    try:
        config_hash = file_hash(arguments.config) if arguments.config else None
        parameters = (ewf_tech_simulator.load_parameters(arguments.config) if arguments.config
                      else ewf_tech_simulator.example_parameters())
        frame, report = run_observed(
            weather_path, occupancy_path, arguments.year,
            hours=None if arguments.full_year else arguments.hours,
            start_row=arguments.start_row, parameters=parameters,
        )
        if arguments.config:
            if file_hash(arguments.config) != config_hash:
                raise RuntimeError("Parameter file changed during this run; discard the results")
            report["sha256"][str(arguments.config.resolve())] = config_hash
        if arguments.reference:
            report["export_comparison"] = compare_export(frame, arguments.reference)
            print(json.dumps(report["export_comparison"], indent=2))
        if arguments.report:
            with arguments.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=True, allow_nan=False)
                stream.write("\n")
            print(f"Run report: {arguments.report}")
    except (EWFException, OSError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(2, f"Run failed: {error}\n")
    energy_stage = report["stages"]["energy"]
    incomplete_year = arguments.full_year and energy_stage["rows"] != report["full_year_expected_rows"]
    comparison_failed = arguments.reference and not report["export_comparison"]["matches"]
    return 2 if energy_stage["nonfinite"] or incomplete_year or comparison_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
