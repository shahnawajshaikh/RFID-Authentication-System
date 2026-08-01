"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : main.py
 Description : Application entry point. Sets up logging, ensures required
               directories exist, initializes the Tkinter GUI application,
               and starts the main event loop.

============================================================================
"""

from __future__ import annotations

import logging
import sys

from config import settings
from gui import RFIDAuthApp
from utils import setup_logging


def main() -> int:
    """
    Application entry point.

    Sets up logging, ensures the Database/Logs directories exist, then
    launches the Tkinter GUI application.

    Returns:
        An exit code: 0 on normal exit, 1 on unhandled startup failure.
    """
    logger: logging.Logger = setup_logging()
    logger.info("Starting %s v%s.", settings.app_name, settings.app_version)

    settings.paths.ensure_directories_exist()

    try:
        app = RFIDAuthApp()
        app.mainloop()
        logger.info("Application closed normally.")
        return 0
    except Exception:  # noqa: BLE001 - top-level catch-all for startup failures
        logger.exception("Unhandled exception during application startup/runtime.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
