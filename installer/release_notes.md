Parqcel 0.1.0 — Installer, AI assistant hardening, and stability fixes

This release provides a Windows installer and several reliability and safety improvements.

Highlights:

- Installer: Inno Setup installer (Parqcel-Installer.exe) that copies the app to %AppData%\Parqcel, installs the project with AI extras (runs `pip install .[ai]`), and creates Start Menu and optional Desktop shortcuts.
- Safety: Strict validation for LLM transformation responses with an explicit `InvalidTransformationResponse` error to avoid silently applying malformed payloads.
- Stability: Centralized temporary file management via `src/app/temp_files.py` to ensure plot and temp artifacts are cleaned up reliably.
- UX and packaging: Improved AI assistant/settings UX, `run_parqcel.cmd` launcher (uses `py -3`), README updates, and packaged icon assets.
- Tests: Existing test suite updated with a parser test; run `pytest -q` to verify.

Important notes:

- The installer requires an existing Python installation on the target machine; by default it targets Python 3.13 but falls back to the `py` launcher or `python.exe` on PATH. The installer runs `pip install` at install time, so an internet connection is required to download dependencies (AI extras include large models/libraries).
- If you prefer a smaller install, consider modifying `installer/parqcel.iss` to install `.[ml]` or the base package instead of `.[ai]`.

How to test the installer locally:

1) Build the installer with Inno Setup (open `installer/parqcel.iss` and Compile).
2) Run the generated `dist\Parqcel-Installer.exe` on a test machine.
3) Launch Parqcel from Start Menu or the Desktop shortcut.

For CI: use the Inno Setup command-line `ISCC.exe` to compile and then attach the produced EXE to a GitHub Release.
