# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import threading
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
from PySide6.QtCore import QCoreApplication, QObject
from qt.logic import Translator
from qt.updates import Updates
from qt import releases
import update_install


class Backend(QObject):
    def __init__(self, root):
        super().__init__()
        self.settings = {'ui_language': 'en_US', 'game_dir': str(root / 'game')}
        self.t_ = Translator(self.settings)
        self._play_state = 'idle'
        self._jobs = None
        self.quit_called = False

    def _quit_app(self):
        self.quit_called = True


class ControllerTests(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='iss-qt-update-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.port = self.root / 'installed'
        self.port.mkdir()
        (self.port / 'launcher.exe').write_text('old')
        self.payload = self.root / 'package'
        self.payload.mkdir()
        (self.payload / 'launcher.exe').write_text('new')
        self.tag = 'v2026.10.19-abcd123'
        update_install.write_manifest(self.payload, self.tag)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            for p in self.payload.iterdir():
                z.write(p, p.name)
        self.zip = data.getvalue()
        self.backend = Backend(self.port)
        self.handoffs = []
        self.running = False
        self.release = {'tag': self.tag, 'url': releases.RELEASES_URL, 'published': '', 'body': '',
                        'assets': [{'name': 'infamous-windows-x86_64.zip', 'size': len(self.zip),
                                    'url': releases.RELEASE_PREFIX + 'download/v1/test.zip',
                                    'digest': 'sha256:' + hashlib.sha256(self.zip).hexdigest()}]}
        self.u = Updates(self.backend, {'frozen': lambda: True, 'nt': lambda: True,
                    'port_dir': lambda: self.port, 'data_dir': lambda: self.port / 'user',
                    'exe': lambda: 'launcher.exe', 'running': lambda: self.running,
                    'version': lambda: 'v2026.10.18-abcd124', 'save': lambda _: None,
                    'backup': lambda: None, 'handoff': lambda *a: self.handoffs.append(a),
                    'opener': lambda *a, **k: io.BytesIO(self.zip)})
        self.u.release = self.release

    def pump(self, condition):
        end = time.monotonic() + 5
        while not condition() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(condition(), self.u.statusText)

    def test_one_confirmation_download_prepare_and_handoff_preserves_install(self):
        self.assertTrue(self.u.canInstall)
        self.u.install()
        self.assertTrue(self.u.dialog['open'])
        self.u.answer('yes')
        self.pump(lambda: self.backend.quit_called or bool(self.u._error))
        self.assertEqual(self.u._error, '')
        self.assertEqual(len(self.handoffs), 1)
        self.assertEqual((self.port / 'launcher.exe').read_text(), 'old')
        self.assertEqual(update_install._read(self.handoffs[0][0])['target'], str(self.port))
        self.assertFalse(self.u.dialog)

    def test_selected_beta_is_installed_separately_without_handoff(self):
        tag = 'beta-2026.10.23-abcdef1'
        (self.payload / 'VERSION').write_text(tag)
        update_install.write_manifest(self.payload, tag)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            for p in self.payload.iterdir():
                z.write(p, p.name)
        self.zip = data.getvalue()
        asset = dict(self.release['assets'][0], size=len(self.zip),
                     digest='sha256:'+hashlib.sha256(self.zip).hexdigest())
        beta = dict(self.release, tag=tag, beta=True, assets=[asset])
        stable = dict(self.release, tag='v2026.10.18-abcd124', assets=[])
        self.u._on_fetched({'releases': [stable, beta]})
        self.u.selectRelease(1)
        self.backend.playBeta = mock.Mock()
        self.u.downloadAndPlayBeta()
        self.pump(lambda: not self.u.busy)
        self.assertEqual(self.u._error, '')
        self.assertTrue(self.u.selectedBetaInstalled)
        self.assertEqual(self.handoffs, [])
        self.assertEqual((self.port/'launcher.exe').read_text(), 'old')
        self.assertFalse(self.backend.quit_called)
        self.assertFalse(self.u.canInstall)
        self.backend.playBeta.assert_called_once_with(tag)

    def test_busy_and_source_checkout_cannot_install(self):
        self.running = True
        self.assertFalse(self.u.canInstall)
        self.u.install()
        self.assertFalse(self.u.dialog)
        self.running = False
        self.u.probes['frozen'] = lambda: False
        self.assertFalse(self.u.canInstall)

    def test_game_started_after_confirmation_blocks_handoff(self):
        self.u.install()
        self.running = True
        self.u.answer('yes')
        self.pump(lambda: bool(self.u._error))
        self.assertEqual(self.handoffs, [])
        self.assertFalse(self.backend.quit_called)

    def test_wrong_digest_and_missing_protocol_cannot_touch_install(self):
        for digest in ('sha256:' + '0' * 64, ''):
            self.u.release['assets'][0]['digest'] = digest
            self.u.install()
            self.u.answer('yes')
            self.pump(lambda: bool(self.u._error))
            self.assertEqual(self.handoffs, [])
        self.assertEqual((self.port / 'launcher.exe').read_text(), 'old')

    def test_slow_journal_inspection_does_not_block_gui_or_property_reads(self):
        entered, release = threading.Event(), threading.Event()
        state = (self.root / 'transaction.json', {'status': 'confirmed'})
        def slow_pending(_):
            entered.set()
            self.assertTrue(release.wait(3))
            return state
        with mock.patch.object(update_install, 'pending', side_effect=slow_pending) as pending:
            self.u.refreshInstallation()
            self.assertTrue(entered.wait(1))
            try:
                self.assertTrue(self.u.busy)
                for _ in range(100):
                    self.assertFalse(self.u.canRollback)
                    self.app.processEvents()
            finally:
                release.set()
            self.pump(lambda: not self.u.busy)
            self.assertTrue(self.u.canRollback)
            for _ in range(100):
                self.assertTrue(self.u.canRollback)
            pending.assert_called_once()

    def test_save_backup_and_handoff_run_off_gui_thread(self):
        gui_thread = threading.get_ident()
        threads = []
        self.u.probes['backup'] = lambda: threads.append(threading.get_ident())
        def handoff(*args):
            threads.append(threading.get_ident())
            self.handoffs.append(args)
        self.u.probes['handoff'] = handoff
        self.u.install()
        self.u.answer('yes')
        self.pump(lambda: self.backend.quit_called or bool(self.u._error))
        self.assertEqual(self.u._error, '')
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(ident != gui_thread for ident in threads))

    def test_prepare_reports_actual_stage_and_file_count(self):
        self.u._phase = 'prepare'
        self.u._on_install_progress(('verify-package', 3, 10, 'out/runtime.dll'))
        self.assertAlmostEqual(self.u.progress, .3)
        self.assertIn('3/10', self.u.progressText)
        self.assertEqual(self.u.progressDetail, 'out/runtime.dll')
        self.assertFalse(self.u.progressIndeterminate)


if __name__ == '__main__':
    unittest.main()
