"""Small palette-aware line icons for workspace actions.

Geometry uses a 20-unit canvas. The engine paints from the current palette each
time, so existing actions follow theme changes without rebuilding their icons.
"""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication

_NAMES = frozenset(
    "open preview save undo redo copy find columns inspector first previous next last".split()
)


def _geometry(name: str) -> QPainterPath:
    path = QPainterPath()

    def line(*points: tuple[float, float]) -> None:
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)

    if name == "open":
        line((3, 15.5), (3, 4.5), (8, 4.5), (10, 6.5), (17, 6.5), (17, 9))
        line((3, 15.5), (5.5, 9), (18, 9), (15.5, 15.5), (3, 15.5))
    elif name == "preview":
        path.moveTo(2, 10)
        path.cubicTo(6, 3, 14, 3, 18, 10)
        path.cubicTo(14, 17, 6, 17, 2, 10)
        path.addEllipse(QRectF(7.5, 7.5, 5, 5))
    elif name == "save":
        line((4, 3), (14, 3), (17, 6), (17, 17), (3, 17), (3, 3), (4, 3))
        line((6, 3), (6, 8), (13, 8), (13, 3))
        path.addRect(QRectF(6, 12, 8, 5))
    elif name in {"undo", "redo"}:
        # Mirror the same curve for a visually balanced pair.
        direction = 1 if name == "undo" else -1

        def x(value: float) -> float:
            return 10 + direction * (value - 10)

        line((x(7), 4), (x(3), 8), (x(7), 12))
        path.moveTo(x(3), 8)
        path.lineTo(x(12), 8)
        path.cubicTo(x(18), 8, x(18), 16, x(12), 16)
    elif name == "copy":
        line((6, 13), (3, 13), (3, 3), (13, 3), (13, 6))
        path.addRoundedRect(QRectF(7, 7, 10, 10), 1, 1)
    elif name == "find":
        path.addEllipse(QRectF(3, 3, 10, 10))
        line((12, 12), (17, 17))
    elif name == "columns":
        path.addRoundedRect(QRectF(3, 3, 14, 14), 1, 1)
        line((3, 7), (17, 7))
        line((8, 3), (8, 17))
        line((12, 3), (12, 17))
    elif name == "inspector":
        path.addRoundedRect(QRectF(3, 3, 14, 14), 1, 1)
        line((11, 3), (11, 17))
        line((13.5, 7), (15, 7))
        line((13.5, 10), (15, 10))
        line((13.5, 13), (15, 13))
    elif name in {"first", "previous"}:
        line((12, 5), (7, 10), (12, 15))
        if name == "first":
            line((4, 5), (4, 15))
    elif name in {"next", "last"}:
        line((8, 5), (13, 10), (8, 15))
        if name == "last":
            line((16, 5), (16, 15))
    return path


class _LineIconEngine(QIconEngine):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.path = _geometry(name)

    def clone(self) -> QIconEngine:
        return _LineIconEngine(self.name)

    def key(self) -> str:
        return f"parqcel-line-{self.name}"

    def paint(
        self,
        painter: QPainter | None,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        if painter is None or rect.isEmpty():
            return
        palette = QApplication.palette()
        group = (
            QPalette.ColorGroup.Disabled
            if mode == QIcon.Mode.Disabled
            else QPalette.ColorGroup.Active
        )
        role = (
            QPalette.ColorRole.HighlightedText
            if mode == QIcon.Mode.Selected
            else QPalette.ColorRole.ButtonText
        )
        side = min(rect.width(), rect.height())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(
            rect.x() + (rect.width() - side) / 2,
            rect.y() + (rect.height() - side) / 2,
        )
        painter.scale(side / 20, side / 20)
        pen = QPen(palette.color(group, role), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path)
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pixmap


def line_icon(name: str) -> QIcon:
    """Return a scalable workspace icon, rejecting unknown action names."""
    if name not in _NAMES:
        raise ValueError(f"Unknown line icon: {name}")
    return QIcon(_LineIconEngine(name))
