"""
Named presets: a saved bundle of everything needed to regenerate
certificates for a recurring event -- template, font, evento name, every
per-field offset/snap/baseline/font-size/bold setting, name-case mode,
and (optionally) email settings. The single biggest time-saver the plan
called out for anyone running the same handful of events repeatedly.

The SMTP password is never stored in plaintext; if the user opts in and
DPAPI is available (see credentials.py) it's stored encrypted, otherwise
it's simply not saved and the field is left for the user to retype.
"""
import json
import os
from typing import Any, Dict, List, Optional

from . import credentials
from .paths import presets_path


def load_all() -> Dict[str, Dict[str, Any]]:
    try:
        with open(presets_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    path = presets_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def list_names() -> List[str]:
    return sorted(load_all().keys())


def save_preset(name: str, data: Dict[str, Any], remember_password: bool = False,
                 smtp_password: str = "") -> None:
    all_presets = load_all()
    payload = dict(data)
    if remember_password and smtp_password and credentials.available():
        blob = credentials.protect(smtp_password)
        if blob:
            payload["smtp_password_enc"] = blob
    all_presets[name] = payload
    _save_all(all_presets)


def load_preset(name: str) -> Optional[Dict[str, Any]]:
    data = load_all().get(name)
    if data is None:
        return None
    data = dict(data)
    enc = data.pop("smtp_password_enc", None)
    if enc:
        plain = credentials.unprotect(enc)
        if plain is not None:
            data["smtp_password"] = plain
    return data


def delete_preset(name: str) -> None:
    all_presets = load_all()
    if name in all_presets:
        del all_presets[name]
        _save_all(all_presets)
