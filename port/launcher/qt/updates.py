# SPDX-License-Identifier: GPL-2.0-or-later
"""The QObject behind the Updates screen. Bounded HTTPS GETs to the GitHub releases API when the player
clicks "Check for updates" (or opens the launcher with the option on, off by default); it sends no
data of the player. "Release page" opens the release in the browser. In a packaged build, "Download
and install" fetches the package (updater.py) after a confirmation. On Windows the verified package
replaces the files of this same folder (update_install.py) after one confirmation: the game, saves,
settings and caches stay, and the previous version can be restored. On Linux it is checked, asked
about again, installed in a new folder next to this one, and the player may restart into it."""
import datetime
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from . import beta_library, releases, report, updater
from .logic import tlg_run
import savemanager
import update_install


class Updates(QObject):
    changed = Signal()
    fetched = Signal(object)
    dialogChanged = Signal()
    progressed = Signal(object)    # (done, total) from the download thread
    stepDone = Signal(object)      # ('downloaded' | 'installed' | 'prepared', value) or an error
    installProgress = Signal(object)
    inspected = Signal(object)
    notesRequested = Signal()

    def __init__(self, backend, probes=None):
        """probes (tests, screenshots): 'fetch' -> f(version) returning the release dict or raising
        UpdateError, 'version' -> the installed version, 'open_url' -> f(url), 'save' -> f(settings),
        'frozen' -> bool, 'nt' -> bool (Windows: in-place), 'port_dir' -> the install folder,
        'data_dir' -> the data folder, 'exe' -> the launcher's file name, 'running' -> bool,
        'opener' -> urlopen-like f(request, timeout), 'backup' -> f(), 'handoff' -> f(journal, rollback),
        'launch' -> f(folder), 'quit' -> f()."""
        super().__init__(backend)
        self.backend = backend
        self.probes = probes or {}
        self._auto_play_beta = False
        self._betas = beta_library.list_installed(self.library_dir())
        self._last_beta_attempt = 0
        self._beta_timer = QTimer(self)
        self._beta_timer.setInterval(60000)
        self._beta_timer.timeout.connect(self._check_betas_if_due)
        self._checking = False
        self._error = ''
        self._phase = ''          # '' | download | install | prepare | handoff | ready
        self._progress = (0, 0)
        self._detail = ''
        self._install_stage = ''
        self._rollback_state = None
        self._verified = False
        self._archive = None      # the downloaded, checked package
        self._work = None         # this update's temporary folder, beside the install
        self._handed = False      # Windows: the journal is with the helper, so its folder must stay
        self._new_dir = None      # the folder it was installed into (Linux)
        self._cancel = threading.Event()
        self._dialog, self._handlers = {}, {}
        seen = backend.settings.get('update_seen')
        self.release = dict(seen) if isinstance(seen, dict) and seen.get('tag') else None
        cached = backend.settings.get('update_catalog')
        self._releases = [r for r in cached if isinstance(r, dict) and r.get('tag')] if isinstance(cached, list) else []
        if not self._releases and self.release:
            self._releases = [self.release]
        self._selected = 0
        if backend.settings.get('update_channel') == 'beta':
            self._selected = next((i for i, r in enumerate(self._releases) if r.get('beta')), 0)
        if self._releases:
            self.release = self._releases[self._selected]
        self.fetched.connect(self._on_fetched)
        self.progressed.connect(self._on_progress)
        self.stepDone.connect(self._on_step)
        self.installProgress.connect(self._on_install_progress)
        self.inspected.connect(self._on_inspected)
        if hasattr(backend, 'stateChanged'):    # a game or shader job starting changes what can be installed
            backend.stateChanged.connect(self.changed)

    def t(self, key, **fmt):
        return self.backend.t_(key, **fmt)

    # -- state ---------------------------------------------------------------------------------------
    def installed(self):
        if 'version' in self.probes:
            return self.probes['version']()
        return report.current_version((tlg_run.PORT_DIR, tlg_run.REPO_DIR), tlg_run.LOG_DIR)

    def status(self):
        if not self.release:
            return 'none'
        status = releases.compare(self.installed(), self.release.get('tag', ''))
        # Explicit selection may switch channels or restore a stable build older than a beta.
        if self._releases and status in ('older', 'unknown') and self.installed() != self.release.get('tag'):
            return 'different'
        return status

    @Property(bool, notify=changed)
    def available(self):
        """A newer version is known (the dot on the rail)."""
        return bool(self.release) and self.status() in ('newer', 'different')

    @Property(str, notify=changed)
    def current(self):
        return self.installed() or self.t('rep_unknown')

    @Property(str, notify=changed)
    def latest(self):
        return self.release['tag'] if self.release else '—'

    @Property(str, notify=changed)
    def published(self):
        return (self.release or {}).get('published', '')

    @Property(bool, notify=changed)
    def checking(self):
        return self._checking

    @Property(bool, notify=changed)
    def canDownload(self):
        return True     # without a known release it opens the releases page

    @Property(str, notify=changed)
    def statusText(self):
        if self._checking:
            return self.t('upd_checking')
        if self.selectedBetaInstalled and not self._error:
            return self.t('upd_beta_ready', tag=self.latest)
        if self._phase == 'ready':
            return self.t('upd_installed', folder=str(self._new_dir))
        if self._error:
            if self.release:    # the release on screen is the one of an earlier check, not today's
                seen = self.release.get('checked') or self.release.get('published') or '?'
                return self._error + ' ' + self.t('upd_cached', checked=seen)
            return self._error
        status = self.status()
        tag = self.latest
        if status == 'none':
            return self.t('upd_never')
        return self.t('upd_' + status, tag=tag, current=self.installed())

    @Property(str, notify=changed)
    def tone(self):
        if self._error:
            return 'bad'
        if self._phase == 'ready':
            return 'good'
        return {'newer': 'warn', 'different': 'warn', 'same': 'good'}.get(self.status(), 'info') \
            if not self._checking else 'info'

    @Property(str, notify=changed)
    def notes(self):
        if not self.release:
            return ''
        notes = releases.extract_notes(self.release.get('body', ''), self.backend.t_.pt())
        return notes or self.t('upd_no_notes')

    @Property('QVariantList', notify=changed)
    def releaseOptions(self):
        return [{'label': self.t(('upd_official_beta' if r.get('source') == 'upstream' else 'upd_beta') if r.get('beta') else 'upd_stable') + ' · ' + r['tag']}
                for r in self._releases]

    @Property(int, notify=changed)
    def releaseIndex(self):
        return self._selected

    @Property(bool, notify=changed)
    def betaSelected(self):
        return bool((self.release or {}).get('beta'))

    def library_dir(self):
        if 'library_dir' in self.probes:
            return Path(self.probes['library_dir']())
        port = self.port_dir()
        return port.parent if port.parent.name == 'infamous-betas' else port.parent / 'infamous-betas'

    @Property('QVariantList', notify=changed)
    def installedBetas(self):
        return [{'tag': row['release']['tag'], 'size': _mb(row.get('bytes', 0))}
                for row in self._betas]

    @Property(bool, notify=changed)
    def selectedBetaInstalled(self):
        return self.betaSelected and any(r['release']['tag'] == self.latest for r in self._betas)

    @Property(bool, notify=changed)
    def canManageBetas(self):
        return self.frozen() and not self.busy and not self._checking and not self.running() and not self._dialog

    @Property(str, notify=changed)
    def betaLibraryPath(self):
        return str(self.library_dir())

    @Slot(str)
    def viewBeta(self, tag):
        if self.busy or self._checking or self._dialog:
            return
        row = next((r for r in self._betas if r['release']['tag'] == tag), None)
        if not row:
            return
        index = next((i for i, r in enumerate(self._releases) if r['tag'] == tag), None)
        if index is None:
            self._releases.append(row['release'])
            index = len(self._releases) - 1
        self.selectRelease(index)
        self.notesRequested.emit()

    @Slot(str)
    def playBeta(self, tag):
        if not self.canManageBetas:
            return
        try:
            if not beta_library.record(self.library_dir(), tag):
                return
            self.backend.playBeta(tag)
        except Exception as error:
            self._fail(error)

    @Slot()
    def downloadAndPlayBeta(self):
        if not self.betaSelected:
            return
        if self.selectedBetaInstalled:
            self.playBeta(self.latest)
        elif self.canInstall:
            self._auto_play_beta = True
            self._start_download()

    @Slot(str)
    def deleteBeta(self, tag):
        if not self.canManageBetas or not any(r['release']['tag'] == tag for r in self._betas):
            return
        self._ask(self.t('upd_beta_delete'), self.t('upd_beta_delete_confirm', tag=tag),
                  [('yes', self.t('upd_beta_delete'), 'primary'), ('no', self.t('upd_cancel'), 'ghost')],
                  {'yes': lambda: self._delete_beta(tag)})

    def _delete_beta(self, tag):
        if self.running():
            return
        self._phase = 'cleanup'
        self._progress = (0, 0)
        self.changed.emit()
        def work():
            try:
                if self.running(live=True):
                    raise update_install.InstallError('busy', 'game')
                beta_library.remove(self.library_dir(), tag, self.port_dir(), self.data_dir(),
                                    self.backend.settings.get('game_dir'))
                self.stepDone.emit(('beta-deleted', beta_library.list_installed(self.library_dir())))
            except Exception as error:
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    @Property(str, notify=changed)
    def baselineTitle(self):
        baseline = (self.release or {}).get('baseline') or {}
        return self.t('upd_baseline', tag=baseline.get('tag', '—'))

    @Property(str, notify=changed)
    def baselineNotes(self):
        if not self.betaSelected:
            return ''
        baseline = (self.release or {}).get('baseline') or {}
        return releases.extract_notes(baseline.get('body', ''), self.backend.t_.pt()) or self.t('upd_baseline_missing')

    @Slot(int)
    def selectRelease(self, index):
        if self._checking or self.busy or self._phase or self._dialog or not 0 <= index < len(self._releases):
            return
        self._selected, self.release = index, self._releases[index]
        self._error = ''
        self.backend.settings['update_channel'] = 'beta' if self.betaSelected else 'stable'
        self._save()
        self.changed.emit()

    @Property(str, notify=changed)
    def introText(self):
        if self.betaSelected:
            return self.t('upd_beta_intro')
        return self.t('upd_intro_inplace' if self.windows() else 'upd_intro')

    @Property(bool, notify=changed)
    def checkOnOpen(self):
        return bool(self.backend.settings.get('check_updates_on_open', False))

    @Slot(bool)
    def setCheckOnOpen(self, value):
        self.backend.settings['check_updates_on_open'] = bool(value)
        self._save()
        self.changed.emit()

    def _save(self):
        if 'save' in self.probes:
            self.probes['save'](self.backend.settings)
        else:
            tlg_run.save_settings(self.backend.settings)

    @Property(bool, notify=changed)
    def checkBetasPeriodically(self):
        return bool(self.backend.settings.get('check_betas_periodically', True))

    @Slot(bool)
    def setCheckBetasPeriodically(self, value):
        self.backend.settings['check_betas_periodically'] = bool(value)
        self._save()
        if value:
            self._check_betas_if_due()
        self.changed.emit()

    def startBetaChecks(self, check_now=True):
        """Only the real app starts this timer; tests and screenshots never start network work."""
        self._beta_timer.start()
        if check_now:
            self._check_betas_if_due()

    def _check_betas_if_due(self):
        last = max(float(self.backend.settings.get('beta_last_checked') or 0), self._last_beta_attempt)
        if self.checkBetasPeriodically and time.time() - last >= 6 * 3600:
            self.check()

    # -- the check -----------------------------------------------------------------------------------
    @Slot()
    def check(self):
        if self._checking or self.busy or self._dialog:
            return
        self._last_beta_attempt = time.time()
        self._checking, self._error = True, ''
        self.changed.emit()
        version = self.installed()

        def work():
            fetch = self.probes.get('fetch') or releases.fetch_catalog
            try:
                self.fetched.emit(fetch(version))
            except releases.UpdateError as error:
                self.fetched.emit(error)
            except Exception as error:    # never let a surprise leave the screen stuck on "checking"
                self.fetched.emit(releases.UpdateError('http', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def _on_fetched(self, result):
        self._checking = False
        today = datetime.date.today().isoformat()
        if isinstance(result, releases.UpdateError):
            self._error = releases.error_text(result, self.t)
        elif result is None:    # 304: the release seen before is still the latest
            if self.release:
                self.release['checked'] = today
                self.backend.settings['update_seen'] = self.release
                self._save()
        elif isinstance(result, dict) and 'releases' in result:
            channel = self.backend.settings.get('update_channel', 'stable')
            self._releases = result['releases']
            for release in self._releases:
                release['body'] = release.get('body', '')[:40000]
                release['checked'] = today
            self._selected = next((i for i, r in enumerate(self._releases)
                                   if channel == 'beta' and r.get('beta')), 0)
            self.release = self._releases[self._selected] if self._releases else None
            self.backend.settings['beta_last_checked'] = time.time()
            self.backend.settings['update_catalog'] = self._releases
            self.backend.settings['update_seen'] = next((r for r in self._releases if not r.get('beta')), None)
            self._save()
        else:
            self.release = {'tag': result['tag'], 'url': result['url'], 'body': result['body'][:20000],
                            'published': result['published'], 'assets': list(result.get('assets') or [])[:20],
                            'checked': today, 'etag': result.get('etag', '')}
            self.backend.settings['update_seen'] = self.release
            self._save()
        self.changed.emit()

    @Slot()
    def download(self):
        url = (self.release or {}).get('url') or releases.RELEASES_URL
        prefix = releases.UPSTREAM_PREFIX if self.betaSelected and (self.release or {}).get('source') == 'upstream' else releases.RELEASE_PREFIX
        if not url.startswith(prefix):
            url = releases.RELEASES_URL
        if 'open_url' in self.probes:
            self.probes['open_url'](url)
        else:
            tlg_run.open_external(url)

    # -- download and install (packaged builds) ------------------------------------------------------
    def frozen(self):
        return self.probes['frozen']() if 'frozen' in self.probes else tlg_run.FROZEN

    def windows(self):
        return self.probes['nt']() if 'nt' in self.probes else updater.platform_key() == 'windows'

    def port_dir(self):
        return Path(self.probes['port_dir']() if 'port_dir' in self.probes else tlg_run.PORT_DIR)

    def exe_name(self):
        return self.probes['exe']() if 'exe' in self.probes else Path(sys.executable).name

    def data_dir(self):
        return Path(self.probes['data_dir']() if 'data_dir' in self.probes else tlg_run.user_dir())

    def running(self, live=False):
        """A game or shader job of this launcher. live=True also asks Windows for a tlg-probe process."""
        if 'running' in self.probes:
            return bool(self.probes['running']())
        return (self.backend._play_state != 'idle' or bool(self.backend._jobs)
                or (live and update_install.game_running()))

    def _in_checkout(self):
        return update_install.source_checkout(self.port_dir())

    @Property(bool, notify=changed)
    def packaged(self):
        return bool(self.frozen())

    @Property(bool, notify=changed)
    def busy(self):
        return self._phase in ('download', 'install', 'prepare', 'handoff', 'inspect', 'cleanup')

    @Property(bool, notify=changed)
    def canInstall(self):
        """A newer release with a package for this platform, in a packaged build, nothing running."""
        if not self.frozen() or self._checking or self._phase or not self.available:
            return False
        if self.betaSelected and (self.selectedBetaInstalled or self.running()):
            return False
        if self.windows() and (self.running() or (not self.betaSelected and self._in_checkout())):
            return False
        try:
            updater.pick_assets(self.release, nt=self.windows())
        except releases.UpdateError:
            return False
        return True

    @Property(bool, notify=changed)
    def canRestart(self):
        return self._phase == 'ready'

    @Property(bool, notify=changed)
    def canCancel(self):
        return self._phase == 'download'

    @Property(bool, notify=changed)
    def canRollback(self):
        """Windows: the previous version is kept until another update is confirmed."""
        if not self.frozen() or not self.windows() or self.busy or self.running():
            return False
        state = self._rollback_state
        return bool(state and state[1]['status'] in ('confirmed', 'installed'))

    def refreshInstallation(self, confirm=False):
        """Journal validation and snapshot pruning must never run in QML getters or the GUI thread."""
        if self.busy:
            return
        port = self.port_dir()
        self._phase = 'inspect'
        self.changed.emit()
        def work():
            try:
                state = update_install.pending(port)
                if confirm:
                    update_install.confirm(port)
                self.inspected.emit(state)
            except Exception as error:
                self.inspected.emit(error)
        threading.Thread(target=work, daemon=True).start()

    def _on_inspected(self, result):
        self._phase = ''
        if isinstance(result, Exception):
            self._fail(result)
            return
        self._rollback_state = result
        self.changed.emit()

    @Property(bool, notify=changed)
    def progressIndeterminate(self):
        return self._phase != 'download' and not self._progress[1]

    def _on_install_progress(self, value):
        self._install_stage, done, total, self._detail = value
        self._progress = (done, total)
        self.changed.emit()

    @Property(float, notify=changed)
    def progress(self):
        done, total = self._progress
        return done / total if total else 0.0

    @Property(str, notify=changed)
    def progressText(self):
        if self._phase == 'download':
            done, total = self._progress
            return self.t('upd_downloading', done=_mb(done), total=_mb(total),
                          pct=int(100 * done / total) if total else 0)
        if self._phase == 'prepare' and self._install_stage:
            done, total = self._progress
            text = self.t('upd_phase_' + self._install_stage)
            return text + (f' — {done}/{total}' if total else '')
        key = {'install': 'upd_installing', 'prepare': 'upd_preparing', 'handoff': 'upd_closing',
               'inspect': 'upd_phase_inspect', 'cleanup': 'upd_phase_cleanup'}.get(self._phase)
        return self.t(key) if key else ''

    @Property(str, notify=changed)
    def progressDetail(self):
        return self._detail if self._phase == 'prepare' else ''

    @Property(str, notify=changed)
    def installHint(self):
        """Why there is no "Download and install" here (a git checkout), or where Windows puts it."""
        if not self.frozen():
            return self.t('upd_source_hint')
        if self.betaSelected:
            return self.t('upd_beta_location', folder=str(self.library_dir()))
        return self.t('upd_same_path_hint', folder=str(self.port_dir())) if self.windows() else ''

    @Property('QVariantMap', notify=dialogChanged)
    def dialog(self):
        return self._dialog

    def _ask(self, title, body, buttons, handlers, lines=()):
        self._handlers = handlers
        self._dialog = {'open': True, 'title': title, 'body': body, 'lines': list(lines),
                        'buttons': [{'id': i, 'label': l, 'tone': t} for i, l, t in buttons]}
        self.dialogChanged.emit()

    @Slot(str)
    def answer(self, button):
        handler = self._handlers.get(button)
        self._dialog, self._handlers = {}, {}
        self.dialogChanged.emit()
        if handler:
            handler()

    def _fail(self, error):
        self._auto_play_beta = False
        self._phase, self._progress = '', (0, 0)
        self._error = self.t('upd_err_' + getattr(error, 'kind', 'write'),
                             detail=getattr(error, 'detail', str(error)))
        if self._work and not self._handed:    # once the helper has the journal, its folder is the recovery
            work = self._work
            self._work = None
            self._phase = 'cleanup'
            def cleanup():
                shutil.rmtree(work, ignore_errors=True)
                self.stepDone.emit(('discarded', None))
            threading.Thread(target=cleanup, daemon=True).start()
        self.changed.emit()

    @Slot()
    def install(self):
        """Step 1: ask before downloading. Windows asks once for the whole update; Linux asks again later."""
        if not self.canInstall:
            return
        try:
            package, _ = updater.pick_assets(self.release, nt=self.windows())
        except releases.UpdateError as error:
            self._fail(error)
            return
        port = self.port_dir()
        if self.betaSelected:
            self._auto_play_beta = False
            self._start_download()
            return
        if self.windows():
            self._ask(self.t('upd_install'),
                      self.t('upd_confirm', tag=self.release['tag'], folder=str(port),
                             size=f'{package["size"] / 1048576:.1f}'),
                      [('yes', self.t('upd_continue'), 'primary'), ('no', self.t('upd_cancel'), 'ghost')],
                      {'yes': self._start_download})
            return
        target = updater.target_folder(port, package['name'], self.release['tag'])
        data = updater.data_to_copy(port, self.data_dir())
        lines = [self.t('upd_ask_where', folder=str(target)), self.t('upd_ask_old', folder=str(port)),
                 self.t('upd_ask_data_copy' if data else 'upd_ask_data_kept', folder=str(self.data_dir()))]
        self._ask(self.t('upd_ask_download_title'),
                  self.t('upd_ask_download', tag=self.release['tag'], size=_mb(package['size'])),
                  [('yes', self.t('upd_download_now'), 'primary'), ('no', self.t('upd_cancel'), 'ghost')],
                  {'yes': self._start_download}, lines)

    def _start_download(self):
        windows = self.windows()
        try:
            if windows and self.running(live=True):
                raise update_install.InstallError('busy', 'game')
            package, sums_asset = updater.pick_assets(self.release, nt=windows)
            port, version = self.port_dir(), self.installed()
            self._work = Path(tempfile.mkdtemp(prefix='.iss-update-', dir=port.parent))
        except Exception as error:
            self._fail(error)
            return
        archive = self._work / package['name']
        # Windows replaces the files in place, so the data folder is never copied.
        data = None if windows or self.betaSelected else updater.data_to_copy(port, self.data_dir())
        opener = self.probes.get('opener')
        self._cancel.clear()
        self._handed, self._archive = False, None
        self._phase, self._progress, self._error = 'download', (0, package['size']), ''
        self.changed.emit()

        def work():
            try:
                need = updater.needed_bytes(package['size'], data)
                if updater.free_bytes(port.parent) < need:
                    raise releases.UpdateError('space', _mb(need))
                sums = updater.fetch_sums(sums_asset, version, opener) if sums_asset else None
                digest = updater.download(package, archive, version, opener,
                                          progress=lambda d, t: self.progressed.emit((d, t)),
                                          cancelled=self._cancel.is_set)
                verified = updater.verify(package['name'], digest, sums, package.get('digest', ''))
                self.stepDone.emit(('downloaded', (archive, verified)))
            except Exception as error:    # never leave the screen stuck on "downloading"
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def cancelDownload(self):
        self._cancel.set()

    def _on_progress(self, value):
        if self._phase == 'download':
            self._progress = value
            self.changed.emit()

    def _on_step(self, result):
        if isinstance(result, Exception):
            self._fail(result)
            return
        step, value = result
        if step == 'discarded':
            self._phase = ''
            self.changed.emit()
        elif step == 'downloaded':
            self._archive, self._verified = value
            self._phase = ''
            self.changed.emit()
            if self.betaSelected:
                self._install_beta()
            elif self.windows():
                self._start_prepare()
            else:
                self._ask_install()
        elif step in ('beta-installed', 'beta-deleted'):
            self._phase = ''
            self._betas = value
            self._work = None
            play, self._auto_play_beta = self._auto_play_beta, False
            self.changed.emit()
            if play and step == 'beta-installed':
                self.playBeta(self.latest)
        elif step == 'installed':
            self._new_dir, self._phase = value, 'ready'
            shutil.rmtree(self._work, ignore_errors=True)
            self._work = None
            self.changed.emit()
            self._ask_restart()
        elif step == 'prepared':
            self._handoff(value)
        elif step == 'handed':
            self._handed = True
            if 'quit' in self.probes:
                self.probes['quit']()
            else:
                self.backend._quit_app()

    def _install_beta(self):
        archive, release = self._archive, dict(self.release)
        root, exe, workdir = self.library_dir(), self.exe_name(), self._work
        self._install_stage = ''
        self._phase = 'prepare'
        self._progress = (0, 0)
        self.changed.emit()
        def work():
            try:
                beta_library.install(archive, root, release, exe,
                                     progress=lambda *value: self.installProgress.emit(value))
                if workdir:
                    shutil.rmtree(workdir)
                self.stepDone.emit(('beta-installed', beta_library.list_installed(root)))
            except Exception as error:
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    def _ask_install(self):
        """Step 2 (Linux): the package is here and checked; ask before installing it."""
        package, _ = updater.pick_assets(self.release)
        target = updater.target_folder(self.port_dir(), package['name'], self.release['tag'])
        self._ask(self.t('upd_ask_install_title'),
                  self.t('upd_ask_install_sha' if self._verified else 'upd_ask_install_size',
                         tag=self.release['tag'], folder=str(target)),
                  [('yes', self.t('upd_install_now'), 'primary'), ('no', self.t('upd_cancel'), 'ghost')],
                  {'yes': self._start_install, 'no': self._discard})

    def _discard(self):
        self._archive = None
        if self._work:
            shutil.rmtree(self._work, ignore_errors=True)
            self._work = None

    def _start_install(self):
        """Linux: extract into a new folder next to the install (the old one stays)."""
        package, _ = updater.pick_assets(self.release)
        archive, port, tag = self._archive, self.port_dir(), self.release['tag']
        exe, data = self.exe_name(), self.data_dir()
        self._phase, self._error = 'install', ''
        self.changed.emit()

        def work():
            try:
                folder = updater.install(archive, port, package['name'], tag, exe, data)
                self.stepDone.emit(('installed', folder))
            except Exception as error:
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    def _ask_restart(self):
        """Step 3 (Linux): offer to start the new version; the old folder stays to go back."""
        self._ask(self.t('upd_ask_restart_title'),
                  self.t('upd_ask_restart', folder=str(self._new_dir), old=str(self.port_dir())),
                  [('yes', self.t('upd_restart_now'), 'primary'), ('no', self.t('upd_later'), 'ghost')],
                  {'yes': self.restart})

    @Slot()
    def restart(self):
        if self._phase != 'ready' or not self._new_dir:
            return
        try:
            if 'launch' in self.probes:
                self.probes['launch'](self._new_dir)
            else:
                updater.launch(self._new_dir, self.exe_name(), tlg_run.desktop_env(), tlg_run.detach_options())
        except OSError as error:
            self._error, self._phase = self.t('upd_err_launch', detail=f'{self._new_dir}: {error}'), ''
            self.changed.emit()
            return
        if 'quit' in self.probes:
            self.probes['quit']()
        else:
            self.backend._quit_app()

    # -- Windows: in place ---------------------------------------------------------------------------
    def _start_prepare(self):
        """Extracts the verified package and writes the journal, all outside the installed files."""
        archive, workdir, tag = self._archive, self._work, self.release['tag']
        port, exe = self.port_dir(), self.exe_name()
        protected = [str(self.data_dir())]
        if self.backend.settings.get('game_dir'):
            protected.append(str(self.backend.settings['game_dir']))
        self._phase, self._error = 'prepare', ''
        self._progress, self._install_stage, self._detail = (0, 0), '', ''
        self.changed.emit()

        def work():
            try:
                progress = lambda *value: self.installProgress.emit(value)
                stage = updater.extract(archive, workdir / 'payload', updater.package_folder(archive.name),
                                        progress=progress)
                archive.unlink(missing_ok=True)
                transaction = update_install.prepare(stage, port, tag, exe_name=exe, protected=protected,
                                                     progress=progress)
                progress('backup', 0, 0, '')
                if 'backup' in self.probes:
                    self.probes['backup']()
                else:
                    savemanager.backup_now(self.data_dir())
                self.stepDone.emit(('prepared', transaction))
            except Exception as error:
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    def _handoff(self, transaction, rollback=False):
        """Windows: this launcher closes; the helper waits for it, applies the journal and reopens."""
        self._save()
        self._phase, self._progress = 'handoff', (0, 0)
        self.changed.emit()
        def work():
            try:
                if self.running(live=True):
                    raise update_install.InstallError('busy', 'game')
                if 'handoff' in self.probes:
                    self.probes['handoff'](transaction, rollback)
                else:
                    update_install.start_helper(transaction, rollback=rollback)
                self.stepDone.emit(('handed', None))
            except Exception as error:
                self.stepDone.emit(error)
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def rollback(self):
        if not self.canRollback:
            return
        transaction, _ = self._rollback_state
        self._ask(self.t('upd_rollback'), self.t('upd_rollback_confirm'),
                  [('yes', self.t('upd_rollback'), 'primary'), ('no', self.t('upd_cancel'), 'ghost')],
                  {'yes': lambda: self._handoff(transaction, True)})


def _mb(size):
    return f'{size / 2 ** 20:.0f} MB' if size >= 2 ** 20 else f'{size / 1024:.0f} KB'
