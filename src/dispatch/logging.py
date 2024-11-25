import logging
from dispatch.config import LOG_LEVEL, LOG_FILE,  module_levels # LOG_FILE_CALL_BACK, LOG_FILE_E6YUN,
import sys

def configure_logging():

    # write to console
    # formatter = logging.Formatter("[%(asctime)s] %(filename)s(%(lineno)d) : %(message)s", "%Y-%m-%d %H:%M:%S")
    # console = logging.StreamHandler(sys.stdout)
    # console.setLevel(logging.INFO)
    # console.setFormatter(formatter)
    # root_logger = logging.getLogger()
    # root_logger.addHandler(console)


    # fh = logging.FileHandler(LOG_FILE)
    # # callback_fh = logging.FileHandler(LOG_FILE_CALL_BACK)
    # # e6yun_fh = logging.FileHandler(LOG_FILE_E6YUN)
    # fh_formatter = logging.Formatter(
    #     '%(asctime)s  [%(levelname)s]:%(message)s', datefmt='%Y/%m/%d %H:%M:%S')
    # fh.setFormatter(fh_formatter)
    # fh.setLevel(LOG_LEVEL)

    # callback_fh.setFormatter(fh_formatter)
    # callback_fh.setLevel('INFO')

    # e6yun_fh.setFormatter(fh_formatter)
    # e6yun_fh.setLevel('INFO')
    LOGFORMAT = "[%(asctime)s][%(filename)s(%(lineno)d)] %(levelname)s:%(message)s"
    logging.basicConfig(
        # filename=LOG_FILE,
        level=LOG_LEVEL, 
        format=LOGFORMAT,
        datefmt="%m-%dT%H:%M:%S",
        encoding='utf-8',
        )
    # logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    # formatter = logging.Formatter("[%(asctime)s] %(filename)s(%(lineno)d) : %(message)s", "%Y-%m-%dT%H:%M:%S")
    # console = logging.StreamHandler()
    # console.setFormatter(formatter)
    # logging.getLogger().addHandler(console)

    # fh = logging.FileHandler(LOG_FILE)
    # fh.setFormatter(formatter)
    # log = logging.getLogger()
    # log.addHandler(fh)


    for log_key, log_value in module_levels.items():
        log = logging.getLogger(log_key)
        log.setLevel(log_value)
        # log.addHandler(fh)
