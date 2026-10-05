# Security

Parqcel's optional assistant proposes dataframe transformations for user review. Application code parses suggestions into a fixed operation plan; it does not compile or execute generated Python.

## Transformation boundary

The implementation is in [parqcel/core/transformations.py](src/parqcel/core/transformations.py). Plans contain an `operations` list with supported select, filter, sort, drop, with-columns, head, tail and rename steps. Expressions use validated operation names and JSON arguments.

For example:

```json
{
  "operations": [
    {
      "op": "filter",
      "predicate": {
        "op": "gt",
        "args": [{"op": "col", "args": ["age"]}, 18]
      }
    },
    {"op": "sort", "columns": ["age"], "descending": true},
    {"op": "head", "count": 10}
  ]
}
```

A compatibility parser also accepts a restricted dataframe expression or a single assignment to `df` or `result`, such as `df.filter(pl.col("age") > 18)`. It translates syntax to the same validated plan. It is not a general Python interpreter.

The dispatcher supports only explicitly implemented operations. Suggestions cannot request arbitrary imports, attribute lookup, callbacks, file/network I/O, joins, loops or general Python calls. Unknown fields, invalid arguments and excessive text/structure are rejected. The legacy `ai.validator` API remains an inspection adapter; application execution uses the core plan executor.

This limits available capabilities, not the CPU or memory used by legitimate Polars work. A valid sort, aggregation or expression over a large dataset can still exhaust resources. There is no subprocess sandbox or enforced process-memory budget. Parser defects and vulnerabilities in Polars, Qt or optional dependencies remain possible.

## Data and network use

The desktop assistant sends the user's prompt to the selected backend. It does not automatically add dataframe rows or column schema, and it does not redact text that a user enters. A prompt may therefore disclose any sensitive information included in it.

The dummy backend is offline. The OpenAI backend uses the configured service endpoint. The Hugging Face backend uses a local transformers pipeline, which may download model weights. Review provider policies and deployment configuration before entering confidential content.

The OpenAI backend sets a 30-second timeout for each SDK request. Its compatibility fallback may issue a second request; this is not a 30-second total deadline. Local model loading and inference can take longer.

## Credentials and configuration

Settings are loaded from `~/.parqcel/config.json`, or the file selected by `PARQCEL_CONFIG_FILE`. Nonempty provider environment variables override file values. The GUI excludes API keys when saving settings.

The OpenAI factory resolves an explicit/configured key, then an environment key, then the optional OS keyring. When keyring is unavailable, the GUI does not fall back to writing secrets into its JSON file. Users can still place a key in a manually managed configuration file; avoid doing so.

Configuration diagnostics avoid printing credential values. Backend error messages can contain provider details; inspect logs before sharing them. Do not commit credentials or sensitive datasets.

## Dataset integrity and task lifetime

Cell values are validated before a session commit. Rejected edits preserve data, dtype and undo/redo state. History has bounded retention and is not a backup.

Background results apply only if the originating dataset and revision are still current. Cancellation discards callback delivery without forcibly stopping the worker. It does not undo side effects such as an in-progress file save. Shutdown waits for running tasks before cleaning temporary artifacts.

Parquet exports write a sibling temporary file and replace the destination after output completes. This avoids directly truncating a destination during normal write failure. It is not a backup, access-control mechanism or guarantee against every filesystem/power-loss scenario.

Dirty-state prompts help prevent accidental loss when opening another dataset or closing the editor. Save completion marks a session clean only when it acknowledges the same revision that was written.

## Developer checks

Keep generated suggestions data-only. New operations need explicit argument validation, an owned dispatcher implementation and rejection tests for unsupported syntax/capabilities.

```bash
python -m pytest tests/test_transformations.py tests/test_validator.py tests/test_ai_execute.py
python -m pytest tests/test_background_tasks.py tests/test_desktop_lifecycle.py tests/test_desktop_save.py
```

Review dependency changes and provider error handling. Use real event-loop tests for cancellation, widget destruction and stale completion; synchronous mocks cannot establish thread-lifecycle safety.

## Reporting a vulnerability

Use the repository's [GitHub Security Advisories](https://github.com/SMcQueen2023/Parqcel/security/advisories) to report privately. Include affected versions, a minimal reproduction and the data/system impact without exposing credentials or real sensitive data.

If a credential is exposed, revoke it through the provider, replace it and review recent usage.

Last updated: 2026-10-04.
