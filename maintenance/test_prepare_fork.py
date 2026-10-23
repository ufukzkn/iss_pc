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
    def test_beta_cannot_be_built_or_published_by_fork_ci(self):
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': prepare.REPO, 'CHANNEL': 'beta'}), \
             patch.object(prepare, 'api') as api:
            with self.assertRaisesRegex(AssertionError, 'Beta publication is disabled'):
                prepare.main()
        api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
