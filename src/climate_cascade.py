# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Klimaatcascade berekeningsmodule voor EWF Tech Simulator.

Deze module implementeert een klimaatcascadesysteem voor temperatuur- en vochtigheidsregeling
met watersproei-nozzles. Omvat complexe thermodynamische berekeningen
en foutafhandeling.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
from ewf_utils import g__m_s_2, temp_0_degC__K, water__kg_m_3, gas_constant_water__J_kg_1_K_1, air_0C__kg_m_3, air_20C__kg_m_3, water__J_kg_1_K_1, latent_heat_water__J_kg_1, vapour__J_kg_1_K_1, air__J_kg_1_K_1, temp_air_office_in__degC
from exceptions import create_data_validation_error, create_configuration_error, create_processing_error

# Fixed values
#temp_water_cascade_in__degC = 13 (converted to adjustable parameter)
#temp_air_cascade_out_set__degC = 17 (converted to adjustable parameter)
nozzle__kg_s_1 = 0.7
#humidity_abs_set__g_kg_1 = 6.93 (converted to adjustable parameter)
#nozzles_min__0 = 1 (converted to adjustable parameter)
#nozzles_max__0 = 25 (converted to adjustable parameter)
heat_tr_water_air__W_K_1_m_2 = 225
heat_tr_air_wall__W_K_1_m_2 = 12
c_0_vap__Pa = 100
c_1_vap__0 = 18.956
c_2_vap__degC = 4030.18
c_3_vap__degC = 235
k_evap__m_s_1 = 0.0000062 * 0.00089
eta_cascade_water_pump__W0 = 0.75
#loss_cascade_water_nozzle__Pa = 50000 (converted to adjustable parameter)
loss_cascade_water_rest__Pa = 15000
droplet_ave_dia__mm = 0.581
droplet_terminal__m_s_1 = 1.741 * droplet_ave_dia__mm + 0.1623
droplet__vmd_dia__mm = 1.708
droplet_ave__m3 = (4/3) * np.pi * np.power(droplet__vmd_dia__mm / (2 * 1000), 3)
droplet_smd__m3 = 1.377
droplet_ave__m2 = 4 * np.pi * np.power(droplet_smd__m3 / (2 * 1000), 2)
supply__Pa = 150.0
temp_air_office_in__degC = 18.0
temp_long_term_heat_store__degC = 12.0
cop_heat_pump_heating__W0 = 4.5
cop_heat_pump_cooling__W0 = 15.0
e_fan_air_pre_heater__W = 0
e_fan_air_post_heater__W = 0
e_pump_heat_recovery__W = 0
e_fan_heat_recovery__W = 0

outdoor_heat_recovery_threshold__degC = 16
preheat_max__degC = 18
eta_heat_recovery__W0 = 0.5

#Evaluates one segment an calculates input for the next segment
def segment_equations(air_in__degC: float, water_in__degC: float, vapour_in__kg_m_3: float, droplets_in__kg_m_3: float,
                      air__s: float, droplet__s: float, cascade_compactness__m2_m_3: float) -> Tuple[float, float, float, float]:
    """Calculate conditions for a single climate cascade segment.
    Args:
        air_in__degC: float. Temperature of input air
        water_in__degC: float. Temperature of input water
        vapour_in__kg_m_3: float. Vapour mass input
        droplets_in__kg_m_3: float. Water mass input
        air__s: float. Timestep for air in segment
        droplet__s: float. Timestep for water in segment
        cascade_compactness__m2_m_3: float
    Returns: Input for next segment
    """

#Pre-calculations
    vapour__Pa = vapour_in__kg_m_3 * gas_constant_water__J_kg_1_K_1 * (air_in__degC + temp_0_degC__K)
    saturation_water__Pa = c_0_vap__Pa * np.exp(c_1_vap__0 - c_2_vap__degC / (water_in__degC + c_3_vap__degC))
    droplets__m_3 = droplets_in__kg_m_3 / (droplet_ave__m3 * water__kg_m_3)
    droplets__m2_m_3 = droplets__m_3 * droplet_ave__m2

