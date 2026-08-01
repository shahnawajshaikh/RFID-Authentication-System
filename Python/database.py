"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : database.py
 Description : Handles all SQLite database operations: schema creation,
               user management (add/delete/search/list), and access log
               recording/retrieval. Thread-safe since the GUI and serial
               listener thread both access data concurrently.

============================================================================
"""

from __future__ import annotations

import csv
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import settings

logger = logging.getLogger(settings.logging.logger_name)


@dataclass
class User:
    """Represents a single row in the Users table."""

    id: Optional[int]
    name: str
    rfid_uid: str
    created_at: str


@dataclass
class AccessLogEntry:
    """Represents a single row in the AccessLogs table."""

    id: Optional[int]
    user_name: str
    uid: str
    status: str
    date_time: str


class DatabaseError(Exception):
    """Raised when a database operation fails unexpectedly."""


class DuplicateUIDError(DatabaseError):
    """Raised when attempting to add a user with a UID that already exists."""


class UserNotFoundError(DatabaseError):
    """Raised when attempting to operate on a user that does not exist."""


class DatabaseManager:
    """
    Manages all interactions with the SQLite database, including schema
    initialization, user CRUD operations, and access log recording.

    A `threading.Lock` guards all database access since SQLite connections
    created with `check_same_thread=False` can be shared across threads
    (GUI thread + serial listener thread) but writes are not inherently
    safe for concurrent access without external synchronization.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        Initializes the DatabaseManager and ensures the schema exists.

        Args:
            db_path: Optional override for the database file path.
        """
        self._db_path: Path = db_path or settings.paths.database_file
        self._lock: threading.Lock = threading.Lock()
        self._users_table: str = settings.database.users_table
        self._logs_table: str = settings.database.access_logs_table

        settings.paths.ensure_directories_exist()
        self._initialize_schema()
        logger.info("DatabaseManager initialized at '%s'.", self._db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a new SQLite connection with sane defaults."""
        try:
            connection = sqlite3.connect(
                self._db_path,
                timeout=settings.database.connection_timeout_seconds,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            return connection
        except sqlite3.Error as exc:
            logger.exception("Failed to connect to database.")
            raise DatabaseError(f"Could not connect to database: {exc}") from exc

    def _initialize_schema(self) -> None:
        """Creates the Users and AccessLogs tables if they do not exist."""
        create_users_sql = f"""
            CREATE TABLE IF NOT EXISTS {self._users_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rfid_uid TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """
        create_logs_sql = f"""
            CREATE TABLE IF NOT EXISTS {self._logs_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                uid TEXT NOT NULL,
                status TEXT NOT NULL,
                date_time TEXT NOT NULL
            );
        """
        try:
            with self._lock:
                connection = self._get_connection()
                try:
                    connection.execute(create_users_sql)
                    connection.execute(create_logs_sql)
                    connection.commit()
                finally:
                    connection.close()
        except sqlite3.Error as exc:
            logger.exception("Failed to initialize database schema.")
            raise DatabaseError(f"Schema initialization failed: {exc}") from exc

    def add_user(self, name: str, rfid_uid: str) -> User:
        """
        Adds a new user to the Users table.

        Args:
            name: The display name of the user.
            rfid_uid: The unique RFID UID (hex string) for the user.

        Returns:
            The newly created User object.

        Raises:
            DuplicateUIDError: If a user with the same UID already exists.
            DatabaseError: If the insert fails for another reason.
        """
        normalized_uid = rfid_uid.strip().upper()
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

        insert_sql = f"""
            INSERT INTO {self._users_table} (name, rfid_uid, created_at)
            VALUES (?, ?, ?);
        """

        with self._lock:
            connection = self._get_connection()
            try:
                cursor = connection.execute(
                    insert_sql, (name.strip(), normalized_uid, created_at)
                )
                connection.commit()
                new_id = cursor.lastrowid
                logger.info(
                    "Added user '%s' with UID '%s' (id=%s).", name, normalized_uid, new_id
                )
                return User(
                    id=new_id, name=name.strip(), rfid_uid=normalized_uid, created_at=created_at
                )
            except sqlite3.IntegrityError as exc:
                logger.warning("Attempted to add duplicate UID '%s'.", normalized_uid)
                raise DuplicateUIDError(
                    f"A user with UID '{normalized_uid}' already exists."
                ) from exc
            except sqlite3.Error as exc:
                logger.exception("Failed to add user '%s'.", name)
                raise DatabaseError(f"Could not add user: {exc}") from exc
            finally:
                connection.close()

    def delete_user(self, user_id: int) -> None:
        """
        Deletes a user from the Users table by their primary key.

        Args:
            user_id: The database ID of the user to delete.

        Raises:
            UserNotFoundError: If no user with the given ID exists.
            DatabaseError: If the delete operation fails.
        """
        delete_sql = f"DELETE FROM {self._users_table} WHERE id = ?;"

        with self._lock:
            connection = self._get_connection()
            try:
                cursor = connection.execute(delete_sql, (user_id,))
                connection.commit()
                if cursor.rowcount == 0:
                    raise UserNotFoundError(f"No user found with id={user_id}.")
                logger.info("Deleted user with id=%s.", user_id)
            except sqlite3.Error as exc:
                logger.exception("Failed to delete user id=%s.", user_id)
                raise DatabaseError(f"Could not delete user: {exc}") from exc
            finally:
                connection.close()

    def get_user_by_uid(self, rfid_uid: str) -> Optional[User]:
        """
        Retrieves a user record matching the given RFID UID.

        Args:
            rfid_uid: The RFID UID (hex string) to search for.

        Returns:
            A User object if a match is found, otherwise None.
        """
        normalized_uid = rfid_uid.strip().upper()
        select_sql = f"""
            SELECT id, name, rfid_uid, created_at
            FROM {self._users_table}
            WHERE rfid_uid = ?;
        """

        with self._lock:
            connection = self._get_connection()
            try:
                row = connection.execute(select_sql, (normalized_uid,)).fetchone()
                if row is None:
                    return None
                return User(
                    id=row["id"], name=row["name"], rfid_uid=row["rfid_uid"],
                    created_at=row["created_at"],
                )
            except sqlite3.Error as exc:
                logger.exception("Failed to query user by UID '%s'.", normalized_uid)
                raise DatabaseError(f"Could not query user: {exc}") from exc
            finally:
                connection.close()

    def get_all_users(self) -> List[User]:
        """
        Retrieves all users in the Users table, ordered by name.

        Returns:
            A list of User objects.
        """
        select_sql = f"""
            SELECT id, name, rfid_uid, created_at
            FROM {self._users_table}
            ORDER BY name ASC;
        """

        with self._lock:
            connection = self._get_connection()
            try:
                rows = connection.execute(select_sql).fetchall()
                return [
                    User(id=r["id"], name=r["name"], rfid_uid=r["rfid_uid"], created_at=r["created_at"])
                    for r in rows
                ]
            except sqlite3.Error as exc:
                logger.exception("Failed to fetch all users.")
                raise DatabaseError(f"Could not fetch users: {exc}") from exc
            finally:
                connection.close()

    def search_users(self, search_term: str) -> List[User]:
        """
        Searches for users whose name or UID contains the given search term
        (case-insensitive partial match).

        Args:
            search_term: The substring to search for.

        Returns:
            A list of matching User objects.
        """
        pattern = f"%{search_term.strip()}%"
        select_sql = f"""
            SELECT id, name, rfid_uid, created_at
            FROM {self._users_table}
            WHERE name LIKE ? COLLATE NOCASE
               OR rfid_uid LIKE ? COLLATE NOCASE
            ORDER BY name ASC;
        """

        with self._lock:
            connection = self._get_connection()
            try:
                rows = connection.execute(select_sql, (pattern, pattern)).fetchall()
                return [
                    User(id=r["id"], name=r["name"], rfid_uid=r["rfid_uid"], created_at=r["created_at"])
                    for r in rows
                ]
            except sqlite3.Error as exc:
                logger.exception("Failed to search users with term '%s'.", search_term)
                raise DatabaseError(f"Could not search users: {exc}") from exc
            finally:
                connection.close()

    def log_access_attempt(self, user_name: str, uid: str, status: str) -> AccessLogEntry:
        """
        Records an authentication attempt in the AccessLogs table.

        Args:
            user_name: The name of the matched user, or "Unknown".
            uid: The RFID UID that was scanned.
            status: Either "GRANTED" or "DENIED".

        Returns:
            The newly created AccessLogEntry object.
        """
        date_time = datetime.now().isoformat(sep=" ", timespec="seconds")
        insert_sql = f"""
            INSERT INTO {self._logs_table} (user_name, uid, status, date_time)
            VALUES (?, ?, ?, ?);
        """

        with self._lock:
            connection = self._get_connection()
            try:
                cursor = connection.execute(
                    insert_sql, (user_name, uid.strip().upper(), status, date_time)
                )
                connection.commit()
                new_id = cursor.lastrowid
                logger.info(
                    "Logged access attempt: user='%s' uid='%s' status='%s'.", user_name, uid, status
                )
                return AccessLogEntry(
                    id=new_id, user_name=user_name, uid=uid.strip().upper(),
                    status=status, date_time=date_time,
                )
            except sqlite3.Error as exc:
                logger.exception("Failed to log access attempt for UID '%s'.", uid)
                raise DatabaseError(f"Could not log access attempt: {exc}") from exc
            finally:
                connection.close()

    def get_all_logs(self, limit: Optional[int] = None) -> List[AccessLogEntry]:
        """
        Retrieves access log entries, most recent first.

        Args:
            limit: Optional maximum number of entries to return.

        Returns:
            A list of AccessLogEntry objects.
        """
        select_sql = f"""
            SELECT id, user_name, uid, status, date_time
            FROM {self._logs_table}
            ORDER BY id DESC
        """
        if limit is not None:
            select_sql += " LIMIT ?;"
            params: tuple = (limit,)
        else:
            select_sql += ";"
            params = ()

        with self._lock:
            connection = self._get_connection()
            try:
                rows = connection.execute(select_sql, params).fetchall()
                return [
                    AccessLogEntry(
                        id=r["id"], user_name=r["user_name"], uid=r["uid"],
                        status=r["status"], date_time=r["date_time"],
                    )
                    for r in rows
                ]
            except sqlite3.Error as exc:
                logger.exception("Failed to fetch access logs.")
                raise DatabaseError(f"Could not fetch access logs: {exc}") from exc
            finally:
                connection.close()

    def export_logs_to_csv(self, export_path: Path) -> Path:
        """
        Exports all access log entries to a CSV file.

        Args:
            export_path: The full file path where the CSV file should be written.

        Returns:
            The path to the exported CSV file.
        """
        logs = self.get_all_logs()

        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["ID", "User Name", "UID", "Status", "Date/Time"])
                for entry in logs:
                    writer.writerow([entry.id, entry.user_name, entry.uid, entry.status, entry.date_time])
            logger.info("Exported %d log entries to '%s'.", len(logs), export_path)
            return export_path
        except OSError as exc:
            logger.exception("Failed to export logs to CSV at '%s'.", export_path)
            raise DatabaseError(f"Could not export logs to CSV: {exc}") from exc
