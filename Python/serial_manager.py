"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : serial_manager.py
 Description : Manages serial communication with the Arduino Uno: COM port
               auto-detection, connect/disconnect, background listening for
               UID messages, and sending GRANTED/DENIED responses.

============================================================================
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

import serial
from serial.tools import list_ports

from config import settings

logger = logging.getLogger(settings.logging.logger_name)


@dataclass
class SerialPortInfo:
    """Represents metadata about an available serial port."""

    device: str
    description: str
    likely_arduino: bool


class SerialConnectionError(Exception):
    """Raised when a serial connection cannot be established."""


class NoArduinoFoundError(SerialConnectionError):
    """Raised when auto-detection cannot find any candidate Arduino port."""


class SerialManager:
    """
    Manages the serial connection to the Arduino Uno running RFID_Login.ino.
    """

    def __init__(self) -> None:
        """Initializes the SerialManager in a disconnected state."""
        self._serial_connection: Optional[serial.Serial] = None
        self._port_name: Optional[str] = None
        self._is_connected: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._uid_queue: "queue.Queue[str]" = queue.Queue()
        self._connection_lock: threading.Lock = threading.Lock()

    @staticmethod
    def list_available_ports() -> List[SerialPortInfo]:
        """
        Lists all currently available serial ports on the system.

        Returns:
            A list of SerialPortInfo objects describing each detected port.
        """
        ports_info: List[SerialPortInfo] = []
        for port in list_ports.comports():
            description = port.description or ""
            likely_arduino = any(
                keyword.lower() in description.lower()
                for keyword in settings.serial.auto_detect_keywords
            )
            ports_info.append(
                SerialPortInfo(device=port.device, description=description, likely_arduino=likely_arduino)
            )
        return ports_info

    def auto_detect_port(self) -> str:
        """
        Attempts to automatically identify the Arduino's COM port.

        Returns:
            The device name of the best-guess Arduino port (e.g., "COM3").

        Raises:
            NoArduinoFoundError: If no candidate port could be identified.
        """
        available_ports = self.list_available_ports()
        candidates = [p for p in available_ports if p.likely_arduino]

        if not candidates:
            logger.warning("Auto-detect found no likely Arduino port.")
            raise NoArduinoFoundError(
                "No Arduino-like device found. Please connect the board or select a COM port manually."
            )

        chosen = candidates[0]
        logger.info("Auto-detected candidate Arduino port: %s (%s).", chosen.device, chosen.description)
        return chosen.device

    def connect(self, port_name: Optional[str] = None) -> str:
        """
        Opens a serial connection to the Arduino and starts the listener thread.

        Args:
            port_name: Optional explicit COM port. If None, auto-detects.

        Returns:
            The name of the port that was successfully connected to.

        Raises:
            NoArduinoFoundError: If auto-detection fails.
            SerialConnectionError: If opening the serial port fails.
        """
        with self._connection_lock:
            if self._is_connected:
                logger.info("Already connected to '%s'.", self._port_name)
                return self._port_name  # type: ignore[return-value]

            resolved_port = port_name or self.auto_detect_port()

            try:
                self._serial_connection = serial.Serial(
                    port=resolved_port,
                    baudrate=settings.serial.baud_rate,
                    timeout=settings.serial.timeout_seconds,
                    write_timeout=settings.serial.write_timeout_seconds,
                )
                time.sleep(2.0)  # allow Arduino auto-reset to complete

                self._port_name = resolved_port
                self._is_connected = True
                self._stop_event.clear()

                self._listener_thread = threading.Thread(
                    target=self._listen_loop, name="SerialListenerThread", daemon=True
                )
                self._listener_thread.start()

                logger.info("Connected to Arduino on port '%s'.", resolved_port)
                return resolved_port

            except serial.SerialException as exc:
                logger.exception("Failed to open serial port '%s'.", resolved_port)
                raise SerialConnectionError(
                    f"Could not open serial port '{resolved_port}': {exc}"
                ) from exc

    def disconnect(self) -> None:
        """Stops the listener thread and closes the serial connection cleanly."""
        with self._connection_lock:
            self._stop_event.set()

            if self._listener_thread is not None and self._listener_thread.is_alive():
                self._listener_thread.join(timeout=2.0)

            if self._serial_connection is not None:
                try:
                    self._serial_connection.close()
                except serial.SerialException:
                    logger.exception("Error while closing serial connection.")
                finally:
                    self._serial_connection = None

            self._is_connected = False
            logger.info("Disconnected from Arduino (port was '%s').", self._port_name)
            self._port_name = None

    def is_connected(self) -> bool:
        """Returns True if the serial connection is currently open and active."""
        return self._is_connected and self._serial_connection is not None

    @property
    def port_name(self) -> Optional[str]:
        """Returns the currently connected port name, or None if disconnected."""
        return self._port_name

    def _listen_loop(self) -> None:
        """
        Runs on a background thread. Continuously reads lines from the
        serial port, extracts UID messages, and places them onto the
        thread-safe queue for consumption by the GUI/auth layer.
        """
        assert self._serial_connection is not None

        while not self._stop_event.is_set():
            try:
                if self._serial_connection.in_waiting > 0:
                    raw_line = self._serial_connection.readline()
                    line = raw_line.decode("utf-8", errors="ignore").strip()

                    if not line:
                        continue

                    if line == settings.serial.ready_message:
                        logger.info("Arduino reported READY.")
                        continue

                    if line.startswith(settings.serial.uid_prefix):
                        uid = line[len(settings.serial.uid_prefix):].strip().upper()
                        if uid:
                            logger.info("Received UID from Arduino: '%s'.", uid)
                            self._uid_queue.put(uid)
                    else:
                        logger.debug("Ignoring unrecognized serial line: '%s'.", line)
                else:
                    time.sleep(0.05)

            except serial.SerialException:
                logger.exception("Serial communication error. Marking connection as lost.")
                self._is_connected = False
                break
            except UnicodeDecodeError:
                logger.warning("Received undecodable bytes on serial port; ignoring.")
                continue

    def send_result(self, granted: bool) -> None:
        """
        Sends the authentication result back to the Arduino.

        Args:
            granted: True to send "GRANTED", False to send "DENIED".

        Raises:
            SerialConnectionError: If not connected or the write fails.
        """
        if not self.is_connected():
            raise SerialConnectionError("Cannot send result: not connected to Arduino.")

        message = settings.serial.granted_message if granted else settings.serial.denied_message

        try:
            payload = f"{message}\n".encode("utf-8")
            self._serial_connection.write(payload)  # type: ignore[union-attr]
            self._serial_connection.flush()  # type: ignore[union-attr]
            logger.info("Sent result to Arduino: '%s'.", message)
        except serial.SerialException as exc:
            logger.exception("Failed to send result '%s' to Arduino.", message)
            raise SerialConnectionError(f"Failed to send result: {exc}") from exc

    def get_next_uid(self, block: bool = False, timeout: Optional[float] = None) -> Optional[str]:
        """
        Retrieves the next UID from the internal queue, if available.

        Args:
            block: Whether to block until a UID is available.
            timeout: Max time to block, in seconds (only if block=True).

        Returns:
            The next UID string, or None if unavailable.
        """
        try:
            return self._uid_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def has_pending_uid(self) -> bool:
        """Returns True if there is at least one UID waiting in the queue."""
        return not self._uid_queue.empty()
