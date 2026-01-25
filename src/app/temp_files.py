from __future__ import annotations

import atexit
import logging
import os
import tempfile
import threading
from typing import Iterable, List

logger = logging.getLogger(__name__)


class TempFileManager:
    """Track and clean up temporary files created by the app."""

    def __init__(self) -> None:
        self._paths: set[str] = set()
        self._lock = threading.Lock()
        atexit.register(self.cleanup)

    def create(self, suffix: str = "", prefix: str = "parqcel_", directory: str | None = None) -> str:
        """Create a NamedTemporaryFile path and register it for cleanup."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=prefix, dir=directory)
        path = tmp.name
        tmp.close()
        self.track(path)
        return path

    def track(self, path: str | None) -> None:
        if not path:
            return
        with self._lock:
            self._paths.add(path)

    def cleanup(self, extra_paths: Iterable[str] | None = None) -> None:
        paths: List[str] = []
        with self._lock:
            paths.extend(self._paths)
            self._paths.clear()
            if extra_paths:
                paths.extend([p for p in extra_paths if p])

        for path in paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                logger.exception("Failed to remove temp file %s", path)
