"""
A real, scrollable log panel -- fixes baseline Known Issue #12, where a
single status label showed only the most recent line and every earlier
failure was gone the instant the next one arrived.
"""
import datetime

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ui import msgbox


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text = QPlainTextEdit()
        self.text.setObjectName("logPanel")
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        layout.addWidget(self.text)

        btn_row = QHBoxLayout()
        export_btn = QPushButton("Exportar log...")
        export_btn.clicked.connect(self._export)
        clear_btn = QPushButton("Limpar")
        clear_btn.clicked.connect(self.text.clear)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._lines = []

    def append(self, line: str):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        full = f"[{stamp}] {line}"
        self._lines.append(full)
        self.text.appendPlainText(full)

    def clear(self):
        self._lines.clear()
        self.text.clear()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar log", "log.txt", "Texto (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._lines))
            msgbox.info(self, "Log exportado", f"Salvo em:\n{path}")
        except Exception as e:
            msgbox.error(self, "Erro", f"Não foi possível salvar o log.\n\n{e}")
