"""Fail a release if the fork's essential DLC and FPS-menu changes disappear."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
checks = {
    'port/scripts/content_profile.py': ('G3CONT02', 'installed_addons'),
    'port/src/probe.c': ('G3CONT02', 'runtime_content_set_addons'),
    'port/src/runtime_content.c': ('runtime_content_set_addons',),
    'port/launcher/infamous_run.py': ('ISS_ADDCONT_DIR',),
    'port/src/runtime_pad.c': ('sample_gyro_aim',),
    'port/launcher/qt/updates.py': ('canInstall', 'update_install.prepare'),
    'port/launcher/update_install.py': ('write_manifest', 'install_lock'),
}
for name, tokens in checks.items():
    source = (root / name).read_text(encoding='utf-8')
    for token in tokens:
        assert token in source, f'{name}: missing {token}; inspect upstream integration before releasing'
overlay = (root / 'port/gpu/shim/tlg_overlay.cpp').read_text(encoding='utf-8')
labels = re.search(r'fps_labels\[\]\s*=\s*\{([^}]+)\}', overlay)
assert labels and re.search(r'"30"\s*,\s*"60"\s*,\s*"120"\s*,\s*"240"', labels[1])
assert 'static_assert(std::size(fps_labels) == G::FpsLimits.size())' in overlay
print('DLC preparation/runtime and FPS label safeguards present')
