import os

from certgen import credentials, paths, prefs, presets


class TestPaths:
    def test_user_data_dir_is_under_appdata_not_file_location(self, tmp_path, monkeypatch):
        fake_appdata = tmp_path / "roaming"
        fake_appdata.mkdir()
        monkeypatch.setenv("APPDATA", str(fake_appdata))

        result = paths.user_data_dir()

        assert result == str(fake_appdata / paths.APP_DIR_NAME)
        assert os.path.isdir(result)

    def test_user_data_dir_independent_of_frozen_meipass(self, tmp_path, monkeypatch):
        # This is the direct regression test for baseline Known Issue #1:
        # simulate being a frozen exe (sys._MEIPASS set to a temp dir that
        # will be deleted on exit) and confirm persistence still lands
        # under %APPDATA%, not anywhere near _MEIPASS.
        import sys
        fake_appdata = tmp_path / "roaming"
        fake_appdata.mkdir()
        monkeypatch.setenv("APPDATA", str(fake_appdata))
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass_temp"), raising=False)

        result = paths.user_data_dir()

        assert "meipass_temp" not in result
        assert result.startswith(str(fake_appdata))

    def test_resource_path_uses_meipass_when_frozen(self, tmp_path, monkeypatch):
        import sys
        meipass = tmp_path / "meipass_temp"
        meipass.mkdir()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

        result = paths.resource_path("assets", "logo.ico")

        assert result == os.path.join(str(meipass), "assets", "logo.ico")

    def test_logs_dir_created(self):
        d = paths.logs_dir()
        assert os.path.isdir(d)


class TestPrefs:
    def test_save_then_load_round_trip(self):
        prefs.save_prefs({"tutorial_shown": True, "last_pdf": r"C:\a.pdf"})
        loaded = prefs.load_prefs()
        assert loaded["tutorial_shown"] is True
        assert loaded["last_pdf"] == r"C:\a.pdf"

    def test_missing_file_returns_empty_dict(self):
        assert prefs.load_prefs() == {}

    def test_survives_across_separate_load_calls(self):
        prefs.save_prefs({"a": 1})
        first = prefs.load_prefs()
        second = prefs.load_prefs()
        assert first == second == {"a": 1}


class TestPresets:
    def test_save_and_load_a_preset(self):
        presets.save_preset("Congresso Anual", {"evento": "Congresso Anual", "font_path": "x.ttf"})
        loaded = presets.load_preset("Congresso Anual")
        assert loaded["evento"] == "Congresso Anual"

    def test_list_names(self):
        presets.save_preset("A", {"evento": "A"})
        presets.save_preset("B", {"evento": "B"})
        assert presets.list_names() == ["A", "B"]

    def test_delete_preset(self):
        presets.save_preset("Temp", {"evento": "Temp"})
        presets.delete_preset("Temp")
        assert presets.load_preset("Temp") is None

    def test_password_not_stored_in_plaintext_when_remembered(self):
        presets.save_preset("ComSenha", {"evento": "E"}, remember_password=True, smtp_password="segredo123")
        raw = presets.load_all()["ComSenha"]
        assert "segredo123" not in str(raw)

    def test_password_not_saved_at_all_when_not_remembered(self):
        presets.save_preset("SemSenha", {"evento": "E"}, remember_password=False, smtp_password="segredo123")
        raw = presets.load_all()["SemSenha"]
        assert "smtp_password_enc" not in raw
        loaded = presets.load_preset("SemSenha")
        assert "smtp_password" not in loaded

    def test_remembered_password_round_trips_on_this_machine(self):
        if not credentials.available():
            import pytest
            pytest.skip("DPAPI not available on this platform")
        presets.save_preset("ComSenha2", {"evento": "E"}, remember_password=True, smtp_password="segredo123")
        loaded = presets.load_preset("ComSenha2")
        assert loaded.get("smtp_password") == "segredo123"


class TestCredentials:
    def test_protect_unprotect_round_trip_on_windows(self):
        if not credentials.available():
            import pytest
            pytest.skip("DPAPI not available on this platform")
        blob = credentials.protect("hunter2")
        assert blob is not None
        assert credentials.unprotect(blob) == "hunter2"

    def test_garbage_blob_returns_none_instead_of_raising(self):
        if not credentials.available():
            import pytest
            pytest.skip("DPAPI not available on this platform")
        assert credentials.unprotect("not-a-real-blob") is None
