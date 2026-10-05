"""Read-only, page-sized access to a local Parquet file without eager loading."""

from __future__ import annotations

from pathlib import Path

import polars as pl


class ParquetSource:
    """Cache file metadata and collect only the requested lazy slice.

    A page may still require decoding a larger Parquet row group. This limits
    retained dataframe size; it is not a hard cap on reader working memory.
    """

    def __init__(self, path: str | Path, page_size: int = 1000) -> None:
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("Page size must be positive")
        self.path = Path(path).absolute()
        if not self.path.is_file():
            raise FileNotFoundError(f"Parquet file not found: {self.path}")
        self.page_size = page_size
        self._fingerprint = self._file_fingerprint()
        scan = self._scan()
        self.schema = scan.collect_schema()
        self.row_count = int(scan.select(pl.len()).collect().item())
        self.page_count = (self.row_count + page_size - 1) // page_size
        self._check_unchanged()

    def _scan(self) -> pl.LazyFrame:
        return pl.scan_parquet(self.path, glob=False, hive_partitioning=False)

    def _file_fingerprint(self) -> tuple[int, int]:
        stat = self.path.stat()
        return stat.st_size, stat.st_mtime_ns

    def _check_unchanged(self) -> None:
        if self._file_fingerprint() != self._fingerprint:
            raise OSError("The Parquet file changed. Close and reopen its preview.")

    def fetch_page(self, page_index: int) -> pl.DataFrame:
        """Return a zero-based page; page zero of an empty file preserves schema."""
        if not isinstance(page_index, int) or not 0 <= page_index < max(
            1, self.page_count
        ):
            raise IndexError("Page is outside the Parquet file")
        self._check_unchanged()
        frame = (
            self._scan().slice(page_index * self.page_size, self.page_size).collect()
        )
        self._check_unchanged()
        return frame
