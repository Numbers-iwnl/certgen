import glob
import os

from certgen import control_csv as cc

SAMPLE_ROWS = [
    {
        "nome": "Ana Beatriz", "email": "ana@example.com", "cpf": "123.456.789-00",
        "turma": "Turma A", "data": "15/03/2026",
        "pdf_arquivo": "Certificado - Evento - Ana Beatriz.pdf",
        "pdf_caminho": r"C:\out\Certificado - Evento - Ana Beatriz.pdf",
    },
    {
        "nome": "Bruno Costa", "email": "", "cpf": "", "turma": "", "data": "16/03/2026",
        "pdf_arquivo": "Certificado - Evento - Bruno Costa.pdf",
        "pdf_caminho": r"C:\out\Certificado - Evento - Bruno Costa.pdf",
    },
]


class TestWriteSendControlCsv:
    def test_creates_csv_with_semicolon_delimiter_and_bom(self, tmp_path):
        path = cc.write_send_control_csv(str(tmp_path), "Meu Evento", SAMPLE_ROWS)
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            raw = f.read()
        assert raw.startswith(b"\xef\xbb\xbf")
        assert b";" in raw.split(b"\n", 1)[0]

    def test_default_status_is_pendente(self, tmp_path):
        path = cc.write_send_control_csv(str(tmp_path), "Evento", SAMPLE_ROWS)
        rows = cc.read_csv_rows(path)
        assert all(r["status_envio"] == "pendente" for r in rows)

    def test_filename_includes_sanitized_event_name(self, tmp_path):
        path = cc.write_send_control_csv(str(tmp_path), "Evento: Turma/2026", SAMPLE_ROWS)
        assert "Evento_ Turma_2026" in os.path.basename(path)

    def test_avoids_overwriting_existing_control_csv(self, tmp_path):
        first = cc.write_send_control_csv(str(tmp_path), "Evento", SAMPLE_ROWS)
        second = cc.write_send_control_csv(str(tmp_path), "Evento", SAMPLE_ROWS)
        assert first != second
        assert os.path.isfile(first) and os.path.isfile(second)

    def test_no_leftover_temp_files(self, tmp_path):
        cc.write_send_control_csv(str(tmp_path), "Evento", SAMPLE_ROWS)
        leftovers = glob.glob(str(tmp_path / ".controle_envio_*"))
        assert leftovers == []


class TestAtomicWriteCsvRows:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "control.csv")
        rows = [dict.fromkeys(cc.FIELDNAMES, "") for _ in range(2)]
        rows[0]["nome"] = "Teste Um"
        rows[0]["status_envio"] = "enviado"
        rows[1]["nome"] = "Teste Dois"
        rows[1]["status_envio"] = "falha"
        rows[1]["erro_envio"] = "Sem email."

        cc.write_csv_rows(path, rows)
        read_back = cc.read_csv_rows(path)

        assert read_back[0]["nome"] == "Teste Um"
        assert read_back[0]["status_envio"] == "enviado"
        assert read_back[1]["erro_envio"] == "Sem email."

    def test_no_temp_file_left_behind_after_write(self, tmp_path):
        path = str(tmp_path / "control.csv")
        rows = [dict.fromkeys(cc.FIELDNAMES, "")]
        cc.write_csv_rows(path, rows)
        entries = os.listdir(tmp_path)
        assert "control.csv" in entries
        assert not any(e.startswith(".controle_envio_") for e in entries)

    def test_original_file_untouched_if_write_fails(self, tmp_path, monkeypatch):
        path = str(tmp_path / "control.csv")
        good_rows = [dict.fromkeys(cc.FIELDNAMES, "")]
        good_rows[0]["nome"] = "Original"
        cc.write_csv_rows(path, good_rows)

        def _boom(*a, **k):
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(os, "replace", _boom)
        bad_rows = [dict.fromkeys(cc.FIELDNAMES, "")]
        bad_rows[0]["nome"] = "Should Not Land"
        try:
            cc.write_csv_rows(path, bad_rows)
        except OSError:
            pass

        # os.replace is mocked but the real one never ran -- the original
        # file on disk must still be exactly what it was before.
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
        assert "Original" in content
        assert "Should Not Land" not in content


class TestCsvHelpers:
    def test_normalize_status_lowercases_and_strips(self):
        assert cc.normalize_status("  Enviado  ") == "enviado"
        assert cc.normalize_status(None) == ""

    def test_can_send_row_true_for_blank_pendente_falha(self):
        assert cc.can_send_row({"status_envio": ""}) is True
        assert cc.can_send_row({"status_envio": "pendente"}) is True
        assert cc.can_send_row({"status_envio": "falha"}) is True

    def test_can_send_row_false_once_enviado(self):
        assert cc.can_send_row({"status_envio": "enviado"}) is False

    def test_backup_file_creates_timestamped_copy(self, tmp_path):
        path = cc.write_send_control_csv(str(tmp_path), "Evento", SAMPLE_ROWS)
        backup_path = cc.backup_file(path)
        assert os.path.isfile(backup_path)
        assert backup_path != path
        with open(path, encoding="utf-8-sig") as a, open(backup_path, encoding="utf-8-sig") as b:
            assert a.read() == b.read()
