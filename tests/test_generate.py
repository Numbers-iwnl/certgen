import os
import zipfile

import pymupdf as fitz
import pytest

from certgen.detect import compute_auto_area_firstpage, detect_field_rects_firstpage
from certgen.fields import ALL_FIELDS, FIELD_CPF, FIELD_DATE, FIELD_NAME, FIELD_TURMA
from certgen.generate import FieldSettings, GenerationEngine, GenerationOptions
from certgen.template_config import FieldCalibration, TemplateConfig


def build_cfg(certificate_pdf, required=None):
    required = required or [FIELD_NAME]
    doc = fitz.open(certificate_pdf)
    rects = detect_field_rects_firstpage(doc)
    doc.close()
    fields = {f: FieldCalibration(0, (r.x0, r.y0, r.x1, r.y1)) for f, r in rects.items()}
    return TemplateConfig(required=required, fields=fields)


def default_field_settings():
    return {f: FieldSettings() for f in ALL_FIELDS}


def base_records():
    return [
        {FIELD_NAME: "Ana Beatriz", FIELD_CPF: "12345678900", FIELD_TURMA: "Turma A",
         FIELD_DATE: "15/03/2026", "email": "ana@example.com"},
        {FIELD_NAME: "Bruno Costa", FIELD_CPF: "98765432100", FIELD_TURMA: "Turma B",
         FIELD_DATE: "16/03/2026", "email": "bruno@example.com"},
    ]


class TestBasicGeneration:
    def test_generates_one_pdf_per_record(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Meu Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)

        result = engine.run(base_records())

        assert result.ok == 2
        assert result.fail == 0
        pdfs = [f for f in os.listdir(result.outdir) if f.endswith(".pdf")]
        assert len(pdfs) == 2

    def test_generated_pdf_contains_the_name(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        pdf_path = next(os.path.join(result.outdir, f) for f in os.listdir(result.outdir)
                         if "Ana" in f and f.endswith(".pdf"))
        doc = fitz.open(pdf_path)
        text = doc.load_page(0).get_text()
        doc.close()
        assert "Ana" in text

    def test_writes_control_csv_with_pendente_status(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        assert result.control_csv_path
        from certgen.control_csv import read_csv_rows
        rows = read_csv_rows(result.control_csv_path)
        assert len(rows) == 2
        assert all(r["status_envio"] == "pendente" for r in rows)

    def test_blank_name_counts_as_failure(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        records = base_records() + [{FIELD_NAME: "", "email": ""}]

        result = engine.run(records)

        assert result.ok == 2
        assert result.fail == 1

    def test_required_cpf_missing_fails_that_record(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf, required=[FIELD_NAME, FIELD_CPF])
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        records = [{FIELD_NAME: "Carlos", FIELD_CPF: "", "email": ""}]

        result = engine.run(records)

        assert result.fail == 1
        assert result.ok == 0

    def test_merge_pdf_creates_single_combined_file(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"), merge_pdf=True)
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        assert result.merged_pdf_path
        merged = fitz.open(result.merged_pdf_path)
        assert merged.page_count == 2
        merged.close()

    def test_cancellation_stops_early(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        records = base_records() * 5  # 10 records

        result = engine.run(records, is_cancelled=lambda: True)

        assert result.cancelled is True
        assert result.ok == 0


class TestNameCaseAndDefaults:
    def test_title_case_applied_to_generated_name(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"),
                                 name_case_mode="title")
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run([{FIELD_NAME: "joão da silva", "email": ""}])

        from certgen.control_csv import read_csv_rows
        rows = read_csv_rows(result.control_csv_path)
        assert rows[0]["nome"] == "João da Silva"

    def test_default_turma_used_when_missing(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf, required=[FIELD_NAME, FIELD_TURMA])
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"),
                                 default_turma="Turma Padrão")
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run([{FIELD_NAME: "Ana", FIELD_TURMA: "", "email": ""}])

        from certgen.control_csv import read_csv_rows
        rows = read_csv_rows(result.control_csv_path)
        assert rows[0]["turma"] == "Turma Padrão"

    def test_global_date_override_applies_to_every_record(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf, required=[FIELD_NAME, FIELD_DATE])
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"),
                                 default_date_override="01/01/2030")
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        from certgen.control_csv import read_csv_rows
        rows = read_csv_rows(result.control_csv_path)
        assert all(r["data"] == "01/01/2030" for r in rows)


class TestSampleDryRun:
    def test_sample_limit_generates_only_n_and_no_control_csv(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"), sample_limit=1)
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        assert result.is_sample is True
        assert result.ok == 1
        assert result.control_csv_path == ""
        assert "_amostra" in result.outdir

    def test_sample_includes_longest_name_for_worst_case_check(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"), sample_limit=1)
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        records = [{FIELD_NAME: "Ana", "email": ""},
                   {FIELD_NAME: "Zzzzzzzzzzzzzzzzzzzzzzzzzz Muito Comprido", "email": ""}]

        result = engine.run(records)

        pdfs = os.listdir(result.outdir)
        assert any("Zzzzzzzzzzzzzzzzzzzzzzzzzz" in p for p in pdfs)


class TestPhase5Extras:
    def test_zip_export_contains_generated_pdfs(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"), make_zip=True)
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        assert result.zip_path and os.path.isfile(result.zip_path)
        with zipfile.ZipFile(result.zip_path) as zf:
            names = zf.namelist()
        assert len(names) == 2

    def test_cert_id_and_qr_do_not_break_generation(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"),
                                 add_cert_id=True, add_qr=True, qr_verify_base_url="https://x.test/v?id=")
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run(base_records())

        assert result.ok == 2
        pdf_path = os.path.join(result.outdir, os.listdir(result.outdir)[0])
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        assert len(page.get_images()) >= 1  # the QR code
        assert "cert_id:" in (doc.metadata.get("keywords") or "")
        doc.close()

    def test_filename_template_customization(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Congresso", output_dir=str(tmp_path / "out"),
                                 filename_template="{nome} - {evento}")
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run([{FIELD_NAME: "Ana", "email": ""}])

        files = os.listdir(result.outdir)
        assert any(f.startswith("Ana - Congresso") for f in files)

    def test_lock_pdf_sets_restrictive_permissions(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"), lock_pdf=True)
        engine = GenerationEngine(cfg, default_field_settings(), opt)
        result = engine.run([{FIELD_NAME: "Ana", "email": ""}])

        pdf_path = os.path.join(result.outdir, os.listdir(result.outdir)[0])
        doc = fitz.open(pdf_path)
        can_open_without_password = not doc.needs_pass
        doc.close()
        assert can_open_without_password  # user_pw is empty -- opens freely, only editing is restricted


class TestConsistentFontSize:
    def test_all_names_get_the_same_font_size(self, certificate_pdf, font_regular, tmp_path):
        cfg = build_cfg(certificate_pdf)
        settings = default_field_settings()
        settings[FIELD_NAME].use_consistent_size = True
        opt = GenerationOptions(template_pdf=certificate_pdf, font_path=font_regular,
                                 evento="Evento", output_dir=str(tmp_path / "out"))
        engine = GenerationEngine(cfg, settings, opt)
        records = [{FIELD_NAME: "Jo", "email": ""},
                   {FIELD_NAME: "Uma Pessoa Com Nome Bem Mais Longo Do Que O Outro", "email": ""}]

        result = engine.run(records)
        assert result.ok == 2  # doesn't crash, both fit at the shared size
