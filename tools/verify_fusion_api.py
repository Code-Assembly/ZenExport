"""Check installed Fusion API surface without importing its native extensions."""

import argparse
import ast
from pathlib import Path

REQUIRED = {
    "core": {
        "Application": ("get",
                        "activeProduct", "activeDocument", "activeViewport", "userInterface"),
        "UserInterface": ("commandDefinitions", "allToolbarPanels", "commandStarting",
                          "messageBox", "createFolderDialog", "inputBox", "createProgressDialog"),
        "Command": ("execute", "destroy", "isExecutedWhenPreEmpted"),
        "CommandDefinition": ("commandCreated", "deleteMe"),
        "CommandDefinitions": ("itemById", "addButtonDefinition"),
        "Document": ("isValid", "name", "dataFile"),
        "ProgressDialog": ("show", "hide", "progressValue", "message", "wasCancelled",
                           "isCancelButtonShown", "cancelButtonText"),
        "ApplicationCommandEventArgs": ("commandId", "isCanceled"),
        "Viewport": ("saveAsImageFile",),
        "ApplicationCommandEventHandler": ("notify",),
        "CommandCreatedEventHandler": ("notify",),
        "CommandEventHandler": ("notify",),
    },
    "fusion": {
        "Design": ("cast", "rootComponent", "exportManager", "parentDocument", "userParameters"),
        "Component": ("id", "name", "revisionId", "bRepBodies", "attributes", "occurrences"),
        "BRepBody": ("nativeObject", "name", "revisionId", "isVisible"),
        "Occurrence": ("component", "bRepBodies", "childOccurrences", "fullPathName",
                       "isVisible", "transform2"),
        "ExportManager": ("createFusionArchiveExportOptions", "createSTEPExportOptions",
                          "createSTLExportOptions", "execute"),
        "STLExportOptions": ("meshRefinement", "sendToPrintUtility"),
        "MeshRefinementSettings": ("MeshRefinementHigh", "MeshRefinementMedium", "MeshRefinementLow"),
    },
}


def check(directory):
    missing = []
    checked = 0
    for module, requirements in REQUIRED.items():
        tree = ast.parse((Path(directory) / (module + ".py")).read_text(encoding="utf-8-sig"))
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        external = {}
        for item in tree.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        external.setdefault(target.value.id, set()).add(target.attr)

        def members(name):
            node = classes.get(name)
            if node is None:
                return set()
            result = set(external.get(name, ()))
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    result.add(item.name.removeprefix("_get_").removeprefix("_set_"))
                elif isinstance(item, ast.Assign):
                    result.update(target.id for target in item.targets if isinstance(target, ast.Name))
            for base in node.bases:
                if isinstance(base, ast.Name):
                    result.update(members(base.id))
            return result

        for name, properties in requirements.items():
            available = members(name)
            for prop in properties:
                checked += 1
                if prop not in available:
                    missing.append(f"adsk.{module}.{name}.{prop}")
    if missing:
        raise RuntimeError("Missing API members:\n" + "\n".join(missing))
    print(f"Verified {checked} API members in installed source. Live behavior remains untested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adsk_directory", type=Path, help="Fusion API/Python/packages/adsk folder")
    check(parser.parse_args().adsk_directory)
