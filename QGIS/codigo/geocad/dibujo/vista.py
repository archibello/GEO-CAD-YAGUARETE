# -*- coding: utf-8 -*-
"""ZOOM, PAN, REGEN y REDIBUJA de IngeCAD en Dibujo de QGIS (3.61.0): las cuentas, sin Qt.

ZOOM tiene las opciones del ZOOM de IngeCAD 0.7.0 (Todo, Centro, Extensión,
Previo, Escala, Ventana; 2X = de la vista actual, 2 = de todo el dibujo, una
esquina tecleada empieza la ventana, Intro = Extensión) y además, como pidió
Fernando (02/11/2026), Siguiente, Objeto, Ampliar/Reducir y la escala del mapa
1:n. Los comandos (vista_commands.py) usan estas cuentas con el mapa de QGIS.
"""

import re

#: el pedido de ZOOM, como el de IngeCAD (clave, etiqueta)
PEDIDO = 'Precise una esquina de ventana, indique un factor de escala (nX o 1:n) o'
OPCIONES = [('T', 'Todo'), ('C', 'Centro'), ('E', 'Extensión'), ('P', 'Previo'), ('SI', 'Siguiente'),
            ('S', 'Escala'), ('V', 'Ventana'), ('O', 'Objeto'), ('AM', 'Ampliar'), ('R', 'Reducir')]
DEFECTO = 'Extensión'

#: palabra escrita -> opción (castellano e inglés, como IngeCAD y AutoCAD)
CLAVES = {
    'T': 'T', 'TODO': 'T', 'A': 'T', 'ALL': 'T',
    'C': 'C', 'CENTRO': 'C', 'CENTER': 'C',
    'E': 'E', 'EXTENSION': 'E', 'EXTENSIÓN': 'E', 'EXTENTS': 'E',
    'P': 'P', 'PREVIO': 'P', 'PREVIOUS': 'P', 'ANTERIOR': 'P',
    'SI': 'SI', 'SIGUIENTE': 'SI', 'N': 'SI', 'NEXT': 'SI',
    'S': 'S', 'ES': 'S', 'ESCALA': 'S', 'SCALE': 'S',
    'V': 'V', 'VENTANA': 'V', 'W': 'V', 'WINDOW': 'V',
    'O': 'O', 'OBJETO': 'O', 'OBJECT': 'O',
    'AM': 'AM', 'AMPLIAR': 'AM', 'I': 'AM', 'IN': 'AM',
    'R': 'R', 'REDUCIR': 'R', 'OUT': 'R',
}

#: Ampliar / Reducir: la vista al doble o a la mitad (los botones de AutoCAD)
PASO = 2.0

_NUM = r'[+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)'
_VECES = re.compile(r'^(' + _NUM + r')\s*X$', re.I)
_XP = re.compile(r'^(' + _NUM + r'|\d+\s*/\s*\d+)\s*XP$', re.I)
_ESCALA = re.compile(r'^1\s*:\s*(' + _NUM + r')$')
_SOLO = re.compile(r'^(?:\d+(?:\.\d*)?|\.\d+)$')


def _num(t):
    return float(t.replace(',', '.'))


def opcion(texto):
    """La opción escrita ('T', 'C', 'E', ...) o None."""
    return CLAVES.get(texto.strip().upper().lstrip('_'))


def factor(texto):
    """Lo que ZOOM toma además de una palabra:
    ('veces', k) = nX de la vista actual; ('todo', k) = n de todo el dibujo;
    ('escala', n) = 1:n del mapa; ('xp', None) = nXP (sólo de IngeCAD);
    None = no es un factor. Un número con coma (0,5) es una esquina, como en
    IngeCAD; con X la coma es decimal (0,5X)."""
    t = texto.strip()
    if _XP.match(t):
        return ('xp', None)
    m = _VECES.match(t)
    if m:
        k = _num(m.group(1))
        return ('veces', k) if k > 0 else None
    m = _ESCALA.match(t)
    if m:
        n = _num(m.group(1))
        return ('escala', n) if n > 0 else None
    if _SOLO.match(t):
        k = float(t)
        return ('todo', k) if k > 0 else None
    return None


def rect_ventana(a, b):
    """(xmin, ymin, xmax, ymax) entre dos esquinas; None si no tiene ancho ni alto."""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    if x1 - x0 <= 0 and y1 - y0 <= 0:
        return None
    return (x0, y0, x1, y1)


