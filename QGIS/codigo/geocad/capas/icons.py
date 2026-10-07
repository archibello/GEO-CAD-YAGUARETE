# -*- coding: utf-8 -*-
"""Iconos SVG y muestras dibujadas (color, grosor y tipo de línea)."""

import os

from qgis.PyQt.QtCore import QPointF, QRectF
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from .compat import qt
from .linetypes import LINETYPES, has_dots

_DIR = os.path.join(os.path.dirname(__file__), 'icons')
_CACHE = {}


def icon(name):
    if name not in _CACHE:
        path = os.path.join(_DIR, name + '.svg')
        _CACHE[name] = QIcon(path) if os.path.exists(path) else QIcon()
    return _CACHE[name]


def pixmap(name, size=16):
    return icon(name).pixmap(size, size)


def _transparent(w, h):
    pm = QPixmap(w, h)
    pm.fill(QColor(0, 0, 0, 0))
    return pm


def color_swatch(color, w=14, h=14, border='#202020'):
    pm = _transparent(w, h)
    p = QPainter(pm)
    p.setPen(QPen(QColor(border), 1))
    p.setBrush(QColor(color))
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return pm


def lineweight_sample(width_mm, w=44, h=14, color='#e6e9ee'):
    pm = _transparent(w, h)
    p = QPainter(pm)
    px = max(1.0, width_mm * 3.2)
    p.fillRect(QRectF(1, (h - px) / 2.0, w - 2, px), QColor(color))
    p.end()
    return pm


def linetype_sample(name, w=120, h=12, color='#e6e9ee'):
    pm = _transparent(w, h)
    p = QPainter(pm)
    p.setRenderHint(qt_render_hint())
    pattern = LINETYPES.get(name, {}).get('pattern', [])
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(qt('PenCapStyle', 'RoundCap' if has_dots(pattern) else 'FlatCap'))
    p.setPen(pen)
    y = h / 2.0
    if not pattern:
        p.drawLine(QPointF(2, y), QPointF(w - 2, y))
    else:
        scale = 1.6  # px por mm en la vista previa
        x, i = 2.0, 0
        while x < w - 2:
            seg = pattern[i % len(pattern)] * scale
            if i % 2 == 0:
                x2 = min(x + max(seg, 0.01), w - 2)
                p.drawLine(QPointF(x, y), QPointF(x2, y))
            x += max(seg, 0.6)
            i += 1
    p.end()
    return pm


def qt_render_hint():
    from qgis.PyQt.QtGui import QPainter as _P
    hint = getattr(_P, 'RenderHint', None)
    if hint is not None and hasattr(hint, 'Antialiasing'):
        return hint.Antialiasing
    return _P.Antialiasing
