"""Pluggable backend implementations for the Assistant.

Provides lightweight wrappers around OpenAI and HuggingFace backends,
each created only if the corresponding library is installed.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, Protocol
import os
import logging

logger = logging.getLogger(__name__)

try:
    import openai
except Exception:
    openai = None

try:
    from transformers import pipeline
except Exception:
    pipeline = None


class BackendProtocol(Protocol):
    def generate_text(self, prompt: str) -> str:
        ...

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        ...


class OpenAIBackend:
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        if openai is None:
            raise ImportError("openai package is not installed")
        if api_key:
            openai.api_key = api_key
        if api_base:
            openai.api_base = api_base

    def generate_text(self, prompt: str) -> str:
        # Use Chat Completions if available, fallback to Completion
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=256
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            try:
                resp = openai.Completion.create(model="text-davinci-003", prompt=prompt, max_tokens=256)
                return resp.choices[0].text.strip()
            except Exception as e:
                logger.exception("OpenAI generation failed: %s", e)
                raise

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        # Ask the LLM to produce a Polars snippet. The caller must review/apply.
        system = (
            "You are an assistant that outputs a JSON object with keys 'text' and 'code'."
            " The 'code' value should be a Python expression using Polars (pl) that performs the requested transformation."
        )
        user_prompt = f"{prompt}\nReturn a JSON object with keys 'text' and 'code'."
        resp_text = self.generate_text(user_prompt)
        # naive extraction: try to find a JSON blob in the text
        import json

        try:
            j = json.loads(resp_text)
            return j
        except Exception:
            # fallback: return as plain text with empty code
            return {"text": resp_text, "code": "# Could not extract code from LLM response"}


class HuggingFaceBackend:
    def __init__(self, model: str = "gpt2"):
        if pipeline is None:
            raise ImportError("transformers is not installed")
        # text-generation pipeline
        self.gen = pipeline("text-generation", model=model)

    def generate_text(self, prompt: str) -> str:
        out = self.gen(prompt, max_length=256, do_sample=False)
        return out[0]["generated_text"].strip()

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        text = self.generate_text(prompt)
        return {"text": text, "code": "# HuggingFace backend returned text; manual extraction required"}


class DummyBackend:
    def generate_text(self, prompt: str) -> str:
        return "(dummy) I can suggest simple transformations like 'top N by column' or 'filter'."

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        return {"text": "(dummy) suggested transformation", "code": "# no-op"}


def create_backend(cfg: Dict[str, Any]):
    provider = cfg.get("provider", "dummy")
    if provider == "openai":
        api_key = cfg.get("openai_api_key") or os.environ.get("PARQCEL_OPENAI_API_KEY")
        api_base = cfg.get("openai_api_base") or os.environ.get("PARQCEL_OPENAI_API_BASE")
        return OpenAIBackend(api_key=api_key, api_base=api_base)
    if provider == "hf":
        model = cfg.get("hf_model", "gpt2")
        return HuggingFaceBackend(model=model)
    return DummyBackend()
