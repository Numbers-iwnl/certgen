"""
Email sending -- rewritten from the baseline email_sender.py with the
Phase 4 fixes:

  - Known Issue #5: one SMTP connection is opened for the whole batch
    instead of once per email, with a bounded reconnect-and-retry on
    transient disconnects instead of failing the row outright.
  - Known Issue #6: the email body is filled in with textutil.safe_format
    (literal placeholder substitution), not str.format(), so a stray '{'
    or '}' a user types into the body can't crash that send.
  - Known Issue #2: a new `test_mode` flag sends a real email to the
    override address WITHOUT touching any row's status_envio -- so
    "send a test" can never again mark a real recipient as served when
    they weren't.
  - Known Issue #13: `is_cancelled` is checked between sends so a batch
    can be stopped from the UI instead of only via Task Manager.

Everything else (resume-by-status, CSV columns, backup-before-batch,
per-row error capture) matches the baseline's behavior, pinned by
tests/test_mailer.py.
"""
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Callable, Optional

from .control_csv import FIELDNAMES, backup_file, can_send_row, read_csv_rows, write_csv_rows
from .textutil import safe_format

DEFAULT_EMAIL_BODY = (
    "Olá, {nome}!\n\n"
    "Segue em anexo o seu certificado.\n\n"
    "Se tiver qualquer dificuldade para abrir o arquivo, responda este e-mail.\n\n"
    "Atenciosamente,\n"
    "Equipe do Evento"
)

# host / port / use_ssl / a short guidance note shown in the UI.
SMTP_PRESETS = {
    "Gmail": {
        "host": "smtp.gmail.com", "port": 587, "use_ssl": False,
        "note": "Use uma 'senha de app' do Google (não a senha normal da conta). "
                "Ative em: Conta Google > Segurança > Senhas de app.",
    },
    "Microsoft 365 / Outlook": {
        "host": "smtp.office365.com", "port": 587, "use_ssl": False,
        "note": "Pode exigir uma 'senha de app' se a verificação em duas etapas "
                "estiver ativada.",
    },
    "Hostinger": {
        "host": "smtp.hostinger.com", "port": 465, "use_ssl": True,
        "note": "Use o e-mail completo da caixa e a senha da caixa de e-mail.",
    },
    "Zoho Mail": {
        "host": "smtp.zoho.com", "port": 465, "use_ssl": True,
        "note": "Pode exigir uma 'senha de app' se a autenticação em duas "
                "etapas estiver ativada.",
    },
}

_MAX_RECONNECT_ATTEMPTS = 2
_RECONNECT_BACKOFF_SECONDS = (2, 4)


class SmtpConnection:
    """A single, reused SMTP session for an entire batch, with a bounded
    reconnect-and-retry on transient disconnects."""

    def __init__(self, host: str, port: int, use_ssl: bool, username: str, password: str):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.username = username
        self.password = password
        self._server = None

    def connect(self) -> None:
        self.close()
        context = ssl.create_default_context()
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        server.login(self.username, self.password)
        self._server = server

    def send(self, msg: EmailMessage) -> None:
        if self._server is None:
            self.connect()
        try:
            self._server.send_message(msg)
            return
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError):
            pass  # fall through to reconnect-and-retry below

        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RECONNECT_ATTEMPTS):
            time.sleep(_RECONNECT_BACKOFF_SECONDS[min(attempt, len(_RECONNECT_BACKOFF_SECONDS) - 1)])
            try:
                self.connect()
                self._server.send_message(msg)
                return
            except Exception as e:
                last_error = e
        raise last_error or RuntimeError("Falha ao reconectar ao servidor SMTP.")

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.quit()
            except Exception:
                pass
            self._server = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def build_message(row: dict, recipient: str, subject: str, body_template: str,
                   from_name: str, from_email: str) -> EmailMessage:
    nome = row.get("nome", "").strip() or "Participante"
    pdf_path = row.get("pdf_caminho", "").strip()

    if not pdf_path:
        raise ValueError("Linha sem pdf_caminho.")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF não encontrado: {pdf_path}")

    msg = EmailMessage()
    msg["Subject"] = safe_format(subject, nome=nome)
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = recipient
    msg.set_content(safe_format(body_template, nome=nome))

    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    msg.add_attachment(pdf_data, maintype="application", subtype="pdf",
                        filename=os.path.basename(pdf_path))
    return msg


