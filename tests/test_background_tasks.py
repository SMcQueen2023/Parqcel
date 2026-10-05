import gc
import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QWidget

from app.background_tasks import cancel_tasks, has_active_tasks, run_in_background


@pytest.fixture
def controlled_work(qtbot):
    """Hold real background work until the test has changed the UI lifecycle."""
    started = threading.Event()
    release = threading.Event()
    worker_threads = []

    def work():
        worker_threads.append(QThread.currentThread())
        started.set()
        if not release.wait(5):
            raise RuntimeError("Test did not release background work")
        return "result"

    yield work, started, release, worker_threads
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(), timeout=5000)


def test_success_and_finished_callbacks_run_in_gui_thread(qtbot, qapp, controlled_work):
    owner = QWidget()
    qtbot.addWidget(owner)
    work, started, release, worker_threads = controlled_work
    calls = []
    task = run_in_background(
        owner,
        work,
        lambda value: calls.append((value, QThread.currentThread())),
        lambda error: calls.append((error, QThread.currentThread())),
        lambda: calls.append(("finished", QThread.currentThread())),
    )
    qtbot.waitUntil(started.is_set)
    assert task.is_running
    assert has_active_tasks(owner)
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert worker_threads[0] != qapp.thread()
    assert calls == [("result", qapp.thread()), ("finished", qapp.thread())]
    assert not has_active_tasks(owner)


def test_failure_is_delivered_in_gui_thread(qtbot, qapp, controlled_work):
    owner = QWidget()
    qtbot.addWidget(owner)
    work, started, release, _ = controlled_work
    calls = []

    def failing_work():
        work()
        raise ValueError("expected failure")

    task = run_in_background(
        owner,
        failing_work,
        lambda value: calls.append(("unexpected success", value)),
        lambda error: calls.append((str(error), QThread.currentThread())),
        lambda: calls.append(("finished", QThread.currentThread())),
    )
    qtbot.waitUntil(started.is_set)
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert calls == [("expected failure", qapp.thread()), ("finished", qapp.thread())]


def test_cancellation_discards_delivery_without_terminating_work(
    qtbot, controlled_work
):
    owner = QWidget()
    qtbot.addWidget(owner)
    work, started, release, _ = controlled_work
    calls = []
    infrastructure_finished = []
    task = run_in_background(
        owner, work, calls.append, calls.append, lambda: calls.append("finished")
    )
    task.finished.connect(lambda: infrastructure_finished.append(True))
    qtbot.waitUntil(started.is_set)
    task.cancel()
    assert task.cancelled
    assert task.is_running
    assert has_active_tasks(owner)
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert calls == []
    assert infrastructure_finished == [True]


def test_deleted_child_keeps_task_alive_and_parent_scope_visible(
    qtbot, controlled_work
):
    parent = QWidget()
    qtbot.addWidget(parent)
    child = QWidget(parent)
    other = QWidget()
    qtbot.addWidget(other)
    work, started, release, _ = controlled_work
    calls = []
    task = run_in_background(
        child, work, calls.append, calls.append, lambda: calls.append("finished")
    )
    qtbot.waitUntil(started.is_set)
    assert has_active_tasks(parent)
    assert not has_active_tasks(parent, include_descendants=False)
    assert not has_active_tasks(other)
    child.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(child))
    assert task.cancelled
    assert task.is_running
    assert has_active_tasks(parent)
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(parent))
    assert calls == []


def test_parent_cancellation_includes_descendants(qtbot, controlled_work):
    parent = QWidget()
    qtbot.addWidget(parent)
    child = QWidget(parent)
    work, started, release, _ = controlled_work
    calls = []
    task = run_in_background(child, work, calls.append, calls.append)
    qtbot.waitUntil(started.is_set)
    cancel_tasks(parent, include_descendants=False)
    assert not task.cancelled
    cancel_tasks(parent)
    assert task.cancelled
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert calls == []


def test_registry_owns_task_when_caller_does_not_keep_handle(qtbot, controlled_work):
    owner = QWidget()
    qtbot.addWidget(owner)
    work, started, release, _ = controlled_work
    calls = []
    run_in_background(owner, work, calls.append, calls.append)
    qtbot.waitUntil(started.is_set)
    gc.collect()
    assert has_active_tasks(owner)
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(owner))
    assert calls == ["result"]


def test_callback_exception_does_not_prevent_cleanup(qtbot, controlled_work, caplog):
    owner = QWidget()
    qtbot.addWidget(owner)
    work, started, release, _ = controlled_work
    finished = []

    def bad_callback(_value):
        raise RuntimeError("UI callback failed")

    task = run_in_background(
        owner, work, bad_callback, bad_callback, lambda: finished.append(True)
    )
    qtbot.waitUntil(started.is_set)
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert finished == [True]
    assert "Background task callback failed" in caplog.text


def test_settings_dialog_close_cancels_pending_connection_test(
    qtbot, monkeypatch, controlled_work
):
    from app.widgets.ai_settings import AISettingsDialog

    work, started, release, _ = controlled_work
    messages = []

    class Backend:
        def test_connection(self):
            work()
            return True

    monkeypatch.setattr("app.widgets.ai_settings.keyring", None)
    monkeypatch.setattr("app.widgets.ai_settings.load_config", lambda: {})
    monkeypatch.setattr("ai.backends.create_backend", lambda config: Backend())
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            f"app.widgets.ai_settings.QMessageBox.{name}",
            lambda *args: messages.append(args),
        )
    dialog = AISettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._on_test()
    qtbot.waitUntil(started.is_set)
    dialog.close()
    assert has_active_tasks(dialog)
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(dialog))
    assert messages == []


def test_assistant_close_discards_pending_response(qtbot, controlled_work):
    from app.widgets.ai_assistant import AIAssistantWidget

    work, started, release, _ = controlled_work

    class Assistant:
        def suggest_transformation(self, prompt):
            work()
            return {"text": "late response", "code": "df.head()"}

    widget = AIAssistantWidget(assistant=Assistant())
    qtbot.addWidget(widget)
    widget.show()
    widget.input.setText("show rows")
    widget._on_send()
    qtbot.waitUntil(started.is_set)
    widget.close()
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(widget))
    assert widget.suggestions.count() == 0
    assert "late response" not in widget.chat.toPlainText()
