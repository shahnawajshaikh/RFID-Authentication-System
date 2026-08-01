"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : auth.py
 Description : Contains the core authentication logic. Verifies scanned
               UIDs against the SQLite database via DatabaseManager, logs
               every attempt, sends the GRANTED/DENIED result back to the
               Arduino via SerialManager, and optionally launches an
               authorized program (e.g., Notepad) on success.

               This module NEVER interacts with the Windows login/lock
               screen. It only verifies RFID UIDs and, at most, launches
               a normal, pre-approved desktop application.

============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from database import DatabaseError, DatabaseManager, User
from serial_manager import SerialConnectionError, SerialManager
from utils import is_valid_uid, launch_authorized_program, normalize_uid

logger = logging.getLogger(settings.logging.logger_name)


@dataclass
class AuthResult:
    """
    Represents the outcome of a single authentication attempt.

    Attributes:
        uid: The normalized UID that was scanned.
        granted: True if access was granted, False otherwise.
        user: The matched User object, or None if no match was found.
        message: A human-readable status message for GUI display.
    """

    uid: str
    granted: bool
    user: Optional[User]
    message: str


class AuthenticationService:
    """
    Coordinates the authentication workflow:
        1. Receives a scanned UID.
        2. Looks it up in the database.
        3. Logs the attempt (GRANTED/DENIED).
        4. Sends the result back to the Arduino for LED/buzzer feedback.
        5. On success, optionally launches an authorized program.
    """

    def __init__(self, database: DatabaseManager, serial_manager: SerialManager) -> None:
        """
        Initializes the AuthenticationService.

        Args:
            database: The shared DatabaseManager instance.
            serial_manager: The shared SerialManager instance.
        """
        self._database = database
        self._serial_manager = serial_manager

    def authenticate_uid(self, raw_uid: str) -> AuthResult:
        """
        Runs the full authentication workflow for a single scanned UID.

        Args:
            raw_uid: The raw UID string as received from the Arduino.

        Returns:
            An AuthResult describing the outcome.
        """
        uid = normalize_uid(raw_uid)

        if not is_valid_uid(uid):
            logger.warning("Received malformed UID from Arduino: '%s'.", raw_uid)
            result = AuthResult(
                uid=uid, granted=False, user=None,
                message="Malformed UID received from reader.",
            )
            self._finalize(result)
            return result

        try:
            user = self._database.get_user_by_uid(uid)
        except DatabaseError as exc:
            logger.exception("Database error while authenticating UID '%s'.", uid)
            result = AuthResult(
                uid=uid, granted=False, user=None,
                message=f"Database error during authentication: {exc}",
            )
            self._finalize(result)
            return result

        if user is not None:
            result = AuthResult(
                uid=uid, granted=True, user=user,
                message=f"Access granted for '{user.name}'.",
            )
        else:
            result = AuthResult(
                uid=uid, granted=False, user=None,
                message="UID not recognized. Access denied.",
            )

        self._finalize(result)
        return result

    def _finalize(self, result: AuthResult) -> None:
        """
        Handles the shared post-decision steps common to every authentication
        attempt: logging to the database, notifying the Arduino, and
        launching the authorized program on success.

        Args:
            result: The AuthResult produced by `authenticate_uid`.
        """
        user_name = result.user.name if result.user else settings.auth.unknown_user_label
        status = settings.auth.status_granted if result.granted else settings.auth.status_denied

        try:
            self._database.log_access_attempt(user_name=user_name, uid=result.uid, status=status)
        except DatabaseError:
            logger.exception("Failed to log access attempt for UID '%s'.", result.uid)

        try:
            if self._serial_manager.is_connected():
                self._serial_manager.send_result(granted=result.granted)
        except SerialConnectionError:
            logger.exception("Failed to send authentication result to Arduino.")

        if result.granted and settings.auth.launch_program_on_success:
            launch_authorized_program()
