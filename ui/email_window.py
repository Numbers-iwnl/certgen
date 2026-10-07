"""
The email step, rebuilt for Phase 4: persistent-connection sending
(handled by certgen.mailer), a real results table instead of a rolling
log line, a cancel button for an in-progress batch, provider presets,
and a genuinely safe test-send that can never mark a real recipient as
served (see certgen.mailer.send_batch's test_mode).
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
                                QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                                QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                                QVBoxLayout, QWidget)

from certgen import credentials
from certgen.control_csv import read_csv_rows
from certgen.mailer import DEFAULT_EMAIL_BODY, SMTP_PRESETS
from ui import msgbox
from ui.workers import EmailWorker


class EmailWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Envio de certificados por e-mail")
        self.resize(820, 720)
        self._worker: EmailWorker = None
        self._row_index = {}

        root = QVBoxLayout(self)

        # CSV picker
        csv_row = QHBoxLayout()
        self.csv_edit = QLineEdit()
        self.csv_edit.setPlaceholderText("controle_envio - ....csv")
        pick_csv_btn = QPushButton("Escolher...")
        pick_csv_btn.clicked.connect(self._pick_csv)
        csv_row.addWidget(QLabel("Controle de envio (.CSV):"))
        csv_row.addWidget(self.csv_edit, 1)
        csv_row.addWidget(pick_csv_btn)
        root.addLayout(csv_row)

        # SMTP group
        smtp_box = QGroupBox("Servidor de e-mail (SMTP)")
        smtp_form = QFormLayout(smtp_box)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Personalizado")
        self.provider_combo.addItems(list(SMTP_PRESETS.keys()))
        self.provider_combo.currentTextChanged.connect(self._apply_provider_preset)
        smtp_form.addRow("Provedor:", self.provider_combo)

        self.provider_note = QLabel("")
        self.provider_note.setWordWrap(True)
        self.provider_note.setProperty("role", "hint")
        smtp_form.addRow("", self.provider_note)

        self.username_edit = QLineEdit()
        smtp_form.addRow("E-mail remetente:", self.username_edit)

        pwd_row = QHBoxLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        show_pwd_btn = QPushButton("👁")
        show_pwd_btn.setCheckable(True)
        show_pwd_btn.setFixedWidth(32)
        show_pwd_btn.toggled.connect(
            lambda on: self.password_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        pwd_row.addWidget(self.password_edit)
        pwd_row.addWidget(show_pwd_btn)
        smtp_form.addRow("Senha:", pwd_row)

        self.remember_pwd_check = QCheckBox("Lembrar senha neste computador (criptografada)")
        if not credentials.available():
            self.remember_pwd_check.setEnabled(False)
            self.remember_pwd_check.setText("Lembrar senha (indisponível neste sistema)")
        smtp_form.addRow("", self.remember_pwd_check)

        host_row = QHBoxLayout()
        self.host_edit = QLineEdit("smtp.hostinger.com")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(465)
        self.ssl_check = QCheckBox("SSL")
        self.ssl_check.setChecked(True)
        host_row.addWidget(self.host_edit, 1)
        host_row.addWidget(QLabel("Porta:"))
        host_row.addWidget(self.port_spin)
        host_row.addWidget(self.ssl_check)
        smtp_form.addRow("Servidor:", host_row)

        root.addWidget(smtp_box)

        # Message group
        msg_box = QGroupBox("Mensagem")
        msg_form = QFormLayout(msg_box)
        self.from_name_edit = QLineEdit("Equipe do Evento")
        msg_form.addRow("Nome remetente:", self.from_name_edit)
        self.subject_edit = QLineEdit("Seu certificado")
        msg_form.addRow("Assunto:", self.subject_edit)
        self.body_edit = QPlainTextEdit(DEFAULT_EMAIL_BODY)
        self.body_edit.setMaximumHeight(140)
        msg_form.addRow("Corpo (use {nome}):", self.body_edit)
        root.addWidget(msg_box)

        # Send options
        opt_box = QGroupBox("Opções de envio")
        opt_form = QFormLayout(opt_box)
        self.override_edit = QLineEdit()
        self.override_edit.setPlaceholderText("Se vazio, envia para o e-mail real de cada pessoa")
        opt_form.addRow("Receber teste em / forçar destino:", self.override_edit)
        limit_row = QHBoxLayout()
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(2000)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 3600)
        self.delay_spin.setValue(3)
        limit_row.addWidget(QLabel("Limite:"))
        limit_row.addWidget(self.limit_spin)
        limit_row.addWidget(QLabel("Intervalo (s):"))
        limit_row.addWidget(self.delay_spin)
        opt_form.addRow("", limit_row)
        root.addWidget(opt_box)

        # Actions
        action_row = QHBoxLayout()
        self.test_btn = QPushButton("Enviar 1 teste (não marca ninguém como enviado)")
        self.test_btn.clicked.connect(self._send_test)
        self.batch_btn = QPushButton("ENVIAR LOTE")
        self.batch_btn.setObjectName("primaryButton")
        self.batch_btn.clicked.connect(self._send_batch)
        self.cancel_btn = QPushButton("Cancelar envio")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        action_row.addWidget(self.test_btn)
        action_row.addWidget(self.batch_btn)
        action_row.addWidget(self.cancel_btn)
        root.addLayout(action_row)

        # Results table + log, tabbed
        tabs = QTabWidget()
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Nome", "Status", "Detalhe"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        tabs.addTab(self.results_table, "Resultados")

        from ui.log_panel import LogPanel
        self.log_panel = LogPanel()
        tabs.addTab(self.log_panel, "Log")
        root.addWidget(tabs, 1)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        self._load_settings()

    # ---------- persistence ----------

    def _load_settings(self):
        from certgen import prefs as prefs_mod
        data = (prefs_mod.load_prefs().get("email") or {})
        self.host_edit.setText(data.get("smtp_host", self.host_edit.text()))
        self.port_spin.setValue(data.get("smtp_port", self.port_spin.value()))
        self.ssl_check.setChecked(data.get("use_ssl", self.ssl_check.isChecked()))
        self.username_edit.setText(data.get("smtp_username", ""))
        self.from_name_edit.setText(data.get("from_name", self.from_name_edit.text()))
        self.subject_edit.setText(data.get("subject", self.subject_edit.text()))
        if data.get("body_template"):
            self.body_edit.setPlainText(data["body_template"])
        self.remember_pwd_check.setChecked(bool(data.get("remember_password", False)))

        if data.get("remember_password") and data.get("smtp_password_enc") and credentials.available():
            plain = credentials.unprotect(data["smtp_password_enc"])
            if plain is not None:
                self.password_edit.setText(plain)

    def _save_settings(self):
        from certgen import prefs as prefs_mod
        p = prefs_mod.load_prefs()
        email_data = {
            "smtp_host": self.host_edit.text().strip(),
            "smtp_port": self.port_spin.value(),
            "use_ssl": self.ssl_check.isChecked(),
            "smtp_username": self.username_edit.text().strip(),
            "from_name": self.from_name_edit.text().strip(),
            "subject": self.subject_edit.text().strip(),
            "body_template": self.body_edit.toPlainText(),
            "remember_password": self.remember_pwd_check.isChecked(),
        }
        if self.remember_pwd_check.isChecked() and credentials.available():
            blob = credentials.protect(self.password_edit.text())
            if blob:
                email_data["smtp_password_enc"] = blob
        p["email"] = email_data
        prefs_mod.save_prefs(p)

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # ---------- helpers ----------

    def _pick_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolha o controle de envio (.CSV)", "", "CSV (*.csv)")
        if path:
            self.csv_edit.setText(path)

    def _apply_provider_preset(self, name: str):
        preset = SMTP_PRESETS.get(name)
        if not preset:
            self.provider_note.setText("")
            return
        self.host_edit.setText(preset["host"])
        self.port_spin.setValue(preset["port"])
        self.ssl_check.setChecked(preset["use_ssl"])
        self.provider_note.setText(preset["note"])

    def _validate_common(self) -> bool:
        if not (self.csv_edit.text().strip() and os.path.isfile(self.csv_edit.text().strip())):
            msgbox.warn(self, "Atenção", "Escolha primeiro o arquivo controle_envio.csv.")
            return False
        if not self.username_edit.text().strip():
            msgbox.warn(self, "Atenção", "Informe a caixa remetente.")
            return False
        if not self.password_edit.text().strip():
            msgbox.warn(self, "Atenção", "Informe a senha da caixa de e-mail.")
            return False
        return True

    def _base_kwargs(self) -> dict:
        return dict(
            csv_path=self.csv_edit.text().strip(),
            smtp_host=self.host_edit.text().strip(),
            smtp_port=self.port_spin.value(),
            use_ssl=self.ssl_check.isChecked(),
            smtp_username=self.username_edit.text().strip(),
            smtp_password=self.password_edit.text().strip(),
            from_name=self.from_name_edit.text().strip() or "Equipe do Evento",
            from_email=self.username_edit.text().strip(),
            subject=self.subject_edit.text().strip() or "Seu certificado",
            body_template=self.body_edit.toPlainText(),
            to_override=self.override_edit.text().strip(),
        )

    def _set_running(self, running: bool):
        self.test_btn.setEnabled(not running)
        self.batch_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    def _start_worker(self, kwargs: dict, is_test: bool):
        self._set_running(True)
        self._worker = EmailWorker(kwargs)
        self._worker.row_result.connect(self._on_row_result)
        self._worker.log.connect(self.log_panel.append)
        self._worker.finished_ok.connect(lambda summary: self._on_finished(summary, is_test))
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    # ---------- actions ----------

    def _send_test(self):
        if not self._validate_common():
            return
        if not self.override_edit.text().strip():
            msgbox.warn(self, "Atenção", "Informe um e-mail em 'Receber teste em' para o teste.")
            return
        kwargs = self._base_kwargs()
        kwargs.update(limit=1, delay_seconds=0, create_backup=False, test_mode=True)
        self.log_panel.append("Iniciando envio de 1 teste (não altera o CSV)...")
        self._start_worker(kwargs, is_test=True)

    def _send_batch(self):
        if not self._validate_common():
            return
        to_override = self.override_edit.text().strip()
        limit = self.limit_spin.value()
        if to_override:
            msg = (f"Você vai enviar até {limit} certificado(s), mas todos irão para:\n\n"
                   f"{to_override}\n\nDeseja continuar?")
        else:
            msg = (f"Você vai enviar até {limit} certificado(s) para os e-mails reais do CSV.\n\n"
                   "Essa ação é real. Deseja continuar?")
        if not msgbox.ask_yes_no(self, "Confirmar envio em lote", msg):
            return

        kwargs = self._base_kwargs()
        kwargs.update(limit=limit, delay_seconds=self.delay_spin.value(),
                       create_backup=True, test_mode=False)
        self.results_table.setRowCount(0)
        self._row_index.clear()
        self.log_panel.append(f"Iniciando envio em lote... limite={limit}")
        self._start_worker(kwargs, is_test=False)

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.log_panel.append("Cancelamento solicitado...")

    def _on_row_result(self, row: dict, status: str, message: str):
        r = self.results_table.rowCount()
        self.results_table.insertRow(r)
        self.results_table.setItem(r, 0, QTableWidgetItem(row.get("nome", "")))
        status_item = QTableWidgetItem({"ok": "Enviado", "falha": "Falha", "ignorado": "Ignorado"}.get(status, status))
        self.results_table.setItem(r, 1, status_item)
        self.results_table.setItem(r, 2, QTableWidgetItem(message))

    def _on_finished(self, summary: dict, is_test: bool):
        self._set_running(False)
        self._save_settings()
        if is_test:
            self.status_label.setText(
                f"Teste concluído: {summary['sent_now']} enviado(s), {summary['failed_now']} falha(s).")
        else:
            self.status_label.setText(
                f"Lote concluído: {summary['sent_now']} enviado(s), {summary['failed_now']} falha(s), "
                f"{summary['skipped_now']} ignorado(s)."
                + (" (cancelado)" if summary.get("cancelled") else ""))
            msgbox.info(self, "Envio em lote", self.status_label.text())

    def _on_failed(self, error: str):
        self._set_running(False)
        msgbox.error(self, "Erro no envio", error)

    def retry_failed_only(self):
        """Re-runs the batch limited to rows currently 'falha' in the CSV
        -- since send_batch already retries falha/pendente automatically,
        this just re-triggers a batch send with the same settings."""
        self._send_batch()
