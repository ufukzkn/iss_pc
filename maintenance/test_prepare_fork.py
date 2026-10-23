"""Upstream code is merged, upstream Actions files cannot accidentally require a PAT."""
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import json
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / '.github/scripts/prepare_fork.py'
spec = importlib.util.spec_from_file_location('prepare_fork', source)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

class MergeTests(unittest.TestCase):
    def test_new_workflow_is_excluded_but_source_update_is_kept(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                def git(*args):
                    return subprocess.check_output(['git', *args], text=True, stderr=subprocess.STDOUT).strip()
                git('init', '-b', 'main')
                git('config', 'user.name', 'fixture')
                git('config', 'user.email', 'fixture@example.invalid')
                Path('.github/workflows').mkdir(parents=True)
                Path('.github/workflows/base.yml').write_text('base')
                Path('source.txt').write_text('base')
                git('add', '.'); git('commit', '-m', 'base')
                git('branch', 'upstream')
                Path('.github/workflows/fork.yml').write_text('fork')
                git('add', '.'); git('commit', '-m', 'fork')
                base = git('rev-parse', 'HEAD')
                git('checkout', 'upstream')
                Path('.github/workflows/new-upstream.yml').write_text('new')
                Path('source.txt').write_text('upstream')
                git('add', '.'); git('commit', '-m', 'upstream')
                git('checkout', 'main')
                prepare.merge_release(base, 'upstream')
                self.assertEqual(Path('source.txt').read_text(), 'upstream')
                self.assertTrue(Path('.github/workflows/fork.yml').exists())
                self.assertFalse(Path('.github/workflows/new-upstream.yml').exists())
                self.assertEqual(git('diff', '--name-only', base, 'HEAD', '--', '.github/workflows'), '')
                # Already merged: no fresh commit on every scheduled check.
                current = git('rev-parse', 'HEAD')
                prepare.merge_release(current, 'upstream')
                self.assertEqual(current, git('rev-parse', 'HEAD'))
            finally:
                os.chdir(original)

class ChannelTests(unittest.TestCase):
    def test_missing_upstream_beta_does_not_substitute_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'outputs'
            with patch.dict(os.environ, {'GITHUB_REPOSITORY': prepare.REPO, 'CHANNEL': 'beta',
                                          'GITHUB_OUTPUT': str(output)}), \
                 patch.object(prepare, 'api', side_effect=[{'tag_name': 'v1.0'}, []]), \
                 patch.object(prepare, 'git') as git:
                prepare.main()
            git.assert_not_called()
            self.assertEqual(output.read_text(), 'needed=false\n')

    def test_beta_reuses_its_branch_and_records_exact_stable_baseline(self):
        stable = {'tag_name': 'v1.0'}
        beta = {'tag_name': 'beta-2026.10.23-abcdef1', 'draft': False, 'prerelease': True,
                'body': "BETA header.\n\n## What's new\n- Test change"}
        responses = [stable, [beta], {'name': 'beta'}, []]
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                if args == ('rev-parse', 'HEAD'):
                    return 'forkbase'
                if args[0] == 'rev-parse':
                    return 'abcdef1'
                return ''
            with patch.dict(os.environ, {'GITHUB_REPOSITORY': prepare.REPO, 'CHANNEL': 'beta',
                         'GITHUB_OUTPUT': str(Path(tmp) / 'outputs'), 'RUNNER_TEMP': tmp}), \
                 patch.object(prepare, 'api', side_effect=responses), \
                 patch.object(prepare, 'git', side_effect=git) as git_call, \
                 patch.object(prepare, 'merge_release') as merge:
                prepare.main()
            info = json.loads((Path(tmp) / 'fork-candidate/candidate.json').read_text())
            self.assertEqual(info['channel'], 'beta')
            self.assertTrue(info['version'].startswith('beta-'))
            self.assertEqual(info['stable_tag'], 'v1.0')
            self.assertTrue(info['upstream_notes'].startswith("## What's new"))
            self.assertIn(unittest.mock.call('fetch', '--no-tags', 'origin', 'beta'), git_call.call_args_list)
            self.assertEqual(merge.call_args_list, [unittest.mock.call('forkbase', 'forkbase'),
                              unittest.mock.call('forkbase', 'refs/tags/' + beta['tag_name'])])


if __name__ == '__main__':
    unittest.main()
