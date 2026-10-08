"""
Ventec dak berekeningsmodule voor EWF Tech Simulator.

Deze module berekent ventec dakcondities en ventilatiesnelheden
voor het ventec dak systeem in het EWF systeem. Omvat windcorrectie
en Venturi-effect berekeningen.
"""

import numpy as np
import pandas as pd

from ewf_utils import (
    air_20C__kg_m_3,
    venturi_wind_acceleration__0,
    wind_correction_factor__0,
    wind_local_displacement_height__m,
    wind_local_roughness_length__m,
)
from schemas import FiniteOutputFrame, VentecFrame, VentecParams, validate_inputs

# Vaste codewaarden
#venturi_wind_acceleration__0 = 1.25
venturi_closed__bool = False
exhaust__Pa = 100.0 # TODO: expose input

@validate_inputs(VentecParams, VentecFrame)
def calculate_ventec_roof(df,
                        venturi_ejector_height__m=20.0,
                        venturi_throat_height__m=1.0,
                        venturi_ejector_opening__m2=1.0):
    """Core ventec dak berekening.

    Args:
        df: Een rij per uur met wind__m_s_1, air_flow_office__m3_s_1,
            eta_fan__W0, chimney_delta__Pa, outdoor_chimney_delta__Pa,
            shunt_delta__Pa. De input wordt niet gewijzigd.
        venturi_ejector_height__m: Ejector hoogte (m), standaard 20.0.
        venturi_throat_height__m: Keel hoogte (m), standaard 1.0.
        venturi_ejector_opening__m2: Ejector opening gebied (m²), standaard 1.0.

    Returns:
        DataFrame met toegevoegde kolommen: wind_ventec_inflow__m_s_1, wind_venturi_accelerated__m_s_1,
        ejector__m_s_1, wind_venturi_pressure_coefficient__0, venturi_draft__Pa,
        exhaust_fan__Pa, e_fan_exh__W.

        Bij windstilte is de windbijdrage nul (limiet van wind**2 * log(1/wind)).
        Zonder luchtdebiet zijn coefficient, trek en ventilatorwaarden nul:
        een inactieve bedrijfsstand, geen voorspelling van statische dakdruk.
    """
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
    # Alleen actief wanneer beide snelheden positief zijn (wind en ventilatie aanwezig)
    active = (df['ejector__m_s_1'] > 0) & (df['wind_venturi_accelerated__m_s_1'] > 0)
    df['wind_venturi_pressure_coefficient__0'] = 0.0
    log_velocity_ratio = (np.log(df.loc[active, 'ejector__m_s_1']) -
                          np.log(df.loc[active, 'wind_venturi_accelerated__m_s_1']))
    if condition_1m:
        df.loc[active, 'wind_venturi_pressure_coefficient__0'] = 0.5374 * log_velocity_ratio + 0.6381
    elif condition_2m:
        df.loc[active, 'wind_venturi_pressure_coefficient__0'] = 0.2913 * log_velocity_ratio + 0.0151

    df['venturi_draft__Pa'] = df['wind_venturi_pressure_coefficient__0'] * 0.5 * air_20C__kg_m_3 * np.power(df['wind_venturi_accelerated__m_s_1'], 2)
    #Als venturi trekt is 'draft' negatief. Dus '+' in formule voor de fan.
    df['exhaust_fan__Pa'] = np.maximum(0, exhaust__Pa + df['chimney_delta__Pa'] - np.minimum(df['outdoor_chimney_delta__Pa'],df['shunt_delta__Pa']) + df['venturi_draft__Pa'])
    # Geen ventilatordruk nodig als er geen debiet is (inactieve bedrijfsmode). Dit voorkomt ongeldige berekeningen
    df.loc[df['air_flow_office__m3_s_1'] == 0, 'exhaust_fan__Pa'] = 0.0

#Oscar(17sep26): formule gecorrigeerd voor trek in de shunt. Oorspronkelijke formule:
    #df['exhaust_fan__Pa'] = np.maximum(0, exhaust__Pa + df['chimney_delta__Pa'] - df['outdoor_chimney_delta__Pa'] + df['venturi_draft__Pa'])

#Oscar 27aug26: efficiency for both fans now calculated in module occupancy
    #df['eta_fan_exh__W0'] = (eta_fan_min__W0 + (df['air_flow_office__m3_s_1'] - fan_min__m3_s_1) /
    #                    (fan_max__m3_s_1 - fan_min__m3_s_1) * (eta_fan_max__W0 - eta_fan_min__W0))
    #Multiply pressure with volume flow.
    df['e_fan_exh__W'] = df['exhaust_fan__Pa'] * df['air_flow_office__m3_s_1'] / df['eta_fan__W0']
    FiniteOutputFrame(df=df, columns=('venturi_draft__Pa', 'exhaust_fan__Pa', 'e_fan_exh__W'))

    return df
