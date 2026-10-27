"""Reconcile earlier ZenExport layouts into paired CAD/Models revision folders."""

import hashlib
import json
import os
from pathlib import Path
import shutil

from .config import (CAD_DIRECTORY, INFO_DIRECTORY, LEGACY_REVISION_DIRECTORY,
                     MANIFEST_FILENAME, MODEL_DIRECTORY)
from .paths import revision_id
from .storage import atomic_json


def _digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.digest()


def migrate_project_layout(project_folder, flat_models=False):
    """Move only inside the named project; never replace a conflicting file.

    All source/destination paths and conflicts are checked before moving files.
    Native files retain their bytes. Original reports are backed up before their
    relative paths are updated. Empty old folders are removed without recursion.
    A journal makes manifest relocation recoverable across interrupted migrations.
    """
    root = Path(project_folder).resolve()
    if not root.is_dir():
        return {"moved": 0, "manifest_paths": {}}

    def checked(path):
        path = Path(path)
        resolved = path.resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError(f"Migration path is outside the project: {path}")
        return path

    def is_revision(path):
        try:
            revision_id(path.name)
            return path.is_dir()
        except ValueError:
            return False

    def relative_target(label, relative):
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe path in old report: {relative}")
        parts = relative.parts
        if not parts:
            raise ValueError("Empty export path in old report")
        prefix = parts[0]
        tail = Path(*parts[1:]) if len(parts) > 1 else relative
        if relative.suffix.lower() in (".f3d", ".f3z", ".step", ".stp"):
            if prefix == MODEL_DIRECTORY:
                tail = Path("Components") / tail
            elif prefix != CAD_DIRECTORY:
                tail = relative
            return Path(CAD_DIRECTORY) / label / tail
        if relative.suffix.lower() == ".stl":
            return Path(MODEL_DIRECTORY) / label / (tail if prefix == MODEL_DIRECTORY else relative)
        return Path(INFO_DIRECTORY) / label / (tail if prefix == INFO_DIRECTORY else relative)

    operations = {}
    rewrites = []
    cleanup_roots = []
    journal = checked(root / INFO_DIRECTORY / "_Migration/layout_moves.json")
    if journal.is_file():
        with journal.open(encoding="utf-8") as stream:
            old_journal = json.load(stream)
        manifest_moves = dict(old_journal.get("manifest_paths", {}))
        pending_rewrites = old_journal.get("pending_rewrites", [])
        for old, new in manifest_moves.items():
            if Path(old).is_absolute() or Path(new).is_absolute():
                raise ValueError("Migration journal paths must be project-relative")
            checked(root / old)
            checked(root / new)
    else:
        manifest_moves = {}
        pending_rewrites = []

    def add_move(source, target):
        source, target = checked(source), checked(target)
        if source.resolve() != target.resolve():
            operations[source] = target

    sources = []
    for category in (LEGACY_REVISION_DIRECTORY, CAD_DIRECTORY):
        parent = root / category
        if parent.is_dir():
            sources.extend(path for path in parent.iterdir() if is_revision(path))
    for source in sources:
        checked(source)
        if source.parent == root / CAD_DIRECTORY and not any(
            (source / name).exists() for name in
            (MODEL_DIRECTORY, CAD_DIRECTORY, INFO_DIRECTORY, MANIFEST_FILENAME, "export_events.jsonl", "_preview.png")
        ):
            continue  # Already organized CAD-only history needs no recursive scan.
        label = source.name
        for file in source.rglob("*"):
            if file.is_file():
                add_move(file, root / relative_target(label, file.relative_to(source)))
        metadata = source / INFO_DIRECTORY / MANIFEST_FILENAME
        if not metadata.is_file():
            metadata = source / MANIFEST_FILENAME
        original_schema = 0
        if metadata.is_file():
            checked(metadata)
            original = metadata.read_bytes()
            report = json.loads(original.decode("utf-8-sig"))
            original_schema = report.get("schema_version", 1)
            if original_schema < 3:
                for item in report.get("files", []):
                    item["path"] = relative_target(label, item["path"]).as_posix()
            destination = root / INFO_DIRECTORY / label / MANIFEST_FILENAME
            report.update(schema_version=3, version=revision_id(label), revision_folder=label,
                          manifest=destination.relative_to(root).as_posix(),
                          folders={"cad": f"{CAD_DIRECTORY}/{label}",
                                   "models": f"{MODEL_DIRECTORY}/{label}",
                                   "info": f"{INFO_DIRECTORY}/{label}"})
            old_key = metadata.relative_to(root).as_posix()
            manifest_moves[old_key] = destination.relative_to(root).as_posix()
            rewrites.append((destination, original, report, label, False))
        for events in (source / "export_events.jsonl", source / INFO_DIRECTORY / "export_events.jsonl"):
            if events.is_file():
                checked(events)
                original = events.read_bytes()
                lines = []
                for line in original.decode("utf-8-sig").splitlines():
                    if line.strip():
                        item = json.loads(line)
                        if original_schema < 3:
                            item["path"] = relative_target(label, item["path"]).as_posix()
                        lines.append(item)
                destination = root / INFO_DIRECTORY / label / "export_events.jsonl"
                rewrites.append((destination, original, lines, label, True))
        cleanup_roots.append(source)

    # These exports predate versioned STL snapshots. Keep their identity explicitly
    # unversioned rather than inventing an association with an older CAD revision.
    # Loose STLs are the current export when STLs are not kept per revision.
    legacy_models = root / MODEL_DIRECTORY
    if legacy_models.is_dir():
        for child in legacy_models.iterdir():
            if child.name.startswith("_") or is_revision(child) or (flat_models and child.is_file()):
                continue
            for file in ([child] if child.is_file() else child.rglob("*")):
                if file.is_file() and file.suffix.lower() in (".stl", ".f3d", ".f3z", ".step", ".stp"):
                    category = MODEL_DIRECTORY if file.suffix.lower() == ".stl" else CAD_DIRECTORY
                    add_move(file, root / category / "_Legacy_unversioned" / file.relative_to(legacy_models))
            if child.is_dir():
                cleanup_roots.append(child)
    preview = root / "_preview.png"
    if preview.is_file():
        add_move(preview, root / INFO_DIRECTORY / "_Legacy_unversioned/_preview.png")
    old_claims = root / LEGACY_REVISION_DIRECTORY / INFO_DIRECTORY / "version_reservations"
    if old_claims.is_dir():
        for file in old_claims.iterdir():
            if file.is_file():
                add_move(file, root / INFO_DIRECTORY / "version_reservations" / file.name)
    old_revisions = root / LEGACY_REVISION_DIRECTORY
    if old_revisions.is_dir():
        cleanup_roots.append(old_revisions)

    prepared = {target for target, *_ in rewrites}
    for pending in pending_rewrites:
        relative = Path(pending["target"])
        if relative.is_absolute():
            raise ValueError("Migration journal targets must be project-relative")
        target = checked(root / relative)
        if target not in prepared:
            rewrites.append((target, None, pending["payload"], target.parent.name, pending["events"]))
            prepared.add(target)

    # Check every payload before the first mutation. A conflict keeps originals.
    destinations = {}
    for source, target in operations.items():
        previous = destinations.get(target)
        if previous and _digest(previous) != _digest(source):
            raise FileExistsError(f"Different old exports map to the same destination: {target}")
        if target.exists() and (not target.is_file() or _digest(target) != _digest(source)):
            raise FileExistsError(f"A different file already exists at {target}")
        destinations[target] = source

    if operations or rewrites:
        atomic_json(journal, {"schema_version": 1, "manifest_paths": manifest_moves,
                             "pending_rewrites": [
                                 {"target": target.relative_to(root).as_posix(),
                                  "payload": payload, "events": events}
                                 for target, _, payload, _, events in rewrites]})
    for target, original, _, label, _ in rewrites:
        if original is None:
            continue
        backup = checked(root / INFO_DIRECTORY / "_Migration" / label /
                         (target.name + "." + hashlib.sha256(original).hexdigest()[:12] + ".bak"))
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists() and backup.read_bytes() != original:
            raise FileExistsError(f"The original report backup has different content: {backup}")
        if not backup.exists():
            with backup.open("xb") as stream:
                stream.write(original)

    moved = 0
    for source, target in operations.items():
        # Validate again immediately before moving, including resolved junctions.
        checked(source)
        checked(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                os.link(source, target)  # exclusive, byte-preserving, same-filesystem fast path
            except FileExistsError:
                raise
            except OSError:
                created = False
                try:
                    with target.open("xb") as output:
                        created = True
                        with source.open("rb") as input_stream:
                            shutil.copyfileobj(input_stream, output)
                        output.flush()
                        os.fsync(output.fileno())
                    if _digest(source) != _digest(target):
                        raise OSError(f"Copied payload verification failed: {source}")
                    shutil.copystat(source, target)
                except Exception:
                    if created:
                        target.unlink()
                    raise
        elif _digest(source) != _digest(target):
            raise FileExistsError(f"Destination changed during migration: {target}")
        source.unlink()
        moved += 1
    for target, _, payload, _, is_events in rewrites:
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_events:
            temporary = target.with_suffix(".migration.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                for item in payload:
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(target)
        else:
            for item in payload.get("files", []):
                if item.get("success"):
                    output = checked(root / item["path"])
                    if not output.is_file() or ("bytes" in item and output.stat().st_size != item["bytes"]):
                        raise OSError(f"A migrated output does not match its original report: {output}")
            atomic_json(target, payload)

    for source in cleanup_roots:
        if not source.is_dir():
            continue
        directories = [path for path in source.rglob("*") if path.is_dir()]
        for directory in sorted(directories + [source], key=lambda path: len(path.parts), reverse=True):
            checked(directory)
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()  # empty only: never recursively delete a project directory
    if operations or rewrites:
        atomic_json(journal, {"schema_version": 1, "manifest_paths": manifest_moves, "pending_rewrites": []})
    return {"moved": moved,
            "manifest_paths": {str(checked(root / old).resolve()): str(checked(root / new).resolve())
                               for old, new in manifest_moves.items()}}
