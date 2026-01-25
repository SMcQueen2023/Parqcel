from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QListWidget,
)
from PyQt6.QtCore import pyqtSignal
from typing import Optional


class AIAssistantWidget(QWidget):
    """A dockable assistant widget providing chat and suggested transformations.

    Emits `apply_code` when the user requests applying a suggested transformation.
    """

    apply_code = pyqtSignal(str)

    def __init__(self, assistant=None, parent=None):
        super().__init__(parent)
        from ai.assistant import assistant_from_config

        self.assistant = assistant or assistant_from_config()

        self.layout = QVBoxLayout(self)

        header = QLabel("AI Assistant")
        self.layout.addWidget(header)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.layout.addWidget(self.chat)

        self.suggestions_label = QLabel("Suggested actions:")
        self.layout.addWidget(self.suggestions_label)
        self.suggestions = QListWidget()
        self.layout.addWidget(self.suggestions)

        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.send_btn = QPushButton("Ask")
        self.apply_btn = QPushButton("Apply Suggestion")
        self.apply_btn.setEnabled(False)
        bottom.addWidget(self.input)
        bottom.addWidget(self.send_btn)
        bottom.addWidget(self.apply_btn)
        self.layout.addLayout(bottom)

        # Signals
        self.send_btn.clicked.connect(self._on_send)
        self.apply_btn.clicked.connect(self._on_apply)

        # Internal last code
        self._last_code: Optional[str] = None

    def _append_chat(self, who: str, text: str) -> None:
        self.chat.append(f"<{who}> {text}")

    def _on_send(self) -> None:
        prompt = self.input.text().strip()
        if not prompt:
            return
        self._append_chat("User", prompt)
        # Ask assistant for suggestion
        try:
            resp = self.assistant.suggest_transformation(prompt)
            text = resp.get("text") if isinstance(resp, dict) else str(resp)
            code = resp.get("code") if isinstance(resp, dict) else ""
        except Exception as e:
            text = f"(assistant error) {e}"
            code = ""
            # clear any previous suggestions to avoid stale apply
            self.suggestions.clear()
            self._last_code = None
            self.apply_btn.setEnabled(False)

        if text:
            self._append_chat("Assistant", text)
        if code:
            # show code as a suggestion and enable apply
            self.suggestions.clear()
            self.suggestions.addItem(code)
            self._last_code = code
            self.apply_btn.setEnabled(True)
        else:
            # no code returned -> ensure apply is disabled
            self.apply_btn.setEnabled(False)
            if not text:
                # ensure no stale code is kept
                self._last_code = None

        self.input.clear()

    def _on_apply(self) -> None:
        if not self._last_code:
            return
        # Emit code for the main window to handle (confirmation & execution)
        self.apply_code.emit(self._last_code)
