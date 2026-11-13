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

To reproduce CI dependencies in an existing environment, run `python -m pip install -c constraints/ci.txt -e ".[dev,ml]"` (omit `ml` for the base profile). Compare Qt runtime and SIP versions as well as PyQt when investigating GUI test failures; older local environments can satisfy the package requirements without matching CI.

## Code boundaries

- Put session state, dataset I/O and transformation operations in `src/parqcel/core` without Qt imports.
- Keep dialogs, task orchestration and rendering in `src/app`; the table model adapts session state to Qt.
- Route dataset changes through a session commit so history, revisions, dirty state and change signals stay consistent.
- Worker functions operate on captured data/configuration. GUI access belongs in callbacks delivered by `app.background_tasks`.
- Check dataset identity and revision before applying asynchronous results. Retain workers until natural completion; cancellation must not destroy a running thread.
- Keep assistant suggestions declarative. Add explicitly validated plan operations rather than generated-Python execution.
- Preserve the distinction between read-only lazy preview and fully materialized editing. Measure before claiming memory bounds.
- Row insertion must validate the complete typed block before one session commit, retaining existing row values and column dtypes. Cover page boundaries, visible clipboard column order, rejection and undo.
- Parquet optimization compares actual bytes with identical writer settings. Recommendations and exports require full-data verification; keep the original order on size ties. Export a separate copy without committing editor changes, and retain export-task tracking after the dialog closes so source changes wait for publication to finish.
- Verify every output row in bounded batches, including batch boundaries and the final partial batch; do not replace exact comparisons with sampling or hashes. Preserve dtype/order checks and cancellation before publication.
- Keep memory estimates specific to execution stages and distinguish them from enforced temporary-file byte limits. Automatic GUI sizing and direct Python defaults differ; document both. Retain Polars 1.28.1 compatibility and do not imply that batching verification makes sorting out of core.

Test the behavior at the relevant boundary: strict edit rejection, history retention, saved-state transitions, failed output, stale work, real widget destruction and packaged imports. Do not replace all asynchronous tests with synchronous callback mocks.

## Quality checks

```bash
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src
python -m pytest -q
```

For performance changes, use `python scripts/benchmark_desktop.py --rows 100000` and a representative `--input` dataset. For optimizer changes, run `python scripts/benchmark_optimizer.py --rows 2000000 --working-mib 1024` and `python scripts/benchmark_optimizer.py --input data.parquet`. Report stage estimates separately from cumulative native peak RSS, plus versions, workload and caveats from [PERFORMANCE.md](PERFORMANCE.md). Synthetic fixture generation runs in a separate process; its cost is excluded from the measured optimizer process.

Focused optimizer checks include `tests/test_parquet_optimizer.py`, `tests/test_optimized_export.py`, `tests/test_resource_limits.py` and `tests/test_parquet_optimizer_dialog.py`. Test exact batch-boundary verification, cancellation, failed writes, available-memory fallback and preference restoration without changing user settings.

## Installed-package checks

Build and install the wheel into a fresh environment instead of relying only on source-path imports:

```bash
python -m build --wheel
# Install the exact wheel from dist into the fresh environment.
python -I scripts/smoke_installed.py
```

The smoke script checks installed desktop/CLI imports, matching package/application versions, packaged resources, typed row insertion and undo, Parquet I/O, optimizer resource controls, and asynchronous analysis and verified export. It checks that optimization leaves editor order and saved state unchanged. Tests in the checkout add `src` to the import path, so they do not replace this packaging check.

The CI configuration runs base tests on Python 3.11 and ML tests on 3.13 across Windows and Linux. Separate jobs check Ruff, Black and mypy, then build and smoke-test the Windows base standalone application and installer. Treat actual workflow results as the evidence that these environments passed.

Windows packaging commands and profile differences are in [README.md](README.md). Standalone binaries support `--smoke-test`, including visible row insertion controls and the optimizer dialog; installer smoke checks belong in an isolated runner or disposable test environment.

Update existing documentation when behavior changes. Record changes after 0.3.0 under [CHANGELOG.md — Unreleased](CHANGELOG.md#unreleased), retaining historical release entries. Installer release notes must match the version, tested commit and artifact being published. Use the private reporting route in [SECURITY.md](SECURITY.md) for vulnerabilities.
