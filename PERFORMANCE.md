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

Every candidate uses the native Polars writer with Zstandard level 3, statistics enabled, 131,072-row groups and 1 MiB pages. Sample sizes narrow the search; they are not projected full-file sizes. The baseline and two best sample alternatives are then written on the full dataset and verified. Only those full measurements can become the recommendation or be exported. The original order wins ties. Comparisons use the original-order rewrite, not the existing source file's potentially different compression settings.

Verification checks metadata schema and row count, then compares every ordered value against the expected dataframe in lazy slices of up to **65,536 rows**. It preserves checks for dtypes, nested values, NaNs and temporal precision, without collecting a second complete dataframe. The previous verification batch is released before reading the next, and cancellation is checked between batches. Decoding a row group can still use more memory than the returned slice. This uses pinned **Polars 1.28.1** and does not provide out-of-core sorting.

The desktop's **Automatic** working budget is one quarter of currently available physical RAM, capped at **4 GiB**, with a **512 MiB** fallback if availability cannot be measured. It is recalculated when analysis starts. Manual choices are **512 MiB, 1, 2, 4 and 8 GiB**. Automatic uses a system snapshot, not a memory reservation or container/process limit. Resource selections persist, and changing them invalidates the prior comparison.

Estimates are calculated separately for sorting, writing and verification; the largest stage is compared with the additional working budget. They account for reordered data, sort indices, native encoding/materialization, callback buffers, verification batches and reader row groups. Average row width and native allocator behavior make these estimates approximate. The already-loaded input, undo history and other app allocations are additional; neither a budget nor the estimated peak is a hard RSS cap. Sample measurement has its own preflight, followed by full-data stage checks before measuring finalists.

The desktop temporary-file limit defaults to **4 GiB**, with **1, 4, 16 and 64 GiB** choices. A bounded writer checks cancellation, free space and the byte limit before each encoded buffer reaches disk. One candidate file is retained at a time and removed before the next; existing source/destination files require additional space. This disk limit does not cap encoding memory. Python callers using `OptimizationOptions()` directly retain **512 MiB** working and **1 GiB** temporary defaults; they can configure those limits and `verification_batch_rows` explicitly.

Export recomputes the selected stable ascending order with nulls last, writes a temporary sibling file, verifies every value and the ordered schema, syncs the file and atomically replaces the chosen destination. It refuses the active source, including resolved paths and existing file aliases. Verification or write failures leave existing destination bytes intact. Cancellation is cooperative between native operations and before publication; it cannot interrupt an active native sort/read/encoding call or undo a completed replacement. Closing waits for workers to drain.

This is a bounded search, not proof of maximal compression. Sampling can miss an order that would compress better on the full dataset. Unsupported Parquet round trips fail explicitly, and custom source metadata is not preserved. Compression and read speed are different objectives: a frequent filter/time key may improve statistics-based skipping even when another key produces a smaller file. See [Apache Parquet encodings](https://parquet.apache.org/docs/file-format/data-pages/encodings/), [Polars Parquet writer options](https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html), and [Polars scan statistics](https://docs.pola.rs/api/python/stable/reference/api/polars.scan_parquet.html).

Automatic codec/row-group searches and out-of-core optimization remain future work.

### Optimizer benchmark

```bash
python scripts/benchmark_optimizer.py --rows 2000000 --working-mib 1024
python scripts/benchmark_optimizer.py --input data.parquet
```

The script writes JSON with stage estimates, candidate sizes, analysis/export timings and cumulative native process peak RSS. It reads supplied files without modifying them; generated fixtures are created in a separate process, and candidate/export files are temporary. Without `--working-mib`, it uses Automatic. Its temporary-file limit is 4 GiB.

One local Windows 11 run with Python 3.13.2 and Polars 1.28.1 used 2,000,000 rows, five columns and a 1 GiB additional working budget. The synthetic fixture contains shuffled IDs, correlated numeric/time values and repetitive strings:

| Measurement | Result |
| --- | ---: |
| Estimated input dataframe size | 488,000,000 bytes (465.4 MiB) |
| Estimated additional peak, writing stage | 1,012,175,872 bytes (965.3 MiB) |
| Analysis / verified export time | 3.39 s / 1.21 s |
| Original-order / smallest tested file | 38,510,448 / 13,622,333 bytes |
| Cumulative process peak RSS, including input | 1,269,096,448 bytes (1.18 GiB) |

This is one synthetic run, not a prediction for other datasets or a before/after memory comparison. Fixture generation is excluded from the measured process; loading, analysis and export share its cumulative peak. Report hardware, cache conditions, versions, dataset shape, writer settings and limits, and repeat measurements on representative files before drawing conclusions.
