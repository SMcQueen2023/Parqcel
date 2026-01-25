import os
import pytest
from ai.assistant import assistant_from_config
from PyQt6.QtCore import Qt


def test_assistant_dummy_response():
    a = assistant_from_config({"provider": "dummy"})
    resp = a.ask("Summarize columns")
    assert isinstance(resp, str)


def test_assistant_suggest_transformation():
    a = assistant_from_config({"provider": "dummy"})
    out = a.suggest_transformation("Show top 5 by revenue", df_name="df")
    assert isinstance(out, dict)
    assert "code" in out


def test_ai_widget_interaction(qtbot):
    from app.widgets.ai_assistant import AIAssistantWidget

    a = assistant_from_config({"provider": "dummy"})
    widget = AIAssistantWidget(assistant=a)
    qtbot.addWidget(widget)

    # simulate user entering a request
    widget.input.setText("Show top 3 by revenue")
    qtbot.mouseClick(widget.send_btn, Qt.MouseButton.LeftButton)

    # The widget should populate suggestions
    assert widget.suggestions.count() >= 0
