# SPDX-License-Identifier: GPL-2.0-or-later
"""Load fork-owned UI text without editing upstream's translation table."""
import json
from pathlib import Path


def load_strings_with_fork(path):
    path = Path(path)
    base = json.loads(path.read_text(encoding='utf-8'))
    overlay = path.with_name('fork_strings.json')
    if not overlay.is_file():
        return base
    extra = json.loads(overlay.read_text(encoding='utf-8'))
    additions, overrides = extra['strings'], extra['overrides']
    # A newly introduced upstream key must not silently replace our feature's message.
    collisions = base.keys() & additions.keys()
    if collisions:
        raise ValueError('Upstream/fork translation key collision: ' + ', '.join(sorted(collisions)))
    for key, value in {**additions, **overrides}.items():
        if not isinstance(value, dict) or not all(isinstance(value.get(lang), str) and value[lang]
                                                  for lang in ('en', 'pt')):
            raise ValueError('Incomplete fork translation: ' + key)
    missing = overrides.keys() - base.keys()
    if missing:
        raise ValueError('Upstream removed overridden translation: ' + ', '.join(sorted(missing)))
    return {**base, **additions, **overrides}
