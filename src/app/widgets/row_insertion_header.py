"""A single hover control for explicit boundaries in a table's row header."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QMouseEvent, QPainter, QPaintEvent, QPen, QResizeEvent
from PyQt6.QtWidgets import (
    QHeaderView,
    QStyle,
    QStyleOptionToolButton,
    QStylePainter,
    QToolButton,
    QWidget,
)


class RowInsertButton(QToolButton):
    """Paint the plus geometrically so font baselines cannot move it off-center."""

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text = ""
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().buttonText().color(), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        center = QRectF(self.rect()).center()
        radius = 4.0
        painter.drawLine(
            QPointF(center.x() - radius, center.y()),
            QPointF(center.x() + radius, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - radius),
            QPointF(center.x(), center.y() + radius),
        )


class RowInsertionHeader(QHeaderView):
    """Keep native row selection; show one boxed plus near a row boundary."""

    insertion_requested = pyqtSignal(int)
    boundary_changed = pyqtSignal(object)
    _BUTTON_SIZE = 20
    _HOVER_DISTANCE = 7

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        overlay_parent: QWidget | None = None,
    ) -> None:
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setSectionsClickable(True)
        self.setSectionsMovable(False)
        self.setHighlightSections(True)
        self.setMinimumWidth(36)
        self.setMouseTracking(True)
        viewport = self.viewport()
        assert viewport is not None
        viewport.setMouseTracking(True)
        self._insertion_enabled = False
        self._boundary: int | None = None
        self._row_offset = 0
        # A host outside the table lets endpoint controls straddle either edge
        # without the table clipping the top or bottom half of the plus sign.
        host = overlay_parent if overlay_parent is not None else parent
        self.insert_button = RowInsertButton(host if host is not None else self)
        self.insert_button.setObjectName("rowInsertButton")
        self.insert_button.setText("+")
        self.insert_button.setAutoRaise(False)
        self.insert_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.insert_button.setFixedSize(self._BUTTON_SIZE, self._BUTTON_SIZE)
        self.insert_button.clicked.connect(self._request_insertion)
        self.insert_button.installEventFilter(self)
        self.insert_button.hide()
        self.sectionResized.connect(self.refresh_boundary)
        self.sectionMoved.connect(self.hide_boundary)
        self.geometriesChanged.connect(self.refresh_boundary)

    def set_insertion_enabled(self, enabled: bool, row_offset: int = 0) -> None:
        self._insertion_enabled = enabled
        self._row_offset = row_offset
        if not enabled:
            self.hide_boundary()
        else:
            self.refresh_boundary()

    @property
    def boundary(self) -> int | None:
        """Current zero-based boundary within the displayed page."""
        return self._boundary

    def hide_boundary(self, *args) -> None:
        self._boundary = None
        self.insert_button.hide()
        self.boundary_changed.emit(None)

    def _boundary_y(self, boundary: int) -> int:
        if boundary == self.count():
            last = self.count() - 1
            return self.sectionViewportPosition(last) + self.sectionSize(last)
        return self.sectionViewportPosition(boundary)

    def show_boundary(self, boundary: int) -> bool:
        """Show a visible page boundary; also useful for keyboard/UI inspection."""
        if (
            not self._insertion_enabled
            or self.count() == 0
            or not 0 <= boundary <= self.count()
        ):
            self.hide_boundary()
            return False
        self._boundary = boundary
        self.refresh_boundary()
        return not self.insert_button.isHidden()

    def refresh_boundary(self, *args) -> None:
        boundary = self._boundary
        viewport = self.viewport()
        if (
            not self._insertion_enabled
            or boundary is None
            or viewport is None
            or self.count() == 0
            or boundary > self.count()
        ):
            self.hide_boundary()
            return
        y = self._boundary_y(boundary)
        if not 0 <= y <= viewport.height() or viewport.width() < self._BUTTON_SIZE:
            self.hide_boundary()
            return
        size = self._BUTTON_SIZE
        host = self.insert_button.parentWidget()
        assert host is not None
        self.insert_button.move(
            viewport.mapTo(
                host, QPoint(max(0, (viewport.width() - size) // 2), y - size // 2)
            )
        )
        if boundary < self.count():
            label = f"Insert above row {self._row_offset + boundary + 1:,}"
        else:
            label = f"Insert below row {self._row_offset + boundary:,}"
        self.insert_button.setToolTip(label)
        self.insert_button.setAccessibleName(label)
        self.insert_button.show()
        self.insert_button.raise_()
        self.boundary_changed.emit(y)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and self._insertion_enabled:
            y = int(event.position().y())
            row = self.logicalIndexAt(y)
            candidate = None
            if row >= 0:
                top = self.sectionViewportPosition(row)
                bottom = top + self.sectionSize(row)
                if y - top <= self._HOVER_DISTANCE:
                    candidate = row
                elif bottom - y <= self._HOVER_DISTANCE:
                    candidate = row + 1
            elif self.count():
                last_y = self._boundary_y(self.count())
                if abs(y - last_y) <= self._HOVER_DISTANCE:
                    candidate = self.count()
            if candidate is None:
                self.hide_boundary()
            else:
                self.show_boundary(candidate)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent | None) -> None:
        # Entering the child button must not hide it before it receives the click.
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())) and not (
            self.insert_button.rect().contains(
                self.insert_button.mapFromGlobal(QCursor.pos())
            )
        ):
            self.hide_boundary()
        super().leaveEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.insert_button and event.type() == QEvent.Type.Leave:
            if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
                self.hide_boundary()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if hasattr(self, "insert_button"):
            self.refresh_boundary()

    def insertion_menu_position(self) -> QPoint:
        return self.insert_button.mapToGlobal(self.insert_button.rect().bottomLeft())

    def _request_insertion(self) -> None:
        if self._insertion_enabled and self._boundary is not None:
            self.insertion_requested.emit(self._boundary)
