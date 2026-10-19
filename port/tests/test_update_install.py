# SPDX-License-Identifier: GPL-2.0-or-later
"""Disk-level update/rollback tests; never use the player's installation."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
import update_install as ui


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='iss-update-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'instalação com espaços'
        self.stage = self.root / 'work' / 'payload'
        self.target.mkdir()
        self.stage.mkdir(parents=True)
        for root, version in ((self.target, 'old'), (self.stage, 'new')):
            (root / 'launcher.exe').write_text(version)
            (root / 'out').mkdir()
            (root / 'out' / 'runtime.dll').write_text(version)
        for name in ('user/savedata/slot/dis.dat', 'user/cache/pipeline.bin', 'game/eboot.bin', 'mods/local.txt'):
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('player')
        ui.write_manifest(self.stage, 'new')

    def prepare(self, **kwargs):
        return ui.prepare(self.stage, self.target, 'new', exe_name='launcher.exe', **kwargs)

    def assert_personal(self):
        for name in ('user/savedata/slot/dis.dat', 'user/cache/pipeline.bin', 'game/eboot.bin', 'mods/local.txt'):
            self.assertEqual((self.target / name).read_text(), 'player')

    def test_apply_same_path_and_restore_without_reverting_saves(self):
        tx = self.prepare()
        ui.apply(tx)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'new')
        self.assert_personal()
        (self.target / 'user/savedata/slot/dis.dat').write_text('new progress')
        ui.recover(tx)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')
        self.assertEqual((self.target / 'user/savedata/slot/dis.dat').read_text(), 'new progress')
        ui.recover(tx)  # idempotent

    def test_progress_reports_install_and_recovery_without_changing_journal_safety(self):
        events = []
        tx = ui.prepare(self.stage, self.target, 'new', exe_name='launcher.exe',
                        progress=lambda *event: events.append(event))
        self.assertIn('verify-package', {event[0] for event in events})
        self.assertIn('check-install', {event[0] for event in events})
        events.clear()
        ui.apply(tx, progress=lambda *event: events.append(event))
        done = [event for event in events if event[0] == 'apply']
        self.assertEqual(done[0][1], 0)
        self.assertEqual(done[-1][1:3], (3, 3))
        events.clear()
        ui.recover(tx, progress=lambda *event: events.append(event))
        self.assertEqual(events[-1][0:3], ('recover', 3, 3))
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')
        self.assert_personal()

    def test_transient_windows_lock_retries_journal_and_payload_atomically(self):
        original = ui.os.replace
        for writer in ('journal', 'payload'):
            for code in (5, 32, 33):
                with self.subTest(writer=writer, winerror=code):
                    dest = self.root / 'atomic-target'
                    dest.write_text('old')
                    error = PermissionError('temporary sharing conflict')
                    error.winerror = code
                    def locked_once(source, target):
                        self.assertEqual(dest.read_text(), 'old')
                        raise error
                    calls = 0
                    def attempt(source, target):
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            return locked_once(source, target)
                        return original(source, target)
                    with mock.patch.object(ui.os, 'replace', side_effect=attempt):
                        with mock.patch.object(ui.time, 'sleep'):
                            if writer == 'journal':
                                ui._json(dest, {'new': True})
                            else:
                                ui._copy(self.stage / 'launcher.exe', dest)
                    self.assertEqual(calls, 2)
                    self.assertNotEqual(dest.read_text(), 'old')
                    self.assertFalse(list(self.root.glob('.iss-*')))

    def test_permanent_lock_is_bounded_and_preserves_journal(self):
        dest = self.root / 'atomic-target'
        dest.write_text('old')
        error = PermissionError('persistent lock')
        error.winerror = 5
        with mock.patch.object(ui.os, 'replace', side_effect=error), \
                mock.patch.object(ui.time, 'monotonic', side_effect=[0, 1, 6]), \
                mock.patch.object(ui.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                ui._json(dest, {'new': True})
        self.assertEqual(dest.read_text(), 'old')
        sleep.assert_called_once_with(0.1)
        self.assertFalse(list(self.root.glob('.iss-write-*')))

    def test_unrelated_replace_error_is_not_retried(self):
        with mock.patch.object(ui.os, 'replace', side_effect=OSError('disk failure')), \
                mock.patch.object(ui.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                ui._json(self.root / 'state.json', {})
        sleep.assert_not_called()

    def test_corrupt_payload_refused_before_writing(self):
        (self.stage / 'launcher.exe').write_text('corrupt')
        with self.assertRaises(ui.InstallError):
            self.prepare()
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')

    def test_protected_payload_and_escape_paths_refused(self):
        manifest = json.loads((self.stage / ui.MANIFEST).read_text())
        entry = manifest['files'][0]
        for name in ('../outside', 'user/evil', 'mods/evil', 'game/eboot.bin', 'C:/escape', 'out/a:stream', 'CON', 'out/../evil'):
            with self.subTest(name=name):
                changed = dict(manifest, files=[dict(entry, path=name)])
                (self.stage / ui.MANIFEST).write_text(json.dumps(changed))
                with self.assertRaises(ui.InstallError):
                    self.prepare(protected=(self.target / 'game',))

    def test_modified_old_managed_file_is_not_overwritten(self):
        ui.write_manifest(self.target, 'old', paths=['launcher.exe', 'out/runtime.dll'])
        (self.target / 'launcher.exe').write_text('user change')
        with self.assertRaises(ui.InstallError):
            self.prepare()

    def test_new_file_collision_is_not_overwritten(self):
        ui.write_manifest(self.target, 'old', paths=['launcher.exe', 'out/runtime.dll'])
        (self.stage / 'added.txt').write_text('packaged')
        (self.target / 'added.txt').write_text('personal')
        ui.write_manifest(self.stage, 'new')
        with self.assertRaises(ui.InstallError):
            self.prepare()

    def test_failure_at_every_replace_restores_old_files(self):
        for fail_at in range(3):  # two files and the installed manifest
            with self.subTest(fail_at=fail_at):
                tx = self.prepare()
                def fail(index):
                    if index == fail_at:
                        raise OSError('simulated locked file')
                with self.assertRaises(ui.InstallError):
                    ui.apply(tx, after_replace=fail)
                self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')
                self.assertEqual((self.target / 'out/runtime.dll').read_text(), 'old')
                self.assert_personal()

    def test_process_death_recovery_uses_write_ahead_journal(self):
        tx = self.prepare()
        with self.assertRaises(SystemExit):
            ui.apply(tx, after_replace=lambda _: sys.exit(9))
        ui.recover(tx)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')
        self.assert_personal()

    def test_obsolete_managed_file_removed_and_rollback_restores_it(self):
        (self.target / 'obsolete.dll').write_text('old lib')
        ui.write_manifest(self.target, 'old', paths=['launcher.exe', 'out/runtime.dll', 'obsolete.dll'])
        tx = self.prepare()
        ui.apply(tx)
        self.assertFalse((self.target / 'obsolete.dll').exists())
        ui.recover(tx)
        self.assertEqual((self.target / 'obsolete.dll').read_text(), 'old lib')

    def test_source_checkout_and_missing_space_refused(self):
        (self.target / '.git').mkdir()
        with self.assertRaises(ui.InstallError):
            self.prepare()
        (self.target / '.git').rmdir()
        with mock.patch.object(ui.shutil, 'disk_usage', return_value=mock.Mock(free=0)):
            with self.assertRaises(ui.InstallError):
                self.prepare()

    def test_exclusive_install_lock(self):
        with ui.install_lock(self.target):
            with self.assertRaises(ui.InstallError):
                with ui.install_lock(self.target):
                    pass

    def test_packaged_install_under_project_requires_valid_managed_files(self):
        (self.root / '.git').mkdir()
        with self.assertRaises(ui.InstallError) as error:
            self.prepare()
        self.assertEqual(error.exception.kind, 'source')
        ui.write_manifest(self.target, 'old', paths=['launcher.exe', 'out/runtime.dll'])
        self.prepare()  # Packaged app below a project, not the checkout itself.
        (self.target / 'launcher.exe').write_text('modified')
        with self.assertRaises(ui.InstallError) as error:
            self.prepare()
        self.assertEqual(error.exception.kind, 'conflict')
        (self.target / 'launcher.exe').write_text('old')
        (self.target / '.git').mkdir()
        with self.assertRaises(ui.InstallError) as error:
            self.prepare()
        self.assertEqual(error.exception.kind, 'source')

    def test_change_after_prepare_is_refused(self):
        tx = self.prepare()
        (self.target / 'launcher.exe').write_text('changed after prepare')
        with self.assertRaises(ui.InstallError):
            ui.apply(tx)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'changed after prepare')

    def test_second_update_keeps_previous_snapshot_and_rolls_back_to_the_previous(self):
        first = self.prepare()
        ui.apply(first)
        ui.confirm(self.target)
        second = self.root / '.iss-update-b' / 'payload'
        second.mkdir(parents=True)
        (second / 'launcher.exe').write_text('newer')
        (second / 'out').mkdir()
        (second / 'out' / 'runtime.dll').write_text('newer')
        ui.write_manifest(second, 'newer')
        tx = ui.prepare(second, self.target, 'newer', exe_name='launcher.exe')
        ui.apply(tx)
        ui.confirm(self.target)
        self.assertTrue(first.parent.exists())  # keep one previous confirmed snapshot
        (self.target / 'user/savedata/slot/dis.dat').write_text('progress after update')
        ui.recover(tx)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'new')
        self.assertEqual((self.target / 'user/savedata/slot/dis.dat').read_text(), 'progress after update')

    def test_external_game_and_data_are_byte_identical_after_apply(self):
        game, data = self.root / 'jogo externo', self.root / 'dados externos'
        for folder in (game, data):
            folder.mkdir()
            (folder / 'eboot.bin').write_text('game')
            (folder / 'slot.dat').write_text('save')
        before = {p: ui._hash(p) for p in (*game.rglob('*'), *data.rglob('*')) if p.is_file()}
        ui.apply(self.prepare(protected=(game, data)))
        after = {p: ui._hash(p) for p in (*game.rglob('*'), *data.rglob('*')) if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'new')

    def test_missing_completed_update_folder_does_not_block_startup(self):
        for status in ('installed', 'confirmed', 'rolled_back'):
            with self.subTest(status=status):
                self.stage.mkdir(parents=True, exist_ok=True)
                (self.stage / 'launcher.exe').write_text('new')
                ui.write_manifest(self.stage, 'new')
                tx = self.prepare()
                ui.apply(tx)
                if status == 'confirmed':
                    ui.confirm(self.target)
                elif status == 'rolled_back':
                    ui.recover(tx)
                shutil.rmtree(tx.parent)
                self.assertIsNone(ui.pending(self.target))
                self.assertFalse((self.target / ui.STATE).exists())
                self.assert_personal()

    def test_missing_interrupted_update_journal_is_not_treated_as_success(self):
        tx = self.prepare()
        with self.assertRaises(SystemExit):
            ui.apply(tx, after_replace=lambda _: sys.exit(9))
        shutil.rmtree(tx.parent)
        with self.assertRaises(ui.InstallError) as error:
            ui.pending(self.target)
        self.assertEqual(error.exception.kind, 'recovery')
        self.assertTrue((self.target / ui.STATE).exists())

    def test_missing_completed_journal_requires_matching_installed_files(self):
        tx = self.prepare()
        ui.apply(tx)
        shutil.rmtree(tx.parent)
        (self.target / 'launcher.exe').write_text('damaged')
        with self.assertRaises(ui.InstallError):
            ui.pending(self.target)
        self.assertTrue((self.target / ui.STATE).exists())

    def test_interrupted_state_records_operations_before_first_replacement(self):
        tx = self.prepare()
        seen = []
        def capture(index):
            seen.append(json.loads((self.target / ui.STATE).read_text(encoding='utf-8')))
            raise SystemExit(9)
        with self.assertRaises(SystemExit):
            ui.apply(tx, after_replace=capture)
        journal = json.loads(tx.read_text(encoding='utf-8'))['operations']
        self.assertEqual(seen[0]['operations'], [{key: row[key] for key in ('path', 'before', 'after', 'size')}
                                                 for row in journal])
        self.assertEqual(seen[0]['target'], str(self.target.resolve()))
        self.assertIn('transaction', seen[0])

    def test_interrupted_update_without_journal_before_any_replacement_is_old_version(self):
        tx = self.prepare()
        with mock.patch.object(ui, '_copy', side_effect=SystemExit(9)):  # first call backs up the first file
            with self.assertRaises(SystemExit):
                ui.apply(tx)
        self.assertTrue((self.target / ui.STATE).exists())
        shutil.rmtree(tx.parent)
        self.assertIsNone(ui.pending(self.target))
        self.assertFalse((self.target / ui.STATE).exists())
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'old')
        self.assertEqual((self.target / 'out/runtime.dll').read_text(), 'old')
        self.assert_personal()

    def test_interrupted_update_without_journal_after_all_replacements_is_new_version(self):
        tx = self.prepare()
        last = len(json.loads(tx.read_text(encoding='utf-8'))['operations']) - 1
        with self.assertRaises(SystemExit):  # only the final state write is lost
            ui.apply(tx, after_replace=lambda index: sys.exit(9) if index == last else None)
        shutil.rmtree(tx.parent)
        self.assertIsNone(ui.pending(self.target))
        self.assertFalse((self.target / ui.STATE).exists())
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'new')
        self.assertEqual((self.target / 'out/runtime.dll').read_text(), 'new')
        self.assert_personal()

    def test_interrupted_update_without_journal_mixed_versions_keeps_state_file(self):
        tx = self.prepare()
        before_manifest = len(json.loads(tx.read_text(encoding='utf-8'))['operations']) - 2
        with self.assertRaises(SystemExit):  # content replaced, installed manifest still old
            ui.apply(tx, after_replace=lambda index: sys.exit(9) if index == before_manifest else None)
        shutil.rmtree(tx.parent)
        with self.assertRaises(ui.InstallError) as error:
            ui.pending(self.target)
        self.assertEqual(error.exception.kind, 'recovery')
        self.assertTrue((self.target / ui.STATE).exists())
        self.assertEqual((self.target / 'launcher.exe').read_text(), 'new')

    def test_prune_preserves_other_installations_and_unfinished_updates(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'launcher.exe').write_text('old')
        for name, target, confirm in (('other', other, True), ('unfinished', self.target, False),
                                      ('old', self.target, True)):
            stage = self.root / ('.iss-update-' + name) / 'payload'
            shutil.copytree(self.stage, stage)
            tx = ui.prepare(stage, target, 'new', exe_name='launcher.exe')
            if confirm:
                ui.apply(tx)
                ui.confirm(target)
        ui._prune(self.root / 'keep', self.target)
        self.assertTrue((self.root / '.iss-update-other').is_dir())
        self.assertTrue((self.root / '.iss-update-unfinished').is_dir())
        self.assertTrue((self.root / '.iss-update-old').exists())  # fewer than two eligible snapshots

    def test_prune_keeps_active_and_one_previous_confirmed_snapshot(self):
        snapshots = []
        for index in range(4):
            stage = self.root / ('.iss-update-snapshot-' + str(index)) / 'payload'
            shutil.copytree(self.stage, stage)
            tx = ui.prepare(stage, self.target, 'new', exe_name='launcher.exe')
            data = json.loads(tx.read_text(encoding='utf-8'))
            data['status'] = 'confirmed'
            ui._json(tx, data)
            os.utime(tx, ns=(index + 1, index + 1))
            snapshots.append(tx.parent)
        ui._prune(snapshots[0], self.target)  # active snapshot has the oldest timestamp
        self.assertEqual([p.exists() for p in snapshots], [True, False, False, True])
        ui._prune(snapshots[0], self.target)
        self.assertEqual([p.exists() for p in snapshots], [True, False, False, True])

    def test_prune_preserves_rolled_back_and_malformed_transactions(self):
        stage = self.root / '.iss-update-rollback' / 'payload'
        shutil.copytree(self.stage, stage)
        tx = ui.prepare(stage, self.target, 'new', exe_name='launcher.exe')
        ui.apply(tx)
        ui.recover(tx)
        malformed = self.root / '.iss-update-malformed'
        malformed.mkdir()
        (malformed / 'transaction.json').write_text('{invalid')
        ui._prune(self.root / 'keep', self.target)
        self.assertTrue(tx.parent.exists())
        self.assertTrue(malformed.exists())


if __name__ == '__main__':
    unittest.main()
