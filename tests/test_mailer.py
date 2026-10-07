import smtplib
import os
import pytest

from certgen import mailer


def make_pdf_row(tmp_path, name="Ana Beatriz", email="ana@example.com", status="pendente"):
    pdf_path = tmp_path / f"{name}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
    row = dict.fromkeys(mailer.FIELDNAMES, "")
    row.update({
        "nome": name, "email": email, "pdf_caminho": str(pdf_path),
        "pdf_arquivo": pdf_path.name, "status_envio": status,
    })
    return row


class TestBuildMessage:
    def test_builds_message_with_attachment(self, tmp_path):
        row = make_pdf_row(tmp_path)
        msg = mailer.build_message(row, recipient="ana@example.com", subject="Assunto",
                                    body_template="Olá, {nome}!", from_name="Equipe",
                                    from_email="equipe@example.com")
        assert msg["Subject"] == "Assunto"
        assert msg["To"] == "ana@example.com"
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert "Olá, Ana Beatriz!" in body
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1

    def test_missing_pdf_path_raises(self, tmp_path):
        row = make_pdf_row(tmp_path)
        row["pdf_caminho"] = ""
        with pytest.raises(ValueError):
            mailer.build_message(row, "a@b.com", "S", "B {nome}", "F", "f@b.com")

    def test_nonexistent_pdf_raises(self, tmp_path):
        row = make_pdf_row(tmp_path)
        row["pdf_caminho"] = str(tmp_path / "gone.pdf")
        with pytest.raises(FileNotFoundError):
            mailer.build_message(row, "a@b.com", "S", "B {nome}", "F", "f@b.com")

    def test_blank_name_falls_back_to_participante(self, tmp_path):
        row = make_pdf_row(tmp_path)
        row["nome"] = "   "
        msg = mailer.build_message(row, "a@b.com", "S", "Olá {nome}", "F", "f@b.com")
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert "Olá Participante" in body

    def test_stray_braces_in_body_do_not_crash(self, tmp_path):
        # baseline Known Issue #6: str.format() would raise here.
        row = make_pdf_row(tmp_path)
        msg = mailer.build_message(row, "a@b.com", "Assunto com { chave solta",
                                    "Olá {nome}, o valor é R$ {total} { }", "F", "f@b.com")
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert "Olá Ana Beatriz, o valor é R$ {total} { }" in body
        assert msg["Subject"] == "Assunto com { chave solta"


class _FakeSmtpServer:
    """Stands in for smtplib.SMTP/SMTP_SSL. Tracks how many TCP-level
    'connections' were made so tests can prove the connection is reused
    across a whole batch instead of reopened per email (Known Issue #5)."""
    instances_created = 0
    sent_messages = []
    fail_recipients = set()
    disconnect_next_send_for = set()

    def __init__(self, host, port, context=None):
        self.host = host
        self.port = port
        _FakeSmtpServer.instances_created += 1

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, pwd):
        pass

    def send_message(self, msg):
        to = msg["To"]
        if to in _FakeSmtpServer.disconnect_next_send_for:
            _FakeSmtpServer.disconnect_next_send_for.discard(to)
            raise smtplib.SMTPServerDisconnected("simulated disconnect")
        if to in _FakeSmtpServer.fail_recipients:
            raise RuntimeError("simulated SMTP failure")
        _FakeSmtpServer.sent_messages.append(msg)

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def _reset_fake_smtp(monkeypatch):
    _FakeSmtpServer.instances_created = 0
    _FakeSmtpServer.sent_messages = []
    _FakeSmtpServer.fail_recipients = set()
    _FakeSmtpServer.disconnect_next_send_for = set()
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", _FakeSmtpServer)
    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSmtpServer)
    yield _FakeSmtpServer


def base_kwargs(csv_path):
    return dict(
        csv_path=csv_path,
        smtp_host="smtp.example.com", smtp_port=465, use_ssl=True,
        smtp_username="user@example.com", smtp_password="secret",
        from_name="Equipe", from_email="user@example.com",
        subject="Seu certificado", body_template="Olá, {nome}!",
        delay_seconds=0, create_backup=False,
    )


def write_control_csv(tmp_path, rows):
    path = str(tmp_path / "control.csv")
    mailer.write_csv_rows(path, rows)
    return path


class TestSmtpConnection:
    def test_reuses_one_connection_across_multiple_sends(self, tmp_path, _reset_fake_smtp):
        rows = [make_pdf_row(tmp_path, f"P{i}", f"p{i}@example.com") for i in range(5)]
        csv_path = write_control_csv(tmp_path, rows)

        mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert _FakeSmtpServer.instances_created == 1
        assert len(_FakeSmtpServer.sent_messages) == 5

    def test_reconnects_once_after_a_disconnect_and_still_delivers(self, tmp_path, _reset_fake_smtp):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        _FakeSmtpServer.disconnect_next_send_for.add("ana@example.com")

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["sent_now"] == 1
        assert _FakeSmtpServer.instances_created == 2  # original + one reconnect


