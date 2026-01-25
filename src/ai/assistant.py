from __future__ import annotations

from typing import Protocol, Any, Dict, List, Optional
import re


class BackendProtocol(Protocol):
    def generate_text(self, prompt: str) -> str:
        ...

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        ...


class DummyBackend:
    """A tiny rule-based backend useful for local testing and scaffolding.

    This is not an LLM — it's a safe fallback that produces simple Polars
    transformation snippets for common NL requests like "top 5 by revenue".
    """

    def generate_text(self, prompt: str) -> str:
        prompt_low = prompt.lower()
        if "top" in prompt_low and "by" in prompt_low:
            return "I can sort and return top-N rows. I will propose a Polars snippet."
        return "I'm a local assistant prototype — ask me to summarize columns or suggest transformations."

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        """Return a dict with a human message and a `code` field containing a Polars snippet.

        The logic below uses simple regex heuristics — replaceable by a real LLM backend.
        """
        text = ""
        code = ""

        # Example: "show top 5 customers by revenue"
        m = re.search(r"top\s+(\d+)\s+.*by\s+(\w+)", prompt, flags=re.IGNORECASE)
        if m:
            n = int(m.group(1))
            col = m.group(2)
            text = f"Sorting `{col}` descending and returning top {n} rows."
            code = f"{df_name}.sort('{col}', descending=True).head({n})"
            return {"text": text, "code": code}

        # Example: "show rows where status == 'active'"
        m2 = re.search(r"where\s+(\w+)\s*(==|=)\s*'([\w\s-]+)'", prompt, flags=re.IGNORECASE)
        if m2:
            col = m2.group(1)
            val = m2.group(3)
            text = f"Filtering where `{col}` == '{val}'."
            code = f"{df_name}.filter(pl.col('{col}') == '{val}')"
            return {"text": text, "code": code}

        # Fallback suggestion
        text = "I couldn't identify a simple transformation; here's a placeholder suggestion."
        code = f"# Review and replace with a concrete Polars transformation on {df_name}\n{df_name}" 
        return {"text": text, "code": code}


class Assistant:
    """Assistant core that delegates to a pluggable backend.

    Methods return lightweight structures suitable for UI consumption.
    """

    def __init__(self, backend: Optional[BackendProtocol] = None):
        self.backend = backend or DummyBackend()

    def ask(self, prompt: str) -> str:
        return self.backend.generate_text(prompt)

    def suggest_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        return self.backend.generate_transformation(prompt, df_name=df_name)

    def explain_column(self, df_sample: List[Dict[str, Any]], column: str) -> str:
        # Very small heuristic explanation for scaffold
        values = [row.get(column) for row in df_sample[:100] if column in row]
        n = len(values)
        if n == 0:
            return f"Column `{column}` not found in sample."
        uniques = len(set(values))
        return f"Column `{column}`: {n} sampled values, {uniques} unique values."


def assistant_from_config(cfg: dict | None = None) -> "Assistant":
    """Create an Assistant wired to a backend according to `cfg`.

    If `cfg` is None, configuration is read from `ai.config.load_config()`.
    """
    from .config import load_config
    from .backends import create_backend

    if cfg is None:
        cfg = load_config()
    backend = create_backend(cfg)
    return Assistant(backend=backend)
