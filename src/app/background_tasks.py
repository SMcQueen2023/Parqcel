"""Run work off the GUI thread without tying thread lifetime to a widget.

Submit and cancel tasks from the GUI thread. Cancellation discards callbacks;
it does not forcibly interrupt Python, Polars, or an in-flight network request.
Windows should defer their final close while ``has_active_tasks(window)`` is true.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QThread, Qt, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

# Parentless tasks outlive their initiating widget until the worker has stopped.
_active_tasks: set[TaskHandle] = set()


class BackgroundTaskWorker(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)
    completed = pyqtSignal()

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self._func = func

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._func()
        except Exception as exc:
            self.failed.emit(exc)
        else:
            self.succeeded.emit(result)
        finally:
            self.completed.emit()


class TaskHandle(QObject):
    """GUI-thread receiver and lifetime owner for one background operation."""

    finished = pyqtSignal()

    def __init__(
        self,
        owner: QObject,
        func: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None] | None,
    ) -> None:
        super().__init__()
        self._owner = weakref.ref(owner)
        self._scope: list[weakref.ReferenceType[QObject]] = []
        ancestor: QObject | None = owner
        while ancestor is not None:
            self._scope.append(weakref.ref(ancestor))
            ancestor = ancestor.parent()
        self._on_success: Callable[[Any], None] | None = on_success
        self._on_error: Callable[[Exception], None] | None = on_error
        self._on_finished: Callable[[], None] | None = on_finished
        self._cancelled = False
        self._running = True

        self._thread: QThread | None = QThread()
        self._worker: BackgroundTaskWorker | None = BackgroundTaskWorker(func)
        self._worker.moveToThread(self._thread)
        owner.destroyed.connect(self.cancel)
        self._thread.started.connect(self._worker.run)
        # PyQt6 6.9's stubs omit the supported connection-type argument.
        self._worker.succeeded.connect(  # type: ignore[call-arg]
            self._succeeded, type=Qt.ConnectionType.QueuedConnection
        )
        self._worker.failed.connect(  # type: ignore[call-arg]
            self._failed, type=Qt.ConnectionType.QueuedConnection
        )
        # quit() is thread-safe; do not depend on GUI delivery to stop the worker.
        self._worker.completed.connect(  # type: ignore[call-arg]
            self._thread.quit, type=Qt.ConnectionType.DirectConnection
        )
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(  # type: ignore[call-arg]
            self._finish, type=Qt.ConnectionType.QueuedConnection
        )

    @property
    def is_running(self) -> bool:
        """True until thread completion has been processed in the GUI thread."""
        return self._running

    def isRunning(self) -> bool:
        """Compatibility helper for callers that previously received a QThread."""
        return self.is_running

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @pyqtSlot()
    def cancel(self) -> None:
        """Discard user callbacks, allowing the worker to finish naturally."""
        self._cancelled = True
        self._on_success = None
        self._on_error = None
        self._on_finished = None

    def _can_deliver(self) -> bool:
        owner = self._owner()
        return not self._cancelled and owner is not None and not sip.isdeleted(owner)

    def _invoke(self, callback: Callable[..., None] | None, *args: Any) -> None:
        if callback is not None and self._can_deliver():
            try:
                callback(*args)
            except Exception:
                # A UI callback must not prevent thread cleanup or escape a Qt slot.
                logger.exception("Background task callback failed")

    @pyqtSlot(object)
    def _succeeded(self, result: Any) -> None:
        self._invoke(self._on_success, result)

    @pyqtSlot(object)
    def _failed(self, exc: Exception) -> None:
        self._invoke(self._on_error, exc)

    @pyqtSlot()
    def _finish(self) -> None:
        self._running = False
        _active_tasks.discard(self)
        self._invoke(self._on_finished)
        owner = self._owner()
        if owner is not None and not sip.isdeleted(owner):
            owner.destroyed.disconnect(self.cancel)
        self._on_success = None
        self._on_error = None
        self._on_finished = None
        self._worker = None
        assert self._thread is not None
        self._thread.deleteLater()
        self._thread = None
        self.finished.emit()

    def _belongs_to(self, owner: QObject, include_descendants: bool) -> bool:
        scope = self._scope if include_descendants else self._scope[:1]
        return any(ref() is owner for ref in scope)


def has_active_tasks(
    owner: QObject | None = None, include_descendants: bool = True
) -> bool:
    """Include descendant tasks even if the child was closed or deleted later."""
    return any(
        owner is None or task._belongs_to(owner, include_descendants)
        for task in _active_tasks
    )


def cancel_tasks(
    owner: QObject | None = None, include_descendants: bool = True
) -> None:
    """Suppress delivery for matching tasks without blocking the GUI thread."""
    for task in tuple(_active_tasks):
        if owner is None or task._belongs_to(owner, include_descendants):
            task.cancel()


def run_in_background(
    owner: QObject,
    func: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    on_finished: Callable[[], None] | None = None,
) -> TaskHandle:
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError("Background tasks must be submitted from the GUI thread")
    if sip.isdeleted(owner):
        raise RuntimeError("Cannot start a background task for a deleted owner")
    task = TaskHandle(owner, func, on_success, on_error, on_finished)
    _active_tasks.add(task)
    assert task._thread is not None
    task._thread.start()
    return task