class TestSendBatch:
    def test_sends_pending_rows_and_marks_enviado(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com"),
                make_pdf_row(tmp_path, "Bruno", "bruno@example.com")]
        csv_path = write_control_csv(tmp_path, rows)

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["sent_now"] == 2
        assert result["failed_now"] == 0
        updated = mailer.read_csv_rows(csv_path)
        assert all(r["status_envio"] == "enviado" for r in updated)

    def test_skips_rows_already_enviado(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com", status="enviado"),
                make_pdf_row(tmp_path, "Bruno", "bruno@example.com", status="pendente")]
        csv_path = write_control_csv(tmp_path, rows)

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["sent_now"] == 1
        assert result["already_sent_before"] == 1

    def test_retries_rows_marked_falha(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com", status="falha")]
        csv_path = write_control_csv(tmp_path, rows)

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["sent_now"] == 1
        assert mailer.read_csv_rows(csv_path)[0]["status_envio"] == "enviado"

    def test_respects_limit(self, tmp_path):
        rows = [make_pdf_row(tmp_path, f"P{i}", f"p{i}@example.com") for i in range(5)]
        csv_path = write_control_csv(tmp_path, rows)

        result = mailer.send_batch(limit=2, **base_kwargs(csv_path))

        assert result["sent_now"] == 2
        statuses = [r["status_envio"] for r in mailer.read_csv_rows(csv_path)]
        assert statuses.count("enviado") == 2
        assert statuses.count("pendente") == 3

    def test_to_override_redirects_recipient(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        kwargs = base_kwargs(csv_path)
        kwargs["to_override"] = "tester@example.com"

        mailer.send_batch(limit=10, **kwargs)

        assert _FakeSmtpServer.sent_messages[0]["To"] == "tester@example.com"
        updated = mailer.read_csv_rows(csv_path)
        assert updated[0]["email"] == "ana@example.com"

    def test_row_with_no_email_and_no_override_marked_falha(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", email="")]
        csv_path = write_control_csv(tmp_path, rows)

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["failed_now"] == 1
        updated = mailer.read_csv_rows(csv_path)
        assert updated[0]["status_envio"] == "falha"
        assert "Sem email" in updated[0]["erro_envio"]

    def test_smtp_exception_marks_row_falha(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        _FakeSmtpServer.fail_recipients.add("ana@example.com")

        result = mailer.send_batch(limit=10, **base_kwargs(csv_path))

        assert result["failed_now"] == 1
        assert mailer.read_csv_rows(csv_path)[0]["status_envio"] == "falha"

    def test_missing_csv_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mailer.send_batch(limit=1, **base_kwargs(str(tmp_path / "nope.csv")))

    def test_create_backup_writes_bak_file(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        kwargs = base_kwargs(csv_path)
        kwargs["create_backup"] = True

        result = mailer.send_batch(limit=10, **kwargs)

        assert result["backup_path"]
        assert os.path.isfile(result["backup_path"])


class TestTestMode:
    def test_sends_real_email_but_never_touches_csv_status(self, tmp_path):
        # This is the fix for baseline Known Issue #2: a "send test" must
        # not mark a real row as delivered when only a test address got it.
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com", status="pendente")]
        csv_path = write_control_csv(tmp_path, rows)
        kwargs = base_kwargs(csv_path)
        kwargs["to_override"] = "tester@example.com"
        kwargs["test_mode"] = True

        result = mailer.send_batch(limit=1, **kwargs)

        assert result["sent_now"] == 1
        assert _FakeSmtpServer.sent_messages[0]["To"] == "tester@example.com"
        # the row Ana is still exactly as it was -- untouched by the test send
        updated = mailer.read_csv_rows(csv_path)
        assert updated[0]["status_envio"] == "pendente"
        assert updated[0]["enviado_em"] == ""

    def test_test_mode_never_creates_backup(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        kwargs = base_kwargs(csv_path)
        kwargs["create_backup"] = True
        kwargs["test_mode"] = True
        kwargs["to_override"] = "tester@example.com"

        result = mailer.send_batch(limit=1, **kwargs)

        assert result["backup_path"] == ""

    def test_test_mode_failure_also_does_not_touch_csv(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com")]
        csv_path = write_control_csv(tmp_path, rows)
        _FakeSmtpServer.fail_recipients.add("tester@example.com")
        kwargs = base_kwargs(csv_path)
        kwargs["test_mode"] = True
        kwargs["to_override"] = "tester@example.com"

        result = mailer.send_batch(limit=1, **kwargs)

        assert result["failed_now"] == 1
        updated = mailer.read_csv_rows(csv_path)
        assert updated[0]["status_envio"] == "pendente"


class TestOnRowCallback:
    def test_fires_once_per_attempt_with_status(self, tmp_path):
        rows = [make_pdf_row(tmp_path, "Ana", "ana@example.com"),
                make_pdf_row(tmp_path, "Bruno", email="")]
        csv_path = write_control_csv(tmp_path, rows)
        events = []

        mailer.send_batch(limit=10, on_row=lambda row, status, msg: events.append((row["nome"], status)),
                           **base_kwargs(csv_path))

        assert ("Ana", "ok") in events
        assert ("Bruno", "falha") in events


class TestCancellation:
    def test_stops_before_processing_further_rows(self, tmp_path):
        rows = [make_pdf_row(tmp_path, f"P{i}", f"p{i}@example.com") for i in range(5)]
        csv_path = write_control_csv(tmp_path, rows)
        calls = {"n": 0}

        def is_cancelled():
            calls["n"] += 1
            return calls["n"] > 2  # allow ~2 sends then stop

        result = mailer.send_batch(limit=10, is_cancelled=is_cancelled, **base_kwargs(csv_path))

        assert result["cancelled"] is True
        assert result["sent_now"] < 5
