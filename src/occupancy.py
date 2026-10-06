# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy==1.13.1, openpyxl==3.1.5

"""
Bezetting berekeningsmodule voor EWF Tech Simulator.

Deze module berekent bezettingspercentages en afgeleide luchtstroomsnelheden
op basis van inputdata en bezettingsschema's. Incl. foutafhandeling
en bestandsbeschermingsmechanismen.
"""

from datetime import datetime
from numbers import Real

import numpy as np
import pandas as pd

from ewf_utils import (
    air_flow_office_set__dm3_s_1_p_1,
    dm3_m_3,
    eta_fan_max__W0,
    eta_fan_min__W0,
    fan_modulation_depth__0,
    flow_modulation_depth__0,
)
from exceptions import create_configuration_error, create_data_validation_error
from weather import safe_read_csv


# Calculation occupancy and derived air flow
def calculate_occupancy(jaar: int, pad: str, df: pd.DataFrame, occupancy_mean__p: float = 165) -> pd.DataFrame:
    """Bereken bezetting en afgeleide luchtstroom.

    Args:
        jaar: Jaar voor tijdsberekening.
        pad: Pad naar het bezettings CSV bestand.
        df: Een rij per uur, evenveel rijen als het bezettingsbestand.
            Rijen worden op positie gekoppeld, niet op pandas-indexlabels.
            De periode start op 1 januari in Europe/Amsterdam.
        occupancy_mean__p: Gemiddelde bezetting in personen, standaard 165.

    Returns:
        DataFrame met toegevoegde kolommen:
        - occupancy__perc: Bezetting als percentage
        - air_flow_office_set__m3_s_1: Gewenste luchtstroomsnelheid
        - air_flow_office__m3_s_1: Werkelijke luchtstroomsnelheid

    Raises:
        DataFileError: Als het bezettingsbestand niet gelezen kan worden.
        ProcessingError: Als bezettingsberekening faalt.
        DataValidationError: Als input data ongeldig is.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or not df.columns.is_unique or not df.index.is_unique:
        raise create_data_validation_error('df', 'niet-lege DataFrame met unieke kolommen en index')
    if isinstance(jaar, bool) or not isinstance(jaar, Real) or not np.isfinite(jaar) or int(jaar) != jaar:
        raise create_configuration_error('jaar', 'geheel kalenderjaar', jaar)
    jaar = int(jaar)
    try:
        start = datetime(jaar, 1, 1, 0)
        pd.Timestamp(start)
    except (ValueError, OverflowError) as error:
        raise create_configuration_error('jaar', 'kalenderjaar binnen het datumbereik van pandas', jaar) from error
    if (isinstance(occupancy_mean__p, bool) or not isinstance(occupancy_mean__p, Real)
            or not np.isfinite(occupancy_mean__p) or occupancy_mean__p <= 0):
        raise create_configuration_error('occupancy_mean__p', 'eindig en groter dan nul', occupancy_mean__p)
    df = df.copy()
    df_occ = safe_read_csv(pad, decimal=',')
    if 'occupancyperc' not in df_occ and 'occupancy(perc)' in df_occ:
        df_occ['occupancyperc'] = df_occ['occupancy(perc)']
    
    # Controleer vereiste kolom
    if 'occupancyperc' not in df_occ.columns:
        raise create_data_validation_error(
            column='occupancyperc',
            expected_type='numeric column',
            actual_value=None
        )

    # Bereken het juiste aantal uren op basis van data lengte
    data_uren = len(df)
    occupancy_uren = len(df_occ)
    if data_uren != occupancy_uren:
        raise create_data_validation_error('occupancyperc', 'evenveel uren als weerdata',
                                           actual_value=occupancy_uren,
                                           custom_message=f'Bezetting heeft {occupancy_uren} uren, weerdata {data_uren}.')
    target_uren = data_uren
    if (not pd.api.types.is_numeric_dtype(df_occ['occupancyperc'])
            or df_occ['occupancyperc'].isna().any() or not df_occ['occupancyperc'].between(0, 100).all()):
        raise create_data_validation_error('occupancyperc', 'bezetting tussen 0 en 100 procent')
    if 'occupancy(perc)' in df_occ and not df_occ['occupancyperc'].equals(df_occ['occupancy(perc)']):
        raise create_data_validation_error('occupancyperc', 'gelijke waarden voor beide bezettingskolommen')
    df['occupancy__perc'] = df_occ['occupancyperc'].to_numpy()
    #Tijd met tijdzone. Gebruikt voor berekening van zonnestand
    #df['tijd met tijdzone'] = df_occ['date and time']

    # Gewenste luchtstroomsnelheid
    flow_max__m3_s_1 = occupancy_mean__p * air_flow_office_set__dm3_s_1_p_1 / dm3_m_3
    flow_min__m3_s_1 = flow_max__m3_s_1 * flow_modulation_depth__0
    df['air_flow_office_set__m3_s_1'] = 0.01 * df['occupancy__perc'] * flow_max__m3_s_1
    # Gewenste luchtstroomsnelheid wordt altijd bereikt in deze simulatie, maar nooit minder dan het minimum dat de ventilator ondersteunt 
    df['air_flow_office__m3_s_1'] = np.maximum(df['air_flow_office_set__m3_s_1'], flow_min__m3_s_1)

    #Determine fan efficiency at the current flow
    fan_max__m3_s_1 = flow_max__m3_s_1
    fan_min__m3_s_1 = fan_max__m3_s_1 * fan_modulation_depth__0
    df['eta_fan__W0'] = (eta_fan_min__W0 + (df['air_flow_office__m3_s_1'] - fan_min__m3_s_1) /
                             (fan_max__m3_s_1 - fan_min__m3_s_1) * (eta_fan_max__W0 - eta_fan_min__W0))

    # Creeer een lijst met tijdstippen met tijdzone (geoptimaliseerd)

    
    # Creëer tijd range met juiste lengte
    try:
        tijd_range = pd.date_range(start, periods=target_uren, freq='h', tz='Europe/Amsterdam')
    except (ValueError, OverflowError) as error:
        raise create_data_validation_error('df', 'periode binnen het datumbereik van pandas') from error
    if tijd_range[-1].year != jaar:
        raise create_data_validation_error('df', 'hoogstens een kalenderjaar aan uurwaarden')
    if 'date and time' in df_occ:
        try:
            supplied_time = pd.to_datetime(df_occ['date and time'], utc=True, errors='raise')
        except (ValueError, TypeError) as error:
            raise create_data_validation_error('date and time', 'geldige tijdstippen met tijdzone') from error
        if not np.array_equal(supplied_time.array.asi8, tijd_range.tz_convert('UTC').asi8):
            raise create_data_validation_error('date and time', 'opeenvolgende uren vanaf 1 januari van het gekozen jaar')
    
    # Voeg tijd kolom toe
    df['tijd met tijdzone'] = tijd_range

    return df