#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Input Lag Fixer - Windows latency tuning utility.

This module implements a conservative Windows-only latency tuning utility for
competitive-gaming benchmark sessions. The application can request a lower
system timer resolution, disable common Game Bar/Game DVR registry settings,
set a detected game process to a safer elevated priority class, and restore the
original settings from a structured backup file.

The project intentionally avoids unsafe or deceptive behavior. It does not
inject into games, patch game memory, bypass anti-cheat, install drivers,
modify boot configuration, disable antivirus software, or request realtime CPU
priority. Every supported operation is logged and designed to be reversible.

Author:
    Input Lag Fixer contributors

License:
    MIT License

Version:
    2.1.0

Changelog:
    2.1.0 - Added settings panel, CLI restore flow, and rollback reporting.
    2.0.0 - Reworked optimization engine and structured configuration model.
    1.3.0 - Added game metadata dataclass and process priority management.
    1.0.0 - Initial timer-resolution and Game DVR policy implementation.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import platform
import queue
import re
import sys
import threading
import time
import traceback
import unittest
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import psutil
except ImportError:  # pragma: no cover - exercised only without dependency installed.
    psutil = None  # type: ignore[assignment]

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover - tkinter is platform/package dependent.
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows validation path.
    winreg = None  # type: ignore[assignment]

APP_NAME = "Input Lag Fixer"
APP_SLUG = "InputLagFixer"
APP_VERSION = "2.1.0"
APP_AUTHOR = "Input Lag Fixer contributors"
APP_LICENSE = "MIT"
DEFAULT_TIMER_RESOLUTION_100NS = 10_000
MIN_TIMER_RESOLUTION_100NS = 5_000
MAX_TIMER_RESOLUTION_100NS = 156_250
CONFIG_FILE_NAME = "config.json"
BACKUP_FILE_NAME = "backup.json"
LOG_FILE_NAME = "input_lag_fixer.log"
WINDOWS_PRIORITY_CLASSES = {"normal", "above_normal", "high"}
GAME_KEY_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class InputLagFixerError(Exception):
    """Base exception for application-specific failures."""


class PlatformNotSupportedError(InputLagFixerError):
    """Raised when the current operating system is not supported."""


class AdminRequiredError(InputLagFixerError):
    """Raised when an operation requires elevated Windows privileges."""


class ConfigurationError(InputLagFixerError):
    """Raised when configuration loading or validation fails."""


class WindowsApiError(InputLagFixerError):
    """Raised when a Windows API call fails.

    Attributes:
        function_name: Name of the API function that failed.
        code: Windows error code or NTSTATUS value.
    """

    def __init__(self, function_name: str, code: int, message: str) -> None:
        """Initialize a Windows API error.

        Args:
            function_name: Name of the failed API function.
            code: Error or status code returned by the API.
            message: Human-readable error message.
        """
        super().__init__(f"{function_name} failed with code {code}: {message}")
        self.function_name = function_name
        self.code = code


class OptimizationError(InputLagFixerError):
    """Raised when an optimization step fails."""


class RollbackError(InputLagFixerError):
    """Raised when settings cannot be restored completely."""


@dataclass(frozen=True)
class GameDefinition:
    """Metadata describing a supported game executable.

    Attributes:
        key: Stable CLI/configuration identifier.
        display_name: Human-readable game name.
        process_name: Windows process executable name.
        window_title: Optional expected top-level window title fragment.
        steam_app_id: Optional Steam application identifier.
        executable_hint: Optional common installation-path hint.
        notes: User-facing operational notes.
    """

    key: str
    display_name: str
    process_name: str
    window_title: str = ""
    steam_app_id: Optional[int] = None
    executable_hint: str = ""
    notes: str = ""


@dataclass
class RegistryBackupEntry:
    """Serializable backup entry for one registry value."""

    hive: str
    path: str
    name: str
    existed: bool
    value: Any
    value_type: Optional[int]
    timestamp: str


