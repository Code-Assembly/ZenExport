"""Build a deterministic, state-free Fusion bundle with only stdlib Python."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zenexport.config import VERSION  # noqa: E402


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    files = {"LICENSE": ROOT / "LICENSE",
             "README.md": ROOT / "README.md",
             "PackageContents.xml": ROOT / "PackageContents.xml",
             "Contents/ZenExport.py": ROOT / "ZenExport.py",
             "Contents/ZenExport.manifest": ROOT / "ZenExport.manifest"}
    for path in sorted((ROOT / "zenexport").glob("*.py")):
        files["Contents/zenexport/" + path.name] = path
    package = ET.parse(files["PackageContents.xml"]).getroot()
    if package.attrib.get("AppVersion") != VERSION:
        raise ValueError("PackageContents.xml version must match zenexport.config.VERSION")
    module = package.find("./Components/ComponentEntry")
    if module is None or module.attrib.get("ModuleName") != "./Contents/ZenExport.py":
        raise ValueError("Bundle module entry is invalid")
    manifest = json.loads(files["Contents/ZenExport.manifest"].read_text(encoding="utf-8-sig"))
    if manifest.get("type") != "addin":
        raise ValueError("Fusion manifest must declare an add-in")
    destination = output / f"ZenExport-{VERSION}.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in sorted(files.items()):
            info = zipfile.ZipInfo("ZenExport.bundle/" + relative, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
    print(f"Built {destination} ({len(files)} files)")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build(parser.parse_args().output)
