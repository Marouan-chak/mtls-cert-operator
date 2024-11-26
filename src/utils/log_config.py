import logging

# Logging configuration
LOG_FORMAT = '[%(asctime)s] %(name)-20s [%(levelname)-8s] %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S,%03d'

def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = []
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT
    )
    
    # Configure kopf's logging format
    for handler in logging.getLogger().handlers:
        handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT)) 