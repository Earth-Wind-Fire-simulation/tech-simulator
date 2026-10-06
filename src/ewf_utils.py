# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy==1.13.1, openpyxl==3.1.5


"""
EWF Utils module voor EWF Tech Simulator.

Deze module bevat fysieke constanten, conversiefactoren en hulpfuncties
voor de EWF Tech Simulator. Omvat alle benodigde utilities voor de berekeningen
in de diverse modules.
"""

import os

import numpy as np
import pandas as pd

# Conversiefactoren 
dm3_m_3 = 1000
Wh_kWh_1 = 1000
s_min_1 = 60
min_h_1 = 60
s_h_1 = s_min_1 * min_h_1
temp_0_degC__K = 273.15

# Fysieke constanten 
g__m_s_2 = 9.80665
Boltzmann_constant__W_m_2_K_4 = 5.670374419e-8
air__J_kg_1_K_1 = 1005.7
air_20C__kg_m_3 = 1.2041
air_0C__kg_m_3 = 1.2922
water__kg_m_3 = 998.2
water__J_kg_1_K_1 = 4182
vapour__J_kg_1_K_1 = 2010
gas_constant_water__J_kg_1_K_1 = 461.526
latent_heat_water__J_kg_1 = 2256400

# EWF constanten
air_flow_office_set__dm3_s_1_p_1 = 10.0
temp_air_office_in__degC = 18
temp_air_office_out__degC = 21

# EWF constanten voor ventilatoren
#Oscar 27aug26 Erronous max corrected (now set in module occupancy)
flow_modulation_depth__0 = 0.2 #0.2 #minimum vantilation flow in building (e.g. night)
fan_modulation_depth__0 = 0.2 #0.2 #point of minimal fan efficiency (maximal eff at 1.0)
#Oscar 27aug26 Fan min and max now calculated and used only in module occupancy
eta_fan_max__W0 = 0.72 #TODO: adjust curve to be more representative of actual fan performance
eta_fan_min__W0 = 0.4

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
