"""Filesystem operations that can be exercised without Fusion."""

import os
from pathlib import Path
import re

from .config import CAD_DIRECTORY, INFO_DIRECTORY, LEGACY_REVISION_DIRECTORY, MODEL_DIRECTORY

_VERSION_NAME = re.compile(r"^v(\d+)(?:[ _-].*)?$", re.IGNORECASE)


def sanitize_filename(name, fallback="Unnamed"):
    name = re.sub(r"\(Untitled\)", "", str(name), flags=re.IGNORECASE)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    name = name[:100].rstrip(". ")
    if not name or name in (".", ".."):
        name = fallback
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name, re.IGNORECASE):
        name = "_" + name
    return name


def design_display_name(name):
    return sanitize_filename(re.sub(r"[\s_]v\d+$", "", name, flags=re.IGNORECASE))


class NameAllocator:
    """Keep distinct objects distinct even on case-insensitive filesystems."""

    def __init__(self):
        self.used = set()

    def allocate(self, name):
        base = sanitize_filename(name)
        candidate = base
        number = 2
        while candidate.casefold() in self.used:
            candidate = f"{base}__{number}"
            number += 1
        self.used.add(candidate.casefold())
        return candidate


def revision_id(folder_name):
    match = _VERSION_NAME.fullmatch(folder_name)
    if not match:
        raise ValueError(f"Not a revision folder: {folder_name}")
    return f"v{int(match.group(1)):02d}"


def reserve_version(project_folder, revision_name="", models=True):
    """Claim a numeric ID atomically, then create its optionally named folder.

    CAD, Models, metadata, and older Revisions folders share one sequence. Numeric
    reservation files prevent concurrent saves with different descriptions from
    claiming the same number. Each revision gets matching CAD/_Info folders, plus
    Models when STLs are kept per revision.
    """
    project = Path(project_folder)
    cad = project / CAD_DIRECTORY
    reservations = project / INFO_DIRECTORY / "version_reservations"
    reservations.mkdir(parents=True, exist_ok=True)
    maximum = 0
    for directory in (cad, project / MODEL_DIRECTORY, project / INFO_DIRECTORY,
                      project / LEGACY_REVISION_DIRECTORY, reservations,
                      project / LEGACY_REVISION_DIRECTORY / INFO_DIRECTORY / "version_reservations"):
        if directory.is_dir():
            with os.scandir(directory) as entries:
                for entry in entries:
                    match = _VERSION_NAME.fullmatch(entry.name)
                    if match:
                        maximum = max(maximum, int(match.group(1)))
    description = sanitize_filename(revision_name, fallback="")[:60].rstrip(". _")
    number = maximum + 1
    while True:
        label = f"v{number:02d}"
        folder_name = f"{label}_{description}" if description else label
        folder = cad / folder_name
        try:
            (reservations / label).touch(exist_ok=False)
        except FileExistsError:
            number += 1
            continue
        for category in (CAD_DIRECTORY, MODEL_DIRECTORY, INFO_DIRECTORY):
            if category == MODEL_DIRECTORY and not models:
                continue
            (project / category / folder_name).mkdir(parents=True, exist_ok=False)
        return folder
