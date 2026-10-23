import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("zenexport_bundle_builder", ROOT / "tools/build_bundle.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackagingTests(unittest.TestCase):
    def test_bundle_contains_complete_runtime_without_personal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = builder.build(directory)
            first = artifact.read_bytes()
            builder.build(directory)
            self.assertEqual(first, artifact.read_bytes())
            with zipfile.ZipFile(artifact) as archive:
                names = set(archive.namelist())
                self.assertTrue({"ZenExport.bundle/LICENSE", "ZenExport.bundle/README.md"} <= names)
                expected = {"ZenExport.bundle/Contents/zenexport/" + path.name
                            for path in (ROOT / "zenexport").glob("*.py")}
                self.assertTrue(expected <= names)
                self.assertTrue(all("session_config" not in name and ".log" not in name for name in names))
                for name in names:
                    if name.endswith(".py"):
                        compile(archive.read(name).decode("utf-8-sig"), name, "exec")

    def test_installer_sources_exist_and_include_entire_runtime(self):
        namespace = {"w": "http://schemas.microsoft.com/wix/2006/wi"}
        wix = ET.parse(ROOT / "installer_source.wxs")
        sources = {node.attrib["Source"] for node in wix.findall(".//w:File", namespace)}
        expected = {"zenexport/" + path.name for path in (ROOT / "zenexport").glob("*.py")}
        self.assertTrue(expected <= sources)
        self.assertNotIn("session_config.json", sources)
        self.assertTrue(all((ROOT / source).is_file() for source in sources))


if __name__ == "__main__":
    unittest.main()
