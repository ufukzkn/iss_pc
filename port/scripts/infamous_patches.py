#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""inFAMOUS Second Son community mods/cheats, written to out/patches.bin.

Reads shadPS4/GoldHEN cheat XML files the player drops in the mods folder (mod_patches.py:
scoped by title ID and app version, checked against the eboot's own segments) and compiles
them into the G3PATCH2 format the loader (probe.c apply_patches) already applies. Nothing in
the mods folder has any effect until it is enabled (the file's own isEnabled="true", or
mods.json): with nothing enabled this writes an empty patch file, the game unaffected.

No built-in patches yet (unlike tlg_pc's frame rate ones): this only carries mods.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mod_patches

from iss_compat import TITLE_IDS, identify, read_eboot_elf
BUILTIN_MODS = (Path(__file__).resolve().parent.parent / 'patches' / 'iss_builtin_intro.xml',)


def write_patch_file(path, writes):
    """G3PATCH2 (probe.c apply_patches): base 0 (no pointer slots), then (offset, length, bytes)."""
    blob = struct.pack('<8sQQ', b'G3PATCH2', 0, len(writes))
    for offset, data, _ in writes:
        blob += struct.pack('<QQ', offset, len(data)) + data
    Path(path).write_bytes(blob)


def prepare(game_dir, out_dir, mods_dir=None, mods_config=None):
    """Writes out/patches.bin from whatever mods are enabled; returns the log lines."""
    lines = []
    writes = []
    if mods_dir:
        eboot = read_eboot_elf(game_dir)
        if eboot is None:
            lines.append('Mods: cannot read eboot.bin: not applied')
        else:
            try:
                segments = mod_patches.eboot_segments(eboot)
                build = identify(game_dir, elf=eboot)
                app_version = build.effective_app_version
                found = mod_patches.external_patches(
                    mods_dir, app_version, build.mod_title_ids, builtin_files=BUILTIN_MODS)
                if build.verified_107 and build.metadata_app_version != app_version:
                    lines.append(f'Mods: verified 1.07 executable; metadata APP_VER {build.metadata_app_version} retained')
                selected = mod_patches.external_selection(found, mods_config)
                writes = mod_patches.compile_external(selected, segments, eboot=eboot)
            except (OSError, ValueError, struct.error) as error:
                lines.append(f'Mods: {error}: not applied')
                writes = []
    write_patch_file(Path(out_dir) / 'patches.bin', writes)
    for _, data, what in writes:
        lines.append(f'Mod {what} ({data.hex()})')
    lines.append(f'Mods: {len(writes)} patch writes')
    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('game_dir')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mods-dir', help='folder of shadPS4/GoldHEN cheat XML files')
    p.add_argument('--mods-config', help='mods.json: {"enabled": [...], "disabled": [...]}')
    a = p.parse_args()
    lines = prepare(a.game_dir, a.out, a.mods_dir, a.mods_config)
    print('\n'.join(lines))


if __name__ == '__main__':
    sys.exit(main())
