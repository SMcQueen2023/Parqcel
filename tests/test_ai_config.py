import json

import pytest

from ai.config import load_config


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    for name in (
        "PARQCEL_CONFIG_FILE",
        "PARQCEL_AI_PROVIDER",
        "PARQCEL_OPENAI_API_KEY",
        "PARQCEL_OPENAI_API_BASE",
        "PARQCEL_HF_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("ai.config.os.path.expanduser", lambda _: str(tmp_path))
    directory = tmp_path / ".parqcel"
    directory.mkdir()
    return directory / "config.json"


def test_loads_settings_saved_in_default_location(config_home):
    config_home.write_text(
        json.dumps({"provider": "hf", "hf_model": "saved-model"}), encoding="utf-8"
    )
    assert load_config() == {"provider": "hf", "hf_model": "saved-model"}


def test_settings_dialog_save_is_loaded_on_restart(config_home, qtbot, monkeypatch):
    from app.widgets.ai_settings import AISettingsDialog

    monkeypatch.setattr("app.widgets.ai_settings.keyring", None)
    monkeypatch.setattr(
        "app.widgets.ai_settings.QMessageBox.information", lambda *args: None
    )
    dialog = AISettingsDialog()
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("hf")
    dialog.hf_input.setText("saved-by-dialog")
    dialog._on_save()

    assert config_home.is_file()
    assert load_config()["hf_model"] == "saved-by-dialog"
    assert load_config()["provider"] == "hf"


def test_explicit_config_file_replaces_default_file(config_home, monkeypatch):
    config_home.write_text(
        json.dumps({"provider": "hf", "hf_model": "should-not-leak"}), encoding="utf-8"
    )
    selected = config_home.parent / "selected.json"
    selected.write_text(json.dumps({"provider": "openai"}), encoding="utf-8")
    monkeypatch.setenv("PARQCEL_CONFIG_FILE", str(selected))
    assert load_config() == {"provider": "openai"}


def test_nonempty_environment_values_override_selected_file(config_home, monkeypatch):
    config_home.write_text(
        json.dumps(
            {"provider": "hf", "hf_model": "saved", "openai_api_base": "saved-base"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PARQCEL_AI_PROVIDER", "openai")
    monkeypatch.setenv("PARQCEL_HF_MODEL", "")
    monkeypatch.setenv("PARQCEL_OPENAI_API_BASE", "environment-base")
    monkeypatch.setenv("PARQCEL_OPENAI_API_KEY", "test-key")
    assert load_config() == {
        "provider": "openai",
        "hf_model": "saved",
        "openai_api_base": "environment-base",
        "openai_api_key": "test-key",
    }


@pytest.mark.parametrize("contents", [None, "invalid-json", "[]", "null", '"text"'])
def test_missing_or_invalid_config_uses_default_provider(config_home, contents):
    if contents is not None:
        config_home.write_text(contents, encoding="utf-8")
    assert load_config() == {"provider": "dummy"}


def test_missing_explicit_file_does_not_fall_back_to_default(config_home, monkeypatch):
    config_home.write_text('{"provider":"hf"}', encoding="utf-8")
    monkeypatch.setenv("PARQCEL_CONFIG_FILE", str(config_home.parent / "missing.json"))
    assert load_config() == {"provider": "dummy"}
