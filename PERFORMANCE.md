# Performance

## Preview versus editing

**File → Preview Parquet...** opens metadata and reads requested pages asynchronously. The default preview page contains 1,000 rows. A lazy Parquet scan collects a slice rather than retaining the whole dataset, and the preview has no edit history. It detects ordinary file changes and asks you to reopen the preview.

Page size is not a hard memory limit: Parquet row-group decoding, wide columns and reader buffers can require more memory than the displayed rows. Metadata work and a row-count query also take time. Rapid page changes can leave earlier reads finishing in the background, although their stale results are discarded.

**File → Open File** eagerly loads the complete dataset into memory for editing. Its 10,000-row display pages reduce the number of displayed rows, not the size of the loaded dataframe. Filtering after opening does not avoid the initial load. CSV strings preserve text by default; choosing type inference changes both behavior and memory requirements.

## Editing and history

`DatasetSession` owns dataframe state independently of Qt. Cell edits use native Polars slices and a replacement value, avoiding full-column conversion to Python lists. Input is validated before committing, including dtype and representable range.

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

Further optimization should follow measured bottlenecks: page-request coalescing, bounded statistics caches, chunk-aware import and explicit materialization policies can build on the current preview/session boundaries.
