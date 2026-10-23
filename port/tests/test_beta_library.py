"""Side-by-side beta integrity, launch arguments and safe deletion. No game or network."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
from qt import beta_library as library
from qt.releases import UpdateError
import update_install


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stable = self.root / 'stable'
        self.stable.mkdir()
        (self.stable / 'launcher.exe').write_text('stable')
        self.user = self.root / 'shared'
        self.user.mkdir()
        (self.user / 'save.dat').write_text('save')
        self.betas = self.root / 'infamous-betas'
        self.tag = 'beta-2026.10.23-abcdef1'
        self.release = {'tag': self.tag, 'beta': True, 'body': 'Beta notes',
                        'baseline': {'tag': 'v1.0', 'body': 'Stable notes'}}

    def package(self, tag=None, corrupt=False):
        tag = tag or self.tag
        stage = self.root / ('payload-' + tag)
        stage.mkdir(exist_ok=True)
        (stage / 'launcher.exe').write_text('beta')
        (stage / 'VERSION').write_text(tag)
        update_install.write_manifest(stage, tag)
        if corrupt:
            (stage / 'launcher.exe').write_text('corrupted')
        archive = self.root / (tag + '.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            for p in stage.iterdir():
                z.write(p, p.name)
        return archive

    def install(self, **kw):
        return library.install(self.package(**kw), self.betas, self.release, 'launcher.exe')

    def test_two_betas_coexist_stable_and_shared_data_unchanged(self):
        first = self.install()
        tag2 = 'beta-2026.10.24-abcdef2'
        second = library.install(self.package(tag2), self.betas, dict(self.release, tag=tag2), 'launcher.exe')
        self.assertNotEqual(first, second)
        self.assertEqual(len(library.list_installed(self.betas)), 2)
        self.assertEqual((self.stable / 'launcher.exe').read_text(), 'stable')
        self.assertEqual((self.user / 'save.dat').read_text(), 'save')
        self.assertFalse((first / 'user').exists())
        self.assertEqual(library.record(self.betas, self.tag)['release']['baseline']['body'], 'Stable notes')

    def test_installed_beta_is_reused_without_extracting_again(self):
        first = self.install()
        with mock.patch.object(library.updater, 'extract', side_effect=AssertionError('redownload')):
            self.assertEqual(first, library.install(self.root/'missing.zip', self.betas, self.release, 'launcher.exe'))

    def test_corrupt_payload_is_not_registered(self):
        with self.assertRaises(update_install.InstallError):
            self.install(corrupt=True)
        self.assertEqual(library.list_installed(self.betas), [])
        self.assertFalse(library.folder(self.betas, self.tag).exists())

    def test_version_mismatch_is_not_installed(self):
        wrong = self.package('beta-2026.10.24-abcdef2')
        with self.assertRaises(UpdateError):
            library.install(wrong, self.betas, self.release, 'launcher.exe')
        self.assertEqual(library.list_installed(self.betas), [])

    def test_delete_only_selected_beta(self):
        first = self.install()
        library.remove(self.betas, self.tag, self.stable, self.user)
        self.assertFalse(first.exists())
        self.assertEqual((self.user/'save.dat').read_text(), 'save')
        self.assertEqual((self.stable/'launcher.exe').read_text(), 'stable')

    def test_delete_current_or_beta_containing_player_data_is_refused(self):
        first = self.install()
        with self.assertRaises(UpdateError):
            library.remove(self.betas, self.tag, first, self.user)
        (first / 'user').mkdir()
        with self.assertRaises(UpdateError):
            library.remove(self.betas, self.tag, self.stable, self.user)
        self.assertTrue(first.exists())

    def test_unknown_folders_and_traversal_are_refused(self):
        for tag in ('../stable', 'beta-../stable', 'beta-..', '/stable'):
            with self.assertRaises(UpdateError):
                library.folder(self.betas, tag)
        with self.assertRaises(UpdateError):
            library.remove(self.betas, self.tag, self.stable, self.user)

    def test_launch_runs_beta_role_with_shared_data_and_clean_frozen_environment(self):
        first = self.install()
        calls = []
        library.launch(self.betas, self.tag, self.user, first/'session.log',
                       env={'_MEIPASS2': 'old'}, popen=lambda *a, **k: calls.append((a,k)))
        args, kw = calls[0]
        self.assertEqual(args[0], [str(first/'launcher.exe'), '--play'])
        self.assertEqual(kw['cwd'], str(first))
        self.assertEqual(kw['env']['ISS_USER_DIR'], str(self.user))
        self.assertNotIn('_MEIPASS2', kw['env'])
        self.assertEqual(kw['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')


if __name__ == '__main__':
    unittest.main()
