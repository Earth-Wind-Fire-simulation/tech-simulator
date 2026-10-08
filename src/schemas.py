"""Pydantic models for simulator inputs and configuration."""

from datetime import datetime
from math import isfinite
from numbers import Real
from os import PathLike
from typing import Annotated, Any, ClassVar

import numpy as np
import pandas as pd
from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

ABSOLUTE_ZERO_C = -273.15
VAPOUR_PRESSURE_SINGULARITY_C = -235.0


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("must be a real number")
    value = float(value)
    if not isfinite(value):
        raise ValueError("must be finite")
    return value


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("must be an integer")
    value = float(value)
    if not isfinite(value) or value != int(value):
        raise ValueError("must be an integer")
    return int(value)


FiniteFloat = Annotated[float, BeforeValidator(_number)]


class ParamsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrameModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    df: pd.DataFrame
    required_columns: ClassVar[tuple[str, ...]] = ()
    numeric_columns: ClassVar[tuple[str, ...]] = ()
    rules: ClassVar[dict[str, dict[str, float]]] = {}

    @model_validator(mode="after")
    def validate_frame(self) -> "FrameModel":
        frame = self.df
        if frame.empty:
            raise ValueError("must be a non-empty DataFrame")
        if not frame.columns.is_unique:
            raise ValueError("columns must be unique")
        if not frame.index.is_unique:
            raise ValueError("index must be unique")
        missing = [column for column in self.required_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")
        for column in self.numeric_columns:
            if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
                raise ValueError(f"{column} must be numeric")
            values = frame[column].to_numpy(dtype=float)
            if frame[column].isna().any() or not np.isfinite(values).all():
                raise ValueError(f"{column} must contain finite values")
        for column, constraints in self.rules.items():
            values = frame[column]
            if "ge" in constraints and (values < constraints["ge"]).any():
                raise ValueError(f"{column} must be >= {constraints['ge']}")
            if "gt" in constraints and (values <= constraints["gt"]).any():
                raise ValueError(f"{column} must be > {constraints['gt']}")
            if "le" in constraints and (values > constraints["le"]).any():
                raise ValueError(f"{column} must be <= {constraints['le']}")
            if "lt" in constraints and (values >= constraints["lt"]).any():
                raise ValueError(f"{column} must be < {constraints['lt']}")
            if "ne" in constraints and (values == constraints["ne"]).any():
                raise ValueError(f"{column} must not equal {constraints['ne']}")
        return self


class CascadeParams(ParamsModel):
    height_cascade__m: FiniteFloat = Field(gt=0)
    cascade_width__m: FiniteFloat = Field(gt=0)
    cascade_depth__m: FiniteFloat = Field(gt=0)
    cascade_segments__0: int
    temp_water_cascade_in__degC: FiniteFloat
    temp_air_in_threshold__degC: FiniteFloat
    temp_air_cascade_out_set__degC: FiniteFloat
    humidity_abs_set__g_kg_1: FiniteFloat
    nozzles_min__0: int = Field(ge=0)
    nozzles_max__0: int = Field(ge=0)
    loss_cascade_water_nozzle__Pa: FiniteFloat

    _integer_fields = field_validator("cascade_segments__0", "nozzles_min__0", "nozzles_max__0", mode="before")(_integer)

    @model_validator(mode="after")
    def validate_cascade(self) -> "CascadeParams":
        if self.cascade_segments__0 <= 0 or self.nozzles_min__0 > self.nozzles_max__0:
            raise ValueError("segments must be > 0 and minimum nozzles <= maximum nozzles")
        if min(self.temp_water_cascade_in__degC, self.temp_air_in_threshold__degC,
               self.temp_air_cascade_out_set__degC) <= ABSOLUTE_ZERO_C:
            raise ValueError("temperatures must be above absolute zero")
        if self.temp_water_cascade_in__degC == VAPOUR_PRESSURE_SINGULARITY_C:
            raise ValueError("water temperature is invalid for vapour pressure calculation")
        if self.humidity_abs_set__g_kg_1 < 0 or self.loss_cascade_water_nozzle__Pa < 0:
            raise ValueError("humidity and pressure must be non-negative")
        return self


class CascadeFrame(FrameModel):
    required_columns = (
        "temp_overpressure_out__degC", "temp_air_heat_recovery_in__degC",
        "air_flow_office__m3_s_1", "humidity_outdoor_rel__0", "temp_outdoor__degC",
        "overpressure_room_delta__Pa", "eta_fan__W0",
    )
    numeric_columns = required_columns
    rules = {
        "air_flow_office__m3_s_1": {"ge": 0},
        "humidity_outdoor_rel__0": {"ge": 0, "le": 1},
        "eta_fan__W0": {"gt": 0, "le": 1},
        "temp_overpressure_out__degC": {"gt": ABSOLUTE_ZERO_C},
        "temp_air_heat_recovery_in__degC": {"gt": ABSOLUTE_ZERO_C},
        "temp_outdoor__degC": {"gt": ABSOLUTE_ZERO_C, "ne": VAPOUR_PRESSURE_SINGULARITY_C},
    }


class EnergyFrame(FrameModel):
    power_columns: ClassVar[tuple[str, ...]] = (
        "e_cascade_heat_pump__W", "e_post_cascade_heat_pump__W",
        "e_cascade_water_pump__W", "e_fan_supply__W", "e_fan_exh__W",
        "e_fan_heat_recovery__W",
    )

    @model_validator(mode="after")
    def validate_energy(self) -> "EnergyFrame":
        available = [column for column in self.power_columns if column in self.df]
        if not available:
            raise ValueError("at least one known electricity column is required")
        for column in available:
            values = self.df[column]
            if not pd.api.types.is_numeric_dtype(values) or values.isna().any():
                raise ValueError(f"{column} must be numeric and non-null")
            if not np.isfinite(values.to_numpy(dtype=float)).all() or (values < 0).any():
                raise ValueError(f"{column} must contain finite non-negative power")
        if isinstance(self.df.index, pd.DatetimeIndex) and len(self.df) > 1:
            intervals = self.df.index.to_series().diff().iloc[1:]
            if not intervals.eq(pd.Timedelta(hours=1)).all():
                raise ValueError("DatetimeIndex must contain consecutive hourly values")
        return self


class FiniteOutputFrame(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    df: pd.DataFrame
    columns: tuple[str, ...]

    @model_validator(mode="after")
    def validate_output(self) -> "FiniteOutputFrame":
        missing = [column for column in self.columns if column not in self.df]
        if missing:
            raise ValueError(f"missing output columns: {missing}")
        values = self.df[list(self.columns)].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("output values must be finite")
        return self


class FiniteResults(BaseModel):
    values: tuple[float, ...]

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if not all(isfinite(value) for value in values):
            raise ValueError("results must be finite")
        return values


class OccupancyParams(ParamsModel):
    jaar: int
    occupancy_mean__p: FiniteFloat = Field(gt=0)

    _year = field_validator("jaar", mode="before")(_integer)

    @field_validator("jaar")
    @classmethod
    def valid_year(cls, value: int) -> int:
        try:
            pd.Timestamp(datetime(value, 1, 1))
        except (ValueError, OverflowError) as error:
            raise ValueError("must be a calendar year supported by pandas") from error
        return value


class OccupancyFrame(FrameModel):
    pass


class OccupancyFile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    df: pd.DataFrame
    target_hours: int
    year: int

    @model_validator(mode="after")
    def validate_file(self) -> "OccupancyFile":
        if "occupancyperc" not in self.df:
            raise ValueError("occupancyperc column is required")
        if len(self.df) != self.target_hours:
            raise ValueError(
                f"occupancy data has {len(self.df)} hours, input data has {self.target_hours}"
            )
        values = self.df["occupancyperc"]
        if not pd.api.types.is_numeric_dtype(values) or values.isna().any():
            raise ValueError("occupancyperc must be numeric and non-null")
        if not values.between(0, 100).all():
            raise ValueError("occupancyperc must be between 0 and 100")
        if "occupancy(perc)" in self.df and not values.equals(self.df["occupancy(perc)"]):
            raise ValueError("occupancyperc and occupancy(perc) must contain equal values")
        try:
            time_range = pd.date_range(
                datetime(self.year, 1, 1), periods=self.target_hours,
                freq="h", tz="Europe/Amsterdam",
            )
        except (ValueError, OverflowError) as error:
            raise ValueError("period is outside the pandas datetime range") from error
        if time_range[-1].year != self.year:
            raise ValueError("occupancy data may span at most one calendar year")
        if "date and time" in self.df:
            try:
                supplied_time = pd.to_datetime(self.df["date and time"], utc=True, errors="raise")
            except (ValueError, TypeError) as error:
                raise ValueError("date and time must be timezone-aware timestamps") from error
            if not np.array_equal(supplied_time.array.asi8, time_range.tz_convert("UTC").asi8):
                raise ValueError("date and time must be consecutive hours from January 1")
        return self


class OverpressureParams(ParamsModel):
    wind_overpressure_inflow_height__m: FiniteFloat = Field(gt=10.5)


class OverpressureFrame(FrameModel):
    required_columns = ("wind__m_s_1", "temp_outdoor__degC")
    numeric_columns = required_columns
    rules = {"wind__m_s_1": {"ge": 0}}


class SolarChimneyParams(ParamsModel):
    weather_location__degN: FiniteFloat = Field(ge=-90, le=90)
    weather_location__degE: FiniteFloat = Field(ge=-180, le=180)
    solar_chimney_height__m: FiniteFloat = Field(gt=0)
    solar_chimney_segments__0: int
    solar_chimney_width__m: FiniteFloat = Field(gt=0)
    solar_chimney_depth__m: FiniteFloat = Field(gt=0)
    solar_chimney_azimuth__degN: FiniteFloat
    glazing_transmittance__0: FiniteFloat = Field(ge=0, le=1)
    glazing__pct: FiniteFloat = Field(ge=0, le=100)
    solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1: FiniteFloat = Field(gt=0)

    _segments = field_validator("solar_chimney_segments__0", mode="before")(_integer)

    @field_validator("solar_chimney_segments__0")
    @classmethod
    def positive_segments(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be a positive integer")
        return value


class SolarChimneyFrame(FrameModel):
    required_columns = ("temp_outdoor__degC", "air_flow_office__m3_s_1", "sol_ghi__W_m_2", "tijd met tijdzone")
    numeric_columns = ("temp_outdoor__degC", "air_flow_office__m3_s_1", "sol_ghi__W_m_2")
    rules = {
        "temp_outdoor__degC": {"gt": ABSOLUTE_ZERO_C},
        "air_flow_office__m3_s_1": {"ge": 0},
        "sol_ghi__W_m_2": {"ge": 0},
    }

    @model_validator(mode="after")
    def validate_timezones(self) -> "SolarChimneyFrame":
        timestamps = self.df["tijd met tijdzone"]
        if timestamps.isna().any():
            raise ValueError("tijd met tijdzone must not contain null values")
        for timestamp in timestamps:
            if not hasattr(timestamp, "utcoffset") or timestamp.utcoffset() is None:
                raise ValueError("tijd met tijdzone must contain timezone-aware datetimes")
        return self


class VentecParams(ParamsModel):
    venturi_ejector_height__m: FiniteFloat = Field(gt=10.5)
    venturi_throat_height__m: FiniteFloat
    venturi_ejector_opening__m2: FiniteFloat = Field(gt=0)

    @field_validator("venturi_throat_height__m")
    @classmethod
    def supported_throat_height(cls, value: float) -> float:
        if value not in (1, 2):
            raise ValueError("must be 1 or 2 m")
        return value


class VentecFrame(FrameModel):
    required_columns = (
        "wind__m_s_1", "air_flow_office__m3_s_1", "eta_fan__W0",
        "chimney_delta__Pa", "outdoor_chimney_delta__Pa", "shunt_delta__Pa",
    )
    numeric_columns = required_columns
    rules = {
        "wind__m_s_1": {"ge": 0},
        "air_flow_office__m3_s_1": {"ge": 0},
        "eta_fan__W0": {"gt": 0, "le": 1},
    }


class WeatherPath(BaseModel):
    path: Any

    @field_validator("path")
    @classmethod
    def valid_path(cls, value: Any) -> Any:
        if not isinstance(value, (str, PathLike)) or not str(value).strip() or os_fspath(value) == "<null>":
            raise ValueError("must be a non-empty file path")
        return value


class KnmiFrame(FrameModel):
    required_columns = ("FH", "T", "Q", "P", "U")
    numeric_columns = required_columns
    rules = {"FH": {"ge": 0}, "Q": {"ge": 0}, "P": {"gt": 0}, "U": {"ge": 0, "le": 100}}


def os_fspath(value: Any) -> str:
    return str(value) if isinstance(value, str) else __import__("os").fspath(value)
