"""Configuration helpers for AI backends.

Reads saved settings from ~/.parqcel/config.json by default. PARQCEL_CONFIG_FILE
selects a different file; nonempty setting environment variables override it.
Supported env vars:
- PARQCEL_AI_PROVIDER: 'openai' | 'hf' | 'dummy' (default: 'dummy')
- PARQCEL_OPENAI_API_KEY
- PARQCEL_OPENAI_API_BASE
- PARQCEL_HF_MODEL
- PARQCEL_CONFIG_FILE
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def _load_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        logger.warning("Ignoring AI config file with a non-object JSON value: %s", path)
        return {}
    return data


def load_config() -> Dict[str, Any]:
    cfg_file = os.environ.get("PARQCEL_CONFIG_FILE") or os.path.join(
        os.path.expanduser("~"), ".parqcel", "config.json"
    )
    cfg = _load_file(cfg_file)
    logger.debug("Read AI configuration from %s", cfg_file)

    # environment overrides
    env_map = {
        "provider": "PARQCEL_AI_PROVIDER",
        "openai_api_key": "PARQCEL_OPENAI_API_KEY",
        "openai_api_base": "PARQCEL_OPENAI_API_BASE",
        "hf_model": "PARQCEL_HF_MODEL",
    }
    for k, ev in env_map.items():
        v = os.environ.get(ev)
        if v:
            cfg[k] = v
            if "key" in k:
                logger.debug("Using AI credential from %s (value masked)", ev)
            else:
                logger.debug("Overriding %s from %s", k, ev)

    # sensible defaults
    cfg.setdefault("provider", "dummy")
    logger.info(
        "AI config resolved: provider=%s, hf_model=%s, openai_base_set=%s, api_key_present=%s",
        cfg.get("provider"),
        cfg.get("hf_model"),
        bool(cfg.get("openai_api_base")),
        bool(cfg.get("openai_api_key")),
    )
    return cfg
