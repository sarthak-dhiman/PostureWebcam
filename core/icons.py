"""
icons.py — Centralised SVG icon loader.

Place SVG files in the ``icons/`` directory at the project root.
This module loads them by name and caches QIcon / QPixmap objects.
"""

import os
from functools import lru_cache

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QSize

_ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")


@lru_cache(maxsize=64)
def icon(name: str) -> QIcon:
    """Return a QIcon for *name* (without extension).

    Falls back to an empty QIcon if the file is missing so the app
    never crashes over a missing asset.
    """
    path = os.path.join(_ICONS_DIR, f"{name}.svg")
    if os.path.isfile(path):
        return QIcon(path)
    # Try PNG fallback
    path_png = os.path.join(_ICONS_DIR, f"{name}.png")
    if os.path.isfile(path_png):
        return QIcon(path_png)
    return QIcon()


@lru_cache(maxsize=64)
def pixmap(name: str, size: int = 20) -> QPixmap:
    """Return a QPixmap scaled to *size* x *size* for *name*."""
    ic = icon(name)
    if ic.isNull():
        return QPixmap()
    return ic.pixmap(QSize(size, size))
