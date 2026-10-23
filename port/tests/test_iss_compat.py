"""Cross-region XML selection and compiled writes use executable identity, not package labels."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import subprocess
import unittest
from unittest import mock

from paths import ROOT
sys.path[:0] = [str(ROOT / 'launcher'), str(ROOT / 'scripts')]
import iss_compat as compat
import infamous_patches as patches
import infamous_run as run
from qt import report
import preset_share


def sfo(values):
    keys, data, rows = bytearray(), bytearray(), bytearray()
    for key, value in values.items():
        encoded = value.encode() + b'\0'
        rows += struct.pack('<HHIII', len(keys), 0x204, len(encoded), len(encoded), len(data))
        keys += key.encode() + b'\0'
        data += encoded
    return struct.pack('<4sIIII', b'\0PSF', 0x101, 20 + len(rows), 20 + len(rows) + len(keys), len(values)) + rows + keys + data


def elf():
    data = bytearray(4096)
    data[:4] = b'\x7fELF'
    struct.pack_into('<Q', data, 0x20, 64)
    struct.pack_into('<HH', data, 0x36, 56, 1)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), 4096)
    return bytes(data)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        (self.game / 'sce_sys').mkdir(parents=True)
        (self.game / 'eboot.bin').write_bytes(elf())
        self.moddir = self.root / 'mods'
        self.moddir.mkdir()
        self.out = self.root / 'out'
        self.out.mkdir()
        self.config = self.root / 'mods.json'
        self.config.write_text('{}')
        patch = mock.patch.object(compat, 'ELF_107_SHA256', hashlib.sha256(elf()).hexdigest())
        patch.start()
        self.addCleanup(patch.stop)
        compat._digest.cache_clear()

    def metadata(self, title='CUSA00004', app='01.00', version='01.07'):
        data = sfo({'TITLE_ID': title, 'APP_VER': app, 'VERSION': version})
        (self.game / 'sce_sys/param.sfo').write_bytes(data)
        return data

    def mod(self, filename, title, app, offset):
        (self.moddir / filename).write_text(f'<PATCHES><ID>{title}</ID><Metadata Name="Example" AppVer="{app}" AppElf="eboot.bin" isEnabled="true"><PatchList><Line Type="bytes" Address="{0x400000 + offset:#x}" Value="1122"/></PatchList></Metadata></PATCHES>')

    def test_both_regions_and_old_metadata_identify_the_same_build_without_rewriting(self):
        for title in sorted(compat.TITLE_IDS):
            for app in ('01.00', '01.07'):
                before = self.metadata(title, app)
                build = compat.identify(self.game)
                self.assertTrue(build.verified_107)
                self.assertEqual(build.effective_app_version, '01.07')
                self.assertEqual(build.mod_title_ids, compat.TITLE_IDS)
                self.assertEqual(build.metadata_app_version, app)
                self.assertEqual((self.game / 'sce_sys/param.sfo').read_bytes(), before)

    def test_version_string_alone_does_not_authorize_aliases(self):
        self.metadata()
        (self.game / 'eboot.bin').write_bytes(elf() + b'different build')
        build = compat.identify(self.game)
        self.assertFalse(build.verified_107)
        self.assertEqual(build.effective_app_version, '01.00')
        self.assertEqual(build.mod_title_ids, {'CUSA00004'})

    def test_unknown_title_and_unsupported_metadata_do_not_inherit_support(self):
        for title, app in [('CUSA99999', '01.07'), ('CUSA00004', '01.06')]:
            self.metadata(title, app)
            build = compat.identify(self.game)
            self.assertFalse(build.verified_107)
            self.assertEqual(build.effective_app_version, app)
            self.assertNotEqual(build.mod_title_ids, compat.TITLE_IDS)

    def test_missing_and_broken_files_fail_closed(self):
        self.assertEqual(compat.identify(self.game).mod_title_ids, set())
        self.metadata()
        (self.game / 'eboot.bin').unlink()
        self.assertFalse(compat.identify(self.game).verified_107)
        (self.game / 'sce_sys/param.sfo').write_bytes(b'broken')
        self.assertEqual(compat.identify(self.game).mod_title_ids, set())

    def test_eboot_change_invalidates_cached_identity(self):
        self.metadata()
        self.assertTrue(compat.identify(self.game).verified_107)
        (self.game / 'eboot.bin').write_bytes(elf() + b'changed')
        self.assertFalse(compat.identify(self.game).verified_107)

    def test_self_and_plain_elf_have_the_same_identity(self):
        self.metadata()
        (self.game / 'eboot.bin').write_bytes(compat.SELF_MAGIC + b'fixture')
        with mock.patch('prepare.parse_self', return_value=(elf(),)):
            self.assertTrue(compat.identify(self.game).verified_107)

    def test_launcher_and_compiler_select_and_apply_the_same_cross_region_mods(self):
        self.mod('us.xml', 'CUSA00223', '01.07', 256)
        self.mod('eu.xml', 'CUSA00004', '01.07', 260)
        self.mod('old.xml', 'CUSA00223', '01.00', 264)
        self.mod('other.xml', 'CUSA99999', '01.07', 268)
        for title in sorted(compat.TITLE_IDS):
            self.metadata(title)
            with mock.patch.object(run, 'mods_dir', return_value=self.moddir), mock.patch.object(run, 'mods_config', return_value=self.config):
                rows = run.list_mods({'game_dir': str(self.game)})
            self.assertEqual({r[0] for r in rows}, {'us.xml/Example', 'eu.xml/Example', run.CAMERA_MOD_KEY, 'iss_builtin_intro.xml/Skip intro movie'})
            lines = patches.prepare(self.game, self.out, self.moddir, self.config)
            data = (self.out / 'patches.bin').read_bytes()
            self.assertEqual(struct.unpack_from('<8sQQ', data), (b'G3PATCH2', 0, 2))
            expected = struct.pack('<8sQQ', b'G3PATCH2', 0, 2) + b''.join(struct.pack('<QQ', offset, 2) + bytes.fromhex('1122') for offset in (260, 256))
            self.assertEqual(data, expected)
            self.assertTrue(any('verified 1.07' in line for line in lines))

    def test_unverified_build_only_gets_own_region_and_raw_version_mods(self):
        self.metadata(app='01.07')
        (self.game / 'eboot.bin').write_bytes(elf() + b'unknown')
        self.mod('us.xml', 'CUSA00223', '01.07', 256)
        self.mod('eu.xml', 'CUSA00004', '01.07', 260)
        patches.prepare(self.game, self.out, self.moddir, self.config)
        self.assertEqual(struct.unpack_from('<8sQQ', (self.out / 'patches.bin').read_bytes())[2], 1)

    def test_legacy_patch_cli_routes_both_regions_to_the_same_compiler(self):
        self.metadata(app='01.07')
        self.mod('eu.xml', 'CUSA00004', '01.07', 260)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/patches.py'), '--game-dir', str(self.game), '--out', str(self.out), '--patches-dir', str(self.moddir)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(struct.unpack_from('<8sQQ', (self.out / 'patches.bin').read_bytes())[2], 1)

    def test_report_and_launch_env_use_verified_version_with_raw_metadata_retained(self):
        self.metadata()
        from prepare import sfo as read_sfo
        self.assertEqual(report.sfo_game(self.game, read_sfo), ('CUSA00004', '01.07'))
        settings = dict(run.DEFAULT_SETTINGS, game_dir=str(self.game))
        with mock.patch.dict(os.environ, {'ISS_USER_DIR': str(self.root / 'user'), 'ISS_VERIFIED_APP_VER': '99.99'}):
            self.assertEqual(run.build_env(settings)['ISS_VERIFIED_APP_VER'], '01.07')
            (self.game / 'eboot.bin').write_bytes(elf() + b'unknown')
            self.assertNotIn('ISS_VERIFIED_APP_VER', run.build_env(settings))

    def test_both_region_preset_headers_are_accepted(self):
        for title in sorted(compat.TITLE_IDS):
            data = preset_share.export_preset(run.DEFAULT_SETTINGS, {})
            data['game'] = title
            path = self.root / 'preset.json'
            path.write_text(json.dumps(data))
            _, problems = preset_share.read_preset(path)
            self.assertFalse(any(p.code == 'game' for p in problems))


if __name__ == '__main__':
    unittest.main()
