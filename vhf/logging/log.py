import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Queue

from dotenv import load_dotenv
from logging_loki import LokiQueueHandler

load_dotenv()
# Avoid noisy tracebacks if a logging handler (e.g., Loki) fails to emit.
logging.raiseExceptions = False

logger = logging.getLogger("vhf")
logger.setLevel(logging.INFO) # Set the lowest level of logs to be handled

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")  # Make sure this directory exists and has write permissions
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
if LOG_FILE_PATH:
    # TimedRotatingFileHandler will rotate the log file daily, keeping the last 7 files
    file_handler = TimedRotatingFileHandler(
        filename=LOG_FILE_PATH,
        when="midnight",
        interval=1,
        backupCount=7
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

LOKI_URL =  os.getenv("LOKI_URL")
if LOKI_URL:
    LOKI_USERNAME = os.getenv("LOKI_USERNAME")
    LOKI_PASSWORD = os.getenv("LOKI_PASSWORD")
    loki_handler = LokiQueueHandler(
        url=LOKI_URL,
        auth=(LOKI_USERNAME, LOKI_PASSWORD),
        tags={"application": "virtual-hedge-fund", "environment": "production"},
        version="1",
        queue=Queue(1000)
    )
    logger.addHandler(loki_handler)

# To also see logs in console when running interactively
if os.getenv("LOG_CONSOLE") == 'True':
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
