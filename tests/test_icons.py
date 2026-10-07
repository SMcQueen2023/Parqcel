import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon, QPalette

from app.icons import line_icon


@pytest.mark.parametrize(
    "name",
    "open preview save undo redo copy add paste find columns inspector first previous next last".split(),
)
def test_workspace_icons_render_at_toolbar_and_hidpi_sizes(qapp, name):
    icon = line_icon(name)
    for scale in (1.0, 2.0):
        pixmap = icon.pixmap(QSize(20, 20), scale)
        assert not pixmap.isNull()
        assert pixmap.width() == int(20 * scale)
        assert pixmap.devicePixelRatio() == scale
        image = pixmap.toImage()
        assert any(
            image.pixelColor(x, y).alpha() > 0
            for x in range(image.width())
            for y in range(image.height())
        )


def test_existing_icon_tracks_palette_and_disabled_colors(qapp):
    original = qapp.palette()
    icon = line_icon("columns")
    try:
        for foreground in ("#203044", "#e5edf6"):
            palette = QPalette(original)
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(foreground))
            palette.setColor(
                QPalette.ColorGroup.Disabled,
                QPalette.ColorRole.ButtonText,
                QColor("#8c9bad"),
            )
            qapp.setPalette(palette)
            for mode, expected in (
                (QIcon.Mode.Normal, foreground),
                (QIcon.Mode.Disabled, "#8c9bad"),
            ):
                image = icon.pixmap(QSize(40, 40), mode).toImage()
                opaque = [
                    image.pixelColor(x, y).name()
                    for x in range(image.width())
                    for y in range(image.height())
                    if image.pixelColor(x, y).alpha() == 255
                ]
                assert opaque and set(opaque) == {expected}
    finally:
        qapp.setPalette(original)


def test_unknown_icon_is_rejected(qapp):
    with pytest.raises(ValueError, match="Unknown line icon"):
        line_icon("missing")
