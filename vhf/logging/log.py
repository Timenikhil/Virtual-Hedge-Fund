import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from logging_loki import LokiQueueHandler

load_dotenv()

LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")  # Make sure this directory exists and has write permissions
LOKI_URL =  os.getenv("LOKI_URL") # e.g., "https://logs-prod-us-central1.grafana.net/loki/api/v1/push"
LOKI_USERNAME = os.getenv("LOKI_USERNAME")
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD")


# 1. Get the root logger
# You can also use a specific logger like: logger = logging.getLogger("my_app")
logger = logging.getLogger("vhf")
logger.setLevel(logging.INFO) # Set the lowest level of logs to be handled

# 2. Create a formatter to define the log message format
# This format will be used by all handlers unless overridden
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 3. Create a handler to write logs to a local file
# TimedRotatingFileHandler will rotate the log file daily, keeping the last 7 files
file_handler = TimedRotatingFileHandler(
    filename=LOG_FILE_PATH,
    when="midnight",
    interval=1,
    backupCount=7
)
file_handler.setFormatter(formatter)

# 4. Create a handler to send logs to Grafana Loki
loki_handler = LokiQueueHandler(
    url=LOKI_URL,
    auth=(LOKI_USERNAME, LOKI_PASSWORD),
    tags={"application": "virtual-hedge-fundF", "environment": "production"},
    version="1",

)

# 5. Add BOTH handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(loki_handler)

# To also see logs in console when running interactively
if os.getenv("LOG_CONSOLE") == 'True':
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)