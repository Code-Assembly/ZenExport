"""Autodesk adapter: owned event handlers and guarded main-thread exports."""

import os
from pathlib import Path
import subprocess
import sys
import uuid

import adsk.core
import adsk.fusion

from .config import (COMMAND_ID, COMMAND_NAME, DESTINATION_COMMAND_ID, PANEL_ID,
                     SAVE_COMMANDS, SETTING_TOGGLES, SETTINGS_COMMAND_ID, VERSION)
from .exporter import execute_export, plan_exports
from .layout import migrate_project_layout
from .model import bind_context, capture_snapshot, file_identity, resolve_context
from .paths import design_display_name, sanitize_filename
from .storage import AmbiguousLegacyContext, ContextStore, create_logger, runtime_directory


class ZenExportAddin:
    def __init__(self, source_directory):
        self.source_directory = Path(source_directory)
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        self.directory = runtime_directory()
        self.store = ContextStore(self.directory, self.source_directory / "session_config.json")
        self.logger = create_logger(self.directory, self.store.settings["debug_log"])
        self.bindings = []
        self.command_definitions = []
        self.controls = []
        self.running = False
        self.busy = False
        self.exporting_document = None

    def attach(self, event, base, callback, group=None):
        owner = self

        class Handler(base):
            def __init__(self):
                super().__init__()

            def notify(self, args):
                if not owner.running:
                    return
                try:
                    callback(args)
                except Exception as error:
                    owner.logger.exception("Event handler failed")
                    owner.ui.messageBox(f"ZenExport could not complete the request:\n{error}\n\n"
                                        f"See {owner.directory / 'zenexport.log'}", "ZenExport")

        handler = Handler()
        if not event.add(handler):
            raise RuntimeError("Fusion refused an event subscription")
        self.bindings.append((event, handler, group))

    def detach_group(self, group):
        for binding in list(self.bindings):
            event, handler, binding_group = binding
            if binding_group is group:
                try:
                    if not event.remove(handler):
                        self.logger.warning("Fusion did not remove a command event handler")
                except Exception:
                    self.logger.exception("Could not detach command event")
                self.bindings.remove(binding)

    def start(self):
        if not self.logger.handlers:
            self.logger = create_logger(self.directory, self.store.settings["debug_log"])
        self.running = True
        try:
            for command_id, name, force_new in (
                (COMMAND_ID, COMMAND_NAME, False),
                (DESTINATION_COMMAND_ID, "ZenExport: Choose Destination", True),
            ):
                previous = self.ui.commandDefinitions.itemById(command_id)
                if previous:
                    previous.deleteMe()
                definition = self.ui.commandDefinitions.addButtonDefinition(
                    command_id, name, "Create a versioned local design backup.", "")
                self.command_definitions.append(definition)
                self.attach(definition.commandCreated, adsk.core.CommandCreatedEventHandler,
                            lambda args, reset=force_new: self.on_command_created(args, reset))
                panel = self.ui.allToolbarPanels.itemById(PANEL_ID)
                if panel:
                    self.controls.append(panel.controls.addCommand(definition))
            try:
                self.add_settings_command()
            except Exception:
                # Settings are optional: Save interception must still start without them.
                self.logger.exception("Could not add the ZenExport: Settings command")
            if self.store.settings["intercept_native_save"]:
                self.attach(self.ui.commandStarting, adsk.core.ApplicationCommandEventHandler,
                            self.on_command_starting)
            self.logger.info("ZenExport %s started; settings=%s", VERSION, self.store.settings)
        except Exception:
            self.stop()
            raise

    def add_settings_command(self):
        previous = self.ui.commandDefinitions.itemById(SETTINGS_COMMAND_ID)
        if previous:
            previous.deleteMe()
        definition = self.ui.commandDefinitions.addButtonDefinition(
            SETTINGS_COMMAND_ID, "ZenExport: Settings", "Choose what ZenExport does on each save.", "")
        self.command_definitions.append(definition)
        self.attach(definition.commandCreated, adsk.core.CommandCreatedEventHandler, self.on_settings_created)
        panel = self.ui.allToolbarPanels.itemById(PANEL_ID)
        if panel:
            previous = panel.controls.itemById(SETTINGS_COMMAND_ID)
            if previous:
                previous.deleteMe()
            self.controls.append(panel.controls.addCommand(definition))

    def stop(self):
        self.running = False
        for event, handler, _ in reversed(self.bindings):
            try:
                if not event.remove(handler):
                    self.logger.warning("Fusion did not remove an event handler")
            except Exception:
                self.logger.exception("Could not detach event")
        self.bindings.clear()
        for obj in self.controls + self.command_definitions:
            try:
                if obj and obj.isValid:
                    obj.deleteMe()
            except Exception:
                self.logger.exception("Could not remove command UI")
        self.controls.clear()
        self.command_definitions.clear()
        self.logger.info("ZenExport stopped")
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

    def on_command_created(self, args, force_new):
        command = args.command
        command.isExecutedWhenPreEmpted = False
        self.attach(command.execute, adsk.core.CommandEventHandler,
                    lambda event: self.request_export(force_new), command)
        self.attach(command.destroy, adsk.core.CommandEventHandler,
                    lambda event: self.detach_group(command), command)

    def on_settings_created(self, args):
        command = args.command
        for key, label in SETTING_TOGGLES:
            command.commandInputs.addBoolValueInput(key, label, True, "", self.store.settings[key])
        self.attach(command.execute, adsk.core.CommandEventHandler,
                    lambda event: self.save_settings(event.command.commandInputs), command)
        self.attach(command.destroy, adsk.core.CommandEventHandler,
                    lambda event: self.detach_group(command), command)

    def save_settings(self, inputs):
        changes = {key: inputs.itemById(key).value for key, _ in SETTING_TOGGLES}
        self.store.update_settings(changes)
        self.logger = create_logger(self.directory, self.store.settings["debug_log"])
        self.logger.info("Settings saved: %s", changes)

    def on_command_starting(self, args):
        if args.commandId in SAVE_COMMANDS:
            self.request_export(self.shift_held(), save_args=args)

    def shift_held(self):
        if sys.platform != "win32":
            return False
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)

    def request_export(self, force_new=False, save_args=None):
        # Fusion invokes both command handlers on its main thread. This restores
        # the original synchronous entry path without depending on custom events.
        if not self.running:
            return False
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        document = self.app.activeDocument
        if not document or not document.isValid:
            return False
        if self.busy:
            same_document = self.exporting_document == document
            if same_document and save_args is not None:
                save_args.isCanceled = True
            self.logger.info("Ignored reentrant export request; same_document=%s", same_document)
            return same_document
        # Cancel only a valid design's Save, and do so before any dialogs/translators
        # can reenter Fusion. A different document's Save remains available.
        if save_args is not None:
            save_args.isCanceled = True
        self.busy = True
        self.exporting_document = document
        try:
            self.logger.info("Starting export; trigger=%s; document=%s; profile=%s",
                             "native_save" if save_args is not None else "toolbar",
                             document.name, self.store.settings["profile"])
            self.export(design, document, force_new)
        finally:
            self.busy = False
            self.exporting_document = None
        return True

    def choose_destination(self, document):
        name = design_display_name(document.name)
        dialog = self.ui.createFolderDialog()
        dialog.title = f"ZenExport: Select parent folder for {name}"
        if dialog.showDialog() != adsk.core.DialogResults.DialogOK:
            return None
        value, cancelled = self.ui.inputBox("Project folder name:", "ZenExport", name)
        if cancelled:
            return None
        name = sanitize_filename(value, fallback="")
        if not name:
            self.ui.messageBox("Enter a project name containing at least one valid character.", "ZenExport")
            return None
        folder = Path(dialog.folder) / name
        return folder.resolve(), name

    def export(self, design, document, force_new):
        try:
            context = None if force_new else resolve_context(design, self.store)
        except AmbiguousLegacyContext as error:
            options = "\n".join(f"{index}: {item['root']}"
                                for index, item in enumerate(error.candidates, 1))
            value, cancelled = self.ui.inputBox(
                f"Multiple saved folders match '{error.name}'.\n{options}\n\n"
                "Enter the number of the existing project to continue:", "ZenExport", "1")
            if cancelled:
                return
            try:
                choice = int(value)
            except ValueError:
                choice = 0
            if not 1 <= choice <= len(error.candidates):
                self.ui.messageBox("Select one of the listed project numbers.", "ZenExport")
                return
            context = error.candidates[choice - 1]
        if context:
            folder = Path(context["root"])
            if not folder.is_dir():
                self.ui.messageBox(f"The saved project folder is unavailable:\n{folder}\n\n"
                                   "Reconnect the drive or use ZenExport: Choose Destination.\n"
                                   "No new project was created.", "ZenExport")
                return
            name = sanitize_filename(context.get("name") or design_display_name(document.name))
            self.logger.info("Resuming saved project: %s", folder)
        else:
            destination = self.choose_destination(document)
            if destination is None:
                return
            folder, name = destination
        settings = self.store.settings
        revision_name = ""
        if settings["prompt_revision_name"]:
            revision_name, cancelled = self.ui.inputBox(
                "Revision description (optional):\n"
                "Example: M6 holes or wider base. Leave empty for a numbered revision.",
                "ZenExport - Revision", "")
            if cancelled:
                return
            revision_name = revision_name.strip()
        migration = migrate_project_layout(folder)
        self.store.relocate_manifests(migration["manifest_paths"])
        if migration["moved"]:
            self.logger.info("Organized %d existing files into paired revision folders", migration["moved"])
        context_id = bind_context(design, self.store, folder, name,
                                  str(uuid.uuid4()) if force_new else (context or {}).get("context_id"))
        snapshot = capture_snapshot(design, include_parts=settings["profile"] == "full")
        count = len(plan_exports(snapshot, name, "v00", settings))
        progress = self.ui.createProgressDialog()
        progress.cancelButtonText = "Stop after current file"
        progress.isCancelButtonShown = True
        progress.show("ZenExport", "Preparing export", 0, count, 0)

        def update(index, total, path):
            progress.progressValue = index
            progress.message = f"{index + 1}/{total}: {path}"
            return not progress.wasCancelled

        def write(job, filename):
            if not document.isValid or self.app.activeDocument != document:
                raise RuntimeError("The active document changed during export")
            if job.format == "png":
                return self.app.activeViewport.saveAsImageFile(filename, 400, 400)
            manager = design.exportManager
            if job.format == "stl":
                options = manager.createSTLExportOptions(job.geometry, filename)
                if options:
                    # STL carries no units. Slicers interpret coordinates as mm,
                    # while Fusion initializes this option from the design units.
                    options.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
                    levels = adsk.fusion.MeshRefinementSettings
                    options.meshRefinement = {
                        "low": levels.MeshRefinementLow,
                        "medium": levels.MeshRefinementMedium,
                        "high": levels.MeshRefinementHigh,
                    }[settings["mesh_quality"]]
                    options.sendToPrintUtility = False
            else:
                factory = (manager.createFusionArchiveExportOptions if job.format == "f3d"
                           else manager.createSTEPExportOptions)
                options = factory(filename, job.geometry) if job.geometry is not None else factory(filename)
            if options is None:
                raise RuntimeError(f"Fusion could not create {job.format} export options")
            return manager.execute(options)

        try:
            version_folder, report = execute_export(folder, name, snapshot, settings, write,
                                                     progress=update, logger=self.logger,
                                                     revision_name=revision_name)
        finally:
            progress.hide()
        if report["status"] == "success":
            self.store.record_success(context_id, folder / report["manifest"],
                                      snapshot.fingerprint, file_identity(document))
        self.logger.info("Export %s: %s (%.4fs)", version_folder, report["status"], report["seconds"])
        failures = sum(not item["success"] for item in report["files"])
        successes = sum(item["success"] for item in report["files"])
        title = {"success": "Complete", "partial": "Incomplete", "cancelled": "Cancelled"}[report["status"]]
        self.ui.messageBox(f"ZenExport: {title}\n{version_folder}\n\n"
                           f"Files: {successes}/{report['planned_files']} saved; {failures} failed.\n"
                           f"Duration: {report['seconds']:.1f}s\n"
                           f"Models: {report['folders']['models']}\n"
                           f"Details: {report['manifest']}", "ZenExport")
        if settings["open_folder"]:
            try:
                if sys.platform == "win32":
                    os.startfile(str(folder))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
            except Exception:
                self.logger.exception("Could not open export folder")
