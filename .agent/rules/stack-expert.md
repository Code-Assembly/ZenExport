---
trigger: always_on
---

# 🧠 STACK EXPERT (BEST PRACTICES)

> **RULE:** Consult this for syntax and library usage.

- **Fusion 360 Python API:** Use `adsk.core` and `adsk.fusion`.
- **Application Context:** `app = adsk.core.Application.get()`, `ui = app.userInterface`, `doc = app.activeDocument`
- **Error Handling:** Always wrap API calls in `try...except` and log errors to avoid crashing Fusion 360 silently. Use `traceback.format_exc()` for debugging.
- **Event Handlers:** Keep `_handlers` array global so event handler objects are not garbage collected by Python.
- **UI Dialogs:** Use `ui.messageBox` and `ui.createFolderDialog()` for interactions.
- **File System:** Use `os` and `json` for configuration management. Use `os.path.join` for cross-platform compatibility.
- **UI Commands:** Remember to clean up old commands using `cmdDef.deleteMe()` before creating a new one in the `run()` method.
