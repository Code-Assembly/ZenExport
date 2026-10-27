import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zenexport.layout import migrate_project_layout
from zenexport.paths import reserve_version
from zenexport.storage import ContextStore, atomic_json


class LayoutMigrationTests(unittest.TestCase):
    def make_snapshot(self, root, schema=2):
        label = "v04_tripa vidas" if schema == 2 else "v02"
        source = root / ("Revisions" if schema == 2 else "CAD") / label
        paths = (["CAD/Part_v04.f3d", "CAD/Part_v04.step", "CAD/Components/Thing/Thing.step",
                  "Models/Thing/Body.stl", "_Info/_preview.png"] if schema == 2 else
                 ["Part_v02.f3d", "Part_v02.step", "Models/Thing/Thing.step",
                  "Models/Thing/Body.stl", "_preview.png"])
        files = []
        digests = {}
        for index, name in enumerate(paths):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"native-payload-{index}".encode()
            path.write_bytes(payload)
            files.append({"path": name, "success": True, "bytes": len(payload)})
            digests[path.suffix + str(index)] = hashlib.sha256(payload).hexdigest()
        report = {"schema_version": schema, "status": "success", "version": "v04" if schema == 2 else "v02",
                  "project_name": "Part", "revision_name": "tripa vidas" if schema == 2 else "", "files": files}
        metadata = source / ("_Info/export_manifest.json" if schema == 2 else "export_manifest.json")
        atomic_json(metadata, report)
        events = metadata.with_name("export_events.jsonl")
        events.write_text("".join(json.dumps(item) + "\n" for item in files), encoding="utf-8")
        return source, metadata, digests

    def assert_migrated(self, root, label, expected):
        manifest = root / "_Info" / label / "export_manifest.json"
        report = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["status"], "success")
        self.assertTrue((root / "CAD" / label).is_dir())
        self.assertTrue((root / "Models" / label).is_dir())
        for index, item in enumerate(report["files"]):
            path = root / item["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected[path.suffix + str(index)])
            self.assertEqual(path.parts[-1], Path(item["path"]).name)
        lines = (manifest.parent / "export_events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["path"] for line in lines], [item["path"] for item in report["files"]])
        return manifest

    def test_common_revision_moves_into_paired_folders_and_updates_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, old_manifest, expected = self.make_snapshot(root)
            original_report = old_manifest.read_bytes()
            claims = root / "Revisions/_Info/version_reservations"
            claims.mkdir(parents=True)
            (claims / "v04").touch()
            result = migrate_project_layout(root)
            manifest = self.assert_migrated(root, source.name, expected)
            self.assertEqual(result["manifest_paths"][str(old_manifest.resolve())], str(manifest.resolve()))
            self.assertFalse((root / "Revisions").exists())
            self.assertTrue((root / "_Info/version_reservations/v04").is_file())
            backups = list((root / "_Info/_Migration" / source.name).glob("export_manifest.json.*.bak"))
            self.assertEqual(backups[0].read_bytes(), original_report)
            self.assertEqual(migrate_project_layout(root)["moved"], 0)
            self.assertEqual(reserve_version(root, "next change").name, "v05_next change")

    def test_embedded_models_and_component_cad_in_old_cad_history_are_separated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, expected = self.make_snapshot(root, schema=1)
            migrate_project_layout(root)
            self.assert_migrated(root, source.name, expected)
            self.assertTrue((root / "CAD/v02/Components/Thing/Thing.step").is_file())
            self.assertFalse((root / "CAD/v02/Models").exists())
            self.assertFalse((root / "CAD/v02/export_manifest.json").exists())

    def test_conflicting_destination_leaves_all_originals_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, metadata, _ = self.make_snapshot(root)
            originals = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
            target = root / "CAD" / source.name / "Part_v04.f3d"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"different-user-file")
            with self.assertRaises(FileExistsError):
                migrate_project_layout(root)
            self.assertTrue(metadata.is_file())
            self.assertEqual(target.read_bytes(), b"different-user-file")
            self.assertTrue(all(path.read_bytes() == content for path, content in originals.items()))

    def test_unversioned_models_are_preserved_without_inventing_a_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Models/Part").mkdir(parents=True)
            (root / "Models/Part/Body.stl").write_bytes(b"old-stl")
            (root / "Models/Part/Part.step").write_bytes(b"old-cad")
            (root / "_preview.png").write_bytes(b"old-preview")
            migrate_project_layout(root)
            self.assertEqual((root / "Models/_Legacy_unversioned/Part/Body.stl").read_bytes(), b"old-stl")
            self.assertEqual((root / "CAD/_Legacy_unversioned/Part/Part.step").read_bytes(), b"old-cad")
            self.assertTrue((root / "_Info/_Legacy_unversioned/_preview.png").is_file())
            self.assertFalse((root / "Models/v01").exists())

    def test_flat_models_keep_loose_stls_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Models/Part").mkdir(parents=True)
            (root / "Models/Body.stl").write_bytes(b"latest")
            (root / "Models/Part/Body.stl").write_bytes(b"old-stl")
            migrate_project_layout(root, flat_models=True)
            self.assertEqual((root / "Models/Body.stl").read_bytes(), b"latest")
            self.assertEqual((root / "Models/_Legacy_unversioned/Part/Body.stl").read_bytes(), b"old-stl")

    def test_report_path_escape_is_rejected_before_any_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, metadata, _ = self.make_snapshot(root)
            report = json.loads(metadata.read_text())
            report["files"][0]["path"] = "../../outside.f3d"
            atomic_json(metadata, report)
            with self.assertRaises(ValueError):
                migrate_project_layout(root)
            self.assertTrue((source / "CAD/Part_v04.f3d").is_file())
            self.assertFalse((root / "CAD").exists())

    def test_copy_fallback_preserves_bytes_when_hard_links_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, expected = self.make_snapshot(root)
            with patch("zenexport.layout.os.link", side_effect=OSError("No hard links")):
                migrate_project_layout(root)
            self.assert_migrated(root, source.name, expected)

    def test_interrupted_metadata_update_is_completed_from_the_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, old_manifest, expected = self.make_snapshot(root)
            original_atomic = atomic_json

            def interrupted(path, data):
                if Path(path).name == "export_manifest.json" and data.get("schema_version") == 3:
                    raise OSError("Simulated interruption after payload moves")
                return original_atomic(path, data)

            with patch("zenexport.layout.atomic_json", side_effect=interrupted):
                with self.assertRaises(OSError):
                    migrate_project_layout(root)
            self.assertFalse(old_manifest.exists())
            result = migrate_project_layout(root)
            manifest = self.assert_migrated(root, source.name, expected)
            self.assertEqual(result["manifest_paths"][str(old_manifest.resolve())], str(manifest.resolve()))

    def test_context_last_success_is_relocated_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, old_manifest, _ = self.make_snapshot(root)
            store = ContextStore(root / "state")
            store.bind("same-id", str(root), "Part")
            store.record_success("same-id", old_manifest, "same-fingerprint")
            result = migrate_project_layout(root)
            store.relocate_manifests(result["manifest_paths"])
            context = store.get("same-id")
            self.assertTrue(Path(context["last_success_manifest"]).is_file())
            self.assertEqual(context["context_id"], "same-id")
            self.assertEqual(context["fingerprint"], "same-fingerprint")
