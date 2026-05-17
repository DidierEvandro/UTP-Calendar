import logging
import os
import sys
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def setup_rpc_logging(is_autorun=False):
    """Configuración para que los logs viajen a la terminal de WinUI 3."""
    logger = logging.getLogger("utp_calendar_autorun" if is_autorun else "utp_calendar_gui")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    
    # Log físico de respaldo
    log_file = LOG_DIR / "utp_calendar_rpc.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    logger.addHandler(file_handler)
    
    # Salida forzada a stdout para captura de C# SOLO si no es autorun silente
    if not is_autorun and sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)
    
    return logger

def get_module_logger(name: str, is_autorun: bool = False) -> logging.Logger:
    base_logger = logging.getLogger("utp_calendar_autorun" if is_autorun else "utp_calendar_gui")
    
    if not base_logger.handlers:
        setup_rpc_logging(is_autorun)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger