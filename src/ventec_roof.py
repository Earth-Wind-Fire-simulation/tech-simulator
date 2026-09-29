# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Ventec dak berekeningsmodule voor EWF Tech Simulator.

Deze module berekent ventec dakcondities en ventilatiesnelheden
voor het ventec dak systeem in het EWF systeem. Omvat windcorrectie
en Venturi-effect berekeningen.
"""

import numpy as np
from ewf_utils import air_20C__kg_m_3, wind_local_displacement_height__m, wind_local_roughness_length__m, wind_correction_factor__0, venturi_wind_acceleration__0

# Vaste codewaarden
#venturi_wind_acceleration__0 = 1.25
venturi_closed__bool = False
exhaust__Pa = 100.0

def calculate_ventec_roof(df,
                        venturi_ejector_height__m=20.0,
                        venturi_throat_height__m=1.0,
                        venturi_ejector_opening__m2=1.0):
    """Core ventec dak berekening.

    Args:
        df: Input DataFrame met vereiste kolommen.
        venturi_ejector_height__m: Ejector hoogte (m), standaard 20.0.
        venturi_throat_height__m: Keel hoogte (m), standaard 1.0.
        venturi_ejector_opening__m2: Ejector opening gebied (m²), standaard 1.0.

    Returns:
        DataFrame met toegevoegde kolommen: wind_ventec_inflow__m_s_1, wind_venturi_accelerated__m_s_1,
        ejector__m_s_1, wind_venturi_pressure_coefficient__0, venturi_suction__Pa,
        exhaust_fan__Pa, eta_fan_exh__W0, e_fan_exh__W.
    """
    if df is None:
        raise ValueError("Input DataFrame is vereist voor ventec dak berekening.")

    df = df.copy()

    # Gevectoriseerde berekeningen
    df['wind_ventec_inflow__m_s_1'] = (wind_correction_factor__0 * df['wind__m_s_1'] *
                                       np.log((venturi_ejector_height__m - wind_local_displacement_height__m) /
                                              wind_local_roughness_length__m))
    df['wind_venturi_accelerated__m_s_1'] = df['wind_ventec_inflow__m_s_1'] * venturi_wind_acceleration__0
    df['ejector__m_s_1'] = df['air_flow_office__m3_s_1'] / venturi_ejector_opening__m2

    # Berekening wind_venturi_pressure_coefficient__0 gebaseerd op venturi_throat_height__m
    condition_1m = venturi_throat_height__m == 1
    condition_2m = venturi_throat_height__m == 2
    df['wind_venturi_pressure_coefficient__0'] = np.where(
        condition_1m,
        0.5374 * np.log(df['ejector__m_s_1'] / df['wind_venturi_accelerated__m_s_1']) + 0.6381,
        np.where(condition_2m,
                 0.2913 * np.log(df['ejector__m_s_1'] / df['wind_venturi_accelerated__m_s_1']) + 0.0151,
                 np.nan)  # Standaard op nan als geen van de voorwaarden geldig is
    )

    df['venturi_draft__Pa'] = df['wind_venturi_pressure_coefficient__0'] * 0.5 * air_20C__kg_m_3 * np.power(df['wind_venturi_accelerated__m_s_1'], 2)
    #Als venturi trekt is 'draft' negatief. Dus '+' in formule voor de fan.
    df['exhaust_fan__Pa'] = np.maximum(0, exhaust__Pa + df['chimney_delta__Pa'] - np.minimum(df['outdoor_chimney_delta__Pa'],df['shunt_delta__Pa']) + df['venturi_draft__Pa'])

#Oscar(17sep26): formule gecorrigeerd voor trek in de shunt. Oorspronkelijke formule:
    #df['exhaust_fan__Pa'] = np.maximum(0, exhaust__Pa + df['chimney_delta__Pa'] - df['outdoor_chimney_delta__Pa'] + df['venturi_draft__Pa'])

#Oscar 27aug26: efficiency for both fans now calculated in module occupancy
    #df['eta_fan_exh__W0'] = (eta_fan_min__W0 + (df['air_flow_office__m3_s_1'] - fan_min__m3_s_1) /
    #                    (fan_max__m3_s_1 - fan_min__m3_s_1) * (eta_fan_max__W0 - eta_fan_min__W0))
    #Multiply pressure with volume flow.
    df['e_fan_exh__W'] = df['exhaust_fan__Pa'] * df['air_flow_office__m3_s_1'] / df['eta_fan__W0']

    return df
