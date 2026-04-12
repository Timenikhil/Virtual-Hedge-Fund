import os
import json
import firebase_admin
from firebase_admin import credentials

from vhf.logging.log import logger

def initialize_firebase_admin():
    """
    Securely initializes the Firebase Admin app once, based on the environment.

    This function is safe to call on module load, even with hot-reloading,
    as it checks if the app is already initialized.

    - In "production", it uses the file path from GOOGLE_APPLICATION_CREDENTIALS.
    - In "development" (or any other state), it uses the JSON string from FIREBASE_SERVICE_ACCOUNT_JSON.
    """
    try:
        # This check prevents the app from crashing on hot-reload
        firebase_admin.get_app()
        logger.info("Firebase Admin SDK already initialized.")
        return
    except ValueError:
        # App not initialized, proceed with setup
        logger.info("Initializing Firebase Admin SDK...")

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized.")
            return
        except Exception as e:
            logger.warn(f"Failed to initialize from path {e}")
    else: # For Serverless
        logger.info("GOOGLE_APPLICATION_CREDENTIALS env var is not set.")

    cred_json_str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not cred_json_str:
        logger.error("FIREBASE_SERVICE_ACCOUNT_JSON env var is not set.")
        raise ImportError("No Firebase Admin credentials found")

    try:
        cred_dict = json.loads(cred_json_str)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized.")
        return
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
        raise ImportError("Failed to initialize Firebase: Invalid JSON in env var.")
    except Exception as e:
        logger.error(f"Failed to initialize from JSON string: {e}")
        raise ImportError(f"Firebase Admin initialization failed from JSON string: {e}")
