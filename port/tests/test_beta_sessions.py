"""Single-click beta session handoff without launching a game."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

LAUNCHER = Path(__file__).resolve().parents[1] / 'launcher'
sys.path.insert(0, str(LAUNCHER))
from qt.backend import Backend


class SessionTests(unittest.TestCase):
    def test_controller_runs_beta_and_follows_native_log_after_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tag = 'beta-2026.10.23-abcdef1'
            (root/tag).mkdir()
            process = mock.Mock()
            process.poll.side_effect = [None, 0]
            process.wait.return_value = 0
            fake = SimpleNamespace(updates=SimpleNamespace(library_dir=lambda: root,
                         data_dir=lambda: root/'shared', probes={'running': lambda: False}),
                         process=None, _play_state='launching', lineReceived=mock.Mock(),
                         stateChanged=mock.Mock(), gameStarted=mock.Mock(), finished=mock.Mock())
            def launch(*args):
                (root/tag/'session.log').write_text('Preparing shaders\n__ISS_GAME_LOG__=native.log\n', encoding='utf-8')
                return process
            with mock.patch('qt.backend.beta_library.launch', side_effect=launch) as start, \
                 mock.patch('qt.backend.time.sleep'):
                Backend._run_beta(fake, tag)
            self.assertEqual(start.call_args.args[1], tag)
            self.assertEqual(start.call_args.args[2], root/'shared')
            fake.lineReceived.emit.assert_called_with('Preparing shaders')
            fake.gameStarted.emit.assert_called_once_with('native.log')
            fake.finished.emit.assert_called_once_with(0)
            self.assertIsNone(fake.process)

    def test_windowless_play_role_supplies_streams_and_reports_native_log(self):
        spec = importlib.util.spec_from_file_location('beta_role_test', LAUNCHER/'infamous_launcher_qt.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp)/'session.log'
            def main(args):
                print('Preparing shaders', flush=True)
                module.tlg_run.launch({})
                return 0
            with mock.patch.dict(os.environ, {'ISS_BETA_SESSION_LOG': str(log)}), \
                 mock.patch.object(sys, 'argv', ['launcher', '--play']), \
                 mock.patch.object(module.multiprocessing, 'freeze_support'), \
                 mock.patch.object(module.tlg_run, 'launch', return_value=(object(), 'native.log')), \
                 mock.patch.object(module.tlg_run, 'main', side_effect=main), \
                 mock.patch.object(sys, 'stdout', None), mock.patch.object(sys, 'stderr', None):
                try:
                    with self.assertRaises(SystemExit) as result:
                        module.main()
                    self.assertEqual(result.exception.code, 0)
                finally:
                    if sys.stdout:
                        sys.stdout.close()
            text = log.read_text(encoding='utf-8')
            self.assertIn('Preparing shaders', text)
            self.assertIn('__ISS_GAME_LOG__=native.log', text)


if __name__ == '__main__':
    unittest.main()
