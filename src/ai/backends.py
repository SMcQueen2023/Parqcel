"""Pluggable backend implementations for the Assistant.

Provides lightweight wrappers around OpenAI and HuggingFace backends,
each created only if the corresponding library is installed.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Protocol
import os
import logging
import json
import re
import importlib.resources as resources

from parqcel.core.transformations import (
    TransformationValidationError,
    parse_transformation,
    plan_to_dict,
)

logger = logging.getLogger(__name__)
OPENAI_REQUEST_TIMEOUT_SECONDS = 30.0


class InvalidTransformationResponse(ValueError):
    """Raised when an LLM transformation payload fails schema validation."""


def _parse_transformation_response(resp_text: str) -> Dict[str, Any]:
    """Accept declarative operations or a validated legacy Polars expression.

    ``code`` remains the display/apply transport used by the existing widget.
    Structured responses put canonical plan JSON there, never generated Python.
    """
    try:
        data = json.loads(resp_text)
    except json.JSONDecodeError as exc:
        raise InvalidTransformationResponse("Response was not valid JSON") from exc

    if not isinstance(data, dict):
        raise InvalidTransformationResponse(
            "Response must be a JSON object with 'text' and 'code'"
        )

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidTransformationResponse("field 'text' must be a non-empty string")
    try:
        if "operations" in data:
            plan = plan_to_dict(
                parse_transformation({"operations": data["operations"]})
            )
            return {"text": text.strip(), "code": json.dumps(plan), **plan}
        code = data.get("code")
        if not isinstance(code, str) or not code.strip():
            raise InvalidTransformationResponse(
                "field 'code' must be a non-empty string or supply 'operations'"
            )
        parse_transformation(code)
    except TransformationValidationError as exc:
        raise InvalidTransformationResponse(str(exc)) from exc

    extra_keys = set(data.keys()) - {"text", "code", "operations"}
    if extra_keys:
        logger.debug(
            "Ignoring extra transformation response keys: %s",
            ", ".join(sorted(extra_keys)),
        )

    return {"text": text.strip(), "code": code.strip()}


def _load_prompt(template_name: str, **kwargs) -> str:
    """Load a prompt template from prompts.json with fallback to minimal templates.

    Args:
        template_name: Name of the template to load
        **kwargs: Template formatting arguments

    Returns:
        Formatted prompt string
    """
    try:
        data = (
            resources.files("ai").joinpath("prompts.json").read_text(encoding="utf-8")
        )
        prompts = json.loads(data)
        template = prompts.get(template_name)
        if template:
            for name, value in kwargs.items():
                template = template.replace("{" + name + "}", str(value))
            return template
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.debug(
            "Could not load prompt template '%s': %s. Using fallback.",
            template_name,
            e,
        )
    except Exception as e:
        logger.warning(
            "Unexpected error loading prompt template '%s': %s. Using fallback.",
            template_name,
            e,
        )

    # fallback minimal template
    if template_name == "transformation":
        return (
            "{prompt}\nReturn JSON with 'text' and 'operations'. "
            "Operations support select (columns), filter (predicate), sort (columns, descending), "
            "drop (columns), with_columns (expressions), head/tail (count), rename (mapping). "
            "Expressions are objects with 'op' and 'args': col(name), lit(value), "
            "add/sub/mul/div/eq/ne/gt/ge/lt/le/and/or(left,right), alias(expression,name)."
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
    def generate_text(self, prompt: str) -> str: ...

    def generate_transformation(
        self, prompt: str, df_name: str = "df"
    ) -> Dict[str, Any]: ...


class OpenAIBackend:
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None):
        openai = _lazy_openai()
        if api_key:
            openai.api_key = api_key
        if api_base:
            openai.api_base = api_base
        self._openai = openai

    def generate_text(self, prompt: str) -> str:
        """Generate text using OpenAI API.

        Tries ChatCompletion first, falls back to Completion if needed.

        Args:
            prompt: The prompt text

        Returns:
            Generated text response

        Raises:
            RuntimeError: If both API calls fail
        """
        openai = self._openai
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                request_timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
            )
            return resp.choices[0].message.content.strip()
        except AttributeError:
            # ChatCompletion not available, try Completion
            logger.debug("ChatCompletion not available, falling back to Completion API")
        except Exception as e:
            logger.warning(
                "ChatCompletion failed: %s, falling back to Completion API", e
            )

        try:
            resp = openai.Completion.create(
                model="text-davinci-003",
                prompt=prompt,
                max_tokens=256,
                request_timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
            )
            return resp.choices[0].text.strip()
        except Exception as e:
            logger.exception("OpenAI Completion API also failed: %s", e)
            raise RuntimeError(f"OpenAI text generation failed: {e}") from e

    def generate_transformation(
        self, prompt: str, df_name: str = "df"
    ) -> Dict[str, Any]:
        # Ask for a declarative plan. The caller must still review/apply.
        user_prompt = _load_prompt("transformation", prompt=prompt, df_name=df_name)
        resp_text = self.generate_text(user_prompt)
        try:
            parsed = _parse_transformation_response(resp_text)
        except InvalidTransformationResponse as exc:
            logger.warning("Invalid transformation response: %s", exc)
            parsed = {"text": f"Invalid transformation response: {exc}", "code": ""}
        return parsed


class HuggingFaceBackend:
    def __init__(self, model: str = "gpt2"):
        pipe = _lazy_hf_pipeline()
        # text-generation pipeline
        self.gen = pipe("text-generation", model=model)

    def generate_text(self, prompt: str) -> str:
        out = self.gen(prompt, max_length=256, do_sample=False)
        return out[0]["generated_text"].strip()

    def generate_transformation(
        self, prompt: str, df_name: str = "df"
    ) -> Dict[str, Any]:
        text = self.generate_text(
            _load_prompt("transformation", prompt=prompt, df_name=df_name)
        )
        try:
            parsed = _parse_transformation_response(text)
        except InvalidTransformationResponse as exc:
            logger.warning("Invalid transformation response: %s", exc)
            parsed = {"text": f"Invalid transformation response: {exc}", "code": ""}
        return parsed


class DummyBackend:
    """One offline backend shared by default and configured assistants."""

    def generate_text(self, prompt: str) -> str:
        return "(dummy) I can suggest simple transformations like 'top N by column' or 'filter'."

    def generate_transformation(
        self, prompt: str, df_name: str = "df"
    ) -> Dict[str, Any]:
        top = re.search(r"top\s+(\d+)\s+.*?by\s+(\w+)", prompt, flags=re.IGNORECASE)
        if top:
            count, column = int(top.group(1)), top.group(2)
            return _parse_transformation_response(
                json.dumps(
                    {
                        "text": f"Sort {column} descending and return top {count} rows.",
                        "operations": [
                            {"op": "sort", "columns": [column], "descending": True},
                            {"op": "head", "count": count},
                        ],
                    }
                )
            )
        filtered = re.search(
            r"where\s+(\w+)\s*(==|=)\s*'([\w\s-]+)'", prompt, flags=re.IGNORECASE
        )
        if filtered:
            column, value = filtered.group(1), filtered.group(3)
            return _parse_transformation_response(
                json.dumps(
                    {
                        "text": f"Filter where {column} equals {value!r}.",
                        "operations": [
                            {
                                "op": "filter",
                                "predicate": {
                                    "op": "eq",
                                    "args": [{"op": "col", "args": [column]}, value],
                                },
                            }
                        ],
                    }
                )
            )
        return {
            "text": "Try 'top 5 by revenue' or \"rows where status == 'active'\".",
            "code": "",
        }


def _saved_openai_key() -> str | None:
    """Read the optional OS keyring only when no explicit key was supplied."""
    try:
        import keyring

        value = keyring.get_password("parqcel", "openai_api_key")
        return value if isinstance(value, str) and value else None
    except Exception:
        logger.debug("No OpenAI API key could be read from the optional OS keyring")
        return None


def create_backend(cfg: Dict[str, Any]) -> BackendProtocol:
    provider = cfg.get("provider", "dummy")
    logger.info("Creating AI backend provider=%s", provider)
    if provider == "openai":
        api_key = (
            cfg.get("openai_api_key")
            or os.environ.get("PARQCEL_OPENAI_API_KEY")
            or _saved_openai_key()
        )
        api_base = cfg.get("openai_api_base") or os.environ.get(
            "PARQCEL_OPENAI_API_BASE"
        )
        logger.debug(
            "OpenAI backend configured (api_base_set=%s, api_key_present=%s)",
            bool(api_base),
            bool(api_key),
        )
        return OpenAIBackend(api_key=api_key, api_base=api_base)
    if provider == "hf":
        model = cfg.get("hf_model") or "gpt2"
        logger.debug("HuggingFace backend configured with model=%s", model)
        return HuggingFaceBackend(model=model)
    return DummyBackend()
