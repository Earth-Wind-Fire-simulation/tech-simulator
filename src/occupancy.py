"""
Bezetting berekeningsmodule voor EWF Tech Simulator.

Deze module berekent bezettingspercentages en afgeleide luchtstroomsnelheden
op basis van inputdata en bezettingsschema's. Incl. foutafhandeling
en bestandsbeschermingsmechanismen.
"""

from datetime import datetime
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
from schemas import OccupancyFile, OccupancyFrame, OccupancyParams
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
    params = OccupancyParams(jaar=jaar, occupancy_mean__p=occupancy_mean__p)
    OccupancyFrame(df=df)
    jaar = params.jaar
    occupancy_mean__p = params.occupancy_mean__p
    start = datetime(jaar, 1, 1, 0)
    df = df.copy()
    df_occ = safe_read_csv(pad, decimal=',')
    if 'occupancyperc' not in df_occ and 'occupancy(perc)' in df_occ:
        df_occ['occupancyperc'] = df_occ['occupancy(perc)']
    occupancy_file = OccupancyFile(df=df_occ, target_hours=len(df), year=jaar)
    df_occ = occupancy_file.df
    target_uren = len(df)
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
    tijd_range = pd.date_range(start, periods=target_uren, freq='h', tz='Europe/Amsterdam')
    
    # Voeg tijd kolom toe
    df['tijd met tijdzone'] = tijd_range

    return df