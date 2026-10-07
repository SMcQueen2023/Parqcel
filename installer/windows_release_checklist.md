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
  - Includes Parquet viewing/editing, row insertion and clipboard paste, lazy Parquet preview, CSV import/export and measured Parquet export optimization
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
9. Verify Save, Save As and CSV export still work, including saved/unsaved state and reopening the output.
10. In Light and Dark themes, hover over row-number borders before, between and after rows. Check the boxed plus is centered at common display scales, then insert a blank row at each boundary. Verify pagination, Undo and Redo.
11. Paste multiple typed rows with **Ctrl+Shift+V**, including reordered/hidden columns. Check insertion position, one-step Undo and rejection of invalid values without partial changes. Read-only preview must not offer insertion.
12. Choose **Analysis → Optimize Parquet export...**, optionally select a preferred column and analyze a sample file. Check original-order and candidate sizes, full-measurement-only export, and original-order fallback when sorting does not improve size.
13. Export an optimized copy and reopen it. Check row count, column order/dtypes and values; sorting may change exported row order. Confirm the source bytes, editor order, unsaved state and Undo history remain unchanged, and that choosing the active source as destination is rejected.
14. Cancel analysis/export and close the optimizer during work. Verify controls recover, ordinary failed/cancelled exports preserve existing destinations, and opening/saving waits for an export still finishing after dialog close. A replacement already in progress may complete. Closing the app must wait for active work.
15. Confirm Parqcel appears in Installed Apps and uninstalls cleanly.

## Release Notes Checklist

- State whether the release is `base` or `ml`
- Call out that the installer does not require Python on the target machine
- Mention any intentionally excluded advanced features
- Explain that optimized export searches tested sort orders, preserves the editor, and uses additional memory and temporary disk space; link the [usage and limits](../README.md#optimize-parquet-export)
- Match notes to the exact tested commit and installer; do not reuse the historical v0.2.0 notes or installer for unreleased features
- Attach `Parqcel-Installer.exe` to the release as the main Windows asset

## Draft a GitHub Release from CI

1. Find a successful **CI** run for the version being released. Confirm the `desktop-package` job passed the standalone and installer smoke tests.
2. Download its `parqcel-windows-base` artifact and extract `Parqcel-Installer.exe` from the ZIP. CI artifacts are temporary build downloads; uploading one does not create a GitHub Release.
3. Confirm `pyproject.toml`, `src/parqcel/__init__.py`, the installer definition and the app's About dialog report the intended new version. Version changes must be included in the tested build commit. Move the appropriate Unreleased changelog entries into that release and rewrite `installer/release_notes.md` for its features, profile, validation and artifact provenance; that file currently describes the previous v0.2.0 build.
4. In **Releases → Draft a new release**, choose an unused version tag, target the tested commit, add the title and matching release notes, and attach the extracted installer. Do not move an existing release tag to new code.
5. Choose **Save draft** to review it without publication. When ready, open the draft, choose **Set as latest release**, and click **Publish release**. A draft does not replace the current public latest release.

The equivalent CLI workflow pins the release to the build's exact commit:

```powershell
$runId = '<successful CI run ID>'
$releaseTag = '<new-version-tag>'
$artifactDirectory = "dist/release-$releaseTag-$runId"
$targetSha = gh run view $runId --repo SMcQueen2023/Parqcel --json headSha --jq '.headSha'
gh run download $runId --repo SMcQueen2023/Parqcel --name parqcel-windows-base --dir $artifactDirectory
gh release create $releaseTag "$artifactDirectory/Parqcel-Installer.exe" `
  --repo SMcQueen2023/Parqcel --draft --target $targetSha `
  --title "Parqcel $releaseTag" --notes-file installer/release_notes.md
```

For GitHub's current UI instructions, see [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Pushing to `main` triggers CI; it does not publish a GitHub Release or update an installed desktop copy. Publish the matching installer as a release asset separately. Users upgrade by closing Parqcel and running the new installer against their existing application folder, then checking **Help → About Parqcel**.

## Recommendation

For mainstream releases, prefer the `base` installer unless there is a specific product reason to ship ML tooling to every Windows desktop user.
