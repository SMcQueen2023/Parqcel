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

from app.background_tasks import run_in_background


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

        self.suggestions_label = QLabel("Suggested code (click to select):")
        self.layout.addWidget(self.suggestions_label)
        self.suggestions = QListWidget()
        self.layout.addWidget(self.suggestions)

        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask for a transformation or insight...")
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
        self.suggestions.itemSelectionChanged.connect(self._on_select)

        # Internal last code
        self._last_code: Optional[str] = None

    def _append_chat(self, who: str, text: str) -> None:
        self.chat.append(f"<{who}> {text}")

    def _on_send(self) -> None:
        prompt = self.input.text().strip()
        if not prompt:
            return
        self._append_chat("User", prompt)
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)
        self.suggestions.clear()
        self._last_code = None
        self.apply_btn.setEnabled(False)

        def _success(resp) -> None:
            text = resp.get("text") if isinstance(resp, dict) else str(resp)
            code = resp.get("code") if isinstance(resp, dict) else ""

            if text:
                self._append_chat("Assistant", text)
            if code:
                self.suggestions.addItem(code)
                self.suggestions.setCurrentRow(0)
                self._last_code = code
                self.apply_btn.setEnabled(True)

        def _error(exc: Exception) -> None:
            self._append_chat("Assistant", f"(assistant error) {exc}")
            self.suggestions.clear()
            self._last_code = None
            self.apply_btn.setEnabled(False)

        def _finished() -> None:
            self.send_btn.setEnabled(True)
            self.input.setEnabled(True)

        run_in_background(
            self,
            lambda: self.assistant.suggest_transformation(prompt),
            _success,
            _error,
            _finished,
        )
        self.input.clear()

    def _on_apply(self) -> None:
        if not self._last_code:
            return
        # Emit code for the main window to handle (confirmation & execution)
        self.apply_code.emit(self._last_code)

    def _on_select(self) -> None:
        items = self.suggestions.selectedItems()
        if not items:
            self._last_code = None
            self.apply_btn.setEnabled(False)
            return
        self._last_code = items[0].text()
        self.apply_btn.setEnabled(True)