#Calculate mass- and heat transfer from air to droplets (produced latent energy is transfered to water)
    transfer_air_water__kg_s_1_m_3 = k_evap__m_s_1 * heat_tr_water_air__W_K_1_m_2 * droplets__m2_m_3 * (vapour__Pa - saturation_water__Pa)
    latent_heat_tr_to_water__W_m_3 = transfer_air_water__kg_s_1_m_3 * (latent_heat_water__J_kg_1 - vapour__J_kg_1_K_1 * (100 - air_in__degC) + water__J_kg_1_K_1 * (100 - water_in__degC))
    sensible_heat_tr_air_water__W_m_3 = (air_in__degC - water_in__degC) * droplets__m2_m_3 * heat_tr_water_air__W_K_1_m_2

#Calculate mass- and heat transfer from air to wall (produced latent energy is transfered to wall)
    transfer_air_wall__kg_s_1_m_3 = k_evap__m_s_1 * heat_tr_air_wall__W_K_1_m_2 * cascade_compactness__m2_m_3 * (vapour__Pa - saturation_water__Pa)
    latent_heat_tr_to_wall__W_m_3 = transfer_air_wall__kg_s_1_m_3 * (latent_heat_water__J_kg_1 - vapour__J_kg_1_K_1 * (100 - air_in__degC) + water__J_kg_1_K_1 * (100 - water_in__degC))
    sensible_heat_tr_air_wall__W_m_3 = (air_in__degC - water_in__degC) * cascade_compactness__m2_m_3 * heat_tr_air_wall__W_K_1_m_2

#Summarize heat transfer
    heat_tr_from_air__W_m_3 = sensible_heat_tr_air_water__W_m_3 + sensible_heat_tr_air_wall__W_m_3
    heat_tr_to_droplets__W_m_3 = sensible_heat_tr_air_water__W_m_3 + latent_heat_tr_to_water__W_m_3

#Calculate new values for vapour mass, air temperature, water mass and water temperature
    vapour_out__kg_m_3 = vapour_in__kg_m_3 - transfer_air_water__kg_s_1_m_3 * air__s
    heat_air_above0C__J_m_3 = (vapour__J_kg_1_K_1 * vapour_in__kg_m_3 + air__J_kg_1_K_1 * air_20C__kg_m_3) * air_in__degC - heat_tr_from_air__W_m_3 * air__s
    air_out__degC = heat_air_above0C__J_m_3 / (vapour__J_kg_1_K_1 * vapour_out__kg_m_3 + air__J_kg_1_K_1 * air_20C__kg_m_3)
    droplets_out__kg_m_3 = droplets_in__kg_m_3 + transfer_air_water__kg_s_1_m_3 * droplet__s
    heat_water_above0C__J_m_3 = water__J_kg_1_K_1 * droplets_in__kg_m_3 * water_in__degC + heat_tr_to_droplets__W_m_3 * droplet__s
    water_out__degC = heat_water_above0C__J_m_3 / (water__J_kg_1_K_1 * droplets_in__kg_m_3)

    return air_out__degC, water_out__degC, vapour_out__kg_m_3, droplets_out__kg_m_3

#Evaluate climate cascade and repeat this to optimize number of nozzles
def calculate_climate_cascade(df: pd.DataFrame, 
                             height_cascade__m: float = 10.0,
                             cascade_width__m: float = 3.0,
                             cascade_depth__m: float = 2.0,
                             cascade_segments__0: int = 10,
                             temp_water_cascade_in__degC: float = 13,
                             temp_air_in_threshold__degC: float = 16,
                             temp_air_cascade_out_set__degC: float = 17,
                             humidity_abs_set__g_kg_1: float = 6.93,
                             nozzles_min__0: int = 1,
                             nozzles_max__0: int = 25,
                             loss_cascade_water_nozzle__Pa: float = 50000
                             ) -> pd.DataFrame:
    """Core climate cascade calculation.

    Args:
        df: Input DataFrame with required columns.
        height_cascade__m: Cascade height (m), default 10.0.
        cascade_width__m: Cascade width (m), default 3.0.
        cascade_depth__m: Cascade depth (m), default 2.0.
        cascade_segments__0: Number of cascade segments, default 10.
        temp_water_cascade_in__degC: Temperature of water in cascade, default 13.
        temp_air_in_threshold__degC: Threshold for switch between Summer and Winter mode, default = 16.
        temp_air_cascade_out_set__degC: Setpoint for output in Summer mode, default = 17.
        humidity_abs_set__g_kg_1: Setpoint for output in Winter mode, default = 6.93.
        nozzles_min__0: Minimum number of nozzles, default = 1.
        nozzles_max__0: Maximum number of nozzles (capacity), default = 25.
        loss_cascade_water_nozzle__Pa: Pressure drop in nozzle, default = 50000.

    Returns:
        DataFrame with added columns for climate cascade outputs.
    """
