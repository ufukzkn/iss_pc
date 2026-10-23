# Windows fork with pending DLC and gyro support

This unofficial build inherits [HayatoG/iss_pc](https://github.com/HayatoG/iss_pc).
HayatoG and the upstream contributors created the native port. Original licenses,
copyright notices and commit authorship are preserved.

Fork downloads: https://github.com/ufukzkn/iss_pc/releases/latest
Gyro setup and limitations: [docs/GYRO_AIM.md](docs/GYRO_AIM.md).

## Following upstream

The root README and `qt/i18n/strings.json` stay identical to the official stable release.
Fork documentation lives here and in fork-specific guides. Fork UI messages live in
`qt/i18n/fork_strings.json`, loaded alongside the upstream table; intentional label overrides
are listed separately. The Windows packager includes this extra JSON through its existing
asset discovery. Upstream README reorganizations and new translation entries can therefore
merge without sharing the same additions. Translation key collisions still fail explicitly.

Runtime, controls and updater integrations remain code changes. They are tested after each
official release merge; a conflicting code change still stops publication for review rather
than silently dropping a feature. Experimental native-pass fixes stay on a separate branch.

- DLC runtime: **BeastBoyyy**, [PR #249](https://github.com/HayatoG/iss_pc/pull/249),
  original commit `d10332d27636ee42603c95a021ff1b1fa7086009` retained in history.
- Optional L2-held gyro aiming: [PR #279](https://github.com/HayatoG/iss_pc/pull/279).
  Off by default; see `docs/GYRO_AIM.md`.
- DLC metadata setup helper and guide: [PR #321](https://github.com/HayatoG/iss_pc/pull/321).
  See `docs/DLC_SETUP.md`. Importing metadata alone does not provide runtime support.
- Upstream's newer `<data folder>/dlc` scan also works: its entitlement labels and
  the existing content-profile labels are deduplicated into the same bounded
  AppContent provider, so enumeration and individual lookups stay consistent.
- Small FPS-menu label correction retained from the earlier fork.

## Updates

Use the ordinary Qt launcher: **Updates > Check for updates > Download and install**.
This is **upstream's updater implementation**, not a second updater feature.
The **Latest release** button opens the release page without installing.

The release feed points to this fork while DLC/gyro patches are unmerged. Installing
an official binary cannot retain code absent from that binary. The fork merges the
latest official stable source release and rebuilds it with the retained patches.
No game files, DLC packages, firmware, personal settings or saves are distributed.

Windows installation now keeps a visible progress window after the launcher closes:
verification, program-file backup/installation, rollback and restart show their own
file counts, current file, elapsed time and time since the last progress event.
Close is enabled only after the operation finishes or fails. Preparation reports
extraction/verification progress in the launcher. Journal inspection, confirmation,
snapshot pruning, save backup and helper startup run outside the GUI thread;
the rollback button uses cached state instead of validating every file on each repaint.

The upstream engine verifies the package, replaces manifest-owned program files in
the same directory, journals the transaction and supports rollback. Saves, settings,
mods and caches remain outside managed program files. Close the game first. The
fork retains **two confirmed program snapshots**; unfinished/failed recovery data
is not automatically deleted. Existing legacy backup folders are separate.

Local compatibility adjustment: a packaged installation below a project directory
is allowed only with an existing package manifest; managed hashes are validated
before replacement. An installation that is itself a Git checkout remains refused.

`Update-inFAMOUS.cmd`/`.ps1` are retained only for migration/recovery from older fork
packages. The Qt UI no longer invokes PowerShell. To migrate an old package, use
the updater scripts from the new release, not a stale copy from the old install.

**Türkçe:** Günlük kullanımda normal launcher'ı açıp Play'e bas. Güncelleme için
Updates > Check for updates > Download and install yeterli. Yeni motor HayatoG'den
geliyor; DLC/gyro kaybolmasın diye paketler geçici olarak bu fork'tan indiriliyor.

## Free-look stick sensitivity

Windows releases include both renderer executables and upstream's renderer v2
defaults. The v2 input bridge passes the same gyro/stick settings as v1, including
window focus. The shader-cache on-demand experiment applies to v1's cache loader;
renderer v2 has its own precompile/cache path. Compare the renderers separately.

**Controls > Controller > Free-look stick sensitivity** in the launcher and
**Insert > Controls > Controller camera** in game share a live `tlg.ini` setting.
Default **1.00x** preserves physical stick input exactly; try **1.35-1.50x** for
quicker small/medium right-stick movements while roaming. L2 aiming, gyro, mouse,
left stick and graffiti keep their own response. This gain reaches full stick
input sooner; it cannot raise the game's maximum camera turn speed. No smoothing,
frame queue or waiting is added. Range: 0.25-3.00x; optional environment override:
`ISS_STICK_LOOK_SENS` / `TLG_STICK_LOOK_SENS`.

## Cache-loading experiment

**Graphics > GPU and shaders > Load shader cache on demand (experimental)** is on
by default in this fork. Once first-start compilation is complete, it restores the
older first-use shader loading policy instead of importing the whole cache in the
background. It is an A/B experiment for the reported FPS drop when loading ends,
not a confirmed performance fix. First-start compilation and existing cache files
are retained. This loading-policy change does not alter shader code or its cache key.

For comparison, turn the option off and restart the game; keep **Load pipelines
while playing** on to select upstream's background import. An explicit
`ISS_LAZY_PROGRAMS=0` / `TLG_LAZY_PROGRAMS=0` also selects that behavior. An explicit
`ISS_WARMUP_BUILD_CACHED=1` / `TLG_WARMUP_BUILD_CACHED=1` still requests a background
pipeline rebuild. Leave graphics, LS, save and camera position unchanged for the test.

**Türkçe:** Deneme seçeneği varsayılan açık. Graphics > GPU and shaders bölümünden
kapatıp oyunu yeniden başlatarak önceki sürümle aynı cache yükleme davranışını
karşılaştırabilirsin. İlk shader derlemesi kapanmaz; cache ve kayıtlar silinmez.

## Source/release provenance

`FORK-BUILD.json` records `upstream_tag`, `upstream_commit` and the exact fork
`commit`. Fork and upstream commit hashes differ because the fork has extra commits.
The upstream commit must be an ancestor of the fork commit; names alone are not
proof. `package-files.json` is the upstream updater's owned-file manifest, regenerated
after adding fork provenance so all hashes match the final package.

The Windows release workflow checks every six hours (GitHub schedules may be late),
on a push to this fork's main, or on manual dispatch. It merges the latest official
stable release into a disposable candidate, runs feature/metadata/updater tests,
builds and self-tests the package, then publishes. Source conflicts stop publication.
Main moving during a build also stops publication; the previous release stays intact.

The fork retains its own Actions routing and never sends upstream Discord messages
or deletes older releases. Upstream source is merged normally; upstream workflow
changes require deliberate review. The separate upstream PR branches contain no
fork release feed or publishing automation. Build tests do not prove mission-level
DLC behavior, aiming feel or performance on every machine.


## Stable and beta builds

In **Updates**, click **Check for updates**, then select a build under **Release channel / build**.
Stable remains the default. Betas are explicitly marked as test builds; their changes appear first,
with the notes for the exact upstream stable baseline underneath. Select Stable again to return
through the same verified installer. The installer retains saves, settings and caches as before.

Both channels install packages built by this fork so the retained controller features remain.
Stable tracks upstream stable releases; beta tracks upstream prereleases on a separate `beta`
integration branch and never advances `main` or GitHub's Latest stable release. Each channel is
checked every six hours. To check manually, run **DLC Windows release** in Actions and choose
`stable` or `beta` under `channel`. Source conflicts stop publication for review.
