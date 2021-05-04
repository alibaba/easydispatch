import logging
from dispatch.config import LOG_LEVEL, module_levels


def configure_logging():
    if LOG_LEVEL == "DEBUG":
        # log level:logged message:full module path:function invoked:line number of logging call
        LOGFORMAT = "%(levelname)s:%(message)s:%(pathname)s:%(funcName)s:%(lineno)d"
        logging.basicConfig(level=LOG_LEVEL, format=LOGFORMAT)
    else:
        logging.basicConfig(level=LOG_LEVEL)

    for log_key in module_levels:
        # print(f"setting log level: {log_key} = {module_levels[log_key]}")
        log = logging.getLogger(log_key)
        log.setLevel(module_levels[log_key])