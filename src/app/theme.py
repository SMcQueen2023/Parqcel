"""Shared compact desktop appearance with an OS-following light/dark mode."""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

from app.preferences import settings

_MODES = {"system", "light", "dark"}
_SETTING_KEY = "appearance/theme"
_CONTROLLER_ATTRIBUTE = "_parqcel_theme_controller"

_LIGHT = {
    "window": "#f3f6fa",
    "surface": "#ffffff",
    "alternate": "#f8fafc",
    "chrome": "#edf2f7",
    "text": "#203044",
    "muted": "#53677d",
    "disabled": "#6f7e8d",
    "border": "#c9d5e2",
    "grid": "#e1e8f0",
    "accent": "#087e8b",
    "accent_text": "#ffffff",
    "selected": "#dceff1",
    "selected_text": "#12434a",
    "hover": "#e3edf5",
    "link": "#245f9e",
    "shadow": "#768599",
}
_DARK = {
    "window": "#18212c",
    "surface": "#1c2633",
    "alternate": "#202c3a",
    "chrome": "#243140",
    "text": "#e5edf6",
    "muted": "#afbed0",
    "disabled": "#8c9bad",
    "border": "#44556a",
    "grid": "#334256",
    "accent": "#6dd5dd",
    "accent_text": "#123338",
    "selected": "#245563",
    "selected_text": "#ecfeff",
    "hover": "#304154",
    "link": "#98c8fb",
    "shadow": "#0d141d",
}


def _system_mode(app: QApplication) -> str:
    hints = app.styleHints()
    return (
        "dark"
        if hints is not None and hints.colorScheme() == Qt.ColorScheme.Dark
        else "light"
    )


def _palette(tokens: dict[str, str]) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.AlternateBase: "alternate",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "chrome",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.ToolTipBase: "surface",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Highlight: "selected",
        QPalette.ColorRole.HighlightedText: "selected_text",
        QPalette.ColorRole.Link: "link",
        QPalette.ColorRole.LinkVisited: "link",
        QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Accent: "accent",
        QPalette.ColorRole.Light: "surface",
        QPalette.ColorRole.Midlight: "chrome",
        QPalette.ColorRole.Mid: "border",
        QPalette.ColorRole.Dark: "border",
        QPalette.ColorRole.Shadow: "shadow",
        QPalette.ColorRole.BrightText: "accent_text",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(tokens[token]))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(tokens["disabled"]))
    return palette


