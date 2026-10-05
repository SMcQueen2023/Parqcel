import pytest

from ai.backends import (
    HuggingFaceBackend,
    InvalidTransformationResponse,
    OpenAIBackend,
    _parse_transformation_response,
    create_backend,
)


def test_parse_transformation_response_valid():
    resp = _parse_transformation_response('{"text": "ok", "code": "df.head()"}')
    assert resp == {"text": "ok", "code": "df.head()"}


def test_parse_transformation_response_invalid_schema():
    with pytest.raises(InvalidTransformationResponse):
        _parse_transformation_response('{"text": 123, "code": ""}')


def test_parse_transformation_response_non_json():
    with pytest.raises(InvalidTransformationResponse):
        _parse_transformation_response("not json")


def test_create_backend_openai_uses_config(monkeypatch):
    class FakeOpenAI:
        api_key = None
        api_base = None

    monkeypatch.setattr("ai.backends._lazy_openai", lambda: FakeOpenAI)

    backend = create_backend(
        {"provider": "openai", "openai_api_key": "k", "openai_api_base": "u"}
    )

    assert isinstance(backend, OpenAIBackend)
    assert backend._openai is FakeOpenAI
    assert FakeOpenAI.api_key == "k"
    assert FakeOpenAI.api_base == "u"


def test_create_backend_hf_uses_model(monkeypatch):
    def fake_pipeline(task, model):
        assert task == "text-generation"
        return lambda prompt, max_length, do_sample: [
            {"generated_text": '{"text": "ok", "code": "df.head()"}'}
        ]

    monkeypatch.setattr("ai.backends._lazy_hf_pipeline", lambda: fake_pipeline)

    backend = create_backend({"provider": "hf", "hf_model": "demo-model"})

    assert isinstance(backend, HuggingFaceBackend)


def test_openai_backend_invalid_transformation_response_falls_back(monkeypatch):
    class FakeOpenAI:
        api_key = None
        api_base = None

    monkeypatch.setattr("ai.backends._lazy_openai", lambda: FakeOpenAI)
    backend = OpenAIBackend(api_key="k")
    monkeypatch.setattr(backend, "generate_text", lambda prompt: '{"text": "ok"}')

    result = backend.generate_transformation("show top 5", df_name="df")

    assert result["text"].startswith("Invalid transformation response")
    assert result["code"] == ""


def test_hf_backend_invalid_transformation_response_falls_back(monkeypatch):
    def fake_pipeline(task, model):
        return lambda prompt, max_length, do_sample: [{"generated_text": "not json"}]

    monkeypatch.setattr("ai.backends._lazy_hf_pipeline", lambda: fake_pipeline)
    backend = HuggingFaceBackend(model="demo-model")

    result = backend.generate_transformation("show top 5", df_name="df")

    assert result["text"].startswith("Invalid transformation response")
    assert result["code"] == ""


def test_structured_response_supplies_safe_widget_transport():
    import json
    import polars as pl
    from parqcel.core.transformations import execute_transformation

    response = _parse_transformation_response(
        json.dumps(
            {
                "text": "Take two rows",
                "operations": [{"op": "head", "count": 2}],
                "code": "df.write_csv('ignored-generated-code.csv')",
            }
        )
    )
    assert "write_csv" not in response["code"]
    assert (
        execute_transformation(pl.DataFrame({"a": [1, 2, 3]}), response["code"]).height
        == 2
    )


def test_legacy_backend_code_is_validated():
    import json

    with pytest.raises(InvalidTransformationResponse):
        _parse_transformation_response(
            json.dumps({"text": "unsafe", "code": "df.write_csv('output')"})
        )


def test_prompt_contains_request_and_structured_schema():
    from ai.backends import _load_prompt

    prompt = _load_prompt(
        "transformation", prompt="Show top 5 by revenue", df_name="df"
    )
    assert "Show top 5 by revenue" in prompt
    assert "operations" in prompt
    assert '"op":"sort"' in prompt


@pytest.mark.parametrize("chat_available", [True, False])
def test_openai_requests_have_finite_timeout(monkeypatch, chat_available):
    from types import SimpleNamespace

    calls = []

    def chat_create(**kwargs):
        calls.append(("chat", kwargs))
        if not chat_available:
            raise AttributeError("Legacy completion-only SDK")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))]
        )

    def completion_create(**kwargs):
        calls.append(("completion", kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(text="pong")])

    fake = SimpleNamespace(
        ChatCompletion=SimpleNamespace(create=chat_create),
        Completion=SimpleNamespace(create=completion_create),
    )
    monkeypatch.setattr("ai.backends._lazy_openai", lambda: fake)
    assert OpenAIBackend().generate_text("ping") == "pong"
    assert [kind for kind, _ in calls] == (
        ["chat"] if chat_available else ["chat", "completion"]
    )
    assert all(kwargs["request_timeout"] == 30.0 for _, kwargs in calls)


@pytest.mark.parametrize(
    "explicit, environment, expected",
    [
        ("explicit", "environment", "explicit"),
        (None, "environment", "environment"),
        (None, None, "saved"),
    ],
)
def test_backend_key_precedence(monkeypatch, explicit, environment, expected):
    from types import SimpleNamespace
    import sys

    reads = []

    def get_password(service, username):
        reads.append((service, username))
        return "saved"

    fake = SimpleNamespace(api_key=None)
    monkeypatch.setattr("ai.backends._lazy_openai", lambda: fake)
    monkeypatch.setitem(
        sys.modules, "keyring", SimpleNamespace(get_password=get_password)
    )
    if environment is None:
        monkeypatch.delenv("PARQCEL_OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PARQCEL_OPENAI_API_KEY", environment)
    create_backend({"provider": "openai", "openai_api_key": explicit})
    assert fake.api_key == expected
    assert reads == ([] if explicit or environment else [("parqcel", "openai_api_key")])


def test_keyring_failure_is_optional(monkeypatch):
    from types import SimpleNamespace
    import sys

    def unavailable(*args):
        raise RuntimeError("no usable keyring")

    monkeypatch.delenv("PARQCEL_OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(
        sys.modules, "keyring", SimpleNamespace(get_password=unavailable)
    )
    monkeypatch.setattr(
        "ai.backends._lazy_openai", lambda: SimpleNamespace(api_key=None)
    )
    assert isinstance(create_backend({"provider": "openai"}), OpenAIBackend)
