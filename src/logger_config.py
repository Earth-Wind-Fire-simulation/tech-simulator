# venv: ewf-tech

# requirements: numpy==1.24.4, pandas==1.5.3, pytz==2025.2, astral==3.2, scipy==1.13.1, openpyxl==3.1.5

"""
Logging configuratie module voor EWF Tech Simulator.

Deze module voorziet een gestandaardiseerd logging systeem
voor alle modules in de EWF Tech Simulator. Omvat file logging,
formattering en log level configuratie.
"""

import logging
import os
from typing import Optional


class EWFLogger:
    """Logger voor EWF Tech Simulator."""
    
    def __init__(self, name: str, log_level: str = "INFO", log_file: Optional[str] = None):
        """
        Initialiseer EWF logger.
        
        Args:
            name: Module naam voor de logger.
            log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            log_file: Optioneel log bestand pad.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # Verwijder bestaande handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()
        
        # Formattering
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (optioneel)
        if log_file:
            if os.path.dirname(log_file):
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, **kwargs)


# Globale logger configuratie
def get_logger(name: str, log_level: str = "INFO", log_file: Optional[str] = None) -> EWFLogger:
    """
    Krijg een geconfigureerde logger voor een module.
    
    Args:
        name: Module naam.
        log_level: Log level (standaard INFO).
        log_file: Optioneel log bestand pad.
    
    Returns:
        Geconfigureerde EWFLogger instance.
    """
    return EWFLogger(name, log_level, log_file)


# Standaard log bestand
DEFAULT_LOG_FILE = os.path.join(
    os.path.dirname(__file__), '..', 'logs', 'ewf_simulator.log'
)
