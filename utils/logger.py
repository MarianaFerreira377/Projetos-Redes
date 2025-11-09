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
    first_config = not logger.handlers
    
    if first_config:
        if logger.level == logging.NOTSET:
            logger.setLevel(level)
        logger.propagate = False
    
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logger.level)
        logger.addHandler(console_handler)
        
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logger.level)
            logger.addHandler(file_handler)
    else:
        # Não recriar handlers nem sobrescrever níveis já ajustados externamente
        pass
    
    return logger

