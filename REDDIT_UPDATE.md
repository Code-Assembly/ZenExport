# ZenExport 6.1.1 update draft

Use only in an existing relevant thread if its community permits a project update.
This file does not mean the update has been posted.

I'm the creator of ZenExport. I've published a 6.1.1 preview with a revised local
export workflow, and I'm sharing it free under the MIT license.

- Matching named revisions under CAD (F3D/STEP) and Models (visible native-body STL).
- Optional descriptions such as `v05_M6 holes` on each new save.
- Remembered destinations, including recovery of older project bindings.
- Staged file writes, per-file results, and reports under _Info.
- Every requested export creates a new revision; count-based save skipping is gone.

The 63 automated tests pass locally. Full recovery checks by reopening exports
remain pending, so start on a disposable design and keep your normal backups.
Local export does not perform Fusion's native/cloud save or change its licensing.
STLs are native parts in component coordinates, not placed assembly instances.

https://github.com/EsKay-Labs/ZenExport/releases/tag/v6.1.1