@dataclass
class OptimizationResult:
    """Result object returned by an optimization or restore operation."""

    success: bool
    message: str
    steps_completed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class AppConfig:
    """Application configuration model.

    Attributes:
        timer_resolution_100ns: Desired timer interval in 100 ns units.
        disable_game_dvr: Whether Game Bar/Game DVR policy tweaks are enabled.
        set_process_priority: Whether game-process priority should be changed.
        priority_class: Target priority class: normal, above_normal, or high.
        selected_game: Game key used by GUI and CLI defaults.
        log_level: Python logging level name.
        custom_games: Additional user-defined game metadata dictionaries.
    """

    timer_resolution_100ns: int = DEFAULT_TIMER_RESOLUTION_100NS
    disable_game_dvr: bool = True
    set_process_priority: bool = True
    priority_class: str = "above_normal"
    selected_game: str = "cs2"
    log_level: str = "INFO"
    custom_games: List[Dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ConfigurationError: If any configuration value is invalid.
        """
        if not isinstance(self.timer_resolution_100ns, int):
            raise ConfigurationError("timer_resolution_100ns must be an integer")
        if not MIN_TIMER_RESOLUTION_100NS <= self.timer_resolution_100ns <= MAX_TIMER_RESOLUTION_100NS:
            raise ConfigurationError(
                f"timer_resolution_100ns must be between {MIN_TIMER_RESOLUTION_100NS} and {MAX_TIMER_RESOLUTION_100NS}"
            )
        if self.priority_class not in WINDOWS_PRIORITY_CLASSES:
            raise ConfigurationError(f"priority_class must be one of {sorted(WINDOWS_PRIORITY_CLASSES)}")
        if not GAME_KEY_PATTERN.match(self.selected_game):
            raise ConfigurationError("selected_game must contain only lowercase letters, numbers, underscores, or hyphens")
        if self.log_level.upper() not in logging._nameToLevel:
            raise ConfigurationError("log_level must be a valid Python logging level")
        for game in self.custom_games:
            validate_custom_game_dict(game)


@dataclass
class ProgressEvent:
    """Event sent from the optimization worker to GUI or CLI consumers."""

    percent: int
    step: str
    message: str


class ToolTip:
    """Small Tkinter tooltip helper for buttons and input controls."""

    def __init__(self, widget: Any, text: str, delay_ms: int = 500) -> None:
        """Create a tooltip for a widget.

        Args:
            widget: Tkinter widget that owns the tooltip.
            text: Text displayed in the tooltip window.
            delay_ms: Hover delay before display.
        """
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip_window: Optional[Any] = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: Optional[Any] = None) -> None:
        """Schedule tooltip display after the configured delay."""
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        """Cancel pending tooltip display."""
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        """Display the tooltip window near the widget."""
        if self._tip_window is not None or tk is None:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip_window = tk.Toplevel(self.widget)
        self._tip_window.wm_overrideredirect(True)
        self._tip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._tip_window,
            text=self.text,
            justify="left",
            background="#1f2937",
            foreground="#f8fafc",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=1)

    def _hide(self, _event: Optional[Any] = None) -> None:
        """Hide and destroy the tooltip window."""
        self._cancel()
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None


def validate_custom_game_dict(game: Mapping[str, Any]) -> None:
    """Validate a custom game definition dictionary.

    Args:
        game: Mapping loaded from configuration.

    Raises:
        ConfigurationError: If required fields are missing or malformed.
    """
    required = {"key", "display_name", "process_name"}
    missing = required.difference(game.keys())
    if missing:
        raise ConfigurationError(f"custom game is missing required fields: {sorted(missing)}")
    key = str(game["key"])
    process_name = str(game["process_name"])
    if not GAME_KEY_PATTERN.match(key):
        raise ConfigurationError(f"custom game key is invalid: {key}")
    if not process_name.lower().endswith(".exe"):
        raise ConfigurationError(f"custom game process must end with .exe: {process_name}")


def get_app_data_dir() -> Path:
    """Return the application data directory.

    Returns:
        Path to the per-user application data directory.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    path = Path(base) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    """Return the log directory, creating it if necessary.

    Returns:
        Path to the log directory.
    """
    path = get_app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(level_name: str = "INFO") -> logging.Logger:
    """Configure application logging for file and console output.

    Args:
        level_name: Python logging level name.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(APP_SLUG)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(threadName)s | %(message)s")
    file_handler = RotatingFileHandler(get_log_dir() / LOG_FILE_NAME, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging._nameToLevel.get(level_name.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.debug("Logging initialized at level %s", level_name)
    return logger


def get_default_games() -> Dict[str, GameDefinition]:
    """Return built-in game definitions.

    Returns:
        Dictionary keyed by stable game identifier.
    """
    games = [
        GameDefinition("cs2", "Counter-Strike 2", "cs2.exe", "Counter-Strike 2", 730, "steamapps/common/Counter-Strike Global Offensive/game/bin/win64/cs2.exe"),
        GameDefinition("valorant", "Valorant", "VALORANT-Win64-Shipping.exe", "VALORANT", None, "Riot Games/VALORANT/live/ShooterGame/Binaries/Win64"),
        GameDefinition("fortnite", "Fortnite", "FortniteClient-Win64-Shipping.exe", "Fortnite", None, "Fortnite/FortniteGame/Binaries/Win64"),
        GameDefinition("apex", "Apex Legends", "r5apex.exe", "Apex Legends", 1172470, "steamapps/common/Apex Legends/r5apex.exe"),
        GameDefinition("overwatch2", "Overwatch 2", "Overwatch.exe", "Overwatch", 2357570, "Overwatch/_retail_/Overwatch.exe"),
    ]
    return {game.key: game for game in games}


def merge_custom_games(config: AppConfig, base_games: Dict[str, GameDefinition]) -> Dict[str, GameDefinition]:
    """Merge custom games from configuration into built-in definitions.

    Args:
        config: Loaded application configuration.
        base_games: Built-in game definitions.

    Returns:
        New dictionary containing built-in and custom games.
    """
    merged = dict(base_games)
    for raw in config.custom_games:
        validate_custom_game_dict(raw)
        game = GameDefinition(
            key=str(raw["key"]),
            display_name=str(raw["display_name"]),
            process_name=str(raw["process_name"]),
            window_title=str(raw.get("window_title", "")),
            steam_app_id=int(raw["steam_app_id"]) if raw.get("steam_app_id") is not None else None,
            executable_hint=str(raw.get("executable_hint", "")),
            notes=str(raw.get("notes", "")),
        )
        merged[game.key] = game
    return merged


class ConfigManager:
    """Load, validate, and save application configuration."""

    def __init__(self, path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        """Create a configuration manager.

        Args:
            path: Optional explicit configuration path.
            logger: Optional logger for diagnostics.
        """
        self.path = path or (get_app_data_dir() / CONFIG_FILE_NAME)
        self.logger = logger or logging.getLogger(APP_SLUG)

    def load(self) -> AppConfig:
        """Load configuration from disk or create defaults.

        Returns:
            Validated application configuration.

        Raises:
            ConfigurationError: If JSON parsing or validation fails.
        """
        if not self.path.exists():
            config = AppConfig()
            self.save(config)
            return config
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            config = AppConfig(**data)
            config.validate()
            self.logger.debug("Configuration loaded from %s", self.path)
            return config
        except TypeError as exc:
            raise ConfigurationError(f"Configuration contains unknown fields: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Configuration is not valid JSON: {exc}") from exc

    def save(self, config: AppConfig) -> None:
        """Validate and save configuration to disk.

        Args:
            config: Configuration to persist.

        Raises:
            ConfigurationError: If validation fails.
        """
        config.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True), encoding="utf-8")
        self.logger.debug("Configuration saved to %s", self.path)


class BackupManager:
    """Manage structured backup files used for rollback."""

    def __init__(self, path: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
        """Create a backup manager.

        Args:
            path: Optional explicit backup path.
            logger: Optional logger for diagnostics.
        """
        self.path = path or (get_app_data_dir() / BACKUP_FILE_NAME)
        self.logger = logger or logging.getLogger(APP_SLUG)

    def load_entries(self) -> List[RegistryBackupEntry]:
        """Load registry backup entries from disk.

        Returns:
            List of backup entries. Empty if no backup exists.
        """
        if not self.path.exists():
            self.logger.info("No backup file found at %s", self.path)
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        entries = [RegistryBackupEntry(**entry) for entry in raw.get("registry", [])]
        self.logger.debug("Loaded %d backup entries", len(entries))
        return entries

    def save_entries(self, entries: Sequence[RegistryBackupEntry]) -> None:
        """Persist registry backup entries.

        Args:
            entries: Entries to write to disk.
        """
        payload = {"version": APP_VERSION, "created_at": utc_now(), "registry": [asdict(entry) for entry in entries]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.logger.debug("Saved %d backup entries to %s", len(entries), self.path)


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format.

    Returns:
        ISO formatted UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def is_windows() -> bool:
    """Return whether the current OS is Windows.

    Returns:
        True if running on Windows; otherwise False.
    """
    return os.name == "nt"


def verify_windows_version() -> None:
    """Verify that the operating system is supported.

    Raises:
        PlatformNotSupportedError: If not running on supported Windows.
    """
    if not is_windows():
        raise PlatformNotSupportedError("Input Lag Fixer supports Windows 10/11 only")
    release = platform.release()
    if release not in {"10", "11"}:
        raise PlatformNotSupportedError(f"Unsupported Windows release: {release}")


def is_admin() -> bool:
    """Return whether the current process has administrator rights.

    Returns:
        True when elevated on Windows; False otherwise.
    """
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def require_admin() -> None:
    """Raise if the process is not elevated.

    Raises:
        AdminRequiredError: If the process lacks administrator rights.
    """
    if not is_admin():
        raise AdminRequiredError("Administrator rights are required for this operation")


def format_exception(exc: BaseException) -> str:
    """Format an exception for user-facing output.

    Args:
        exc: Exception instance.

    Returns:
        Single-line human-readable exception string.
    """
    return f"{exc.__class__.__name__}: {exc}"


class WindowsTimerResolution:
    """ctypes wrapper around ntdll timer-resolution APIs."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize timer-resolution API bindings.

        Args:
            logger: Logger used for diagnostics.
        """
        self.logger = logger
        self._requested_value: Optional[int] = None
        self._available = False
        if is_windows():
            self._ntdll = ctypes.WinDLL("ntdll")
            self._bind_functions()
        else:
            self._ntdll = None

    def _bind_functions(self) -> None:
        """Bind NtQueryTimerResolution and NtSetTimerResolution functions."""
        assert self._ntdll is not None
        self._query = self._ntdll.NtQueryTimerResolution
        self._query.argtypes = [ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG)]
        self._query.restype = wintypes.LONG
        self._set = self._ntdll.NtSetTimerResolution
        self._set.argtypes = [wintypes.ULONG, wintypes.BOOLEAN, ctypes.POINTER(wintypes.ULONG)]
        self._set.restype = wintypes.LONG
        self._available = True

    def query(self) -> Tuple[int, int, int]:
        """Query minimum, maximum, and current timer resolution.

        Returns:
            Tuple of minimum, maximum, and current resolution in 100 ns units.

        Raises:
            WindowsApiError: If the API call fails.
        """
        if not self._available:
            raise WindowsApiError("NtQueryTimerResolution", -1, "API unavailable on this platform")
        minimum = wintypes.ULONG()
        maximum = wintypes.ULONG()
        current = wintypes.ULONG()
        status = int(self._query(ctypes.byref(minimum), ctypes.byref(maximum), ctypes.byref(current)))
        if status != 0:
            raise WindowsApiError("NtQueryTimerResolution", status, "NTSTATUS indicates failure")
        self.logger.debug("Timer resolution query min=%s max=%s current=%s", minimum.value, maximum.value, current.value)
        return int(minimum.value), int(maximum.value), int(current.value)

    def request(self, target_100ns: int) -> int:
        """Request a timer resolution for the current session.

        Args:
            target_100ns: Desired timer interval in 100 ns units.

        Returns:
            Current resolution granted by Windows.

        Raises:
            WindowsApiError: If the API call fails.
        """
        if not self._available:
            raise WindowsApiError("NtSetTimerResolution", -1, "API unavailable on this platform")
        current = wintypes.ULONG()
        status = int(self._set(wintypes.ULONG(target_100ns), wintypes.BOOLEAN(True), ctypes.byref(current)))
        if status != 0:
            raise WindowsApiError("NtSetTimerResolution", status, "failed to request timer resolution")
        self._requested_value = target_100ns
        self.logger.info("Requested timer resolution %s; current=%s", target_100ns, current.value)
        return int(current.value)

    def release(self) -> Optional[int]:
        """Release a previous timer-resolution request.

        Returns:
            Current timer resolution after release, or None if nothing was requested.

        Raises:
            WindowsApiError: If the API call fails.
        """
        if self._requested_value is None:
            return None
        current = wintypes.ULONG()
        status = int(self._set(wintypes.ULONG(self._requested_value), wintypes.BOOLEAN(False), ctypes.byref(current)))
        if status != 0:
            raise WindowsApiError("NtSetTimerResolution", status, "failed to release timer resolution")
        self.logger.info("Released timer resolution request; current=%s", current.value)
        self._requested_value = None
        return int(current.value)


class WindowsMessageQueue:
    """Bounded wrapper around PeekMessageW for current-thread diagnostics."""

    PM_REMOVE = 0x0001

    class MSG(ctypes.Structure):
        """ctypes representation of the Win32 MSG structure."""

        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize message-queue wrapper.

        Args:
            logger: Logger used for diagnostics.
        """
        self.logger = logger
        self._available = False
        if is_windows():
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._peek = self._user32.PeekMessageW
            self._peek.argtypes = [ctypes.POINTER(self.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
            self._peek.restype = wintypes.BOOL
            self._available = True

    def drain_current_thread(self, limit: int = 100) -> int:
        """Drain pending messages from the current thread only.

        Args:
            limit: Maximum number of messages to remove.

        Returns:
            Number of messages removed.
        """
        if not self._available:
            return 0
        count = 0
        msg = self.MSG()
        while count < limit and self._peek(ctypes.byref(msg), None, 0, 0, self.PM_REMOVE):
            count += 1
        self.logger.debug("Drained %d current-thread messages", count)
        return count


class RegistryManager:
    """Read, write, backup, and restore Windows registry values."""

    HIVE_MAP: Dict[str, Any] = {}

    def __init__(self, backup_manager: BackupManager, logger: logging.Logger) -> None:
        """Create a registry manager.

        Args:
            backup_manager: Backup persistence helper.
            logger: Logger used for diagnostics.
        """
        self.backup_manager = backup_manager
        self.logger = logger
        if winreg is not None:
            self.HIVE_MAP = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}

    def read_value(self, hive: str, path: str, name: str) -> Tuple[bool, Any, Optional[int]]:
        """Read one registry value.

        Args:
            hive: Registry hive short name.
            path: Registry key path.
            name: Value name.

        Returns:
            Tuple of existed flag, value, and registry value type.
        """
        if winreg is None:
            return False, None, None
        try:
            with winreg.OpenKey(self.HIVE_MAP[hive], path, 0, winreg.KEY_READ) as key:
                value, value_type = winreg.QueryValueEx(key, name)
                return True, value, int(value_type)
        except FileNotFoundError:
            return False, None, None
        except OSError:
            return False, None, None

    def write_dword(self, hive: str, path: str, name: str, value: int) -> None:
        """Write a DWORD registry value.

        Args:
            hive: Registry hive short name.
            path: Registry key path.
            name: Value name.
            value: DWORD integer to write.
        """
        if winreg is None:
            raise PlatformNotSupportedError("winreg is available only on Windows")
        access = winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        with winreg.CreateKeyEx(self.HIVE_MAP[hive], path, 0, access) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))
        self.logger.info("Wrote registry %s\\%s %s=%s", hive, path, name, value)

    def delete_value(self, hive: str, path: str, name: str) -> None:
        """Delete a registry value if it exists.

        Args:
            hive: Registry hive short name.
            path: Registry key path.
            name: Value name.
        """
        if winreg is None:
            raise PlatformNotSupportedError("winreg is available only on Windows")
        try:
            with winreg.OpenKey(self.HIVE_MAP[hive], path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            self.logger.info("Deleted registry %s\\%s %s", hive, path, name)
        except FileNotFoundError:
            self.logger.debug("Registry value already absent: %s\\%s %s", hive, path, name)

    def backup_and_write_dword(self, hive: str, path: str, name: str, value: int) -> RegistryBackupEntry:
        """Backup and write a DWORD registry value.

        Args:
            hive: Registry hive short name.
            path: Registry key path.
            name: Value name.
            value: DWORD integer to write.

        Returns:
            Backup entry representing the original state.
        """
        existed, old_value, old_type = self.read_value(hive, path, name)
        entry = RegistryBackupEntry(hive, path, name, existed, old_value, old_type, utc_now())
        self.write_dword(hive, path, name, value)
        return entry

    def restore_entry(self, entry: RegistryBackupEntry) -> None:
        """Restore one backed-up registry entry.

        Args:
            entry: Backup entry to restore.
        """
        if winreg is None:
            raise PlatformNotSupportedError("winreg is available only on Windows")
        if not entry.existed:
            self.delete_value(entry.hive, entry.path, entry.name)
            return
        value_type = entry.value_type if entry.value_type is not None else winreg.REG_DWORD
        access = winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        with winreg.CreateKeyEx(self.HIVE_MAP[entry.hive], entry.path, 0, access) as key:
            winreg.SetValueEx(key, entry.name, 0, value_type, entry.value)
        self.logger.info("Restored registry %s\\%s %s", entry.hive, entry.path, entry.name)


class ProcessManager:
    """Find game processes and manage safe priority classes."""

    PRIORITY_MAP: Dict[str, Any] = {}

    def __init__(self, logger: logging.Logger) -> None:
        """Create a process manager.

        Args:
            logger: Logger used for diagnostics.
        """
        self.logger = logger
        if psutil is not None and is_windows():
            self.PRIORITY_MAP = {
                "normal": psutil.NORMAL_PRIORITY_CLASS,
                "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                "high": psutil.HIGH_PRIORITY_CLASS,
            }

    def find_by_process_name(self, process_name: str) -> List[Any]:
        """Find running processes by executable name.

        Args:
            process_name: Executable name to match case-insensitively.

        Returns:
            List of psutil Process objects.
        """
        if psutil is None:
            raise OptimizationError("psutil is required for process management")
        matches: List[Any] = []
        expected = process_name.lower()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name == expected:
                    matches.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.logger.debug("Found %d processes matching %s", len(matches), process_name)
        return matches

    def set_priority(self, proc: Any, priority_class: str) -> None:
        """Set a process to a safe priority class.

        Args:
            proc: psutil Process object.
            priority_class: normal, above_normal, or high.

        Raises:
            OptimizationError: If priority class is unsupported.
        """
        if priority_class not in self.PRIORITY_MAP:
            raise OptimizationError(f"Unsupported priority class: {priority_class}")
        proc.nice(self.PRIORITY_MAP[priority_class])
        self.logger.info("Set PID %s priority to %s", proc.pid, priority_class)


class OptimizationEngine:
    """Coordinates system checks, optimization steps, verification, and restore."""

    GAME_DVR_VALUES: Tuple[Tuple[str, str, str, int], ...] = (
        ("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", 0),
        ("HKCU", r"System\GameConfigStore", "GameDVR_FSEBehaviorMode", 2),
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0),
        ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0),
    )

    def __init__(self, config: AppConfig, games: Dict[str, GameDefinition], logger: logging.Logger) -> None:
        """Create an optimization engine.

        Args:
            config: Application configuration.
            games: Available game definitions.
            logger: Logger used for diagnostics.
        """
        self.config = config
        self.games = games
        self.logger = logger
        self.backup_manager = BackupManager(logger=logger)
        self.registry = RegistryManager(self.backup_manager, logger)
        self.processes = ProcessManager(logger)
        self.timer = WindowsTimerResolution(logger)
        self.messages = WindowsMessageQueue(logger)
        self._last_registry_entries: List[RegistryBackupEntry] = []

    def preflight(self) -> List[str]:
        """Run pre-optimization system checks.

        Returns:
            List of warning messages.

        Raises:
            InputLagFixerError: If a required preflight check fails.
        """
        warnings: List[str] = []
        verify_windows_version()
        if not is_admin():
            warnings.append("Not running as administrator; HKLM and priority operations may fail")
        if psutil is None:
            raise OptimizationError("psutil is not installed")
        if winreg is None:
            raise OptimizationError("winreg is unavailable; registry operations cannot run")
        try:
            minimum, maximum, current = self.timer.query()
            self.logger.info("Timer resolution available min=%s max=%s current=%s", minimum, maximum, current)
        except InputLagFixerError as exc:
            warnings.append(str(exc))
        return warnings

    def optimize(self, game_key: str, progress: Optional[Callable[[ProgressEvent], None]] = None) -> OptimizationResult:
        """Apply configured optimizations for a game.

        Args:
            game_key: Game definition key.
            progress: Optional callback for progress updates.

        Returns:
            Optimization result with completed steps and warnings.
        """
        result = OptimizationResult(True, "Optimization completed")
        completed: List[str] = []
        try:
            self._emit(progress, 5, "preflight", "Running system checks")
            result.warnings.extend(self.preflight())
            if game_key not in self.games:
                raise OptimizationError(f"Unknown game key: {game_key}")
            game = self.games[game_key]
            self._emit(progress, 20, "backup", "Preparing registry backup")
            registry_entries: List[RegistryBackupEntry] = []
            if self.config.disable_game_dvr:
                self._emit(progress, 35, "game_dvr", "Disabling Game Bar and Game DVR policies")
                for hive, path, name, value in self.GAME_DVR_VALUES:
                    registry_entries.append(self.registry.backup_and_write_dword(hive, path, name, value))
                self.backup_manager.save_entries(registry_entries)
                self._last_registry_entries = registry_entries
                completed.append("game_dvr")
            self._emit(progress, 55, "timer", "Requesting timer resolution")
            try:
                self.timer.request(self.config.timer_resolution_100ns)
                completed.append("timer")
            except InputLagFixerError as exc:
                result.warnings.append(str(exc))
            self._emit(progress, 70, "priority", f"Locating {game.display_name} process")
            if self.config.set_process_priority:
                matches = self.processes.find_by_process_name(game.process_name)
                if matches:
                    for proc in matches:
                        self.processes.set_priority(proc, self.config.priority_class)
                    completed.append("priority")
                else:
                    result.warnings.append(f"Game process not running: {game.process_name}")
            self._emit(progress, 85, "message_queue", "Refreshing utility message queue")
            self.messages.drain_current_thread(limit=50)
            completed.append("message_queue")
            self._emit(progress, 95, "verify", "Verifying applied settings")
            verification_warnings = self.verify(game_key)
            result.warnings.extend(verification_warnings)
            self._emit(progress, 100, "done", "Optimization complete")
            result.steps_completed = completed
            return result
        except Exception as exc:
            self.logger.error("Optimization failed: %s", exc, exc_info=True)
            result.success = False
            result.message = "Optimization failed; attempting rollback"
            result.errors.append(format_exception(exc))
            try:
                self.rollback_partial(completed)
            except Exception as rollback_exc:
                result.errors.append(f"Rollback failed: {format_exception(rollback_exc)}")
            return result

    def verify(self, game_key: str) -> List[str]:
        """Verify a subset of applied settings.

        Args:
            game_key: Game definition key used for process checks.

        Returns:
            List of warning strings.
        """
        warnings: List[str] = []
        if self.config.disable_game_dvr:
            for hive, path, name, expected in self.GAME_DVR_VALUES:
                existed, value, _value_type = self.registry.read_value(hive, path, name)
                if not existed or int(value) != expected:
                    warnings.append(f"Registry verification failed for {hive}\\{path} {name}")
        if self.config.set_process_priority and game_key in self.games:
            game = self.games[game_key]
            matches = self.processes.find_by_process_name(game.process_name)
            if not matches:
                warnings.append(f"Could not verify priority because {game.process_name} is not running")
        return warnings

    def rollback_partial(self, completed_steps: Sequence[str]) -> None:
        """Rollback changes made during a failed optimization.

        Args:
            completed_steps: Names of steps that completed before failure.
        """
        if "timer" in completed_steps:
            self.timer.release()
        if "game_dvr" in completed_steps:
            for entry in reversed(self._last_registry_entries):
                self.registry.restore_entry(entry)

    def restore(self, progress: Optional[Callable[[ProgressEvent], None]] = None) -> OptimizationResult:
        """Restore backed-up settings and release runtime requests.

        Args:
            progress: Optional callback for progress updates.

        Returns:
            Restore result.
        """
        result = OptimizationResult(True, "Restore completed")
        try:
            self._emit(progress, 10, "timer", "Releasing timer request")
            try:
                self.timer.release()
            except InputLagFixerError as exc:
                result.warnings.append(str(exc))
            self._emit(progress, 40, "backup", "Loading backup")
            entries = self.backup_manager.load_entries()
            self._emit(progress, 60, "registry", "Restoring registry values")
            for entry in reversed(entries):
                try:
                    self.registry.restore_entry(entry)
                except Exception as exc:
                    result.errors.append(format_exception(exc))
            self._emit(progress, 100, "done", "Restore complete")
            if result.errors:
                result.success = False
                result.message = "Restore completed with errors"
            return result
        except Exception as exc:
            self.logger.error("Restore failed: %s", exc, exc_info=True)
            return OptimizationResult(False, "Restore failed", errors=[format_exception(exc)])

    def _emit(self, callback: Optional[Callable[[ProgressEvent], None]], percent: int, step: str, message: str) -> None:
        """Emit a progress event to callback and log output.

        Args:
            callback: Optional event consumer.
            percent: Integer progress percent.
            step: Stable step identifier.
            message: Human-readable message.
        """
        event = ProgressEvent(percent, step, message)
        self.logger.info("%3d%% | %s | %s", percent, step, message)
        if callback is not None:
            callback(event)


