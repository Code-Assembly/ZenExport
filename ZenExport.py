"""Fusion entry point. Load a private package to coexist with other add-ins."""

import importlib.util
from pathlib import Path
import sys
import traceback

_addin = None
_PACKAGE = "_zenexport_runtime"


def run(context):
    global _addin
    try:
        if _addin is not None:
            _addin.stop()
            _addin = None
        # Fusion keeps Python's module cache between add-in reloads.
        for name in list(sys.modules):
            if name == _PACKAGE or name.startswith(_PACKAGE + "."):
                del sys.modules[name]
        directory = Path(__file__).resolve().parent / "zenexport"
        spec = importlib.util.spec_from_file_location(
            _PACKAGE, directory / "__init__.py", submodule_search_locations=[str(directory)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[_PACKAGE] = package
        spec.loader.exec_module(package)
        module = importlib.import_module(_PACKAGE + ".addin")
        _addin = module.ZenExportAddin(Path(__file__).resolve().parent)
        _addin.start()
    except Exception:
        details = traceback.format_exc()
        if _addin is not None:
            _addin.stop()
            _addin = None
        import adsk.core
        adsk.core.Application.get().userInterface.messageBox("ZenExport could not start:\n" + details)


def stop(context):
    global _addin
    if _addin is not None:
        _addin.stop()
        _addin = None
