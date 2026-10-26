"""Merge main's retained features and upstream developer into a disposable beta candidate."""
import datetime
import json
import os
from pathlib import Path
import subprocess

from prepare_fork import REPO, UPSTREAM, api, git, merge_release


def main():
    assert os.environ['GITHUB_REPOSITORY'] == REPO
    main_commit = git('rev-parse', 'HEAD')
    previous = api(f'repos/{REPO}/branches/beta', missing=True)
    if previous:
        git('fetch', '--no-tags', 'origin', 'beta')
        git('checkout', '--detach', 'FETCH_HEAD')
    beta_base = git('rev-parse', 'HEAD')
    # No source conflict is discarded automatically. Workflow routing stays ours.
    merge_release(main_commit, main_commit)
    remotes = git('remote').splitlines()
    if 'upstream' not in remotes:
        git('remote', 'add', 'upstream', f'https://github.com/{UPSTREAM}.git')
    git('fetch', '--no-tags', 'upstream', 'developer')
    developer = git('rev-parse', 'FETCH_HEAD')
    merge_release(main_commit, developer)
    candidate = git('rev-parse', 'HEAD')
    stable = api(f'repos/{REPO}/releases/latest')
    releases = api(f'repos/{REPO}/releases?per_page=30')
    already_built = any(r.get('prerelease') and not r.get('draft') and
                        r.get('tag_name', '').startswith('beta-fork-') and
                        r.get('target_commitish') == candidate for r in releases)
    needed = not already_built or os.environ.get('FORCE') == 'true'
    version = 'beta-fork-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y.%m.%d') + '-' + candidate[:7]
    result = {'repository': REPO, 'upstream_repository': UPSTREAM, 'upstream_tag': 'developer',
              'upstream_commit': developer, 'base_commit': main_commit, 'beta_base_commit': beta_base,
              'commit': candidate, 'version': version, 'needed': needed, 'channel': 'beta',
              'stable_tag': stable['tag_name']}
    folder = Path(os.environ['RUNNER_TEMP']) / 'fork-candidate'
    folder.mkdir()
    (folder / 'candidate.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if needed:
        git('bundle', 'create', str(folder / 'candidate.bundle'), 'HEAD')
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write(f'needed={str(needed).lower()}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
