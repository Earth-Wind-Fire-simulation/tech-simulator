"""
Electriciteitsberekeningsmodule voor EWF Tech Simulator.

Deze module berekent totale electriciteitsverbruik en afgeleide statistieken
op basis van inputdata van diverse systemcomponenten. Incl. foutafhandeling.
"""

import numpy as np
import pandas as pd

from ewf_utils import Wh_kWh_1, min_h_1
from schemas import EnergyFrame, FiniteResults


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
    EnergyFrame(df=df)
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

    # Tel alle beschikbare electriciteitskolommen
    df['e__ewf_total__W'] = sum(e_cols, start=pd.Series(0.0, index=df.index))
    FiniteResults(values=tuple(df['e__ewf_total__W'].to_numpy(dtype=float)))

    interval_min = min_h_1

    e_ewf_total__h = len(df) * interval_min / min_h_1  # Totale uren op basis van aantal intervallen

    # Bereken gemiddeld vermogen en totale energie
    e_ewf_total_mean__W = df['e__ewf_total__W'].mean()
    e_ewf_total_sum__kWh = e_ewf_total_mean__W * e_ewf_total__h / Wh_kWh_1
    FiniteResults(values=(float(e_ewf_total_sum__kWh),))

    return df, e_ewf_total_mean__W, e_ewf_total_sum__kWh