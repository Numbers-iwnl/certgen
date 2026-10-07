"""
Path resolution split into two clearly separate concerns:

- resource_path(): read-only assets bundled WITH the app (icons, banners).
  In a frozen PyInstaller onefile build these live under sys._MEIPASS,
  which is fine -- that directory exists for exactly the lifetime of the
  process, which is all a read-only resource needs.

- user_data_dir(): anything the app WRITES and expects to survive to the
  next launch (prefs, presets, logs). This must NEVER be derived from
  __file__ or sys._MEIPASS -- both point inside the onefile temp
  extraction directory, which is deleted when the process exits. That
  was baseline Known Issue #1: prefs silently never persisted in the
  packaged exe. Everything persistent goes to %APPDATA% instead.
"""
import os
import sys

APP_DIR_NAME = "GeradorCertificados"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _dev_root() -> str:
    # certgen/paths.py -> repo root is one level up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """Path to a read-only bundled resource (assets/*)."""
    base = getattr(sys, "_MEIPASS", _dev_root())
    return os.path.join(base, *parts)


def user_data_dir() -> str:
    """Writable, persistent-across-launches directory for this app."""
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(root, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir() -> str:
    path = os.path.join(user_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def prefs_path() -> str:
    return os.path.join(user_data_dir(), "prefs.json")


def presets_path() -> str:
    return os.path.join(user_data_dir(), "presets.json")


def asset(*parts: str) -> str:
    return resource_path("assets", *parts)
