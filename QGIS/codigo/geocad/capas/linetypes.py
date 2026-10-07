# -*- coding: utf-8 -*-
"""Tipos de línea y grosores estándar de AutoCAD."""

# Patrones en mm (positivo = trazo, se alterna trazo/hueco). 0.01 = punto.
LINETYPES = {
    'Continuous': {'desc': 'Continua ________________', 'pattern': []},
    'DASHED':     {'desc': 'Trazos __ __ __ __ __ __', 'pattern': [6.0, 3.0]},
    'DASHED2':    {'desc': 'Trazos (.5x) _ _ _ _ _ _ _', 'pattern': [3.0, 1.5]},
    'HIDDEN':     {'desc': 'Oculta _ _ _ _ _ _ _ _ _', 'pattern': [3.0, 1.5]},
    'HIDDEN2':    {'desc': 'Oculta (.5x) _ _ _ _ _ _ _ _', 'pattern': [1.5, 0.75]},
    'CENTER':     {'desc': 'Centro ____ _ ____ _ ____', 'pattern': [12.0, 2.0, 2.0, 2.0]},
    'CENTER2':    {'desc': 'Centro (.5x) ___ _ ___ _ ___', 'pattern': [7.0, 1.2, 1.2, 1.2]},
    'PHANTOM':    {'desc': 'Fantasma _____ _ _ _____ _ _', 'pattern': [12.0, 2.0, 2.0, 2.0, 2.0, 2.0]},
    'DOT':        {'desc': 'Puntos . . . . . . . . . .', 'pattern': [0.01, 1.5]},
    'DASHDOT':    {'desc': 'Trazo punto __ . __ . __ .', 'pattern': [6.0, 2.0, 0.01, 2.0]},
    'DIVIDE':     {'desc': 'Divisoria __ . . __ . . __', 'pattern': [6.0, 2.0, 0.01, 2.0, 0.01, 2.0]},
    'BORDER':     {'desc': 'Borde __ __ . __ __ . __', 'pattern': [6.0, 2.0, 6.0, 2.0, 0.01, 2.0]},
    'ACAD_ISO02W100': {'desc': 'ISO trazos __ __ __ __', 'pattern': [12.0, 3.0]},
    'ACAD_ISO10W100': {'desc': 'ISO trazo punto ____ . ____', 'pattern': [12.0, 3.0, 0.01, 3.0]},
}

LINETYPE_ORDER = list(LINETYPES.keys())

# Compatibilidad con la versión 1.x del complemento
LEGACY_LINETYPES = {'solid': 'Continuous', 'dash': 'DASHED',
                    'dot': 'DOT', 'dash dot': 'DASHDOT'}

LINEWEIGHTS = [0.00, 0.05, 0.09, 0.13, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35,
               0.40, 0.50, 0.53, 0.60, 0.70, 0.80, 0.90, 1.00, 1.06, 1.20,
               1.40, 1.58, 2.00, 2.11]

LW_DEFAULT = -1  # "Predeterminado"
LWDEFAULT_MM = 0.25


def lineweight_mm(lw):
    return LWDEFAULT_MM if lw is None or lw < 0 else float(lw)


def lineweight_text(lw):
    if lw is None or lw < 0:
        return 'Predeterminado'
    return '%.2f mm' % lw


def has_dots(pattern):
    return any(v < 0.1 for v in pattern[::2])
