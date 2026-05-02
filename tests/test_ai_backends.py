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
        _parse_transformation_response('not json')


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
    assert result["code"] == "# Could not extract code from LLM response"


def test_hf_backend_invalid_transformation_response_falls_back(monkeypatch):
    def fake_pipeline(task, model):
        return lambda prompt, max_length, do_sample: [{"generated_text": "not json"}]

    monkeypatch.setattr("ai.backends._lazy_hf_pipeline", lambda: fake_pipeline)
    backend = HuggingFaceBackend(model="demo-model")

    result = backend.generate_transformation("show top 5", df_name="df")

    assert result["text"].startswith("Invalid transformation response")
    assert result["code"] == "# HuggingFace backend returned text; manual extraction required"
