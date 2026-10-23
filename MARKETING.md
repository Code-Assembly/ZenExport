# ZenExport community sharing kit

Publication drafts, not a record of completed posts. Disclose ownership and check
each community's current rules and your posting history before submitting.

## Open-source community

Title: ZenExport: an MIT-licensed Fusion add-in for versioned F3D/STEP and STL exports

I'm sharing ZenExport, my free, MIT-licensed Python add-in for Autodesk Fusion,
as a gift to the CAD and 3D-printing community.

It groups each requested export into matching revision folders:

```text
MyProject/
  CAD/v05_M6 holes/       # F3D + STEP, including component CAD exports
  Models/v05_M6 holes/    # visible native BRep bodies as STL
  _Info/v05_M6 holes/     # preview, file results and timings
```

It remembers a design's destination, offers an optional description on each save,
and creates a fresh numbered revision. The latest refactor adds staged file writes,
partial-failure reporting, legacy destination recovery, and layout migration.
The add-in runtime uses Python's standard library plus Fusion's API.

6.1.1 is a preview. The 63 automated tests pass locally, but full recovery checks
by reopening the exported files are still pending. Try a disposable design first.
Local export does not perform Fusion's native/cloud save or change Autodesk's
licensing limits. STLs use native component coordinates.

Source and instructions: https://github.com/EsKay-Labs/ZenExport

Preview download: https://github.com/EsKay-Labs/ZenExport/releases/tag/v6.1.1

## Maker forum

Title: A free Fusion tool for keeping matching CAD and STL revisions

I made ZenExport for the repetitive step between editing a Fusion design and
preparing files for printing, and I'm sharing it free under the MIT license.

One export creates a numbered F3D/STEP snapshot under CAD and the matching visible
native-body STLs under Models. You can label the revision, for example "M6 holes",
and the same label appears in both folders. Preview images and export reports stay
separate under _Info. Existing revisions are retained.

The current 6.1.1 preview includes 63 passing automated tests. Live recovery checks
are still pending, so start with a disposable design and retain your usual backups.
STLs are individual parts in component coordinates. This does not perform a native
Fusion save or replace Autodesk's licensing requirements.

Source, download and instructions: https://github.com/EsKay-Labs/ZenExport

## Short announcement

ZenExport 6.1.1 preview is available: a free MIT-licensed Fusion add-in for matching
named CAD/STL revisions, local F3D/STEP exports, and export reports. Shared by
EsKay-Labs as a gift to the maker community. Full exported-file recovery validation
is still pending. https://github.com/EsKay-Labs/ZenExport

## Publication constraints checked on 2026-10-24

- r/Fusion360: the visible rule prohibits self-promotion and product promotion.
  Do not publish a promotional post without moderator permission.
- r/opensource: its low-effort rule explicitly prohibits AI-generated content;
  do not submit these AI-assisted drafts there.
  https://www.reddit.com/r/opensource/
- r/maker: self-promotional posts are prohibited.
  https://www.reddit.com/r/maker/
- r/3Dprinting: the community rules prohibit software posts seeking beta testers
  or feedback. Do not post this preview announcement there.
  https://www.reddit.com/r/3Dprinting/wiki/communityrules/
- Prusa forum: the guidelines prohibit spam and unapproved self-promotion.
  Obtain moderator clearance before a promotional announcement.
  https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/prusa-forum-guidelines-and-rules/

A free license is not an exemption from community rules. Do not claim "best",
guaranteed backups, instant exports, licensing-limit bypasses, or automatic cloud saves.
