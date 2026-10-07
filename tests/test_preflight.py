import pymupdf as fitz

from certgen.fields import FIELD_CPF, FIELD_EMAIL, FIELD_NAME
from certgen.preflight import run_preflight


def rect():
    return fitz.Rect(0, 0, 250, 60)


class TestPreflight:
    def test_flags_missing_email_when_needed(self, font_regular):
        records = [{FIELD_NAME: "Ana", FIELD_EMAIL: ""}, {FIELD_NAME: "Bruno", FIELD_EMAIL: "b@x.com"}]
        report = run_preflight(records, required_fields=[], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none", needs_email=True)
        assert report.missing_email == ["Ana"]

    def test_does_not_flag_email_when_not_needed(self, font_regular):
        records = [{FIELD_NAME: "Ana", FIELD_EMAIL: ""}]
        report = run_preflight(records, required_fields=[], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none", needs_email=False)
        assert report.missing_email == []

    def test_flags_invalid_cpf_when_required(self, font_regular):
        records = [{FIELD_NAME: "Ana", FIELD_CPF: "123"}, {FIELD_NAME: "Bruno", FIELD_CPF: "12345678900"}]
        report = run_preflight(records, required_fields=[FIELD_CPF], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none")
        assert report.invalid_cpf == ["Ana"]

    def test_flags_duplicate_names(self, font_regular):
        records = [{FIELD_NAME: "Ana"}, {FIELD_NAME: "Ana"}, {FIELD_NAME: "Bruno"}]
        report = run_preflight(records, required_fields=[], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none")
        assert report.duplicate_names == ["Ana"]

    def test_flags_names_that_shrink_below_readable_size(self, font_regular):
        tiny_rect = fitz.Rect(0, 0, 30, 10)
        records = [{FIELD_NAME: "Um Nome Extremamente Longo Que Nao Vai Caber De Jeito Nenhum"}]
        report = run_preflight(records, required_fields=[], name_rect=tiny_rect,
                                font_path=font_regular, name_case_mode="none")
        assert report.names_too_small

    def test_has_warnings_false_when_clean(self, font_regular):
        records = [{FIELD_NAME: "Ana", FIELD_EMAIL: "a@x.com", FIELD_CPF: "12345678900"}]
        report = run_preflight(records, required_fields=[FIELD_CPF], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none", needs_email=True)
        assert report.has_warnings is False

    def test_blank_name_rows_are_skipped_entirely(self, font_regular):
        records = [{FIELD_NAME: ""}]
        report = run_preflight(records, required_fields=[FIELD_CPF], name_rect=rect(),
                                font_path=font_regular, name_case_mode="none", needs_email=True)
        assert not report.has_warnings
