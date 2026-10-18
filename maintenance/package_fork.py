"""Add provenance, updater and per-file hashes to a source-free player package."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('package', type=Path)
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
info = json.loads(args.candidate.read_text(encoding='utf-8-sig'))
assert info['repository'] == 'ufukzkn/iss_pc'
with zipfile.ZipFile(args.package) as archive:
    entries = {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}
prefix = 'infamous-windows-x86_64/'
assert all(name.startswith(prefix) for name in entries)
for name in ('Update-inFAMOUS.ps1', 'Update-inFAMOUS.cmd'):
    entries[prefix + name] = (root / 'maintenance' / name).read_bytes()
entries[prefix + 'FORK-README.md'] = (root / 'FORK-README.md').read_bytes()
entries[prefix + 'VERSION'] = (info['version'] + '\n').encode()
manifest = dict(info, schema=1, features=['dlc-unlockers', 'fps-menu-labels'],
                dlc_author='BeastBoyyy', dlc_pr='https://github.com/HayatoG/iss_pc/pull/249',
                files={name[len(prefix):]: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())})
entries[prefix + 'FORK-BUILD.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
with zipfile.ZipFile(args.package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name, data in entries.items():
        archive.writestr(name, data)
digest = hashlib.sha256(args.package.read_bytes()).hexdigest()
args.package.with_suffix(args.package.suffix + '.sha256').write_text(f'{digest}  {args.package.name}\n', encoding='ascii')
print(json.dumps({'package': str(args.package), 'files': len(entries), 'sha256': digest}))
