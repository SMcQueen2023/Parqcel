from ai.assistant import assistant_from_config
from PyQt6.QtCore import Qt


def _run_sync(owner, func, on_success, on_error, on_finished=None):
    try:
        on_success(func())
    except Exception as exc:
        on_error(exc)
    finally:
        if on_finished is not None:
            on_finished()


def test_assistant_dummy_response():
    a = assistant_from_config({"provider": "dummy"})
    resp = a.ask("Summarize columns")
    assert isinstance(resp, str)


def test_assistant_suggest_transformation():
    a = assistant_from_config({"provider": "dummy"})
    out = a.suggest_transformation("Show top 5 by revenue", df_name="df")
    assert isinstance(out, dict)
    assert "code" in out


def test_ai_widget_interaction(qtbot, monkeypatch):
    from app.widgets.ai_assistant import AIAssistantWidget

    monkeypatch.setattr("app.widgets.ai_assistant.run_in_background", _run_sync)

    a = assistant_from_config({"provider": "dummy"})
    widget = AIAssistantWidget(assistant=a)
    qtbot.addWidget(widget)

    # simulate user entering a request
    widget.input.setText("Show top 3 by revenue")
    qtbot.mouseClick(widget.send_btn, Qt.MouseButton.LeftButton)

    # The widget should populate suggestions
    assert widget.suggestions.count() > 0


def test_ai_widget_clears_stale_suggestion_after_error(qtbot, monkeypatch):
    from app.widgets.ai_assistant import AIAssistantWidget

    monkeypatch.setattr("app.widgets.ai_assistant.run_in_background", _run_sync)

    class FailingAssistant:
        def suggest_transformation(self, prompt):
            raise RuntimeError("backend unavailable")

    widget = AIAssistantWidget(assistant=FailingAssistant())
    qtbot.addWidget(widget)

    widget.suggestions.addItem("df.head()")
    widget._last_code = "df.head()"
    widget.apply_btn.setEnabled(True)

    widget.input.setText("Show top 3 by revenue")
    qtbot.mouseClick(widget.send_btn, Qt.MouseButton.LeftButton)

    assert widget.suggestions.count() == 0
    assert widget._last_code is None
    assert widget.apply_btn.isEnabled() is False
    assert widget.send_btn.isEnabled() is True
    assert widget.input.isEnabled() is True
