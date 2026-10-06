"""
Electriciteitsberekeningsmodule voor EWF Tech Simulator.

Deze module berekent totale electriciteitsverbruik en afgeleide statistieken
op basis van inputdata van diverse systemcomponenten. Incl. foutafhandeling.
"""

import numpy as np
import pandas as pd

from ewf_utils import Wh_kWh_1, min_h_1
from exceptions import create_data_validation_error


def calculate_energy(df):
    """Core electriciteitsberekening om alle electriciteitswaarden op te tellen en totalen te berekenen.

    Args:
        df: Een rij per uur met minstens een bekende electriciteitskolom in W.
            Alle opgenomen vermogens moeten numeriek, eindig en niet-negatief zijn.
            Ontbrekende componenten worden niet meegerekend; ontbrekende waarden
            binnen een opgenomen component zijn niet toegestaan.

    Returns:
        Tuple van (DataFrame, float, float):
        - DataFrame met toegevoegde kolom e__ewf_total__W
        - Gemiddeld vermogen in W
        - Totale energie in kWh

    Raises:
        ValueError: Als input DataFrame None is.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or not df.columns.is_unique or not df.index.is_unique:
        raise create_data_validation_error('df', 'niet-lege DataFrame met unieke kolommen en index')

    if isinstance(df.index, pd.DatetimeIndex) and len(df) > 1:
        if not df.index.to_series().diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
            raise create_data_validation_error('df.index', 'opeenvolgende uurwaarden')

    df = df.copy()

    # Bereken totale electriciteit
    # Controleer beschikbare kolommen om KeyError te voorkomen
    available_cols = df.columns.tolist()
    
    # Gebruik alleen beschikbare kolommen
    e_cols = []
    if 'e_cascade_heat_pump__W' in available_cols:
        e_cols.append(df['e_cascade_heat_pump__W'])
    if 'e_post_cascade_heat_pump__W' in available_cols:
        e_cols.append(df['e_post_cascade_heat_pump__W'])
    if 'e_cascade_water_pump__W' in available_cols:
        e_cols.append(df['e_cascade_water_pump__W'])
    if 'e_fan_supply__W' in available_cols:
        e_cols.append(df['e_fan_supply__W'])
    if 'e_fan_exh__W' in available_cols:
        e_cols.append(df['e_fan_exh__W'])
    if 'e_fan_heat_recovery__W' in available_cols:
        e_cols.append(df['e_fan_heat_recovery__W'])

    if not e_cols:
        raise create_data_validation_error('df', 'minstens een bekende electriciteitskolom in W')
    for column in e_cols:
        if (not pd.api.types.is_numeric_dtype(column) or column.isna().any()
                or not np.isfinite(column.to_numpy(dtype=float)).all() or (column < 0).any()):
            raise create_data_validation_error(column.name, 'eindig niet-negatief vermogen in W')
    
    # Tel alle beschikbare electriciteitskolommen
    df['e__ewf_total__W'] = sum(e_cols, start=pd.Series(0.0, index=df.index))
    if not np.isfinite(df['e__ewf_total__W']).all():
        raise create_data_validation_error('e__ewf_total__W', 'eindig totaalvermogen in W')

    interval_min = min_h_1

    e_ewf_total__h = len(df) * interval_min / min_h_1  # Totale uren op basis van aantal intervallen

    # Bereken gemiddeld vermogen en totale energie
    e_ewf_total_mean__W = df['e__ewf_total__W'].mean()
    e_ewf_total_sum__kWh = e_ewf_total_mean__W * e_ewf_total__h / Wh_kWh_1
    if not np.isfinite(e_ewf_total_sum__kWh):
        raise create_data_validation_error('e_ewf_total_sum__kWh', 'eindige energie in kWh')

    return df, e_ewf_total_mean__W, e_ewf_total_sum__kWh