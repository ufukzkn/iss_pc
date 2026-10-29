# Autosave history

The game keeps its original Auto0 and Auto1 slots. The fork additionally preserves
the five most recent distinct autosave payloads under
`<user_dir>/autosave_history/<user>/<CUSA>/entry-...`.
Both CUSA00004 and CUSA00223 use their own histories. Manual saves are untouched.

Capture runs before an existing autosave is mounted writable and after a save with
updated metadata is unmounted. Each entry contains the unmodified `dis.dat`,
`param.bin`, optional icon, and original slot name. A snapshot is offered only after
all required files have been copied, checked, and the staging directory renamed.
Old entries are pruned only after the new entry is complete. A failed copy logs an
error but does not block saving or prune older entries.

In **Saves and data > Backups**, history entries start with `autosave-history/` and
show the saved chapter/progress. Restoring one creates a new manual save slot;
it first takes the regular safety backup and refuses while either renderer runs.
It does not replace live autosaves or other manual saves.

This is a rolling five-entry history, not five extra slots in the game's autosave
list. Continued autosaving eventually replaces all five history entries too.
The existing ten launch-time full backups remain independent. This feature cannot
recover saves overwritten before it was installed. It is best-effort protection:
storage failures and power loss can still prevent a complete snapshot.

Validation: `test_autosave_history.c` covers rotation across both autosave slots,
deduplication, manual exclusion, and copy failure without pruning.
`test_autosave_history.py` covers safe recovery into a new manual slot, running-game
guards, invalid paths, and incomplete snapshot exclusion.
