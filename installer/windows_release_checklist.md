# Windows Release Checklist

Use this checklist when producing the mainstream Windows release artifact for Parqcel.

## Goal

Ship `Parqcel-Installer.exe` as the primary download for mainstream Windows users.
Keep `pip` installation available as a secondary path for technical users.

## Prerequisites

- Project repository checked out locally
- Project virtual environment available at `.venv`
- Desktop packaging tools installed into the venv:
  - `./.venv/Scripts/python.exe -m pip install .[desktop-build]`
- Inno Setup 6 installed locally
  - Default compiler path: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
  - If installed elsewhere, pass the explicit path with `-InnoCompilerPath`

## Build Profiles

- `base`: mainstream viewer/editor build
  - Includes Parquet, CSV, and Excel viewing/editing
  - Excludes ML and AI stacks to keep the installer smaller and more predictable
- `ml`: advanced desktop build with featurization and dimensionality reduction
  - Install `.[ml,desktop-build]` into the venv before building
- AI-heavy workflows should stay on the Python install path unless there is a deliberate reason to ship a larger desktop bundle

## Build Commands

### Base installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_desktop.ps1 `
  -Clean `
  -PythonExecutable .\.venv\Scripts\python.exe `
  -Installer
```

### Base installer with explicit Inno Setup compiler path

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_desktop.ps1 `
  -Clean `
  -PythonExecutable .\.venv\Scripts\python.exe `
  -Installer `
  -InnoCompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

### ML installer

```powershell
.\.venv\Scripts\python.exe -m pip install .[ml,desktop-build]
powershell -ExecutionPolicy Bypass -File scripts/build_windows_desktop.ps1 `
  -Clean `
  -Profile ml `
  -PythonExecutable .\.venv\Scripts\python.exe `
  -Installer
```

## Build Outputs

- Standalone app bundle: `dist\Parqcel\Parqcel.exe`
- Windows installer: `installer\dist\Parqcel-Installer.exe`

## Smoke Test As a Mainstream User

1. Copy `installer\dist\Parqcel-Installer.exe` to a clean Windows machine, VM, or separate user profile.
2. Double-click the installer from File Explorer.
3. Accept the default install folder unless you have a reason to change it.
4. Optionally enable the Desktop shortcut.
5. Finish setup.
6. Launch Parqcel from the Start Menu.
7. Verify the app opens without requiring Python or a terminal.
8. Open a sample `.parquet`, `.csv`, and `.xlsx` file.
9. Verify save/export still works.
10. Confirm Parqcel appears in Installed Apps and uninstalls cleanly.

## Release Notes Checklist

- State whether the release is `base` or `ml`
- Call out that the installer does not require Python on the target machine
- Mention any intentionally excluded advanced features
- Attach `Parqcel-Installer.exe` to the release as the main Windows asset

## Recommendation

For mainstream releases, prefer the `base` installer unless there is a specific product reason to ship ML tooling to every Windows desktop user.
