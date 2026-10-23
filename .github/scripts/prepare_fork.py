"""Merge only the latest official release into a disposable CI checkout; never push here."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

REPO = 'ufukzkn/iss_pc'
UPSTREAM = 'HayatoG/iss_pc'

def api(path, missing=False):
    request = urllib.request.Request('https://api.github.com/' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json', 'User-Agent': 'iss-pc-maintained-fork'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing and error.code == 404:
            return None
        raise

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

def merge_release(base, target):
    """Keep this fork's workflow routing: GITHUB_TOKEN cannot import upstream workflows.

    Merge source changes normally and fail on source conflicts; only the workflow directory
    is deliberately kept from our base. No extra workflow-write PAT is needed.
    """
    result = subprocess.run(['git', '-c', 'user.name=iss_pc fork automation',
                             '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                             'merge', '--no-edit', '--no-ff', '--no-commit', target])
    pending = subprocess.run(['git', 'rev-parse', '--verify', 'MERGE_HEAD'], capture_output=True).returncode == 0
    if not pending:
        if result.returncode:
            raise RuntimeError('Cannot prepare upstream merge')
        return
    conflicts = git('diff', '--name-only', '--diff-filter=U').splitlines()
    if any(not name.startswith('.github/workflows/') for name in conflicts):
        raise RuntimeError('Upstream source conflict; manual resolution needed: ' + ', '.join(conflicts))
    git('restore', '--source=' + base, '--staged', '--worktree', '--', '.github/workflows')
    git('-c', 'user.name=iss_pc fork automation',
        '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com', 'commit', '--no-edit')

def main():
    assert os.environ['GITHUB_REPOSITORY'] == REPO
    # Betas are downloaded directly by the launcher. CI only maintains fork stable releases.
    assert os.environ.get('CHANNEL', 'stable') == 'stable', 'Beta publication is disabled'
    official = api(f'repos/{UPSTREAM}/releases/latest')
    tag = official['tag_name']
    assert re.fullmatch(r'v[0-9A-Za-z.+_-]+', tag), 'Unexpected upstream tag'
    assert not official['draft'] and not official['prerelease']
    base = git('rev-parse', 'HEAD')
    git('remote', 'add', 'upstream', f'https://github.com/{UPSTREAM}.git')
    git('fetch', '--no-tags', 'upstream', 'tag', tag)
    merge_release(base, f'refs/tags/{tag}')
    candidate = git('rev-parse', 'HEAD')
    published = api(f'repos/{REPO}/releases/latest', missing=True)
    needed = not published or published['target_commitish'] != candidate or os.environ.get('FORCE') == 'true'
    version = 'v' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y.%m.%d') + '-' + candidate[:7]
    result = {'repository': REPO, 'upstream_repository': UPSTREAM, 'upstream_tag': tag,
              'upstream_commit': git('rev-parse', f'refs/tags/{tag}^{{commit}}'),
              'base_commit': base, 'commit': candidate, 'version': version, 'needed': needed}
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
