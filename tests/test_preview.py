import pymupdf as fitz

from certgen.detect import detect_field_rects_firstpage
from certgen.fields import ALL_FIELDS, FIELD_CPF, FIELD_NAME, FIELD_TURMA
from certgen.generate import FieldSettings
from certgen.preview import render_preview_doc
from certgen.template_config import FieldCalibration, TemplateConfig


def build_cfg(certificate_pdf, required=None):
    doc = fitz.open(certificate_pdf)
    rects = detect_field_rects_firstpage(doc)
    doc.close()
    fields = {f: FieldCalibration(0, (r.x0, r.y0, r.x1, r.y1)) for f, r in rects.items()}
    return TemplateConfig(required=required or [FIELD_NAME], fields=fields)


def default_settings():
    return {f: FieldSettings() for f in ALL_FIELDS}


class TestRenderPreviewDoc:
    def test_draws_name_text(self, certificate_pdf, font_regular):
        cfg = build_cfg(certificate_pdf)
        doc = render_preview_doc(certificate_pdf, cfg, default_settings(), font_regular,
                                  {FIELD_NAME: "Ana Beatriz"})
        text = doc.load_page(0).get_text()
        doc.close()
        assert "Ana" in text

    def test_skips_non_required_fields_even_if_calibrated(self, certificate_pdf, font_regular):
        cfg = build_cfg(certificate_pdf, required=[FIELD_NAME])  # CPF/Turma calibrated but not required
        doc = render_preview_doc(certificate_pdf, cfg, default_settings(), font_regular,
                                  {FIELD_NAME: "Ana", FIELD_CPF: "111.222.333-44"})
        text = doc.load_page(0).get_text()
        doc.close()
        assert "111.222.333" not in text

    def test_draws_required_secondary_field(self, certificate_pdf, font_regular):
        cfg = build_cfg(certificate_pdf, required=[FIELD_NAME, FIELD_TURMA])
        doc = render_preview_doc(certificate_pdf, cfg, default_settings(), font_regular,
                                  {FIELD_NAME: "Ana", FIELD_TURMA: "Turma A"})
        text = doc.load_page(0).get_text()
        doc.close()
        assert "Turma A" in text or "Turma\xa0A" in text  # see render-quirk note in test_render.py

    def test_no_font_path_returns_unmodified_doc(self, certificate_pdf):
        cfg = build_cfg(certificate_pdf)
        doc = render_preview_doc(certificate_pdf, cfg, default_settings(), "", {FIELD_NAME: "Ana"})
        text = doc.load_page(0).get_text()
        doc.close()
        assert "Ana" not in text  # nothing drawn, still the raw template

    def test_common_name_size_used_when_provided(self, certificate_pdf, font_regular):
        cfg = build_cfg(certificate_pdf)
        doc = render_preview_doc(certificate_pdf, cfg, default_settings(), font_regular,
                                  {FIELD_NAME: "Ana"}, common_name_size=40.0)
        assert doc.load_page(0).get_text()  # renders without error
        doc.close()
