"""Pluggable backend implementations for the Assistant.

Provides lightweight wrappers around OpenAI and HuggingFace backends,
each created only if the corresponding library is installed.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, Protocol
import os
import logging
import json
import importlib.resources as resources

logger = logging.getLogger(__name__)


class InvalidTransformationResponse(ValueError):
    """Raised when an LLM transformation payload fails schema validation."""


def _parse_transformation_response(resp_text: str) -> Dict[str, str]:
    """Parse and validate backend response into {text, code}.

    Expected schema: a JSON object with string fields 'text' and 'code'.
    Raises InvalidTransformationResponse when validation fails.
    """
    try:
        data = json.loads(resp_text)
    except json.JSONDecodeError as exc:
        raise InvalidTransformationResponse("Response was not valid JSON") from exc

    if not isinstance(data, dict):
        raise InvalidTransformationResponse("Response must be a JSON object with 'text' and 'code'")

    text = data.get("text")
    code = data.get("code")

    errors = []
    if not isinstance(text, str) or not text.strip():
        errors.append("field 'text' must be a non-empty string")
    if not isinstance(code, str) or not code.strip():
        errors.append("field 'code' must be a non-empty string")

    if errors:
        raise InvalidTransformationResponse("; ".join(errors))

    extra_keys = set(data.keys()) - {"text", "code"}
    if extra_keys:
        logger.debug("Ignoring extra transformation response keys: %s", ", ".join(sorted(extra_keys)))

    return {"text": text.strip(), "code": code.strip()}


def _load_prompt(template_name: str, **kwargs) -> str:
    try:
        data = resources.files("ai").joinpath("prompts.json").read_text(encoding="utf-8")
        prompts = json.loads(data)
        template = prompts.get(template_name)
        if template:
            return template.format(**kwargs)
    except Exception:
        pass
    # fallback minimal template
    if template_name == "transformation":
        return (
            "{prompt}\nReturn a JSON object with keys 'text' and 'code'. "
            "The 'code' must be a single Python expression that operates on the Polars DataFrame named '{df_name}' using the 'pl' module."
        ).format(**kwargs)
    if template_name == "ping":
        return "Respond with OK"
    return kwargs.get("prompt", "")


def _lazy_openai():
    try:
        import openai  # type: ignore
    except Exception as exc:
        raise ImportError("openai package is not installed") from exc
    return openai


def _lazy_hf_pipeline():
    try:
        from transformers import pipeline  # type: ignore
    except Exception as exc:
        raise ImportError("transformers package is not installed") from exc
    return pipeline


class BackendProtocol(Protocol):
    def generate_text(self, prompt: str) -> str:
        ...

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        ...


class OpenAIBackend:
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        openai = _lazy_openai()
        if api_key:
            openai.api_key = api_key
        if api_base:
            openai.api_base = api_base
        self._openai = openai

    def generate_text(self, prompt: str) -> str:
        # Use Chat Completions if available, fallback to Completion
        openai = self._openai
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
        user_prompt = _load_prompt("transformation", prompt=prompt, df_name=df_name)
        resp_text = self.generate_text(user_prompt)
        try:
            parsed = _parse_transformation_response(resp_text)
        except InvalidTransformationResponse as exc:
            logger.warning("Invalid transformation response: %s", exc)
            parsed = {"text": f"Invalid transformation response: {exc}", "code": ""}
        if not parsed.get("code"):
            parsed["code"] = "# Could not extract code from LLM response"
        return parsed


class HuggingFaceBackend:
    def __init__(self, model: str = "gpt2"):
        pipe = _lazy_hf_pipeline()
        # text-generation pipeline
        self.gen = pipe("text-generation", model=model)

    def generate_text(self, prompt: str) -> str:
        out = self.gen(prompt, max_length=256, do_sample=False)
        return out[0]["generated_text"].strip()

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        text = self.generate_text(prompt)
        try:
            parsed = _parse_transformation_response(text)
        except InvalidTransformationResponse as exc:
            logger.warning("Invalid transformation response: %s", exc)
            parsed = {"text": f"Invalid transformation response: {exc}", "code": ""}
        if not parsed.get("code"):
            parsed["code"] = "# HuggingFace backend returned text; manual extraction required"
        return parsed


class DummyBackend:
    def generate_text(self, prompt: str) -> str:
        return "(dummy) I can suggest simple transformations like 'top N by column' or 'filter'."

    def generate_transformation(self, prompt: str, df_name: str = "df") -> Dict[str, Any]:
        return {"text": "(dummy) suggested transformation", "code": "# no-op"}


def create_backend(cfg: Dict[str, Any]):
    provider = cfg.get("provider", "dummy")
    logger.info("Creating AI backend provider=%s", provider)
    if provider == "openai":
        api_key = cfg.get("openai_api_key") or os.environ.get("PARQCEL_OPENAI_API_KEY")
        api_base = cfg.get("openai_api_base") or os.environ.get("PARQCEL_OPENAI_API_BASE")
        logger.debug(
            "OpenAI backend configured (api_base_set=%s, api_key_present=%s)",
            bool(api_base),
            bool(api_key),
        )
        return OpenAIBackend(api_key=api_key, api_base=api_base)
    if provider == "hf":
        model = cfg.get("hf_model", "gpt2")
        logger.debug("HuggingFace backend configured with model=%s", model)
        return HuggingFaceBackend(model=model)
    return DummyBackend()
