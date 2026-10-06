"""Application preferences with an optional isolated settings file."""

import os

from PyQt6.QtCore import QSettings


def settings() -> QSettings:
    path = os.environ.get("PARQCEL_SETTINGS_FILE")
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("Parqcel", "Parqcel")