# Maak een kopie van de input DataFrame om mutatieproblemen in Grasshopper te voorkomen
    df = df.copy()

    if df is None:
        raise create_data_validation_error(
            column='df',
            expected_type='pd.DataFrame',
            actual_value=None,
            custom_message='Input DataFrame is vereist voor klimaatcascade berekening.'
        )

    if df.empty:
        raise create_data_validation_error(
            column='df',
            expected_type='pd.DataFrame (non-empty)',
            actual_value='empty DataFrame',
            custom_message='Input DataFrame is leeg - geen data om te verwerken.'
        )

    # Valideer vereiste kolommen
    required_columns = [
        'temp_overpressure_out__degC',
        'temp_air_heat_recovery_in__degC',
        'air_flow_office__m3_s_1',
        'humidity_outdoor_rel__0',
        'temp_outdoor__degC',
        'overpressure_room_delta__Pa'
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise create_data_validation_error(
            column='df',
            expected_type='pd.DataFrame met vereiste kolommen',
            actual_value=None,
            custom_message=f'Input DataFrame mist vereiste kolommen voor klimaatcascade berekening: {missing_columns}. '
                           f'Beschikbare kolommen: {list(df.columns)}'
        )

# Pre-calculate cascade geometry
    cascade_segment_height__m = height_cascade__m / cascade_segments__0
    cascade_compactness__m2_m_3 = 2 * (cascade_width__m + cascade_depth__m) / (cascade_width__m * cascade_depth__m)
    cascade_cross_section_0__m2 = cascade_width__m * cascade_depth__m

# Vectorized pre-calculation (heat recovery applied depending on conditions)
    df['temp_air_cascade_in__degC'] = np.where(df['temp_overpressure_out__degC'] < outdoor_heat_recovery_threshold__degC,
                                               np.minimum(preheat_max__degC,
                                                          df['temp_overpressure_out__degC'] + eta_heat_recovery__W0 * (df['temp_air_heat_recovery_in__degC'] - df['temp_overpressure_out__degC'])),
                                               df['temp_overpressure_out__degC'])
    df['cascade_air__m_s_1'] = df['air_flow_office__m3_s_1'] / cascade_cross_section_0__m2

# Initializing output arrays
    output_cols = ['total_droplet_velocity__m_s_1', 'humidity_cascade_in_abs__gr_kg_1', 'nozzles__0', 'temp_air_cascade_out__degC', 'temp_water_cascade_out__degC', 'humidity_cascade_out_abs__gr_kg_1']
    for col in output_cols:
        if col not in df.columns:
            df[col] = np.full(len(df), np.nan)

# Loop over all time-steps (index)
    for index in df.index:
#pre-calculation (inputs for simulation)
        temp_air_cascade__degC = df.loc[index, 'temp_air_cascade_in__degC']
        temp_water_cascade__degC = temp_water_cascade_in__degC
        humidity_outdoor_rel__0 = df.loc[index, 'humidity_outdoor_rel__0']
        temp_outdoor__degC = df.loc[index, 'temp_outdoor__degC']

        air__s = cascade_segment_height__m / df.loc[index, 'cascade_air__m_s_1']
        droplet__m_s_1 = df.loc[index, 'cascade_air__m_s_1'] + droplet_terminal__m_s_1
        df.loc[index, 'total_droplet_velocity__m_s_1'] = droplet__m_s_1
        droplet__s = cascade_segment_height__m / droplet__m_s_1

        saturation_outdoor__Pa = c_0_vap__Pa * np.exp(
            c_1_vap__0 - c_2_vap__degC / (temp_outdoor__degC + c_3_vap__degC))
        vapour__kg_m_3 = (humidity_outdoor_rel__0 * saturation_outdoor__Pa) / (
                    gas_constant_water__J_kg_1_K_1 * (temp_outdoor__degC + temp_0_degC__K))
        humidity_outdoor_abs__gr_kg_1 = 1000 * vapour__kg_m_3 / air_20C__kg_m_3
        df.loc[index, 'humidity_cascade_in_abs__gr_kg_1'] = humidity_outdoor_abs__gr_kg_1

# Default output when ventilation is off (no simulation)
        if df.loc[index, 'cascade_air__m_s_1'] == 0:
            df.loc[index, 'nozzles__0'] = nozzles_min__0
            df.loc[index, 'temp_air_cascade_out__degC'] = temp_air_cascade__degC
            df.loc[index, 'temp_water_cascade_out__degC'] = temp_water_cascade__degC
            df.loc[index, 'humidity_cascade_out_abs__gr_kg_1'] = vapour__kg_m_3
        else: #else perform simulation
#Optimizing number of nozzles (set temperature/humidity must be within interval lo-hi
            lo = nozzles_min__0 - 1
            hi = nozzles_max__0 + 1
            while ( hi - lo > 1 ):
                number_of_nozzles = (lo + hi) // 2

                temp_air_seg__degC = temp_air_cascade__degC
                temp_water_seg__degC = temp_water_cascade__degC
                vapour_seg__kg_m_3 = vapour__kg_m_3
                #Add 0.001 nozzles to prevent div0 error
                droplets_seg__kg_m_3 = (nozzle__kg_s_1 * (number_of_nozzles+0.001)) / (cascade_cross_section_0__m2 * droplet__m_s_1)

#Evaluate cascade for given number of nozzles
                for segment in range(cascade_segments__0):
                    temp_air_seg__degC, temp_water_seg__degC, vapour_seg__kg_m_3, droplets_seg__kg_m_3 = segment_equations(
                        temp_air_seg__degC,
                        temp_water_seg__degC,
                        vapour_seg__kg_m_3,
                        droplets_seg__kg_m_3,
                        air__s,
                        droplet__s,
                        cascade_compactness__m2_m_3)

#Check weather temperature/humidity is below/above setpoint. Adjust inteval lo-hi
                if  ( temp_air_cascade__degC >= temp_air_in_threshold__degC and (temp_air_seg__degC < temp_air_cascade_out_set__degC) ) or ( temp_air_cascade__degC < temp_air_in_threshold__degC and (vapour_seg__kg_m_3 / air_20C__kg_m_3 * 1000 > humidity_abs_set__g_kg_1) ):
                    hi = number_of_nozzles #nozzles is too high. Adjust interval to lo-NON
                    temp_air_hi__degC = temp_air_seg__degC
                    temp_water_hi__degC = temp_water_seg__degC
                    vapour_hi__kg_m_3 = vapour_seg__kg_m_3
                else:
                    lo = number_of_nozzles #nozzles is too low. Adjust interval to NON-hi
                    temp_air_lo__degC = temp_air_seg__degC
                    temp_water_lo__degC = temp_water_seg__degC
                    vapour_lo__kg_m_3 = vapour_seg__kg_m_3
#Select 'lo' unless it remained at the lower limit
            if lo >= nozzles_min__0:
                df.loc[index, 'nozzles__0'] = lo
                df.loc[index, 'temp_air_cascade_out__degC'] = temp_air_lo__degC
                df.loc[index, 'temp_water_cascade_out__degC'] = temp_water_lo__degC
                df.loc[index, 'humidity_cascade_out_abs__gr_kg_1'] = vapour_lo__kg_m_3 / air_20C__kg_m_3 * 1000
            else:
                df.loc[index, 'nozzles__0'] = hi
                df.loc[index, 'temp_air_cascade_out__degC'] = temp_air_hi__degC
                df.loc[index, 'temp_water_cascade_out__degC'] = temp_water_hi__degC
                df.loc[index, 'humidity_cascade_out_abs__gr_kg_1'] = vapour_hi__kg_m_3 / air_20C__kg_m_3 * 1000

    df['water_cascade__kg_s_1'] = nozzle__kg_s_1 * df['nozzles__0']

# Calculate additional outputs
    df['temp_air_cascade_average__degC'] = (2/3 * df['temp_air_cascade_out__degC'] +
                                           1/3 * (df['temp_air_cascade_in__degC'] +
                                                  df['temp_air_cascade_out__degC']) / 2)
    df['cascade_delta_hydro__Pa'] = (df['water_cascade__kg_s_1'] * g__m_s_2 * height_cascade__m /
                                   ((cascade_width__m * cascade_depth__m) *
                                    (droplet_terminal__m_s_1 + df['cascade_air__m_s_1'])))
    df['cascade_delta_therm__Pa'] = air_0C__kg_m_3 * ( temp_0_degC__K / (df['temp_air_cascade_average__degC']+temp_0_degC__K) ) * g__m_s_2 * height_cascade__m
    df['cascade_delta__Pa'] = df['cascade_delta_hydro__Pa'] + df['cascade_delta_therm__Pa']
    df['channel_in_delta__Pa'] = air_0C__kg_m_3 * ( temp_0_degC__K / (temp_air_office_in__degC+temp_0_degC__K)) * g__m_s_2 * height_cascade__m
    df['outdoor_cascade_delta__Pa'] = air_0C__kg_m_3 * ( temp_0_degC__K / (df['temp_outdoor__degC']+temp_0_degC__K)) * g__m_s_2 * height_cascade__m

    # Oscar 27aug26: efficiency for both fans now calculated in module occupancy
    #df['eta_fan_supply__W0'] = (eta_fan_min__W0 + (df['air_flow_office__m3_s_1'] - fan_min__m3_s_1) /
    #                     (fan_max__m3_s_1 - fan_min__m3_s_1) * (eta_fan_max__W0 - eta_fan_min__W0))

    df['supply_fan__Pa'] = np.maximum(0, supply__Pa - df['overpressure_room_delta__Pa'] - df['cascade_delta__Pa']
                                                        + np.maximum(df['outdoor_cascade_delta__Pa'],df['channel_in_delta__Pa']))
#Oscar(17sep26): Formule aangepast voor trek in invoerkanaal. Oorspronkelijke formule:
    #df['supply_fan__Pa'] = np.maximum(0, supply__Pa - df['overpressure_room_delta__Pa'] - df['cascade_delta__Pa'] + df['outdoor_cascade_delta__Pa'])

    df['e_fan_supply__W'] = df['supply_fan__Pa'] * df['air_flow_office__m3_s_1'] / df['eta_fan__W0']

    df['e_cascade_water_pump__W'] = ( ( df['water_cascade__kg_s_1'] / water__kg_m_3 ) *
                                    (water__kg_m_3 * g__m_s_2 * height_cascade__m +
                                     loss_cascade_water_nozzle__Pa +
                                     loss_cascade_water_rest__Pa) / eta_cascade_water_pump__W0)

    df['cascade_heat_pump_is_heating__sign'] = np.sign(temp_water_cascade_in__degC - df['temp_water_cascade_out__degC'])
#update Oscar (30jan26): prepended minus sign inserted for cooling to have positive power (temperature difference is negative)
    df['cop_cascade_heat_pump__W0'] = np.where(df['cascade_heat_pump_is_heating__sign'] == 1,
                                              cop_heat_pump_heating__W0,
                                              -cop_heat_pump_cooling__W0)
    df['e_cascade_heat_pump__W'] = (df['water_cascade__kg_s_1'] * water__J_kg_1_K_1 *
                                   (temp_water_cascade_in__degC - df['temp_water_cascade_out__degC']) /
                                   df['cop_cascade_heat_pump__W0'])

    df['post_cascade_heat_pump_is_heating__sign'] = np.sign(temp_air_office_in__degC - df['temp_air_cascade_out__degC'])
    df['cop_post_cascade_heat_pump__W0'] = np.where(df['post_cascade_heat_pump_is_heating__sign'] == 1,
                                                   cop_heat_pump_heating__W0,
                                                   cop_heat_pump_cooling__W0)
    df['e_post_cascade_heat_pump__W'] = (df['air_flow_office__m3_s_1'] * air_20C__kg_m_3 *
                                        air__J_kg_1_K_1 * np.maximum(0, temp_air_office_in__degC - df['temp_air_cascade_out__degC']) /
                                        df['cop_post_cascade_heat_pump__W0'])

    return df
