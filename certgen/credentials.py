"""
Optional "remember this password" support via Windows DPAPI
(CryptProtectData/CryptUnprotectData). Encryption is tied to the
Windows user account, so the stored blob is useless on another machine
or to another user -- no separate secret to manage.

Uses ctypes directly against crypt32.dll instead of a pip dependency
(e.g. `keyring`) to avoid that package's backend auto-discovery being
flaky under a frozen PyInstaller build. Everything here is best-effort:
any failure (non-Windows, DPAPI unavailable) just means "don't offer to
remember the password," never a hard failure of the app.
"""
import base64
import ctypes
import ctypes.wintypes as wt
import sys
from typing import Optional


def available() -> bool:
    return sys.platform == "win32"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes) -> _DataBlob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def protect(plaintext: str) -> Optional[str]:
    """Encrypt a string, return a base64 blob safe to store in JSON.
    Returns None if DPAPI isn't available or encryption fails."""
    if not available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        data_in = _to_blob(plaintext.encode("utf-8"))
        data_out = _DataBlob()
        ok = crypt32.CryptProtectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        )
        if not ok:
            return None
        try:
            raw = ctypes.string_at(data_out.pbData, data_out.cbData)
            return base64.b64encode(raw).decode("ascii")
        finally:
            kernel32.LocalFree(data_out.pbData)
    except Exception:
        return None


def unprotect(blob_b64: str) -> Optional[str]:
    if not available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        raw = base64.b64decode(blob_b64)
        data_in = _to_blob(raw)
        data_out = _DataBlob()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        )
        if not ok:
            return None
        try:
            plain = ctypes.string_at(data_out.pbData, data_out.cbData)
            return plain.decode("utf-8")
        finally:
            kernel32.LocalFree(data_out.pbData)
    except Exception:
        return None
