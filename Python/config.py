"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : config.py
 Description : Centralized configuration module. Holds all constants, file
               paths, serial settings, GUI theme colors, and application
               settings so no other module contains hardcoded values.

============================================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PathConfig:
    """Holds all filesystem paths used throughout the application."""

    base_dir: Path = BASE_DIR
    database_dir: Path = BASE_DIR / "Database"
    database_file: Path = BASE_DIR / "Database" / "users.db"
    logs_dir: Path = BASE_DIR / "Logs"
    log_file: Path = BASE_DIR / "Logs" / "access.log"
    exports_dir: Path = BASE_DIR / "Logs" / "exports"
    images_dir: Path = BASE_DIR / "Images"

    def ensure_directories_exist(self) -> None:
        """Creates all required directories if they do not already exist."""
        for directory in (
            self.database_dir,
            self.logs_dir,
            self.exports_dir,
            self.images_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class SerialConfig:
    """Holds all serial communication settings used to talk to the Arduino."""

    baud_rate: int = 9600
    timeout_seconds: float = 1.0
    write_timeout_seconds: float = 1.0
    reconnect_delay_seconds: float = 3.0
    auto_detect_keywords: tuple[str, ...] = (
        "Arduino",
        "CH340",
        "USB-SERIAL",
        "USB Serial",
        "wchusbserial",
        "usbmodem",
    )
    handshake_timeout_seconds: float = 5.0
    uid_prefix: str = "UID:"
    granted_message: str = "GRANTED"
    denied_message: str = "DENIED"
    ready_message: str = "READY"


@dataclass(frozen=True)
class DatabaseConfig:
    """Holds SQLite database schema configuration."""

    users_table: str = "Users"
    access_logs_table: str = "AccessLogs"
    connection_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class AuthConfig:
    """
    Holds authentication and access-control related settings.

    authorized_program_path launches a normal, already-authorized program
    (Notepad by default) after a GRANTED result. This does NOT interact
    with, bypass, or emulate the Windows login/lock screen in any way.
    """

    status_granted: str = "GRANTED"
    status_denied: str = "DENIED"
    unknown_user_label: str = "Unknown"
    authorized_program_path: str = r"C:\Windows\System32\notepad.exe"
    launch_program_on_success: bool = True


@dataclass(frozen=True)
class GUIConfig:
    """Holds GUI appearance and behavior settings for the Tkinter dark theme."""

    window_title: str = "RFID Authentication System"
    window_width: int = 950
    window_height: int = 640
    min_width: int = 800
    min_height: int = 560

    bg_color: str = "#1e1e2e"
    secondary_bg_color: str = "#282a3a"
    card_bg_color: str = "#31334a"
    fg_color: str = "#e0e0e0"
    muted_fg_color: str = "#9198a8"
    accent_color: str = "#3b82f6"
    success_color: str = "#22c55e"
    error_color: str = "#ef4444"
    warning_color: str = "#f59e0b"

    font_family: str = "Segoe UI"
    font_size_normal: int = 11
    font_size_heading: int = 18
    font_size_subheading: int = 13
    font_size_monospace: int = 14

    poll_interval_ms: int = 150


@dataclass(frozen=True)
class LoggingConfig:
    """Holds Python `logging` module configuration."""

    logger_name: str = "rfid_auth_system"
    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    log_level: str = "INFO"
    max_bytes: int = 1_048_576
    backup_count: int = 5


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration aggregating all sub-configurations."""

    paths: PathConfig = field(default_factory=PathConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    app_name: str = "RFID Authentication System"
    app_version: str = "1.0.0"


settings: AppConfig = AppConfig()


def get_env_override(key: str, default: str) -> str:
    """
    Retrieves a configuration value from an environment variable, falling
    back to a provided default if the variable is not set.

    Args:
        key: The environment variable name to look up.
        default: The default value to return if the variable is unset.

    Returns:
        The environment variable's value, or the default.
    """
    return os.environ.get(key, default)


if __name__ == "__main__":
    settings.paths.ensure_directories_exist()
    print(f"[config.py] {settings.app_name} v{settings.app_version}")
    print(f"[config.py] Database path: {settings.paths.database_file}")
    print(f"[config.py] Log file path: {settings.paths.log_file}")
