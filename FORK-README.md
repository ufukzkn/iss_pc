# DLC Windows fork

This is a convenience Windows build of [HayatoG/iss_pc](https://github.com/HayatoG/iss_pc), maintained in [ufukzkn/iss_pc](https://github.com/ufukzkn/iss_pc). It is an unofficial fork, not a new port.

Credits: **HayatoG and the upstream contributors** created the native port. **BeastBoyyy** implemented DLC entitlement support in [upstream PR #249](https://github.com/HayatoG/iss_pc/pull/249), commit `d10332d27636ee42603c95a021ff1b1fa7086009`; that commit and its authorship are retained. This fork adds the missing 60 FPS menu label, a compile-time label/value count check, release integration and an updater. Original copyright notices and licenses are preserved; see `port/LICENSE` and the third-party licenses.

Optional L2-held native gyro aiming is tracked separately in [upstream draft PR #279](https://github.com/HayatoG/iss_pc/pull/279). It is off by default; enable it under Controls. See `docs/GYRO_AIM.md` for settings and limitations.

## Windows: one click updates / tek tikla guncelleme

Download a complete Windows package from **this fork's Releases**, then use `Update-inFAMOUS.cmd` inside the installation. For the existing local installation, the same two updater files can sit beside the `infamous-windows-x86_64` folder. The ordinary launcher shortcut and Play button continue to work.

**Qt launcher:** open Updates, click Check for updates, then **Fetch and install** when a new version is available. The launcher stays open while the package is downloaded, verified and self-tested. It then exits briefly so its files can be replaced safely; a hidden worker backs up/applies (or rolls back) and reopens the launcher with the result. The script is copied to TEMP before the handoff, and the applying phase rechecks all prepared file hashes. No CMD window or manual command is needed. Close the game first. The command-line updater remains a recovery/fallback route.

PowerShell command (an explicit path is optional when using the standard folder layout):

```powershell
powershell.exe -NoProfile -File .\Update-inFAMOUS.ps1 -InstallDir .\infamous-windows-x86_64
```

Add `-CheckOnly` to check without installing. Close the game and launchers before installing. The updater downloads only `ufukzkn/iss_pc` releases, verifies the archive SHA256 and every listed file, rejects unexpected/game/player files and escaping paths, and tests the staged launcher before changing the installed program. It backs up saves/settings and changed program files, preserves caches and unrelated files, verifies installed hashes, and restores program files if installation or the installed launcher's selftest fails. After a successful installation, only the last two successful update backups for that installation remain under `infamous-update-backups`; failed/incomplete transactions and unrelated folders are kept for recovery. Cleanup failures do not roll back a successful update. The Qt Updates page also has a **Latest release** button to open the release page without installing anything.

**Turkce:** `Update-inFAMOUS.cmd` dosyasina cift tikla. Oyun ve launcher kapali olmali. Guncelleme once indirilip dogrulanir ve test edilir; sonra kayitlar/ayarlar ile degisecek program dosyalari yedeklenir. Hata olursa onceki program dosyalari geri yuklenir. Normal launcher kisayolunu kullanmaya devam edebilirsin. Resmi ZIP'i ustune acmak yerine bu guncelleyiciyi kullan; resmi pakette henuz bulunmayan DLC yamasi aksi halde kalkabilir.

## Release maintenance

`DLC Windows release` checks the latest **official stable release** every six hours (GitHub schedules can be delayed), on a push to this fork's `main`, or with Actions > Run workflow. It merges that release into a disposable checkout, verifies DLC/FPS features, runs Python/native DLC tests and updater recovery tests, builds Windows, and tests the actual package. Only a passing candidate is pushed to `main` and published. Merge conflicts stop the run for manual resolution. No custom PAT or external webhook is required. If DLC is merged upstream, the retained tests continue checking it; code refactors can require updating the feature guard.

The original upstream Build workflow is retained but its jobs only run in HayatoG's repository. This fork's own workflow never sends Discord messages or deletes older releases. GitHub can disable inactive scheduled workflows; a manual run or subsequent repository activity can be needed.

Upstream source is merged normally, but this fork keeps its own `.github/workflows` directory. Importing new upstream Actions files would require a workflow-write PAT, and they are not needed for this fork's Windows release pipeline. Source conflicts still stop publication for manual resolution.

Build/launcher tests do not guarantee mission-level DLC behavior or game performance. No game, DLC, firmware, personal paths, saves or settings are distributed. The player supplies the base game and owned DLC metadata separately, as documented upstream.
