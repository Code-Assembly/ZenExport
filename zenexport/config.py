"""Central identifiers and conservative export defaults."""

from . import __version__

VERSION = __version__
COMMAND_ID = "ZenExport_Cmd_v5"  # Preserve existing Fusion command customizations.
COMMAND_NAME = "ZenExport Save"
DESTINATION_COMMAND_ID = "ZenExport_ChooseDestination"
PANEL_ID = "SolidScriptsAddinsPanel"
ATTRIBUTE_GROUP = "ZenExport"
LEGACY_REVISION_DIRECTORY = "Revisions"
CAD_DIRECTORY = "CAD"
MODEL_DIRECTORY = "Models"
INFO_DIRECTORY = "_Info"
MANIFEST_FILENAME = "export_manifest.json"
DEFAULT_SETTINGS = {
    "intercept_native_save": True,
    "profile": "full",
    "mesh_quality": "high",
    "thumbnail": True,
    "open_folder": True,
    "prompt_revision_name": True,
}
PROFILES = {
    "full": {"step": True, "stl": True, "components": True},
    "cad": {"step": True, "stl": False, "components": False},
    "backup": {"step": False, "stl": False, "components": False},
}
SAVE_COMMANDS = frozenset(("PLM360SaveCommand", "FusionSaveCommand", "FileSave", "Save"))


def validate_settings(settings):
    result = dict(DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        raise ValueError("settings must be a JSON object")
    for key in ("intercept_native_save", "thumbnail", "open_folder", "prompt_revision_name"):
        if key in settings:
            if not isinstance(settings[key], bool):
                raise ValueError(f"{key} must be true or false")
            result[key] = settings[key]
    for key, choices in (("profile", PROFILES), ("mesh_quality", ("low", "medium", "high"))):
        if key in settings:
            if settings[key] not in choices:
                raise ValueError(f"Invalid {key}: {settings[key]!r}")
            result[key] = settings[key]
    return result
