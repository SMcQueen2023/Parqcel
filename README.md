# Parqcel

![Parqcel logo](src/parqcel/assets/parqcel_icon.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Parqcel is a desktop Parquet viewer and editor built with PyQt6 and Polars. It supports CSV import, filtering, sorting, column statistics, typed cell editing, row insertion and measured Parquet export optimization. Optional packages add feature engineering, PCA/UMAP and an AI assistant.

Use **File → Preview Parquet...** to inspect a file through read-only lazy pages. Use **File → Open for editing...** to load a complete dataset for editing. Preview and editable pagination have different memory requirements; see [PERFORMANCE.md](PERFORMANCE.md).

## ☁️ Cloud-Native GCP (Phase 1)

Parqcel includes optional Phase 1 deployment scaffolding for Google Cloud Platform. The desktop app and Windows installer do not require GCP. Cloud deployment is manual-only and requires the configuration described in the rollout guide.

- Architecture and rollout guide: [docs/gcp-phase1-cloud-native.md](docs/gcp-phase1-cloud-native.md)
- GitHub Actions deployment workflow: [.github/workflows/gcp-deploy.yml](.github/workflows/gcp-deploy.yml)
- Cloud Build configs and Dockerfiles: [deploy/gcp](deploy/gcp)
- Terraform bootstrap for base GCP resources: [deploy/gcp/terraform](deploy/gcp/terraform)

---

## Desktop workflow

1. Preview a Parquet file, or open it in the editor. CSV import offers **Strings (preserve text)** or **Infer numbers and other types**; strings are the default.
2. Navigate pages and right-click a column header to sort, filter, rename, format, convert its type or request statistics. **View → Columns** searches and shows/hides columns; drag headers to rearrange the view.
3. Edit supported scalar cells, insert blank rows or paste new rows, and add or drop columns. Invalid edits leave the dataset and history unchanged. Complex column types remain read-only.
4. Use Undo/Redo buttons or the platform's standard keyboard shortcuts. History is bounded; an operation may exceed the retained history budget.
5. Use **Save** to update an existing Parquet file, **Save As...** for a new Parquet destination, or **Export CSV...** for a CSV snapshot. Writes use a temporary sibling file and replace the destination after successful output. CSV export leaves the Parquet saved/unsaved state unchanged.

### Spreadsheet workspace

- **View → Appearance** offers System, Light and Dark themes. The editor and preview share grid controls and appearance.
- **Ctrl+C** copies a rectangular selection as tab-separated raw values; **Copy with headers** includes column names. Display rounding does not affect copied values. Hidden columns are omitted and displayed column order is respected. Clipboard output is limited to 100,000 cells and 10 MiB.
- **Display format** controls numbers, percentages, scientific notation and dates without changing the underlying data. Null values are shown explicitly; the inspector displays the full unformatted cell value (up to 100,000 characters).
- The selection summary reports count, non-null/null counts and finite numeric sum, average, minimum and maximum. It covers selected visible cells on the current page, up to 50,000 cells.
- **Ctrl+F** finds literal values with case and column options, and **Ctrl+G** jumps to a row. Editor searches cover the complete loaded dataset; preview searches cover only the displayed page. Search uses raw values, independently of display formatting.
- **Inspector** shows the schema and selected cell. Request a column profile to calculate statistics in the background: the loaded dataset in the editor, or the current page in preview. Exact distinct counts can require substantial work on high-cardinality columns.
- Column widths, visibility, order and display formats are remembered by file path. These preferences do not modify the file or add undo history. Column renaming is an editable dataset operation and can be undone.
- In the editor, hover over a row-number boundary to reveal a boxed **+** on the border between rows. Its insertion line identifies the exact position, including before the first row and after the last row. Choose **Insert blank row** or **Paste clipboard as new rows**. **Add row** in the toolbar/Edit menu provides the same commands before the current row, or at the end of the dataset when no row is current.
- **Paste as new rows** (**Ctrl+Shift+V**) reads tab-separated clipboard cells in visible column order, starting with the first visible column. It inserts new rows without overwriting existing cells. The first clipboard row is treated as data, not guessed to be a header. Omitted columns become null; blank fields stay empty in string columns and become null in other supported columns. Invalid typed values reject the entire paste. Each insertion is one undo step, subject to the history budget. Clipboard input is limited to 10 MiB and inserted rows to 100,000 total dataset cells, including omitted columns. The existing typed editor rejects pasted temporal values beyond six fractional-second digits; existing nanosecond values remain intact. Normal **Ctrl+V** within a cell editor still pastes text into that cell.
- The start screen and File menu list recent files. Dropping a Parquet file opens read-only preview; dropping a CSV file starts the editor's import workflow.

**Help → About Parqcel** reports the application version. Package and installer version declarations are currently **0.2.0**. Row insertion and Parquet export optimization are unreleased checkout changes; the previous 0.2.0 installer does not include them. See [CHANGELOG.md](CHANGELOG.md) and the [Windows release checklist](installer/windows_release_checklist.md) when preparing a new version.

### Optimize Parquet export

Open a dataset for editing, then choose **Analysis → Optimize Parquet export...**. Optionally choose a preferred sort column, such as a date or a column you frequently filter on, and click **Analyze**. The comparison measures actual file sizes for a bounded set of sort orders, then fully measures and verifies the original order and the two best sample candidates. The smallest tested full output is selected; the original order wins ties.

Select a fully measured result and choose **Export selected…** to create a new Parquet copy. The export sorts whole rows stably and verifies column order, dtypes and every value before publishing the file. It leaves the editor, source file, undo history and saved/unsaved state unchanged. The active source cannot be used as the export destination.

Savings compare against an original-order rewrite with identical settings: Zstandard level 3, statistics enabled, 131,072-row groups and 1 MiB pages. They do not compare against the existing source file, whose encoding may differ. This search finds the smallest tested candidate, not a guaranteed global optimum. Smaller files do not necessarily make every query faster.

Analysis uses up to 20,000 sampled rows and 12 candidate orders, with a 512 MiB estimate for additional working memory and a 1 GiB temporary-file limit. The dataset must already fit in the editor; larger optimization jobs can be rejected by the resource checks. Memory checks are estimates, not a cap on native allocations. Cancel stops between native operations; closing the app waits for work to finish. Output preserves supported dataset values and schema, but does not retain custom source-file metadata. See [PERFORMANCE.md](PERFORMANCE.md) for details.

The title marks unsaved changes. Opening another file or closing the window offers Save, Discard and Cancel. Undoing back to the saved state clears the unsaved marker.

Long operations run in the background. Results apply only while the originating dataset and revision are still current. A save writes the snapshot captured when it began; later edits remain unsaved. **Cancel** discards result delivery while active work finishes naturally; it does not roll back a file write already in progress. Closing waits for active work before releasing its resources.

Parquet is the primary supported format. Excel remains a legacy optional import path: its reader engine is not bundled or supported by the base installation.

## Installation

### Windows desktop

Use the standalone Windows installer provided with a release. It includes Python and creates normal application shortcuts. The **base** build contains the editor and preview; the **ml** build also includes feature engineering and dimensionality reduction. Hosted/local AI stacks are excluded from both desktop build profiles.

### Python and source

Python 3.11 or newer is required. From a checkout:

```bash
python -m pip install .
parqcel
# Equivalent module entry point:
python -m parqcel
```

Choose additional packages as needed:

| Profile | Command |
| --- | --- |
| Core desktop | `python -m pip install .` |
| Feature engineering, PCA/UMAP and plots | `python -m pip install ".[ml]"` |
| OpenAI backend and keyring | `python -m pip install ".[ai-openai]"` |
| Local Hugging Face tooling | `python -m pip install ".[ai-local]"` |
| Combined optional AI/ML packages | `python -m pip install ".[ai]"` |
| Development tools and base tests | `python -m pip install -e ".[dev]"` |

Optional actions are unavailable when their dependencies are missing. Installing the ML profile does not require configuring an AI provider.

### Build a Windows package

```powershell
python -m pip install -c constraints/ci.txt ".[desktop-build]"
pwsh -File .\scripts\build_windows_desktop.ps1 -Clean -Profile base -Installer
```

For an ML build, install `".[ml,desktop-build]"` and use `-Profile ml`. Installer creation requires Inno Setup. Outputs are `dist\Parqcel` and `installer\dist\Parqcel-Installer.exe`; preserve separate output copies when producing multiple profiles.

## Command-line workflows

The CLI shares dataset I/O and transformation services with the desktop. Featurization and PCA require the ML profile.

```bash
parqcel-cli featurize input.parquet -o features.parquet
parqcel-cli pca input.csv --csv-types infer --components 3 -o embeddings.csv
parqcel-cli assistant "top 5 by revenue"
```

CSV defaults to strings in both desktop and CLI; specify `--csv-types infer` when inferred numeric columns are wanted. Featurization writes Parquet and PCA writes CSV. The assistant command prints a suggestion; it does not apply it to a dataset.

## AI assistant

The default `dummy` provider works offline and recognizes a small set of prompts. Optional `openai` and `hf` providers use their installed backends; the Hugging Face backend runs a local transformers pipeline and may download model weights.

Suggestions are declarative transformation plans. Review the suggestion before applying it. Supported dataframe operations are select, filter, sort, drop, with-columns, head, tail and rename. A restricted Polars-expression compatibility parser translates supported older suggestions into the same plan. Generated Python is never compiled or executed.

The assistant sends your prompt to the selected backend. Dataset contents and schema are not automatically added, and prompts are not automatically redacted. Resource-intensive valid operations can still consume substantial memory or CPU. See [SECURITY.md](SECURITY.md) for boundaries and credential handling.

Configure the provider through **Settings → AI Settings**, environment variables, or a JSON file:

```json
{
  "provider": "dummy",
  "hf_model": "gpt2"
}
```

The default file is `~/.parqcel/config.json`. `PARQCEL_CONFIG_FILE` selects a different file. Nonempty `PARQCEL_AI_PROVIDER`, `PARQCEL_OPENAI_API_KEY`, `PARQCEL_OPENAI_API_BASE` and `PARQCEL_HF_MODEL` override file values. GUI saves exclude API keys; keyring is the optional persistence mechanism.

## Development and checks

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src
```

ML-specific tests skip when their optional packages are absent. Install `".[dev,ml]"` in a separate environment to exercise that profile. Qt tests run offscreen and include real background-task lifecycle tests.

```bash
python scripts/benchmark_desktop.py --rows 100000
python scripts/benchmark_desktop.py --input data.parquet
```

The benchmark emits JSON timing and native process peak-memory measurements. It does not measure rendered UI latency or establish a universal memory limit.

The repository CI configuration covers Windows/Linux base tests on Python 3.11, ML tests on 3.13, installed-wheel smoke checks, lint/format/type checks, and Windows base desktop/installer smoke checks. Check the workflow run for results; configuration alone does not establish that a release passed.

[constraints/ci.txt](constraints/ci.txt) pins tested runtime, ML, QA and build-tool versions for CI. Each test job preserves its resolved dependency list as an artifact.

- [CONTRIBUTING.md](CONTRIBUTING.md): development boundaries and validation
- [PERFORMANCE.md](PERFORMANCE.md): memory behavior and benchmark interpretation
- [SECURITY.md](SECURITY.md): transformation and data boundaries
- [CHANGELOG.md](CHANGELOG.md): release history

## License and author

[MIT](LICENSE). Created by [Scott McQueen](https://github.com/SMcQueen2023).
