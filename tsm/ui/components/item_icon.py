"""Item icon framed in its quality colour.

The border palette is the one the item tooltip already uses, so an icon and its
tooltip always agree on the item's quality colour.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from tsm.ui.components._wowhead_html import _BORDER_COLORS

_FALLBACK_BORDER = "#9d9d9d"
_EMPTY_FILL = "#1a1a1a"


def quality_color(quality: int) -> str:
    """Border colour for a WoW item quality, matching the tooltip border."""
    return _BORDER_COLORS.get(quality, _FALLBACK_BORDER)


def item_icon_pixmap(icon_path: Path | None, quality: int, size: int = 32) -> QPixmap:
    """Square icon with a 1px quality-coloured frame.

    With no cached image the frame is drawn over an empty fill, which is also
    what an offline run shows.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(_EMPTY_FILL))

    painter = QPainter(pixmap)
    if icon_path is not None:
        source = QPixmap(str(icon_path))
        if not source.isNull():
            painter.drawPixmap(
                pixmap.rect(),
                source.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
    painter.setPen(QColor(quality_color(quality)))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
    painter.end()
    return pixmap
