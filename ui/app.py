"""
Application bootstrap: single-instance guard, global crash handling,
theme application, and closing the PyInstaller native splash screen.

The splash itself is defined once, in GeradorCertificados.spec's
Splash(...) object -- it's rendered by the PyInstaller bootloader
directly (via a bundled Tcl/Tk runtime), before Python even starts,
which is what gives instant feedback during the onefile exe's
temp-extraction. It is a SEPARATE mechanism from any Qt splash screen:
PyInstaller auto-injects a `pyi_splash` module into the frozen exe, and
that splash stays on screen until this code explicitly calls
`pyi_splash.close()`. Skipping that call is why an earlier build shipped
with the splash stuck on screen forever after the window loaded. In a
non-frozen dev run (`python main.py`) there is no bundled splash and no
`pyi_splash` module, so the import is best-effort.
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from certgen import logging_setup
from certgen.paths import asset
from certgen.version import APP_NAME, __version__

from ui.dialogs import CrashDialog
from ui.main_window import MainWindow
from ui.single_instance import SingleInstanceGuard
from ui.theme import STYLESHEET


def _close_native_splash():
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass  # not a frozen build with a splash, or already closed


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)

    try:
        app.setWindowIcon(QIcon(asset("logo.ico")))
    except Exception:
        pass

    log_path = logging_setup.setup_logging()

    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        _close_native_splash()
        return 0  # another instance is already running and has been focused

    window = MainWindow()

    def _on_focus_requested():
        window.showNormal()
        window.raise_()
        window.activateWindow()

    guard.focus_requested.connect(_on_focus_requested)

    def _on_crash(traceback_text: str):
        try:
            CrashDialog(traceback_text, log_path, window).exec()
        except Exception:
            pass

    logging_setup.set_crash_callback(_on_crash)
    logging_setup.install_excepthook()

    window.show()
    _close_native_splash()

    return app.exec()
