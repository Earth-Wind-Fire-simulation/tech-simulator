# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy==1.13.1, openpyxl==3.1.5

"""
Overdrukkamer berekeningsmodule voor EWF Tech Simulator.

Deze module berekent overdrukcondities op basis van wind en temperatuur
voor de overdrukkamer in het EWF systeem. Omvat windcorrectie
en drukberekeningen.
"""

from numbers import Real

import numpy as np
import pandas as pd

from ewf_utils import (
    air_20C__kg_m_3,
    venturi_wind_acceleration__0,
    wind_correction_factor__0,
    wind_local_displacement_height__m,
    wind_local_roughness_length__m,
)
from exceptions import create_configuration_error, create_data_validation_error

# Vaste codewaarden
wind_overpressure_inflow_threshold__m_s_1 = 2.5  # Drempel windsnelheid uit vergelijking
wind_overpressure_coefficient__0 = 0.8  # Coëfficiënt uit vergelijking

# Berekening van overdrukkamercondities
def calculate_overpressure_room(df, wind_overpressure_inflow_height__m=17.0):
    """Bereken overdrukkamercondities op basis van wind en temperatuur.

    Args:
        df: Een rij per uur met wind__m_s_1 en temp_outdoor__degC.
        wind_overpressure_inflow_height__m: Hoogte voor wind overdruk instroom (m), standaard 17.0.
    
    Returns:
        Kopie met temp_overpressure_in__degC, temp_overpressure_out__degC,
        wind_overpressure_inflow__m_s_1 en overpressure_room_delta__Pa.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or not df.columns.is_unique or not df.index.is_unique:
        raise create_data_validation_error('df', 'niet-lege DataFrame met unieke kolommen en index')
    for column in ['wind__m_s_1', 'temp_outdoor__degC']:
        if column not in df or not pd.api.types.is_numeric_dtype(df[column]):
            raise create_data_validation_error(column, 'numerieke kolom')
        if df[column].isna().any() or not np.isfinite(df[column].to_numpy(dtype=float)).all():
            raise create_data_validation_error(column, 'eindige waarden')
    if (df['wind__m_s_1'] < 0).any():
        raise create_data_validation_error('wind__m_s_1', 'niet-negatieve windsnelheid')
    if (isinstance(wind_overpressure_inflow_height__m, bool) or not isinstance(wind_overpressure_inflow_height__m, Real)
            or not np.isfinite(wind_overpressure_inflow_height__m)
            or wind_overpressure_inflow_height__m <= wind_local_displacement_height__m + wind_local_roughness_length__m):
        raise create_configuration_error('wind_overpressure_inflow_height__m',
                                         'boven verplaatsingshoogte plus ruwheidslengte', wind_overpressure_inflow_height__m)
    
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