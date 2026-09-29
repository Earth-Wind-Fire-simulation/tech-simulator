# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Overdrukkamer berekeningsmodule voor EWF Tech Simulator.

Deze module berekent overdrukcondities op basis van wind en temperatuur
voor de overdrukkamer in het EWF systeem. Omvat windcorrectie
en drukberekeningen.
"""

import numpy as np
import pandas as pd
from ewf_utils import air_20C__kg_m_3, wind_correction_factor__0, wind_local_displacement_height__m, wind_local_roughness_length__m, venturi_wind_acceleration__0

# Vaste codewaarden
wind_overpressure_inflow_threshold__m_s_1 = 2.5  # Drempel windsnelheid uit vergelijking
wind_overpressure_coefficient__0 = 0.8  # Coëfficiënt uit vergelijking

# Berekening van overdrukkamercondities
def calculate_overpressure_room(df, wind_overpressure_inflow_height__m=17.0):
    """Bereken overdrukkamercondities op basis van wind en temperatuur.

    Args:
        df: Input DataFrame met vereiste kolommen ['wind_knmi__m_s_1', 'temp_outdoor__degC'].
        wind_overpressure_inflow_height__m: Hoogte voor wind overdruk instroom (m), standaard 17.0.
    
    Returns:
        DataFrame met toegevoegde kolommen: temp_overpressure_in__degC, temp_overpressure_out__degC, overpressure_room_gain__Pa.
    """
    if df is None:
        raise ValueError("Input DataFrame is vereist voor overdrukkamer berekening.")
    
    # Maak een kopie van de input DataFrame om mutatieproblemen in Grasshopper te voorkomen
    df = df.copy()
    
    # Tussenberekening: wind overdruk instroomsnelheid

    wind_overpressure_inflow__m_s_1 = (wind_correction_factor__0 * df['wind__m_s_1'] *
                                      np.log((wind_overpressure_inflow_height__m - wind_local_displacement_height__m) /
                                             wind_local_roughness_length__m))

    wind_overpressure_inflow__m_s_1 = wind_overpressure_inflow__m_s_1 * venturi_wind_acceleration__0

    # Overdrukkamerwinst op basis van windsnelheidsdrempel
    overpressure_room_gain__Pa = np.where(wind_overpressure_inflow__m_s_1 > wind_overpressure_inflow_threshold__m_s_1,
                                         0.5 * wind_overpressure_coefficient__0 * air_20C__kg_m_3 * np.power(wind_overpressure_inflow__m_s_1, 2),
                                         0)

    # Temperatuurtoewijzingen
    df['temp_overpressure_in__degC'] = df['temp_outdoor__degC']
    df['temp_overpressure_out__degC'] = df['temp_overpressure_in__degC']

    # Voeg overdrukwinst toe aan DataFrame
    df['wind_overpressure_inflow__m_s_1'] = wind_overpressure_inflow__m_s_1
    df['overpressure_room_delta__Pa'] = overpressure_room_gain__Pa

    return df