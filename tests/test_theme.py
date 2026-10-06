import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette

from app import theme
from app.preferences import settings


@pytest.fixture
def appearance(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PARQCEL_SETTINGS_FILE", str(tmp_path / "theme.ini"))
    original_palette = QPalette(qapp.palette())
    original_font = QFont(qapp.font())
    original_stylesheet = qapp.styleSheet()
    original_style = qapp.style().objectName()
    original_mode = theme.theme_mode()
    original_resolved = qapp.property("parqcelResolvedTheme")
    yield qapp
    controller = getattr(qapp, "_parqcel_theme_controller", None)
    if controller is not None:
        controller.mode = original_mode
    qapp.setStyle(original_style)
    qapp.setPalette(original_palette)
    qapp.setFont(original_font)
    qapp.setStyleSheet(original_stylesheet)
    qapp.setProperty("parqcelResolvedTheme", original_resolved)


def _contrast(first, second):
    def luminance(color):
        channels = [color.redF(), color.greenF(), color.blueF()]
        values = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return sum(
            weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), values)
        )

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_palette_keeps_grid_controls_and_selection_readable(appearance, mode):
    theme.apply_theme(appearance, mode)
    palette = appearance.palette()
    for foreground, background in (
        (QPalette.ColorRole.Text, QPalette.ColorRole.Base),
        (QPalette.ColorRole.WindowText, QPalette.ColorRole.Window),
        (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Button),
        (QPalette.ColorRole.HighlightedText, QPalette.ColorRole.Highlight),
        (QPalette.ColorRole.ToolTipText, QPalette.ColorRole.ToolTipBase),
        (QPalette.ColorRole.PlaceholderText, QPalette.ColorRole.Base),
    ):
        assert _contrast(palette.color(foreground), palette.color(background)) >= 4.5
    assert 9 <= appearance.font().pointSizeF() <= 10
    assert "QTableView::item:focus" in appearance.styleSheet()
    assert "QPushButton:focus" in appearance.styleSheet()
    assert appearance.property("parqcelResolvedTheme") == mode


def test_mode_is_persisted_and_restored(appearance):
    theme.apply_theme(appearance, "dark")
    assert settings().value("appearance/theme") == "dark"
    assert theme.theme_mode() == "dark"
    theme.apply_theme(appearance, "light")
    settings().setValue("appearance/theme", "dark")
    theme.setup_theme(appearance)
    assert theme.theme_mode() == "dark"
    assert appearance.property("parqcelResolvedTheme") == "dark"


def test_system_theme_follows_os_changes_but_explicit_mode_does_not(
    appearance, monkeypatch
):
    current = {"mode": "light"}
    monkeypatch.setattr(theme, "_system_mode", lambda app: current["mode"])
    theme.apply_theme(appearance, "system")
    assert appearance.property("parqcelResolvedTheme") == "light"
    current["mode"] = "dark"
    appearance.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert theme.theme_mode() == "system"
    assert appearance.property("parqcelResolvedTheme") == "dark"
    assert settings().value("appearance/theme") == "system"
    theme.apply_theme(appearance, "light")
    appearance.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert appearance.property("parqcelResolvedTheme") == "light"


def test_invalid_mode_does_not_change_saved_preference(appearance):
    theme.apply_theme(appearance, "dark")
    with pytest.raises(ValueError):
        theme.apply_theme(appearance, "sepia")
    assert settings().value("appearance/theme") == "dark"
    settings().setValue("appearance/theme", "invalid")
    theme.setup_theme(appearance)
    assert theme.theme_mode() == "system"
