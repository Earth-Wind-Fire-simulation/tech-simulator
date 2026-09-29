# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Electriciteitsberekeningsmodule voor EWF Tech Simulator.

Deze module berekent totale electriciteitsverbruik en afgeleide statistieken
op basis van inputdata van diverse systemcomponenten. Incl. foutafhandeling.
"""

import pandas as pd
from ewf_utils import Wh_kWh_1, s_min_1, min_h_1

def calculate_energy(df):
    """Core electriciteitsberekening om alle electriciteitswaarden op te tellen en totalen te berekenen.

    Args:
        df: Input DataFrame met electriciteitskolommen.

    Returns:
        Tuple van (DataFrame, float, float):
        - DataFrame met toegevoegde kolom e__ewf_total__W
        - Gemiddeld vermogen in W
        - Totale energie in kWh

    Raises:
        ValueError: Als input DataFrame None is.
    """
    if df is None:
        raise ValueError("Input DataFrame is vereist voor electriciteitsberekening.")

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
    df['e__ewf_total__W'] = sum(e_cols)

    #Oscar(3sep26): Optie met index.freq wordt niet gebruikt maar gaf wel een opmerking dat dit niet klopt. Daarom verwijdert.
    # Leid tijdsinterval en totale uren af
    #if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 1:
    #    if df.index.freq is not None:
    #        interval_min = df.index.freq.n  # Extraheer interval in minuten van frequentie
    #     else:
    #        # Fallback naar gemiddeld verschil als frequentie niet is ingesteld (onregelmatige index)
    #        intervals = df.index.to_series().diff().dropna()
    #        interval_min = intervals.mean().total_seconds() / s_min_1
    #else:
    interval_min = min_h_1  # Standaard naar 1 uur, d.w.z. 60 minuten als index niet datetime of onvoldoende data

    e_ewf_total__h = len(df) * interval_min / min_h_1  # Totale uren op basis van aantal intervallen

    # Bereken gemiddeld vermogen en totale energie
    e_ewf_total_mean__W = df['e__ewf_total__W'].mean()
    e_ewf_total_sum__kWh = e_ewf_total_mean__W * e_ewf_total__h / Wh_kWh_1

    return df, e_ewf_total_mean__W, e_ewf_total_sum__kWh