"""Upstream translation changes and fork-only text coexist without editing one JSON file."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
from qt.fork_i18n import load_strings_with_fork


class ForkTranslationTests(unittest.TestCase):
    def test_upstream_new_key_and_changed_text_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / 'strings.json'
            base.write_text(json.dumps({'upstream': {'en': 'New upstream text', 'pt': 'Novo'},
                                        'new_key': {'en': 'New feature', 'pt': 'Recurso'},
                                        'link': {'en': 'Release page', 'pt': 'Release'}}))
            (root / 'fork_strings.json').write_text(json.dumps({
                'strings': {'fork_progress': {'en': 'Installing', 'pt': 'Instalando'}},
                'overrides': {'link': {'en': 'Latest release', 'pt': 'Release atual'}}}))
            result = load_strings_with_fork(base)
            self.assertEqual(result['upstream']['en'], 'New upstream text')
            self.assertIn('new_key', result)
            self.assertEqual(result['fork_progress']['en'], 'Installing')
            self.assertEqual(result['link']['en'], 'Latest release')

    def test_collision_fails_instead_of_silently_masking_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'strings.json').write_text(json.dumps({'same': {'en': 'Base', 'pt': 'Base'}}))
            (root / 'fork_strings.json').write_text(json.dumps({
                'strings': {'same': {'en': 'Fork', 'pt': 'Fork'}}, 'overrides': {}}))
            with self.assertRaisesRegex(ValueError, 'collision'):
                load_strings_with_fork(root / 'strings.json')

    def test_optional_overlay_preserves_upstream_loader_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'strings.json'
            base.write_text('{"fixture": {"en": "A", "pt": "B"}}')
            self.assertEqual(load_strings_with_fork(base)['fixture']['en'], 'A')


if __name__ == '__main__':
    unittest.main()
