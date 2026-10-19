# 🏯 ZenExport v5.2

![License](https://img.shields.io/badge/License-MIT-green.svg) ![Fusion 360](https://img.shields.io/badge/Fusion%20360-Addin-orange.svg) ![Python](https://img.shields.io/badge/Python-3.x-blue.svg)

**The "Peace of Mind" Local Save Workflow for Fusion 360.**

ZenExport is a Fusion 360 Add-In that **replaces** the native Cloud Save (`Ctrl+S` on Windows, `Cmd+S` on macOS) with a powerful local asset manager. It forces a disciplined, organised folder structure on your hard drive, keeping your IP safe and your versions sane.

---

## ✨ Features that Spark Joy

- 🚫 **Ctrl+S / Cmd+S Override:** We intercept the native save command. No more "Cloud Save" dialogs. One press, one local backup.
- 🧠 **Smart Context Binding:**
  - Setup a project _once_. ZenExport stores the project inside the design itself, and drops a `zenexport.json` in the project folder.
  - Reopen any exported `.f3d`, press Save, and it goes to the right place. Every time.
  - Moved the folder? Pick it once and ZenExport picks up the numbering where it left off.
- 💾 **Incremental Versioning:** auto-saves as `Project_v01.f3d`, `Project_v02.f3d`... never overwriting history.
- 🚀 **Real Change Detection:** Fingerprints your design's DNA (Timeline, every Parameter including sketch dimensions, every Body's geometry). If nothing changed, it asks before saving a duplicate version.
- 📝 **Version Notes:** Type a short note on save (e.g. _reduced width to 10_) and it lands as `reduced width to 10.txt` next to that version. Leave it blank for no file.
- 📦 **Full Package Export:**
  - 📄 `.f3d` (Parametric Source)
  - 🛠️ `.step` (CAD Interchange)
  - 🗿 `.stl` (Resultant Mesh for every visible body)
  - 🖼️ `_preview.png` (Viewport Snapshot)
- 📂 **Auto-Open:** Opens the project folder after every save (Explorer or Finder) so you can grab your files immediately.
- 🍎 **Windows & macOS:** Works on both.

---

## 🛠️ Installation

1.  **Download** this folder.
2.  Move it to your Fusion 360 API folder:
    - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
    - **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
    - _(Ensure the folder is named `ZenExport` and contains `ZenExport.py` inside)_
3.  **Restart Fusion 360**.
4.  Go to **Utilities > Scripts and Add-Ins**, select `ZenExport`, and ensure **Run on Startup** is checked.

---

## 🎮 How to Use

### 1. The First Save (Initialization)

Open a new design. Press **`Ctrl+S`** (**`Cmd+S`** on macOS).

- ZenExport will ask: _"Where should this project live?"_
- Select a parent directory (e.g., `Desktop/MyProjects`).
- Confirm the **Project Name** (e.g., `TurboEncabulator`).
- Add an optional **Version Note**, or leave it blank.
- **Action:** It creates `.../TurboEncabulator/CAD/v01/`, runs the export, and renames the "Untitled" tab to `TurboEncabulator`.
- _Picked a folder that is already a ZenExport project (it has a `zenexport.json`)? It adopts it and skips the name prompt._

### 2. The Routine (Update)

Make some changes. Press **`Ctrl+S`**.

- **Action:** ZenExport detects the design changes and creates `v02` in the same folder. The only prompt is the optional note.
- _If no changes were made, it asks whether to save a new version anyway._
- _Cancel the note prompt to abort the save._

### 3. The "Resume" (Context Awareness)

- Close Fusion.
- Re-open your `TurboEncabulator_v02.f3d` file.
- Press **`Ctrl+S`**.
- **Action:** The `.f3d` remembers its project folder, so ZenExport resumes saving there as `v03`. No prompts.

### 4. Moving a Project

- Move or rename the project folder however you like.
- On the next save ZenExport can't find it, so it asks for a location.
- Pick the moved folder. It reads the `zenexport.json` inside and continues the numbering.

---

## 📂 Folder Structure

ZenExport enforces this clean layout:

```text
MyProject/
├── CAD/
│   ├── v01/
│   │   ├── MyProject_v01.f3d
│   │   └── MyProject_v01.step
│   └── v02/
│       ├── MyProject_v02.f3d
│       ├── MyProject_v02.step
│       └── reduced width to 10.txt
├── Models/
│   ├── Body1.stl
│   └── ComponentA_Body1.stl
├── _preview.png
└── zenexport.json
```

- `Models/` always holds the latest mesh of each visible body. Bodies in components are prefixed with the component name.
- `zenexport.json` marks the folder as a ZenExport project. Don't delete it.

---

## ⚠️ Known Limitations

- **Tab names:** ZenExport renames an "Untitled" tab to the project name, but Fusion still treats the design as unsaved. Rely on the file system names!
- **Local Only:** This script does NOT upload to the Autodesk Cloud.

---

_"Order is the sanity of the mind, the health of the body, the peace of the city."_
