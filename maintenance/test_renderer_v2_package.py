"""A release must carry both runnable renderer backends, not just their source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def package(self, folder, include_v2):
        archive = folder / 'infamous-windows-x86_64.zip'
        files = {'out/tlg-probe.exe': b'v1', 'gpu_v2/defaults.env': b'ISS_NATIVE_PASSES=1\n'}
        if include_v2:
            files['out/tlg-probe-v2.exe'] = b'v2'
        with zipfile.ZipFile(archive, 'w') as z:
            for name, data in files.items():
                z.writestr('infamous-windows-x86_64/' + name, data)
        candidate = folder / 'candidate.json'
        candidate.write_text(json.dumps({'repository': 'ufukzkn/iss_pc', 'version': 'fixture'}))
        return archive, candidate

    def test_missing_v2_refused_without_rewriting_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, candidate = self.package(Path(tmp), False)
            before = archive.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / 'maintenance/package_fork.py'),
                                     str(archive), str(candidate)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'out/tlg-probe-v2.exe', result.stderr)
            self.assertEqual(archive.read_bytes(), before)

    def test_both_renderers_are_hashed_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, candidate = self.package(Path(tmp), True)
            subprocess.run([sys.executable, str(ROOT / 'maintenance/package_fork.py'),
                            str(archive), str(candidate)], check=True, capture_output=True)
            with zipfile.ZipFile(archive) as z:
                prefix = 'infamous-windows-x86_64/'
                info = json.loads(z.read(prefix + 'FORK-BUILD.json'))
                self.assertIn('renderer-v2', info['features'])
                manifest = json.loads(z.read(prefix + 'package-files.json'))
                rows = {row['path']: row for row in manifest['files']}
                for name in ('out/tlg-probe.exe', 'out/tlg-probe-v2.exe', 'gpu_v2/defaults.env'):
                    self.assertEqual(rows[name]['sha256'], hashlib.sha256(z.read(prefix + name)).hexdigest())


if __name__ == '__main__':
    unittest.main()
