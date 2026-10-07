"""
Fixes baseline Known Issue #7: with console=False, every log_warn/log_err
call and every unhandled traceback vanished into nothing in the packaged
exe. This module gives the app a real rotating log file plus a global
excepthook, so "it crashed" turns into an actual diagnosable report.
"""
import logging
import logging.handlers
import os
import sys
import traceback
from typing import Callable, Optional

from .paths import logs_dir

_LOG_FILE = "app.log"
logger = logging.getLogger("certgen")

_crash_callback: Optional[Callable[[str], None]] = None


def setup_logging(level: int = logging.INFO) -> str:
    """Configure the root 'certgen' logger. Returns the log file path."""
    logger.setLevel(level)
    logger.handlers.clear()

    log_path = os.path.join(logs_dir(), _LOG_FILE)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if not getattr(sys, "frozen", False):
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

    return log_path


def set_crash_callback(callback: Optional[Callable[[str], None]]) -> None:
    """Register a UI-level callback invoked with a formatted traceback
    string whenever an unhandled exception reaches install_excepthook's
    handler."""
    global _crash_callback
    _crash_callback = callback


def install_excepthook() -> None:
    def _handle(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Unhandled exception:\n%s", text)
        if _crash_callback is not None:
            try:
                _crash_callback(text)
            except Exception:
                logger.exception("crash callback itself failed")

    sys.excepthook = _handle
