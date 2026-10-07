"""App-wide preferences: last-used file paths, tutorial-shown flag,
optionally a DPAPI-encrypted SMTP password. Stored under %APPDATA%
(see paths.py) -- fixes baseline Known Issue #1, where this same data
lived next to __file__ and was silently lost in the packaged exe."""
import json
import os
from typing import Any, Dict

from .paths import prefs_path


def load_prefs() -> Dict[str, Any]:
    try:
        with open(prefs_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_prefs(prefs: Dict[str, Any]) -> None:
    try:
        path = prefs_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass
