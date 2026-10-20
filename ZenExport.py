"""ZenExport v5.2 - Fusion 360 Script for Local Design Backup.

This script automates exporting Fusion 360 designs locally with:
- Auto-Versioning: Saves numbered history (v01, v02) for CAD files
- Context Binding: Resumes project path per-design (Multi-Tab Support)
- Thumbnails: Generates viewport preview image
- Auto-Open: Launches folder after export
- Smart Save: Hashing to prevent redundant saves

Author: ZenExport (Generated via GEMINI.md)
Version: 5.2 (Context Aware)
"""

import adsk.core
import adsk.fusion
import traceback
import os
import json
import re
import glob
import sys
import subprocess
import hashlib

# ============================================================================
# CONSTANTS & GLOBALS
# ============================================================================

CMD_ID = "ZenExport_Cmd_v5" # Updated ID to force refresh
CMD_NAME = "ZenExport Save"
CMD_DESC = "Saves versioned backup locally (Ctrl+S override)."
ResourcesFolder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources")
CONFIG_FILENAME = "session_config.json"
PROJECT_FILENAME = "zenexport.json"
ATTR_GROUP = "ZenExport"
MESH_REFINEMENT = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
LOG_MAX_BYTES = 512 * 1024
LOG_CMD_ID = "ZenExport_DebugLog"
LOG_CMD_NAME = "ZenExport Debug Log"
LOG_CMD_DESC = "Writes zenexport_debug.log next to the add-in."
ADDINS_PANEL_ID = "SolidScriptsAddinsPanel" # Utilities > Add-Ins

# Global Event Handlers
_handlers = []
_debug_log = False

# ============================================================================
# LOGGING HELPER
# ============================================================================

def get_log_path() -> str:
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "zenexport_debug.log")

def log_to_console(app: adsk.core.Application, message: str) -> None:
    try:
        text_palette = app.userInterface.palettes.itemById("TextCommands")
        if text_palette:
            text_palette.writeText(f"[ZenExport] {message}")
    except: pass

    if not _debug_log: return
    try:
        path = get_log_path()
        # Keep one previous log, so both files together stay near 2x LOG_MAX_BYTES
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as f:
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except: pass

# ============================================================================
# CONFIGURATION & CONTEXT BINDING
# ============================================================================

def get_config_path() -> str:
    script_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(script_dir, CONFIG_FILENAME)

def load_config() -> dict:
    path = get_config_path()
    if not os.path.exists(path): return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_config_file(data: dict) -> None:
    path = get_config_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except: pass

def read_project(folder: str) -> dict | None:
    path = os.path.join(folder, PROJECT_FILENAME)
    if not os.path.exists(path): return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def write_project(folder: str, name: str, hash_val: str) -> None:
    try:
        with open(os.path.join(folder, PROJECT_FILENAME), 'w', encoding='utf-8') as f:
            json.dump({"name": name, "hash": hash_val}, f, indent=4)
    except Exception as e:
        log_to_console(adsk.core.Application.get(), f"Project File Err: {e}")

def bind_design(design: adsk.fusion.Design, project_name: str, root_folder: str) -> None:
    try:
        design.attributes.add(ATTR_GROUP, "root", root_folder)
        design.attributes.add(ATTR_GROUP, "name", project_name)
        # Fusion only allows renaming before the first cloud save
        doc = design.parentDocument
        if not doc.isSaved and doc.name != project_name: doc.name = project_name
    except Exception as e:
        log_to_console(adsk.core.Application.get(), f"Bind Err: {e}")

def get_context_for_design(design: adsk.fusion.Design) -> dict | None:
    """Retrieves context using design attributes or Name."""
    cfg = load_config()
    contexts = cfg.get("contexts", {})
    
    # 1. Attributes travel inside every exported .f3d, so they survive reopening and renames
    try:
        attr = design.attributes.itemByName(ATTR_GROUP, "root")
        proj = read_project(attr.value) if attr else None
        if proj: return dict(proj, root=attr.value)
    except: pass
    
    # 2. Try Name (Fallback for fresh open of saved files where GUID changed)
    try:
        full_name = design.parentDocument.name
        # Regex to strip version suffix like _v01, _v1,  v01,  v1
        # Captures "MyProject" from "MyProject_v05" or "MyProject v5"
        match = re.search(r'^(.*?)[\s_]v\d+$', full_name, re.IGNORECASE)
        if match:
             name_key = sanitize_filename(match.group(1))
        else:
             name_key = sanitize_filename(full_name)
             
        # Debug Log (checking regex capture)
        if match: log_to_console(adsk.core.Application.get(), f"Parsed Key: {name_key}")
             
    except:
        return None
        
    return contexts.get(name_key)

