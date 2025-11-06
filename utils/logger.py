"""
Sistema de logging para debug e análise.
"""
import logging
import sys
from datetime import datetime


def setup_logger(name, log_file=None, level=logging.INFO):
    """
    Configura um logger.
    
    Args:
        name: nome do logger
        log_file: arquivo para salvar logs (opcional)
        level: nível de log
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Formato das mensagens
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para arquivo (se especificado)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

