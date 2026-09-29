# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy


"""
EWF Utils module voor EWF Tech Simulator.

Deze module bevat fysieke constanten, conversiefactoren en hulpfuncties
voor de EWF Tech Simulator. Omvat alle benodigde utilities voor de berekeningen
in de diverse modules.
"""

import numpy as np
import pandas as pd
import os

# Conversiefactoren 
dm3_m_3 = 1000
Wh_kWh_1 = 1000
s_min_1 = 60
min_h_1 = 60
s_h_1 = s_min_1 * min_h_1
temp_0_degC__K = 273.15

# Fysieke constanten 
g__m_s_2 = 9.81
Boltzmann_constant__W_m_2_K_4 = 5.67e-8
air__J_kg_1_K_1 = 1007
air_20C__kg_m_3 = 1.205
air_0C__kg_m_3 = 1.293
water__kg_m_3=1000
water__J_kg_1_K_1=4184
vapour__J_kg_1_K_1=2020
gas_constant_water__J_kg_1_K_1=462
latent_heat_water__J_kg_1=2257000

# EWF constanten
air_flow_office_set__dm3_s_1_p_1 = 10.0
temp_air_office_in__degC=18
temp_air_office_out__degC=21

# EWF constanten voor ventilatoren
#Oscar 27aug26 Erronous max corrected (now set in module occupancy)
#fan_max__m3_h_1=67500
flow_modulation_depth__0 = 0.2 #0.2 #minimum vantilation flow in building (e.g. night)
fan_modulation_depth__0 = 0.2 #0.2 #point of minimal fan efficiency (maximal eff at 1.0)
#Oscar 27aug26 Fan min and max now calculated and used only in module occupancy
#fan_min__m3_h_1=fan_max__m3_h_1*fan_modulation_depth__0
#fan_max__m3_s_1=fan_max__m3_h_1/s_h_1
#fan_min__m3_s_1=fan_min__m3_h_1/s_h_1
eta_fan_max__W0=0.72
eta_fan_min__W0=0.4

# EWF constants for wind speed correction based on height
wind_knmi_height__m = 10
wind_knmi_roughness_length__m = 0.03
wind_local_roughness_length__m = 0.5
wind_local_displacement_height__m = 10
wind_reference_height__m = 60
wind_correction_factor__0=(np.log(wind_reference_height__m / wind_knmi_roughness_length__m) / np.log(wind_knmi_height__m / wind_knmi_roughness_length__m)) / np.log((wind_reference_height__m+wind_local_displacement_height__m-wind_knmi_height__m) / wind_local_roughness_length__m)
venturi_wind_acceleration__0 = 1.25

# EWF generic simulation component utities

# Declare Grasshopper input variables with type hints to satisfy Pylance
calc_start: bool
in_data_filepath: str
out_data_filepath: str

# Get the directory of ewf_utils.py and set base directory to ../data
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))

default_filepath='ewf-sim-data.parquet'

# Create the data directory if it doesn't exist
try:
    os.makedirs(BASE_DIR, exist_ok=True)
except PermissionError as e:
    pass  # Stil fout bij directory creatie
