"""
Single-instance guard via QLocalServer/QLocalSocket.

Cold start on a onefile PyInstaller build takes a few seconds (the exe
re-extracts to a temp dir on every launch). An impatient double-click
during that window would otherwise spawn a second full instance instead
of doing nothing -- this makes a second launch just focus the first
window instead.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SERVER_NAME = "GeradorCertificados.SingleInstance"


class SingleInstanceGuard(QObject):
    focus_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: QLocalServer = None

    def try_acquire(self) -> bool:
        """Returns True if this is the primary instance. If another
        instance is already running, notifies it to focus its window and
        returns False -- caller should exit immediately."""
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(200):
            socket.write(b"focus")
            socket.flush()
            socket.waitForBytesWritten(200)
            socket.close()
            return False

        # Stale server (e.g. previous crash didn't clean up) -- remove and rebind.
        QLocalServer.removeServer(_SERVER_NAME)
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(_SERVER_NAME)
        return True

    def _on_new_connection(self):
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: self._on_ready_read(conn))

    def _on_ready_read(self, conn):
        conn.readAll()
        self.focus_requested.emit()
        conn.close()