def centro(r):
    return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)


def rect_centro(c, alto, aspecto):
    """La vista de ``alto`` con centro ``c``; ``aspecto`` = ancho / alto del mapa."""
    medio_y = alto / 2.0
    medio_x = medio_y * aspecto
    return (c[0] - medio_x, c[1] - medio_y, c[0] + medio_x, c[1] + medio_y)


def rect_escalado(r, k):
    """``r`` visto ``k`` veces más grande (k > 1 acerca, k < 1 aleja), mismo centro."""
    c = centro(r)
    medio_x = (r[2] - r[0]) / 2.0 / k
    medio_y = (r[3] - r[1]) / 2.0 / k
    return (c[0] - medio_x, c[1] - medio_y, c[0] + medio_x, c[1] + medio_y)


def union(rects, minimo=1.0):
    """Lo que encierra a todos los rectángulos (los objetos de ZOOM Objeto), con un
    5 % de margen; un punto solo o una línea recta toman ``minimo`` de lado."""
    rects = [r for r in rects if r is not None]
    if not rects:
        return None
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[2] for r in rects)
    y1 = max(r[3] for r in rects)
    lado = max(x1 - x0, y1 - y0)
    if lado <= 0:
        lado = minimo
    m = lado * 0.05
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    # sin ancho (o sin alto) toma el lado mayor, para que la vista no sea una raya
    hx = ((x1 - x0) if x1 > x0 else lado) / 2.0 + m
    hy = ((y1 - y0) if y1 > y0 else lado) / 2.0 + m
    return (cx - hx, cy - hy, cx + hx, cy + hy)


def altura(texto, actual):
    """«Indique magnificación o altura»: nX = la vista actual n veces más cerca;
    un número = alto de la vista en unidades del mapa; vacío = la de ahora."""
    t = texto.strip()
    if not t:
        return actual
    m = _VECES.match(t)
    if m:
        k = _num(m.group(1))
        if k <= 0:
            raise ValueError('La magnificación debe ser mayor que cero.')
        return actual / k
    try:
        h = _num(t)
    except ValueError:
        raise ValueError('Indique una altura o una magnificación (2X).')
    if h <= 0:
        raise ValueError('La altura debe ser mayor que cero.')
    return h


def _igual(a, b):
    tol = 1e-9 * max(1.0, abs(a[2] - a[0]), abs(a[3] - a[1]))
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Historial:
    """Las vistas para ZOOM Previo y Siguiente (como push_view de IngeCAD).

    El mapa de QGIS 4 no anota en su historial las vistas que cambia un
    complemento, así que se lleva acá: cada cambio de vista se anota; una
    ráfaga (la rueda del ratón, un arrastre) cuenta como una sola vista, y lo
    que hace un comando de vista (``cortar`` antes y después) es una vista
    propia."""
    RAFAGA = 0.6        # segundos entre cambios de una misma ráfaga
    MAXIMO = 50

    def __init__(self):
        self.vistas = []
        self.i = -1
        self.t = None

    def actual(self):
        return self.vistas[self.i] if self.vistas else None

    def anotar(self, r, ahora):
        if self.vistas and _igual(r, self.vistas[self.i]):
            return
        del self.vistas[self.i + 1:]
        if self.vistas and self.t is not None and ahora - self.t < self.RAFAGA:
            self.vistas[self.i] = r
        else:
            self.vistas.append(r)
        if len(self.vistas) > self.MAXIMO:
            del self.vistas[:len(self.vistas) - self.MAXIMO]
        self.i = len(self.vistas) - 1
        self.t = ahora

    def cortar(self):
        self.t = None

    def previo(self):
        if self.i <= 0:
            return None
        self.i -= 1
        self.t = None
        return self.vistas[self.i]

    def siguiente(self):
        if self.i >= len(self.vistas) - 1:
            return None
        self.i += 1
        self.t = None
        return self.vistas[self.i]


__all__ = ['PEDIDO', 'OPCIONES', 'DEFECTO', 'CLAVES', 'PASO', 'opcion', 'factor', 'rect_ventana',
           'centro', 'rect_centro', 'rect_escalado', 'union', 'altura', 'Historial']
