# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy==1.13.1, openpyxl==3.1.5

"""
Weergegevensverwerkingsmodule voor EWF Tech Simulator.

Deze module handelt weergegevensimport, -verwerking en -conversie
van diverse weergegevensformaten. Incl. foutafhandeling
en bestandsbeschermingsmechanismen.
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd

from exceptions import (
    EWFException,
    create_data_validation_error,
    create_file_not_found_error,
    create_permission_error,
    create_processing_error,
)


def safe_read_csv(pad: str, decimal: str = '.') -> pd.DataFrame:
    """Lees een eigen tijdelijke kopie; laat bron en buur-bestanden ongemoeid.

    Args:
        pad: Pad naar het CSV bestand.
        decimal: Decimaalteken, '.' voor weerdata en ',' voor bezetting.

    Returns:
        DataFrame met data. Bij fouten wordt een EWFException opgegooid.

    Raises:
        DataFileError: Als het bestand niet gevonden kan worden.
        DataFileError: Als er geen toegang is tot het bestand.
        ProcessingError: Als het bestand corrupt is.
    """
    
    # 1. Controleer input
    if not isinstance(pad, (str, os.PathLike)) or not os.fspath(pad).strip() or os.fspath(pad) == "<null>":
        raise create_data_validation_error(
            column='pad',
            expected_type='str (non-empty)',
            actual_value=pad,
            custom_message='Geen geldig bestandspad ontvangen voor weergegevens.'
        )
    
    try:
        with tempfile.TemporaryDirectory(prefix='ewf-csv-') as temp_dir:
            temp_pad = os.path.join(temp_dir, 'input.csv')
            shutil.copyfile(pad, temp_pad)
            df = pd.read_csv(temp_pad, sep=';', decimal=decimal)
        return df
        
    except FileNotFoundError:
        raise create_file_not_found_error(pad)
    except PermissionError:
        raise create_permission_error(pad, "lezen")
    except EWFException:
        raise
    except (OSError, ValueError, pd.errors.ParserError) as e:
        raise create_processing_error(
            step="CSV lezen",
            message=f"Fout bij het lezen van CSV-data: {e}",
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
        if df.empty:
            raise create_data_validation_error('df', 'niet-lege weerdata')
        for column in ['FH', 'T', 'Q', 'P', 'U']:
            if column not in df or not pd.api.types.is_numeric_dtype(df[column]):
                raise create_data_validation_error(column, 'numerieke KNMI-kolom')
            if df[column].isna().any() or not np.isfinite(df[column].to_numpy(dtype=float)).all():
                raise create_data_validation_error(column, 'eindige KNMI-waarden')
        if (df[['FH', 'Q']] < 0).any().any() or (df['P'] <= 0).any() or not df['U'].between(0, 100).all():
            raise create_data_validation_error('FH/Q/P/U', 'wind en straling >= 0, druk > 0, vochtigheid 0..100')
        
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
                
        return df_weather
        
    except EWFException:
        raise
    except (ValueError, TypeError, KeyError, ArithmeticError) as e:
        raise create_processing_error(
            step="Weergegevens verwerking",
            message=f"Fout bij het verwerken van weergegevens: {e}. Controleer het bestandsformaat en inhoud.",
            data_info={'file_path': pad, 'error_type': type(e).__name__}
        )