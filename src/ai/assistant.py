from __future__ import annotations

from typing import Any, Dict, List, Optional

from .backends import BackendProtocol, DummyBackend


class Assistant:
    """Assistant core that delegates to a pluggable backend."""

    def __init__(self, backend: Optional[BackendProtocol] = None):
        self.backend = backend or DummyBackend()

    def ask(self, prompt: str) -> str:
        return self.backend.generate_text(prompt)

    def suggest_transformation(
        self, prompt: str, df_name: str = "df"
    ) -> Dict[str, Any]:
        return self.backend.generate_transformation(prompt, df_name=df_name)

    def explain_column(self, df_sample: List[Dict[str, Any]], column: str) -> str:
        values = [row.get(column) for row in df_sample[:100] if column in row]
        n = len(values)
        if n == 0:
            return f"Column `{column}` not found in sample."
        uniques = len(set(values))
        return f"Column `{column}`: {n} sampled values, {uniques} unique values."


def assistant_from_config(cfg: dict | None = None) -> Assistant:
    """Create an assistant using the configured backend."""
    from .config import load_config
    from .backends import create_backend

    if cfg is None:
        cfg = load_config()
    return Assistant(backend=create_backend(cfg))
