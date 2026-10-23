"""Fail a release if the fork's essential DLC and FPS-menu changes disappear."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
checks = {
    'port/scripts/content_profile.py': ('G3CONT02', 'installed_addons'),
    'port/src/probe.c': ('G3CONT02', 'runtime_content_set_addons', 'install_iss_camera_speed', 'install_iss_pitch_safeguard'),
    'port/src/iss_camera_hook.h': ('CUSA00004', 'iss_camera_signature_match'),
    'port/launcher/userdata.py': ('CUSA00004',),
    'port/launcher/savemanager.py': ('SERIALS',),
    'port/src/runtime_content.c': ('runtime_content_set_addons',),
    'port/launcher/infamous_run.py': ('ISS_ADDCONT_DIR', 'camera_build_supported', 'camera_mod_environment', 'ISS_CAMERA_PREVENT_PITCH_SLOWDOWN'),
    'port/src/runtime_pad.c': ('sample_gyro_aim', 'stick_look_axis'),
    'port/launcher/qt/updates.py': ('canInstall', 'update_install.prepare', 'releaseOptions', 'baselineNotes'),
    'port/launcher/update_install.py': ('write_manifest', 'install_lock'),
    'port/launcher/qt/update_progress.py': ('UpdateProgress', 'show_errors=False'),
    'port/launcher/qt/logic.py': ('load_strings_with_fork',),
    'port/launcher/qt/fork_i18n.py': ('fork_strings.json', 'collisions'),
    'port/launcher/qt/i18n/fork_strings.json': ('"strings"', '"overrides"'),
    'port/launcher/qt/qml/UpdateProgress.qml': ('updateJob.timing', 'updateJob.countText'),
    '.github/workflows/fork-release.yml': ('TLG_RENDERER_V2=1 bash build.sh',),
    'port/gpu_v2/gpu/gpu_host.cpp': ('out->gyro_aim', 'out->gyro_focused', 'out->stick_look_sensitivity'),
    'port/gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp': ('UseOnDemandShaderStages', '"TLG_LAZY_PROGRAMS"'),
    'port/launcher/backports_table.py': ('TLG_LAZY_PROGRAMS',),
    'port/launcher/qt/graphics.py': ('TLG_LAZY_PROGRAMS',),
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
