import concurrent.futures
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from zenexport.config import DEFAULT_SETTINGS, validate_settings
from zenexport.exporter import execute_export, plan_exports
from zenexport.model import bind_context, capture_snapshot, resolve_context
from zenexport.paths import NameAllocator, reserve_version, revision_id, sanitize_filename
from zenexport.storage import AmbiguousLegacyContext, ContextStore, atomic_json

from fakes import Body, Component, Occurrence, design


class PathsTests(unittest.TestCase):
    def test_unsafe_and_reserved_names_cannot_escape_destination(self):
        for value in ("..", ".", "CON", "con.txt", "LPT1", "body. ", "a/b\\c", "\x00"):
            result = sanitize_filename(value)
            self.assertTrue(result)
            self.assertEqual(Path(result).name, result)
            self.assertNotIn(result, (".", "..", "CON", "con.txt", "LPT1"))
            self.assertFalse(result.endswith((".", " ")))

    def test_collision_after_sanitization_or_case_is_not_overwritten(self):
        names = NameAllocator()
        values = [names.allocate(value) for value in ("Body", "body", "a/b", "a\\b", "Body__2")]
        self.assertEqual(len(values), len({value.casefold() for value in values}))

    def test_concurrent_reservations_and_existing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            cad = Path(directory) / "CAD"
            cad.mkdir()
            (cad / "v09").mkdir()
            (cad / "v100").write_text("blocked", encoding="utf-8")
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                folders = list(pool.map(lambda _: reserve_version(directory), range(12)))
            self.assertEqual(len(set(folders)), 12)
            self.assertTrue(all(int(path.name[1:]) > 100 for path in folders))

    def test_named_revisions_continue_old_and_new_numbering(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "CAD/v04").mkdir(parents=True)
            (project / "Revisions/v07_older change").mkdir(parents=True)
            folder = reserve_version(project, "τρύπες M6")
            self.assertEqual(folder.name, "v08_τρύπες M6")
            self.assertEqual(revision_id(folder.name), "v08")
            self.assertEqual(reserve_version(project).name, "v09")

    def test_concurrent_different_descriptions_cannot_claim_the_same_number(self):
        with tempfile.TemporaryDirectory() as directory:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                folders = list(pool.map(lambda index: reserve_version(directory, f"change {index}"), range(12)))
            self.assertEqual(len({revision_id(path.name) for path in folders}), 12)
            self.assertEqual({revision_id(path.name) for path in folders}, {f"v{i:02d}" for i in range(1, 13)})

    def test_revision_description_cannot_escape_its_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "CAD"
            for label in ("../outside", "", "..", "a/b\\c", "CON", "long name " * 50):
                folder = reserve_version(directory, label)
                self.assertEqual(folder.parent, parent)
                self.assertLessEqual(len(folder.name), 65)
                self.assertTrue(folder.is_dir())


