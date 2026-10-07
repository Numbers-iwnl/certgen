from certgen import xlsx_source as xs
from certgen.fields import FIELD_CPF, FIELD_DATE, FIELD_EMAIL, FIELD_NAME, FIELD_TURMA


class TestReadRecordsFromXlsx:
    def test_reads_all_columns_no_header(self, sample_xlsx_no_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_no_header, skip_header=False)
        assert len(recs) == 3  # blank-name row skipped

        first = recs[0]
        assert first[FIELD_NAME] == "Ana Beatriz"
        assert first[FIELD_CPF] == "12345678900"
        assert first[FIELD_TURMA] == "Turma A"
        assert first[FIELD_DATE] == "15/03/2026"
        assert first[FIELD_EMAIL] == "ana@example.com"

    def test_missing_optional_columns_become_empty(self, sample_xlsx_no_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_no_header, skip_header=False)
        bruno = recs[1]
        assert bruno[FIELD_CPF] == ""
        assert bruno[FIELD_TURMA] == ""
        assert bruno[FIELD_DATE] == ""
        assert bruno[FIELD_EMAIL] == ""

    def test_string_date_passthrough(self, sample_xlsx_no_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_no_header, skip_header=False)
        assert recs[2][FIELD_DATE] == "10/02/2026"

    def test_skip_header_true_drops_first_row(self, sample_xlsx_with_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_with_header, skip_header=True)
        assert len(recs) == 1
        assert recs[0][FIELD_NAME] == "Diego Alves"

    def test_skip_header_false_treats_header_as_data(self, sample_xlsx_with_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_with_header, skip_header=False)
        assert len(recs) == 2
        assert recs[0][FIELD_NAME] == "Nome"

    def test_blank_rows_excluded(self, sample_xlsx_no_header):
        recs = xs.read_records_from_xlsx(sample_xlsx_no_header, skip_header=False)
        assert "" not in [r[FIELD_NAME] for r in recs]


class TestSniffHeaders:
    def test_returns_first_row_values(self, sample_xlsx_with_header):
        headers = xs.sniff_headers(sample_xlsx_with_header)
        assert headers == ["Nome", "CPF", "Turma", "Data", "Email"]

    def test_returns_reordered_headers(self, sample_xlsx_reordered_headers):
        headers = xs.sniff_headers(sample_xlsx_reordered_headers)
        assert headers == ["Email", "Nome", "Turma"]


class TestDetectDefaultMapping:
    def test_matches_by_header_name_case_insensitive(self):
        mapping = xs.detect_default_mapping(["email", "NOME", "Turma"])
        assert mapping[FIELD_EMAIL] == 0
        assert mapping[FIELD_NAME] == 1
        assert mapping[FIELD_TURMA] == 2

    def test_falls_back_positionally_for_unrecognized_headers(self):
        mapping = xs.detect_default_mapping(["Col A", "Col B", "Col C", "Col D", "Col E"])
        assert mapping[FIELD_NAME] == 0
        assert mapping[FIELD_CPF] == 1
        assert mapping[FIELD_TURMA] == 2
        assert mapping[FIELD_DATE] == 3
        assert mapping[FIELD_EMAIL] == 4

    def test_accent_insensitive(self):
        mapping = xs.detect_default_mapping(["E-mail"])
        assert mapping[FIELD_EMAIL] == 0


class TestReadRecordsWithMapping:
    def test_reads_reordered_columns_correctly(self, sample_xlsx_reordered_headers):
        headers = xs.sniff_headers(sample_xlsx_reordered_headers)
        mapping = xs.detect_default_mapping(headers)
        recs = xs.read_records_with_mapping(sample_xlsx_reordered_headers, mapping, skip_header=True)

        assert len(recs) == 1
        assert recs[0][FIELD_NAME] == "Elis Regina"
        assert recs[0][FIELD_EMAIL] == "elis@example.com"
        assert recs[0][FIELD_TURMA] == "Turma D"
        assert recs[0][FIELD_CPF] == ""  # unmapped -> blank

    def test_unmapped_field_is_blank_for_every_record(self, sample_xlsx_with_header):
        mapping = {FIELD_NAME: 0, FIELD_CPF: None, FIELD_TURMA: None, FIELD_DATE: None, FIELD_EMAIL: None}
        recs = xs.read_records_with_mapping(sample_xlsx_with_header, mapping, skip_header=True)
        assert recs[0][FIELD_NAME] == "Diego Alves"
        assert recs[0][FIELD_CPF] == ""
        assert recs[0][FIELD_EMAIL] == ""

    def test_blank_name_row_skipped(self, sample_xlsx_no_header):
        mapping = {FIELD_NAME: 0, FIELD_CPF: 1, FIELD_TURMA: 2, FIELD_DATE: 3, FIELD_EMAIL: 4}
        recs = xs.read_records_with_mapping(sample_xlsx_no_header, mapping, skip_header=False)
        assert len(recs) == 3
