from PyQt6.QtCore import Qt

from app.widgets.ai_settings import AISettingsDialog


def _run_sync(owner, func, on_success, on_error, on_finished=None):
    try:
        on_success(func())
    except Exception as exc:
        on_error(exc)
    finally:
        if on_finished is not None:
            on_finished()


def test_ai_settings_test_connection_openai_success(qtbot, monkeypatch):
    captured = {}
    messages = []

    class FakeBackend:
        def generate_text(self, prompt):
            return "pong"

    def fake_create_backend(cfg):
        captured["cfg"] = cfg
        return FakeBackend()

    monkeypatch.setattr("app.widgets.ai_settings.run_in_background", _run_sync)
    monkeypatch.setattr("app.widgets.ai_settings.load_config", lambda: {"provider": "dummy"})
    monkeypatch.setattr("ai.backends.create_backend", fake_create_backend)
    monkeypatch.setattr(
        "app.widgets.ai_settings.QMessageBox.information",
        lambda *args: messages.append(("info", args[1], args[2])),
    )
    monkeypatch.setattr(
        "app.widgets.ai_settings.QMessageBox.warning",
        lambda *args: messages.append(("warning", args[1], args[2])),
    )
    monkeypatch.setattr(
        "app.widgets.ai_settings.QMessageBox.critical",
        lambda *args: messages.append(("critical", args[1], args[2])),
    )

    dlg = AISettingsDialog()
    qtbot.addWidget(dlg)
    dlg.provider.setCurrentText("openai")
    dlg.key_input.setText("secret")
    dlg.base_input.setText("https://api.example.test")

    qtbot.mouseClick(dlg.test_btn, Qt.MouseButton.LeftButton)

    assert captured["cfg"]["provider"] == "openai"
    assert captured["cfg"]["openai_api_key"] == "secret"
    assert captured["cfg"]["openai_api_base"] == "https://api.example.test"
    assert messages[0][0] == "info"
    assert dlg.test_btn.isEnabled() is True


def test_ai_settings_test_connection_hf_failure(qtbot, monkeypatch):
    messages = []

    monkeypatch.setattr("app.widgets.ai_settings.run_in_background", _run_sync)
    monkeypatch.setattr("app.widgets.ai_settings.load_config", lambda: {"provider": "hf"})
    monkeypatch.setattr(
        "ai.backends.create_backend",
        lambda cfg: (_ for _ in ()).throw(RuntimeError("backend unavailable")),
    )
    monkeypatch.setattr(
        "app.widgets.ai_settings.QMessageBox.critical",
        lambda *args: messages.append(("critical", args[1], args[2])),
    )

    dlg = AISettingsDialog()
    qtbot.addWidget(dlg)
    dlg.provider.setCurrentText("hf")
    dlg.hf_input.setText("demo-model")

    qtbot.mouseClick(dlg.test_btn, Qt.MouseButton.LeftButton)

    assert messages == [
        ("critical", "Test Failed", "Error during test: backend unavailable")
    ]
    assert dlg.test_btn.isEnabled() is True