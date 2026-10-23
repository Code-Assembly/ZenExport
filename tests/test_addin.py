"""Lifecycle and command routing against a small deterministic Autodesk adapter."""

import importlib
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fakes import Body, Component, design
from zenexport.model import bind_context
from zenexport.storage import atomic_json


class Event:
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)
        return True

    def remove(self, handler):
        self.handlers.remove(handler)
        return True

    def fire(self, args):
        for handler in list(self.handlers):
            handler.notify(args)


class Definition:
    def __init__(self):
        self.commandCreated = Event()
        self.isValid = True

    def deleteMe(self):
        self.isValid = False


class Definitions:
    def __init__(self):
        self.items = {}

    def itemById(self, key):
        value = self.items.get(key)
        return value if value and value.isValid else None

    def addButtonDefinition(self, key, name, description, resource):
        definition = Definition()
        self.items[key] = definition
        return definition


class Manager:
    def __init__(self):
        self.formats = []
        self.fail = False

    def createFusionArchiveExportOptions(self, filename, geometry=None):
        return SimpleNamespace(filename=filename, format="f3d")

    def createSTEPExportOptions(self, filename, geometry=None):
        return SimpleNamespace(filename=filename, format="step")

    def createSTLExportOptions(self, geometry, filename):
        return SimpleNamespace(filename=filename, format="stl")

    def execute(self, options):
        self.formats.append(options.format)
        if self.fail:
            return False
        Path(options.filename).write_bytes(b"mock-fusion-export")
        return True


class AddinTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ZENEXPORT_DATA_DIR": str(Path(self.temporary.name) / "state")})
        self.env.start()
        self.messages = []
        self.model = design(Component("Root", [Body("Body")]))
        self.manager = Manager()
        self.model.exportManager = self.manager
        ui = SimpleNamespace(commandDefinitions=Definitions(), commandStarting=Event(),
                             allToolbarPanels=SimpleNamespace(itemById=lambda key: None),
                             inputBox=Mock(return_value=("", False)),
                             messageBox=lambda *args: self.messages.append(args))
        progress = SimpleNamespace(wasCancelled=False, show=lambda *args: None, hide=lambda: None)
        ui.createProgressDialog = lambda: progress
        self.app = SimpleNamespace(userInterface=ui, activeProduct=self.model,
                                   activeDocument=self.model.parentDocument)
        # Reproduce the actual live failure: posting rejects every request, even
        # though registration/subscription can succeed. Exports must not use it.
        self.app.registerCustomEvent = Mock(return_value=Event())
        self.app.unregisterCustomEvent = Mock(return_value=True)
        self.app.fireCustomEvent = Mock(return_value=False)
        adsk = ModuleType("adsk")
        core = ModuleType("adsk.core")
        fusion = ModuleType("adsk.fusion")
        core.Application = SimpleNamespace(get=lambda: self.app)
        for name in ("CustomEventHandler", "ApplicationCommandEventHandler",
                     "CommandCreatedEventHandler", "CommandEventHandler"):
            setattr(core, name, object)
        fusion.Design = SimpleNamespace(cast=lambda value: value if value is self.model else None)
        fusion.MeshRefinementSettings = SimpleNamespace(MeshRefinementHigh=3, MeshRefinementMedium=2,
                                                        MeshRefinementLow=1)
        adsk.core, adsk.fusion = core, fusion
        self.modules = patch.dict(sys.modules, {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion})
        self.modules.start()
        sys.modules.pop("zenexport.addin", None)
        self.module = importlib.import_module("zenexport.addin")
        self.addin = self.module.ZenExportAddin(Path(self.temporary.name))
        # Host keyboard input must not change a simulated Save into Choose Destination.
        self.addin.shift_held = Mock(return_value=False)
        self.addin.store.settings.update(open_folder=False, thumbnail=False)
        bind_context(self.model, self.addin.store, self.temporary.name, "Test")
        self.addin.start()

    def tearDown(self):
        self.addin.stop()
        self.modules.stop()
        sys.modules.pop("zenexport.addin", None)
        self.env.stop()
        self.temporary.cleanup()

    def test_native_save_is_cancelled_before_exports_run_on_the_main_thread(self):
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        main_thread = threading.get_ident()
        original_execute = self.manager.execute

        def execute(options):
            self.assertTrue(args.isCanceled)
            self.assertEqual(threading.get_ident(), main_thread)
            return original_execute(options)

        self.manager.execute = execute
        self.addin.ui.commandStarting.fire(args)
        self.assertTrue(args.isCanceled)
        self.assertEqual(self.manager.formats, ["f3d", "step", "stl"])
        recorded = next(iter(self.addin.store.data["contexts"].values()))
        self.assertIn("v01", recorded["last_success_manifest"])

    def test_failure_never_advances_success_marker(self):
        self.manager.fail = True
        self.addin.request_export()
        recorded = next(iter(self.addin.store.data["contexts"].values()))
        self.assertNotIn("last_success_manifest", recorded)
        self.assertIn("Incomplete", self.messages[-1][0])

    def test_non_design_document_keeps_native_save(self):
        self.app.activeProduct = None
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        self.addin.ui.commandStarting.fire(args)
        self.assertFalse(args.isCanceled)
        self.assertEqual(self.manager.formats, [])

    def test_export_succeeds_without_using_the_rejected_custom_event_api(self):
        self.assertTrue(self.addin.request_export())
        self.assertEqual(self.manager.formats, ["f3d", "step", "stl"])
        self.addin.stop()
        self.app.registerCustomEvent.assert_not_called()
        self.app.fireCustomEvent.assert_not_called()
        self.app.unregisterCustomEvent.assert_not_called()

    def test_invalid_document_keeps_native_save_and_creates_no_export(self):
        self.app.activeDocument.isValid = False
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        self.addin.ui.commandStarting.fire(args)
        self.assertFalse(args.isCanceled)
        self.assertEqual(self.manager.formats, [])

    def test_sequential_saves_create_distinct_versions(self):
        self.addin.request_export()
        self.addin.request_export()
        revisions = Path(self.temporary.name) / "CAD"
        self.assertTrue((revisions / "v01/Test_v01.f3d").is_file())
        self.assertTrue((revisions / "v02/Test_v02.f3d").is_file())

    def test_reentrant_save_of_the_same_document_does_not_start_another_export(self):
        original_execute = self.manager.execute

        def execute(options):
            nested = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
            self.addin.ui.commandStarting.fire(nested)
            self.assertTrue(nested.isCanceled)
            return original_execute(options)

        self.manager.execute = execute
        self.addin.request_export()
        self.assertEqual(self.manager.formats, ["f3d", "step", "stl"])
        self.assertFalse((Path(self.temporary.name) / "CAD/v02").exists())

    def test_another_documents_native_save_is_available_during_export(self):
        self.addin.busy = True
        self.addin.exporting_document = self.app.activeDocument
        self.app.activeDocument = SimpleNamespace(isValid=True)
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        self.addin.ui.commandStarting.fire(args)
        self.assertFalse(args.isCanceled)
        self.assertEqual(self.manager.formats, [])

    def test_export_exception_releases_busy_state_and_displays_the_cause(self):
        self.addin.export = Mock(side_effect=RuntimeError("Destination unavailable"))
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        self.addin.ui.commandStarting.fire(args)
        self.assertTrue(args.isCanceled)
        self.assertFalse(self.addin.busy)
        self.assertIsNone(self.addin.exporting_document)
        self.assertIn("Destination unavailable", self.messages[-1][0])

    def test_toolbar_execute_exports_directly(self):
        command = SimpleNamespace(execute=Event(), destroy=Event())
        self.addin.on_command_created(SimpleNamespace(command=command), False)
        command.execute.fire(None)
        self.assertEqual(self.manager.formats, ["f3d", "step", "stl"])

    def test_legacy_project_resumes_existing_history_without_project_setup(self):
        project = Path(self.temporary.name) / "patterns"
        (project / "CAD/v04").mkdir(parents=True)
        original = project / "CAD/v04/old.f3d"
        original.write_bytes(b"existing-backup")
        legacy = Path(self.temporary.name) / "session_config.json"
        atomic_json(legacy, {"contexts": {"patterns": {"root": str(project), "name": "patterns"}}})
        self.addin.store.import_legacy(legacy)
        self.model.rootComponent.attributes.values.clear()
        self.model.parentDocument.name = "patterns_v01"
        self.addin.choose_destination = Mock(side_effect=AssertionError("Should not ask for a new project"))
        self.addin.request_export()
        self.addin.choose_destination.assert_not_called()
        self.assertTrue((project / "CAD/v05/patterns_v05.f3d").is_file())
        self.assertEqual(original.read_bytes(), b"existing-backup")
        self.assertFalse((project / "patterns").exists())

    def test_known_missing_project_does_not_create_a_replacement(self):
        self.addin.store.bind("missing-id", str(Path(self.temporary.name) / "disconnected"), "Missing")
        self.model.rootComponent.attributes.add("ZenExport", "ContextId", "missing-id")
        self.addin.choose_destination = Mock(side_effect=AssertionError("Should not initialize a replacement"))
        self.addin.request_export()
        self.addin.choose_destination.assert_not_called()
        self.assertEqual(self.manager.formats, [])
        self.assertIn("unavailable", self.messages[-1][0])

    def test_ambiguous_legacy_projects_offer_existing_folders_without_browsing(self):
        base = Path(self.temporary.name)
        first, second = base / "A/Part", base / "B/Part"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        legacy = base / "session_config.json"
        atomic_json(legacy, {"contexts": {
            "Part": {"root": str(first), "name": "Part"},
            "old-revision": {"root": str(second), "name": "Part"},
        }})
        self.addin.store.import_legacy(legacy)
        self.model.rootComponent.attributes.values.clear()
        self.model.parentDocument.name = "Part_v01"
        self.addin.ui.inputBox = Mock(side_effect=[("2", False), ("", False)])
        self.addin.choose_destination = Mock(side_effect=AssertionError("Should not create a new project"))
        self.addin.request_export()
        self.assertTrue((second / "CAD/v01/Part_v01.f3d").is_file())
        self.assertFalse((first / "CAD").exists())
        self.addin.choose_destination.assert_not_called()

    def test_save_description_names_the_revision_and_keeps_the_numeric_sequence(self):
        self.addin.ui.inputBox = Mock(side_effect=[("τρύπες M6", False), ("wider base", False)])
        self.addin.request_export()
        self.addin.request_export()
        revisions = Path(self.temporary.name) / "CAD"
        self.assertTrue((revisions / "v01_τρύπες M6/Test_v01.f3d").is_file())
        self.assertTrue((revisions / "v02_wider base/Test_v02.f3d").is_file())
        recorded = next(iter(self.addin.store.data["contexts"].values()))
        self.assertTrue(Path(recorded["last_success_manifest"]).is_file())
        self.assertEqual(Path(recorded["last_success_manifest"]).parent.parent.name, "_Info")

    def test_cancelling_revision_description_creates_no_revision_or_metadata_changes(self):
        self.addin.ui.inputBox = Mock(return_value=("cancelled", True))
        writes_before = self.model.rootComponent.attributes.writes
        state_before = self.addin.store.path.read_bytes()
        self.addin.request_export()
        self.assertEqual(self.manager.formats, [])
        self.assertFalse((Path(self.temporary.name) / "CAD").exists())
        self.assertEqual(self.model.rootComponent.attributes.writes, writes_before)
        self.assertEqual(self.addin.store.path.read_bytes(), state_before)

    def test_revision_description_prompt_can_be_disabled(self):
        self.addin.store.settings["prompt_revision_name"] = False
        self.addin.request_export()
        self.addin.ui.inputBox.assert_not_called()
        self.assertTrue((Path(self.temporary.name) / "CAD/v01/Test_v01.f3d").is_file())

    def test_command_destroy_releases_its_handlers(self):
        initial = len(self.addin.bindings)
        command = SimpleNamespace(execute=Event(), destroy=Event())
        self.addin.on_command_created(SimpleNamespace(command=command), False)
        self.assertEqual(len(self.addin.bindings), initial + 2)
        command.destroy.fire(None)
        self.assertEqual(len(self.addin.bindings), initial)
        self.assertEqual(command.execute.handlers, [])

    def test_stop_removes_all_handlers_and_restart_does_not_duplicate_them(self):
        self.assertEqual(len(self.addin.ui.commandStarting.handlers), 1)
        self.addin.stop()
        self.assertEqual(self.addin.bindings, [])
        self.assertEqual(self.addin.ui.commandStarting.handlers, [])
        self.addin.start()
        self.assertEqual(len(self.addin.ui.commandStarting.handlers), 1)

    def test_stopped_handler_cannot_export_after_reload(self):
        stale_handler = self.addin.ui.commandStarting.handlers[0]
        self.addin.stop()
        args = SimpleNamespace(commandId="FusionSaveCommand", isCanceled=False)
        stale_handler.notify(args)
        self.assertFalse(args.isCanceled)
        self.assertEqual(self.manager.formats, [])
        self.assertFalse(self.addin.request_export())

    def test_entry_point_reload_uses_private_package_and_removes_old_handlers(self):
        self.addin.stop()
        entry_path = Path(__file__).resolve().parents[1] / "ZenExport.py"
        spec = importlib.util.spec_from_file_location("zenexport_entry_test", entry_path)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        try:
            entry.run(None)
            first = entry._addin
            self.assertIsNotNone(first)
            self.assertEqual(first.__class__.__module__, "_zenexport_runtime.addin")
            entry.run(None)
            self.assertIsNot(first, entry._addin)
            self.assertFalse(first.running)
            self.assertEqual(len(self.addin.ui.commandStarting.handlers), 1)
        finally:
            entry.stop(None)
            for name in list(sys.modules):
                if name == "_zenexport_runtime" or name.startswith("_zenexport_runtime."):
                    del sys.modules[name]
        self.assertEqual(self.addin.ui.commandStarting.handlers, [])


if __name__ == "__main__":
    unittest.main()
