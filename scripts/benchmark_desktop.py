"""Measure core desktop operations and native process peak memory.

Examples:
    python scripts/benchmark_desktop.py --rows 100000
    python scripts/benchmark_desktop.py --input dataset.parquet

Outputs JSON to stdout. Generated fixtures live in a temporary directory and
are built in a separate process so their allocation peak does not skew results.
Peak RSS is the process high-water mark, not an operation's allocation delta.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from logic.stats import generate_statistics  # noqa: E402
from parqcel.core.io import CsvTypes, read_dataset  # noqa: E402
from parqcel.core.parquet_source import ParquetSource  # noqa: E402
from parqcel.core.session import DatasetSession  # noqa: E402
from parqcel.core.values import is_editable_dtype  # noqa: E402


def peak_rss_bytes() -> int:
    """Include native Polars allocations in the process memory high-water mark."""
    if os.name != "nt":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)

    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.PeakWorkingSetSize)


def benchmark(path: Path, *, csv_types: CsvTypes = "strings") -> dict[str, Any]:
    operations = {}
    environment = {
        "python": platform.python_version(),
        "polars": pl.__version__,
        "platform": platform.platform(),
    }

    def measure(name: str, operation: Callable[[], Any]) -> Any:
        start = time.perf_counter()
        result = operation()
        operations[name] = {
            "seconds": time.perf_counter() - start,
            "process_peak_rss_bytes": peak_rss_bytes(),
        }
        return result

    baseline = peak_rss_bytes()
    if path.suffix.lower() == ".parquet":
        source = measure("preview_metadata", lambda: ParquetSource(path))
        measure("preview_first_page", lambda: source.fetch_page(0))
        if source.page_count > 1:
            measure(
                "preview_last_page", lambda: source.fetch_page(source.page_count - 1)
            )
    frame = measure("load", lambda: read_dataset(path, csv_types=csv_types))
    rows, columns, estimated_bytes = frame.height, frame.width, frame.estimated_size()
    session = DatasetSession(frame)
    editable = [
        name for name, dtype in frame.schema.items() if is_editable_dtype(dtype)
    ]
    edit_column = editable[0] if editable and frame.height else None
    if edit_column is not None:
        dtype = frame.schema[edit_column]
        original = frame[edit_column][0]
        if dtype.is_integer() or dtype.is_float():
            replacement = 0 if original != 0 else 1
        elif dtype == pl.String:
            replacement = "benchmark" if original != "benchmark" else ""
        elif dtype == pl.Boolean:
            replacement = not original
        else:
            replacement = None
        del frame
        measure("edit", lambda: session.set_cell(0, edit_column, replacement))
        restored = measure("undo", session.undo)
        operations["undo"]["restored"] = restored
        if not restored:
            operations["undo"]["note"] = "Snapshot exceeded the session history budget"
    else:
        del frame
        reason = "Dataset is empty or has no supported editable columns"
        operations["edit"] = {"skipped": reason}
        operations["undo"] = {"skipped": reason}
    stats = measure("stats", lambda: generate_statistics(session.get_dataframe()))
    return {
        **environment,
        "rows": rows,
        "columns": columns,
        "dataframe_estimated_bytes": estimated_bytes,
        "csv_types": csv_types,
        "edit_column": edit_column,
        "stats_characters": len(stats),
        "baseline_process_peak_rss_bytes": baseline,
        "process_peak_rss_bytes": peak_rss_bytes(),
        "memory_measurement": "Cumulative process peak RSS, including native allocations",
        "operations": operations,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, help="Existing dataset to read without modifying it"
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=100_000,
        help="Generated fixture rows (default: 100000)",
    )
    parser.add_argument("--csv-types", choices=("strings", "infer"), default="strings")
    args = parser.parse_args(argv)
    if args.rows <= 0:
        parser.error("--rows must be positive")
    if args.input is not None:
        result = benchmark(args.input, csv_types=args.csv_types)
        result["fixture"] = "user-provided; read-only"
    else:
        with tempfile.TemporaryDirectory(prefix="parqcel_benchmark_") as directory:
            path = Path(directory) / "numeric.parquet"
            generator = (
                "import sys; import polars as pl; "
                "values=pl.int_range(0,int(sys.argv[2]),eager=True); "
                "pl.DataFrame({'value':values,'scaled':values*0.5,'group':values%128})"
                ".write_parquet(sys.argv[1],row_group_size=10000)"
            )
            subprocess.run(
                [sys.executable, "-B", "-c", generator, str(path), str(args.rows)],
                check=True,
            )
            result = benchmark(path)
            result["fixture"] = (
                "temporary numeric fixture; generated in separate process"
            )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
