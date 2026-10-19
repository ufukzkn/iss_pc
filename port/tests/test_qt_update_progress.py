# SPDX-License-Identifier: GPL-2.0-or-later
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
from PySide6.QtCore import QCoreApplication
from qt.logic import Translator
from qt.update_progress import UpdateProgress


class ProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_worker_progress_and_clock_remain_responsive_during_slow_operation(self):
        entered, release = threading.Event(), threading.Event()
        def work(progress):
            progress('apply', 1, 4, 'out/runtime.dll')
            entered.set()
            return 0 if release.wait(3) else 1
        model = UpdateProgress(Translator({'ui_language': 'en_US'}), work)
        model.start()
        self.assertTrue(entered.wait(1))
        try:
            self.app.processEvents()
            self.assertFalse(model.settled)
            self.assertEqual(model.filename, 'out/runtime.dll')
            self.assertEqual(model.fraction, .25)
            self.assertIn('1 / 4', model.countText)
            self.assertIn('Elapsed:', model.timing)
        finally:
            release.set()
        end = time.monotonic() + 3
        while not model.settled and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(model.settled)
        self.assertFalse(model.failed)
        self.assertEqual(model.exit_code, 0)
        model.timer.stop()

    def test_failure_keeps_details_and_unlocks_close(self):
        model = UpdateProgress(Translator({'ui_language': 'en_US'}), lambda _: 1)
        model._progress(('error', 0, 0, 'busy: game is running'))
        model._complete(1)
        self.assertTrue(model.failed)
        self.assertTrue(model.settled)
        self.assertEqual(model.filename, 'busy: game is running')
        self.assertIn('update-error.log', model.hint)
        model.timer.stop()


if __name__ == '__main__':
    unittest.main()
