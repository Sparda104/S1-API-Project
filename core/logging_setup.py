import logging, logging.config, os, sys

def configure_logging(debug=False, app_logger_name='scholarone'):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base, 'config', 'logging.ini')
    if os.path.exists(ini_path):
        logging.config.fileConfig(ini_path, disable_existing_loggers=False)
    else:
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    logger = logging.getLogger(app_logger_name)
    if debug:
        logger.setLevel(logging.DEBUG)
    return logger
