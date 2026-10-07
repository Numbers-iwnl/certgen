import re
import pytest

from certgen import textutil


class TestFormatCpf:
    def test_formats_11_digits(self):
        assert textutil.format_cpf("12345678900") == "123.456.789-00"

    def test_strips_existing_punctuation(self):
        assert textutil.format_cpf("123.456.789-00") == "123.456.789-00"

    def test_wrong_length_unchanged(self):
        assert textutil.format_cpf("123") == "123"

    def test_empty_and_none(self):
        assert textutil.format_cpf("") == ""
        assert textutil.format_cpf(None) == ""


class TestSanitizeFilename:
    def test_replaces_forbidden_chars(self):
        assert textutil.sanitize_filename('a\\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_strips_trailing_dots_and_spaces(self):
        assert textutil.sanitize_filename("nome. ") == "nome"

    def test_normal_names_untouched(self):
        assert textutil.sanitize_filename("João da Silva") == "João da Silva"

    def test_blank_becomes_placeholder(self):
        assert textutil.sanitize_filename("") == "sem_nome"
        assert textutil.sanitize_filename("...") == "sem_nome"

    @pytest.mark.parametrize("reserved", ["CON", "con", "PRN", "AUX", "NUL", "COM1", "LPT9"])
    def test_reserved_windows_names_get_prefixed(self, reserved):
        result = textutil.sanitize_filename(reserved)
        assert result != reserved
        assert result.endswith(reserved)

    def test_reserved_name_with_extension_still_caught(self):
        result = textutil.sanitize_filename("CON.pdf")
        assert not result.upper().startswith("CON.")

    def test_non_reserved_name_untouched(self):
        assert textutil.sanitize_filename("Convite") == "Convite"


class TestTruncateForPathLimits:
    def test_short_name_untouched(self):
        assert textutil.truncate_for_path_limits(r"C:\out", "file.pdf", max_total=240) == "file.pdf"

    def test_long_name_truncated_but_extension_kept(self):
        directory = "C:\\out"
        long_name = ("A" * 300) + ".pdf"
        result = textutil.truncate_for_path_limits(directory, long_name, max_total=50)
        assert result.endswith(".pdf")
        assert len(directory) + 1 + len(result) <= 50


class TestTimestamp:
    def test_matches_format(self):
        assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}h\d{2}$", textutil.timestamp())


class TestEnsureFontFile:
    def test_accepts_ttf(self, font_regular):
        assert textutil.ensure_font_file(font_regular) == font_regular

    def test_rejects_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            textutil.ensure_font_file(str(tmp_path / "nope.ttf"))

    def test_rejects_empty(self):
        with pytest.raises(FileNotFoundError):
            textutil.ensure_font_file("")

    def test_rejects_wrong_extension(self, tmp_path):
        bad = tmp_path / "font.txt"
        bad.write_text("not a font")
        with pytest.raises(ValueError):
            textutil.ensure_font_file(str(bad))


class TestUniquePath:
    def test_no_collision(self, tmp_path):
        p = str(tmp_path / "file.pdf")
        assert textutil.unique_path(p) == p

    def test_single_collision(self, tmp_path):
        (tmp_path / "file.pdf").write_text("x")
        assert textutil.unique_path(str(tmp_path / "file.pdf")) == str(tmp_path / "file (2).pdf")

    def test_multiple_collisions(self, tmp_path):
        (tmp_path / "file.pdf").write_text("x")
        (tmp_path / "file (2).pdf").write_text("x")
        (tmp_path / "file (3).pdf").write_text("x")
        assert textutil.unique_path(str(tmp_path / "file.pdf")) == str(tmp_path / "file (4).pdf")


class TestTitleCasePtbr:
    def test_capitalizes_each_word(self):
        assert textutil.title_case_ptbr("ana beatriz") == "Ana Beatriz"

    def test_keeps_connectives_lowercase_mid_name(self):
        assert textutil.title_case_ptbr("joão da silva santos") == "João da Silva Santos"

    def test_first_word_capitalized_even_if_connective(self):
        assert textutil.title_case_ptbr("da silva") == "Da Silva"

    def test_all_caps_input_normalizes(self):
        assert textutil.title_case_ptbr("MARIA DE SOUZA") == "Maria de Souza"

    def test_hyphenated_name(self):
        assert textutil.title_case_ptbr("maria-clara silva") == "Maria-Clara Silva"

    def test_empty_string(self):
        assert textutil.title_case_ptbr("") == ""

    def test_multiple_connectives(self):
        assert textutil.title_case_ptbr("carlos dos santos e silva") == "Carlos dos Santos e Silva"


class TestApplyNameCase:
    def test_none_mode_passthrough(self):
        assert textutil.apply_name_case("ana beatriz", "none") == "ana beatriz"

    def test_title_mode_uses_ptbr_rules(self):
        assert textutil.apply_name_case("joão da silva", "title") == "João da Silva"

    def test_upper_mode(self):
        assert textutil.apply_name_case("joão da silva", "upper") == "JOÃO DA SILVA"


class TestSafeFormat:
    def test_substitutes_known_placeholder(self):
        assert textutil.safe_format("Olá, {nome}!", nome="Ana") == "Olá, Ana!"

    def test_ignores_stray_braces_instead_of_raising(self):
        # baseline Known Issue #6: str.format() would raise here.
        result = textutil.safe_format("Preço: R$ {valor} (sem chaves soltas: { })", nome="Ana")
        assert result == "Preço: R$ {valor} (sem chaves soltas: { })"

    def test_multiple_placeholders(self):
        result = textutil.safe_format("{nome} - {evento}", nome="Ana", evento="Congresso")
        assert result == "Ana - Congresso"

    def test_repeated_placeholder(self):
        result = textutil.safe_format("{nome}, olá {nome}!", nome="Ana")
        assert result == "Ana, olá Ana!"
