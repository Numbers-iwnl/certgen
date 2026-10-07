"""The send-control CSV: the handoff file between generation and email
sending. Behavior ported from email_sender.py, with one deliberate fix:
writes are now atomic (temp file + os.replace) instead of writing
directly over the live file, closing baseline Known Issue #11 (a crash
mid-write could corrupt the file the whole resume mechanism depends on).
"""
import csv
import datetime
import os
import tempfile

from .textutil import sanitize_filename, unique_path

FIELDNAMES = [
    "nome", "email", "cpf", "turma", "data",
    "pdf_arquivo", "pdf_caminho",
    "status_envio", "erro_envio", "enviado_em",
]


def normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def can_send_row(row: dict) -> bool:
    return normalize_status(row.get("status_envio", "")) in ("", "pendente", "falha")


def read_csv_rows(path: str):
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = []
        for row in reader:
            rows.append({field: row.get(field, "") for field in FIELDNAMES})
        return rows


def _atomic_write_csv(path: str, rows) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".controle_envio_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELDNAMES})
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def write_csv_rows(path: str, rows) -> None:
    _atomic_write_csv(path, rows)


def backup_file(path: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.{stamp}.bak"
    with open(path, "r", encoding="utf-8-sig") as src, open(backup_path, "w", encoding="utf-8-sig") as dst:
        dst.write(src.read())
    return backup_path


def write_send_control_csv(outdir: str, evento: str, rows) -> str:
    """Create the initial control CSV right after certificate generation."""
    filename = unique_path(os.path.join(outdir, f"controle_envio - {sanitize_filename(evento)}.csv"))
    normalized = [
        {
            "nome": row.get("nome", ""),
            "email": row.get("email", ""),
            "cpf": row.get("cpf", ""),
            "turma": row.get("turma", ""),
            "data": row.get("data", ""),
            "pdf_arquivo": row.get("pdf_arquivo", ""),
            "pdf_caminho": row.get("pdf_caminho", ""),
            "status_envio": row.get("status_envio", "pendente"),
            "erro_envio": row.get("erro_envio", ""),
            "enviado_em": row.get("enviado_em", ""),
        }
        for row in rows
    ]
    _atomic_write_csv(filename, normalized)
    return filename
