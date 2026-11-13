"""Measure optimizer time and native peak memory on generated or existing Parquet.

Generated inputs are built in a separate process; supplied input files are never
modified. All candidate and export files are temporary. Peak RSS is cumulative,
not a hard memory limit or an operation's independent allocation count.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from benchmark_desktop import peak_rss_bytes  # noqa: E402
from parqcel.core.io import write_parquet_verified_atomic  # noqa: E402
from parqcel.core.parquet_optimizer import (  # noqa: E402
    OptimizationOptions,
    analyze_parquet,
    estimate_working_memory,
    sorted_frame,
)
from parqcel.core.resource_limits import (  # noqa: E402
    MIB,
    available_memory_bytes,
    recommended_working_budget,
)


def generate_fixture(path: Path, rows: int, payload_bytes: int) -> None:
    values = pl.int_range(0, rows, eager=True).shuffle(seed=1729)
    frame = pl.DataFrame({"id": values}).with_columns(
        (pl.col("id") % 64).cast(pl.UInt32).alias("group"),
        (pl.col("id") * 0.01).alias("amount"),
        (1_760_000_000_000_000_000 + pl.col("id") * 1_000_000)
        .cast(pl.Datetime("ns"))
        .alias("timestamp"),
        pl.concat_str(
            pl.lit("x" * (payload_bytes - 12)),
            pl.col("id").cast(pl.String).str.pad_start(12, "0"),
        ).alias("payload"),
    )
    frame.write_parquet(path)


def benchmark(path: Path, working_mib: int | None) -> dict:
    start = time.perf_counter()
    frame = pl.read_parquet(path, glob=False, hive_partitioning=False)
    load_seconds = time.perf_counter() - start
    available = available_memory_bytes()
    options = OptimizationOptions(
        max_working_bytes=(
            working_mib * MIB if working_mib else recommended_working_budget()
        ),
        max_temporary_bytes=4 * 1024 * MIB,
    )
    stages = []

    def progress(message: str) -> None:
        stages.append({"stage": message, "process_peak_rss_bytes": peak_rss_bytes()})

    start = time.perf_counter()
    report = analyze_parquet(frame, options, progress=progress)
    analysis_seconds = time.perf_counter() - start
    with tempfile.TemporaryDirectory(prefix="parqcel-optimize-benchmark-") as directory:
        start = time.perf_counter()
        ordered = sorted_frame(frame, report.best.keys)
        exported_bytes = write_parquet_verified_atomic(
            ordered,
            Path(directory) / "optimized.parquet",
            options=report.write_options,
            verification_batch_rows=options.verification_batch_rows,
            max_temporary_bytes=options.max_temporary_bytes,
            protected_paths=[path],
        )
        export_seconds = time.perf_counter() - start
    assert exported_bytes == report.best.full_bytes
    return {
        "python": platform.python_version(),
        "polars": pl.__version__,
        "platform": platform.platform(),
        "rows": frame.height,
        "columns": frame.width,
        "dataframe_estimated_bytes": frame.estimated_size(),
        "available_memory_after_load_bytes": available,
        "options": asdict(options),
        "working_estimate": asdict(estimate_working_memory(frame, options)),
        "load_seconds": load_seconds,
        "analysis_seconds": analysis_seconds,
        "export_seconds": export_seconds,
        "baseline_bytes": report.baseline.full_bytes,
        "best_bytes": report.best.full_bytes,
        "best_keys": report.best.keys,
        "candidates": [asdict(candidate) for candidate in report.candidates],
        "process_peak_rss_bytes": peak_rss_bytes(),
        "stages": stages,
        "memory_measurement": "Cumulative process peak RSS including native allocations; fixture generation excluded",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Existing Parquet file, read-only")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--payload-bytes", type=int, default=216)
    parser.add_argument(
        "--working-mib", type=int, help="Override Automatic working budget"
    )
    parser.add_argument("--generate-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (
        args.rows <= 0
        or args.payload_bytes < 12
        or (args.working_mib is not None and args.working_mib <= 0)
    ):
        parser.error(
            "Rows and working MiB must be positive; payload bytes must be at least 12"
        )
    if args.generate_output is not None:
        generate_fixture(args.generate_output, args.rows, args.payload_bytes)
        return
    if args.input is not None:
        result = benchmark(args.input, args.working_mib)
        result["fixture"] = "User-provided Parquet; read-only"
    else:
        with tempfile.TemporaryDirectory(
            prefix="parqcel-optimizer-fixture-"
        ) as directory:
            path = Path(directory) / "input.parquet"
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(Path(__file__).resolve()),
                    "--generate-output",
                    str(path),
                    "--rows",
                    str(args.rows),
                    "--payload-bytes",
                    str(args.payload_bytes),
                ],
                check=True,
            )
            result = benchmark(path, args.working_mib)
            result["fixture"] = (
                "Shuffled IDs, numeric values, ns timestamps and repetitive strings; not representative of every dataset"
            )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
