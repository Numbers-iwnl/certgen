import pymupdf as fitz
from certgen import fonts


class TestAdvanceWidth:
    def test_wider_text_measures_wider(self, font_regular):
        short = fonts.advance_width("Ana", font_regular, 24)
        long = fonts.advance_width("Ana Beatriz da Silva Santos", font_regular, 24)
        assert long > short

    def test_larger_size_wider(self, font_regular):
        assert fonts.advance_width("Ana", font_regular, 48) > fonts.advance_width("Ana", font_regular, 12)

    def test_empty_string_zero_width(self, font_regular):
        assert fonts.advance_width("", font_regular, 24) == 0


class TestFontMetricsEm:
    def test_ascender_positive_descender_negative(self, font_regular):
        asc, desc = fonts.font_metrics_em(font_regular)
        assert asc > 0
        assert desc < 0

    def test_invalid_font_falls_back(self, tmp_path):
        bogus = tmp_path / "not_a_font.ttf"
        bogus.write_bytes(b"not a real font")
        assert fonts.font_metrics_em(str(bogus)) == (0.9, -0.2)


class TestFitsInRect:
    def test_short_text_fits_large_rect(self, font_regular):
        rect = fitz.Rect(0, 0, 400, 100)
        assert fonts.fits_in_rect("Ana", rect, font_regular, 24) is True

    def test_huge_font_does_not_fit_tiny_rect(self, font_regular):
        rect = fitz.Rect(0, 0, 40, 20)
        assert fonts.fits_in_rect("Ana Beatriz da Silva", rect, font_regular, 96) is False


class TestAutosizeFontToRect:
    def test_empty_text_returns_default(self, font_regular):
        rect = fitz.Rect(0, 0, 400, 100)
        assert fonts.autosize_font_to_rect("", rect, font_regular) == 24.0

    def test_result_within_bounds(self, font_regular):
        rect = fitz.Rect(0, 0, 400, 100)
        size = fonts.autosize_font_to_rect("Ana Beatriz", rect, font_regular, min_size=8.0, max_size=200.0)
        assert 8.0 <= size <= 200.0

    def test_fits_within_target_rect(self, font_regular):
        rect = fitz.Rect(0, 0, 300, 80)
        text = "Nome de Teste Razoavelmente Longo"
        size = fonts.autosize_font_to_rect(text, rect, font_regular)
        assert fonts.fits_in_rect(text, rect, font_regular, size)

    def test_longer_text_smaller_or_equal_font(self, font_regular):
        rect = fitz.Rect(0, 0, 300, 80)
        short_size = fonts.autosize_font_to_rect("Ana", rect, font_regular)
        long_size = fonts.autosize_font_to_rect(
            "Ana Beatriz Costa Fernandes de Oliveira Junior", rect, font_regular)
        assert long_size <= short_size


class TestCommonFontSizeForAll:
    def test_empty_list_default(self, font_regular):
        rect = fitz.Rect(0, 0, 400, 100)
        assert fonts.common_font_size_for_all([], rect, font_regular) == 24.0

    def test_common_size_fits_every_name(self, font_regular):
        rect = fitz.Rect(0, 0, 300, 80)
        names = ["Ana", "Bruno Costa", "Carla Fernandes de Oliveira Santos"]
        size = fonts.common_font_size_for_all(names, rect, font_regular)
        assert all(fonts.fits_in_rect(n, rect, font_regular, size) for n in names)

    def test_no_larger_than_worst_case_individual(self, font_regular):
        rect = fitz.Rect(0, 0, 300, 80)
        names = ["Ana", "Carla Fernandes de Oliveira Santos e Silva Junior"]
        common = fonts.common_font_size_for_all(names, rect, font_regular)
        worst = min(fonts.autosize_font_to_rect(n, rect, font_regular) for n in names)
        assert common <= worst
