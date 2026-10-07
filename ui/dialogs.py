from typing import Dict, List, Optional

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                                QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                                QListWidget, QPlainTextEdit, QPushButton,
                                QTextEdit, QVBoxLayout)

from certgen import detect
from certgen.fields import ALL_FIELDS, FIELD_NAME, FIELD_TITLES
from certgen.preflight import PreflightReport
from certgen.xlsx_source import MAPPABLE_FIELDS
from ui import msgbox


class TemplateFieldsDialog(QDialog):
    """Which of Nome/CPF/Data/Turma does this template use? Nome is
    always required. Mirrors the baseline's TemplateFieldsDialog."""

    def __init__(self, template_pdf: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Campos deste modelo")
        self.template_pdf = template_pdf
        self.checks: Dict[str, QCheckBox] = {}
        self.status_labels: Dict[str, QLabel] = {}
        self.detected: Dict[str, fitz.Rect] = {}
        self.required: List[str] = [FIELD_NAME]

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Marque o que este PDF usa. Clique em \"Detectar automaticamente\"\n"
            "para localizar as áreas na 1ª página (o app tenta adivinhar)."))

        grid = QGridLayout()
        for row, field in enumerate(ALL_FIELDS):
            cb = QCheckBox(FIELD_TITLES[field])
            if field == FIELD_NAME:
                cb.setChecked(True)
                cb.setEnabled(False)
            self.checks[field] = cb
            grid.addWidget(cb, row, 0)
            status = QLabel("—")
            status.setProperty("role", "hint")
            self.status_labels[field] = status
            grid.addWidget(status, row, 1)
        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        detect_btn = QPushButton("Detectar automaticamente")
        detect_btn.clicked.connect(self._detect_now)
        btn_row.addWidget(detect_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _detect_now(self):
        try:
            doc = fitz.open(self.template_pdf)
        except Exception as e:
            msgbox.error(self, "PDF", f"Não foi possível abrir o PDF.\n\n{e}")
            return
        try:
            self.detected = detect.detect_field_rects_firstpage(doc)
            for f, label in self.status_labels.items():
                if f in self.detected:
                    label.setText("Encontrado")
                    label.setProperty("role", "ok")
                else:
                    label.setText("Não encontrado")
                    label.setProperty("role", "error")
                label.style().unpolish(label)
                label.style().polish(label)
        finally:
            doc.close()

    def _on_ok(self):
        self.required = [f for f, cb in self.checks.items() if cb.isChecked()]
        self.accept()


class ColumnMappingDialog(QDialog):
    """Lets the user tell the app which spreadsheet column is which,
    instead of silently assuming the rigid A=Nome,B=CPF,... layout.
    Pre-filled with the best automatic guess."""

    def __init__(self, headers: List[str], default_mapping: Dict[str, Optional[int]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirme as colunas da planilha")
        self.headers = headers
        self.combos: Dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Confira se cada campo está apontando para a coluna certa:"))

        form = QFormLayout()
        options = ["(nenhuma)"] + [f"{chr(65+i)}: {h}" if h else f"{chr(65+i)}: (sem título)"
                                    for i, h in enumerate(headers)]
        for field in MAPPABLE_FIELDS:
            combo = QComboBox()
            combo.addItems(options)
            idx = default_mapping.get(field)
            combo.setCurrentIndex((idx + 1) if idx is not None else 0)
            self.combos[field] = combo
            form.addRow(FIELD_TITLES.get(field, field.title()) + ":", combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self) -> Dict[str, Optional[int]]:
        result = {}
        for field, combo in self.combos.items():
            idx = combo.currentIndex()
            result[field] = (idx - 1) if idx > 0 else None
        return result


class PreflightDialog(QDialog):
    """Shows what run_preflight() found before committing to a full
    batch -- missing emails, malformed CPFs, duplicate names, names that
    will render too small to read."""

    def __init__(self, report: PreflightReport, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verificação antes de gerar")
        self.proceed = False

        layout = QVBoxLayout(self)
        summary = QLabel(f"{report.total_records} registro(s) na planilha.")
        layout.addWidget(summary)

        def add_section(title: str, items: List[str]):
            if not items:
                return
            box = QGroupBox(f"{title} ({len(items)})")
            inner = QVBoxLayout(box)
            listw = QListWidget()
            listw.addItems(items[:200])
            listw.setMaximumHeight(120)
            inner.addWidget(listw)
            layout.addWidget(box)

        add_section("Sem e-mail", report.missing_email)
        add_section("CPF inválido", report.invalid_cpf)
        add_section("Nomes duplicados", report.duplicate_names)
        add_section("Nomes que ficarão com letra muito pequena", report.names_too_small)

        if not report.has_warnings:
            layout.addWidget(QLabel("Nenhum problema encontrado. Tudo certo para gerar!"))

        buttons = QDialogButtonBox()
        proceed_btn = buttons.addButton("Gerar mesmo assim" if report.has_warnings else "Gerar",
                                         QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        proceed_btn.setObjectName("primaryButton")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        self.proceed = True
        self.accept()


class CrashDialog(QDialog):
    """Shown by the global excepthook. Non-technical users get a plain
    message; the traceback is there to copy into a support message,
    not to read."""

    def __init__(self, traceback_text: str, log_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ocorreu um erro inesperado")
        self.resize(560, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Algo deu errado. O programa pode continuar, mas essa ação pode não "
            "ter sido concluída.\n\n"
            f"Um registro foi salvo em:\n{log_path}\n\n"
            "Se for pedir ajuda, copie o texto abaixo e envie junto:"))

        text = QPlainTextEdit()
        text.setPlainText(traceback_text)
        text.setReadOnly(True)
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
