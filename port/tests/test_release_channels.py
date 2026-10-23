"""Release channel selection and pinned baseline notes; no network or player data."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
from qt import releases, updater
from qt.updates import Updates
from PySide6.QtCore import QCoreApplication, QObject


class FeedTests(unittest.TestCase):
    def item(self, tag, beta=False, **extra):
        return dict(tag_name=tag, prerelease=beta, draft=False, published_at='2026-10-23T12:00:00Z',
                    html_url=releases.UPSTREAM_PREFIX + 'tag/' + tag, **extra)

    def fetch(self, listing, baseline_error=False):
        def open_(request, **kwargs):
            url = request.full_url
            if '?per_page=' in url:
                data = list(listing)
                if not baseline_error:
                    stable = self.item('v1.0', body="## What's new\n- Stable change")
                    stable['published_at'] = '2026-10-22T12:00:00Z'
                    data.append(stable)
            else:
                data = self.item('v2026.10.22-abcdef1')
            return io.BytesIO(json.dumps(data).encode())
        return releases.fetch_catalog(opener=open_)['releases']

    def test_stable_first_drafts_excluded_and_exact_baseline_notes(self):
        draft = self.item('draft', True)
        draft['draft'] = True
        result = self.fetch([self.item('beta-2026.10.23-abcdef2', True, body='Stable baseline: v1.0\n'), draft])
        self.assertFalse(result[0]['beta'])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]['baseline']['tag'], 'v1.0')
        self.assertIn('Stable change', result[1]['baseline']['body'])

    def test_foreign_assets_are_never_installable(self):
        result = self.fetch([self.item('beta-2026.10.23-abcdef2', True,
            assets=[dict(name='infamous-windows-x86_64.zip', size=20,
                         browser_download_url='https://github.com/other/project/releases/download/x/a.zip')])])
        self.assertEqual(result[1]['assets'], [])

    def test_no_beta_keeps_stable_usable(self):
        self.assertEqual(len(self.fetch([])), 1)

    def test_baseline_failure_does_not_hide_beta(self):
        result = self.fetch([self.item('beta-2026.10.23-abcdef2', True, body='Stable baseline: v1.0\n')], True)
        self.assertNotIn('baseline', result[1])

    def test_official_assets_are_beta_only_and_not_an_in_place_stable_update(self):
        link = releases.UPSTREAM_PREFIX + 'download/beta-test/infamous-windows-x86_64.zip'
        result = self.fetch([self.item('beta-2026.10.23-abcdef2', True,
            assets=[dict(name='infamous-windows-x86_64.zip', size=20, browser_download_url=link)])])
        beta = result[1]
        self.assertEqual(beta['source'], 'upstream')
        self.assertEqual(updater.pick_assets(beta, nt=True)[0]['url'], link)
        self.assertTrue(beta['url'].startswith(releases.UPSTREAM_PREFIX))
        with self.assertRaises(releases.UpdateError):
            updater.pick_assets(dict(beta, beta=False), nt=True)

    def test_baseline_excludes_stable_published_after_beta(self):
        future = self.item('v2.0', body='Future stable')
        future['published_at'] = '2026-10-24T12:00:00Z'
        result = self.fetch([self.item('beta-2026.10.23-abcdef2', True), future])
        self.assertEqual(result[1]['baseline']['tag'], 'v1.0')

    def test_beta_tags_are_comparable(self):
        self.assertEqual(releases.parse_version('beta-2026.10.23-abcdef2'), ((2026, 10, 23), 'abcdef2'))
        self.assertEqual(releases.compare('beta-2026.10.23-abcdef2', 'beta-2026.10.23-abcdef2'), 'same')


class Backend(QObject):
    def __init__(self):
        super().__init__()
        self.settings = {}
        self.t_ = lambda key, **fmt: key.format(**fmt)
        self.t_.pt = lambda: False


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.backend = Backend()
        self.current = 'beta-2026.10.23-abcdef2'
        self.u = Updates(self.backend, {'version': lambda: self.current, 'save': lambda _: None})
        self.stable = dict(tag='v2026.10.22-abcdef1', body='Stable fork', url=releases.RELEASES_URL,
                           published='2026-10-22', beta=False, assets=[])
        self.beta = dict(tag=self.current, body="## What's new\n- Beta change", published='2026-10-23',
                         url=releases.RELEASE_PREFIX+'tag/'+self.current, beta=True, assets=[],
                         baseline=dict(tag='v1.0', body="## What's new\n- Stable change"))
        self.u._on_fetched({'releases': [self.stable, self.beta]})

    def test_default_stable_and_return_from_newer_beta(self):
        self.assertEqual(self.u.latest, self.stable['tag'])
        self.assertTrue(self.u.available)
        self.assertEqual(self.u.status(), 'different')
        self.u.selectRelease(1)
        self.assertTrue(self.u.betaSelected)
        self.assertFalse(self.u.available)
        self.assertIn('Beta change', self.u.notes)
        self.assertIn('Stable change', self.u.baselineNotes)
        self.u.selectRelease(0)
        self.assertFalse(self.u.betaSelected)
        self.assertEqual(self.u.baselineNotes, '')

    def test_download_link_matches_selection(self):
        opened = []
        self.u.probes['open_url'] = opened.append
        self.u.selectRelease(1)
        self.u.download()
        self.assertEqual(opened, [self.beta['url']])

    def test_selection_locked_during_download_or_confirmation(self):
        self.u._phase = 'download'
        self.u.selectRelease(1)
        self.assertEqual(self.u.latest, self.stable['tag'])
        self.u._phase = ''
        self.u._dialog = {'open': True}
        self.u.selectRelease(1)
        self.assertEqual(self.u.latest, self.stable['tag'])

    def test_beta_preference_survives_refresh_and_restart(self):
        self.u.selectRelease(1)
        self.u._on_fetched({'releases': [self.stable, self.beta]})
        self.assertTrue(self.u.betaSelected)
        restored = Updates(self.backend, self.u.probes)
        self.assertTrue(restored.betaSelected)

    def test_periodic_beta_check_runs_only_when_six_hours_are_due(self):
        self.u.check = Mock()
        self.backend.settings['beta_last_checked'] = 100000
        with patch('qt.updates.time.time', return_value=100000 + 6*3600 - 1):
            self.u._check_betas_if_due()
        self.u.check.assert_not_called()
        with patch('qt.updates.time.time', return_value=100000 + 6*3600):
            self.u._check_betas_if_due()
        self.u.check.assert_called_once()
        self.u.check.reset_mock()
        self.backend.settings['check_betas_periodically'] = False
        with patch('qt.updates.time.time', return_value=200000):
            self.u._check_betas_if_due()
        self.u.check.assert_not_called()

    def test_failed_check_keeps_selection_and_cached_notes(self):
        self.u.selectRelease(1)
        self.u._on_fetched(releases.UpdateError('offline'))
        self.assertEqual(self.u.latest, self.beta['tag'])
        self.assertIn('Stable change', self.u.baselineNotes)


if __name__ == '__main__':
    unittest.main()
