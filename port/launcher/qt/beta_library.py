# SPDX-License-Identifier: GPL-2.0-or-later
"""Verified side-by-side beta packages. Shared player data is never stored here."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import updater
from .releases import UpdateError, parse_version, _same_commit
import update_install

MARKER = '.iss-beta.json'
TAG = re.compile(r'beta-[0-9A-Za-z](?:[0-9A-Za-z.+_-]{0,93}[0-9A-Za-z])?$')


def folder(root, tag):
    root = Path(root).absolute()
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise UpdateError('archive', 'Invalid beta tag')
    target = root / tag
    # A managed build must remain an immediate real child, including on Windows junctions.
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise UpdateError('write', 'Beta library is a link')
    if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
        raise UpdateError('write', 'Beta folder is a link')
    if target.resolve().parent != root.resolve():
        raise UpdateError('write', 'Beta folder escapes its library')
    return target


def record(root, tag):
    target = folder(root, tag)
    try:
        with (target / MARKER).open('rb') as stream:
            data = json.loads(stream.read(160000))
        exe = data['exe']
        if not isinstance(data.get('bytes'), int) or data['bytes'] < 0:
            raise ValueError('Invalid package size')
        if (data['schema'] != 1 or data['release']['tag'] != tag or not data['release'].get('beta')
                or Path(exe).name != exe or not (target / exe).is_file()
                or (target / 'VERSION').read_text(encoding='utf-8').strip() != data.get('package_version', tag)):
            raise ValueError('Invalid beta record')
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_installed(root):
    root = Path(root)
    if not root.is_dir():
        return []
    result = []
    for child in root.iterdir():
        if TAG.fullmatch(child.name):
            try:
                data = record(root, child.name)
                if data:
                    result.append(data)
            except UpdateError:
                continue
    return sorted(result, key=lambda r: (r['release'].get('timestamp', ''), r['release']['tag']), reverse=True)


def install(archive, root, release, exe, progress=None):
    """Extract and verify before registering the beta. An existing version is reused."""
    root = Path(root)
    target = folder(root, release['tag'])
    if not release.get('beta') or Path(exe).name != exe:
        raise UpdateError('archive', 'Expected a beta package')
    root.mkdir(parents=True, exist_ok=True)
    with update_install.install_lock(root, '.iss-beta.lock'):
        if record(root, release['tag']):
            return target
        if target.exists():
            raise UpdateError('write', 'Unmanaged folder already exists: ' + str(target))
        work = Path(tempfile.mkdtemp(prefix='.partial-', dir=root))
        try:
            stage = updater.extract(archive, work / 'payload', updater.package_folder(Path(archive).name), progress)
            manifest, entries = update_install._check_payload(stage, progress=progress)
            package_version = (stage / 'VERSION').read_text(encoding='utf-8').strip()
            matches = package_version == release['tag']
            if release.get('source') == 'upstream':
                actual, expected = parse_version(package_version), parse_version(release['tag'])
                matches = (actual != 'bad' and expected != 'bad' and
                           _same_commit(actual[1], expected[1]))
            if (manifest.get('version') != package_version or not matches or not (stage / exe).is_file()):
                raise UpdateError('archive', 'Package version does not match the selected beta')
            data = {'schema': 1, 'release': release, 'exe': exe, 'package_version': package_version,
                    'bytes': sum(row['size'] for row in entries.values())}
            (stage / MARKER).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            update_install._replace(stage, target)
        finally:
            shutil.rmtree(work)
    return target


def session_running(root, tag):
    folder(root, tag)
    path = Path(root) / ('.' + tag + '.running.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        raise update_install.InstallError('busy', 'Cannot check beta session')
    try:
        pid = int(data['pid'])
        if os.name == 'nt':
            update_install.wait_for_exit(pid, timeout=0)
        else:
            os.kill(pid, 0)
            return True
    except ProcessLookupError:
        return False
    except (update_install.InstallError, PermissionError):
        return True
    except (KeyError, ValueError, TypeError):
        raise update_install.InstallError('busy', 'Invalid beta session record')
    return False


def remove(root, tag, current, shared_data, game_dir=None):
    """Remove only a registered beta; refuse running-install/player-data locations."""
    root = Path(root)
    if not record(root, tag):
        raise UpdateError('write', 'Not a managed beta')
    with update_install.install_lock(root, '.iss-beta.lock'), \
            update_install.install_lock(root, '.' + tag + '.session.lock'):
        target = folder(root, tag)
        if session_running(root, tag):
            raise update_install.InstallError('busy', 'Beta is running')
        if not record(root, tag):
            raise UpdateError('write', 'Not a managed beta')
        for protected in (current, shared_data, game_dir):
            if protected:
                path = Path(protected).resolve()
                if path == target.resolve() or target.resolve() in path.parents:
                    raise UpdateError('write', 'Beta contains a protected location')
        for name in ('user', 'savedata', 'savedata_backups', 'cache', 'mods', 'eboot.bin'):
            if (target / name).exists():
                raise UpdateError('write', 'Beta contains player data: ' + name)
        # The resolved absolute target was checked above; no shell or external path is used.
        shutil.rmtree(target)


def launch(root, tag, shared_data, session_log, env=None, options=None, popen=subprocess.Popen):
    data = record(root, tag)
    if not data:
        raise UpdateError('launch', 'Beta package is missing')
    target = folder(root, tag)
    environment = dict(os.environ if env is None else env)
    environment['ISS_USER_DIR'] = str(Path(shared_data).absolute())
    environment['ISS_BETA_SESSION_LOG'] = str(Path(session_log).absolute())
    environment['ISS_BETA_SESSION_LOCK'] = str(Path(root).absolute() / ('.' + tag + '.session.lock'))
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    environment.pop('_MEIPASS2', None)
    with update_install.install_lock(root, '.iss-beta.lock'):
        if session_running(root, tag):
            raise update_install.InstallError('busy', 'Beta is already running')
        if data['release'].get('source') == 'upstream':
            # Upstream's existing --play role receives a real inherited output handle.
            # The original package is neither injected with scripts nor patched.
            environment.pop('ISS_BETA_SESSION_LOG', None)
            environment.pop('ISS_BETA_SESSION_LOCK', None)
            with open(session_log, 'wb') as output:
                process = popen([str(target / data['exe']), '--play'], cwd=str(target), env=environment,
                                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                **(options or {}))
        else:
            process = popen([str(target / data['exe']), '--play'], cwd=str(target), env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            **(options or {}))
        update_install._json(Path(root) / ('.' + tag + '.running.json'), {'pid': process.pid})
    return process
