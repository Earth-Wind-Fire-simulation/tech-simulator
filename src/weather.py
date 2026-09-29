# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy

"""
Weergegevensverwerkingsmodule voor EWF Tech Simulator.

Deze module handelt weergegevensimport, -verwerking en -conversie
van diverse weergegevensformaten. Incl. foutafhandeling
en bestandsbeschermingsmechanismen.
"""

import pandas as pd
import os
import shutil
from typing import Optional
from exceptions import create_file_not_found_error, create_permission_error, create_data_validation_error, create_processing_error

def safe_read_csv(pad: str) -> Optional[pd.DataFrame]:
    """Lees CSV bestand veilig zonder het origineel te verwijderen.

    Args:
        pad: Pad naar het CSV bestand.

    Returns:
        DataFrame met data of None bij fout.

    Raises:
        DataFileError: Als het bestand niet gevonden kan worden.
        DataFileError: Als er geen toegang is tot het bestand.
        ProcessingError: Als het bestand corrupt is.
    """
    
    # 1. Controleer input
    if pad is None or pad == "" or pad == "<null>":
        raise create_data_validation_error(
            column='pad',
            expected_type='str (non-empty)',
            actual_value=pad,
            custom_message='Geen geldig bestandspad ontvangen voor weergegevens.'
        )
    
    # 2. Maak een tijdelijke kopie
    base_name = os.path.splitext(pad)[0]
    extension = os.path.splitext(pad)[1]
    temp_pad = f"{base_name}_temp{extension}"
    
    try:
        # 3. Kopieer het origineel
        shutil.copy2(pad, temp_pad)
        
        # 4. Lees de kopie
        df = pd.read_csv(temp_pad, sep=";")
        
        # 5. Verwijder de kopie
        os.remove(temp_pad)
        
        # 6. Controleer origineel
        if not os.path.exists(pad):
            raise create_processing_error(
                step="Bestandsverificatie",
                message="Origineel bestand is verdwenen na kopie operatie",
                data_info={'original_file': pad, 'temp_file': temp_pad}
            )
            
        return df
        
    except FileNotFoundError:
        raise create_file_not_found_error(pad)
    except PermissionError:
        raise create_permission_error(pad, "lezen")
    except Exception as e:
        raise create_processing_error(
            step="CSV lezen",
            message=f"Onverwachte fout bij het lezen van weather data: {str(e)}",
            data_info={'file_path': pad, 'error_type': type(e).__name__}
        )

# Weergegevens ophalen/genereren logica
def retrieve_weather_data(pad: str) -> pd.DataFrame:
    """Haal weergegevens op en verwerk naar standaard formaat.

    Args:
        pad: Pad naar het weergegevens CSV bestand.

    Returns:
        DataFrame met verwerkte weergegevens met kolommen:
        - wind__m_s_1: Windsnelheid in m/s
        - temp_outdoor__degC: Buitentemperatuur in °C
        - sol_ghi__W_m_2: Globale zonnestraling in W/m²
        - Air_outdoor__Pa: Luchtdruk in Pa
        - humidity_outdoor_rel__0: Relatieve vochtigheid als fractie

    Raises:
        DataFileError: Als het bestand niet gelezen kan worden.
        ProcessingError: Als data verwerking faalt.
    """
    try:
        df = safe_read_csv(pad)
        
        # Haal relevante kolommen uit dataframe
        wind = df['FH']
        temp = df['T']
        zon = df['Q']
        druk = df['P']
        vocht = df['U']
        
        # Kolom bezetting omrekenen van procent naar fractie
        wind = 0.10*wind
        temp = 0.10*temp
        zon = (10000./3600.)*zon
        druk = 10.*druk
        vocht = 0.010*vocht
        
        # Maak een nieuw dataframe van relevante kolommen (efficiënt)
        df_weather = pd.DataFrame({
            'wind__m_s_1': wind,
            'temp_outdoor__degC': temp,
            'sol_ghi__W_m_2': zon,
            'Air_outdoor__Pa': druk,
            'humidity_outdoor_rel__0': vocht
        })
        
        # Controleer of resultaat geldig is
        #if df_weather is None or len(df_weather) == 0:
        #    raise create_processing_error(
        #        step="Weergegevens validatie",
        #        message="Geen geldige weergegevens gevonden in het bestand. Controleer of het bestand correcte data bevat.",
        #        data_info={'file_path': pad, 'data_length': len(df_weather) if df_weather is not None else 0}
        #    )
        
        return df_weather
        
    except Exception as e:
        raise create_processing_error(
            step="Weergegevens verwerking",
            message=f"Fout bij het verwerken van weergegevens: {str(e)}. Controleer het bestandsformaat en inhoud.",
            data_info={'file_path': pad, 'error_type': type(e).__name__}
        )