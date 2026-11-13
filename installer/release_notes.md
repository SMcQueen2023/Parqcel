# Parqcel v0.3.0 — Add rows and optimize Parquet exports

November 12, 2026

Parqcel 0.3.0 builds on the 0.2.0 spreadsheet workspace with typed row insertion and measured Parquet compression comparisons. Both features run locally and are included in the base Windows installer.

## What's new since 0.2.0

- **Add rows:** hover over a row-number boundary to insert a blank row, or use **Add row** in the toolbar/Edit menu. The insertion marker identifies the position before, between or after rows.
- **Paste as new rows:** **Ctrl+Shift+V** inserts tab-separated clipboard data in visible column order. Typed validation rejects the entire paste if a field is invalid; one insertion is one undo step, within the history budget. It does not overwrite existing cells or guess a header row.
- **Optimize Parquet export:** compare actual file sizes for a bounded set of whole-row sort orders. The original order and up to two sample finalists receive full-data measurements and verification. Select a fully measured candidate and export a separate copy; the source file, editor order and saved/unsaved state remain unchanged.
- **Adjust resource budgets:** Automatic working memory uses one quarter of currently available RAM, capped at 4 GiB, with a 512 MiB fallback when availability cannot be measured. Manual choices range from 512 MiB to 8 GiB. The temporary-file limit defaults to 4 GiB and offers 1, 4, 16 and 64 GiB choices. Settings are remembered, and the dialog shows sort, write and verification estimates.
- **Verify large outputs in batches:** every ordered value and dtype is checked in batches of up to 65,536 rows, avoiding a second complete verification dataframe. Cancellation is checked between batches and before publication; failed validation leaves an existing destination intact.

## Windows download and upgrade

Download **Parqcel-Installer.exe** from the [v0.3.0 release assets](https://github.com/SMcQueen2023/Parqcel/releases/tag/v0.3.0). This is the **base** build for Parquet viewing/editing, CSV import/export, row insertion and optimized-copy export. Python does not need to be installed separately.

1. Close Parqcel before upgrading.
2. Run the new installer and choose the same application folder as your existing installation.
3. Reopen Parqcel and confirm **Help → About Parqcel** reports **0.3.0**.

The base installer excludes optional ML and AI dependencies. Use the documented Python extras for those features; no ML installer is attached to this release.

## Limits and measured behavior

Editing and sorting still require the complete dataset in memory. Preview remains read-only and paged. The optimizer uses pinned Polars 1.28.1; batched verification does not provide out-of-core sorting. Working-memory estimates cover additional work, excluding the loaded input, undo history and other application memory. They are not hard limits on native allocations.

The default search uses up to 20,000 sampled rows and 12 candidate orders, with identical Zstandard level 3 writer settings. It selects the smallest **tested** full output, not a guaranteed global optimum, and keeps the original order on size ties. Smaller files do not necessarily improve every query. Custom source Parquet metadata is not retained.

One local Windows 11 benchmark with 2,000,000 synthetic rows and five columns completed analysis in **3.39 seconds** and verified export in **1.21 seconds**, with **1.18 GiB** cumulative process peak memory. The original-order rewrite was 38,510,448 bytes; the smallest tested output was 13,622,333 bytes. This single run used Python 3.13.2, Polars 1.28.1 and a 1 GiB additional working budget. Its repetitive, correlated data is not representative of every dataset. See [benchmark details and reproduction commands](https://github.com/SMcQueen2023/Parqcel/blob/v0.3.0/PERFORMANCE.md#optimizer-benchmark).

Clipboard input is limited to 10 MiB and each insertion to 100,000 cells across the full dataset schema. Cancellation cannot interrupt an active native operation or undo a replacement already in progress; shutdown waits for active workers.

## Build provenance

The [GitHub release](https://github.com/SMcQueen2023/Parqcel/releases/tag/v0.3.0) records the exact source commit, successful CI run and installer SHA-256. The Windows asset is taken from that commit's `parqcel-windows-base` CI artifact. Validation covers Windows/Linux base and ML tests, code quality, installed-wheel checks, and standalone/installer smoke tests; the installer smoke checks cover a fresh installation and uninstallation.

See the [0.3.0 changelog](https://github.com/SMcQueen2023/Parqcel/blob/v0.3.0/CHANGELOG.md#030---2026-11-12) for the complete change list.
