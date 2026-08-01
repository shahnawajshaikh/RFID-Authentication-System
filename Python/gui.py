"""
============================================================================
 Project     : RFID-Based Authentication System
 File        : gui.py
 Description : Tkinter-based dark-themed GUI for the RFID Authentication
               System. Displays connection status, scanned UID, matched
               user, and access decisions in real time. Provides admin
               controls for adding/deleting users, searching, viewing
               logs, and exporting logs to CSV.

============================================================================
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from auth import AuthenticationService, AuthResult
from config import settings
from database import DatabaseError, DatabaseManager, DuplicateUIDError, User, UserNotFoundError
from serial_manager import NoArduinoFoundError, SerialConnectionError, SerialManager
from utils import is_valid_name, is_valid_uid

logger = logging.getLogger(settings.logging.logger_name)


class RFIDAuthApp(tk.Tk):
    """
    Main application window for the RFID Authentication System.

    Wires together the DatabaseManager, SerialManager, and
    AuthenticationService, and presents a dark-themed Tkinter interface
    for monitoring authentication events and administering users/logs.
    """

    def __init__(self) -> None:
        """Initializes the main window, services, and all GUI widgets."""
        super().__init__()

        self._database = DatabaseManager()
        self._serial_manager = SerialManager()
        self._auth_service = AuthenticationService(self._database, self._serial_manager)

        self._configure_window()
        self._build_style()
        self._build_layout()
        self._refresh_users_table()

        self.protocol("WM_DELETE_WINDOW", self._on_exit)

        # Kick off background polling of the serial UID queue.
        self.after(settings.gui.poll_interval_ms, self._poll_serial_queue)

        # Attempt to auto-connect to the Arduino on startup.
        self.after(200, self._attempt_auto_connect)

    # -----------------------------------------------------------------
    # Window / Style Setup
    # -----------------------------------------------------------------
    def _configure_window(self) -> None:
        """Configures the main window title, size, and minimum dimensions."""
        self.title(settings.gui.window_title)
        self.geometry(f"{settings.gui.window_width}x{settings.gui.window_height}")
        self.minsize(settings.gui.min_width, settings.gui.min_height)
        self.configure(bg=settings.gui.bg_color)

    def _build_style(self) -> None:
        """Configures ttk styles to achieve a consistent dark theme."""
        style = ttk.Style(self)
        style.theme_use("clam")

        gui = settings.gui

        style.configure(
            "TFrame", background=gui.bg_color,
        )
        style.configure(
            "Card.TFrame", background=gui.card_bg_color,
        )
        style.configure(
            "TLabel", background=gui.bg_color, foreground=gui.fg_color,
            font=(gui.font_family, gui.font_size_normal),
        )
        style.configure(
            "Card.TLabel", background=gui.card_bg_color, foreground=gui.fg_color,
            font=(gui.font_family, gui.font_size_normal),
        )
        style.configure(
            "Heading.TLabel", background=gui.bg_color, foreground=gui.fg_color,
            font=(gui.font_family, gui.font_size_heading, "bold"),
        )
        style.configure(
            "Muted.TLabel", background=gui.bg_color, foreground=gui.muted_fg_color,
            font=(gui.font_family, gui.font_size_normal),
        )
        style.configure(
            "UID.TLabel", background=gui.card_bg_color, foreground=gui.accent_color,
            font=("Consolas", gui.font_size_monospace, "bold"),
        )
        style.configure(
            "Status.TLabel", background=gui.card_bg_color,
            font=(gui.font_family, gui.font_size_subheading, "bold"),
        )
        style.configure(
            "TButton", background=gui.accent_color, foreground="#ffffff",
            font=(gui.font_family, gui.font_size_normal, "bold"), padding=8,
        )
        style.map("TButton", background=[("active", "#2563eb")])

        style.configure(
            "Treeview", background=gui.secondary_bg_color, fieldbackground=gui.secondary_bg_color,
            foreground=gui.fg_color, rowheight=26,
            font=(gui.font_family, gui.font_size_normal),
        )
        style.configure(
            "Treeview.Heading", background=gui.card_bg_color, foreground=gui.fg_color,
            font=(gui.font_family, gui.font_size_normal, "bold"),
        )
        style.map("Treeview", background=[("selected", gui.accent_color)])

    def _build_layout(self) -> None:
        """Builds the overall layout: header, status card, and tabbed admin panel."""
        gui = settings.gui

        header = ttk.Frame(self, style="TFrame", padding=(20, 15))
        header.pack(fill=tk.X)

        ttk.Label(header, text=settings.gui.window_title, style="Heading.TLabel").pack(side=tk.LEFT)

        self._connection_var = tk.StringVar(value="Disconnected")
        self._connection_label = tk.Label(
            header, textvariable=self._connection_var, bg=gui.bg_color,
            fg=gui.error_color, font=(gui.font_family, gui.font_size_subheading, "bold"),
        )
        self._connection_label.pack(side=tk.RIGHT)

        ttk.Button(header, text="Connect", command=self._on_connect_clicked).pack(side=tk.RIGHT, padx=8)

        self._build_status_card()
        self._build_admin_tabs()

    def _build_status_card(self) -> None:
        """Builds the live scan-status card: waiting/UID/user/result display."""
        gui = settings.gui
        card = ttk.Frame(self, style="Card.TFrame", padding=20)
        card.pack(fill=tk.X, padx=20, pady=(0, 15))

        self._status_var = tk.StringVar(value="Waiting for RFID scan...")
        status_label = tk.Label(
            card, textvariable=self._status_var, bg=gui.card_bg_color, fg=gui.fg_color,
            font=(gui.font_family, gui.font_size_subheading, "bold"),
        )
        status_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._status_label = status_label

        ttk.Label(card, text="Scanned UID:", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        self._uid_var = tk.StringVar(value="--")
        ttk.Label(card, textvariable=self._uid_var, style="UID.TLabel").grid(row=1, column=1, sticky="w", padx=10)

        ttk.Label(card, text="User:", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self._user_var = tk.StringVar(value="--")
        ttk.Label(card, textvariable=self._user_var, style="Card.TLabel").grid(
            row=2, column=1, sticky="w", padx=10, pady=(6, 0)
        )

        ttk.Label(card, text="Result:", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._result_var = tk.StringVar(value="--")
        self._result_label = tk.Label(
            card, textvariable=self._result_var, bg=gui.card_bg_color, fg=gui.fg_color,
            font=(gui.font_family, gui.font_size_normal, "bold"),
        )
        self._result_label.grid(row=3, column=1, sticky="w", padx=10, pady=(6, 0))

    def _build_admin_tabs(self) -> None:
        """Builds the tabbed notebook containing Users and Logs administration."""
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        users_tab = ttk.Frame(notebook, style="TFrame", padding=15)
        logs_tab = ttk.Frame(notebook, style="TFrame", padding=15)

        notebook.add(users_tab, text="Users")
        notebook.add(logs_tab, text="Access Logs")

        self._build_users_tab(users_tab)
        self._build_logs_tab(logs_tab)

    def _build_users_tab(self, parent: ttk.Frame) -> None:
        """Builds the Users administration tab: search bar, table, action buttons."""
        toolbar = ttk.Frame(parent, style="TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(toolbar, text="Search:", style="TLabel").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=8)
        search_entry.bind("<Return>", lambda _event: self._on_search_users())

        ttk.Button(toolbar, text="Search", command=self._on_search_users).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_users_table).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Add User", command=self._on_add_user).pack(side=tk.RIGHT, padx=4)
        ttk.Button(toolbar, text="Delete Selected", command=self._on_delete_user).pack(side=tk.RIGHT, padx=4)

        columns = ("id", "name", "uid", "created_at")
        self._users_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for col, label, width in (
            ("id", "ID", 50), ("name", "Name", 220), ("uid", "RFID UID", 180), ("created_at", "Created At", 180)
        ):
            self._users_tree.heading(col, text=label)
            self._users_tree.column(col, width=width, anchor="w")
        self._users_tree.pack(fill=tk.BOTH, expand=True)

    def _build_logs_tab(self, parent: ttk.Frame) -> None:
        """Builds the Access Logs tab: table of attempts and CSV export button."""
        toolbar = ttk.Frame(parent, style="TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="Refresh Logs", command=self._refresh_logs_table).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Export to CSV", command=self._on_export_logs).pack(side=tk.RIGHT, padx=4)

        columns = ("id", "user_name", "uid", "status", "date_time")
        self._logs_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for col, label, width in (
            ("id", "ID", 50), ("user_name", "User", 180), ("uid", "UID", 160),
            ("status", "Status", 90), ("date_time", "Date/Time", 180),
        ):
            self._logs_tree.heading(col, text=label)
            self._logs_tree.column(col, width=width, anchor="w")
        self._logs_tree.pack(fill=tk.BOTH, expand=True)

        self._refresh_logs_table()

    # -----------------------------------------------------------------
    # Connection Handling
    # -----------------------------------------------------------------
    def _attempt_auto_connect(self) -> None:
        """Attempts to auto-connect to the Arduino shortly after startup."""
        self._on_connect_clicked()

    def _on_connect_clicked(self) -> None:
        """Handles the Connect button: attempts auto-detect and connect."""
        if self._serial_manager.is_connected():
            messagebox.showinfo("Already Connected", f"Already connected on {self._serial_manager.port_name}.")
            return

        try:
            port = self._serial_manager.connect()
            self._set_connection_status(True, port)
        except NoArduinoFoundError:
            self._set_connection_status(False, None)
            messagebox.showwarning(
                "Arduino Not Found",
                "Could not auto-detect an Arduino. Please check the USB connection.",
            )
        except SerialConnectionError as exc:
            self._set_connection_status(False, None)
            messagebox.showerror("Connection Error", str(exc))

    def _set_connection_status(self, connected: bool, port: Optional[str]) -> None:
        """Updates the connection status label and color."""
        gui = settings.gui
        if connected:
            self._connection_var.set(f"Connected ({port})")
            self._connection_label.configure(fg=gui.success_color)
        else:
            self._connection_var.set("Disconnected")
            self._connection_label.configure(fg=gui.error_color)

    # -----------------------------------------------------------------
    # Serial Queue Polling / Authentication Flow
    # -----------------------------------------------------------------
    def _poll_serial_queue(self) -> None:
        """
        Periodically polls the SerialManager's UID queue on the main GUI
        thread and triggers authentication when a new UID arrives.
        """
        if self._serial_manager.is_connected():
            uid = self._serial_manager.get_next_uid(block=False)
            if uid is not None:
                self._handle_scanned_uid(uid)
        elif self._connection_var.get() != "Disconnected":
            # Connection was lost unexpectedly (e.g., cable unplugged)
            self._set_connection_status(False, None)

        self.after(settings.gui.poll_interval_ms, self._poll_serial_queue)

    def _handle_scanned_uid(self, uid: str) -> None:
        """
        Runs the authentication workflow for a scanned UID and updates the
        status card with the result.

        Args:
            uid: The raw UID string received from the Arduino.
        """
        self._uid_var.set(uid)
        self._status_var.set("Authenticating...")
        self.update_idletasks()

        result: AuthResult = self._auth_service.authenticate_uid(uid)
        self._display_auth_result(result)
        self._refresh_logs_table()

    def _display_auth_result(self, result: AuthResult) -> None:
        """
        Updates the status card widgets to reflect an AuthResult.

        Args:
            result: The AuthResult to display.
        """
        gui = settings.gui
        self._uid_var.set(result.uid)
        self._user_var.set(result.user.name if result.user else "Unknown")

        if result.granted:
            self._result_var.set("ACCESS GRANTED")
            self._result_label.configure(fg=gui.success_color)
            self._status_var.set("Access granted. Waiting for next scan...")
        else:
            self._result_var.set("ACCESS DENIED")
            self._result_label.configure(fg=gui.error_color)
            self._status_var.set("Access denied. Waiting for next scan...")

    # -----------------------------------------------------------------
    # Users Tab Handlers
    # -----------------------------------------------------------------
    def _refresh_users_table(self) -> None:
        """Reloads the Users table from the database into the treeview."""
        try:
            users = self._database.get_all_users()
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))
            return

        self._populate_users_tree(users)

    def _populate_users_tree(self, users: list[User]) -> None:
        """Clears and repopulates the users treeview with the given users."""
        for row_id in self._users_tree.get_children():
            self._users_tree.delete(row_id)

        for user in users:
            self._users_tree.insert(
                "", tk.END, iid=str(user.id),
                values=(user.id, user.name, user.rfid_uid, user.created_at),
            )

    def _on_search_users(self) -> None:
        """Handles the Search button: filters the users table by term."""
        term = self._search_var.get().strip()
        if not term:
            self._refresh_users_table()
            return

        try:
            users = self._database.search_users(term)
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))
            return

        self._populate_users_tree(users)

    def _on_add_user(self) -> None:
        """
        Handles the Add User button: prompts for a name and UID, then
        inserts the new user into the database.
        """
        name = simpledialog.askstring("Add User", "Enter user's full name:", parent=self)
        if name is None:
            return
        if not is_valid_name(name):
            messagebox.showerror("Invalid Name", "Please enter a valid name (letters, numbers, spaces only).")
            return

        uid = simpledialog.askstring(
            "Add User", "Enter RFID UID (hex, e.g. A1B2C3D4)\nor scan the card now and check the status card:",
            parent=self,
        )
        if uid is None:
            return
        if not is_valid_uid(uid):
            messagebox.showerror("Invalid UID", "Please enter a valid hexadecimal UID.")
            return

        try:
            self._database.add_user(name=name, rfid_uid=uid)
            messagebox.showinfo("Success", f"User '{name}' added successfully.")
            self._refresh_users_table()
        except DuplicateUIDError as exc:
            messagebox.showerror("Duplicate UID", str(exc))
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))

    def _on_delete_user(self) -> None:
        """Handles the Delete Selected button: removes the selected user."""
        selection = self._users_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a user to delete.")
            return

        user_id = int(selection[0])
        values = self._users_tree.item(selection[0], "values")
        user_name = values[1] if values else "this user"

        confirmed = messagebox.askyesno(
            "Confirm Deletion", f"Are you sure you want to delete '{user_name}'?"
        )
        if not confirmed:
            return

        try:
            self._database.delete_user(user_id)
            messagebox.showinfo("Deleted", f"User '{user_name}' was deleted.")
            self._refresh_users_table()
        except UserNotFoundError as exc:
            messagebox.showerror("Not Found", str(exc))
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))

    # -----------------------------------------------------------------
    # Logs Tab Handlers
    # -----------------------------------------------------------------
    def _refresh_logs_table(self) -> None:
        """Reloads the AccessLogs table from the database into the treeview."""
        try:
            logs = self._database.get_all_logs(limit=500)
        except DatabaseError as exc:
            messagebox.showerror("Database Error", str(exc))
            return

        for row_id in self._logs_tree.get_children():
            self._logs_tree.delete(row_id)

        for entry in logs:
            self._logs_tree.insert(
                "", tk.END, iid=str(entry.id),
                values=(entry.id, entry.user_name, entry.uid, entry.status, entry.date_time),
            )

    def _on_export_logs(self) -> None:
        """Handles the Export to CSV button: writes all logs to a CSV file."""
        settings.paths.ensure_directories_exist()
        filename = f"access_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        export_path = settings.paths.exports_dir / filename

        try:
            saved_path: Path = self._database.export_logs_to_csv(export_path)
            messagebox.showinfo("Export Complete", f"Logs exported to:\n{saved_path}")
        except DatabaseError as exc:
            messagebox.showerror("Export Failed", str(exc))

    # -----------------------------------------------------------------
    # Application Exit
    # -----------------------------------------------------------------
    def _on_exit(self) -> None:
        """Handles the window close event: disconnects serial cleanly and exits."""
        confirmed = messagebox.askyesno("Exit", "Are you sure you want to exit?")
        if not confirmed:
            return

        try:
            self._serial_manager.disconnect()
        except Exception:
            logger.exception("Error while disconnecting serial manager on exit.")

        self.destroy()
