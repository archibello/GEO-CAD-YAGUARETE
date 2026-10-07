# -*- coding: utf-8 -*-
"""Paleta AutoCAD Color Index (ACI 1-255) y utilidades de color."""

import colorsys

ACI_NAMES = {1: 'rojo', 2: 'amarillo', 3: 'verde', 4: 'cyan',
             5: 'azul', 6: 'magenta', 7: 'blanco'}

_STD = {
    1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255),
    5: (0, 0, 255), 6: (255, 0, 255), 7: (255, 255, 255),
    8: (128, 128, 128), 9: (192, 192, 192),
}
_GRAYS = {250: 51, 251: 80, 252: 105, 253: 130, 254: 190, 255: 255}
_LEVELS = [255, 204, 153, 127, 76]


def _build():
    table = dict(_STD)
    for i in range(10, 250):
        hue = ((i - 10) // 10) * 15 / 360.0
        sub = i % 10
        level = _LEVELS[sub // 2] / 255.0
        sat = 1.0 if sub % 2 == 0 else 0.5
        r, g, b = colorsys.hsv_to_rgb(hue, sat, level)
        table[i] = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
    for i, v in _GRAYS.items():
        table[i] = (v, v, v)
    return table


ACI_RGB = _build()


def aci_to_hex(index):
    r, g, b = ACI_RGB.get(int(index), (255, 255, 255))
    return '#%02x%02x%02x' % (r, g, b)


def color_display_name(color):
    """Texto de la columna Color, como en AutoCAD."""
    aci = color.get('aci')
    if aci:
        return ACI_NAMES.get(aci, str(aci))
    h = color.get('rgb', '#000000').lstrip('#')
    return '%d,%d,%d' % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def color_hex(color):
    aci = color.get('aci')
    if aci:
        return aci_to_hex(aci)
    return color.get('rgb', '#000000')


def parse_color_text(text):
    """Acepta '1'..'255', 'rojo', 'red', '255,0,0' o '#ff0000'. Devuelve dict o None."""
    t = (text or '').strip().lower()
    if not t:
        return None
    eng = {'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5,
           'magenta': 6, 'white': 7, 'cian': 4, 'negro': 7, 'black': 7}
    for k, v in ACI_NAMES.items():
        if t == v:
            return {'aci': k}
    if t in eng:
        return {'aci': eng[t]}
    if t.isdigit() and 1 <= int(t) <= 255:
        return {'aci': int(t)}
    if t.startswith('#') and len(t) == 7:
        try:
            int(t[1:], 16)
            return {'aci': None, 'rgb': t}
        except ValueError:
            return None
    parts = [p.strip() for p in t.split(',')]
    if len(parts) == 3 and all(p.isdigit() and int(p) <= 255 for p in parts):
        return {'aci': None, 'rgb': '#%02x%02x%02x' % tuple(int(p) for p in parts)}
    return None
