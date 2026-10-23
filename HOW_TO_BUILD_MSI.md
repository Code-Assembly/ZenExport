# Building and validating ZenExport distribution

## Portable bundle (verified)

Run from the repository root with Python 3.10 or newer:

```powershell
py -3.13 tools/build_bundle.py
```

This creates `dist/ZenExport-6.1.1.zip` and a SHA-256 sidecar. Extract the ZIP to obtain
`ZenExport.bundle`. The bundle includes PackageContents.xml, the Fusion entry point,
its .manifest, all eight runtime modules, the README, and the MIT license. It excludes session_config.json,
per-user configuration, logs, tests, development tools, and unrelated project files.
Repeated builds from identical source bytes with the same Python/zlib toolchain
produce identical ZIP bytes.

Bundle generation and payload completeness are tested. Fusion's discovery and loading
of this bundle have not been tested during the infrastructure refactor. Retain the
manual Scripts and Add-Ins loading route until the live acceptance checklist passes.

## Optional Windows MSI (source corrected; build/install pending)

`installer_source.wxs` targets WiX v3 syntax and a machine-wide 64-bit installation
under `C:\ProgramData\Autodesk\ApplicationPlugins\ZenExport.bundle`.
WiX is not installed in the current environment, so no MSI was produced or installed.
Use an existing trusted WiX v3 toolchain if MSI packaging is required.

From the repository root, with the WiX tools available on PATH:

```powershell
New-Item -ItemType Directory -Path dist -Force
candle.exe -arch x64 installer_source.wxs -out dist/installer_source.wixobj
light.exe dist/installer_source.wixobj -out dist/ZenExport-6.1.1.msi
```

The source now includes each runtime file as an individual installer component and
never installs personal context state. Runtime settings/logs are created separately
in the user's writable ZenExport data directory. The original UpgradeCode is retained.
The product version, bundle version, and Python runtime version are all 6.1.1.

## Release acceptance

1. Run automated checks in README, and create the bundle.
2. Compile/link MSI if distributing one, inspect its payload, and test install,
   upgrade, and uninstall on a clean Windows environment.
3. Confirm Fusion discovers exactly one installed copy. Stop any development copy
   before loading the installed one.
4. Complete the README live acceptance checklist, including reopening the first F3D
   and a linked assembly recovery test.
5. Sign distributable installers through the project's release process, if applicable.

Do not infer live Fusion compatibility or successful MSI installation from ZIP creation
or XML parsing alone.
