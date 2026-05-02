from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class BackgroundTaskWorker(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self._func = func

    def run(self) -> None:
        try:
            result = self._func()
        except Exception as exc:  # pragma: no cover - exercised via callbacks
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


def run_in_background(
    owner: QObject,
    func: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    on_finished: Callable[[], None] | None = None,
) -> QThread:
    thread = QThread(owner)
    worker = BackgroundTaskWorker(func)
    worker.moveToThread(thread)

    background_threads = getattr(owner, "_background_threads", None)
    if background_threads is None:
        background_threads = []
        setattr(owner, "_background_threads", background_threads)
    background_threads.append(thread)

    def _cleanup() -> None:
        if thread in background_threads:
            background_threads.remove(thread)
        if on_finished is not None:
            on_finished()

    thread.started.connect(worker.run)
    worker.succeeded.connect(on_success)
    worker.failed.connect(on_error)
    worker.succeeded.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.succeeded.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(_cleanup)
    thread.start()
    return thread