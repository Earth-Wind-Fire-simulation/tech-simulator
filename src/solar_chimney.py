# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Zonnekachel berekeningsmodule voor EWF Tech Simulator.

Deze module berekent zonnekachelcondities en warmteoverdracht
voor de zonnekachel in het EWF systeem. Omvat complexe thermodynamische
berekeningen en warmtestraling.
"""

import numpy as np
import pandas as pd
from astral.location import Location, LocationInfo
from scipy.optimize import fsolve
# from tqdm import tqdm  # Toegevoegd voor voortgangsbalk
import sys
from ewf_utils import Boltzmann_constant__W_m_2_K_4, temp_0_degC__K, air_0C__kg_m_3, air_20C__kg_m_3, air__J_kg_1_K_1, temp_air_office_out__degC, g__m_s_2

# Codewaarden
solar_chimney_tilt__degV = 0
solar_chimney_tilt__degH = (90 - solar_chimney_tilt__degV) % 180
solar_chimney_emissivity__0 = 0.793

def segment_equations(vars, air_in_temp__degC, temp_outdoor__degC, air_flow_office__m3_s_1, 
                      solar_chimney_width__m, solar_chimney_depth__m, glazing_fraction__0, segment_height__m,
                      solar_chimney_cross_section__m2, glazing_transmittance__0,
                      solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1, solar_chimney_emissivity__0,
                      solar_chimney__W_m_2):
    """Bereken condities voor een enkele zonnekachel segment."""
    wall_temp__degC, glass_temp__degC, air_temp__degC = vars
    air_velocity__m_s_1 = air_flow_office__m3_s_1 / solar_chimney_cross_section__m2

    heat_tr_rad__W_m_2_K_1 = 4 * solar_chimney_emissivity__0 * Boltzmann_constant__W_m_2_K_4 * \
                             ((wall_temp__degC + glass_temp__degC) / 2 + temp_0_degC__K)**3
    heat_tr_glass_air__W_m_2_K_1 = 3 * np.abs(glass_temp__degC - air_temp__degC)**(1/3)
    heat_tr_wall_air__W_m_2_K_1 = np.abs((wall_temp__degC - air_temp__degC) + (8 * air_velocity__m_s_1)**3)**(1/3)

    glass_outdoor__W = segment_height__m * solar_chimney_width__m * \
                       solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1 * (glass_temp__degC - temp_outdoor__degC)
    glass_air__W = segment_height__m * solar_chimney_width__m * \
                   heat_tr_glass_air__W_m_2_K_1 * (glass_temp__degC - air_temp__degC)
    rad_wall_glass__W = segment_height__m * solar_chimney_width__m * \
                      heat_tr_rad__W_m_2_K_1 * (wall_temp__degC - glass_temp__degC)
    conv_wall_air__W = segment_height__m * solar_chimney_width__m * \
                       heat_tr_wall_air__W_m_2_K_1 * (wall_temp__degC - air_temp__degC)
    irradiance__W = segment_height__m * solar_chimney_width__m * glazing_fraction__0 * \
                    glazing_transmittance__0 * solar_chimney__W_m_2
    heat_loss__W = solar_chimney_width__m * solar_chimney_depth__m * air_20C__kg_m_3 * \
                   air__J_kg_1_K_1 * (air_temp__degC - air_in_temp__degC) * air_velocity__m_s_1

    eq1 = glass_outdoor__W + glass_air__W - rad_wall_glass__W       # Heat balance glass
    eq2 = glass_air__W + conv_wall_air__W - heat_loss__W            # Heat balance air
    eq3 = conv_wall_air__W + rad_wall_glass__W - irradiance__W      # Heat balance wall
    return [eq1, eq2, eq3]

def calculate_solar_chimney(df,
                           weather_location__degN=52.37,
                           weather_location__degE=4.90,
                           solar_chimney_height__m=16.0,
                           solar_chimney_segments__0=10,
                           solar_chimney_width__m=3.2,
                           solar_chimney_depth__m=1.4,
                           solar_chimney_azimuth__degN=180.0,
                           glazing_transmittance__0=0.7,
                           glazing__pct=80,
                           solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1=1.2):
    """Core solar chimney calculation.

    Args:
        df: Input DataFrame with required columns.
        weather_location__degN: Latitude (degrees North), default 52.37.
        weather_location__degE: Longitude (degrees East), default 4.90.
        solar_chimney_height__m: Chimney height (m), default 16.0.
        solar_chimney_segments__0: Number of segments, default 10.
        solar_chimney_width__m: Chimney width (m), default 3.2.
        solar_chimney_depth__m: Chimney depth (m), default 1.4.
        solar_chimney_azimuth__degN: Azimuth (degrees North), default 180.0.
        glazing_transmittance__0: Glazing transmittance, default 0.7.
        glazing__pct: Glazing percentage, default 80.
        solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1: Heat transfer coefficient (W/m²/K), default 1.2.

    Returns:
        DataFrame with added columns: temp_air_chimney_out__degC, chimney_draft__Pa.
    """
    if df is None:
        raise ValueError("Input DataFrame is required for solar chimney calculation.")
    
    # Maak een kopie van de input DataFrame om mutatieproblemen in Grasshopper te voorkomen
    df = df.copy()
    
    glazing_fraction__0 = glazing__pct / 100
    solar_chimney_cross_section__m2 = solar_chimney_width__m * solar_chimney_depth__m
    segment_height__m = solar_chimney_height__m / solar_chimney_segments__0
    solar_chimney_segments__0=int(solar_chimney_segments__0)
   
    # deze print is voor debugging
    print('aantal segmenten',solar_chimney_segments__0) 

    tb = df['tijd met tijdzone']
    tbstr = ['']*len(tb)
    for i in range(len(tb)):
        tbi = tb[i]
        tbstr[i] = str(tbi.strftime('%d-%m-%Y %H:%M %z'))
    # print(tbstr)
    df['tijd met tijdzone'] = tbstr
    
    # Locatie van de waarnemer met
    # eerst breedtegraad (noord = positief)
    # en dan lengtegraad (oost is positief)
    lc = LocationInfo('use coordinates', 'use coordinates', 'use coordinates', weather_location__degN, weather_location__degE)

    # Orientatie van de zonneschoorsteen: Noord = 0, Oost = 90
    hoek = solar_chimney_azimuth__degN

    # Stand van de zon: x1 = cos(el)*cos(az), y1 = cos(el)*sin(az), z1 = sin(el)
    # Normaal van de schoorsteen: x2 = cos(hoek), y2 = sin(hoek), z2 = nul
    # De instralingsfactor is het inwendig product x1*x2 + y1*y2 + z1*z2 (mits de lengtes één zijn)

    # Vectorized arrays voor betere performance
    factor = np.zeros(len(tb))
    az = np.zeros(len(tb))
    el = np.zeros(len(tb))
    
    # Batch solar calculations (vectorized waar mogelijk)
    # Probeer vectorized astral calculations (complex - kan niet altijd vectorized worden)
    for i in range(len(tb)):
        az[i] = Location(lc).solar_azimuth(tb[i])  # Azimut: Noord = 0, Oost = 90
        el[i] = Location(lc).solar_elevation(tb[i])  # Elevatie: Hoogte boven de horizon
        factor[i] = np.max([np.cos((np.pi / 180) * el[i]) * np.cos((np.pi / 180) * (hoek - az[i])), 0])
    df['azimut'] = az
    df['elevatie'] = el
    df['instralingsfactor'] = factor


    # Temporary solar calculation (to be replaced with pvlib)
    df['solar_chimney__W_m_2'] = (
        df['sol_ghi__W_m_2'] * df['instralingsfactor']
    )

    # Pre-allocate output arrays (geoptimaliseerd)
    simulation_intervals__0 = len(df)
    wall_temps = np.zeros((simulation_intervals__0, solar_chimney_segments__0), dtype=np.float64)
    glass_temps = np.zeros((simulation_intervals__0, solar_chimney_segments__0), dtype=np.float64)
    air_temps = np.zeros((simulation_intervals__0, solar_chimney_segments__0), dtype=np.float64)
    temp_air_chimney_out__degC = np.zeros(simulation_intervals__0, dtype=np.float64)
    temp_air_chimney_average__degC = np.zeros(simulation_intervals__0, dtype=np.float64)
    chimney_delta__Pa = np.zeros(simulation_intervals__0, dtype=np.float64)
    shunt_delta__Pa = np.zeros(simulation_intervals__0, dtype=np.float64)
    outdoor_chimney_delta__Pa = np.zeros(simulation_intervals__0, dtype=np.float64)

    # Simulation loop
    #initial_guess = [40, 50, 22]  # [wall_temp, glass_temp, air_temp] in °C

    # Pre-extract data voor betere performance
    temp_outdoor_K_series = df['temp_outdoor__degC'] + temp_0_degC__K
    solar_chimney_W_m_2_series = df['solar_chimney__W_m_2']
    air_flow_office_m3_s_1_series = df['air_flow_office__m3_s_1']
    
    # Batch processing waar mogelijk (vectorized data access)
    for interval in range(simulation_intervals__0):
        temp_outdoor__K = temp_outdoor_K_series.iloc[interval]
        solar_chimney__W_m_2 = solar_chimney_W_m_2_series.iloc[interval]
        air_flow_office__m3_s_1 = air_flow_office_m3_s_1_series.iloc[interval]
        air_in_temp__degC = temp_air_office_out__degC

        initial_guess = [40, 50, 22]  # [wall_temp, glass_temp, air_temp] in °C
        for segment in range(solar_chimney_segments__0):
            solution = fsolve(
                segment_equations,
                initial_guess,
                args=(air_in_temp__degC, temp_outdoor__K - temp_0_degC__K, air_flow_office__m3_s_1, 
                      solar_chimney_width__m, solar_chimney_depth__m, glazing_fraction__0, segment_height__m,
                      solar_chimney_cross_section__m2, glazing_transmittance__0,
                      solar_chimney_heat_tr_glass_outdoor__W_m_2_K_1, solar_chimney_emissivity__0,
                      solar_chimney__W_m_2)
            )
            wall_temps[interval, segment], glass_temps[interval, segment], air_temps[interval, segment] = solution
            air_in_temp__degC = air_temps[interval, segment]
            initial_guess = solution

        temp_air_chimney_out__degC[interval] = air_temps[interval, -1]
        temp_air_chimney_average__degC[interval] = (temp_air_office_out__degC + temp_air_chimney_out__degC[interval]) / 2
        temp_air_chimney_average__K = temp_air_chimney_average__degC[interval] + temp_0_degC__K
        temp_outdoor__K = df['temp_outdoor__degC'].iloc[interval] + temp_0_degC__K
        temp_air_office_out__K = temp_air_office_out__degC + temp_0_degC__K
        chimney_delta__Pa[interval] = air_0C__kg_m_3 * (temp_0_degC__K / temp_air_chimney_average__K) * g__m_s_2 * solar_chimney_height__m
        shunt_delta__Pa[interval] = air_0C__kg_m_3 * (temp_0_degC__K / temp_air_office_out__K ) * g__m_s_2 * solar_chimney_height__m
        outdoor_chimney_delta__Pa[interval] = air_0C__kg_m_3 * (temp_0_degC__K / temp_outdoor__K) * g__m_s_2 * solar_chimney_height__m

    df['temp_air_chimney_out__degC'] = temp_air_chimney_out__degC
    df['temp_air_chimney_average__degC'] = temp_air_chimney_average__degC
    df['chimney_delta__Pa'] = chimney_delta__Pa
    df['shunt_delta__Pa'] = shunt_delta__Pa
    df['outdoor_chimney_delta__Pa'] = outdoor_chimney_delta__Pa
    df['temp_air_heat_recovery_in__degC'] = df['temp_air_chimney_out__degC']

    # Optionally include segment temperatures
    # df['wall_temps__degC'] = list(wall_temps)
    # df['glass_temps__degC'] = list(glass_temps)
    # df['air_temps__degC'] = list(air_temps)
    return df