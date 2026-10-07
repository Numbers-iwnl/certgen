"""
Regression test for a gap caught during manual verification: the email
window's "remember password" checkbox was built but never actually wired
to persistence. These tests exercise the real EmailWindow widget (not a
mock), so a UI/backend wiring gap like that fails here instead of only
being catchable by manually opening the window.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from certgen import credentials


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def email_window(qapp):
    from ui.email_window import EmailWindow
    win = EmailWindow()
    yield win
    win.deleteLater()


class TestEmailSettingsPersistence:
    def test_settings_round_trip_without_password(self, qapp):
        from ui.email_window import EmailWindow
        win1 = EmailWindow()
        win1.host_edit.setText("smtp.myhost.test")
        win1.port_spin.setValue(2525)
        win1.ssl_check.setChecked(False)
        win1.username_edit.setText("me@myhost.test")
        win1.from_name_edit.setText("Equipe Teste")
        win1.subject_edit.setText("Assunto customizado")
        win1.body_edit.setPlainText("Corpo customizado {nome}")
        win1._save_settings()

        win2 = EmailWindow()
        assert win2.host_edit.text() == "smtp.myhost.test"
        assert win2.port_spin.value() == 2525
        assert win2.ssl_check.isChecked() is False
        assert win2.username_edit.text() == "me@myhost.test"
        assert win2.from_name_edit.text() == "Equipe Teste"
        assert win2.subject_edit.text() == "Assunto customizado"
        assert win2.body_edit.toPlainText() == "Corpo customizado {nome}"
        assert win2.password_edit.text() == ""  # never remembered -> never restored

    def test_password_not_persisted_when_remember_unchecked(self, qapp):
        from ui.email_window import EmailWindow
        win1 = EmailWindow()
        win1.password_edit.setText("shouldnotpersist")
        win1.remember_pwd_check.setChecked(False)
        win1._save_settings()

        from certgen import prefs
        saved = prefs.load_prefs().get("email", {})
        assert "smtp_password_enc" not in saved

        win2 = EmailWindow()
        assert win2.password_edit.text() == ""

    @pytest.mark.skipif(not credentials.available(), reason="DPAPI not available on this platform")
    def test_password_persisted_encrypted_when_remember_checked(self, qapp):
        from ui.email_window import EmailWindow
        win1 = EmailWindow()
        win1.password_edit.setText("supersecret")
        win1.remember_pwd_check.setChecked(True)
        win1._save_settings()

        from certgen import prefs
        saved = prefs.load_prefs().get("email", {})
        assert "smtp_password_enc" in saved
        assert "supersecret" not in str(saved)  # never stored in plaintext

        win2 = EmailWindow()
        assert win2.remember_pwd_check.isChecked() is True
        assert win2.password_edit.text() == "supersecret"

    def test_closing_the_window_saves_settings(self, qapp):
        from ui.email_window import EmailWindow
        win1 = EmailWindow()
        win1.subject_edit.setText("Assunto ao fechar")
        win1.close()

        win2 = EmailWindow()
        assert win2.subject_edit.text() == "Assunto ao fechar"

    def test_provider_preset_updates_host_port_ssl(self, email_window):
        email_window.provider_combo.setCurrentText("Gmail")
        assert email_window.host_edit.text() == "smtp.gmail.com"
        assert email_window.port_spin.value() == 587
        assert email_window.ssl_check.isChecked() is False
        assert email_window.provider_note.text()
