"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : utils.py
 Description : Miscellaneous shared utility functions used across the
               application: logging setup, UID validation/formatting,
               timestamp helpers, and safe external-program launching.

============================================================================
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from config import settings

_UID_PATTERN = re.compile(r"^[0-9A-Fa-f]{4,20}$")


def setup_logging() -> logging.Logger:
    """
    Configures and returns the application-wide logger.

    Sets up a rotating file handler (writing to Logs/access.log) and a
    console handler, both using the format defined in config.LoggingConfig.

    Returns:
        The configured `logging.Logger` instance.
    """
    settings.paths.ensure_directories_exist()

    logger = logging.getLogger(settings.logging.logger_name)
    logger.setLevel(settings.logging.log_level)

    if logger.handlers:
        # Logging has already been configured (e.g., in a previous call);
        # avoid attaching duplicate handlers.
        return logger

    formatter = logging.Formatter(
        fmt=settings.logging.log_format,
        datefmt=settings.logging.date_format,
    )

    file_handler = RotatingFileHandler(
        filename=settings.paths.log_file,
        maxBytes=settings.logging.max_bytes,
        backupCount=settings.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def is_valid_uid(uid: str) -> bool:
    """
    Validates that a string looks like a plausible RFID UID: a hexadecimal
    string between 4 and 20 characters long (covers 4-byte and 7-byte UIDs).

    Args:
        uid: The UID string to validate.

    Returns:
        True if the UID matches the expected hexadecimal pattern.
    """
    if not uid:
        return False
    return bool(_UID_PATTERN.match(uid.strip()))


def normalize_uid(uid: str) -> str:
    """
    Normalizes a UID string to a consistent format: stripped of whitespace
    and uppercased.

    Args:
        uid: The raw UID string.

    Returns:
        The normalized UID string.
    """
    return uid.strip().upper()


def current_timestamp() -> str:
    """
    Returns:
        The current date/time formatted as "YYYY-MM-DD HH:MM:SS".
    """
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def is_valid_name(name: str) -> bool:
    """
    Validates that a user-provided name is non-empty and contains only
    reasonable characters (letters, numbers, spaces, hyphens, apostrophes).

    Args:
        name: The name string to validate.

    Returns:
        True if the name is considered valid.
    """
    stripped = name.strip()
    if not stripped or len(stripped) > 100:
        return False
    return bool(re.match(r"^[A-Za-z0-9 .'\-_]+$", stripped))


def launch_authorized_program(program_path: Optional[str] = None) -> bool:
    """
    Launches a pre-approved, ordinary application (e.g., Notepad) as a
    reward action after successful RFID authentication.

    IMPORTANT: This function only starts a normal user-space application.
    It does NOT interact with, automate, or bypass the Windows login/lock
    screen, and it does NOT perform any privilege escalation.

    Args:
        program_path: Optional override path to the executable to launch.
            Defaults to `settings.auth.authorized_program_path`.

    Returns:
        True if the program was launched successfully, False otherwise.
    """
    logger = logging.getLogger(settings.logging.logger_name)
    path_to_launch = program_path or settings.auth.authorized_program_path

    try:
        if not Path(path_to_launch).exists():
            logger.warning("Authorized program path does not exist: '%s'.", path_to_launch)
            return False

        subprocess.Popen([path_to_launch])
        logger.info("Launched authorized program: '%s'.", path_to_launch)
        return True
    except (OSError, ValueError):
        logger.exception("Failed to launch authorized program: '%s'.", path_to_launch)
        return False


def truncate_text(text: str, max_length: int = 40) -> str:
    """
    Truncates a string to a maximum length, appending an ellipsis if it
    was shortened. Useful for keeping GUI labels/tables tidy.

    Args:
        text: The text to truncate.
        max_length: The maximum allowed length before truncation.

    Returns:
        The original text, or a truncated version ending in "...".
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
