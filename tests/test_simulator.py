"""Regression checks derived from the EWF audit, including explicit failure states."""

import inspect
import io
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
PARAMETER_FILE = ROOT / "input" / "simulation_parameters_python.json"
WEATHER_2025 = ROOT / "input" / "WeerData" / "De Bilt 2025.csv"
OCCUPANCY_2025 = ROOT / "input" / "Occupancy Data" / "Occ2025vac27to32and52.csv"

import numpy as np
import pandas as pd
from pydantic import ValidationError

import climate_cascade
import energy
import ewf_tech_simulator
import ewf_utils
import exceptions
import logger_config
import occupancy
import over_pressure_room
import solar_chimney
import ventec_roof
import weather
from exceptions import (
    ConfigurationError as LegacyConfigurationError,
)
from exceptions import (
    DataFileError,
    ProcessingError,
)
from exceptions import (
    DataValidationError as LegacyDataValidationError,
)
from schemas import CascadeFrame, CascadeParams

ConfigurationError = ValidationError
DataValidationError = ValidationError


def cascade_input(air_flow_office__m3_s_1=1.0):
    """One hour of mild weather with all columns consumed by the cascade."""
    return pd.DataFrame({
        "temp_overpressure_out__degC": [20.0],
        "temp_air_heat_recovery_in__degC": [21.0],
        "air_flow_office__m3_s_1": [air_flow_office__m3_s_1],
        "humidity_outdoor_rel__0": [0.5],
        "temp_outdoor__degC": [20.0],
        "overpressure_room_delta__Pa": [0.0],
        "eta_fan__W0": [0.72],
    })


class EnergyChecks(unittest.TestCase):
    def test_invalid_power_and_time_inputs_are_rejected(self):
        frames = [
            pd.DataFrame(),
            pd.DataFrame({'e_fan_supply__W': [-1.0]}),
            pd.DataFrame({'e_fan_supply__W': [np.inf]}),
            pd.DataFrame({'e_fan_supply__W': ['1000']}),
            pd.DataFrame({'e_fan_supply__W': [1.0, 2.0]}, index=[0, 0]),
            pd.DataFrame({'e_fan_supply__W': [1.0, 2.0]}, index=pd.date_range('2025-01-01', periods=2, freq='2h')),
        ]
        for frame in frames:
            with self.subTest(frame=frame):
                with self.assertRaises(DataValidationError):
                    energy.calculate_energy(frame)

    def test_multiple_components_integrate_without_extrapolation(self):
        frame = pd.DataFrame({'e_fan_supply__W': [1000.0, 2000.0], 'e_fan_exh__W': [500.0, 1000.0]})
        result, mean, total = energy.calculate_energy(frame)
        self.assertEqual(result['e__ewf_total__W'].tolist(), [1500.0, 3000.0])
        self.assertEqual(mean, 2250.0)
        self.assertEqual(total, 4.5)

    def test_one_kilowatt_for_one_hour_is_one_kwh(self):
        frame = pd.DataFrame({"e_fan_supply__W": [1000.0]})
        original = frame.copy(deep=True)
        result, mean, total = energy.calculate_energy(frame)
        self.assertEqual(mean, 1000.0)
        self.assertEqual(total, 1.0)
        self.assertEqual(result["e__ewf_total__W"].iloc[0], 1000.0)
        pd.testing.assert_frame_equal(frame, original)

    def test_missing_power_is_not_reported_as_complete_energy(self):
        frame = pd.DataFrame({"e_fan_supply__W": [1000.0, np.nan]})
        try:
            _, _, total = energy.calculate_energy(frame)
        except (ValueError, DataValidationError):
            return
        self.assertFalse(np.isfinite(total), "Incomplete measurements produced a finite total")

    def test_no_power_columns_is_not_reported_as_zero_energy(self):
        with self.assertRaises((ValueError, DataValidationError)):
            energy.calculate_energy(pd.DataFrame({"unrelated": [1.0]}))