def _stylesheet(t: dict[str, str]) -> str:
    return f"""
        QMainWindow, QDialog {{ background: {t['window']}; color: {t['text']}; }}
        QLabel {{ color: {t['text']}; }}
        QLabel#workspaceTitle {{ font-size: 18px; font-weight: 600; }}
        QLabel#workspaceSubtitle, QLabel#secondaryText {{ color: {t['muted']}; }}
        QLabel#modeBadge {{ color: {t['selected_text']}; background: {t['selected']};
            border-radius: 4px; padding: 4px 9px; font-weight: 600; }}
        QLabel#sectionTitle {{ color: {t['muted']}; font-weight: 600; }}
        QLabel#emptyState {{ color: {t['muted']}; padding: 26px; font-size: 14px; }}
        QToolBar {{ background: {t['chrome']}; border: 1px solid {t['border']};
            border-radius: 5px; padding: 4px; spacing: 3px; }}
        QToolBar::separator {{ background: {t['border']}; width: 1px; margin: 4px 7px; }}
        QToolButton, QPushButton {{ background: {t['surface']}; color: {t['text']};
            border: 1px solid {t['border']}; border-radius: 4px; padding: 5px 9px; }}
        QToolButton {{ background: transparent; border-color: transparent; }}
        QToolButton:hover, QPushButton:hover {{ background: {t['hover']}; }}
        QToolButton:pressed, QPushButton:pressed, QToolButton:checked, QPushButton:checked {{
            background: {t['selected']}; color: {t['selected_text']}; }}
        QToolButton:focus, QPushButton:focus {{ border: 1px solid {t['accent']}; }}
        QToolButton:disabled, QPushButton:disabled {{ color: {t['disabled']}; }}
        QPushButton#primaryButton {{ background: {t['accent']}; color: {t['accent_text']};
            border-color: {t['accent']}; }}
        QPushButton#primaryButton:disabled {{ background: {t['chrome']};
            color: {t['disabled']}; border-color: {t['border']}; }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
            background: {t['surface']}; color: {t['text']};
            border: 1px solid {t['border']}; border-radius: 4px; padding: 5px 7px;
            selection-background-color: {t['selected']};
            selection-color: {t['selected_text']}; }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {t['accent']}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
            background: {t['chrome']}; color: {t['disabled']}; }}
        QTableView, QTreeView, QListView {{ background: {t['surface']};
            alternate-background-color: {t['alternate']}; color: {t['text']};
            border: 1px solid {t['border']}; gridline-color: {t['grid']};
            selection-background-color: {t['selected']};
            selection-color: {t['selected_text']}; }}
        QTableView::item {{ padding: 3px 6px; }}
        QTableView::item:focus {{ border: 1px solid {t['accent']}; }}
        QHeaderView::section {{ background: {t['chrome']}; color: {t['text']};
            border: none; border-right: 1px solid {t['grid']};
            border-bottom: 1px solid {t['border']}; padding: 6px 8px; font-weight: 600; }}
        QTableCornerButton::section {{ background: {t['chrome']}; border: 1px solid {t['border']}; }}
        QMenuBar, QMenu {{ background: {t['surface']}; color: {t['text']}; }}
        QMenu {{ border: 1px solid {t['border']}; padding: 4px; }}
        QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
        QMenu::item {{ padding: 6px 22px; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {t['selected']}; color: {t['selected_text']}; }}
        QMenu::item:disabled {{ color: {t['disabled']}; }}
        QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
        QStatusBar {{ background: {t['chrome']}; color: {t['muted']}; }}
        QStatusBar::item {{ border: none; }}
        QGroupBox {{ border: 1px solid {t['border']}; border-radius: 5px;
            margin-top: 10px; padding: 12px 8px 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {t['muted']}; }}
        QSplitter::handle {{ background: {t['border']}; }}
        QToolTip {{ background: {t['surface']}; color: {t['text']};
            border: 1px solid {t['border']}; padding: 5px; }}
    """


class _ThemeController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.mode = "system"
        app.setStyle("Fusion")
        font = QFont(app.font())
        font.setPointSizeF(min(10.0, max(9.0, font.pointSizeF())))
        app.setFont(font)
        hints = app.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._system_changed)

    def refresh(self) -> None:
        resolved = _system_mode(self.app) if self.mode == "system" else self.mode
        tokens = _DARK if resolved == "dark" else _LIGHT
        self.app.setPalette(_palette(tokens))
        self.app.setStyleSheet(_stylesheet(tokens))
        self.app.setProperty("parqcelResolvedTheme", resolved)

    def _system_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self.mode == "system":
            self.refresh()


def _controller(app: QApplication) -> _ThemeController:
    controller = getattr(app, _CONTROLLER_ATTRIBUTE, None)
    if controller is None:
        controller = _ThemeController(app)
        setattr(app, _CONTROLLER_ATTRIBUTE, controller)
    return controller


def apply_theme(app: QApplication, mode: str = "system") -> None:
    """Apply and persist the selected appearance for all application windows."""
    if mode not in _MODES:
        raise ValueError("Theme must be system, light, or dark")
    controller = _controller(app)
    controller.mode = mode
    controller.refresh()
    settings().setValue(_SETTING_KEY, mode)


def setup_theme(app: QApplication) -> None:
    """Restore the saved appearance, defaulting invalid settings to system."""
    saved = settings().value(_SETTING_KEY, "system")
    mode = saved if isinstance(saved, str) and saved in _MODES else "system"
    controller = _controller(app)
    controller.mode = mode
    controller.refresh()


def theme_mode() -> str:
    """Return the selected mode, which may differ from the resolved OS color."""
    app = QApplication.instance()
    if isinstance(app, QApplication):
        controller = getattr(app, _CONTROLLER_ATTRIBUTE, None)
        if controller is not None:
            return controller.mode
    saved = settings().value(_SETTING_KEY, "system")
    return saved if isinstance(saved, str) and saved in _MODES else "system"
