# ZenExport 6.1.1

Versioned local backups and manufacturing exports for Autodesk Fusion.

## Status

**6.1.1 is a preview release.** Automated verification covers the domain, filesystem
operations, simulated Fusion events, and release packaging. Earlier 6.0.3 and 6.1.0
exports succeeded in the local Fusion session, but the final 6.1.1 save workflow,
exported-file recovery, and MSI installation still need live validation. Reload and
validate the add-in on a disposable design before depending on it for production backups.

Free and open source under the [MIT license](LICENSE), shared by
[EsKay-Labs](https://github.com/EsKay-Labs) as a gift to the Fusion and 3D-printing community.
Download the [6.1.1 preview](https://github.com/EsKay-Labs/ZenExport/releases/tag/v6.1.1)
or use the source installation below.

The detailed audit, evidence, architecture, and priorities are in
[.agent/knowledge/architecture.md](.agent/knowledge/architecture.md).

## How it works

1. The toolbar command, or an intercepted native Save, captures the active design.
2. The command handler runs the export directly on Fusion's main thread, restoring
   the original synchronous entry path. Native Save is cancelled after validating the
   design/document and before starting the export. A guard prevents reentrant saves
   from launching duplicate exports. Custom event posting is no longer used.
3. The design's portable context UUID and optional cloud file ID resolve its folder.
   A new design prompts for a parent folder and project name.
4. Context attributes are written **before** creating the first F3D archive.
5. The full profile traverses the assembly once to gather visible native part targets
   and a diagnostic SHA-256 fingerprint. CAD/backup profiles avoid per-part traversal.
   Repeated instances share native part exports; distinct objects with identical
   names receive unique filesystem names.
6. An optional revision description is requested, e.g. `M6 holes`. Leaving it empty
   keeps a plain numeric name; Cancel exits before reserving a revision or writing
   context attributes. A shared `vNN_description` label is reserved under CAD, Models,
   and _Info, so each format has its own matching revision folder.
   Each requested output is written to a
   temporary file and published only after Fusion reports success and the output is
   non-empty.
7. `export_manifest.json` records every outcome, file size, snapshot/translation
   durations, and final status.
   The local last-success marker advances only when all required exports succeed.

Every explicit save request creates a version. The old count-based skip check was
removed: changing a dimension or geometry does not necessarily change object counts.
The new fingerprint is diagnostic and does not authorize skipping a backup.

## Installation and use

For the release ZIP, extract it and copy `ZenExport.bundle/Contents` to a folder
named `ZenExport`. Then select that `ZenExport` folder in Fusion's Scripts and Add-Ins
dialog. This manual route avoids relying on automatic bundle discovery, which still
needs live verification. The ZIP includes this README and the MIT license.

Keep `ZenExport.py`, `ZenExport.manifest`, and the entire `zenexport/` directory together.
Add this folder through Fusion's **Utilities > Scripts and Add-Ins**, or place it under:

- Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\ZenExport`
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ZenExport`

Stop the older instance, then run ZenExport and optionally enable Run on Startup.
Do not run the Scripts-folder copy and an installed bundle at the same time.

The Scripts and Add-Ins toolbar panel exposes:

- **ZenExport Save**: export the active design to its remembered project.
- **ZenExport: Choose Destination**: choose a new destination and context explicitly.

By default the existing native Save interception is preserved. This can include
clicking native Save as well as pressing Ctrl+S. The command IDs are inherited from
the previous implementation and require checking against your Fusion version.
Shift while invoking native Save also selects a new destination on Windows.
The separate Choose Destination command works without a platform-specific key check.
There is no unsupported `CommandDefinition.hotKey` assignment.

Cancelling setup creates no export. Cancelling an ongoing export takes effect between
files when Fusion delivers the cancellation; an individual translator call cannot be
interrupted by this add-in. All model/export/UI API work stays on the main thread.

## Output layout

```text
MyProject/
├── CAD/
│   └── v03_M6 holes/
│       ├── MyProject_v03.f3d
│       ├── MyProject_v03.step
│       └── Components/Component/
│           ├── Component.step
│           └── Component.f3d
├── Models/
│   └── v03_M6 holes/
│       └── Component/Body.stl
└── _Info/
    ├── v03_M6 holes/
    │   ├── _preview.png
    │   ├── export_events.jsonl
    │   └── export_manifest.json
    ├── version_reservations/
    └── _Migration/
```

CAD and Models are the two main project folders. Each gets the same revision label:
`CAD/v03_M6 holes` contains STEP/F3D; `Models/v03_M6 holes` contains matching STL files.
Auxiliary files use the same label under `_Info`:

- `_preview.png`: a viewport image for visual identification.
- `export_manifest.json`: the result summary, timings, file list, and full revision
  description. Its schema is version 3; file paths are relative to the project root.
- `export_events.jsonl`: one outcome per exported file, useful for troubleshooting an
  interrupted export.

The project-level `_Info/version_reservations` directory holds small numeric
claims so simultaneous saves with different descriptions cannot reuse a revision ID.
Archive filenames retain the numeric version, e.g. `MyProject_v03.f3d`, while the folder
holds the description. Greek text is supported; unsafe filename characters are replaced
and long folder descriptions are shortened. The full description remains in the manifest.

Root-component bodies also receive a Models subfolder; the root archive/STEP already
represent the whole design. Subcomponent CAD exports can include their descendants.
STLs are a **native part library in component coordinates**, with one file per visible
native BRep body, not one transformed mesh per assembly instance. Whole-design STEP/F3D
retain assembly placement. Occurrence proxies determine effective body visibility.

`success` means every required output succeeded. A failed optional thumbnail is shown
in the report but does not invalidate CAD backup success. `partial`, `cancelled`, and
`in_progress` versions remain available for inspection and never overwrite history.
After an interrupted process, the append-only event file contains completed outcomes;
the manifest remains `in_progress`. A retry claims a new version number.

**Layout correction in 6.1.1:** Existing `Revisions/vNN` snapshots and Models embedded
inside older CAD revisions are reorganized into matching project-level CAD/Models
folders. The next number counts both old and new histories. A completed save opens
the project root so both matching folders are visible.

Migration checks all destinations before moving files, preserves native file bytes,
backs up original reports under `_Info/_Migration`, and updates their relative paths
and the last-success pointer. Interrupted metadata rewrites can resume from a journal.
Conflicting files stop migration instead of being overwritten. Only empty old folders
are removed. Older unversioned exports are retained under `_Legacy_unversioned` within
their format category: their original revision cannot be reconstructed reliably.

## Settings and logs

Writable state is separate from the installed program:

- Windows: `%LOCALAPPDATA%\ZenExport\config.json`
- macOS: `~/Library/Application Support/ZenExport/config.json`
- Override for isolated development: `ZENEXPORT_DATA_DIR`

The file is created on first run. Edit `settings` while the add-in is stopped, then
restart it. Preserve `schema_version` and `contexts`.

```json
{
  "schema_version": 1,
  "settings": {
    "intercept_native_save": true,
    "profile": "full",
    "mesh_quality": "high",
    "thumbnail": true,
    "open_folder": true,
    "prompt_revision_name": true
  },
  "contexts": {}
}
```

| Profile | Whole-design F3D | Whole-design STEP | Visible-body STL | Component STEP/F3D |
| --- | --- | --- | --- | --- |
| full | yes | yes | yes | yes |
| cad | yes | yes | no | no |
| backup | yes | no | no | no |

`mesh_quality` accepts `low`, `medium`, or `high`. STL units follow the Fusion design's
export default. Set `intercept_native_save` to `false` to use the toolbar independently
of native Save. `thumbnail` and `open_folder` can be disabled for routine work.
Set `prompt_revision_name` to `false` to save numbered revisions without the description
prompt. With the default `true`, each save offers a new, optional description; existing
revision folders are never renamed by that prompt.

`zenexport.log` lives beside config, with rotation at approximately 2 MB and three
backup logs. Configuration writes use temporary files and atomic replacement. Invalid
configuration stops startup with an error rather than silently discarding saved paths.
Version directory reservation handles concurrent claims. The per-user context file is
intended for a single active ZenExport runtime; use separate `ZENEXPORT_DATA_DIR`
locations if running independent Fusion instances concurrently.

## Migration and limitations

- Existing `session_config.json` bindings are copied to the per-user configuration's
  `legacy_contexts` on startup. The original file is preserved and never distributed.
  Old archives without attributes resume by their recorded name after stripping the
  trailing Fusion version and archive extension, e.g. `patterns_v01` resumes `patterns`.
  Matching duplicate records are consolidated by destination; the only existing match
  is reused. Multiple existing matches offer a numbered selection of saved folders.
- Legacy name/revision lookup is limited to migration. On the next export the design
  receives a stable context UUID before F3D creation. Reopening older archives reuses
  that migrated identity. Generic Untitled names do not automatically select another
  document's project; an exact old revision binding can recover the original tab.
- A known folder that is unavailable is reported without initializing a replacement
  project. Reconnect its drive or explicitly choose a destination.
- A context UUID travels in the design; the local store takes precedence over paths in
  older archives. Deliberately copying a design can also copy its context. Choose
  Destination creates an independent context for a fork.
- Local F3D export does not perform a native/cloud document save, rename an Untitled
  tab, or guarantee clearing Fusion's modified flag. Closing the document can still
  produce Fusion's native save prompt.
- External references, different linked revisions, configurations, and F3D/F3Z recovery
  need live validation. Failed translator calls are reported; no automatic unlinking or
  dependency conversion is performed.
- Per-body STL export handles BRep bodies. Mesh bodies and drawings are outside this
  per-part workflow. Native Save is not intercepted when no active Design is available.
- Non-empty files and a successful API return do not prove semantic validity. Reopen
  exported files in Fusion to validate geometry, history, units, and references.
- No automatic deletion or retention pruning is enabled. Each full snapshot costs disk
  space, and new files consume fresh version numbers even after partial attempts.

## Development checks

The production runtime uses only Python's standard library plus Fusion's bundled
`adsk` API. Python 3.10+ is required; tests were run locally on 3.11 and 3.13.

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.13 -m compileall -q ZenExport.py zenexport tools tests
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install ruff==0.14.1
./.venv/Scripts/python.exe -m ruff check .
py -3.13 tools/build_bundle.py
```

To inspect compatibility with a particular Fusion installation without loading its
native libraries:

```powershell
py -3.13 tools/verify_fusion_api.py "<Fusion installation>/API/Python/packages/adsk"
```

This checks member existence, not native behavior. CI runs lint, tests, compilation,
and deterministic bundle creation on Windows. See [HOW_TO_BUILD_MSI.md](HOW_TO_BUILD_MSI.md)
for distribution. Check the repository's Actions tab for the current CI result.
No native installer build has been performed.

## Live acceptance checklist (pending)

Use a temporary project and retain a separate known-good backup.

- Load, stop, and reload twice; confirm one pair of toolbar commands and no duplicate
  save interception. Test native Save with interception enabled and disabled.
- Export two separate Untitled documents to different folders; edit and switch tabs.
- Reopen the very first exported F3D and confirm that the destination is remembered.
- Change a parameter value without adding timeline items; confirm a new version.
- Test repeated, renamed, same-name, and nested hidden components; inspect body counts
  and STL coordinates, units, and visibility.
- Force an export or filesystem failure; verify partial status and a successful retry.
- Test cancellation, missing destinations, and linked assemblies; reopen F3D and STEP
  and compare geometry and parametric history with the source.
- Measure full/cad/backup profiles on representative small and large projects. Use
  per-format durations in the export manifest before drawing performance conclusions.
