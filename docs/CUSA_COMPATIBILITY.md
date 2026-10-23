# CUSA00004 / CUSA00223 compatibility

Both title IDs are supported. Saves and DLC keep their real regional title; nothing renames a save folder, changes CONTENT_ID, rewrites param.sfo, or changes cache keys.

A verified 1.07 executable has unwrapped ELF SHA-256 `b3afd173a379f83e1e408e71fdef22b78f93092d332b79decd48a18a08bfc605`. The European merged dump tested here reports APP_VER `01.00` and VERSION `01.07`, while containing exactly this executable. The launcher and XML compiler use effective version `01.07` only after verifying the ELF. VERSION alone is not evidence of compatible code.

For this verified build, XML eboot mods scoped to either CUSA00004 or CUSA00223 and AppVer `01.07` are listed and compiled using the same rules, including the built-in intro skip. Literal write bounds and unique executable-pattern matching remain in force; existing mod selections are preserved. No mod is newly enabled automatically. A file targeting another module, another app version or another game is not made compatible by changing its label.

Unrecognized executable hashes retain their real APP_VER and only their own title ID for XML selection. This avoids assuming that arbitrary editions, modified executables or older updates share addresses. The native camera mod also retains its runtime instruction-signature checks.

The Qt report and classic launcher show the effective version. Reports preserve the raw metadata fields, and the native game log distinguishes the verified executable from APP_VER when they differ. Presets with either regional game header are accepted. Save discovery/backup/import/export preserve each region; shader-cache tools recognize both IDs but do not merge their cache contents. DLC metadata is still matched to the actual game's title ID.

Tests use synthetic files; no game files, DLC data, player saves or settings are distributed. Matching executable code does not prove that every arbitrary data-file replacement mod is interchangeable, nor that a third-party cheat has no bugs.
