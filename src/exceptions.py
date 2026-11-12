"""
Custom exceptions voor EWF Tech Simulator.

Voorziet specifieke, beschrijvende foutafhandeling met foutcodes
en gebruiksvriendelijke berichten.
"""

from typing import Any, Optional


class EWFException(Exception):
    """Basis exception voor EWF Tech Simulator."""
    
    def __init__(self, message: str, error_code: str = None, details: Optional[dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {super().__str__()}"
        return super().__str__()


class DataFileError(EWFException):
    """Exception voor data bestand gerelateerde fouten."""
    
    def __init__(self, message: str, file_path: str = None, error_code: str = None, details: Optional[dict] = None):
        super().__init__(message, error_code, details)
        self.file_path = file_path
    
    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.file_path:
            return f"{base_msg} (Bestand: {self.file_path})"
        return base_msg


class DataValidationError(EWFException):
    """Exception for data validation errors."""
    
    def __init__(self, message: str, column: str = None, expected_type: str = None, error_code: str = None):
        details = {}
        if column:
            details['column'] = column
        if expected_type:
            details['expected_type'] = expected_type
        
        super().__init__(message, error_code, details)
        self.column = column
        self.expected_type = expected_type


class ConfigurationError(EWFException):
    """Exception for configuration related errors."""
    
    def __init__(self, message: str, parameter: str = None, valid_range: str = None, error_code: str = None):
        details = {}
        if parameter:
            details['parameter'] = parameter
        if valid_range:
            details['valid_range'] = valid_range
        
        super().__init__(message, error_code, details)
        self.parameter = parameter
        self.valid_range = valid_range


class ProcessingError(EWFException):
    """Exception for data processing errors."""
    
    def __init__(self, message: str, step: str = None, data_info: Optional[dict] = None, error_code: str = None):
        details = {}
        if step:
            details['step'] = step
        if data_info:
            details.update(data_info)
        
        super().__init__(message, error_code, details)
        self.step = step
        self.data_info = data_info or {}


# Error codes voor consistente error handling
ERROR_CODES = {
    'FILE_NOT_FOUND': 'E001',
    'FILE_PERMISSION': 'E002', 
    'FILE_CORRUPT': 'E003',
    'DATA_VALIDATION': 'E004',
    'CONFIGURATION': 'E005',
    'PROCESSING': 'E006',
    'COLLECTION_EMPTY': 'E007'
}


def create_file_not_found_error(file_path: str) -> DataFileError:
    """Create a standardized file not found error."""
    return DataFileError(
        message=f"Het data bestand '{file_path}' kan niet worden gevonden.",
        file_path=file_path,
        error_code=ERROR_CODES['FILE_NOT_FOUND'],
        details={
            'solutions': [
                "1. Controleer of de bestandsnaam correct is",
                "2. Controleer of het bestand in de juiste map staat", 
                "3. Selecteer opnieuw het data bestand",
                "4. Controleer of de bestandsextensie correct is (.csv)"
            ]
        }
    )


def create_permission_error(file_path: str, action: str = None) -> DataFileError:
    """Create a standardized permission error."""
    message = f"Geen toegang tot bestand '{file_path}'."
    if action:
        message += f" Kan niet {action}."
    
    return DataFileError(
        message=message,
        file_path=file_path,
        error_code=ERROR_CODES['FILE_PERMISSION'],
        details={
            'action': action,
            'solutions': [
                "1. Sluit Excel of andere programma's die het bestand gebruiken",
                "2. Controleer of het bestand niet 'read-only' is",
                "3. Probeer een ander data bestand",
                "4. Herstart Grasshopper en probeer opnieuw",
                "5. Controleer bestandspermissies"
            ]
        }
    )


def create_data_validation_error(column: str, expected_type: str, actual_value: Any = None, custom_message: str = None) -> DataValidationError:
    """Create a standardized data validation error with optional custom message."""
    message = custom_message if custom_message else f"Data validatiefout in kolom '{column}'. Verwacht: {expected_type}."
    if actual_value is not None:
        message += f" Ontvangen: {actual_value!r}."
    error = DataValidationError(
        message=message,
        column=column,
        expected_type=expected_type,
        error_code=ERROR_CODES['DATA_VALIDATION']
    )
    error.details['actual_value'] = actual_value
    return error


def create_configuration_error(parameter: str, valid_range: str, actual_value: Any = None) -> ConfigurationError:
    """Create a standardized configuration error."""
    error = ConfigurationError(
        message=f"Configuratiefout in parameter '{parameter}'. Verwacht: {valid_range}. Ontvangen: {actual_value!r}.",
        parameter=parameter,
        valid_range=valid_range,
        error_code=ERROR_CODES['CONFIGURATION']
    )
    error.details['actual_value'] = actual_value
    return error


def create_processing_error(step: str, message: str, data_info: Optional[dict] = None) -> ProcessingError:
    """Create a standardized processing error."""
    return ProcessingError(
        message=f"Verwerkingsfout in stap '{step}': {message}",
        step=step,
        data_info=data_info,
        error_code=ERROR_CODES['PROCESSING']
    )
