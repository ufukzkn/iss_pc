# SPDX-License-Identifier: GPL-2.0-or-later
"""Visible Windows helper, loaded from the staged package, never from the live install.

The GUI owns no installation files. Its worker uses the existing journal/locks and
rollback engine. Closing is allowed only after the operation has settled.
"""
from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import update_install
from .logic import Translator, tlg_run


class UpdateProgress(QObject):
    changed = Signal()
    progressed = Signal(object)
    completed = Signal(int)

    def __init__(self, translator, work):
        super().__init__()
        self.t = translator
        self.work = work
        self.phase, self.done, self.total, self.detail = 'check-install', 0, 0, ''
        self.started = self.activity = time.monotonic()
        self.finished = False
        self.exit_code = 1
        self.progressed.connect(self._progress)
        self.completed.connect(self._complete)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.changed)
        self.timer.start()

    def start(self):
        def worker():
            try:
                code = self.work(lambda *event: self.progressed.emit(event))
            except Exception as error:
                self.progressed.emit(('error', 0, 0, str(error)))
                code = 1
            self.completed.emit(code)
        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def _progress(self, event):
        self.phase, self.done, self.total, self.detail = event
        self.activity = time.monotonic()
        self.changed.emit()

    def _complete(self, code):
        self.exit_code, self.finished = code, True
        self.timer.stop()
        if code == 0:
            self.phase, self.detail = 'done', ''
        elif self.phase != 'error':
            self.phase = 'error'
        self.changed.emit()

    @Property(str, notify=changed)
    def heading(self):
        return self.t('upd_phase_' + self.phase)

    @Property(str, notify=changed)
    def filename(self):
        return self.detail

    @Property(float, notify=changed)
    def fraction(self):
        return self.done / self.total if self.total else 0.0

    @Property(bool, notify=changed)
    def indeterminate(self):
        return not self.total and not self.finished

    @Property(bool, notify=changed)
    def settled(self):
        return self.finished

    @Property(bool, notify=changed)
    def failed(self):
        return self.finished and self.exit_code != 0

    @Property(str, notify=changed)
    def countText(self):
        return f'{self.done} / {self.total} ({100 * self.fraction:.0f}%)' if self.total else ''

    @Property(str, notify=changed)
    def timing(self):
        now = time.monotonic()
        return self.t('upd_elapsed', elapsed=int(now - self.started), idle=int(now - self.activity))

    @Property(str, notify=changed)
    def hint(self):
        return self.t('upd_helper_error_hint' if self.failed else 'upd_helper_hint')

    @Property(str, constant=True)
    def closeLabel(self):
        return self.t('upd_helper_close')

    @Property(str, notify=changed)
    def statusLabel(self):
        return self.t('upd_helper_status_error' if self.failed else
                      'upd_helper_status_done' if self.settled else 'upd_helper_status_active')

    @Property(str, notify=changed)
    def detailLabel(self):
        return self.t('upd_helper_details' if self.failed else 'upd_helper_current_file')


def run(transaction, wait_pid, rollback=False):
    app = QGuiApplication.instance() or QGuiApplication([])
    from .app import load_fonts
    display_font, text_font = load_fonts()
    app.setFont(QFont(text_font, 11))
    model = UpdateProgress(Translator(tlg_run.load_settings()),
        lambda progress: update_install.helper(transaction, wait_pid, rollback=rollback,
                                              progress=progress, show_errors=False))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('updateJob', model)
    engine.rootContext().setContextProperty('updateFontDisplay', display_font)
    engine.rootContext().setContextProperty('updateFontText', text_font)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'UpdateProgress.qml')))
    if not engine.rootObjects():
        raise RuntimeError('Unable to open the update progress window; installation has not started')
    def completed(code):
        if code == 0:
            QTimer.singleShot(1000, app.quit)
    model.completed.connect(completed)
    QTimer.singleShot(150, model.start)
    app.exec()
    return model.exit_code
