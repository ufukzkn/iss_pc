# SPDX-License-Identifier: GPL-2.0-or-later
"""Build identity shared by the launcher and XML compiler; never rewrites game metadata."""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path
import struct

TITLE_IDS = frozenset({'CUSA00004', 'CUSA00223'})
APP_VER_107 = '01.07'
ELF_107_SHA256 = 'b3afd173a379f83e1e408e71fdef22b78f93092d332b79decd48a18a08bfc605'
SELF_MAGIC = b'O\x15=\x1d'


def read_eboot_elf(game):
    try:
        data = (Path(game) / 'eboot.bin').read_bytes()
        if data[:4] == SELF_MAGIC:
            from prepare import parse_self
            data = bytes(parse_self(data)[0])
        return data
    except (OSError, ValueError, struct.error):
        return None


@lru_cache(maxsize=8)
def _digest(game, size, mtime_ns, ctime_ns):
    elf = read_eboot_elf(game)
    return hashlib.sha256(elf).hexdigest() if elf is not None else None


@dataclass(frozen=True)
class GameBuild:
    title_id: str | None
    metadata_app_version: str | None
    package_version: str | None
    effective_app_version: str | None
    verified_107: bool
    mod_title_ids: frozenset


def identify(game, *, elf=None, metadata=None):
    if metadata is None:
        try:
            from prepare import sfo
            metadata = sfo((Path(game) / 'sce_sys/param.sfo').read_bytes())
        except (OSError, ValueError, struct.error):
            metadata = {}
    title, app = metadata.get('TITLE_ID'), metadata.get('APP_VER')
    digest = None
    if title in TITLE_IDS and app in (None, '01.00', APP_VER_107):
        if elf is not None:
            digest = hashlib.sha256(elf).hexdigest()
        else:
            try:
                path = Path(game).resolve()
                stat = (path / 'eboot.bin').stat()
                digest = _digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            except OSError:
                pass
    verified = digest == ELF_107_SHA256
    # A title or VERSION string alone never makes another region's offsets compatible.
    ids = TITLE_IDS if verified else frozenset({title}) if title in TITLE_IDS else frozenset()
    return GameBuild(title, app, metadata.get('VERSION'), APP_VER_107 if verified else app,
                     verified, ids)
