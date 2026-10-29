# SPDX-License-Identifier: GPL-3.0-or-later
"""Referencias a objetos para un solo punto (las «Osnap Overrides» de AutoCAD).

Al digitalizar líneas, polilíneas o polígonos con las herramientas de QGIS,
Shift + clic derecho despliega el mismo menú que IngeCAD (en inglés, mismas
opciones y orden) y la opción elegida vale para el punto siguiente.

Acá están las cuentas, en Python puro (sin Qt ni QGIS), sobre lo que hay
cerca del cursor en coordenadas del mapa. referencias_qgis.py junta esa
geometría de las capas, muestra el menú y agrega el vértice.

Mismo criterio que el motor de IngeCAD (core/snap.py, GPL-3.0): Geometric
Center es el centroide del área (no el promedio de los vértices), Origin es
el (0, 0) del espacio, PER se ofrece cuando el cursor está sobre el objeto
aunque el pie quede lejos, y Apparent Intersection queda en gris.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

#: (clave, texto del menú); None = separador. El orden del menú de IngeCAD.
MENU = (
    ("FROM", "From"),
    ("M2P", "Mid Between 2 Points"),
    None,
    ("END", "Endpoint"),
    ("MID", "Midpoint"),
    ("INT", "Intersection"),
    ("APP", "Apparent Intersection"),
    ("EXT", "Extension"),
    None,
    ("CEN", "Center"),
    ("GCE", "Geometric Center"),
    ("QUA", "Quadrant"),
    ("TAN", "Tangent"),
    None,
    ("PER", "Perpendicular"),
    ("PAR", "Parallel"),
    ("NOD", "Node"),
    ("INS", "Insertion"),
    ("NEA", "Nearest"),
    ("ORI", "Origin"),
    ("NON", "None"),
    None,
    ("SETTINGS", "Object Snap Settings..."),
)

#: las que todavía no están (en gris, como en IngeCAD)
NO_DISPONIBLES = {}     # APP desde la 3.56.0 (guias.py)

ETIQUETA = {item[0]: item[1] for item in MENU if item}

#: las que se resuelven buscando un objeto cerca del cursor
BUSCAN = frozenset({"END", "MID", "INT", "CEN", "GCE", "QUA", "TAN", "PER",
                    "NOD", "INS", "NEA", "ORI"})

#: las que necesitan el punto anterior
PIDEN_PREVIO = frozenset({"PER", "TAN", "PAR"})

_TAU = 2.0 * math.pi


@dataclass
class Datos:
    """La geometría cerca del cursor, en coordenadas del mapa.

    segs: tramos rectos (x1, y1, x2, y2, oid) — END y MID en sus puntas.
    cuerdas: tramos de un círculo o arco linealizado — sólo NEA, PER e INT.
    arcos: (cx, cy, r, a0, a1, completo, oid); a0 → a1 antihorario.
    nodos: puntos sueltos (capas de puntos). inserciones: puntos de inserción.
    centros: centroides de las figuras cerradas (Geometric Center).
    extremos: puntas de líneas curvas linealizadas (END en sus dos puntas).
    """
    segs: list = field(default_factory=list)
    cuerdas: list = field(default_factory=list)
    arcos: list = field(default_factory=list)
    nodos: list = field(default_factory=list)
    inserciones: list = field(default_factory=list)
    centros: list = field(default_factory=list)
    extremos: list = field(default_factory=list)


# ------------------------------------------------------------------ geometría
def centroide(pts):
    """Centroide del área de un anillo (sin repetir el primero al final), o None."""
    if len(pts) >= 2 and _igual(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    dos_a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cruz = x0 * y1 - x1 * y0
        dos_a += cruz
        cx += (x0 + x1) * cruz
        cy += (y0 + y1) * cruz
    if abs(dos_a) < 1e-12:
        return None
    return (cx / (3.0 * dos_a), cy / (3.0 * dos_a))


def circulo_de_anillo(pts, tolerancia=0.01, minimo=8):
    """(cx, cy, r) si el anillo cerrado es un círculo linealizado (todos los
    vértices a la misma distancia del centro, ±1 %), o None. Así llegan a
    QGIS los círculos de IngeCAD y de un DXF."""
    if len(pts) >= 2 and _igual(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < minimo:
        return None
    c = centroide(pts)
    if c is None:
        return None
    radios = [math.hypot(x - c[0], y - c[1]) for x, y in pts]
    r = sum(radios) / len(radios)
    if r <= 0 or max(abs(d - r) for d in radios) > tolerancia * r:
        return None
    return (c[0], c[1], r)


def arco_de_tres(p0, p1, p2):
    """El arco que pasa por p0, p1 y p2 (un tramo de CircularString):
    (cx, cy, r, a0, a1) con a0 → a1 antihorario, o None si están alineados."""
    (x0, y0), (x1, y1), (x2, y2) = p0, p1, p2
    d = 2.0 * (x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1))
    if abs(d) < 1e-12:
        return None
    s0, s1, s2 = x0 * x0 + y0 * y0, x1 * x1 + y1 * y1, x2 * x2 + y2 * y2
    cx = (s0 * (y1 - y2) + s1 * (y2 - y0) + s2 * (y0 - y1)) / d
    cy = (s0 * (x2 - x1) + s1 * (x0 - x2) + s2 * (x1 - x0)) / d
    r = math.hypot(x0 - cx, y0 - cy)
    a0 = math.atan2(y0 - cy, x0 - cx) % _TAU
    am = math.atan2(y1 - cy, x1 - cx) % _TAU
    a2 = math.atan2(y2 - cy, x2 - cx) % _TAU
    if _en_barrido(am, a0, a2):
        return (cx, cy, r, a0, a2)
    return (cx, cy, r, a2, a0)          # va en sentido horario: se da vuelta


def _en_barrido(ang, a0, a1):
    ang, a0, a1 = ang % _TAU, a0 % _TAU, a1 % _TAU
    if a0 <= a1:
        return a0 - 1e-12 <= ang <= a1 + 1e-12
    return ang >= a0 - 1e-12 or ang <= a1 + 1e-12


def _igual(a, b, tol=1e-9):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _mas_cercano_en_tramo(s, px, py):
    x1, y1, x2, y2 = s[:4]
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return (x1 + t * dx, y1 + t * dy)


def _pie_en_tramo(s, px, py):
    """Pie de la perpendicular desde (px, py), sólo si cae dentro del tramo."""
    x1, y1, x2, y2 = s[:4]
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 <= 1e-24:
        return None
    t = ((px - x1) * dx + (py - y1) * dy) / l2
    if t < -1e-9 or t > 1 + 1e-9:
        return None
    return (x1 + t * dx, y1 + t * dy)


def _cruce_tramos(a, b):
    x1, y1, x2, y2 = a[:4]
    x3, y3, x4, y4 = b[:4]
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-18:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _cruces_tramo_circulo(s, arco):
    x1, y1, x2, y2 = s[:4]
    cx, cy, r = arco[:3]
    dx, dy = x2 - x1, y2 - y1
    a = dx * dx + dy * dy
    if a <= 1e-24:
        return []
    b = 2 * (dx * (x1 - cx) + dy * (y1 - cy))
    c = (x1 - cx) ** 2 + (y1 - cy) ** 2 - r * r
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    raiz = math.sqrt(disc)
    out = []
    for t in sorted({(-b - raiz) / (2 * a), (-b + raiz) / (2 * a)}):
        if -1e-9 <= t <= 1 + 1e-9:
            out.append((x1 + t * dx, y1 + t * dy))
    return out


def _cruces_circulos(a, b):
    (x0, y0, r0), (x1, y1, r1) = a[:3], b[:3]
    d = math.hypot(x1 - x0, y1 - y0)
    if d <= 1e-12 or d > r0 + r1 or d < abs(r0 - r1):
        return []
    m = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(r0 * r0 - m * m, 0.0))
    xm, ym = x0 + m * (x1 - x0) / d, y0 + m * (y1 - y0) / d
    return [(xm + h * (y1 - y0) / d, ym - h * (x1 - x0) / d),
            (xm - h * (y1 - y0) / d, ym + h * (x1 - x0) / d)]


def _sobre_arco(arco, x, y):
    return arco[5] or _en_barrido(math.atan2(y - arco[1], x - arco[0]), arco[3], arco[4])


def _tangentes(arco, px, py):
    cx, cy, r = arco[:3]
    d = math.hypot(px - cx, py - cy)
    if d <= r:
        return []
    base = math.atan2(py - cy, px - cx)
    abre = math.acos(r / d)
    return [(cx + r * math.cos(base + s * abre), cy + r * math.sin(base + s * abre))
            for s in (1, -1)]


# ------------------------------------------------------------------ búsqueda
def buscar(modo, cursor, umbral, datos, previo=None):
    """El punto de la referencia `modo` más cercano al cursor dentro de
    `umbral` (unidades del mapa), o None. `previo`: el último vértice
    (PER y TAN se miden desde ahí)."""
    cx, cy = cursor
    mejor = [None, None]

    def ofrecer(x, y, alcance=None):
        d = math.hypot(x - cx, y - cy) if alcance is None else alcance
        if d <= umbral and (mejor[1] is None or d < mejor[1]):
            mejor[0], mejor[1] = (float(x), float(y)), d

    rectos = datos.segs
    todos = list(datos.segs) + list(datos.cuerdas)
    if modo == "ORI":
        ofrecer(0.0, 0.0)
    elif modo == "END":
        for s in rectos:
            ofrecer(s[0], s[1])
            ofrecer(s[2], s[3])
        for a in datos.arcos:
            if not a[5]:
                for ang in (a[3], a[4]):
                    ofrecer(a[0] + a[2] * math.cos(ang), a[1] + a[2] * math.sin(ang))
        for x, y in datos.extremos:
            ofrecer(x, y)
    elif modo == "MID":
        for s in rectos:
            ofrecer((s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0)
        for a in datos.arcos:
            if not a[5]:
                fin = a[4] if a[4] >= a[3] else a[4] + _TAU
                m = (a[3] + fin) / 2.0
                ofrecer(a[0] + a[2] * math.cos(m), a[1] + a[2] * math.sin(m))
    elif modo == "CEN":
        for a in datos.arcos:
            ofrecer(a[0], a[1])
    elif modo == "GCE":
        for x, y in datos.centros:
            ofrecer(x, y)
    elif modo == "NOD":
        for x, y in datos.nodos:
            ofrecer(x, y)
    elif modo == "INS":
        for x, y in datos.inserciones:
            ofrecer(x, y)
    elif modo == "QUA":
        for a in datos.arcos:
            for paso in range(4):
                ang = paso * math.pi / 2.0
                if a[5] or _en_barrido(ang, a[3], a[4]):
                    ofrecer(a[0] + a[2] * math.cos(ang), a[1] + a[2] * math.sin(ang))
    elif modo == "INT":
        cerca = [s for s in todos if _dist_tramo(s, cx, cy) <= umbral][:64]
        for i, a in enumerate(cerca):
            for b in cerca[i + 1:]:
                if _mismo_objeto(a, b):
                    continue
                p = _cruce_tramos(a, b)
                if p is not None:
                    ofrecer(*p)
        bordes = [a for a in datos.arcos
                  if abs(math.hypot(cx - a[0], cy - a[1]) - a[2]) <= umbral][:32]
        for i, a in enumerate(bordes):
            for s in cerca:
                if s[4] == a[6]:
                    continue
                for x, y in _cruces_tramo_circulo(s, a):
                    if _sobre_arco(a, x, y):
                        ofrecer(x, y)
            for b in bordes[i + 1:]:
                if b[6] == a[6]:
                    continue
                for x, y in _cruces_circulos(a, b):
                    if _sobre_arco(a, x, y) and _sobre_arco(b, x, y):
                        ofrecer(x, y)
    elif modo == "PER" and previo is not None:
        fx, fy = previo
        mismo = umbral * 1e-3
        for s in todos:
            p = _pie_en_tramo(s, fx, fy)
            if p is None or math.hypot(p[0] - fx, p[1] - fy) <= mismo:
                continue
            sobre = _mas_cercano_en_tramo(s, cx, cy)
            ofrecer(p[0], p[1], alcance=math.hypot(sobre[0] - cx, sobre[1] - cy))
        for a in datos.arcos:          # a un círculo: el punto en la recta centro-previo
            d = math.hypot(fx - a[0], fy - a[1])
            if d <= 1e-12:
                continue
            for s in (1, -1):
                x = a[0] + s * a[2] * (fx - a[0]) / d
                y = a[1] + s * a[2] * (fy - a[1]) / d
                if _sobre_arco(a, x, y):
                    ofrecer(x, y)
    elif modo == "TAN":
        for a in datos.arcos:
            if previo is not None:
                for x, y in _tangentes(a, *previo):
                    if _sobre_arco(a, x, y):
                        ofrecer(x, y)
            else:                      # sin punto anterior: el punto del borde bajo el cursor
                d = math.hypot(cx - a[0], cy - a[1])
                if d > 1e-12 and abs(d - a[2]) <= umbral:
                    x, y = a[0] + a[2] * (cx - a[0]) / d, a[1] + a[2] * (cy - a[1]) / d
                    if _sobre_arco(a, x, y):
                        ofrecer(x, y)
    elif modo == "NEA":
        for s in todos:
            ofrecer(*_mas_cercano_en_tramo(s, cx, cy))
        for a in datos.arcos:
            d = math.hypot(cx - a[0], cy - a[1])
            if d > 1e-12:
                x, y = a[0] + a[2] * (cx - a[0]) / d, a[1] + a[2] * (cy - a[1]) / d
                if _sobre_arco(a, x, y):
                    ofrecer(x, y)
    return mejor[0]


def _dist_tramo(s, px, py):
    q = _mas_cercano_en_tramo(s, px, py)
    return math.hypot(q[0] - px, q[1] - py)


def _mismo_objeto(a, b):
    """Dos tramos de una misma cadena que se tocan en la punta no son una
    intersección (el vértice ya es END); sí lo son si se cruzan en el medio."""
    if a[4] != b[4]:
        return False
    return any(_igual(p, q) for p in ((a[0], a[1]), (a[2], a[3]))
               for q in ((b[0], b[1]), (b[2], b[3])))


# ------------------------------------------------------------------ Extension y Parallel
def fuente_extension(cursor, umbral, datos):
    """La punta de un tramo bajo el cursor y la dirección que sale de él por
    esa punta: ((x, y), (ux, uy)), o None. Se «adquiere» pasando por encima,
    como en AutoCAD."""
    cx, cy = cursor
    mejor = None
    for s in datos.segs:
        for (ex, ey), (ox, oy) in (((s[2], s[3]), (s[0], s[1])), ((s[0], s[1]), (s[2], s[3]))):
            largo = math.hypot(ex - ox, ey - oy)
            d = math.hypot(ex - cx, ey - cy)
            if largo > 1e-12 and d <= umbral and (mejor is None or d < mejor[0]):
                mejor = (d, ((ex, ey), ((ex - ox) / largo, (ey - oy) / largo)))
    return mejor[1] if mejor else None


def sobre_extension(cursor, umbral, fuentes):
    """El punto de la prolongación (más allá de la punta) más cercano al
    cursor, si está dentro del umbral; o None."""
    cx, cy = cursor
    mejor = None
    for (ex, ey), (ux, uy) in fuentes:
        t = (cx - ex) * ux + (cy - ey) * uy
        if t <= 0:
            continue
        x, y = ex + t * ux, ey + t * uy
        d = math.hypot(x - cx, y - cy)
        if d <= umbral and (mejor is None or d < mejor[0]):
            mejor = (d, (x, y))
    return mejor[1] if mejor else None


def direccion_de_tramo(cursor, umbral, datos):
    """Dirección unitaria del tramo recto bajo el cursor (para Parallel), o None."""
    cx, cy = cursor
    mejor = None
    for s in datos.segs:
        largo = math.hypot(s[2] - s[0], s[3] - s[1])
        d = _dist_tramo(s, cx, cy)
        if largo > 1e-12 and d <= umbral and (mejor is None or d < mejor[0]):
            mejor = (d, ((s[2] - s[0]) / largo, (s[3] - s[1]) / largo))
    return mejor[1] if mejor else None


def sobre_paralela(cursor, umbral, previo, direcciones):
    """El punto de la recta por `previo` paralela a una dirección adquirida,
    el más cercano al cursor dentro del umbral; o None."""
    if previo is None:
        return None
    cx, cy = cursor
    px, py = previo
    mejor = None
    for ux, uy in direcciones:
        t = (cx - px) * ux + (cy - py) * uy
        x, y = px + t * ux, py + t * uy
        d = math.hypot(x - cx, y - cy)
        if abs(t) > 1e-12 and d <= umbral and (mejor is None or d < mejor[0]):
            mejor = (d, (x, y))
    return mejor[1] if mejor else None


# ------------------------------------------------------------------ From y Mid Between 2 Points
def medio(p, q):
    return ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)


_NUM = r"[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+]?\d+)?"


def _num(texto):
    return float(texto.replace(",", "."))


def desplazamiento(texto, base):
    """El punto a `texto` de `base`, como el FROM de AutoCAD: «@dx,dy» o
    «@distancia<ángulo» (grados, antihorario desde el este). La @ es
    opcional. Con «;» entre los dos valores se puede usar coma decimal
    («@3,5;-2»). Devuelve (x, y) o None si no se entiende."""
    t = (texto or "").strip().replace(" ", "")
    if t.startswith("@"):
        t = t[1:]
    if not t:
        return None
    m = re.fullmatch(f"({_NUM})<({_NUM})", t)
    if m:
        d, ang = _num(m.group(1)), math.radians(_num(m.group(2)))
        return (base[0] + d * math.cos(ang), base[1] + d * math.sin(ang))
    sep = ";" if ";" in t else ","
    partes = t.split(sep)
    if len(partes) != 2:
        return None
    try:
        dx, dy = (_num(p) if sep == ";" else float(p) for p in partes)
    except ValueError:
        return None
    return (base[0] + dx, base[1] + dy)
