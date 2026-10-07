# Parqcel v0.2.0 — Spreadsheet workspace and Parquet analysis

Parqcel 0.2.0 adds a shared spreadsheet workspace for editable datasets and read-only Parquet previews, with System, Light and Dark themes.

## What's new

- A compact toolbar, recent files and drag-and-drop Parquet preview.
- Read-only lazy Parquet pages with schema and row counts, without loading the entire dataset into the editor.
- Copy selections with optional headers; hide, reorder, resize, auto-fit and rename columns.
- View-only number, percentage, scientific and date formatting that preserves the underlying values.
- Selection summaries, Find, Go To and an inspector for exact cell values, schema and background column profiles.
- Separate Save and Save As actions, plus atomic CSV export that preserves the editing session's unsaved state.
- An About dialog identifying the app as version 0.2.0.

## Reliability improvements

- Typed cell validation preserves data and history when an edit is invalid.
- Cell edits preserve grid selection; sorting and column changes participate in bounded undo/redo history.
- Background operations use revision checks and discard stale results. Repeated searches, profiles and preview page requests are coalesced to limit concurrent work.
- Unsaved-change prompts, atomic snapshot saves and coordinated shutdown protect editing workflows.
- AI-assisted transformations use validated declarative plans instead of executing generated Python.

## Windows download and upgrade

Download **Parqcel-Installer.exe** from this release's assets. This is the **base** desktop build for Parquet viewing/editing and CSV import/export. Python does not need to be installed separately.

To upgrade, close Parqcel, run the installer and choose the same application folder as your existing installation. Launch the app and verify **Help → About Parqcel** reports **0.2.0**.

The base installer excludes optional ML and AI dependencies. Those remain available through the documented Python installation extras; no ML installer is attached to this release.

## Scope and validation

- Editing loads the complete dataset. Preview stays read-only and paged; preview Find and column profiles operate on the current page.
- Display preferences do not change file contents. Copy uses raw values, independently of display formatting.
- The release installer comes from successful [CI run 37474199204](https://github.com/SMcQueen2023/Parqcel/actions/runs/37474199204), built from commit `8e154a052d96ac721c3c9d6069e30e4a52ad6a1a`.
- Validation covers Windows/Linux base and ML test profiles, code quality, installed-wheel checks, and standalone/installer smoke tests. The local full suite passed 314 tests.
