# Performance

## Preview versus editing

**File → Preview Parquet...** opens metadata and reads requested pages asynchronously. The default preview page contains 1,000 rows. A lazy Parquet scan collects a slice rather than retaining the whole dataset, and the preview has no edit history. It detects ordinary file changes and asks you to reopen the preview.

Page size is not a hard memory limit: Parquet row-group decoding, wide columns and reader buffers can require more memory than the displayed rows. Metadata work and a row-count query also take time. Preview reads run one at a time; rapid page requests retain only the latest pending destination and discard stale results.

**File → Open for editing...** eagerly loads the complete dataset into memory for editing. Its 10,000-row display pages reduce the number of displayed rows, not the size of the loaded dataframe. Filtering after opening does not avoid the initial load. CSV strings preserve text by default; choosing type inference changes both behavior and memory requirements.

## Editing and history

`DatasetSession` owns dataframe state independently of Qt. Cell edits use native Polars slices and a replacement value, avoiding full-column conversion to Python lists. Input is validated before committing, including dtype and representable range.

Row insertion joins native dataframe slices around a typed block of new rows. It preserves existing values and schema and commits once. Clipboard parsing runs in the background; a changed dataset invalidates the pending result. Clipboard input is capped at 10 MiB, and an insertion at 100,000 cells across the complete schema, including nulls in omitted columns. These limits bound inserted content, not total process memory.

Polars clones share buffers; a history snapshot is not necessarily a deep copy of every column. The [Polars clone documentation](https://docs.pola.rs/api/python/stable/reference/dataframe/api/polars.DataFrame.clone.html) describes this operation as avoiding data copying. Operations that replace buffers still increase retained memory, particularly repeated sorting, conversion and feature generation.

Each undo/redo stack defaults to at most **20 snapshots** and **256 MiB of estimated dataframe sizes**. This estimate conservatively counts shared buffers more than once and is not a process-memory cap. A snapshot larger than the budget is not retained. History limits are session constructor settings, not a preferences dialog.

## Background work

Opening, saving, filtering, sorting, type conversion, statistics, ML operations and assistant requests use background tasks. Callbacks run in the GUI thread. Dataset identity and revision checks prevent late results from overwriting newer edits or another open file. Statistics caches are invalidated by dataset changes.

Cancellation suppresses callbacks; it does not forcibly interrupt native calculations, network requests or file output. Closing waits asynchronously for active tasks to finish. A slow external request can therefore delay shutdown. The OpenAI backend uses a timeout per request, but fallback requests and local inference do not create a single guaranteed total deadline.

Saving captures a dataframe snapshot and writes through a temporary sibling file before replacing the destination. An edit during saving remains dirty. Temporary output consumes additional disk space; cancellation can still leave the requested save completed.

## Measure your workload

From an installed development checkout:

```bash
python scripts/benchmark_desktop.py --rows 100000
python scripts/benchmark_desktop.py --rows 1000000
python scripts/benchmark_desktop.py --input data.parquet
python scripts/benchmark_desktop.py --input data.csv --csv-types infer
```

The benchmark reports JSON containing:

- Python, Polars and platform versions, dataset dimensions and estimated dataframe bytes.
- Parquet metadata, first-page and last-page timings where applicable.
- Eager load, cell edit, undo and statistics timings.
- Whether undo retained a usable snapshot.
- Native process peak resident memory, including Polars allocations.

Windows uses `PeakWorkingSetSize`; Linux/macOS use `resource.getrusage`. Values are cumulative process high-water marks, not per-operation allocation deltas. Preview and eager measurements share a process, so their peaks are not independent memory comparisons. Use separate runs and representative files when comparing changes.

Generated numeric fixtures are written in a temporary directory by a separate process, keeping fixture-generation allocations out of the measured process. The default is 100,000 rows. Existing input files are read without modification, and empty or unsupported edit columns produce explicit skipped metrics.

These measurements exclude GUI painting, user interaction, cold-storage guarantees and provider latency. Repeat runs and report file shape, compression, cache conditions and hardware before drawing performance conclusions. Dense ML feature matrices, high-cardinality text/categorical columns and global statistics may dominate memory even when page navigation is cheap.

Feature generation checks a default 256 MiB budget before allocating dense numeric/categorical matrices, densifying TF-IDF, or concatenating the result. It estimates dense components plus output, not total process memory; source data, sparse matrices and estimator scratch space are additional. Reduce rows/features when this guard rejects an operation. Projection sampling occurs before NumPy conversion.

Further optimization should follow measured bottlenecks: bounded statistics caches, chunk-aware import and explicit materialization policies can build on the current preview/session boundaries.

## Parquet compression comparison

**Analysis → Optimize Parquet export...** measures candidate row orders for the current editor snapshot. It runs in one sequential background worker and never commits a change to the session. The dialog is modal to the editor, preventing concurrent edits or file changes during export. Opening it while other work is active asks the user to wait. Changed dataset identities or revisions invalidate pending results. Opening or saving a dataset also waits for an export to finish after its dialog is closed, so a cancelled writer cannot race with a new active source.

The default search samples up to 20,000 rows uniformly over the full row range with a fixed seed, retaining their original relative order for the sample baseline. It profiles distinct counts, adjacent runs and string widths. Up to 12 orders include the unchanged order, single-column keys and pairs, giving early slots to both repeating values and high-cardinality numeric/time columns. A preferred column influences the candidates; it does not force the recommendation. Constant or unsupported sort keys are skipped. Nested columns remain attached to their whole rows.

Every candidate uses the native Polars writer with Zstandard level 3, statistics enabled, 131,072-row groups and 1 MiB pages. Sample sizes narrow the search; they are not projected full-file sizes. The baseline and two best sample alternatives are then written on the full dataset and reread to verify ordered schema and exact values. Only those full measurements can become the recommendation or be exported. The original order wins ties. Comparisons use the original-order rewrite, not the existing source file's potentially different compression settings.

The additional working-memory estimate is limited to 512 MiB by default. It accounts for sampled/sorted frames, sorting indices, an encoded buffer and a verification reread; the input, undo history and other app allocations are additional. Native allocator and codec behavior prevent this from being a hard RSS cap. A temporary candidate is removed before writing the next. Preflight estimates and free-space checks reject unsuitable jobs, and a bounded writer limits each encoded temporary file to 1 GiB. Python callers can supply validated `OptimizationOptions` for other budgets; the desktop currently uses these defaults. Out-of-core sorting is not implemented.

Export recomputes the selected stable ascending order with nulls last, writes a temporary sibling file, verifies every value and the ordered schema, syncs the file and atomically replaces the chosen destination. It refuses the active source, including resolved paths and existing file aliases. Verification or write failures leave existing destination bytes intact. Cancellation is cooperative between native operations and before publication; it cannot interrupt an active native sort/read/encoding call or undo a completed replacement. Closing waits for workers to drain.

This is a bounded search, not proof of maximal compression. Sampling can miss an order that would compress better on the full dataset. Unsupported Parquet round trips fail explicitly, and custom source metadata is not preserved. Compression and read speed are different objectives: a frequent filter/time key may improve statistics-based skipping even when another key produces a smaller file. See [Apache Parquet encodings](https://parquet.apache.org/docs/file-format/data-pages/encodings/), [Polars Parquet writer options](https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html), and [Polars scan statistics](https://docs.pola.rs/api/python/stable/reference/api/polars.scan_parquet.html).

Automatic codec/row-group searches and out-of-core optimization remain future work. For local comparisons, report dataset shape, Polars version, writer settings, sample/candidate limits, tested full byte counts, elapsed time and process peak memory; synthetic results are not a prediction for other files.
