"""Development synchronization never publishes over the stable channel."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, call

scripts = Path(__file__).resolve().parents[1] / '.github/scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('prepare_beta', scripts / 'prepare_beta.py')
beta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(beta)


class PrepareBetaTests(unittest.TestCase):
    def prepare(self, built=False, conflict=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        hashes = iter(['main-sha', 'previous-beta-sha', 'candidate-sha'])
        def git(*args):
            if args == ('rev-parse', 'HEAD'):
                return next(hashes)
            if args == ('rev-parse', 'FETCH_HEAD'):
                return 'developer-sha'
            if args == ('remote',):
                return 'origin\nupstream'
            return ''
        def api(path, missing=False):
            if path.endswith('/branches/beta'):
                return {'name': 'beta'}
            if path.endswith('/releases/latest'):
                return {'tag_name': 'stable-version'}
            return [{'prerelease': True, 'draft': False, 'tag_name': 'beta-fork-existing',
                     'target_commitish': 'candidate-sha'}] if built else []
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': beta.REPO, 'RUNNER_TEMP': str(directory),
                                     'GITHUB_OUTPUT': str(directory / 'output'), 'FORCE': 'false'}), \
             patch.object(beta, 'git', side_effect=git) as commands, \
             patch.object(beta, 'api', side_effect=api), \
             patch.object(beta, 'merge_release', side_effect=RuntimeError('source conflict') if conflict else None) as merge:
            if conflict:
                with self.assertRaisesRegex(RuntimeError, 'source conflict'):
                    beta.main()
                self.assertFalse((directory / 'fork-candidate').exists())
                return
            beta.main()
        result = json.loads((directory / 'fork-candidate/candidate.json').read_text())
        return result, commands, merge

    def test_merge_main_and_developer_preserves_beta_ancestry(self):
        result, commands, merge = self.prepare()
        self.assertEqual(merge.call_args_list, [call('main-sha', 'main-sha'), call('main-sha', 'developer-sha')])
        self.assertEqual(result['beta_base_commit'], 'previous-beta-sha')
        self.assertEqual(result['base_commit'], 'main-sha')
        self.assertEqual(result['stable_tag'], 'stable-version')
        self.assertTrue(result['version'].startswith('beta-fork-'))
        self.assertTrue(result['needed'])

    def test_unchanged_published_beta_does_not_rebuild(self):
        result, commands, _ = self.prepare(built=True)
        self.assertFalse(result['needed'])
        self.assertFalse(any(c.args[:2] == ('bundle', 'create') for c in commands.call_args_list))

    def test_source_conflict_stops_before_export(self):
        self.prepare(conflict=True)


if __name__ == '__main__':
    unittest.main()
