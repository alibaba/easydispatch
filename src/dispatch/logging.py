import logging
from dispatch.config import LOG_LEVEL, LOG_FILE, LOG_FILE_CALL_BACK, module_levels


def configure_logging():

    fh = logging.FileHandler(LOG_FILE)
    callback_fh = logging.FileHandler(LOG_FILE_CALL_BACK)
    fh_formatter = logging.Formatter(
        '%(asctime)s  [%(levelname)s]:%(message)s', datefmt='%Y/%m/%d %H:%M:%S')
    fh.setFormatter(fh_formatter)
    fh.setLevel(LOG_LEVEL)

    callback_fh.setFormatter(fh_formatter)
    callback_fh.setLevel('INFO')
    if LOG_LEVEL == "DEBUG":
        # log level:logged message:full module path:function invoked:line number of logging call
        LOGFORMAT = "%(levelname)s:%(message)s:%(pathname)s:%(funcName)s:%(lineno)d"
        logging.basicConfig(level=LOG_LEVEL, format=LOGFORMAT)
    else:
        logging.basicConfig(level=LOG_LEVEL)

    for log_key, log_value in module_levels.items():

        log = logging.getLogger(log_key)
        log.setLevel(log_value)
        if log.handlers:
            continue
        if log_key == 'ipms_apms_rps_callback':
            log.addHandler(callback_fh)
        else:
            log.addHandler(fh)
