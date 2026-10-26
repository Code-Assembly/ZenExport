"""Writable per-user state, atomic JSON replacement, and bounded logging."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import uuid

from .config import validate_settings
from .paths import design_display_name, sanitize_filename


def runtime_directory():
    override = os.environ.get("ZENEXPORT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ZenExport"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ZenExport"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ZenExport"


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".zenexport-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def create_logger(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ZenExport")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(directory / "zenexport.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


class AmbiguousLegacyContext(ValueError):
    def __init__(self, name, candidates):
        super().__init__(f"Multiple saved project folders match {name!r}")
        self.name = name
        self.candidates = candidates


class ContextStore:
    """Stable identities, plus a one-time compatibility lookup for v5 archives."""

    def __init__(self, directory, legacy_path=None):
        self.path = Path(directory) / "config.json"
        if self.path.exists():
            with self.path.open(encoding="utf-8") as stream:
                self.data = json.load(stream)
            if not isinstance(self.data, dict) or self.data.get("schema_version") != 1:
                raise ValueError(f"Unsupported config schema: {self.path}")
            if not isinstance(self.data.get("contexts"), dict):
                raise ValueError(f"Invalid contexts in {self.path}")
        else:
            self.data = {"schema_version": 1, "settings": {}, "contexts": {}}
        self.settings = validate_settings(self.data.get("settings", {}))
        self.data["settings"] = self.settings
        if not self.path.exists():
            self.save()
        if legacy_path is not None and Path(legacy_path).is_file():
            self.import_legacy(legacy_path)

    def save(self):
        atomic_json(self.path, self.data)

    def import_legacy(self, path):
        """Copy old bindings into writable state, preserving the original file."""
        with Path(path).open(encoding="utf-8-sig") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or not isinstance(data.get("contexts"), dict):
            raise ValueError(f"Invalid legacy contexts: {path}")
        current = self.data.get("legacy_contexts", {})
        if not isinstance(current, dict):
            raise ValueError("Invalid legacy_contexts in config.json")
        merged = dict(current)
        for key, value in data["contexts"].items():
            if (isinstance(value, dict) and isinstance(value.get("root"), str)
                    and value["root"] and isinstance(value.get("name"), str)):
                # The old hash is intentionally not imported as a success marker.
                merged[key] = {"root": value["root"], "name": value["name"]}
        if merged != current:
            self.data["legacy_contexts"] = merged
            self.save()

    def find_legacy_context(self, document_name, revision_id=None):
        """Resume v5 history when a matching destination is unambiguous.

        Revision/name matching is confined to legacy migration. A deterministic
        UUID per old project root makes repeated opens of old archives idempotent.
        """
        legacy = self.data.get("legacy_contexts", {})
        if not isinstance(legacy, dict):
            raise ValueError("Invalid legacy_contexts in config.json")

        def normalize(name):
            name = str(name).strip()
            if name.lower().endswith((".f3d", ".f3z")):
                name = name[:-4]
            return sanitize_filename(name, fallback="").casefold()

        def candidate(value):
            if not isinstance(value, dict) or not isinstance(value.get("root"), str):
                return None
            path = Path(value["root"]).expanduser()
            if not path.is_absolute():
                return None
            path_key = os.path.normcase(str(path.resolve()))
            context_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "zenexport:legacy:" + path_key))
            return self.get(context_id) or {
                "root": str(path.resolve()), "name": value.get("name") or path.name,
                "context_id": context_id,
            }

        # An exact old revision key can still recover an Untitled tab; it is not
        # used as the new identity and is superseded by UUID binding after export.
        revision_match = candidate(legacy[revision_id]) if revision_id in legacy else None
        if revision_match and Path(revision_match["root"]).is_dir():
            return revision_match

        full_name = normalize(document_name)
        base_name = normalize(design_display_name(full_name)) if full_name else ""
        if not full_name or base_name in ("untitled", "unnamed"):
            return revision_match
        # Exact project names win before stripping a trailing Fusion version.
        for alias in dict.fromkeys((full_name, base_name)):
            matches = {}
            for key, value in legacy.items():
                if not isinstance(value, dict):
                    continue
                if alias not in (normalize(key), normalize(value.get("name", ""))):
                    continue
                match = candidate(value)
                if match is not None:
                    path_key = os.path.normcase(str(Path(match["root"]).resolve()))
                    matches.setdefault(path_key, match)
            existing = [match for match in matches.values() if Path(match["root"]).is_dir()]
            choices = existing or list(matches.values())
            if len(choices) == 1:
                return choices[0]
            if len(choices) > 1:
                raise AmbiguousLegacyContext(document_name, choices)
        return revision_match

    def get(self, context_id, file_id=None):
        contexts = self.data["contexts"]
        context = contexts.get("context:" + context_id) if context_id else None
        if context is None and file_id:
            context = contexts.get("file:" + file_id)
        if context is None:
            return None
        if not isinstance(context, dict) or not isinstance(context.get("root"), str):
            raise ValueError("Invalid saved project context")
        return dict(context)

    def bind(self, context_id, root, name, file_id=None):
        existing = self.get(context_id, file_id) or {}
        context = dict(existing, root=str(root), name=name, context_id=context_id)
        self.data["contexts"]["context:" + context_id] = context
        if file_id:
            self.data["contexts"]["file:" + file_id] = context
        self.data["last_save_directory"] = str(Path(root).parent)
        self.save()

    def record_success(self, context_id, manifest_path, fingerprint, file_id=None):
        context = self.get(context_id, file_id)
        if context is None:
            raise ValueError("Cannot record success without a bound context")
        context.update(last_success_manifest=str(manifest_path), fingerprint=fingerprint)
        self.data["contexts"]["context:" + context_id] = context
        if file_id:
            self.data["contexts"]["file:" + file_id] = context
        self.save()

    def relocate_manifests(self, paths):
        normalized = {os.path.normcase(str(Path(old).resolve())): new for old, new in paths.items()}
        changed = False
        for context in self.data["contexts"].values():
            old = context.get("last_success_manifest")
            if old:
                new = normalized.get(os.path.normcase(str(Path(old).resolve())))
                if new and Path(new).is_file() and old != new:
                    context["last_success_manifest"] = new
                    changed = True
        if changed:
            self.save()
