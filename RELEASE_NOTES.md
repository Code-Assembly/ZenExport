# ZenExport 6.1.1 preview

Free and open source under the MIT license. Shared by EsKay-Labs as a gift to the
Fusion and 3D-printing community.

## Changes

- Matching named revisions under `CAD/vNN_description`, `Models/vNN_description`,
  and `_Info/vNN_description`; all STEP/F3D files stay under CAD.
- Optional revision descriptions on each new save. Renaming existing revisions
  through a dedicated command is not implemented.
- Remembered design destinations, portable context identity, and migration of older
  project bindings without repeatedly asking for a new folder.
- Main-thread exports without custom-event posting; protection against duplicate
  exports during reentrant Save events.
- Staged outputs, truthful success/partial/cancelled reports, per-file timings,
  and success markers that advance only after all required files succeed.
- Conflict-checked migration of older layouts, preserved native file bytes,
  original report backups, and a resumable metadata-update journal.
- Modular runtime, full/cad/backup profiles, automated tests, and Windows CI.
- Portable ZIP with source, installation instructions, MIT license, and SHA-256 checksum.

## Download and install

Download `ZenExport-6.1.1.zip` and optionally verify it against its `.sha256` file.
Extract it, copy `ZenExport.bundle/Contents` into a folder named `ZenExport`, and
add that folder through Fusion's Scripts and Add-Ins dialog. Stop older copies
before starting this one. The ZIP README contains the full instructions.

## Verification and limits

63 automated tests pass locally. Lint, bytecode compilation, and deterministic ZIP
packaging pass. Earlier 6.0.3/6.1.0 exports succeeded in the local Fusion session.
The final 6.1.1 save workflow and recovery by reopening F3D/STEP still need live
validation. macOS and MSI installation have not been verified; no MSI is supplied.

This is a preview: start with a disposable design and retain separate known-good
backups. Local export does not perform Fusion's native/cloud save or guarantee
clearing its modified flag. Native Save interception is enabled by default and
can be disabled in settings. STLs are visible native BRep parts in component
coordinates. Linked assemblies and external references need additional recovery
validation. The add-in does not change Autodesk licensing limits.
