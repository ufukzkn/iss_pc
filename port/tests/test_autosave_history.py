"""Native rotation plus safe launcher restoration of a single historical autosave."""
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest import mock
from paths import ROOT
sys.path.insert(0, str(ROOT / 'launcher'))
import savemanager as sm


class AutosaveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.user = Path(self.temp.name)
        self.entry = self.user / 'autosave_history/1/CUSA00004/entry-00000000000000000001'
        self.entry.mkdir(parents=True)
        (self.entry / 'dis.dat').write_bytes(b'x' * 131072)
        (self.entry / 'param.bin').write_bytes(bytes(1328))
        (self.entry / 'slot.txt').write_text('infamousssAuto1\n')

    def test_restore_preserves_live_saves_and_makes_new_manual_slot(self):
        game = self.user / 'savedata/1/CUSA00004'
        for slot in ('infamousssAuto1', 'infamousssUser0'):
            (game / slot).mkdir(parents=True)
            (game / slot / 'dis.dat').write_bytes(b'keep')
        history = [b for b in sm.list_backups(self.user) if b['name'].startswith('autosave-history/')]
        self.assertEqual(len(history), 1)
        with mock.patch.object(sm, 'prefs', return_value={'keep': 10, 'extra': ''}):
            sm.restore_backup(self.user, history[0]['name'], running=lambda: False)
        self.assertEqual((game / 'infamousssAuto1/dis.dat').read_bytes(), b'keep')
        self.assertEqual((game / 'infamousssUser0/dis.dat').read_bytes(), b'keep')
        self.assertEqual((game / 'infamousssUser1/dis.dat').read_bytes(), b'x' * 131072)
        self.assertTrue(sm.save_backup.list_backups(self.user))

    def test_running_game_and_traversal_are_refused(self):
        name = sm._autosave_history(self.user)[0]['name']
        with self.assertRaises(sm.SaveError):
            sm.restore_backup(self.user, name, running=lambda: True)
        with self.assertRaises(sm.SaveError):
            sm.restore_backup(self.user, 'autosave-history/../CUSA00004/entry-00000000000000000001', running=lambda: False)
        self.assertTrue(sm.game_running(lambda: ['tlg-probe-v2.exe']))

    def test_incomplete_and_staging_snapshots_are_not_offered(self):
        (self.entry / 'param.bin').write_bytes(b'broken')
        self.assertEqual(sm._autosave_history(self.user), [])
        self.entry.rename(self.entry.with_name('.pending-00000000000000000001'))
        self.assertEqual(sm._autosave_history(self.user), [])

    def test_native_capture_contract(self):
        binary = ROOT / 'out' / ('autosave-history-test.exe' if sys.platform == 'win32' else 'autosave-history-test')
        if not binary.exists():
            self.skipTest('build the native autosave-history-test target first')
        native = self.user / 'native'
        native.mkdir()
        run = subprocess.run([str(binary), str(native)], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