def update_context_for_design(design: adsk.fusion.Design, project_name: str, root_folder: str, hash_val: str) -> None:
    """Updates context binding for a specific design."""
    cfg = load_config()
    # Drop old Revision ID keys: the ID changes on every edit, so they never match again
    cfg["contexts"] = {k: v for k, v in cfg.get("contexts", {}).items() if k == v.get("name")}
    
    # We will store a secondary key if name is valid
    if project_name != "Untitled":
         cfg["contexts"][project_name] = {
            "root": root_folder,
            "hash": hash_val,
             "name": project_name
        }
    
    # Legacy fallback for single-mode
    cfg["last_save_directory"] = root_folder
    
    save_config_file(cfg)

# ============================================================================
# UTILS & VERSIONING
# ============================================================================

def sanitize_filename(name: str) -> str:
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, "_")
    return name

def is_shift_held() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
    except:
        return False

def open_folder(path: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        os.startfile(path)

def ensure_folder_exists(app: adsk.core.Application, folder_path: str) -> None:
    if not os.path.exists(folder_path):
        log_to_console(app, f"Creating directory: {folder_path}")
        os.makedirs(folder_path, exist_ok=True)

def get_next_version_number(cad_folder: str) -> int:
    if not os.path.exists(cad_folder):
        return 1
    items = os.listdir(cad_folder)
    versions = []
    regex = re.compile(r'^v(\d+)$')
    for item in items:
        if os.path.isdir(os.path.join(cad_folder, item)):
            match = regex.match(item)
            if match:
                versions.append(int(match.group(1)))
    return (max(versions) + 1) if versions else 1

# ============================================================================
# STATE TRACKING & FEEDBACK
# ============================================================================

def get_design_hash(design: adsk.fusion.Design) -> str:
    try:
        h = hashlib.sha1()
        def add(*vals):
            h.update(("|".join(str(v) for v in vals) + "\n").encode("utf-8"))

        # Direct-modelling designs have no timeline
        if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            tl = design.timeline
            add(tl.count, tl.markerPosition)
            for i in range(tl.count):
                item = tl.item(i)
                add(item.name, item.isSuppressed)
        for p in design.allParameters:
            add(p.name, p.expression, round(p.value, 6))
        for comp in design.allComponents:
            for b in comp.bRepBodies:
                add(comp.name, b.name, b.isVisible, round(b.volume, 6), round(b.area, 6), b.vertices.count)
        add(design.rootComponent.allOccurrences.count)
        return h.hexdigest()
    except:
        return "ERROR"

def show_success_feedback(ui, mode, res, path):
    f3d_icon = '✅' if res['f3d'] else '❌'
    step_icon = '✅' if res['step'] else '❌'
    
    msg = f"ZenExport {mode} Complete!\n"
    msg += f"Saved to: {path}\n\n"
    msg += f"Version: {res['version']}\n"
    msg += f"• F3D: {f3d_icon}\n"
    msg += f"• STEP: {step_icon}\n"
    msg += f"• STLs: {res['stl_ok']} exported ({res['stl_fail']} failed)"
    
    ui.messageBox(msg, f"ZenExport {mode}")

# ============================================================================
# EXPORT LOGIC
# ============================================================================

def save_thumbnail(app: adsk.core.Application, folder: str) -> bool:
    try:
        viewport = app.activeViewport
        path = os.path.join(folder, "_preview.png")
        viewport.saveAsImageFile(path, 400, 400)
        return True
    except:
        return False

def write_note(app, folder: str, note: str) -> None:
    fname = sanitize_filename(note).strip(" .")[:100].rstrip(" .")
    if not fname: return
    try:
        with open(os.path.join(folder, f"{fname}.txt"), "w", encoding="utf-8") as f:
            f.write(note.strip())
    except Exception as e:
        log_to_console(app, f"Note Err: {e}")

def export_cad_files(app, design, cad_folder, versioned_name) -> tuple[bool, bool]:
    export_mgr = design.exportManager
    f3d_path = os.path.join(cad_folder, f"{versioned_name}.f3d")
    f3d_ok = False
    try:
        opts = export_mgr.createFusionArchiveExportOptions(f3d_path)
        f3d_ok = export_mgr.execute(opts)
    except Exception as e:
        log_to_console(app, f"F3D Err: {e}")

    step_path = os.path.join(cad_folder, f"{versioned_name}.step")
    step_ok = False
    try:
        opts = export_mgr.createSTEPExportOptions(step_path)
        step_ok = export_mgr.execute(opts)
    except Exception as e:
        log_to_console(app, f"STEP Err: {e}")

    return f3d_ok, step_ok

def export_stl_files(app, design, bodies, models_folder) -> tuple[int, int]:
    export_mgr = design.exportManager
    s, f = 0, 0
    used = set()
    for name, body in bodies:
        base = f"{name}_{body.name}" if name else body.name
        fname = sanitize_filename(f"{base}.stl")
        n = 2
        # Lowercase: macOS and Windows filesystems ignore case
        while fname.lower() in used:
            fname = sanitize_filename(f"{base} ({n}).stl")
            n += 1
        used.add(fname.lower())
        path = os.path.join(models_folder, fname)
        try:
            opts = export_mgr.createSTLExportOptions(body, path)
            opts.meshRefinement = MESH_REFINEMENT
            if export_mgr.execute(opts): s += 1
            else: f += 1
        except: f += 1
    return s, f

def collect_bodies(design) -> list:
    bodies = []
    # Occurrence bodies are proxies in root context, so STLs keep their assembly position
    def traverse(occs, prefix=""):
        for occ in occs:
            if not occ.isVisible: continue
            name = f"{prefix}_{occ.component.name}" if prefix else occ.component.name
            for b in occ.bRepBodies:
                if b.isVisible: bodies.append((name, b))
            traverse(occ.childOccurrences, name)
    root = design.rootComponent
    for b in root.bRepBodies:
        if b.isVisible: bodies.append(("", b))
    traverse(root.occurrences)
    return bodies

def perform_sync_export(app, design, project_folder, project_name, note="") -> dict:
    cad_folder = os.path.join(project_folder, "CAD")
    models_folder = os.path.join(project_folder, "Models")
    ensure_folder_exists(app, cad_folder)
    ensure_folder_exists(app, models_folder)
    
    save_thumbnail(app, project_folder)
    
    ver_num = get_next_version_number(cad_folder)
    ver_lbl = f"v{ver_num:02d}"
    versioned_name = f"{project_name}_{ver_lbl}"
    target_cad = os.path.join(cad_folder, ver_lbl)
    ensure_folder_exists(app, target_cad)
    
    f3d, step = export_cad_files(app, design, target_cad, versioned_name)
    write_note(app, target_cad, note)
    bodies = collect_bodies(design)
    stl_s, stl_f = 0, 0
    if bodies: stl_s, stl_f = export_stl_files(app, design, bodies, models_folder)
    
    # Returning plain dict (NO F3D PATH needed since no Auto-Swap)
    return {'f3d': f3d, 'step': step, 'stl_ok': stl_s, 'stl_fail': stl_f, 'version': versioned_name, 'proj_root': project_folder}

# ============================================================================
# CORE LOGIC
# ============================================================================

def run_zen_export_logic(app, design, mode_override=None):
    ui = app.userInterface
    doc = app.activeDocument
    
    # 1. PREREQUISITE CHECK (Soft)
    # We allow "Untitled" or unsaved files to proceed to INIT mode.
    # The user wants to "Save" them via ZenExport.
    
    full_name = doc.name
    # Strict Name Parsing via Regex (Handles " Name v1" and "Name_v01")
    match = re.search(r'^(.*?)[\s_]v\d+$', full_name, re.IGNORECASE)
    if match:
        design_name = sanitize_filename(match.group(1))
    else:
        design_name = sanitize_filename(full_name)
    
    # If Untitled, we handle in INIT flow
    
    current_hash = get_design_hash(design)
    
    project_folder = ""
    project_name = ""
    mode = "INIT"
    last_hash = ""
    
    # 2. LOGIC FORKING (Disk-Based Check)
    # First, consult session memory for a "Known Location" for this design
    ctx = get_context_for_design(design)
    
    # Override logic
    shift = is_shift_held()
    if shift or mode_override == "INIT":
        mode = "INIT"
    elif ctx:
         # CANDIDATE Path found. Now Validate on DISK.
         candidate_root = ctx.get("root", "")
         if candidate_root and os.path.exists(candidate_root):
             # Condition A: Folder Exists -> Incremental Update
             mode = "UPDATE"
             project_folder = candidate_root
             project_name = ctx.get("name", design_name) # Use stored name if available
             last_hash = ctx.get("hash", "")
             log_to_console(app, f"Context Validated: '{design_name}' -> {project_folder}")
         else:
             # Condition B: Folder Missing (Deleted?) -> Trigger Init
             log_to_console(app, f"Context Invalid/Missing: '{candidate_root}' -> Re-initializing")
             mode = "INIT"
    
    # 3. Dirty Flag Check (Only for Updates)
    if mode == "UPDATE":
        if current_hash == last_hash:
            answer = ui.messageBox("No changes detected since last ZenExport.\nSave a new version anyway?", "ZenExport",
                                   adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                                   adsk.core.MessageBoxIconTypes.QuestionIconType)
            if answer != adsk.core.DialogResults.DialogYes: return

    # 4. INITIALIZATION (New / Lost Context)
    if mode == "INIT":
        # We need to establish a location.
        dlg = ui.createFolderDialog()
        dlg.title = f"ZenExport: Select Location for '{design_name}'"
        if dlg.showDialog() != adsk.core.DialogResults.DialogOK: return
        base_dir = dlg.folder

        # Picked a project folder itself: adopt it without asking for a name
        proj = read_project(base_dir)
        if proj:
            project_folder = base_dir
            project_name = proj.get("name") or sanitize_filename(os.path.basename(base_dir))
            log_to_console(app, f"Adopting project: {project_folder}")
        else:
            # Determine Project Name (Default to Design Name)
            # If Untitled, default to MyProduct or empty
            def_name = design_name if design_name not in ("Untitled", "(Unsaved)") else "MyProduct"

            res = ui.inputBox("Confirm Project Folder Name:", "ZenExport Setup", def_name)
            if res[1]: return
            project_name = sanitize_filename(res[0])
            if not project_name: return

            project_folder = os.path.join(base_dir, project_name)

            # Check if we are "adopting" an existing folder
            proj = read_project(project_folder)
            if proj:
                project_name = proj.get("name") or project_name
                log_to_console(app, f"Adopting project: {project_folder}")
            elif os.path.exists(project_folder):
                 log_to_console(app, "Adopting existing folder structure.")

    # 4b. VERSION NOTE (Cancel aborts the save)
    note_res = ui.inputBox("Version note (optional):", "ZenExport", "")
    if note_res[1]: return

    # 5. EXECUTION (bind first so the attributes are saved into the exported .f3d)
    bind_design(design, project_name, project_folder)
    res = perform_sync_export(app, design, project_folder, project_name, note_res[0])
    
    # 6. CONTEXT BINDING (Update Record)
    if res['f3d']: write_project(project_folder, project_name, current_hash)
    update_context_for_design(design, project_name, project_folder, current_hash)
    
    # 7. FEEDBACK & AUTO-OPEN
    if not res['f3d'] and not res['step']:
        ui.messageBox(f"ZenExport failed: no .f3d or .step written for {res['version']}.\nSee the Text Commands panel for the error.",
                      "ZenExport", adsk.core.MessageBoxButtonTypes.OKButtonType,
                      adsk.core.MessageBoxIconTypes.CriticalIconType)
        return

    try: open_folder(project_folder)
    except: pass
         
    show_success_feedback(ui, mode, res, project_folder)


# ============================================================================
# EVENT HANDLERS
# ============================================================================

class ZenExportCommandStartingHandler(adsk.core.ApplicationCommandEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        try:
            cmd_id = args.commandId
            app = adsk.core.Application.get()
            TARGET_CMDS = ["PLM360SaveCommand", "FusionSaveCommand", "FileSave", "Save"]
            
            if cmd_id in TARGET_CMDS:
                log_to_console(app, f"🚫 Intercepted: {cmd_id}")
                args.isCanceled = True
                design = adsk.fusion.Design.cast(app.activeProduct)
                if design: run_zen_export_logic(app, design)
        except Exception as e:
            log_to_console(app, f"Interceptor Err: {e}")

class ZenExportCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            onExecute = ZenExportExecuteHandler() 
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except: pass

class ZenExportExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            design = adsk.fusion.Design.cast(app.activeProduct)
            if design: run_zen_export_logic(app, design)
        except: pass

class ZenExportLogCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        try:
            onExecute = ZenExportLogExecuteHandler()
            args.command.execute.add(onExecute)
            _handlers.append(onExecute)
        except: pass

class ZenExportLogExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        global _debug_log
        try:
            _debug_log = args.command.parentCommandDefinition.controlDefinition.isChecked
            cfg = load_config()
            cfg["debug_log"] = _debug_log
            save_config_file(cfg)
            log_to_console(adsk.core.Application.get(), f"Debug log {'on' if _debug_log else 'off'}: {get_log_path()}")
        except: pass

class ZenExportDocumentActivatedHandler(adsk.core.DocumentEventHandler):
    def __init__(self): super().__init__()
    def notify(self, args):
        pass

# ============================================================================
# MAIN
# ============================================================================

def remove_log_toggle(ui) -> None:
    panel = ui.allToolbarPanels.itemById(ADDINS_PANEL_ID)
    control = panel.controls.itemById(LOG_CMD_ID) if panel else None
    if control: control.deleteMe()
    logDef = ui.commandDefinitions.itemById(LOG_CMD_ID)
    if logDef: logDef.deleteMe()

def run(context):
    global _debug_log
    try:
        _debug_log = load_config().get("debug_log", False)
        app = adsk.core.Application.get()
        ui = app.userInterface
        log_to_console(app, "ZenExport Starting...")
        
        cmdDef = ui.commandDefinitions.itemById(CMD_ID)
        if cmdDef: cmdDef.deleteMe()
        
        if not os.path.exists(ResourcesFolder):
            try: os.makedirs(ResourcesFolder)
            except: pass
            
        cmdDef = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESC, ResourcesFolder)
        cmdDef.hotKey = "Ctrl+S"
        
        onCreated = ZenExportCommandCreatedHandler()
        cmdDef.commandCreated.add(onCreated) 
        _handlers.append(onCreated)
        
        onStarting = ZenExportCommandStartingHandler()
        ui.commandStarting.add(onStarting)
        _handlers.append(onStarting)
        
        onActivated = ZenExportDocumentActivatedHandler()
        app.documentActivated.add(onActivated)
        _handlers.append(onActivated)
        
        remove_log_toggle(ui)
        logDef = ui.commandDefinitions.addCheckBoxDefinition(LOG_CMD_ID, LOG_CMD_NAME, LOG_CMD_DESC, _debug_log)
        onLogCreated = ZenExportLogCreatedHandler()
        logDef.commandCreated.add(onLogCreated)
        _handlers.append(onLogCreated)
        panel = ui.allToolbarPanels.itemById(ADDINS_PANEL_ID)
        if panel: panel.controls.addCommand(logDef)
        
        log_to_console(app, "ZenExport Ready.")
        
    except:
        app = adsk.core.Application.get()
        if app.userInterface:
            app.userInterface.messageBox(f"Start Failed:\n{traceback.format_exc()}")

def stop(context):
    try:
        app = adsk.core.Application.get()
        if app.userInterface:
            cmdDef = app.userInterface.commandDefinitions.itemById(CMD_ID)
            if cmdDef: cmdDef.deleteMe()
            remove_log_toggle(app.userInterface)
        log_to_console(app, "ZenExport Stopped.")
    except: pass