def send_batch(
    csv_path: str,
    smtp_host: str,
    smtp_port: int,
    use_ssl: bool,
    smtp_username: str,
    smtp_password: str,
    from_name: str,
    from_email: str,
    subject: str,
    body_template: str,
    limit: int = 10,
    delay_seconds: int = 3,
    to_override: str = "",
    create_backup: bool = True,
    test_mode: bool = False,
    logger: Optional[Callable[[str], None]] = None,
    on_row: Optional[Callable[[dict, str, str], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    Send certificates from the control CSV.

    test_mode=True sends real email(s) but never writes status_envio /
    erro_envio / enviado_em back to the CSV -- use this for "send me a
    test" so it can never mark a real recipient as served.

    on_row(row, status, message) fires after each attempt ("ok" / "falha"
    / "ignorado"), for a UI results table -- independent of `logger`,
    which stays available for a scrolling text log.
    """

    def log(m: str):
        if logger:
            logger(m)

    def emit_row(row: dict, status: str, message: str = ""):
        if on_row:
            on_row(dict(row), status, message)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV não encontrado: {csv_path}")

    rows = read_csv_rows(csv_path)
    if not rows:
        raise ValueError("CSV vazio.")

    backup_path = ""
    if create_backup and not test_mode:
        backup_path = backup_file(csv_path)
        log(f"Backup criado: {backup_path}")

    pending_count = sum(1 for row in rows if can_send_row(row))
    sent_count_before = sum(1 for row in rows if row.get("status_envio", "").strip().lower() == "enviado")

    log(f"Total de linhas: {len(rows)}")
    log(f"Já enviados: {sent_count_before}")
    log(f"Pendentes/falha para tentar agora: {pending_count}")
    log(f"Limite desta execução: {limit}")

    sent_now = 0
    failed_now = 0
    skipped_now = 0
    cancelled = False

    with SmtpConnection(smtp_host, smtp_port, use_ssl, smtp_username, smtp_password) as conn:
        for idx, row in enumerate(rows, start=1):
            if sent_now >= limit:
                break
            if is_cancelled and is_cancelled():
                log("Envio cancelado pelo usuário.")
                cancelled = True
                break

            if not can_send_row(row):
                skipped_now += 1
                continue

            recipient_original = row.get("email", "").strip()
            recipient = (to_override or "").strip() or recipient_original

            if not recipient:
                if not test_mode:
                    row["status_envio"] = "falha"
                    row["erro_envio"] = "Sem email."
                    row["enviado_em"] = ""
                    write_csv_rows(csv_path, rows)
                failed_now += 1
                log(f"[FALHA] {idx}: {row.get('nome','')} | sem email")
                emit_row(row, "falha", "Sem email.")
                continue

            try:
                msg = build_message(row=row, recipient=recipient, subject=subject,
                                     body_template=body_template, from_name=from_name,
                                     from_email=from_email)
                conn.send(msg)

                if not test_mode:
                    import datetime
                    row["status_envio"] = "enviado"
                    row["erro_envio"] = ""
                    row["enviado_em"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    write_csv_rows(csv_path, rows)

                sent_now += 1
                log(f"[OK] {idx}: {row.get('nome','')} -> {recipient}")
                emit_row(row, "ok", "")

            except Exception as e:
                if not test_mode:
                    row["status_envio"] = "falha"
                    row["erro_envio"] = str(e)[:300]
                    row["enviado_em"] = ""
                    write_csv_rows(csv_path, rows)
                failed_now += 1
                log(f"[ERRO] {idx}: {row.get('nome','')} -> {recipient} | {e}")
                emit_row(row, "falha", str(e)[:300])

            if sent_now < limit and not (is_cancelled and is_cancelled()):
                time.sleep(delay_seconds)

    return {
        "backup_path": backup_path,
        "total": len(rows),
        "pending_before": pending_count,
        "already_sent_before": sent_count_before,
        "sent_now": sent_now,
        "failed_now": failed_now,
        "skipped_now": skipped_now,
        "cancelled": cancelled,
        "csv_path": csv_path,
        "test_mode": test_mode,
    }
