# Contributing

Keep changes focused and explain the user-visible result, relevant tests and remaining limitations in the pull request. Discuss substantial design changes in an issue before starting a broad rewrite.

## Development profiles

Use Python 3.11 or newer and a virtual environment. From the repository root:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

The base profile should remain usable without NumPy, scikit-learn or AI packages. ML tests skip when optional dependencies are absent. Exercise them in a separate environment:

```bash
python -m pip install -e ".[dev,ml]"
python -m pytest -q
```

Keep external AI requests mocked in automated tests. Qt tests default to `QT_QPA_PLATFORM=offscreen`.

## Code boundaries

- Put session state, dataset I/O and transformation operations in `src/parqcel/core` without Qt imports.
- Keep dialogs, task orchestration and rendering in `src/app`; the table model adapts session state to Qt.
- Route dataset changes through a session commit so history, revisions, dirty state and change signals stay consistent.
- Worker functions operate on captured data/configuration. GUI access belongs in callbacks delivered by `app.background_tasks`.
- Check dataset identity and revision before applying asynchronous results. Retain workers until natural completion; cancellation must not destroy a running thread.
- Keep assistant suggestions declarative. Add explicitly validated plan operations rather than generated-Python execution.
- Preserve the distinction between read-only lazy preview and fully materialized editing. Measure before claiming memory bounds.

Test the behavior at the relevant boundary: strict edit rejection, history retention, saved-state transitions, failed output, stale work, real widget destruction and packaged imports. Do not replace all asynchronous tests with synchronous callback mocks.

## Quality checks

```bash
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src
python -m pytest -q
```

For performance changes, use `python scripts/benchmark_desktop.py --rows 100000` and a representative `--input` dataset. Report versions, workload and measurement caveats from [PERFORMANCE.md](PERFORMANCE.md).

## Installed-package checks

Build and install the wheel into a fresh environment instead of relying only on source-path imports:

```bash
python -m build --wheel
# Install the exact wheel from dist into the fresh environment.
python -I scripts/smoke_installed.py
```

The smoke script checks installed desktop/CLI imports, packaged resources, session undo and Parquet I/O. Tests in the checkout add `src` to the import path, so they do not replace this packaging check.

The CI configuration runs base tests on Python 3.11 and ML tests on 3.13 across Windows and Linux. Separate jobs check Ruff, Black and mypy, then build and smoke-test the Windows base standalone application and installer. Treat actual workflow results as the evidence that these environments passed.

Windows packaging commands and profile differences are in [README.md](README.md). Standalone binaries support `--smoke-test`; installer smoke checks belong in an isolated runner or disposable test environment.

Update existing documentation when behavior changes. Record unreleased changes in [CHANGELOG.md](CHANGELOG.md), and use the private reporting route in [SECURITY.md](SECURITY.md) for vulnerabilities.
