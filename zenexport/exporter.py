"""Versioned export orchestration with explicit outcomes and no Autodesk imports."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

from .config import (CAD_DIRECTORY, INFO_DIRECTORY, MANIFEST_FILENAME,
                     MODEL_DIRECTORY, PROFILES, VERSION)
from .paths import NameAllocator, reserve_version, revision_id, sanitize_filename
from .storage import atomic_json


@dataclass
class ExportJob:
    format: str
    relative_path: str
    geometry: object = None
    required: bool = True


def plan_exports(snapshot, name, version, settings, revision_folder=None):
    profile = PROFILES[settings["profile"]]
    if (profile["stl"] or profile["components"]) and not snapshot.parts_collected:
        raise ValueError("Per-part export requires a complete assembly snapshot")
    stem = f"{sanitize_filename(name)}_{version}"
    revision_folder = revision_folder or version
    cad = Path(CAD_DIRECTORY) / revision_folder
    versioned = settings["versioned_models"]
    models = Path(MODEL_DIRECTORY) / revision_folder if versioned else Path(MODEL_DIRECTORY)
    stl_names = NameAllocator()
    info = Path(INFO_DIRECTORY) / revision_folder
    jobs = [ExportJob("f3d", (cad / (stem + ".f3d")).as_posix())]
    if profile["step"]:
        jobs.append(ExportJob("step", (cad / (stem + ".step")).as_posix()))
    for index, target in enumerate(snapshot.components):
        # The root is named after the document, e.g. "(Unsaved)"; its bodies need no folder.
        folder = models / target.folder if index else models
        if profile["stl"]:
            for body_name, body in target.bodies:
                if versioned:
                    path = folder / (body_name + ".stl")
                else:
                    if body_name.casefold() in stl_names.used:
                        body_name = f"{target.folder} {body_name}"
                    path = models / (stl_names.allocate(body_name) + ".stl")
                jobs.append(ExportJob("stl", path.as_posix(), body))
        if index and profile["components"]:
            component_cad = cad / "Components" / target.folder
            jobs.extend(ExportJob(fmt, (component_cad / (target.folder + "." + fmt)).as_posix(),
                                  target.component) for fmt in ("step", "f3d"))
    if settings["thumbnail"]:
        jobs.append(ExportJob("png", (info / "_preview.png").as_posix(), required=False))
    return jobs


def execute_export(project_folder, name, snapshot, settings, export_file,
                   progress=None, logger=None, revision_name=""):
    """export_file(job, temporary_path) must return a truthful success boolean.

    Each output is staged beside its destination and published with os.replace.
    A partial version is kept for inspection; it never advances last-success state.
    The manifest, rather than the existence of a version directory, defines success.
    """
    project = Path(project_folder)
    versioned = settings["versioned_models"]
    folder = reserve_version(project, revision_name, models=versioned)
    version = revision_id(folder.name)
    jobs = plan_exports(snapshot, name, version, settings, folder.name)
    manifest_relative = (Path(INFO_DIRECTORY) / folder.name / MANIFEST_FILENAME).as_posix()
    report = {
        "schema_version": 3, "zenexport_version": VERSION,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress", "project_name": name, "version": version,
        "revision_name": revision_name.strip(), "revision_folder": folder.name,
        "manifest": manifest_relative,
        "folders": {"cad": (Path(CAD_DIRECTORY) / folder.name).as_posix(),
                    "models": (Path(MODEL_DIRECTORY) / folder.name).as_posix() if versioned
                              else MODEL_DIRECTORY,
                    "info": (Path(INFO_DIRECTORY) / folder.name).as_posix()},
        "profile": settings["profile"], "mesh_quality": settings["mesh_quality"],
        "fingerprint": snapshot.fingerprint,
        "snapshot_seconds": round(snapshot.capture_seconds, 4),
        "parts_collected": snapshot.parts_collected,
        "occurrences_visited": snapshot.occurrences_visited,
        "component_definitions": len(snapshot.components),
        "planned_files": len(jobs), "files": [],
    }
    manifest = project / manifest_relative
    ledger = manifest.parent / "export_events.jsonl"
    atomic_json(manifest, report)
    started = time.perf_counter()
    cancelled = False
    for index, job in enumerate(jobs):
        if progress and not progress(index, len(jobs), job.relative_path):
            cancelled = True
            break
        target = project / job.relative_path
        temporary = target.with_name(f".zenexport-{uuid.uuid4().hex}{target.suffix}")
        item_started = time.perf_counter()
        item = {"format": job.format, "path": job.relative_path, "required": job.required,
                "success": False}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not export_file(job, str(temporary)):
                raise RuntimeError("Fusion reported an unsuccessful export")
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Fusion did not create a non-empty output file")
            temporary.replace(target)
            item.update(success=True, bytes=target.stat().st_size)
        except Exception as error:
            item["error"] = str(error)
            if logger:
                logger.exception("Export failed: %s", job.relative_path)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError as error:
                item["cleanup_error"] = str(error)
                if logger:
                    logger.exception("Could not remove staged file: %s", temporary)
        item["seconds"] = round(time.perf_counter() - item_started, 4)
        report["files"].append(item)
        # Append O(1) data per output; rewriting an ever-growing manifest is O(n²).
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    required_failed = any(not item["success"] and item["required"] for item in report["files"])
    report["status"] = "cancelled" if cancelled else ("partial" if required_failed else "success")
    # Only a complete save replaces the previous STLs; anything less keeps them.
    if (report["status"] == "success" and not versioned and PROFILES[settings["profile"]]["stl"]
            and (project / MODEL_DIRECTORY).is_dir()):
        current = {Path(job.relative_path).name.casefold() for job in jobs if job.format == "stl"}
        report["removed_files"] = []
        for stale in (project / MODEL_DIRECTORY).iterdir():
            if stale.is_file() and stale.suffix.lower() == ".stl" and stale.name.casefold() not in current:
                try:
                    stale.unlink()
                    report["removed_files"].append((Path(MODEL_DIRECTORY) / stale.name).as_posix())
                except OSError:
                    if logger:
                        logger.exception("Could not remove old STL: %s", stale)
    report["seconds"] = round(time.perf_counter() - started, 4)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(manifest, report)
    return folder, report
