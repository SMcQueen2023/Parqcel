"""Logging configuration helper for Parqcel.

Provides a small helper to configure the standard library `logging` module
from `config.toml` or the `PARQCEL_LOG_LEVEL` environment variable.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    import tomllib
except Exception:  # pragma: no cover - tomllib available on py3.11
    tomllib = None


def configure_logging(default_level: str = "INFO") -> None:
    """Configure root logging for the application.

    Priority: `PARQCEL_LOG_LEVEL` env var -> config.toml `app.log_level` -> default_level
    """
    level_name = os.environ.get("PARQCEL_LOG_LEVEL")

    if level_name is None:
        cfg_path = Path(__file__).parent.parent / "config.toml"
        if cfg_path.exists() and tomllib is not None:
            try:
                with cfg_path.open("rb") as fh:
                    cfg = tomllib.load(fh)
                level_name = cfg.get("app", {}).get("log_level")
            except Exception:
                level_name = None

    if not level_name:
        level_name = default_level

    level = getattr(logging, str(level_name).upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
