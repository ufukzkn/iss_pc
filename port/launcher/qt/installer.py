# SPDX-License-Identifier: GPL-2.0-or-later
"""Two-phase Windows update handoff. Never replace a running frozen launcher's files.

Prepare in a background process while Qt stays responsive. Once a verified package passes its
selftest, copy the applying script outside the install, start it waiting for this launcher,
then let Qt exit normally. The hidden worker applies/rolls back and reopens the launcher.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PREFIX = 'ISS_UPDATE:'

def supported(root):
    return os.name == 'nt' and getattr(sys, 'frozen', False) and (Path(root) / 'Update-inFAMOUS.ps1').is_file()

def powershell():
    return str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')

def read_notice():
    name = os.environ.pop('ISS_UPDATE_RESULT_FILE', '')
    if not name:
        return None
    try:
        result = json.loads(Path(name).read_text(encoding='utf-8-sig'))
        return result if result.get('status') in ('success', 'error') else None
    except (OSError, ValueError, TypeError):
        return None

def prepare(root, progress, owner_pid=None):
    root = Path(root).resolve()
    session = Path(tempfile.mkdtemp(prefix='iss-launcher-update-'))
    script = session / 'Update-inFAMOUS.ps1'
    shutil.copy2(root / script.name, script)
    plan = session / 'prepared.json'
    command = [powershell(), '-NoProfile', '-File', str(script), '-InstallDir', str(root),
               '-PrepareOnly', '-PreparedPlan', str(plan), '-WaitForProcessId', str(owner_pid or os.getpid())]
    last_error = ''
    log = session / 'prepare.log'
    with log.open('w', encoding='utf-8') as output:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        for line in child.stdout:
            output.write(line)
            if line.startswith(PREFIX):
                event = json.loads(line[len(PREFIX):])
                if event['phase'] == 'error':
                    last_error = event.get('message', '')
                progress(event['phase'])
        code = child.wait()
    if code or not plan.is_file():
        raise RuntimeError(last_error or 'The update could not be prepared. See ' + str(log))
    data = json.loads(plan.read_text(encoding='utf-8-sig'))
    if Path(data['target']).resolve() != root or data.get('schema') != 1:
        raise RuntimeError('Unexpected prepared update target')
    return {'session': str(session), 'plan': str(plan), 'script': str(script), 'version': data['version']}

def handoff(prepared, parent_pid=None, restart=True):
    session = Path(prepared['session'])
    command = [powershell(), '-NoProfile', '-File', prepared['script'], '-ApplyPrepared', prepared['plan'],
               '-WaitForProcessId', str(parent_pid or os.getpid()), '-ResultFile', str(session / 'result.json')]
    if restart:
        command.append('-RestartLauncher')
    with (session / 'install.log').open('wb') as output:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                 close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    return child.pid
