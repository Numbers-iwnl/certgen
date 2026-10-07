import os

from certgen import logging_setup


class TestSetupLogging:
    def test_creates_log_file_under_appdata(self):
        log_path = logging_setup.setup_logging()
        logging_setup.logger.info("hello")
        for h in logging_setup.logger.handlers:
            h.flush()
        assert os.path.isfile(log_path)
        with open(log_path, encoding="utf-8") as f:
            assert "hello" in f.read()


class TestExcepthook:
    def test_crash_callback_receives_formatted_traceback(self, monkeypatch):
        received = []
        logging_setup.set_crash_callback(lambda text: received.append(text))
        logging_setup.install_excepthook()

        import sys
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())

        assert len(received) == 1
        assert "ValueError: boom" in received[0]
        logging_setup.set_crash_callback(None)
