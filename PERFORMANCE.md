# Performance Considerations for Parqcel

This document outlines performance considerations and optimization opportunities for working with large datasets in Parqcel.

## Current Performance Characteristics

### Memory Usage

#### Undo/Redo System
- **Current Implementation**: Uses `df.clone()` to create full dataframe copies for each undo/redo state
- **Memory Impact**: For multi-GB files, each undo operation creates a complete copy in memory
- **Recommendation**: Consider implementing:
  - Transaction-based diffs (store only changes, not full copies)
  - Copy-on-write (COW) semantics leveraging Polars' internal optimizations
  - Configurable undo stack depth to limit memory growth

#### Data Model Operations
- **Current**: `PolarsTableModel.data()` and `setData()` may call `to_list()` on large columns
- **Impact**: For columns with millions of rows, this creates Python list objects in memory
- **Optimization**: Use Polars expressions directly where possible; avoid materialization

### Parsing Performance

#### DateTime Parsing (`logic/parsers.py`)
The `convert_series_to_datetime()` function tries multiple format strings sequentially:
- **Complexity**: O(n × m) where n = number of rows, m = number of format attempts
- **Current Optimization**: 
  - Sample-based format detection (first 500 rows)
  - Vectorized parsing with Polars (fast path)
  - Python fallback only for remaining nulls
- **Further Optimizations**:
  - Memoize detected format per column for repeated operations
  - Batch format detection across multiple columns
  - Allow users to specify format hints to skip detection

### UI Responsiveness

#### Long-Running Operations
Currently, operations like featurization, dimensionality reduction, and datetime parsing are synchronous:
- **Impact**: UI freezes during long operations
- **Recommendation**: 
  - Use `QThread` or `asyncio` for background processing
  - Add progress indicators for operations > 1 second
  - Allow cancellation of long-running operations

## Optimization Strategies

### For Large Files (>1GB)

1. **Lazy Loading**
   - Current: Entire file loaded into memory
   - Proposed: Stream rows in chunks, load only visible pages
   - Benefit: Reduced initial load time and memory footprint

2. **Column Statistics Caching**
   - Current: Statistics recomputed on each access
   - Proposed: Cache computed stats, invalidate on data changes
   - Benefit: Faster stats panel updates

3. **Efficient Filtering**
   - Current: Filters create new DataFrame each time
   - Optimization: Chain filters using Polars lazy API
   - Benefit: Reduced memory allocations

### For Repeated Operations

1. **Format Detection Cache**
   ```python
   # Example: Cache detected datetime formats per column
   _format_cache = {}  # {column_name: format_string}
   ```

2. **Feature Engineering Pipeline**
   - Store intermediate featurization results
   - Reuse TF-IDF vectorizers across runs
   - Cache fitted encoders for categorical columns

## Best Practices for Users

### Working with Large Datasets

1. **Memory Budget**
   - Expect ~3x file size in RAM (file + loaded data + undo buffer)
   - Limit undo depth for files > 1GB
   - Close other applications when working with large files

2. **Performance Tips**
   - Use filters to reduce working set size
   - Avoid frequent type conversions on large columns
   - Save intermediate results to Parquet for faster reloading

3. **DateTime Parsing**
   - For consistent date formats, first row detection is usually sufficient
   - If parsing is slow, consider preprocessing dates in a script
   - Use ISO 8601 format (YYYY-MM-DD) for fastest parsing

## Profiling Opportunities

To identify bottlenecks in production usage:

1. **Add Performance Metrics**
   ```python
   import time
   start = time.perf_counter()
   # operation
   elapsed = time.perf_counter() - start
   logger.info(f"Operation took {elapsed:.3f}s")
   ```

2. **Memory Profiling**
   - Use `tracemalloc` to track memory allocations
   - Profile undo/redo operations specifically

3. **UI Profiling**
   - Track time between user action and UI update
   - Target: <100ms for responsive interactions

## Future Optimizations

### Short-term (Low-hanging fruit)
- [ ] Cache column statistics
- [ ] Add progress bars for operations > 1s
- [ ] Async loading for large files

### Medium-term (Significant impact)
- [ ] Implement diff-based undo/redo
- [ ] Use QThread for long operations
- [ ] Lazy file loading with pagination

### Long-term (Architectural changes)
- [ ] Streaming data model for files > 10GB
- [ ] Distributed computing support (Dask/Ray)
- [ ] GPU acceleration for featurization (cuDF)

## Monitoring

Recommended metrics to track:
- File load time vs. file size
- Memory usage per operation type
- UI freeze duration (target: 0)
- Test with files: 100MB, 1GB, 10GB

## Conclusion

Parqcel is well-architected for typical use cases (files < 1GB). For very large datasets, implementing the recommendations above will significantly improve user experience. The most impactful changes are:
1. Diff-based undo/redo (memory)
2. Async operations with progress indicators (UX)
3. Column statistics caching (responsiveness)