class StorageTests(unittest.TestCase):
    def test_legacy_archive_resumes_without_attributes_and_migration_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / "patterns"
            (project / "CAD/v04").mkdir(parents=True)
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {
                "patterns": {"root": str(project), "name": "patterns", "hash": "old-hash"},
                "old-revision": {"root": str(project), "name": "patterns", "hash": "old-hash"},
            }})
            original = legacy.read_bytes()
            store = ContextStore(base / "state", legacy)
            model = design()
            model.parentDocument.name = "patterns_v01.f3d"
            context = resolve_context(model, store)
            self.assertEqual(Path(context["root"]).resolve(), project.resolve())
            self.assertNotIn("hash", context)
            key = bind_context(model, store, project, context["name"], context["context_id"])
            reopened = design()
            reopened.parentDocument.name = "patterns v2"
            recovered = resolve_context(reopened, ContextStore(base / "state"))
            self.assertEqual(recovered["context_id"], key)
            self.assertEqual(Path(recovered["root"]).resolve(), project.resolve())
            self.assertNotIn("hash", store.data["legacy_contexts"]["patterns"])
            self.assertEqual(legacy.read_bytes(), original)

    def test_legacy_lookup_prefers_the_only_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            current = base / "current/Part"
            current.mkdir(parents=True)
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {
                "Part": {"root": str(base / "old/Part"), "name": "Part"},
                "old-revision": {"root": str(current), "name": "Part"},
            }})
            store = ContextStore(base / "state", legacy)
            context = store.find_legacy_context("part_v03")
            self.assertEqual(Path(context["root"]).resolve(), current.resolve())

    def test_legacy_lookup_does_not_choose_between_two_existing_same_name_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first, second = base / "A/Part", base / "B/Part"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {
                "Part": {"root": str(first), "name": "Part"},
                "old-revision": {"root": str(second), "name": "Part"},
            }})
            store = ContextStore(base / "state", legacy)
            with self.assertRaises(AmbiguousLegacyContext) as raised:
                store.find_legacy_context("Part_v01")
            self.assertEqual(len(raised.exception.candidates), 2)

    def test_untitled_legacy_migration_requires_an_exact_old_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first, second = base / "A", base / "B"
            first.mkdir()
            second.mkdir()
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {
                "revision-A": {"root": str(first), "name": "A"},
                "revision-B": {"root": str(second), "name": "B"},
                "Untitled": {"root": str(first), "name": "Untitled"},
            }})
            store = ContextStore(base / "state", legacy)
            self.assertIsNone(store.find_legacy_context("Untitled"))
            self.assertEqual(Path(store.find_legacy_context("Untitled", "revision-B")["root"]).resolve(),
                             second.resolve())

    def test_legacy_lookup_keeps_known_missing_destination_instead_of_initializing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            missing = base / "disconnected/Part"
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {"Part": {"root": str(missing), "name": "Part"}}})
            store = ContextStore(base / "state", legacy)
            self.assertEqual(Path(store.find_legacy_context("Part_v01")["root"]).resolve(), missing.resolve())
            self.assertFalse(missing.exists())

    def test_legacy_migration_preserves_current_contexts_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            store = ContextStore(base / "state")
            store.settings["open_folder"] = False
            store.bind("modern-id", str(base), "Modern")
            legacy = base / "session_config.json"
            atomic_json(legacy, {"contexts": {"Modern": {"root": str(base / "old"), "name": "Modern"}}})
            migrated = ContextStore(base / "state", legacy)
            self.assertFalse(migrated.settings["open_folder"])
            self.assertEqual(migrated.get("modern-id")["root"], str(base))
            self.assertIsNone(migrated.find_legacy_context("DifferentProject_v01"))

    def test_failed_atomic_write_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            atomic_json(path, {"before": True})
            with patch("zenexport.storage.os.replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"after": True})
            self.assertEqual(json.loads(path.read_text()), {"before": True})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_corrupt_config_is_reported_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                ContextStore(directory)
            self.assertEqual(path.read_text(), "broken")

    def test_settings_validate_types_and_profiles(self):
        for value in ({"profile": "fast"}, {"mesh_quality": "ultra"}, {"open_folder": "false"},
                      {"prompt_revision_name": "false"}, {"debug_log": "false"},
                      {"versioned_models": "false"}):
            with self.assertRaises(ValueError):
                validate_settings(value)

    def test_two_untitled_designs_and_revision_changes_keep_separate_contexts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(directory)
            first, second = design(), design()
            first_id = bind_context(first, store, Path(directory) / "A", "A")
            second_id = bind_context(second, store, Path(directory) / "B", "B")
            first.rootComponent.revisionId = "changed-by-edit"
            self.assertNotEqual(first_id, second_id)
            self.assertEqual(resolve_context(first, store)["name"], "A")
            self.assertEqual(resolve_context(second, store)["name"], "B")
            writes = first.rootComponent.attributes.writes
            bind_context(first, store, Path(directory) / "A", "A")
            self.assertEqual(first.rootComponent.attributes.writes, writes)

    def test_first_archive_identity_and_legacy_attribute_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(directory)
            model = design()
            model.rootComponent.attributes.add("ZenExport", "LocalPath", directory)
            model.rootComponent.attributes.add("ZenExport", "ProjectName", "Legacy")
            context = resolve_context(model, store)
            self.assertEqual(context["name"], "Legacy")
            key = bind_context(model, store, directory, context["name"])
            self.assertEqual(model.rootComponent.attributes.itemByName("ZenExport", "ContextId").value, key)
            reopened = design(model.rootComponent)
            self.assertEqual(resolve_context(reopened, ContextStore(directory))["context_id"], key)

    def test_cloud_file_identity_survives_missing_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(directory)
            first = design()
            first.parentDocument.dataFile = SimpleNamespace(id="cloud-file-123")
            key = bind_context(first, store, directory, "Cloud")
            second = design()
            second.parentDocument.dataFile = SimpleNamespace(id="cloud-file-123")
            self.assertEqual(resolve_context(second, store)["context_id"], key)


class SnapshotTests(unittest.TestCase):
    def test_design_without_a_user_parameter_collection_can_be_exported(self):
        model = design()
        model.userParameters = None
        self.assertTrue(capture_snapshot(model).fingerprint)

    def test_backup_snapshot_avoids_body_and_occurrence_api_reads(self):
        root = SimpleNamespace(name="Root", id="root-id", revisionId="rev-1")
        snapshot = capture_snapshot(design(root), include_parts=False)
        self.assertFalse(snapshot.parts_collected)
        self.assertEqual(snapshot.occurrences_visited, 0)
        jobs = plan_exports(snapshot, "Test", "v01", dict(DEFAULT_SETTINGS, profile="backup"))
        self.assertEqual([job.format for job in jobs], ["f3d", "png"])
        with self.assertRaises(ValueError):
            plan_exports(snapshot, "Test", "v01", DEFAULT_SETTINGS)

    def test_linked_revisions_with_same_component_id_are_not_merged(self):
        first = Component("Part", [Body("Body")])
        second = Component("Part", [Body("Body")])
        second.id = first.id
        root = Component("Root")
        root.occurrences = [Occurrence(first, "A:1"), Occurrence(second, "B:1")]
        snapshot = capture_snapshot(design(root))
        self.assertEqual(len(snapshot.components), 3)
        self.assertEqual(sum(len(target.bodies) for target in snapshot.components), 2)

    def test_distinct_same_name_components_and_bodies_are_all_preserved(self):
        root = Component("Root")
        root.occurrences = [Occurrence(Component("Part", [Body("Body"), Body("body")]), "Part:1"),
                            Occurrence(Component("part", [Body("Body")]), "Part:2")]
        snapshot = capture_snapshot(design(root))
        self.assertEqual(len(snapshot.components), 3)
        self.assertEqual(sum(len(target.bodies) for target in snapshot.components), 3)
        jobs = plan_exports(snapshot, "Test", "v01", DEFAULT_SETTINGS)
        self.assertEqual(len(jobs), len({job.relative_path.casefold() for job in jobs}))

    def test_repeated_native_component_is_exported_once_and_hidden_parent_is_skipped(self):
        part = Component("Part", [Body("Body")])
        hidden = Component("Hidden", [Body("HiddenBody")])
        root = Component("Root")
        root.occurrences = [Occurrence(part, "Part:1"), Occurrence(part, "Part:2"),
                            Occurrence(hidden, "Hidden:1", visible=False,
                                       children=[Occurrence(part, "Hidden:1+Part:1")])]
        snapshot = capture_snapshot(design(root))
        self.assertEqual(len(snapshot.components), 2)
        self.assertEqual(sum(len(target.bodies) for target in snapshot.components), 1)
        self.assertEqual(snapshot.occurrences_visited, 3)

    def test_visibility_union_is_evaluated_in_occurrence_context(self):
        native = Body("Body")
        part = Component("Part", [native])
        invisible_proxy = Body("Body", visible=False)
        invisible_proxy.nativeObject = native
        visible_proxy = Body("Body")
        visible_proxy.nativeObject = native
        root = Component("Root")
        root.occurrences = [Occurrence(part, "Part:1", bodies=[invisible_proxy]),
                            Occurrence(part, "Part:2", bodies=[visible_proxy])]
        snapshot = capture_snapshot(design(root))
        self.assertEqual(snapshot.components[1].bodies[0][1], native)
        self.assertEqual(len(snapshot.components[1].bodies), 1)

    def test_geometry_parameter_and_transform_changes_affect_fingerprint(self):
        body = Body("Body")
        root = Component("Root", [body])
        part = Component("Part")
        occurrence = Occurrence(part, "Part:1")
        root.occurrences = [occurrence]
        model = design(root)
        before = capture_snapshot(model).fingerprint
        self.assertEqual(before, capture_snapshot(model).fingerprint)
        body.revisionId = "new-geometry-same-counts"
        geometry = capture_snapshot(model).fingerprint
        self.assertNotEqual(before, geometry)
        model.userParameters.append(SimpleNamespace(name="length", expression="12 mm", value=1.2))
        parameters = capture_snapshot(model).fingerprint
        self.assertNotEqual(geometry, parameters)
        occurrence.transform2 = SimpleNamespace(asArray=lambda: [1.0, 0.0, 1.0, 0.0])
        self.assertNotEqual(parameters, capture_snapshot(model).fingerprint)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = capture_snapshot(design(Component("Root", [Body("Body")])))
        self.settings = dict(DEFAULT_SETTINGS, thumbnail=False, versioned_models=True)

    @staticmethod
    def write(job, path):
        Path(path).write_bytes(b"fake-export-payload")
        return True

    def test_complete_snapshot_is_versioned_and_contains_truthful_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            first, report = execute_export(directory, "Test", self.snapshot, self.settings, self.write)
            second, _ = execute_export(directory, "Test", self.snapshot, self.settings, self.write)
            self.assertEqual((first.name, second.name), ("v01", "v02"))
            self.assertEqual(report["status"], "success")
            self.assertEqual(json.loads((Path(directory) / "_Info" / first.name / "export_manifest.json").read_text())["status"], "success")
            self.assertTrue((Path(directory) / "Models" / first.name / "Root/Body.stl").is_file())
            self.assertFalse(list(first.rglob(".zenexport-*")))

    def test_flat_models_keep_only_the_latest_stls_in_the_models_root(self):
        settings = dict(self.settings, versioned_models=False)
        with tempfile.TemporaryDirectory() as directory:
            models = Path(directory) / "Models"
            models.mkdir()
            (models / "Renamed.stl").write_bytes(b"old")
            (models / "notes.txt").write_bytes(b"user file")
            folder, report = execute_export(directory, "Test", self.snapshot, settings, self.write)
            self.assertEqual(report["folders"]["models"], "Models")
            self.assertEqual(sorted(path.name for path in models.iterdir()), ["Body.stl", "notes.txt"])
            self.assertEqual(report["removed_files"], ["Models/Renamed.stl"])
            self.assertFalse((models / folder.name).exists())
            self.assertTrue((folder / "Test_v01.f3d").is_file())

    def test_flat_models_survive_a_failed_or_cad_only_save(self):
        settings = dict(self.settings, versioned_models=False)
        with tempfile.TemporaryDirectory() as directory:
            execute_export(directory, "Test", self.snapshot, settings, self.write)
            execute_export(directory, "Test", self.snapshot, settings, lambda *args: False)
            execute_export(directory, "Test", self.snapshot, dict(settings, profile="cad"), self.write)
            self.assertEqual((Path(directory) / "Models/Body.stl").read_bytes(), b"fake-export-payload")

    def test_flat_models_prefix_the_component_when_body_names_clash(self):
        root = Component("Root", [Body("Body1")])
        root.occurrences = [Occurrence(Component("Bracket", [Body("Body1")]), "Bracket:1")]
        jobs = plan_exports(capture_snapshot(design(root)), "Test", "v01",
                            dict(DEFAULT_SETTINGS, versioned_models=False))
        self.assertEqual([job.relative_path for job in jobs if job.format == "stl"],
                         ["Models/Body1.stl", "Models/Bracket Body1.stl"])

    def test_false_empty_and_missing_exports_are_failures(self):
        for mode in ("false", "empty", "missing", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                def fail(job, path):
                    if mode == "empty":
                        Path(path).touch()
                    if mode == "exception":
                        raise RuntimeError("Translator failed")
                    return mode != "false"
                folder, report = execute_export(directory, "Test", self.snapshot, self.settings, fail)
                self.assertEqual(report["status"], "partial")
                self.assertTrue(all(not item["success"] for item in report["files"]))
                self.assertFalse(list(folder.rglob("*.f3d")))
                self.assertFalse(list(folder.rglob(".zenexport-*")))

    def test_failure_does_not_overwrite_history_or_advance_success_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ContextStore(Path(directory) / "state")
            store.bind("id", directory, "Test")
            first, report = execute_export(directory, "Test", self.snapshot, self.settings, self.write)
            store.record_success("id", Path(directory) / "_Info" / first.name / "export_manifest.json", self.snapshot.fingerprint)
            original = (first / "Test_v01.f3d").read_bytes()
            second, report = execute_export(directory, "Test", self.snapshot, self.settings, lambda *args: False)
            self.assertEqual(report["status"], "partial")
            self.assertEqual((first / "Test_v01.f3d").read_bytes(), original)
            self.assertIn("v01", store.get("id")["last_success_manifest"])
            self.assertNotEqual(first, second)

    def test_cancel_between_files_keeps_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, report = execute_export(directory, "Test", self.snapshot, self.settings, self.write,
                                             progress=lambda index, total, path: index < 1)
            self.assertEqual(report["status"], "cancelled")
            self.assertEqual(len(report["files"]), 1)
            self.assertTrue((folder / "Test_v01.f3d").exists())

    def test_component_directory_failure_is_reported_without_losing_root_backup(self):
        original_mkdir = Path.mkdir

        def restricted_mkdir(path, *args, **kwargs):
            if path.name == "Root":
                raise PermissionError("Component directory is read-only")
            return original_mkdir(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with patch("zenexport.exporter.Path.mkdir", new=restricted_mkdir):
                folder, report = execute_export(directory, "Test", self.snapshot, self.settings, self.write)
            self.assertEqual(report["status"], "partial")
            self.assertTrue((folder / "Test_v01.f3d").is_file())
            self.assertIn("read-only", report["files"][-1]["error"])

    def test_thumbnail_failure_is_visible_but_not_a_backup_failure(self):
        def writer(job, path):
            return False if job.format == "png" else self.write(job, path)
        with tempfile.TemporaryDirectory() as directory:
            _, report = execute_export(directory, "Test", self.snapshot, DEFAULT_SETTINGS, writer)
            self.assertEqual(report["status"], "success")
            self.assertFalse(report["files"][-1]["success"])

    def test_profiles_reduce_export_operations(self):
        full = plan_exports(self.snapshot, "Test", "v01", self.settings)
        cad = plan_exports(self.snapshot, "Test", "v01", dict(self.settings, profile="cad"))
        backup = plan_exports(self.snapshot, "Test", "v01", dict(self.settings, profile="backup"))
        self.assertEqual([len(full), len(cad), len(backup)], [3, 2, 1])

    def test_all_cad_and_auxiliary_files_are_in_their_requested_folders(self):
        root = Component("Root", [Body("Main")])
        root.occurrences = [Occurrence(Component("Part", [Body("Body")]), "Part:1")]
        snapshot = capture_snapshot(design(root))
        with tempfile.TemporaryDirectory() as directory:
            folder, report = execute_export(directory, "Test", snapshot, DEFAULT_SETTINGS, self.write,
                                             revision_name="τρύπες M6")
            self.assertEqual(folder.name, "v01_τρύπες M6")
            self.assertEqual(report["version"], "v01")
            self.assertEqual(report["revision_name"], "τρύπες M6")
            self.assertEqual({path.name for path in Path(directory).iterdir()}, {"CAD", "Models", "_Info"})
            self.assertTrue((folder / "Test_v01.f3d").is_file())
            self.assertTrue((folder / "Components/Part/Part.step").is_file())
            self.assertTrue((Path(directory) / "_Info" / folder.name / "_preview.png").is_file())
            self.assertTrue((Path(directory) / "_Info" / folder.name / "export_events.jsonl").is_file())
            for path in Path(directory).rglob("*"):
                if path.suffix in (".f3d", ".step"):
                    self.assertEqual(path.relative_to(Path(directory)).parts[0], "CAD")
            manifest = json.loads((Path(directory) / report["manifest"]).read_text(encoding="utf-8"))
            self.assertTrue(all((Path(directory) / item["path"]).is_file() for item in manifest["files"]))


if __name__ == "__main__":
    unittest.main()
