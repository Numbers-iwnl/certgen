"""
Background workers. Qt's signal/slot mechanism marshals cross-thread
calls safely by default (a signal emitted from a QThread.run() body is
delivered to the main thread's slots via a queued connection) -- this is
what makes baseline Known Issue #3 (Tk variables read from a worker
thread) structurally impossible here rather than something to remember
not to do.
"""
from PySide6.QtCore import QThread, Signal

from certgen.generate import GenerationEngine, GenerationResult
from certgen.mailer import send_batch


class GenerationWorker(QThread):
    progress = Signal(int, int)
    log = Signal(str)
    finished_ok = Signal(object)  # GenerationResult
    failed = Signal(str)

    def __init__(self, engine: GenerationEngine, records, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.records = records
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result: GenerationResult = self.engine.run(
                self.records,
                progress_cb=lambda done, total: self.progress.emit(done, total),
                log_cb=lambda msg: self.log.emit(msg),
                is_cancelled=lambda: self._cancelled,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class EmailWorker(QThread):
    row_result = Signal(dict, str, str)  # row, status ("ok"/"falha"/"ignorado"), message
    log = Signal(str)
    finished_ok = Signal(dict)  # summary dict from send_batch
    failed = Signal(str)

    def __init__(self, send_kwargs: dict, parent=None):
        super().__init__(parent)
        self.send_kwargs = send_kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            summary = send_batch(
                on_row=lambda row, status, msg: self.row_result.emit(row, status, msg),
                logger=lambda msg: self.log.emit(msg),
                is_cancelled=lambda: self._cancelled,
                **self.send_kwargs,
            )
            self.finished_ok.emit(summary)
        except Exception as e:
            self.failed.emit(str(e))
