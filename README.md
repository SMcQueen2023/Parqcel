Parqcel is a PyQt6 + Polars desktop app for opening, exploring, editing, and analyzing Parquet/CSV/Excel files with fast pagination, undo/redo, stats, filters, featurization, dimensionality reduction, and an optional AI assistant.

## Install
- GUI only: `pip install .`
- With data-science extras (featurizer, PCA/UMAP): `pip install .[ml]`
- With AI assistant extras (OpenAI/HF clients): `pip install .[ai]`
- Dev/test stack: `pip install .[dev]`

## Run
- GUI: `parqcel` or `python -m parqcel`
- Headless CLI (featurize/PCA/assistant): `parqcel-cli --help`

## Core features
- Open Parquet, CSV, Excel; fast pagination on large data
- Inline editing with undo/redo; Save As Parquet
- Column stats, quick filters, type conversion, multi-sort
- Featurize (numeric/categorical/text), PCA/UMAP plots (Plotly)
- AI assistant (optional) to suggest Polars snippets; safe executor validates AST and only allows `df`/`pl` operations

## AI setup (optional)
- Config file: `%USERPROFILE%/.parqcel/config.json` (written by the GUI Settings dialog)
- Secrets: stored in OS keyring when available; not written to config
- Env overrides: `PARQCEL_AI_PROVIDER`, `PARQCEL_OPENAI_API_KEY`, `PARQCEL_OPENAI_API_BASE`, `PARQCEL_HF_MODEL`
- Backends: `dummy` (offline scaffold), `openai`, `hf` (transformers pipeline)

## Testing
```powershell
pip install .[dev]
pytest -q
```

## Developer notes
- Formatting/lint: `black`, `ruff` (see pyproject.toml)
- Type checking: `mypy` (mypy.ini)
- CI: `.github/workflows/ci.yml` installs `.[dev]` and runs `pytest -q`

## Author
Scott McQueen — Data Engineer
