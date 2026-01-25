"""Configuration helpers for AI backends.

Reads configuration from environment variables and an optional JSON file.
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


def _load_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    # optional config file
    cfg_file = os.environ.get("PARQCEL_CONFIG_FILE")
    if cfg_file:
        cfg.update(_load_file(cfg_file))

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

    # sensible defaults
    cfg.setdefault("provider", "dummy")
    return cfg
