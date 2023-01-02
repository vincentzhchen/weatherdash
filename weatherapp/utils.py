import logging
import os


def get_logger():

    home_dir = os.path.expanduser("~")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    log_dir = os.path.join(home_dir, ".weatherdash")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "logs.log"),
        when="D",
        interval=30,
        backupCount=4,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger
