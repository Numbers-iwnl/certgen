import json
from certgen.fields import FIELD_CPF, FIELD_NAME, FIELD_TURMA
from certgen.template_config import (
    CALIBRATION_SUFFIX, FieldCalibration, TemplateConfig,
    load_template_config, save_template_config,
)


class TestTemplateConfigRoundTrip:
    def test_save_then_load_preserves_fields_and_required(self, blank_pdf):
        cfg = TemplateConfig(
            required=[FIELD_NAME, FIELD_CPF],
            fields={
                FIELD_NAME: FieldCalibration(0, (10.0, 20.0, 200.0, 60.0), style=None),
                FIELD_CPF: FieldCalibration(0, (10.0, 80.0, 200.0, 100.0), style={"bold": True}),
            },
        )
        save_template_config(blank_pdf, cfg)
        loaded = load_template_config(blank_pdf)

        assert loaded is not None
        assert set(loaded.required) == {FIELD_NAME, FIELD_CPF}
        assert loaded.fields[FIELD_NAME].rect == (10.0, 20.0, 200.0, 60.0)
        assert loaded.fields[FIELD_CPF].style == {"bold": True}

    def test_meta_file_uses_expected_suffix(self, blank_pdf):
        import os
        cfg = TemplateConfig(required=[FIELD_NAME], fields={FIELD_NAME: FieldCalibration(0, (0, 0, 1, 1))})
        save_template_config(blank_pdf, cfg)
        assert os.path.isfile(blank_pdf + CALIBRATION_SUFFIX)

    def test_no_config_returns_none(self, blank_pdf):
        assert load_template_config(blank_pdf) is None

    def test_saved_version_is_3(self, blank_pdf):
        cfg = TemplateConfig(required=[FIELD_NAME], fields={FIELD_NAME: FieldCalibration(0, (0, 0, 1, 1))})
        save_template_config(blank_pdf, cfg)
        with open(blank_pdf + CALIBRATION_SUFFIX, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 3


class TestLegacyConfigFormats:
    def test_loads_v1_single_field_format(self, blank_pdf):
        meta_path = blank_pdf + CALIBRATION_SUFFIX
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"page_index": 0, "rect": [1, 2, 3, 4]}, f)

        cfg = load_template_config(blank_pdf)

        assert cfg is not None
        assert cfg.version == 1
        assert cfg.required == [FIELD_NAME]
        assert cfg.fields[FIELD_NAME].rect == (1, 2, 3, 4)

    def test_loads_v2_multi_field_without_style(self, blank_pdf):
        meta_path = blank_pdf + CALIBRATION_SUFFIX
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "version": 2,
                "required": [FIELD_NAME, FIELD_TURMA],
                "fields": {
                    FIELD_NAME: {"page_index": 0, "rect": [0, 0, 10, 10]},
                    FIELD_TURMA: {"page_index": 0, "rect": [0, 20, 10, 30]},
                },
            }, f)

        cfg = load_template_config(blank_pdf)

        assert cfg.version == 2
        assert cfg.fields[FIELD_TURMA].style is None

    def test_corrupt_json_returns_none(self, blank_pdf):
        meta_path = blank_pdf + CALIBRATION_SUFFIX
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        assert load_template_config(blank_pdf) is None
