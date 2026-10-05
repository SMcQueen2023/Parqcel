# Parqcel

![Parqcel logo](src/parqcel/assets/parqcel_icon.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Parqcel is a desktop Parquet viewer and editor built with PyQt6 and Polars. It supports CSV import, filtering, sorting, column statistics and typed cell editing. Optional packages add feature engineering, PCA/UMAP and an AI assistant.

Use **File → Preview Parquet...** to inspect a file through read-only lazy pages. Use **File → Open File** to load a complete dataset for editing. Preview and editable pagination have different memory requirements; see [PERFORMANCE.md](PERFORMANCE.md).

## Desktop workflow

1. Preview a Parquet file, or open it in the editor. CSV import offers **Strings (preserve text)** or **Infer numbers and other types**; strings are the default.
2. Navigate pages and right-click a column header to sort, filter, convert its type or request statistics.
3. Edit supported scalar cells, add columns or drop columns. Invalid edits leave the dataset and history unchanged. Complex column types remain read-only.
4. Use Undo/Redo buttons or the platform's standard keyboard shortcuts. History is bounded; an operation may exceed the retained history budget.
5. Choose **File → Save As...** to export Parquet. Saving writes a temporary sibling file and replaces the destination after successful output.

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
