Parqcel 0.1.1 — Windows release packaging, async UX improvements, and reliability fixes

This release refreshes the Windows desktop release flow and packages the latest reliability, safety, and UX improvements.

Highlights:

- Windows packaging: refreshed standalone bundle and installer outputs for both the `base` and `ml` desktop profiles.
- Responsiveness: featurization, dimensionality reduction, AI assistant requests, and AI backend connection tests now run off the UI thread.
- Data editing reliability: dropped-column operations now participate correctly in undo/redo.
- AI safety and docs: stricter malformed-response handling plus README guidance that matches the current assistant scope.
- Tests: focused pytest coverage added for undo/redo regressions, async UI helpers, backend parsing, and AI settings workflows.

Important notes:

- The installer no longer depends on Python being installed on the target machine.
- The packaged feature set is determined by the desktop build profile. Use the default `base` profile for viewer/editor only, or build with the `ml` profile after installing `.[ml]` to ship ML tooling.
- Advanced AI dependencies remain better suited to the Python install path because they are large and environment-sensitive.

How to test the installer locally:

1) Build the desktop bundle with `scripts\build_windows_desktop.ps1`.
2) Compile `installer\parqcel.iss` with Inno Setup, or pass `-Installer` to the build script.
3) Run the generated `installer\dist\Parqcel-Installer.exe` on a test machine.
4) Launch Parqcel from Start Menu or the Desktop shortcut.

For CI: run PyInstaller first, then use the Inno Setup command-line `ISCC.exe` to compile and attach the produced EXE to a GitHub Release.
