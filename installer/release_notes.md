Parqcel 0.1.0 — Desktop installer, AI assistant hardening, and stability fixes

This release provides a standalone Windows desktop installer and several reliability and safety improvements.

Highlights:

- Installer: Inno Setup installer (Parqcel-Installer.exe) that packages a standalone PyInstaller desktop build, installs it under `%LocalAppData%\Programs\Parqcel`, and creates Start Menu and optional Desktop shortcuts.
- Safety: Strict validation for LLM transformation responses with an explicit `InvalidTransformationResponse` error to avoid silently applying malformed payloads.
- Stability: Centralized temporary file management via `src/app/temp_files.py` to ensure plot and temp artifacts are cleaned up reliably.
- UX and packaging: Improved AI assistant/settings UX, a standalone Windows packaging flow, `run_parqcel.cmd` launcher for Python users, README updates, and packaged icon assets.
- Tests: Existing test suite updated with a parser test; run `pytest -q` to verify.

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
