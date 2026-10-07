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
  - Includes Parquet viewing/editing, lazy Parquet preview and CSV import/export
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
8. Preview and edit a sample `.parquet` file; import a `.csv` file.
9. Verify save/export still works.
10. Confirm Parqcel appears in Installed Apps and uninstalls cleanly.

## Release Notes Checklist

- State whether the release is `base` or `ml`
- Call out that the installer does not require Python on the target machine
- Mention any intentionally excluded advanced features
- Attach `Parqcel-Installer.exe` to the release as the main Windows asset

## Draft a GitHub Release from CI

1. Find a successful **CI** run for the version being released. Confirm the `desktop-package` job passed the standalone and installer smoke tests.
2. Download its `parqcel-windows-base` artifact and extract `Parqcel-Installer.exe` from the ZIP. CI artifacts are temporary build downloads; uploading one does not create a GitHub Release.
3. Confirm the package, `src/parqcel/__init__.py`, installer and app's About dialog report the intended version. Review `installer/release_notes.md` for that version and profile.
4. In **Releases → Draft a new release**, choose a new version tag such as `v0.2.0`, target the tested commit, add the title and release notes, and attach the extracted installer.
5. Choose **Save draft** to review it without publication. When ready, open the draft, choose **Set as latest release**, and click **Publish release**. A draft does not replace the current public latest release.

The equivalent CLI workflow pins the release to the build's exact commit:

```powershell
$runId = '<successful CI run ID>'
$releaseTag = 'v0.2.0'
$artifactDirectory = "dist/release-$releaseTag-$runId"
$targetSha = gh run view $runId --repo SMcQueen2023/Parqcel --json headSha --jq '.headSha'
gh run download $runId --repo SMcQueen2023/Parqcel --name parqcel-windows-base --dir $artifactDirectory
gh release create $releaseTag "$artifactDirectory/Parqcel-Installer.exe" `
  --repo SMcQueen2023/Parqcel --draft --target $targetSha `
  --title "Parqcel $releaseTag" --notes-file installer/release_notes.md
```

For GitHub's current UI instructions, see [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

## Recommendation

For mainstream releases, prefer the `base` installer unless there is a specific product reason to ship ML tooling to every Windows desktop user.