class CascadeChecks(unittest.TestCase):
    def test_none_raises_declared_validation_error(self):
        with self.assertRaises(DataValidationError):
            climate_cascade.calculate_climate_cascade(None)

    def test_off_state_preserves_humidity_in_same_units(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = climate_cascade.calculate_climate_cascade(
                cascade_input(0.0), nozzles_min__0=0
            )
        self.assertAlmostEqual(
            result["humidity_cascade_out_abs__gr_kg_1"].iloc[0],
            result["humidity_cascade_in_abs__gr_kg_1"].iloc[0],
            places=10,
        )

    def test_off_state_does_not_divide_by_zero(self):
        with np.errstate(divide="raise", invalid="raise"):
            climate_cascade.calculate_climate_cascade(cascade_input(0.0), nozzles_min__0=0)

    def test_missing_fan_efficiency_has_validation_error(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with self.assertRaises(DataValidationError):
                climate_cascade.calculate_climate_cascade(
                    cascade_input(0.0).drop(columns="eta_fan__W0")
                )

    def test_empty_input_has_validation_error(self):
        with self.assertRaises(DataValidationError):
            climate_cascade.calculate_climate_cascade(cascade_input().iloc[:0])

    def test_equilibrium_segment_preserves_state(self):
        temperature = 20.0
        saturation = climate_cascade.c_0_vap__Pa * np.exp(
            climate_cascade.c_1_vap__0 - climate_cascade.c_2_vap__degC /
            (temperature + climate_cascade.c_3_vap__degC)
        )
        vapour = saturation / (climate_cascade.gas_constant_water__J_kg_1_K_1 *
                               (temperature + climate_cascade.temp_0_degC__K))
        result = climate_cascade.segment_equations(temperature, temperature, vapour, 0.1, 0.1, 0.1, 1.0)
        np.testing.assert_allclose(result, [temperature, temperature, vapour, 0.1], rtol=1e-12)

    def test_low_flow_does_not_return_nonfinite_state(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                result = climate_cascade.calculate_climate_cascade(
                    cascade_input(0.1), **ewf_tech_simulator.example_parameters()["climate_cascade"]
                )
            except ProcessingError as error:
                self.assertEqual(error.step, "cascade segment")
                self.assertIn("segment", error.data_info)
                return
        state = result[["temp_air_cascade_out__degC", "temp_water_cascade_out__degC",
                        "humidity_cascade_out_abs__gr_kg_1"]]
        self.assertTrue(np.isfinite(state.to_numpy()).all())

    def test_coarse_segments_do_not_produce_negative_humidity(self):
        parameters = ewf_tech_simulator.example_parameters()["climate_cascade"]
        parameters["cascade_segments__0"] = 10
        try:
            result = climate_cascade.calculate_climate_cascade(cascade_input(1.0), **parameters)
        except ProcessingError as error:
            self.assertEqual(error.step, "cascade segment")
            self.assertIn("nozzles", error.data_info)
            return
        self.assertGreaterEqual(result["humidity_cascade_out_abs__gr_kg_1"].iloc[0], 0.0)

    def test_nozzle_search_matches_exhaustive_candidates(self):
        parameters = ewf_tech_simulator.example_parameters()["climate_cascade"]
        parameters.update(nozzles_min__0=1, nozzles_max__0=12)
        for temperature in (5.0, 20.0, 35.0):
            with self.subTest(temperature=temperature):
                frame = cascade_input(29.16)
                frame["temp_outdoor__degC"] = temperature
                frame["temp_overpressure_out__degC"] = temperature
                chosen = climate_cascade.calculate_climate_cascade(frame, **parameters).iloc[0]
                acceptable = []
                for count in range(1, 13):
                    fixed = dict(parameters, nozzles_min__0=count, nozzles_max__0=count)
                    result = climate_cascade.calculate_climate_cascade(frame, **fixed).iloc[0]
                    summer = result["temp_air_cascade_in__degC"] >= parameters["temp_air_in_threshold__degC"]
                    too_many = (result["temp_air_cascade_out__degC"] < parameters["temp_air_cascade_out_set__degC"]
                                if summer else result["humidity_cascade_out_abs__gr_kg_1"] > parameters["humidity_abs_set__g_kg_1"])
                    if not too_many:
                        acceptable.append(count)
                self.assertEqual(chosen["nozzles__0"], max(acceptable) if acceptable else 1)


def roof_input(wind__m_s_1=2.0, air_flow_office__m3_s_1=1.0):
    return pd.DataFrame({
        "wind__m_s_1": [wind__m_s_1],
        "air_flow_office__m3_s_1": [air_flow_office__m3_s_1],
        "eta_fan__W0": [0.72],
        "chimney_delta__Pa": [200.0],
        "outdoor_chimney_delta__Pa": [200.0],
        "shunt_delta__Pa": [200.0],
    })


class PressureChecks(unittest.TestCase):
    def test_positive_flow_correlation_is_unchanged(self):
        for height, coefficient, offset in [(1.0, 0.5374, 0.6381), (2.0, 0.2913, 0.0151)]:
            result = ventec_roof.calculate_ventec_roof(roof_input(), venturi_throat_height__m=height)
            expected = coefficient * np.log(result['ejector__m_s_1'] / result['wind_venturi_accelerated__m_s_1']) + offset
            np.testing.assert_allclose(result['wind_venturi_pressure_coefficient__0'], expected, rtol=1e-12)

    def test_calm_and_off_states_have_no_floating_point_warnings(self):
        with np.errstate(all='raise'):
            for wind, flow in [(0.0, 0.0), (0.0, 1.0), (2.0, 0.0)]:
                result = ventec_roof.calculate_ventec_roof(roof_input(wind, flow))
                self.assertTrue(np.isfinite(result.to_numpy()).all())
                if flow == 0:
                    self.assertEqual(result['e_fan_exh__W'].iloc[0], 0.0)

    def test_calm_wind_has_finite_exhaust_power(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = ventec_roof.calculate_ventec_roof(roof_input(wind__m_s_1=0.0))
        self.assertTrue(np.isfinite(result["e_fan_exh__W"]).all())

    def test_no_flow_has_finite_venturi_pressure(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = ventec_roof.calculate_ventec_roof(roof_input(air_flow_office__m3_s_1=0.0))
        self.assertTrue(np.isfinite(result["venturi_draft__Pa"]).all())

    def test_unsupported_throat_height_is_rejected(self):
        with self.assertRaises((ValueError, ConfigurationError)):
            ventec_roof.calculate_ventec_roof(roof_input(), venturi_throat_height__m=1.5)

    def test_no_wind_gives_no_overpressure_and_preserves_input(self):
        frame = pd.DataFrame({"wind__m_s_1": [0.0], "temp_outdoor__degC": [20.0]})
        original = frame.copy(deep=True)
        result = over_pressure_room.calculate_overpressure_room(frame)
        self.assertEqual(result["overpressure_room_delta__Pa"].iloc[0], 0.0)
        pd.testing.assert_frame_equal(frame, original)

    def test_height_at_displacement_is_rejected(self):
        frame = pd.DataFrame({"wind__m_s_1": [2.0], "temp_outdoor__degC": [20.0]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            with self.assertRaises((ValueError, ConfigurationError)):
                over_pressure_room.calculate_overpressure_room(frame, wind_overpressure_inflow_height__m=10.0)


class DataChecks(unittest.TestCase):
    def test_concurrent_reads_preserve_source_and_neighbours(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'weather.csv'
            neighbour = Path(directory) / 'weather_temp.csv'
            pd.DataFrame({'value': [1, 2]}).to_csv(source, sep=';', index=False)
            pd.DataFrame({'other': [3]}).to_csv(neighbour, sep=';', index=False)
            before = (source.read_bytes(), neighbour.read_bytes())
            with ThreadPoolExecutor(max_workers=4) as workers:
                results = list(workers.map(weather.safe_read_csv, [source] * 8))
            for result in results:
                self.assertEqual(result['value'].tolist(), [1, 2])
            self.assertEqual(before, (source.read_bytes(), neighbour.read_bytes()))

    def test_owned_temp_directory_is_cleaned_after_parse_failure(self):
        directories = []
        original = tempfile.TemporaryDirectory

        def track_directory(*args, **kwargs):
            directory = original(*args, **kwargs)
            directories.append(Path(directory.name))
            return directory

        with original() as directory:
            source = Path(directory) / 'empty.csv'
            source.touch()
            with patch.object(weather.tempfile, 'TemporaryDirectory', side_effect=track_directory):
                with self.assertRaises(ProcessingError):
                    weather.safe_read_csv(source)
        self.assertTrue(directories)
        self.assertTrue(all(not directory.exists() for directory in directories))

    def test_read_permission_error_keeps_its_type(self):
        with patch.object(weather.shutil, 'copyfile', side_effect=PermissionError('denied')):
            with self.assertRaises(DataFileError) as caught:
                weather.retrieve_weather_data('unreadable.csv')
        self.assertEqual(caught.exception.error_code, 'E002')

    def test_weather_units_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weather.csv"
            pd.DataFrame({"FH": [25], "T": [125], "Q": [36], "P": [10132], "U": [50]}).to_csv(
                source, sep=";", index=False
            )
            original = source.read_bytes()
            result = weather.retrieve_weather_data(str(source))
            np.testing.assert_allclose(result.iloc[0], [2.5, 12.5, 100, 101320, 0.5])
            self.assertEqual(source.read_bytes(), original)

    def test_existing_adjacent_temp_file_is_not_destroyed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weather.csv"
            neighbour = Path(directory) / "weather_temp.csv"
            pd.DataFrame({"value": [1]}).to_csv(source, sep=";", index=False)
            pd.DataFrame({"valuable": [123]}).to_csv(neighbour, sep=";", index=False)
            original = neighbour.read_bytes()
            weather.safe_read_csv(str(source))
            self.assertTrue(neighbour.exists(), "An existing neighbouring file was deleted")
            self.assertEqual(neighbour.read_bytes(), original)

    def test_failed_csv_parse_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weather.csv"
            source.touch()
            with self.assertRaises(ProcessingError):
                weather.safe_read_csv(str(source))
            self.assertFalse((Path(directory) / "weather_temp.csv").exists())

    def test_weather_preserves_file_not_found_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DataFileError):
                weather.retrieve_weather_data(str(Path(directory) / "absent.csv"))

    def test_occupancy_does_not_silently_truncate_weather(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            source = Path(directory) / "occupancy.csv"
            pd.DataFrame({"occupancyperc": [50.0]}).to_csv(source, sep=";", decimal=",", index=False)
            frame = pd.DataFrame({"temp_outdoor__degC": [10.0, 11.0]})
            try:
                result = occupancy.calculate_occupancy(2025, str(source), frame)
            except DataValidationError:
                return
            self.assertEqual(len(result), len(frame))

    def test_occupancy_alignment_with_nondefault_index(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            source = Path(directory) / "occupancy.csv"
            pd.DataFrame({"occupancyperc": [50.0, 75.0]}).to_csv(source, sep=";", decimal=",", index=False)
            frame = pd.DataFrame({"temp_outdoor__degC": [10.0, 11.0]}, index=[10, 11])
            result = occupancy.calculate_occupancy(2025, str(source), frame)
            self.assertEqual(result["occupancy__perc"].tolist(), [50.0, 75.0])
            historical = occupancy.calculate_occupancy(1850, str(source), frame)
            self.assertEqual(historical['tijd met tijdzone'].iloc[0].year, 1850)
            with self.assertRaises(ConfigurationError):
                occupancy.calculate_occupancy(9999, str(source), frame)

    def test_partial_year_crossing_dst_has_correct_length(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            source = Path(directory) / "occupancy.csv"
            pd.DataFrame({"occupancyperc": np.full(3000, 50.0)}).to_csv(source, sep=";", decimal=",", index=False)
            frame = pd.DataFrame({"temp_outdoor__degC": np.full(3000, 10.0)})
            result = occupancy.calculate_occupancy(2025, str(source), frame)
            self.assertEqual(len(result), 3000)


class SolarChecks(unittest.TestCase):
    def solar_input(self):
        return pd.DataFrame({
            "tijd met tijdzone": pd.date_range("2025-06-21 12:00", periods=1, tz="Europe/Amsterdam"),
            "temp_outdoor__degC": [20.0],
            "air_flow_office__m3_s_1": [1.0],
            "sol_ghi__W_m_2": [500.0],
        })

    def test_solver_nominal_residual(self):
        residuals = []
        original_solver = solar_chimney.fsolve

        def observed_solver(function, initial_guess, args, **kwargs):
            result = original_solver(function, initial_guess, args=args, **kwargs)
            solution = result[0] if kwargs.get('full_output') else result
            residuals.append(np.max(np.abs(function(solution, *args))))
            return result

        with patch.object(solar_chimney, "fsolve", side_effect=observed_solver), redirect_stdout(io.StringIO()):
            result = solar_chimney.calculate_solar_chimney(self.solar_input(), solar_chimney_segments__0=2)
        self.assertTrue(np.isfinite(result["temp_air_chimney_out__degC"]).all())
        self.assertLess(max(residuals), 0.001, "Heat-balance numerical residual exceeds 1 mW per segment")

    def test_nondefault_index_is_supported(self):
        frame = self.solar_input()
        frame.index = [10]
        with redirect_stdout(io.StringIO()):
            result = solar_chimney.calculate_solar_chimney(frame, solar_chimney_segments__0=1)
        self.assertEqual(result.index.tolist(), [10])

    def test_cold_low_flow_nights_converge_with_checked_retry(self):
        for temperature in (3.2, 3.5):
            with self.subTest(temperature=temperature):
                frame = self.solar_input()
                frame['temp_outdoor__degC'] = temperature
                frame['air_flow_office__m3_s_1'] = 29.16 * 0.08
                frame['sol_ghi__W_m_2'] = 0.0
                with redirect_stdout(io.StringIO()):
                    result = solar_chimney.calculate_solar_chimney(frame, **ewf_tech_simulator.example_parameters()['solar_chimney'])
                self.assertTrue(np.isfinite(result['temp_air_chimney_out__degC']).all())
                self.assertGreater(result['temp_air_chimney_out__degC'].iloc[0], temperature)
                self.assertLess(result['temp_air_chimney_out__degC'].iloc[0], solar_chimney.temp_air_office_out__degC)

    def test_fractional_segment_count_is_rejected(self):
        with redirect_stdout(io.StringIO()):
            with self.assertRaises((ValueError, ConfigurationError)):
                solar_chimney.calculate_solar_chimney(self.solar_input(), solar_chimney_segments__0=1.5)

    def test_unconverged_solver_is_not_used(self):
        failed = (np.array([40.0, 50.0, 22.0]), {'fvec': np.array([10.0, 0.0, 0.0])}, 4, 'not converged')
        with patch.object(solar_chimney, 'fsolve', return_value=failed), redirect_stdout(io.StringIO()):
            with self.assertRaises(ProcessingError) as caught:
                solar_chimney.calculate_solar_chimney(self.solar_input(), solar_chimney_segments__0=1)
        self.assertEqual(caught.exception.data_info['solver_status'], 4)

    def test_large_residual_is_rejected_despite_success_status(self):
        failed = (np.array([40.0, 50.0, 22.0]), {'fvec': np.array([10.0, 0.0, 0.0])}, 1, 'converged')
        with patch.object(solar_chimney, 'fsolve', return_value=failed), redirect_stdout(io.StringIO()):
            with self.assertRaises(ProcessingError):
                solar_chimney.calculate_solar_chimney(self.solar_input(), solar_chimney_segments__0=1)


class IntegrationChecks(unittest.TestCase):

    def test_snapshot_core_dimensions_and_throat(self):
        tree = ET.parse(ROOT / "ewf_tech_simulator.ghx")
        for component_index in (106, 107, 108, 109, 110, 111, 112, 123):
            component = tree.find(f".//chunk[@name='Object'][@index='{component_index}']")
            self.assertEqual(float(component.find(".//item[@name='number']").text), 1000.0)
        selected = tree.find(".//chunk[@name='Object'][@index='55']")
        selected_items = [chunk for chunk in selected.iter("chunk")
                          if chunk.find("./items/item[@name='Selected']") is not None
                          and chunk.find("./items/item[@name='Selected']").text == "true"]
        self.assertEqual(len(selected_items), 1)
        self.assertEqual(float(selected_items[0].find("./items/item[@name='Expression']").text), 1000.0)

    def test_grasshopper_pipeline_order(self):
        components = {int(component.attrib['index']): component
                      for component in ET.parse(ROOT / 'ewf_tech_simulator.ghx').findall(".//chunk[@name='Object']")}
        output_owners = {}
        for index, component in components.items():
            for output in component.findall(".//chunk[@name='OutputParam']"):
                output_owners[output.findtext("./items/item[@name='InstanceGuid']")] = index
        pipeline = set()
        for index, component in components.items():
            for parameter in component.findall(".//chunk[@name='InputParam']"):
                if parameter.findtext("./items/item[@name='Name']") == '_df':
                    for source in parameter.findall("./items/item[@name='Source']"):
                        pipeline.add((output_owners[source.text], index))
        self.assertEqual(pipeline, {(97, 99), (99, 102), (102, 103), (103, 100), (100, 101), (101, 104), (104, 166)})

    def test_export_comparison_detects_changed_values(self):
        frame = pd.DataFrame({"e__ewf_total__W": [1000.0, np.nan], "label": ["first", "second"]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.xlsx"
            frame.to_excel(path, sheet_name="Outputdata", index=False)
            self.assertTrue(ewf_tech_simulator.compare_export(frame, path)["matches"])
            frame.loc[0, "e__ewf_total__W"] = 1001.0
            self.assertFalse(ewf_tech_simulator.compare_export(frame, path)["matches"])

    def test_runner_repeatability_and_no_input_mutation(self):
        arguments = (ROOT / "input/WeerData/De Bilt 2025.csv", ROOT / "input/Occupancy Data/Occ2025vac27to32and52.csv", 2025)
        first, first_report = ewf_tech_simulator.run_simulation(*arguments, hours=2)
        second, second_report = ewf_tech_simulator.run_simulation(*arguments, hours=2)
        pd.testing.assert_frame_equal(first, second, check_exact=True)
        self.assertEqual(first_report["sha256"], second_report["sha256"])
        self.assertEqual(list(first_report["stages"]), [
            "weather", "occupancy", "solar_chimney", "ventec_roof",
            "over_pressure_room", "climate_cascade", "energy"
        ])


class CommandLineChecks(unittest.TestCase):
    def test_example_configuration_matches_defaults(self):
        parameters = ewf_tech_simulator.load_parameters(PARAMETER_FILE)
        self.assertEqual(parameters, ewf_tech_simulator.example_parameters())

    def test_partial_configuration_preserves_other_defaults(self):
        defaults = ewf_tech_simulator.example_parameters()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'parameters.json'
            path.write_text(json.dumps({'occupancy': {'occupancy_mean__p': 200}}), encoding='utf-8')
            parameters = ewf_tech_simulator.load_parameters(path)
        self.assertEqual(parameters['occupancy']['occupancy_mean__p'], 200)
        self.assertNotEqual(defaults['occupancy']['occupancy_mean__p'], 200)
        self.assertEqual(parameters['solar_chimney'], defaults['solar_chimney'])

    def test_invalid_configuration_is_rejected(self):
        invalid = [[], {'unknown': {}}, {'occupancy': []},
                   {'occupancy': {'wrong_name': 100}}, {'occupancy': {'occupancy_mean__p': True}},
                   {'occupancy': {'occupancy_mean__p': float('inf')}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'parameters.json'
            for configuration in invalid:
                with self.subTest(configuration=configuration):
                    path.write_text(json.dumps(configuration), encoding='utf-8')
                    with self.assertRaises((TypeError, ValueError)):
                        ewf_tech_simulator.load_parameters(path)

    def test_cli_runs_from_another_directory_and_exports_results(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory)
            report_path = Path(directory) / 'run.json'
            result = subprocess.run([
                sys.executable, '-B', str(ROOT / 'ewf_tech_simulator.py'), '--hours', '2',
                '--config', str(PARAMETER_FILE),
                '--xlsx', str(csv_path), '--report', str(report_path),
            ], cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            exported = list(csv_path.glob('*-ewf-sim-data_total.xlsx'))
            self.assertEqual(len(exported), 1)
            self.assertEqual(len(pd.read_excel(exported[0], sheet_name='Outputdata')), 2)
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['stages']['energy']['rows'], 2)
            self.assertFalse(any(Path(path).suffix in ('.ghx', '.md') for path in report['sha256']))
            self.assertIn(str(PARAMETER_FILE.resolve()), report['sha256'])

    def test_cli_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing'
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                ewf_tech_simulator.main(['--xlsx', str(path)])
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse(path.exists())

    def test_cli_reports_missing_input_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            messages = io.StringIO()
            with redirect_stderr(messages), self.assertRaises(SystemExit) as caught:
                ewf_tech_simulator.main(['--weather', str(Path(directory) / 'missing.csv')])
            self.assertEqual(caught.exception.code, 2)
            self.assertIn('Simulation failed:', messages.getvalue())
            self.assertNotIn('Traceback', messages.getvalue())


class UtilityChecks(unittest.TestCase):
    def test_occupancy_generator_compiles_on_documented_python(self):
        path = ROOT / "input/Occupancy Data/Occupancy Data Aanmaken/main.py"
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_generated_occupancy_file_matches_loader_schema(self):
        path = ROOT / "input/Occupancy Data/Occupancy Data Aanmaken/Occupancy.csv"
        frame = pd.read_csv(path, sep=";", decimal=",")
        weather_frame = pd.DataFrame({'temp_outdoor__degC': np.full(len(frame), 20.0)})
        result = occupancy.calculate_occupancy(2025, str(path), weather_frame)
        self.assertEqual(result['occupancy__perc'].tolist(), frame['occupancy(perc)'].tolist())

    def test_reconfiguring_logger_closes_previous_file_handler(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.log'
            first = logger_config.get_logger('ewf-audit-handlers', log_file=str(path))
            handler = first.logger.handlers[-1]
            first.info('before reconfiguration')
            second = logger_config.get_logger('ewf-audit-handlers')
            self.assertIsNone(handler.stream)
            self.assertEqual(len(second.logger.handlers), 1)

    def test_validation_message_includes_bad_value(self):
        error = exceptions.create_data_validation_error("humidity", "fraction", actual_value=123.0)
        self.assertIn("123", str(error) + str(error.details))

    def test_logger_can_use_filename_without_directory(self):
        with patch.object(logger_config.logging, "FileHandler"), patch.object(logger_config.os, "makedirs") as mkdir:
            logger_config.get_logger("ewf-audit-check", log_file="audit.log")
            self.assertNotIn(unittest.mock.call("", exist_ok=True), mkdir.call_args_list)


class EnergyComponentChecks(unittest.TestCase):
    POWER_COLUMNS = [
        "e_cascade_heat_pump__W", "e_post_cascade_heat_pump__W", "e_cascade_water_pump__W",
        "e_fan_supply__W", "e_fan_exh__W", "e_fan_heat_recovery__W",
    ]

    def test_all_known_power_columns_are_summed(self):
        frame = pd.DataFrame({name: [float(2 ** i)] for i, name in enumerate(self.POWER_COLUMNS)})
        frame["unrelated__W"] = 1e6
        result, _, _ = energy.calculate_energy(frame)
        self.assertEqual(result["e__ewf_total__W"].iloc[0], 63.0)

    def test_each_power_column_is_validated(self):
        for name in self.POWER_COLUMNS:
            with self.subTest(column=name):
                with self.assertRaises(DataValidationError):
                    energy.calculate_energy(pd.DataFrame({name: [1.0, -1.0]}))

    def test_hourly_datetime_index_is_accepted(self):
        index = pd.date_range("2025-01-01", periods=3, freq="h")
        frame = pd.DataFrame({"e_fan_supply__W": [1000.0, 2000.0, 3000.0]}, index=index)
        _, mean, total = energy.calculate_energy(frame)
        self.assertEqual(mean, 2000.0)
        self.assertEqual(total, 6.0)

    def test_non_dataframe_is_rejected(self):
        with self.assertRaises(DataValidationError):
            energy.calculate_energy(None)


class CascadeBehaviourChecks(unittest.TestCase):
    def parameters(self):
        return ewf_tech_simulator.example_parameters()["climate_cascade"]

    def test_invalid_input_values_are_rejected(self):
        cases = [
            ("air_flow_office__m3_s_1", -1.0), ("humidity_outdoor_rel__0", 1.5),
            ("humidity_outdoor_rel__0", -0.1), ("eta_fan__W0", 0.0), ("eta_fan__W0", 1.5),
            ("temp_outdoor__degC", np.nan), ("temp_outdoor__degC", np.inf),
            ("temp_overpressure_out__degC", -300.0), ("temp_outdoor__degC", -235.0),
        ]
        for column, value in cases:
            with self.subTest(column=column, value=value):
                frame = cascade_input(0.0)
                frame[column] = value
                with self.assertRaises(DataValidationError):
                    climate_cascade.calculate_climate_cascade(frame)

    def test_non_numeric_and_duplicate_index_inputs_are_rejected(self):
        frame = cascade_input(0.0)
        frame["eta_fan__W0"] = "0.72"
        with self.assertRaises(DataValidationError):
            climate_cascade.calculate_climate_cascade(frame)
        duplicated = pd.concat([cascade_input(0.0)] * 2)
        with self.assertRaises(DataValidationError):
            climate_cascade.calculate_climate_cascade(duplicated)

    def test_invalid_configuration_is_rejected(self):
        invalid = [
            {"cascade_segments__0": 0}, {"cascade_segments__0": 1.5}, {"cascade_segments__0": True},
            {"nozzles_min__0": 5, "nozzles_max__0": 2}, {"nozzles_min__0": -1},
            {"height_cascade__m": -1.0}, {"cascade_width__m": 0.0}, {"cascade_depth__m": np.nan},
            {"temp_water_cascade_in__degC": np.inf}, {"humidity_abs_set__g_kg_1": -1.0},
            {"loss_cascade_water_nozzle__Pa": -1.0}, {"temp_water_cascade_in__degC": -235.0},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ConfigurationError):
                    climate_cascade.calculate_climate_cascade(cascade_input(0.0), **overrides)

    def test_zero_flow_uses_minimum_nozzles_and_draws_no_air_power(self):
        result = climate_cascade.calculate_climate_cascade(
            cascade_input(0.0), nozzles_min__0=3, nozzles_max__0=10
        ).iloc[0]
        self.assertEqual(result["nozzles__0"], 3)
        self.assertEqual(result["temp_air_cascade_out__degC"], result["temp_air_cascade_in__degC"])
        self.assertEqual(result["e_fan_supply__W"], 0.0)
        self.assertEqual(result["e_post_cascade_heat_pump__W"], 0.0)

    def test_heat_recovery_preheats_cold_air_up_to_maximum(self):
        cases = [(5.0, 21.0, 13.0), (10.0, 30.0, 18.0), (20.0, 30.0, 20.0)]
        for outside, recovery, expected in cases:
            with self.subTest(outside=outside):
                frame = cascade_input(0.0)
                frame["temp_overpressure_out__degC"] = outside
                frame["temp_air_heat_recovery_in__degC"] = recovery
                result = climate_cascade.calculate_climate_cascade(frame)
                self.assertAlmostEqual(result["temp_air_cascade_in__degC"].iloc[0], expected)

    def test_nominal_run_respects_limits_and_preserves_input(self):
        parameters = self.parameters()
        for temperature in (5.0, 25.0):
            with self.subTest(temperature=temperature):
                frame = cascade_input(29.16)
                frame["temp_outdoor__degC"] = temperature
                frame["temp_overpressure_out__degC"] = temperature
                original = frame.copy(deep=True)
                result = climate_cascade.calculate_climate_cascade(frame, **parameters)
                pd.testing.assert_frame_equal(frame, original)
                row = result.iloc[0]
                self.assertGreaterEqual(row["nozzles__0"], parameters["nozzles_min__0"])
                self.assertLessEqual(row["nozzles__0"], parameters["nozzles_max__0"])
                self.assertAlmostEqual(row["water_cascade__kg_s_1"], climate_cascade.nozzle__kg_s_1 * row["nozzles__0"])
                self.assertAlmostEqual(row["cascade_delta__Pa"], row["cascade_delta_hydro__Pa"] + row["cascade_delta_therm__Pa"])
                numeric = result.select_dtypes(include=[np.number]).to_numpy()
                self.assertTrue(np.isfinite(numeric).all())
                for column in ("e_fan_supply__W", "e_cascade_water_pump__W",
                               "e_cascade_heat_pump__W", "e_post_cascade_heat_pump__W", "supply_fan__Pa"):
                    self.assertGreaterEqual(row[column], 0.0, column)


class RoofAndPressureValidationChecks(unittest.TestCase):
    def test_invalid_roof_input_is_rejected(self):
        for column in ("wind__m_s_1", "air_flow_office__m3_s_1", "eta_fan__W0", "chimney_delta__Pa"):
            with self.subTest(missing=column):
                with self.assertRaises(DataValidationError):
                    ventec_roof.calculate_ventec_roof(roof_input().drop(columns=column))
        for column, value in [("wind__m_s_1", -1.0), ("air_flow_office__m3_s_1", -1.0),
                              ("eta_fan__W0", 0.0), ("eta_fan__W0", 1.1), ("shunt_delta__Pa", np.nan)]:
            with self.subTest(column=column, value=value):
                frame = roof_input()
                frame[column] = value
                with self.assertRaises(DataValidationError):
                    ventec_roof.calculate_ventec_roof(frame)
        for frame in (None, roof_input().iloc[:0], pd.concat([roof_input()] * 2)):
            with self.assertRaises(DataValidationError):
                ventec_roof.calculate_ventec_roof(frame)

    def test_invalid_roof_configuration_is_rejected(self):
        displacement_plus_roughness = (
            ewf_utils.wind_local_displacement_height__m + ewf_utils.wind_local_roughness_length__m
        )
        invalid = [{"venturi_ejector_height__m": displacement_plus_roughness},
                   {"venturi_ejector_opening__m2": 0.0}, {"venturi_throat_height__m": True},
                   {"venturi_ejector_height__m": np.nan}]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ConfigurationError):
                    ventec_roof.calculate_ventec_roof(roof_input(), **overrides)

    def test_exhaust_fan_power_follows_pressure_balance(self):
        frame = roof_input()
        frame["chimney_delta__Pa"] = 30.0
        frame["outdoor_chimney_delta__Pa"] = 25.0
        frame["shunt_delta__Pa"] = 20.0
        original = frame.copy(deep=True)
        result = ventec_roof.calculate_ventec_roof(frame).iloc[0]
        expected_pressure = max(0.0, ventec_roof.exhaust__Pa + 30.0 - min(25.0, 20.0) + result["venturi_draft__Pa"])
        self.assertAlmostEqual(result["exhaust_fan__Pa"], expected_pressure)
        self.assertAlmostEqual(result["e_fan_exh__W"], expected_pressure * 1.0 / 0.72)
        pd.testing.assert_frame_equal(frame, original)

    def test_overpressure_only_above_wind_threshold(self):
        height = 50.0
        profile = (ewf_utils.wind_correction_factor__0 * ewf_utils.venturi_wind_acceleration__0 *
                   np.log((height - ewf_utils.wind_local_displacement_height__m) /
                          ewf_utils.wind_local_roughness_length__m))
        frame = pd.DataFrame({"wind__m_s_1": [0.5 / profile, 10.0], "temp_outdoor__degC": [8.0, 8.0]})
        result = over_pressure_room.calculate_overpressure_room(frame, wind_overpressure_inflow_height__m=height)
        self.assertEqual(result["overpressure_room_delta__Pa"].iloc[0], 0.0)
        inflow = 10.0 * profile
        expected = (0.5 * over_pressure_room.wind_overpressure_coefficient__0 *
                    ewf_utils.air_20C__kg_m_3 * inflow ** 2)
        self.assertAlmostEqual(result["overpressure_room_delta__Pa"].iloc[1], expected)
        self.assertAlmostEqual(result["wind_overpressure_inflow__m_s_1"].iloc[1], inflow)
        self.assertEqual(result["temp_overpressure_out__degC"].tolist(), [8.0, 8.0])

    def test_invalid_overpressure_input_is_rejected(self):
        valid = pd.DataFrame({"wind__m_s_1": [2.0], "temp_outdoor__degC": [20.0]})
        for frame in (None, valid.iloc[:0], valid.drop(columns="temp_outdoor__degC"),
                      valid.assign(wind__m_s_1=-1.0), valid.assign(temp_outdoor__degC=np.nan)):
            with self.assertRaises(DataValidationError):
                over_pressure_room.calculate_overpressure_room(frame)
        for height in (True, np.nan, 5.0):
            with self.assertRaises(ConfigurationError):
                over_pressure_room.calculate_overpressure_room(valid, wind_overpressure_inflow_height__m=height)


class WeatherValidationChecks(unittest.TestCase):
    VALID = {"FH": [25, 30], "T": [125, 130], "Q": [36, 0], "P": [10132, 10140], "U": [50, 100]}

    def read(self, data):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "weather.csv"
            pd.DataFrame(data).to_csv(source, sep=";", index=False)
            return weather.retrieve_weather_data(str(source))

    def test_invalid_weather_content_is_rejected(self):
        broken = {
            "missing column": {k: v for k, v in self.VALID.items() if k != "Q"},
            "negative wind": dict(self.VALID, FH=[-1, 30]),
            "negative radiation": dict(self.VALID, Q=[-1, 0]),
            "zero pressure": dict(self.VALID, P=[0, 10140]),
            "humidity above 100": dict(self.VALID, U=[50, 101]),
            "text value": dict(self.VALID, T=["warm", "cold"]),
            "missing value": dict(self.VALID, T=[125, None]),
            "no rows": {k: [] for k in self.VALID},
        }
        for label, data in broken.items():
            with self.subTest(label):
                with self.assertRaises(DataValidationError):
                    self.read(data)

    def test_invalid_paths_are_rejected(self):
        for path in (None, "", "   ", "<null>"):
            with self.subTest(path=path):
                with self.assertRaises(DataValidationError):
                    weather.safe_read_csv(path)

    def test_output_columns_and_conversions(self):
        result = self.read(self.VALID)
        self.assertEqual(list(result.columns), [
            "wind__m_s_1", "temp_outdoor__degC", "sol_ghi__W_m_2", "Air_outdoor__Pa", "humidity_outdoor_rel__0"
        ])
        np.testing.assert_allclose(result.iloc[1], [3.0, 13.0, 0.0, 101400.0, 1.0])

    def test_bundled_weather_and_occupancy_files_have_matching_lengths(self):
        for year in range(2020, 2026):
            with self.subTest(year=year):
                weather_frame = weather.retrieve_weather_data(str(ROOT / "input" / "WeerData" / f"De Bilt {year}.csv"))
                occupancy_path = ROOT / "input" / "Occupancy Data" / f"Occ{year}vac27to32and52.csv"
                with redirect_stdout(io.StringIO()):
                    result = occupancy.calculate_occupancy(year, str(occupancy_path), weather_frame)
                self.assertEqual(len(result), len(weather_frame))
                self.assertTrue(weather_frame["humidity_outdoor_rel__0"].between(0, 1).all())


class OccupancyBehaviourChecks(unittest.TestCase):
    def run_occupancy(self, columns, weather_rows=None, year=2025, **kwargs):
        length = len(next(iter(columns.values())))
        frame = pd.DataFrame({"temp_outdoor__degC": np.full(weather_rows or length, 10.0)})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "occupancy.csv"
            pd.DataFrame(columns).to_csv(source, sep=";", decimal=",", index=False)
            with redirect_stdout(io.StringIO()):
                return occupancy.calculate_occupancy(year, str(source), frame, **kwargs)

    def test_flow_and_fan_efficiency_follow_occupancy(self):
        result = self.run_occupancy({"occupancyperc": [0.0, 50.0, 100.0]}, occupancy_mean__p=100)
        maximum = 100 * ewf_utils.air_flow_office_set__dm3_s_1_p_1 / ewf_utils.dm3_m_3
        minimum = maximum * ewf_utils.flow_modulation_depth__0
        np.testing.assert_allclose(result["air_flow_office_set__m3_s_1"], [0.0, 0.5 * maximum, maximum])
        np.testing.assert_allclose(result["air_flow_office__m3_s_1"], [minimum, 0.5 * maximum, maximum])
        self.assertAlmostEqual(result["eta_fan__W0"].iloc[2], ewf_utils.eta_fan_max__W0)
        self.assertAlmostEqual(result["eta_fan__W0"].iloc[0], ewf_utils.eta_fan_min__W0)

    def test_time_column_is_hourly_and_timezone_aware(self):
        result = self.run_occupancy({"occupancyperc": [10.0, 20.0]})
        self.assertEqual(str(result["tijd met tijdzone"].iloc[0]), "2025-01-01 00:00:00+01:00")
        self.assertEqual(result["tijd met tijdzone"].diff().iloc[1], pd.Timedelta(hours=1))

    def test_hour_count_must_match_weather(self):
        with self.assertRaises(DataValidationError):
            self.run_occupancy({"occupancyperc": [10.0, 20.0]}, weather_rows=3)

    def test_occupancy_must_be_a_percentage(self):
        for values in ([-1.0, 50.0], [50.0, 100.5], [50.0, np.nan]):
            with self.subTest(values=values):
                with self.assertRaises(DataValidationError):
                    self.run_occupancy({"occupancyperc": values})

    def test_missing_occupancy_column_is_rejected(self):
        with self.assertRaises(DataValidationError):
            self.run_occupancy({"other": [1.0, 2.0]})

    def test_alternative_column_name_is_accepted_but_must_agree(self):
        result = self.run_occupancy({"occupancy(perc)": [10.0, 20.0]})
        self.assertEqual(result["occupancy__perc"].tolist(), [10.0, 20.0])
        with self.assertRaises(DataValidationError):
            self.run_occupancy({"occupancyperc": [10.0, 20.0], "occupancy(perc)": [10.0, 30.0]})

    def test_supplied_timestamps_must_match_calendar(self):
        correct = pd.date_range("2025-01-01", periods=2, freq="h", tz="Europe/Amsterdam").strftime("%Y-%m-%d %H:%M:%S%z")
        result = self.run_occupancy({"occupancyperc": [10.0, 20.0], "date and time": list(correct)})
        self.assertEqual(len(result), 2)
        shifted = ["2025-01-01 05:00:00+0100", "2025-01-01 06:00:00+0100"]
        with self.assertRaises(DataValidationError):
            self.run_occupancy({"occupancyperc": [10.0, 20.0], "date and time": shifted})

    def test_invalid_arguments_are_rejected(self):
        for mean in (0, -5, True, np.nan, np.inf):
            with self.subTest(mean=mean):
                with self.assertRaises(ConfigurationError):
                    self.run_occupancy({"occupancyperc": [10.0, 20.0]}, occupancy_mean__p=mean)
        for year in (2025.5, True, np.nan):
            with self.subTest(year=year):
                with self.assertRaises(ConfigurationError):
                    self.run_occupancy({"occupancyperc": [10.0, 20.0]}, year=year)
        with self.assertRaises(DataValidationError):
            occupancy.calculate_occupancy(2025, "unused.csv", pd.DataFrame())

    def test_more_than_one_calendar_year_is_rejected(self):
        with self.assertRaises(DataValidationError):
            self.run_occupancy({"occupancyperc": np.full(8800, 50.0)})

    def test_missing_file_raises_file_error(self):
        frame = pd.DataFrame({"temp_outdoor__degC": [10.0]})
        with self.assertRaises(DataFileError):
            occupancy.calculate_occupancy(2025, str(ROOT / "absent.csv"), frame)


class SolarValidationChecks(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({
            "tijd met tijdzone": pd.date_range("2025-06-21 12:00", periods=1, tz="Europe/Amsterdam"),
            "temp_outdoor__degC": [20.0],
            "air_flow_office__m3_s_1": [1.0],
            "sol_ghi__W_m_2": [500.0],
        })

    def calculate(self, frame, **kwargs):
        kwargs.setdefault("solar_chimney_segments__0", 1)
        with redirect_stdout(io.StringIO()):
            return solar_chimney.calculate_solar_chimney(frame, **kwargs)

    def test_invalid_input_is_rejected(self):
        valid = self.frame()
        naive = valid.assign(**{"tijd met tijdzone": valid["tijd met tijdzone"].dt.tz_localize(None)})
        cases = [
            valid.drop(columns="sol_ghi__W_m_2"), valid.drop(columns="tijd met tijdzone"), naive,
            valid.assign(sol_ghi__W_m_2=-1.0), valid.assign(air_flow_office__m3_s_1=-1.0),
            valid.assign(temp_outdoor__degC=np.nan), valid.assign(temp_outdoor__degC=-300.0),
            valid.iloc[:0], pd.concat([valid] * 2), None,
        ]
        for index, frame in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(DataValidationError):
                    self.calculate(frame)

    def test_invalid_configuration_is_rejected(self):
        invalid = [
            {"solar_chimney_segments__0": 0}, {"solar_chimney_segments__0": True},
            {"glazing__pct": 101}, {"glazing_transmittance__0": 1.5},
            {"weather_location__degN": 91}, {"weather_location__degE": 181},
            {"solar_chimney_height__m": 0}, {"solar_chimney_width__m": -1},
            {"solar_chimney_depth__m": np.nan}, {"solar_chimney_azimuth__degN": np.inf},
            {"solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1": 0},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ConfigurationError):
                    self.calculate(self.frame(), **overrides)

    def test_outputs_and_input_preservation(self):
        frame = self.frame()
        original = frame.copy(deep=True)
        result = self.calculate(frame)
        pd.testing.assert_frame_equal(frame, original)
        for column in ("azimut", "elevatie", "instralingsfactor", "temp_air_chimney_out__degC",
                       "temp_air_chimney_average__degC", "chimney_delta__Pa", "shunt_delta__Pa",
                       "outdoor_chimney_delta__Pa", "temp_air_heat_recovery_in__degC"):
            self.assertIn(column, result)
        self.assertEqual(result["tijd met tijdzone"].iloc[0], "21-06-2025 12:00 +0200")
        self.assertEqual(result["temp_air_heat_recovery_in__degC"].iloc[0],
                         result["temp_air_chimney_out__degC"].iloc[0])

    def test_sun_on_wrong_side_gives_no_irradiation(self):
        south = self.calculate(self.frame(), solar_chimney_azimuth__degN=180.0)
        north = self.calculate(self.frame(), solar_chimney_azimuth__degN=0.0)
        self.assertGreater(south["instralingsfactor"].iloc[0], 0.0)
        self.assertEqual(north["instralingsfactor"].iloc[0], 0.0)
        self.assertGreater(south["temp_air_chimney_out__degC"].iloc[0],
                           north["temp_air_chimney_out__degC"].iloc[0])


class RunnerChecks(unittest.TestCase):
    def test_example_parameters_match_function_signatures(self):
        functions = {
            "occupancy": occupancy.calculate_occupancy, "solar_chimney": solar_chimney.calculate_solar_chimney,
            "ventec_roof": ventec_roof.calculate_ventec_roof,
            "over_pressure_room": over_pressure_room.calculate_overpressure_room,
            "climate_cascade": climate_cascade.calculate_climate_cascade,
        }
        parameters = ewf_tech_simulator.example_parameters()
        self.assertEqual(set(parameters), set(functions))
        for component, function in functions.items():
            with self.subTest(component=component):
                positional = [None, None, None] if component == "occupancy" else [None]
                inspect.signature(function).bind(*positional, **parameters[component])

    def test_invalid_run_arguments_are_rejected(self):
        for kwargs in ({"hours": 0}, {"hours": -3}, {"start_row": -1}, {"hours": None, "start_row": 5}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ewf_tech_simulator.run_simulation(WEATHER_2025, OCCUPANCY_2025, 2025, **kwargs)

    def test_slice_beyond_available_data_is_rejected(self):
        with self.assertRaises(ValueError):
            ewf_tech_simulator.run_simulation(WEATHER_2025, OCCUPANCY_2025, 2025, hours=2, start_row=1_000_000)

    def test_start_row_selects_later_hours_with_fresh_index(self):
        frame, report = ewf_tech_simulator.run_simulation(WEATHER_2025, OCCUPANCY_2025, 2025, hours=2, start_row=5)
        self.assertEqual(frame.index.tolist(), [0, 1])
        self.assertEqual(frame["tijd met tijdzone"].iloc[0], "01-01-2025 05:00 +0100")
        self.assertEqual(report["start_row"], 5)
        self.assertEqual(report["requested_hours"], 2)
        self.assertEqual(report["full_year_expected_rows"], 8760)
        self.assertEqual(report["rows_with_nonfinite_total"], 0)
        self.assertTrue(np.isfinite(frame["e__ewf_total__W"]).all())

    def test_leap_year_report_expects_extra_day(self):
        weather_2024 = ROOT / "input" / "WeerData" / "De Bilt 2024.csv"
        occupancy_2024 = ROOT / "input" / "Occupancy Data" / "Occ2024vac27to32and52.csv"
        _, report = ewf_tech_simulator.run_simulation(weather_2024, occupancy_2024, 2024, hours=1)
        self.assertEqual(report["full_year_expected_rows"], 8784)

    def test_custom_parameters_change_the_result(self):
        parameters = ewf_tech_simulator.example_parameters()
        parameters["occupancy"]["occupancy_mean__p"] = 6000
        base, _ = ewf_tech_simulator.run_simulation(WEATHER_2025, OCCUPANCY_2025, 2025, hours=1)
        large, _ = ewf_tech_simulator.run_simulation(WEATHER_2025, OCCUPANCY_2025, 2025, hours=1, parameters=parameters)
        self.assertGreater(large["air_flow_office__m3_s_1"].iloc[0], base["air_flow_office__m3_s_1"].iloc[0])

    def test_frame_summary_counts_nonfinite_values(self):
        frame = pd.DataFrame({"a": [1.0, np.nan, np.inf], "b": ["x", "y", "z"]})
        summary = ewf_tech_simulator.frame_summary(frame)
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["nonfinite"], {"a": 2})
        self.assertEqual(len(summary["first_rows"]), 3)

    def test_file_hash_and_package_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.txt"
            path.write_bytes(b"abc")
            self.assertEqual(
                ewf_tech_simulator.file_hash(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )
        self.assertIsNotNone(ewf_tech_simulator.package_version("numpy"))
        self.assertIsNone(ewf_tech_simulator.package_version("ewf-no-such-distribution"))

    def test_export_comparison_reports_column_and_length_differences(self):
        frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.xlsx"
            frame.to_excel(path, sheet_name="Outputdata", index=False)
            comparison = ewf_tech_simulator.compare_export(frame.drop(columns="b").assign(c=1.0), path)
            self.assertEqual(comparison["missing_columns"], ["b"])
            self.assertEqual(comparison["extra_columns"], ["c"])
            self.assertFalse(comparison["matches"])
            self.assertFalse(ewf_tech_simulator.compare_export(frame.iloc[:1], path)["matches"])

    def test_export_xlsx_layout(self):
        frame = pd.DataFrame({"e__ewf_total__W": [1000.0, 2000.0]})
        with tempfile.TemporaryDirectory() as directory:
            path = ewf_tech_simulator.export_xlsx(
                frame, directory, ewf_tech_simulator.example_parameters(), 2025, 1500.0, 3.0, auteur="Tester",
            )
            self.assertTrue(path.name.endswith("-ewf-sim-data_total.xlsx"))
            sheets = pd.read_excel(path, sheet_name=None, header=None)
            self.assertEqual(list(sheets), ["Info", "Inputdata", "Outputdata"])
            info = sheets["Info"].set_index(0)[1]
            self.assertEqual(info["Auteur:"], "Tester")
            self.assertEqual(str(info["Berekend jaar:"]), "2025")
            inputdata = sheets["Inputdata"]
            self.assertEqual(inputdata.iloc[0].tolist(), ["Parameter", "Waarde", "Eenheid"])
            self.assertEqual(inputdata.iloc[-1].tolist(), ["Berekende energieverbruik", 3.0, "kWh"])
            self.assertEqual(len(sheets["Outputdata"]), 3)

    def test_export_xlsx_requires_existing_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                ewf_tech_simulator.export_xlsx(
                    pd.DataFrame({"a": [1]}), Path(directory) / "absent",
                    ewf_tech_simulator.example_parameters(), 2025, 0.0, 0.0,
                )

    def test_unknown_parameter_value_types_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parameters.json"
            for value in ("200", None, [1]):
                with self.subTest(value=value):
                    path.write_text(json.dumps({"occupancy": {"occupancy_mean__p": value}}), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        ewf_tech_simulator.load_parameters(path)


class SchemaChecks(unittest.TestCase):
    def cascade_parameters(self):
        return {
            "height_cascade__m": 10.0,
            "cascade_width__m": 3.0,
            "cascade_depth__m": 2.0,
            "cascade_segments__0": 10,
            "temp_water_cascade_in__degC": 13.0,
            "temp_air_in_threshold__degC": 16.0,
            "temp_air_cascade_out_set__degC": 17.0,
            "humidity_abs_set__g_kg_1": 6.93,
            "nozzles_min__0": 1,
            "nozzles_max__0": 25,
            "loss_cascade_water_nozzle__Pa": 50000.0,
        }

    def test_integer_parameters_reject_fractional_values_and_booleans(self):
        for value in (1.5, True):
            with self.subTest(value=value):
                parameters = self.cascade_parameters()
                parameters["cascade_segments__0"] = value
                with self.assertRaises(ValidationError) as caught:
                    CascadeParams(**parameters)
                self.assertIn("cascade_segments__0", str(caught.exception))

    def test_numeric_parameters_reject_text_and_nonfinite_values(self):
        for value in ("10", np.inf):
            with self.subTest(value=value):
                parameters = self.cascade_parameters()
                parameters["height_cascade__m"] = value
                with self.assertRaises(ValidationError) as caught:
                    CascadeParams(**parameters)
                self.assertIn("height_cascade__m", str(caught.exception))

    def test_frame_validation_identifies_the_invalid_column(self):
        frame = cascade_input().assign(eta_fan__W0=1.5)
        with self.assertRaises(ValidationError) as caught:
            CascadeFrame(df=frame)
        self.assertIn("eta_fan__W0", str(caught.exception))


class CommandLineErrorChecks(unittest.TestCase):
    def run_main(self, *arguments):
        messages = io.StringIO()
        with redirect_stderr(messages), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            ewf_tech_simulator.main(list(arguments))
        return caught.exception.code, messages.getvalue()

    def test_hours_and_full_year_are_mutually_exclusive(self):
        code, _ = self.run_main("--hours", "5", "--full-year")
        self.assertEqual(code, 2)

    def test_existing_report_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text("keep", encoding="utf-8")
            code, _ = self.run_main("--report", str(report))
            self.assertEqual(code, 2)
            self.assertEqual(report.read_text(encoding="utf-8"), "keep")

    def test_report_in_missing_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _ = self.run_main("--report", str(Path(directory) / "absent" / "report.json"))
            self.assertEqual(code, 2)

    def test_non_positive_hours_report_failure(self):
        code, message = self.run_main("--hours", "0")
        self.assertEqual(code, 2)
        self.assertIn("Simulation failed:", message)

    def test_invalid_config_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"occupancy": {"wrong_name": 1}}), encoding="utf-8")
            code, message = self.run_main("--config", str(config))
            self.assertEqual(code, 2)
            self.assertIn("Unknown parameter", message)

    def test_successful_run_returns_zero_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                code = ewf_tech_simulator.main(["--hours", "1", "--report", str(report)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["stages"]["energy"]["rows"], 1)


class ExceptionChecks(unittest.TestCase):
    def test_factories_return_typed_errors_with_codes(self):
        cases = [
            (exceptions.create_file_not_found_error("x.csv"), DataFileError, "E001"),
            (exceptions.create_permission_error("x.csv", "lezen"), DataFileError, "E002"),
            (exceptions.create_data_validation_error("col", "numeric"), LegacyDataValidationError, "E004"),
            (exceptions.create_configuration_error("param", "positive", -1), LegacyConfigurationError, "E005"),
            (exceptions.create_processing_error("step", "failed", {"row": 3}), ProcessingError, "E006"),
        ]
        for error, expected_type, code in cases:
            with self.subTest(code=code):
                self.assertIsInstance(error, expected_type)
                self.assertIsInstance(error, exceptions.EWFException)
                self.assertEqual(error.error_code, code)
                self.assertTrue(str(error).startswith(f"[{code}]"))

    def test_error_details_carry_context(self):
        self.assertIn("x.csv", str(exceptions.create_file_not_found_error("x.csv")))
        configuration = exceptions.create_configuration_error("param", "positive", -1)
        self.assertEqual(configuration.parameter, "param")
        self.assertEqual(configuration.details["actual_value"], -1)
        processing = exceptions.create_processing_error("step", "failed", {"row": 3})
        self.assertEqual(processing.step, "step")
        self.assertEqual(processing.details["row"], 3)
        validation = exceptions.create_data_validation_error("col", "numeric")
        self.assertEqual(validation.column, "col")
        self.assertEqual(validation.expected_type, "numeric")


if __name__ == "__main__":
    unittest.main(verbosity=2)