class InputLagFixerApp:
    """Tkinter GUI application for Input Lag Fixer."""

    COLORS = {
        "bg": "#0f172a",
        "panel": "#111827",
        "panel_alt": "#1f2937",
        "text": "#e5e7eb",
        "muted": "#94a3b8",
        "accent": "#38bdf8",
        "accent_dark": "#0284c7",
        "danger": "#ef4444",
        "success": "#22c55e",
    }

    def __init__(self, root: Any, config: AppConfig, games: Dict[str, GameDefinition], config_manager: ConfigManager, logger: logging.Logger) -> None:
        """Create the GUI application.

        Args:
            root: Tkinter root window.
            config: Loaded application configuration.
            games: Available game definitions.
            config_manager: Configuration persistence helper.
            logger: Logger used for diagnostics.
        """
        self.root = root
        self.config = config
        self.games = games
        self.config_manager = config_manager
        self.logger = logger
        self.engine = OptimizationEngine(config, games, logger)
        self.progress_queue: "queue.Queue[ProgressEvent]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.selected_game = tk.StringVar(value=config.selected_game)
        self.status_text = tk.StringVar(value="Ready")
        self.progress_value = tk.IntVar(value=0)
        self.animation_index = 0
        self._build_style()
        self._build_layout()
        self._schedule_progress_poll()

    def _build_style(self) -> None:
        """Configure Tkinter theme styles."""
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("840x560")
        self.root.minsize(760, 500)
        self.root.configure(bg=self.COLORS["bg"])
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.COLORS["bg"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"], relief="flat")
        style.configure("TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.COLORS["bg"], foreground=self.COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 20))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(14, 8))
        style.configure("Accent.TButton", background=self.COLORS["accent_dark"], foreground="#ffffff")
        style.configure("Horizontal.TProgressbar", troughcolor=self.COLORS["panel_alt"], background=self.COLORS["accent"])
        style.configure("TCombobox", fieldbackground=self.COLORS["panel_alt"], background=self.COLORS["panel_alt"], foreground=self.COLORS["text"])

    def _build_layout(self) -> None:
        """Build all primary GUI widgets."""
        container = ttk.Frame(self.root, padding=24)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="Transparent Windows latency tuning for competitive benchmark sessions.", style="Muted.TLabel").pack(anchor="w", pady=(4, 20))
        panel = ttk.Frame(container, style="Panel.TFrame", padding=20)
        panel.pack(fill="x")
        ttk.Label(panel, text="Select game", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 11)).grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(panel, textvariable=self.selected_game, values=list(self.games.keys()), state="readonly", width=35)
        combo.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ToolTip(combo, "Choose the game process that should receive priority tuning.")
        panel.columnconfigure(0, weight=1)
        optimize_button = ttk.Button(panel, text="Run Optimization", style="Accent.TButton", command=self.run_optimize)
        optimize_button.grid(row=1, column=1, padx=(16, 0))
        ToolTip(optimize_button, "Apply selected timer, Game DVR, and process-priority optimizations.")
        restore_button = ttk.Button(panel, text="Restore", command=self.run_restore)
        restore_button.grid(row=1, column=2, padx=(8, 0))
        ToolTip(restore_button, "Restore backed-up registry values and release timer requests.")
        settings_button = ttk.Button(panel, text="Settings", command=self.show_settings)
        settings_button.grid(row=1, column=3, padx=(8, 0))
        ToolTip(settings_button, "Open advanced options for timer resolution, priority, and logging.")
        about_button = ttk.Button(panel, text="About", command=self.show_about)
        about_button.grid(row=1, column=4, padx=(8, 0))
        ToolTip(about_button, "Show version, license, and safety information.")
        self.progress = ttk.Progressbar(container, orient="horizontal", mode="determinate", variable=self.progress_value, maximum=100)
        self.progress.pack(fill="x", pady=(24, 8))
        self.status = ttk.Label(container, textvariable=self.status_text, style="Muted.TLabel")
        self.status.pack(anchor="w")
        info = tk.Text(container, height=12, bg=self.COLORS["panel"], fg=self.COLORS["text"], insertbackground=self.COLORS["text"], relief="flat", padx=12, pady=12, font=("Consolas", 10))
        info.pack(fill="both", expand=True, pady=(20, 0))
        info.insert("end", self._safety_text())
        info.configure(state="disabled")

    def _safety_text(self) -> str:
        """Return safety text displayed in the GUI.

        Returns:
            Multiline safety text.
        """
        return (
            "Safety model:\n"
            "  • No anti-cheat bypassing, injection, driver installation, or Defender disabling.\n"
            "  • Timer requests are runtime-only and released on restore/shutdown.\n"
            "  • Game DVR registry values are backed up before changes.\n"
            "  • Process priority is limited to Normal, Above Normal, or High.\n"
            "  • Realtime priority is intentionally unsupported.\n"
        )

    def run_optimize(self) -> None:
        """Start optimization in a background thread."""
        if self.worker and self.worker.is_alive():
            return
        game_key = self.selected_game.get()
        self.config.selected_game = game_key
        self.config_manager.save(self.config)
        self._start_worker(lambda: self.engine.optimize(game_key, self.progress_queue.put))

    def run_restore(self) -> None:
        """Start restore in a background thread."""
        if self.worker and self.worker.is_alive():
            return
        self._start_worker(lambda: self.engine.restore(self.progress_queue.put))

    def _start_worker(self, target: Callable[[], OptimizationResult]) -> None:
        """Start a worker thread for a long-running operation.

        Args:
            target: Callable that returns an optimization result.
        """
        def wrapped() -> None:
            try:
                result = target()
                final_message = result.message
                if result.warnings:
                    final_message += f" ({len(result.warnings)} warnings)"
                if result.errors:
                    final_message += f" ({len(result.errors)} errors)"
                self.progress_queue.put(ProgressEvent(100 if result.success else 0, "result", final_message))
            except Exception as exc:
                self.logger.error("Worker crashed: %s", exc, exc_info=True)
                self.progress_queue.put(ProgressEvent(0, "error", format_exception(exc)))
        self.progress_value.set(0)
        self.status_text.set("Starting...")
        self.worker = threading.Thread(target=wrapped, name="optimizer", daemon=True)
        self.worker.start()
        self._animate_status()

    def _animate_status(self) -> None:
        """Animate the status bar while a worker is alive."""
        if self.worker and self.worker.is_alive():
            dots = "." * (self.animation_index % 4)
            current = self.status_text.get().rstrip(".")
            self.status_text.set(current + dots)
            self.animation_index += 1
            self.root.after(300, self._animate_status)

    def _schedule_progress_poll(self) -> None:
        """Schedule recurring progress queue polling."""
        self._poll_progress()
        self.root.after(100, self._schedule_progress_poll)

    def _poll_progress(self) -> None:
        """Consume queued progress events and update the GUI."""
        while True:
            try:
                event = self.progress_queue.get_nowait()
            except queue.Empty:
                break
            self.progress_value.set(event.percent)
            self.status_text.set(f"{event.step}: {event.message}")

    def show_about(self) -> None:
        """Display the About dialog."""
        if messagebox is None:
            return
        messagebox.showinfo(
            "About Input Lag Fixer",
            f"{APP_NAME} {APP_VERSION}\n\n"
            f"License: {APP_LICENSE}\n"
            f"Author: {APP_AUTHOR}\n\n"
            "This tool applies transparent, reversible Windows latency settings. "
            "It does not bypass anti-cheat systems or disable security software.",
        )

    def show_settings(self) -> None:
        """Open the settings panel."""
        if tk is None:
            return
        window = tk.Toplevel(self.root)
        window.title("Settings")
        window.geometry("520x420")
        window.configure(bg=self.COLORS["bg"])
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        timer_var = tk.IntVar(value=self.config.timer_resolution_100ns)
        dvr_var = tk.BooleanVar(value=self.config.disable_game_dvr)
        priority_var = tk.BooleanVar(value=self.config.set_process_priority)
        priority_class_var = tk.StringVar(value=self.config.priority_class)
        log_level_var = tk.StringVar(value=self.config.log_level)
        ttk.Label(frame, text="Timer resolution (100 ns units)").pack(anchor="w")
        timer_entry = ttk.Entry(frame, textvariable=timer_var)
        timer_entry.pack(fill="x", pady=(4, 12))
        ToolTip(timer_entry, "10000 means 1 ms. Lower values may not be granted by Windows.")
        dvr_check = ttk.Checkbutton(frame, text="Disable Game Bar / Game DVR policy values", variable=dvr_var)
        dvr_check.pack(anchor="w", pady=4)
        ToolTip(dvr_check, "Backs up and writes common Game DVR registry policy values.")
        priority_check = ttk.Checkbutton(frame, text="Set game process priority", variable=priority_var)
        priority_check.pack(anchor="w", pady=4)
        ToolTip(priority_check, "Sets detected game process to a safe elevated priority class.")
        ttk.Label(frame, text="Priority class").pack(anchor="w", pady=(12, 0))
        priority_combo = ttk.Combobox(frame, textvariable=priority_class_var, values=sorted(WINDOWS_PRIORITY_CLASSES), state="readonly")
        priority_combo.pack(fill="x", pady=(4, 12))
        ToolTip(priority_combo, "Realtime priority is intentionally unsupported.")
        ttk.Label(frame, text="Log level").pack(anchor="w")
        log_combo = ttk.Combobox(frame, textvariable=log_level_var, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly")
        log_combo.pack(fill="x", pady=(4, 12))
        ToolTip(log_combo, "Console logging threshold. File logging always captures DEBUG diagnostics.")

        def save_settings() -> None:
            """Persist settings entered in the dialog."""
            try:
                self.config.timer_resolution_100ns = int(timer_var.get())
                self.config.disable_game_dvr = bool(dvr_var.get())
                self.config.set_process_priority = bool(priority_var.get())
                self.config.priority_class = priority_class_var.get()
                self.config.log_level = log_level_var.get()
                self.config_manager.save(self.config)
                window.destroy()
            except Exception as exc:
                if messagebox is not None:
                    messagebox.showerror("Invalid settings", str(exc))

        save_button = ttk.Button(frame, text="Save", style="Accent.TButton", command=save_settings)
        save_button.pack(anchor="e", pady=(16, 0))
        ToolTip(save_button, "Validate and save settings to config.json.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(description="Input Lag Fixer - Windows latency tuning utility")
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode")
    parser.add_argument("--optimize", action="store_true", help="Apply configured optimizations")
    parser.add_argument("--restore", action="store_true", help="Restore backed-up settings")
    parser.add_argument("--game", default=None, help="Game key to optimize")
    parser.add_argument("--list-games", action="store_true", help="List supported games")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--run-tests", action="store_true", help="Run built-in unit tests")
    return parser


def print_games(games: Mapping[str, GameDefinition]) -> None:
    """Print available games to stdout.

    Args:
        games: Mapping of game key to definition.
    """
    for key, game in games.items():
        print(f"{key:12s} {game.display_name:24s} {game.process_name}")


def progress_to_console(event: ProgressEvent) -> None:
    """Print a progress event in CLI mode.

    Args:
        event: Progress event to display.
    """
    print(f"[{event.percent:3d}%] {event.step}: {event.message}")


def run_cli(args: argparse.Namespace, config: AppConfig, games: Dict[str, GameDefinition], logger: logging.Logger) -> int:
    """Run the command-line interface.

    Args:
        args: Parsed command-line arguments.
        config: Application configuration.
        games: Available game definitions.
        logger: Logger used for diagnostics.

    Returns:
        Process exit code.
    """
    if args.list_games:
        print_games(games)
        return 0
    engine = OptimizationEngine(config, games, logger)
    game_key = args.game or config.selected_game
    if args.optimize:
        result = engine.optimize(game_key, progress_to_console)
    elif args.restore:
        result = engine.restore(progress_to_console)
    else:
        print("No action specified. Use --optimize, --restore, or --list-games.")
        return 2
    print(result.message)
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    return 0 if result.success else 1


def run_gui(config: AppConfig, games: Dict[str, GameDefinition], config_manager: ConfigManager, logger: logging.Logger) -> int:
    """Run the Tkinter GUI.

    Args:
        config: Application configuration.
        games: Available game definitions.
        config_manager: Configuration persistence helper.
        logger: Logger used for diagnostics.

    Returns:
        Process exit code.
    """
    if tk is None:
        print("Tkinter is not available. Use --cli mode.", file=sys.stderr)
        return 1
    root = tk.Tk()
    InputLagFixerApp(root, config, games, config_manager, logger)
    root.mainloop()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Application entry point.

    Args:
        argv: Optional argument sequence. Defaults to sys.argv when None.

    Returns:
        Process exit code.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if args.run_tests:
        return run_tests()
    bootstrap_logger = setup_logging("INFO")
    try:
        config_manager = ConfigManager(logger=bootstrap_logger)
        config = config_manager.load()
        logger = setup_logging(config.log_level)
        games = merge_custom_games(config, get_default_games())
        if args.cli or args.optimize or args.restore or args.list_games:
            return run_cli(args, config, games, logger)
        return run_gui(config, games, config_manager, logger)
    except Exception as exc:
        bootstrap_logger.error("Fatal error: %s", exc, exc_info=True)
        print(format_exception(exc), file=sys.stderr)
        return 1


class ConfigValidationTests(unittest.TestCase):
    """Unit tests for configuration validation."""

    def test_default_config_is_valid(self) -> None:
        """Default configuration should pass validation."""
        AppConfig().validate()

    def test_invalid_timer_resolution_fails(self) -> None:
        """Timer values outside the safe range should fail."""
        config = AppConfig(timer_resolution_100ns=1)
        with self.assertRaises(ConfigurationError):
            config.validate()

    def test_invalid_priority_fails(self) -> None:
        """Unknown priority classes should fail."""
        config = AppConfig(priority_class="realtime")
        with self.assertRaises(ConfigurationError):
            config.validate()

    def test_invalid_custom_game_fails(self) -> None:
        """Custom game definitions require executable process names."""
        config = AppConfig(custom_games=[{"key": "demo", "display_name": "Demo", "process_name": "demo"}])
        with self.assertRaises(ConfigurationError):
            config.validate()


class GameDefinitionTests(unittest.TestCase):
    """Unit tests for game definition helpers."""

    def test_default_games_have_expected_keys(self) -> None:
        """Built-in game definitions should include common game keys."""
        games = get_default_games()
        self.assertIn("cs2", games)
        self.assertIn("valorant", games)

    def test_custom_games_merge(self) -> None:
        """Custom game definitions should merge into base definitions."""
        config = AppConfig(custom_games=[{"key": "demo", "display_name": "Demo Game", "process_name": "demo.exe"}])
        merged = merge_custom_games(config, get_default_games())
        self.assertIn("demo", merged)
        self.assertEqual(merged["demo"].process_name, "demo.exe")


class UtilityTests(unittest.TestCase):
    """Unit tests for platform-neutral utility functions."""

    def test_utc_now_contains_timezone(self) -> None:
        """UTC timestamps should include timezone information."""
        self.assertIn("+00:00", utc_now())

    def test_format_exception_contains_class_name(self) -> None:
        """Formatted exceptions should include the class name."""
        self.assertIn("ValueError", format_exception(ValueError("demo")))


def run_tests() -> int:
    """Run built-in unit tests.

    Returns:
        Process exit code representing test success or failure.
    """
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
