import os
import sys
import pytest

# Ensure Qt can run headless during CI and local test runs where no display is available.
# Must set before importing PyQt modules.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def isolate_workspace_preferences(monkeypatch, tmp_path):
    monkeypatch.setenv("PARQCEL_SETTINGS_FILE", str(tmp_path / "preferences.ini"))


@pytest.fixture(autouse=True)
def reject_unexpected_message_boxes(monkeypatch):
    # An unexpected error in a worker callback must fail CI, not wait forever
    # inside a headless modal dialog. Dialog-specific tests override these spies.
    messages = []

    def record(parent, title, text, *args, **kwargs):
        messages.append(f"{title}: {text}")
        return QMessageBox.StandardButton.Ok

    for method in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, method, record)
    yield
    assert not messages, "Unexpected message boxes: " + "; ".join(messages)


@pytest.fixture(autouse=True)
def dismiss_unsaved_changes(monkeypatch):
    # Headless test cleanup must never wait for a modal close confirmation.
    # Tests of save/cancel behavior override this default explicitly.
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
