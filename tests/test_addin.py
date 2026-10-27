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
from zenexport.storage import ContextStore, atomic_json


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


class Inputs:
    def __init__(self):
        self.items = {}

    def addBoolValueInput(self, key, name, is_check_box, resource, value):
        self.items[key] = SimpleNamespace(name=name, value=value)
        return self.items[key]

    def itemById(self, key):
        return self.items.get(key)


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
        fusion.DistanceUnits = SimpleNamespace(MillimeterDistanceUnits=0, CentimeterDistanceUnits=1,
                                               MeterDistanceUnits=2, InchDistanceUnits=3)
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

    def test_stl_dimensions_are_millimeters_regardless_of_design_units(self):
        # Model a 2 x 3 x 4 cm part through a translator that honors unitType.
        # Leaving the design default in place reproduces the slicer scale bug.
        factors_from_cm = {0: 10, 1: 1, 2: 0.01, 3: 1 / 2.54}
        original_execute = self.manager.execute
        exported = []

        def execute(options):
            if options.format != "stl":
                return original_execute(options)
            factor = factors_from_cm[options.unitType]
            vertices = [(0, 0, 0), (2 * factor, 0, 0), (0, 3 * factor, 4 * factor)]
            Path(options.filename).write_text(
                "solid part\n" + "".join(f"vertex {x} {y} {z}\n" for x, y, z in vertices)
                + "endsolid part\n", encoding="ascii")
            exported.append(vertices)
            return True

        self.manager.execute = execute
        for units in (0, 1, 2, 3):
            with self.subTest(design_units=units):
                self.manager.createSTLExportOptions = lambda geometry, filename: SimpleNamespace(
                    filename=filename, format="stl", unitType=units)
                self.addin.request_export()
                self.assertEqual(exported[-1], [(0, 0, 0), (20, 0, 0), (0, 30, 40)])

    def test_rejected_stl_unit_setting_is_a_failure_not_a_wrong_scale_success(self):
        class RejectedUnits:
            def __init__(self, filename):
                self.filename = filename
                self.format = "stl"

            @property
            def unitType(self):
                return 1

            @unitType.setter
            def unitType(self, value):
                raise RuntimeError("STL millimeter units rejected")

        self.manager.createSTLExportOptions = lambda geometry, filename: RejectedUnits(filename)
        self.addin.request_export()
        self.assertEqual(self.manager.formats, ["f3d", "step"])
        self.assertIn("Incomplete", self.messages[-1][0])
        recorded = next(iter(self.addin.store.data["contexts"].values()))
        self.assertNotIn("last_success_manifest", recorded)

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
        self.assertTrue((revisions / "v01_τρύπες-M6/Test_v01.f3d").is_file())
        self.assertTrue((revisions / "v02_wider-base/Test_v02.f3d").is_file())
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

    def open_settings(self):
        command = SimpleNamespace(commandInputs=Inputs(), execute=Event(), destroy=Event())
        definition = self.addin.ui.commandDefinitions.itemById("ZenExport_Settings")
        definition.commandCreated.fire(SimpleNamespace(command=command))
        return command

    def press_ok(self, command):
        command.execute.fire(SimpleNamespace(command=command))
        command.destroy.fire(None)

    def test_settings_dialog_has_a_check_box_per_setting(self):
        inputs = self.open_settings().commandInputs.items
        self.assertEqual([item.name for item in inputs.values()],
                         ["Open folder after save", "Notes on save", "Keep STLs per revision",
                          "Record debug log"])
        self.assertEqual([item.value for item in inputs.values()], [False, True, False, False])

    def test_ok_saves_settings_for_the_next_start(self):
        command = self.open_settings()
        command.commandInputs.items["open_folder"].value = True
        self.press_ok(command)
        self.assertTrue(self.addin.store.settings["open_folder"])
        self.assertTrue(ContextStore(self.addin.directory).settings["open_folder"])

    def test_cancel_leaves_settings_unchanged(self):
        command = self.open_settings()
        command.commandInputs.items["prompt_revision_name"].value = False
        command.destroy.fire(None)
        self.assertTrue(self.addin.store.settings["prompt_revision_name"])

    def test_failed_settings_save_keeps_the_running_settings(self):
        command = self.open_settings()
        command.commandInputs.items["prompt_revision_name"].value = False
        with patch("zenexport.storage.atomic_json", side_effect=OSError("disk full")):
            self.press_ok(command)
        self.assertTrue(self.addin.store.settings["prompt_revision_name"])
        self.assertIn("disk full", self.messages[-1][0])

    def test_settings_command_failure_keeps_save_interception(self):
        self.addin.stop()
        original = self.addin.ui.commandDefinitions.addButtonDefinition

        def add(key, *args):
            if key == "ZenExport_Settings":
                raise RuntimeError("settings unavailable")
            return original(key, *args)

        self.addin.ui.commandDefinitions.addButtonDefinition = add
        self.addin.start()
        self.assertEqual(len(self.addin.ui.commandStarting.handlers), 1)

    def test_stop_removes_the_settings_command(self):
        definition = self.addin.ui.commandDefinitions.itemById("ZenExport_Settings")
        self.addin.stop()
        self.assertFalse(definition.isValid)

    def test_debug_log_is_off_by_default_and_records_once_ticked(self):
        log = self.addin.directory / "zenexport.log"
        self.addin.request_export()
        self.assertFalse(log.exists())
        command = self.open_settings()
        command.commandInputs.items["debug_log"].value = True
        self.press_ok(command)
        self.addin.request_export()
        self.assertIn("Starting export", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
