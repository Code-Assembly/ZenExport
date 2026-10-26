Hey everyone! 👋

A while back, I shared **ZenExport**, a tool I made for my Autodesk Fusion and
3D-printing workflow.

I've been using it for quite a while with good results, and I've recently made
some useful updates. 🛠️

## ⌨️ CTRL + S → local CAD + STL revisions

With ZenExport's Save interception enabled, **press CTRL + S** to export your
active design into a fresh local revision.

No need to repeat the F3D, STEP and individual-part STL exports manually after every change.

```text
          ⌨️ CTRL + S
                │
       🏷️ Optional revision note
                │
        📁 MyProjectFolder/
                │
                ├── CAD/
                │   └── v05_M6 holes/
                │       └── F3D + STEP
                │
                ├── Models/
                │   └── v05_M6 holes/
                │       └── STL files
                │
                └── _Info/
                    └── v05_M6 holes/
                        └── Preview + reports
```

Here's what you get:

- 💾 **F3D + STEP snapshots** — keep your editable Fusion archive and a STEP copy.
- 🖨️ **Individual STLs** — export visible solid bodies into separate files for slicing.
- 🔢 **Automatic revisions** — each ZenExport save gets a fresh number.
- 🏷️ **Meaningful names** — add descriptions like `M6 holes`, `longer bracket`, or `better clearance`.
- 📂 **Remembered destination** — choose your project folder initially; subsequent saves reuse it.
- 📸 **Viewport preview** — quickly recognize the design in each revision.

Prefer fewer prompts? Turn off the optional description prompt and **CTRL + S
creates numbered revisions without asking for a description.** ⚡

The recent updates improve folder organization, recovery of older project
destinations, and reporting when an export fails.

🎁 **Free and open source — a small gift from me to fellow makers.**

👉 Source, download and installation:
https://github.com/EsKay-Labs/ZenExport

ℹ️ With interception enabled, CTRL + S runs ZenExport's local exports instead of
Fusion's native/cloud save. You can disable interception in settings. The latest
6.1.1 update is a preview while exported-file recovery checks are completed;
keep your normal backups. STLs use native component coordinates. I used AI
assistance for the recent refactor and tests.
