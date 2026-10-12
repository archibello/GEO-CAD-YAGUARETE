# SPDX-License-Identifier: GPL-3.0-or-later
"""GEORREF (RUBBERSHEET, AJUSTEIMAGEN): llevar una imagen a su lugar con
puntos de control, como el Georreferenciador de QGIS (módulo «georref», 3.18.0).

IngeCAD no tiene cómo ajustar un plano escaneado o una foto aérea con
puntos de control (AutoCAD Map lo hace con RUBBERSHEET). Acá:

  1) se designa UNA imagen (imágenes y vectores no se mezclan; de a una);
  2) se marcan pares de puntos con referencias o coordenadas escritas:
     «Punto en la imagen n» (dónde está) y «Punto de destino n» (dónde
     tiene que quedar). Cada par se ve como una flecha numerada; U quita
     el último. Con los puntos suficientes se ve, punteado, dónde va a
     quedar la imagen;
  3) Enter abre la TABLA DE PUNTOS, como la «Tabla de PCT» de QGIS:
     habilitado, X/Y de origen (píxeles de la imagen, como QGIS), X/Y de
     destino, dX, dY y residuo, y el error medio; el método con los mismos
     nombres de QGIS;
  4) «Transformar»: Lineal, Helmert y Polinómica 1 no rehacen la imagen:
     cambian su punto de inserción y sus vectores. Proyectiva, Polinómica
     2-3 y Thin Plate Spline (3.21.0) la deforman: GeoCAD la rehace con PIL
     (remuestreo Vecino / Lineal / Cúbica; fondo transparente, blanco o los
     dos) en una copia con su archivo de mundo, y el dibujo pasa a usarla.
     Un solo U la vuelve a como estaba. Los puntos quedan en
     «<imagen>.points», el mismo archivo del Georreferenciador de QGIS (y se
     pueden cargar de ahí).

«Transformar en QGIS» con GDAL llega más adelante. Las cuentas no usan Qt.
"""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

from core import actions
from tools.base import Tool

from . import modulos

PROGRAMA = "ingecad"

#: clave -> (nombre como en QGIS, puntos mínimos, disponible en esta versión)
METODOS = {
    "lineal": ("Lineal", 2, True),
    "helmert": ("Helmert", 2, True),
    "polinomica1": ("Polinómica 1", 3, True),
    "polinomica2": ("Polinómica 2", 6, True),
    "polinomica3": ("Polinómica 3", 10, True),
    "tps": ("Thin Plate Spline", 3, True),
    "proyectiva": ("Proyectiva", 4, True),
}
DISPONIBLES = tuple(k for k, (_n, _m, d) in METODOS.items() if d)
#: los que deforman la imagen: hay que rehacerla (3.21.0)
REHACEN = frozenset({"polinomica2", "polinomica3", "tps", "proyectiva"})
#: remuestreo al rehacer (los nombres de QGIS)
REMUESTREOS = {"vecino": "Vecino más próximo", "lineal": "Lineal", "cubica": "Cúbica"}
_ultimo_remuestreo = ["vecino"]
#: fondo de la imagen rehecha, fuera de la imagen deformada
FONDOS = {
    "transparente": "Transparente (PNG; TIFF si la original lo es)",
    "blanco": "Blanco (el mismo formato de la original)",
    "ambos": "Los dos: transparente y blanco (el dibujo usa la transparente)",
}
_ultimo_fondo = ["transparente"]
#: el método con que arranca la tabla (Helmert: no deforma un plano escaneado)
METODO_INICIAL = "helmert"
_ultimo_metodo = [METODO_INICIAL]          # el último usado, mientras IngeCAD esté abierto
#: qué se guarda al transformar (3.18.1), además del dibujo
SALIDAS = {
    "copia": "Una copia ajustada, con su archivo de mundo (la original queda como está)",
    "mundo": "Un archivo de mundo junto a la imagen original",
    "dibujo": "Sólo el dibujo",
}
_ultima_salida = ["copia"]
SUFIJO_COPIA = "_georref"

CABECERA_POINTS = "mapX,mapY,sourceX,sourceY,enable,dX,dY,residual"
EPS = 1e-12


def _fmt(v: float, dec: int = 4) -> str:
    return f"{v:.{dec}f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else f"{v:g}"


# ------------------------------------------------------------- los métodos
class AjusteError(ValueError):
    """No se puede calcular (pocos puntos, puntos repetidos o alineados)."""


# -- los que deforman (3.21.0): cuentas en Python puro, sin numpy
def _resolver(A, b):
    """A·x = b por Gauss con pivoteo parcial; None si es singular."""
    n = len(A)
    M = [list(map(float, fila)) + [float(v)] for fila, v in zip(A, b)]
    escala = max((abs(v) for fila in M for v in fila[:n]), default=0.0) or 1.0
    for k in range(n):
        piv = max(range(k, n), key=lambda i: abs(M[i][k]))
        if abs(M[piv][k]) <= 1e-12 * escala:
            return None
        M[k], M[piv] = M[piv], M[k]
        for i in range(k + 1, n):
            m = M[i][k] / M[k][k]
            if m:
                for j in range(k, n + 1):
                    M[i][j] -= m * M[k][j]
    x = [0.0] * n
    for k in range(n - 1, -1, -1):
        x[k] = (M[k][n] - sum(M[k][j] * x[j] for j in range(k + 1, n))) / M[k][k]
    return x


def _minimos_cuadrados(filas, valores):
    """El x que minimiza |F·x − v| (ecuaciones normales); None si no hay
    solución única."""
    m = len(filas[0])
    A = [[sum(f[i] * f[j] for f in filas) for j in range(m)] for i in range(m)]
    b = [sum(f[i] * v for f, v in zip(filas, valores)) for i in range(m)]
    return _resolver(A, b)


def _normalizador(puntos):
    """Centro y escala (distancia media al centro = √2), como Hartley: las
    cuentas quedan bien condicionadas con coordenadas de millones."""
    n = len(puntos)
    cx = sum(p[0] for p in puntos) / n
    cy = sum(p[1] for p in puntos) / n
    d = sum(math.hypot(p[0] - cx, p[1] - cy) for p in puntos) / n
    return cx, cy, (math.sqrt(2) / d if d > EPS else 1.0)


def _terminos(orden, x, y):
    return [x ** (i - j) * y ** j for i in range(orden + 1) for j in range(i + 1)]


class Modelo:
    """Un ajuste que deforma la imagen: ``directo`` lleva píxel de QGIS ->
    dibujo; ``inverso``, dibujo -> píxel (lo usa el remuestreo). Se aplica
    con :func:`aplicar` igual que los 6 coeficientes de los afines."""

    metodo = ""

    def directo(self, p):
        raise NotImplementedError

    def inverso(self, p):
        raise NotImplementedError

    def invertido(self) -> "Modelo":
        return _Invertido(self)


class _Invertido(Modelo):
    def __init__(self, m):
        self.m, self.metodo = m, m.metodo

    def directo(self, p):
        return self.m.inverso(p)

    def inverso(self, p):
        return self.m.directo(p)

    def invertido(self):
        return self.m


def _h_aplicar(H, p):
    x, y = p
    w = H[2][0] * x + H[2][1] * y + H[2][2]
    if abs(w) <= EPS:
        raise ZeroDivisionError("punto en el infinito")
    return ((H[0][0] * x + H[0][1] * y + H[0][2]) / w,
            (H[1][0] * x + H[1][1] * y + H[1][2]) / w)


def _h_mult(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _h_inversa(H):
    (a, b, c), (d, e, f), (g, h, i) = H
    A, B, C = e * i - f * h, -(d * i - f * g), d * h - e * g
    det = a * A + b * B + c * C
    if abs(det) <= EPS:
        raise AjusteError("Proyectiva: con estos puntos la imagen quedaría aplastada.")
    return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
            [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
            [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]]


class Proyectiva(Modelo):
    """X = (a·x + b·y + c) / (g·x + h·y + 1), Y = (d·x + e·y + f) / (...):
    lleva 4 puntos a cualquier cuadrilátero (exacto) y con más ajusta por
    mínimos cuadrados (DLT normalizada). Las rectas siguen rectas."""

    metodo = "proyectiva"

    def __init__(self, origen, destino):
        sx, sy, ss = _normalizador(origen)
        dx, dy, ds = _normalizador(destino)
        filas, valores = [], []
        for (x, y), (X, Y) in zip(origen, destino):
            x, y = (x - sx) * ss, (y - sy) * ss
            X, Y = (X - dx) * ds, (Y - dy) * ds
            filas.append([x, y, 1, 0, 0, 0, -x * X, -y * X])
            valores.append(X)
            filas.append([0, 0, 0, x, y, 1, -x * Y, -y * Y])
            valores.append(Y)
        h = _minimos_cuadrados(filas, valores)
        if h is None:
            raise AjusteError("Proyectiva necesita 4 puntos sin 3 alineados.")
        Hn = [h[0:3], h[3:6], [h[6], h[7], 1.0]]
        Ts = [[ss, 0, -ss * sx], [0, ss, -ss * sy], [0, 0, 1]]
        Td_inv = [[1 / ds, 0, dx], [0, 1 / ds, dy], [0, 0, 1]]
        H = _h_mult(Td_inv, _h_mult(Hn, Ts))
        k = H[2][2]
        if abs(k) <= EPS:
            raise AjusteError("Proyectiva: con estos puntos la imagen se iría al infinito.")
        self.H = [[v / k for v in fila] for fila in H]
        self.Hi = _h_inversa(self.H)

    def directo(self, p):
        return _h_aplicar(self.H, p)

    def inverso(self, p):
        return _h_aplicar(self.Hi, p)

    def denominador(self, p):
        return self.H[2][0] * p[0] + self.H[2][1] * p[1] + self.H[2][2]


class _Polinomio:
    """Un sentido de la polinómica de orden 2 o 3, en coordenadas
    normalizadas."""

    def __init__(self, orden, origen, destino, nombre):
        self.orden = orden
        self.no = _normalizador(origen)
        cx, cy, s = self.no
        filas = [_terminos(orden, (x - cx) * s, (y - cy) * s) for x, y in origen]
        self.cx = _minimos_cuadrados(filas, [p[0] for p in destino])
        self.cy = _minimos_cuadrados(filas, [p[1] for p in destino])
        if self.cx is None or self.cy is None:
            raise AjusteError(f"{nombre}: los puntos no alcanzan para calcularla (hay "
                              "puntos repetidos, alineados o sobre una misma curva).")

    def __call__(self, p):
        cx, cy, s = self.no
        t = _terminos(self.orden, (p[0] - cx) * s, (p[1] - cy) * s)
        return (sum(a * b for a, b in zip(self.cx, t)), sum(a * b for a, b in zip(self.cy, t)))


class Polinomica(Modelo):
    """Polinómica 2 (6 términos) o 3 (10), por mínimos cuadrados. Como GDAL,
    la vuelta (dibujo -> píxel) es otra polinómica ajustada con los mismos
    puntos al revés: no hay fórmula exacta para invertirla."""

    def __init__(self, orden, origen, destino):
        self.metodo = f"polinomica{orden}"
        self.nombre = METODOS[self.metodo][0]
        self.orden, self._origen, self._destino = orden, list(origen), list(destino)
        self._ida = _Polinomio(orden, origen, destino, self.nombre)
        self._vuelta = None

    def directo(self, p):
        return self._ida(p)

    def inverso(self, p):
        if self._vuelta is None:
            self._vuelta = _Polinomio(self.orden, self._destino, self._origen, self.nombre)
        return self._vuelta(p)


def _u(r2):
    return r2 * math.log(r2) if r2 > 0 else 0.0


class _Spline:
    """Un sentido de la Thin Plate Spline: pasa exacta por cada punto y se
    dobla lo mínimo entre ellos (U(r) = r²·ln r²), más una parte afín."""

    def __init__(self, origen, destino):
        self.no = _normalizador(origen)
        cx, cy, s = self.no
        self.p = [((x - cx) * s, (y - cy) * s) for x, y in origen]
        n = len(self.p)
        A = []
        for i, (xi, yi) in enumerate(self.p):
            fila = [_u((xi - xj) ** 2 + (yi - yj) ** 2) for xj, yj in self.p]
            A.append(fila + [1.0, xi, yi])
        A.append([1.0] * n + [0.0] * 3)
        A.append([x for x, _y in self.p] + [0.0] * 3)
        A.append([y for _x, y in self.p] + [0.0] * 3)
        self.wx = _resolver(A, [q[0] for q in destino] + [0.0] * 3)
        self.wy = _resolver(A, [q[1] for q in destino] + [0.0] * 3)
        if self.wx is None or self.wy is None:
            raise AjusteError("Thin Plate Spline necesita 3 puntos que no estén alineados "
                              "y sin puntos repetidos.")

    def __call__(self, p):
        cx, cy, s = self.no
        x, y = (p[0] - cx) * s, (p[1] - cy) * s
        n = len(self.p)
        X = self.wx[n] + self.wx[n + 1] * x + self.wx[n + 2] * y
        Y = self.wy[n] + self.wy[n + 1] * x + self.wy[n + 2] * y
        for k, (xi, yi) in enumerate(self.p):
            u = _u((x - xi) ** 2 + (y - yi) ** 2)
            X += self.wx[k] * u
            Y += self.wy[k] * u
        return X, Y


class ThinPlateSpline(Modelo):
    """La «goma»: cada punto va exacto a su destino (residuos cero) y la
    imagen se estira suave entre ellos. La vuelta es otra spline con los
    puntos al revés, como en GDAL."""

    metodo = "tps"

    def __init__(self, origen, destino):
        self._origen, self._destino = list(origen), list(destino)
        self._ida = _Spline(origen, destino)
        self._vuelta = None

    def directo(self, p):
        return self._ida(p)

    def inverso(self, p):
        if self._vuelta is None:
            self._vuelta = _Spline(self._destino, self._origen)
        return self._vuelta(p)


def _ajustar_deformante(metodo, origen, destino):
    if len(set(origen)) != len(origen) or len(set(destino)) != len(destino):
        raise AjusteError("Hay puntos repetidos: apagá uno de cada par repetido.")
    if metodo == "proyectiva":
        from itertools import combinations

        for pts in (origen, destino):
            if len(pts) == 4 and any(abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
                                     <= 1e-9 * max(1.0, math.dist(a, b) * math.dist(a, c))
                                     for a, b, c in combinations(pts, 3)):
                raise AjusteError("Proyectiva necesita 4 puntos sin 3 alineados.")
        return Proyectiva(origen, destino)
    if metodo == "tps":
        return ThinPlateSpline(origen, destino)
    return Polinomica(int(metodo[-1]), origen, destino)


def ajustar(metodo: str, origen, destino):
    """Los 6 coeficientes (a, b, c, d, e, f) de X = a + b·x + c·y,
    Y = d + e·x + f·y que llevan ``origen`` (x, y) a ``destino`` (X, Y), por
    mínimos cuadrados, como QGIS:
      Lineal        escala en X y en Y por separado y desplazamiento, sin giro;
      Helmert       escala única, giro y desplazamiento (no deforma);
      Polinómica 1  afín: escalas, giro y sesgo.
    Proyectiva, Polinómica 2-3 y Thin Plate Spline no entran en 6
    coeficientes: devuelven un :class:`Modelo`."""
    if metodo not in METODOS:
        raise AjusteError(f"Método desconocido: {metodo}.")
    nombre, minimo, disponible = METODOS[metodo]
    if not disponible:
        raise AjusteError(f"{nombre} llega más adelante.")
    origen = [(float(x), float(y)) for x, y in origen]
    destino = [(float(x), float(y)) for x, y in destino]
    n = len(origen)
    if n != len(destino):
        raise AjusteError("Hay distinta cantidad de puntos de origen y de destino.")
    if n < minimo:
        raise AjusteError(f"{nombre} necesita al menos {minimo} puntos habilitados (hay {n}).")
    if metodo in REHACEN:
        return _ajustar_deformante(metodo, origen, destino)
    mx = sum(p[0] for p in origen) / n
    my = sum(p[1] for p in origen) / n
    mX = sum(p[0] for p in destino) / n
    mY = sum(p[1] for p in destino) / n
    o = [(x - mx, y - my) for x, y in origen]
    d = [(x - mX, y - mY) for x, y in destino]
    sxx = sum(x * x for x, _y in o)
    syy = sum(y * y for _x, y in o)
    escala = max(sxx, syy, 1.0)
    if metodo == "lineal":
        if sxx <= EPS * escala or syy <= EPS * escala:
            raise AjusteError("Lineal necesita puntos que no estén todos en una misma "
                              "horizontal o vertical de la imagen.")
        b = sum(p[0] * q[0] for p, q in zip(o, d)) / sxx
        f = sum(p[1] * q[1] for p, q in zip(o, d)) / syy
        c = e = 0.0
    elif metodo == "helmert":
        s = sxx + syy
        if s <= EPS:
            raise AjusteError("Los puntos de origen están todos en el mismo lugar.")
        A = sum(p[0] * q[0] + p[1] * q[1] for p, q in zip(o, d)) / s
        B = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(o, d)) / s
        b, c, e, f = A, -B, B, A
    else:                                          # polinomica1: afín
        sxy = sum(x * y for x, y in o)
        det = sxx * syy - sxy * sxy
        if abs(det) <= 1e-9 * escala * escala:
            raise AjusteError("Polinómica 1 necesita 3 puntos que no estén alineados.")
        sxX = sum(p[0] * q[0] for p, q in zip(o, d))
        syX = sum(p[1] * q[0] for p, q in zip(o, d))
        sxY = sum(p[0] * q[1] for p, q in zip(o, d))
        syY = sum(p[1] * q[1] for p, q in zip(o, d))
        b = (sxX * syy - syX * sxy) / det
        c = (syX * sxx - sxX * sxy) / det
        e = (sxY * syy - syY * sxy) / det
        f = (syY * sxx - sxY * sxy) / det
    if abs(b * f - c * e) <= EPS:
        raise AjusteError("Con estos puntos la imagen quedaría aplastada (escala cero).")
    a = mX - b * mx - c * my
    dd = mY - e * mx - f * my
    return (a, b, c, dd, e, f)


def aplicar(coef, p) -> tuple:
    if isinstance(coef, Modelo):
        return coef.directo(p)
    a, b, c, d, e, f = coef
    x, y = p
    return (a + b * x + c * y, d + e * x + f * y)


def inversa(coef):
    if isinstance(coef, Modelo):
        return coef.invertido()
    a, b, c, d, e, f = coef
    det = b * f - c * e
    ib, ic, ie, if_ = f / det, -c / det, -e / det, b / det
    return (-(ib * a + ic * d), ib, ic, -(ie * a + if_ * d), ie, if_)


def residuos(coef, origen, destino) -> list:
    """(dX, dY, residuo) de cada punto: destino − calculado, en unidades
    del dibujo."""
    out = []
    for p, q in zip(origen, destino):
        X, Y = aplicar(coef, p)
        dx, dy = q[0] - X, q[1] - Y
        out.append((dx, dy, math.hypot(dx, dy)))
    return out


def error_medio(res, habilitados) -> float:
    """Error medio cuadrático de los puntos habilitados."""
    r = [x[2] for x, h in zip(res, habilitados) if h]
    return math.sqrt(sum(v * v for v in r) / len(r)) if r else 0.0


def describir(coef) -> str:
    """Escala y giro que resultan, para el informe."""
    if isinstance(coef, Modelo):
        return "deforma la imagen: al transformar se rehace"
    _a, b, c, _d, e, f = coef
    sx, sy = math.hypot(b, e), math.hypot(c, f)
    giro = math.degrees(math.atan2(e, b))
    if abs(sx - sy) <= 1e-9 * max(sx, sy):
        return f"escala {_fmt(sx, 6)}, giro {_fmt(giro, 4)}°"
    return f"escala X {_fmt(sx, 6)}, Y {_fmt(sy, 6)}, giro {_fmt(giro, 4)}°"


# ------------------------------------------------------------- la imagen
def tamano(img) -> tuple:
    s = img.dxf.image_size
    return float(s[0]), float(s[1])


def _base(img):
    """insert, u, v (por píxel) de la imagen, en 2D."""
    i, u, v = img.dxf.insert, img.dxf.u_pixel, img.dxf.v_pixel
    return (i[0], i[1]), (u[0], u[1]), (v[0], v[1])


def coef_imagen(img) -> tuple:
    """Píxel de QGIS (columna, −fila; arriba a la izquierda = 0, 0) -> dibujo.
    ezdxf cuenta las filas desde abajo: y = sourceY + alto."""
    (ix, iy), (ux, uy), (vx, vy) = _base(img)
    _w, h = tamano(img)
    return (ix + vx * h, ux, vx, iy + vy * h, uy, vy)


def mundo_a_pixel(img, p) -> tuple:
    return aplicar(inversa(coef_imagen(img)), p)


def pixel_a_mundo(img, s) -> tuple:
    return aplicar(coef_imagen(img), s)


def esquinas(img, coef=None, tramos: int = 16) -> list:
    """Las 4 esquinas de la imagen en el dibujo (con ``coef``: donde
    quedarían después de transformar). Polinómica 2-3 y TPS curvan los
    bordes: van ``tramos`` puntos por lado."""
    w, h = tamano(img)
    c = coef if coef is not None else coef_imagen(img)
    return [aplicar(c, s) for s in borde_pixeles(w, h, c, tramos)]


def borde_pixeles(w, h, coef=None, tramos: int = 16) -> list:
    """El contorno de la imagen en píxeles de QGIS: las 4 esquinas o, si
    ``coef`` curva los bordes, ``tramos`` puntos por lado."""
    vertices = ((0, 0), (w, 0), (w, -h), (0, -h))
    if not isinstance(coef, Modelo) or isinstance(coef, Proyectiva):
        return list(vertices)
    out = []
    for i in range(4):
        (x0, y0), (x1, y1) = vertices[i], vertices[(i + 1) % 4]
        out += [(x0 + (x1 - x0) * k / tramos, y0 + (y1 - y0) * k / tramos) for k in range(tramos)]
    return out


def marco(puntos) -> list:
    return [(puntos[i], puntos[(i + 1) % len(puntos)]) for i in range(len(puntos))]


def dentro(img, p) -> bool:
    w, h = tamano(img)
    try:
        x, y = mundo_a_pixel(img, p)
    except ZeroDivisionError:
        return False
    return -EPS <= x <= w + EPS and -h - EPS <= y <= EPS


def matriz(img, coef, alto=None):
    """La Matrix44 (dibujo -> dibujo) que lleva la imagen de donde está a
    donde la deja ``coef`` (píxel de QGIS -> dibujo). Va por TransformCommand
    de IngeCAD: deshacer exacto y la imagen se redibuja sin regenerar.
    ``alto``: el de la imagen rehecha (si no, el de la imagen)."""
    from ezdxf.math import Matrix44

    h = float(alto) if alto is not None else tamano(img)[1]
    (ix, iy), (ux, uy), (vx, vy) = _base(img)
    a, b, c, d, e, f = coef
    nu, nv = (b, e), (c, f)                   # vectores nuevos por píxel
    ni = (a - c * h, d - f * h)               # esquina de abajo a la izquierda
    det = ux * vy - vx * uy
    # L·[u v] = [nu nv]  ->  L = [nu nv]·[u v]⁻¹
    i00, i01, i10, i11 = vy / det, -vx / det, -uy / det, ux / det
    l00 = nu[0] * i00 + nv[0] * i10
    l01 = nu[0] * i01 + nv[0] * i11
    l10 = nu[1] * i00 + nv[1] * i10
    l11 = nu[1] * i01 + nv[1] * i11
    tx = ni[0] - (l00 * ix + l01 * iy)
    ty = ni[1] - (l10 * ix + l11 * iy)
    return Matrix44((l00, l10, 0, 0, l01, l11, 0, 0, 0, 0, 1, 0, tx, ty, 0, 1))


def archivo_imagen(img, document=None):
    """La ruta del archivo de la imagen (relativa al dibujo si no es absoluta)."""
    try:
        nombre = img.image_def.dxf.filename
    except Exception:  # noqa: BLE001
        return None
    if not nombre:
        return None
    p = Path(nombre)
    if not p.is_absolute():
        base = getattr(document, "path", None)
        if base:
            p = Path(base).parent / p
    return p


def ruta_points(img, document=None):
    """«plano.png.points», junto a la imagen, como lo guarda QGIS."""
    p = archivo_imagen(img, document)
    return p.with_name(p.name + ".points") if p is not None else None


# ------------------------------------------------------------- archivo .points
def escribir_points(ruta, pares, crs: str = "", metodo: str = "") -> Path:
    """El .points del Georreferenciador de QGIS. ``pares``: dicts con sx, sy
    (píxel de QGIS), X, Y (dibujo) y on. dX, dY y residuo, en píxeles (como
    QGIS; él los vuelve a calcular al cargar). Si ya había uno distinto,
    queda una copia «.points.bak»."""
    ruta = Path(ruta)
    hab = [p for p in pares if p["on"]]
    coef_inv = None
    if metodo:
        try:
            coef_inv = inversa(ajustar(metodo, [(p["sx"], p["sy"]) for p in hab],
                                       [(p["X"], p["Y"]) for p in hab]))
        except (AjusteError, ZeroDivisionError):
            coef_inv = None
    lineas = []
    if crs:
        lineas.append(f"#CRS: {crs}")
    lineas.append(CABECERA_POINTS)
    for p in pares:
        dx = dy = r = 0.0
        if coef_inv is not None:
            qx, qy = aplicar(coef_inv, (p["X"], p["Y"]))
            dx, dy = qx - p["sx"], qy - p["sy"]
            r = math.hypot(dx, dy)
        lineas.append(",".join(repr(float(v)) for v in (p["X"], p["Y"], p["sx"], p["sy"]))
                      + f",{1 if p['on'] else 0},{dx!r},{dy!r},{r!r}")
    texto = "\n".join(lineas) + "\n"
    if ruta.exists():
        try:
            if ruta.read_text(encoding="utf-8") == texto:
                return ruta
            shutil.copy2(ruta, ruta.with_name(ruta.name + ".bak"))
        except OSError:
            pass
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def leer_points(ruta) -> list:
    """Los pares de un .points de QGIS (también los viejos, separados por
    espacios o tabuladores, sin «enable»)."""
    pares = []
    for linea in Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines():
        t = linea.strip()
        if not t or t.startswith("#") or t.lower().startswith("mapx"):
            continue
        campos = [c for c in t.replace("\t", ",").replace(" ", ",").split(",") if c != ""]
        try:
            X, Y, sx, sy = (float(v) for v in campos[:4])
        except ValueError:
            continue
        on = True
        if len(campos) > 4:
            try:
                on = bool(int(float(campos[4])))
            except ValueError:
                on = True
        pares.append({"sx": sx, "sy": sy, "X": X, "Y": Y, "on": on})
    return pares


def crs_dibujo() -> str:
    """El sistema de coordenadas del proyecto (GeoCAD > Opciones), o ""."""
    try:
        from . import config

        return str(config.get("crs_proyecto") or "")
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------- archivo de mundo y copia (3.18.1)
#: extensión del archivo de mundo según la de la imagen (la de ESRI / GDAL)
MUNDO = {".png": ".pgw", ".jpg": ".jgw", ".jpeg": ".jgw", ".tif": ".tfw", ".tiff": ".tfw",
         ".bmp": ".bpw", ".gif": ".gfw"}


def ruta_mundo(ruta) -> Path:
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    return ruta.with_suffix(MUNDO.get(ext, (ext[:2] + ext[-1:] + "w") if len(ext) >= 3 else ".wld"))


def texto_mundo(coef) -> str:
    """Las 6 líneas del archivo de mundo: tamaño del píxel en X, giro, giro,
    tamaño en Y (negativo), X e Y del CENTRO del píxel de arriba a la
    izquierda. Lineal, Helmert y Polinómica 1 entran exactos (giro y sesgo)."""
    a, b, c, d, e, f = coef
    x0, y0 = aplicar(coef, (0.5, -0.5))
    return "\n".join(repr(float(v)) for v in (b, e, -c, -f, x0, y0)) + "\n"


def _escribir(ruta: Path, texto: str) -> Path:
    """Escribe sin perder lo que había: si existía distinto, queda «.bak»."""
    if ruta.exists():
        try:
            if ruta.read_text(encoding="utf-8") == texto:
                return ruta
            shutil.copy2(ruta, ruta.with_name(ruta.name + ".bak"))
        except OSError:
            pass
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def wkt(crs: str) -> str:
    try:
        import pyproj

        return pyproj.CRS.from_user_input(crs).to_wkt()
    except Exception:  # noqa: BLE001 -- sin pyproj o un código raro: sin sistema
        return ""


def escribir_mundo(ruta_imagen, coef, crs: str = "") -> list:
    """El archivo de mundo junto a la imagen y, si hay sistema de
    coordenadas, «<imagen>.aux.xml» con él (lo lee GDAL, y así QGIS). Un
    .aux.xml que ya estaba no se toca. Devuelve lo escrito."""
    ruta_imagen = Path(ruta_imagen)
    hechos = [_escribir(ruta_mundo(ruta_imagen), texto_mundo(coef))]
    texto = wkt(crs) if crs else ""
    aux = ruta_imagen.with_name(ruta_imagen.name + ".aux.xml")
    if texto and not aux.exists():
        from xml.sax.saxutils import escape

        aux.write_text("<PAMDataset>\n  <SRS dataAxisToSRSAxisMapping=\"1,2\">"
                       f"{escape(texto)}</SRS>\n</PAMDataset>\n", encoding="utf-8")
        hechos.append(aux)
    return hechos


def nombre_copia(ruta, ext=None) -> Path:
    """«plano_georref.png» (o _georref2, 3...): nunca pisa nada, ni la
    imagen ni su archivo de mundo, puntos o .aux.xml. ``ext``: otra
    extensión (la imagen rehecha con fondo transparente es PNG)."""
    ruta = Path(ruta)
    ext = ext or ruta.suffix
    for i in range(1, 1000):
        nueva = ruta.with_name(f"{ruta.stem}{SUFIJO_COPIA}{i if i > 1 else ''}{ext}")
        vecinos = (nueva, ruta_mundo(nueva), nueva.with_name(nueva.name + ".points"),
                   nueva.with_name(nueva.name + ".aux.xml"))
        if not any(v.exists() for v in vecinos):
            return nueva
    raise OSError("demasiadas copias ajustadas de esta imagen")


def destino_copia(elegida, original) -> Path:
    """La ruta elegida con «Guardar copia geo como...», con la extensión de
    la original (los mismos bytes con otra extensión confundirían a QGIS).
    Nunca la original misma."""
    elegida, original = Path(elegida).expanduser(), Path(original)
    if elegida.suffix.lower() != original.suffix.lower():
        elegida = elegida.with_name(elegida.name + original.suffix)
    if elegida.resolve() == original.resolve():
        raise OSError("la copia no puede ser la imagen original")
    if not elegida.parent.is_dir():
        raise OSError(f"no existe la carpeta {elegida.parent}")
    return elegida


def nombre_en_dibujo(copia, guardado, original) -> str:
    """Cómo queda escrita la copia en el dibujo: relativa (como estaba la
    original) si está en la misma carpeta; si no, la ruta completa."""
    guardado = Path(guardado)
    if not guardado.is_absolute() and Path(copia).parent.resolve() == Path(original).parent.resolve():
        return str(guardado.with_name(Path(copia).name))
    return str(copia)


def _recargar_pixeles(handle) -> None:
    """IngeCAD guarda la textura de cada IMAGE y, cuando la IMAGE cambia,
    sólo corre las 4 esquinas de esa textura (nunca vuelve a leer el
    archivo): con la imagen rehecha se veía la ORIGINAL, sin deformar, con
    el tamaño de píxel nuevo. Después del comando (y de cada U o rehacer):
    se oculta la textura vieja y se regenera, que lee el archivo nuevo. Sin
    ventana (pruebas), nada."""
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    def hacer():
        for w in app.topLevelWidgets():
            vp = getattr(w, "viewport", None)
            if vp is None or not hasattr(w, "regen_in_memory"):
                continue
            try:
                vp.hide_handles([handle])
            except Exception:  # noqa: BLE001
                pass
            (getattr(w, "regen_in_background", None) or w.regen_in_memory)()

    # después de que IngeCAD termine con el comando: él vuelve a mostrar la
    # textura vieja al correr sus esquinas
    QtCore.QTimer.singleShot(0, hacer)


class GeorrefCommand(actions.TransformCommand):
    """La imagen a su lugar y, con copia, apuntando al archivo nuevo. Es un
    TransformCommand: IngeCAD la redibuja al instante y un solo U deshace
    las dos cosas (el archivo copiado queda en el disco). Con ``tamano``
    (imagen rehecha, 3.21.0) cambia además su tamaño en píxeles y su recorte
    vuelve al rectángulo entero; U devuelve los dos."""

    def __init__(self, img, matrix, copia=None, tamano=None, transparente=False) -> None:
        super().__init__("GEORREF", [img], matrix)
        self.img = img
        self.copia = copia                   # nombre a guardar en el IMAGEDEF nuevo
        self.tamano = tamano
        self.transparente = transparente     # imagen rehecha con fondo transparente
        self._def_antes = img.image_def
        self._def_nuevo = None
        self._tam_antes = None

    def _cambiar_tamano(self) -> None:
        img = self.img
        d = img.dxf
        self._tam_antes = (tuple(d.image_size), list(img.boundary_path), d.get("flags", 0),
                           d.get("clipping", 0), d.get("clipping_boundary_type", 1),
                           d.get("count_boundary_points", 2))
        d.image_size = (float(self.tamano[0]), float(self.tamano[1]))
        img.reset_boundary_path()
        if self.transparente:
            # sin la marca «usar transparencia» el alfa no cuenta y el fondo se ve negro
            img.set_flag_state(img.USE_TRANSPARENCY, state=True)

    def _devolver_tamano(self) -> None:
        if self._tam_antes is None:
            return
        img = self.img
        size, borde, flags, clip, tipo, cuenta = self._tam_antes
        img.dxf.image_size = size
        img._boundary_path = list(borde)
        img.dxf.flags = flags
        img.dxf.clipping = clip
        img.dxf.clipping_boundary_type = tipo
        img.dxf.count_boundary_points = cuenta
        self._tam_antes = None

    def _apuntar(self, imagedef) -> None:
        img = self.img
        reactor = img.image_def_reactor
        viejo = img.image_def
        if reactor is not None and viejo is not None and viejo is not imagedef:
            viejo.discard_reactor_handle(reactor.dxf.handle)
            imagedef.append_reactor_handle(reactor.dxf.handle)
        img.image_def = imagedef

    def do(self, document) -> None:
        super().do(document)
        if self.tamano is not None and self.entities:
            self._cambiar_tamano()
        if self.copia is not None and self.entities:
            if self._def_nuevo is None:
                w, h = tamano(self.img)
                self._def_nuevo = document.doc.add_image_def(
                    filename=str(self.copia), size_in_pixel=(int(w), int(h)))
            self._apuntar(self._def_nuevo)
        if self.tamano is not None and self.entities:
            _recargar_pixeles(self.img.dxf.handle)

    def undo(self, document) -> None:
        if self.copia is not None and self._def_antes is not None:
            self._apuntar(self._def_antes)
        self._devolver_tamano()
        super().undo(document)
        if self.tamano is not None and self.entities:
            _recargar_pixeles(self.img.dxf.handle)


# ------------------------------------------------------------- la tabla
def filas_tabla(pares, metodo: str) -> dict:
    """Lo que muestra la tabla: cada fila con sus residuos (si se puede
    calcular), el error medio y el motivo si no se puede."""
    hab = [p for p in pares if p["on"]]
    coef, motivo = None, ""
    try:
        coef = ajustar(metodo, [(p["sx"], p["sy"]) for p in hab],
                       [(p["X"], p["Y"]) for p in hab])
    except AjusteError as exc:
        motivo = str(exc)
    filas = []
    res = residuos(coef, [(p["sx"], p["sy"]) for p in pares],
                   [(p["X"], p["Y"]) for p in pares]) if coef else [None] * len(pares)
    for i, (p, r) in enumerate(zip(pares, res), 1):
        filas.append({"id": i, "on": p["on"], "sx": p["sx"], "sy": p["sy"],
                      "X": p["X"], "Y": p["Y"],
                      "dX": r[0] if r else None, "dY": r[1] if r else None,
                      "residuo": r[2] if r else None})
    rms = error_medio(res, [p["on"] for p in pares]) if coef else None
    return {"filas": filas, "coef": coef, "rms": rms, "motivo": motivo}


def texto_tabla(pares, metodo: str) -> list:
    """La tabla en líneas de texto (para la línea de comandos)."""
    t = filas_tabla(pares, metodo)
    out = [f"Tabla de puntos — método {METODOS[metodo][0]}:",
           "  On  ID   X origen    Y origen     X destino      Y destino        dX        dY   Residuo"]
    for f in t["filas"]:
        res = ("" if f["dX"] is None else
               f"{f['dX']:>10.4f}{f['dY']:>10.4f}{f['residuo']:>10.4f}")
        out.append(f"  {'sí' if f['on'] else 'no':>2}{f['id']:>4}{f['sx']:>11.2f}{f['sy']:>12.2f}"
                   f"{f['X']:>15.4f}{f['Y']:>15.4f}{res}")
    if t["coef"] is None:
        out.append("  " + t["motivo"])
    else:
        out.append(f"  Error medio: {_fmt(t['rms'])} · {describir(t['coef'])}")
    return out


def _metodo_de_texto(t: str):
    t = t.upper().replace(" ", "").replace("Ó", "O")
    if t in ("L", "LINEAL", "LINEAR"):
        return "lineal"
    if t in ("H", "HELMERT"):
        return "helmert"
    if t in ("P", "P1", "POL1", "POLINOMICA", "POLINOMICA1", "POLYNOMIAL1"):
        return "polinomica1"
    if t in ("P2", "POL2", "POLINOMICA2", "POLYNOMIAL2"):
        return "polinomica2"
    if t in ("P3", "POL3", "POLINOMICA3", "POLYNOMIAL3"):
        return "polinomica3"
    if t in ("TPS", "THINPLATESPLINE", "SPLINE"):
        return "tps"
    if t in ("PR", "PROYECTIVA", "PROJECTIVE"):
        return "proyectiva"
    return None


def _remuestreo_de_texto(t: str):
    t = t.upper().replace("Ú", "U")
    return {"VECINO": "vecino", "BILINEAL": "lineal", "CUBICA": "cubica"}.get(t)


# ------------------------------------------------------------- la orden
class GeorrefTool(Tool):
    """GEORREF: una imagen, pares de puntos (origen -> destino) con
    referencias, la tabla de puntos y Transformar."""

    entity_picker = True
    #: referencias que se suman mientras se marcan los pares
    REFERENCIAS = frozenset({"END", "MID", "INT", "NOD", "CEN"})
    PEDIDO_IMAGEN = ("Designe UNA imagen a ajustar (imágenes y vectores no se mezclan; "
                     "clic en la imagen o en su borde):")
    PEDIDO_TABLA = ("Tabla de puntos [Lineal/Helmert/Polinómica1/P2/P3/TPS/PRoyectiva/Apagar n/"
                    "Guardar/Marcar más/COPIA/COMO/MUNDO/DIBUJO/VECINO/BILINEAL/CÚBICA/"
                    "TRANSPARENTE/BLANCO/AMBOS/Transformar] <Transformar>:")

    def start(self) -> None:
        self.name = "GEORREF"
        self._img = None
        self._pares = []                  # {sx, sy, X, Y, on}
        self._pendiente = None            # punto de origen sin su destino (dibujo)
        self._tabla = False               # en la tabla (línea de comandos)
        self._metodo = _ultimo_metodo[0]
        self._salida = _ultima_salida[0]
        self._remuestreo = _ultimo_remuestreo[0]
        self._fondo = _ultimo_fondo[0]
        self._copia_en = None             # «Guardar copia geo como...»: dónde
        self.entity_picker = True
        s = self.ctx.services
        previa = list(getattr(s, "selection", None) or ())
        if previa:
            ents = [e for h in previa if (e := self._entidad(h)) is not None]
            imgs = [e for e in ents if e.dxftype() == "IMAGE"]
            if s is not None:
                s.selection = set()
            if len(imgs) == 1:
                otros = len(ents) - 1
                if otros:
                    self.ctx.echo(f"GeoCAD Yaguareté: imágenes y vectores no se mezclan; "
                                  f"se ajusta la imagen y quedan afuera {otros} objeto(s).")
                self._elegir(imgs[0])
                return
            if len(imgs) > 1:
                self.ctx.echo(f"GeoCAD Yaguareté: hay {len(imgs)} imágenes elegidas; "
                              "se ajustan de a una.")
        self.prompt(self.PEDIDO_IMAGEN)

    # -- ayudas -----------------------------------------------------------------
    def _documento(self):
        return getattr(getattr(self.ctx.services, "window", None), "document", None)

    def _entidad(self, handle):
        doc = self._documento()
        if doc is None:
            return None
        e = doc.doc.entitydb.get(handle)
        return e if e is not None and e.is_alive else None

    def _imagen_en(self, p):
        """La imagen bajo el punto: la que toma el clic (su borde) o, si no,
        la de más arriba que lo contiene."""
        s = self.ctx.services
        e = s.pick_entity(p) if s is not None else None
        if e is not None and e.dxftype() == "IMAGE":
            return e, None
        doc = self._documento()
        if doc is not None:
            imgs = [i for i in doc.doc.modelspace().query("IMAGE") if dentro(i, p)]
            if imgs:
                return imgs[-1], None
        return None, e

    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._img is not None and not self._tabla else frozenset()

    def _n(self) -> int:
        return len(self._pares) + 1

    def _pedir_par(self) -> None:
        if self._pendiente is None:
            self.prompt(f"Punto en la imagen {self._n()} [Cargar puntos/Deshacer] "
                        "<Enter: tabla de puntos>:")
        else:
            self.prompt(f"Punto de destino {self._n()} [Deshacer]:")

    def _elegir(self, img) -> None:
        self._img = img
        self.entity_picker = False         # los pares, con referencias
        w, h = tamano(img)
        doc = self._documento()
        f = archivo_imagen(img, doc)
        self.ctx.echo(f"Imagen: {f.name if f else '(sin archivo)'} ({int(w)} x {int(h)} píxeles).")
        r = ruta_points(img, doc)
        if r is not None and r.exists():
            try:
                n = len(leer_points(r))
            except OSError:
                n = 0
            if n:
                self.ctx.echo(f"Hay {n} puntos guardados en {r.name}: C (Cargar puntos) los trae.")
        self._pedir_par()

    # -- entrada -------------------------------------------------------------------
    def on_point(self, point) -> None:
        if self._tabla:
            return
        p = (float(point[0]), float(point[1]))
        if self._img is None:
            img, otro = self._imagen_en(p)
            if img is None:
                if otro is not None:
                    self.ctx.echo(f"GeoCAD Yaguareté: {otro.dxftype()} no es una imagen. "
                                  "Por ahora GEORREF ajusta imágenes; los vectores llegan más adelante.")
                self.prompt(self.PEDIDO_IMAGEN)
                return
            self._elegir(img)
            return
        if not self._img.is_alive:
            self.ctx.echo("La imagen ya no está en el dibujo.")
            self.ctx.finish()
            return
        if self._pendiente is None:
            self._pendiente = p
            self.last_point = p
            self._pedir_par()
            return
        sx, sy = mundo_a_pixel(self._img, self._pendiente)
        self._pares.append({"sx": sx, "sy": sy, "X": p[0], "Y": p[1], "on": True})
        self._pendiente = None
        self.last_point = p
        self.ctx.echo(self._resumen())
        self._pedir_par()

    def _resumen(self) -> str:
        hab = [x for x in self._pares if x["on"]]
        nombre, minimo, _d = METODOS[self._metodo]
        if len(hab) < minimo:
            return f"{len(self._pares)} par(es). {nombre} necesita {minimo}."
        t = filas_tabla(self._pares, self._metodo)
        if t["coef"] is None:
            return f"{len(self._pares)} par(es). {t['motivo']}"
        return (f"{len(self._pares)} par(es). {nombre}: error medio {_fmt(t['rms'])}. "
                "Enter abre la tabla de puntos.")

    def on_option(self, text: str) -> bool:
        t = text.strip().upper().lstrip("_")
        if self._img is None:
            return False
        if self._tabla:
            return self._opcion_tabla(t)
        if t in ("U", "D", "DESHACER", "UNDO"):
            if self._pendiente is not None:
                self._pendiente = None
                self.ctx.echo("Se quitó el punto en la imagen sin destino.")
            elif self._pares:
                self._pares.pop()
                self.ctx.echo(f"Se quitó el par {len(self._pares) + 1}.")
            else:
                self.ctx.echo("No hay pares para quitar.")
            self._pedir_par()
            return True
        if t in ("C", "CARGAR", "CARGARPUNTOS", "LOAD") and self._pendiente is None:
            self._cargar()
            self._pedir_par()
            return True
        return False

    def _cargar(self, ruta=None) -> bool:
        ruta = ruta or ruta_points(self._img, self._documento())
        if ruta is None or not Path(ruta).exists():
            self.ctx.echo("No hay archivo de puntos junto a la imagen.")
            return False
        try:
            pares = leer_points(ruta)
        except OSError as exc:
            self.ctx.echo(f"No se pudo leer {Path(ruta).name}: {exc}")
            return False
        self._pares = pares
        self.ctx.echo(f"Cargados {len(pares)} pares de {Path(ruta).name}.")
        return True

    def on_enter(self) -> None:
        if self._img is None:
            self.ctx.finish()
            return
        if self._tabla:
            self._transformar()
            return
        if self._pendiente is not None:
            self.ctx.echo("Falta el punto de destino de ese par (U lo quita).")
            self._pedir_par()
            return
        if not self._pares:
            self.ctx.finish()
            return
        self._abrir_tabla()

    def on_cancel(self) -> None:
        if self._img is not None:
            self.ctx.echo("GEORREF cancelado: la imagen queda como estaba.")
        self.ctx.finish()

    # -- la tabla ------------------------------------------------------------------
    def _abrir_tabla(self) -> None:
        from . import georref_ui

        r = georref_ui.tabla(getattr(self.ctx.services, "window", None), self)
        if r is georref_ui.SIN_QT:
            self._tabla = True
            self._mostrar_tabla()
            return
        if r is None:
            self.on_cancel()
            return
        self._metodo = r.get("metodo", self._metodo)
        _ultimo_metodo[0] = self._metodo
        self._salida = _ultima_salida[0] = r.get("salida", self._salida)
        self._remuestreo = _ultimo_remuestreo[0] = r.get("remuestreo", self._remuestreo)
        self._fondo = _ultimo_fondo[0] = r.get("fondo", self._fondo)
        if r.get("copia_en"):
            self._copia_en = Path(r["copia_en"])
        for p, on in zip(self._pares, r.get("habilitados", ())):
            p["on"] = bool(on)
        if r.get("pares") is not None:          # cargados desde la tabla
            self._pares = r["pares"]
        accion = r.get("accion")
        if accion == "transformar":
            self._transformar()
        else:                                    # marcar más pares
            self._pedir_par()

    def _opcion_tabla(self, t: str) -> bool:
        m = _metodo_de_texto(t)
        if m is not None:
            self._metodo = _ultimo_metodo[0] = m
        elif (rm := _remuestreo_de_texto(t)) is not None:
            self._remuestreo = _ultimo_remuestreo[0] = rm
        elif t.lower() in FONDOS:
            self._fondo = _ultimo_fondo[0] = t.lower()
        elif (num := re.fullmatch(r"(?:A|APAGAR|E|ENCENDER)\s*(\d+)", t)) is not None:
            i = int(num.group(1)) - 1               # A3 / APAGAR 3 / E3: apaga o prende el 3
            if not 0 <= i < len(self._pares):
                self.ctx.echo(f"No hay punto {i + 1}.")
            else:
                self._pares[i]["on"] = not self._pares[i]["on"]
        elif t in ("G", "GUARDAR", "SAVE"):
            self._guardar()
        elif t in ("COPIA", "MUNDO", "DIBUJO"):
            self._salida = _ultima_salida[0] = t.lower()
        elif t in ("COMO", "CÓMO", "GUARDARCOMO", "COPIACOMO"):
            orig = archivo_imagen(self._img, self._documento())
            inicio = str(self._copia_en or (nombre_copia(orig) if orig else ""))
            texto = self.ctx.ask_text("Guardar copia geo como (carpeta y nombre):", inicio)
            if texto:
                self._copia_en = Path(texto.strip())
                self._salida = _ultima_salida[0] = "copia"
        elif t in ("M", "MARCAR", "MARCARMAS", "MARCARMÁS"):
            self._tabla = False
            self._pedir_par()
            return True
        elif t in ("T", "TRANSFORMAR"):
            self._transformar()
            return True
        else:
            return False
        self._mostrar_tabla()
        return True

    def _mostrar_tabla(self) -> None:
        for linea in texto_tabla(self._pares, self._metodo):
            self.ctx.echo(linea)
        if self._metodo in REHACEN:
            self.ctx.echo(f"  {METODOS[self._metodo][0]} deforma la imagen: se rehace en una copia "
                          f"(remuestreo {REMUESTREOS[self._remuestreo]}; fondo "
                          f"{FONDOS[self._fondo][0].lower() + FONDOS[self._fondo][1:]}).")
        else:
            self.ctx.echo(f"  Al transformar se guarda: {SALIDAS[self._salida]}.")
        if (self._salida == "copia" or self._metodo in REHACEN) and self._copia_en is not None:
            self.ctx.echo(f"  Copia geo en: {self._copia_en}")
        self.prompt(self.PEDIDO_TABLA)

    def _guardar(self, ruta=None):
        ruta = ruta or ruta_points(self._img, self._documento())
        if ruta is None:
            self.ctx.echo("La imagen no tiene archivo: no se pueden guardar los puntos.")
            return None
        try:
            r = escribir_points(ruta, self._pares, crs_dibujo(), self._metodo)
        except OSError as exc:
            self.ctx.echo(f"No se pudieron guardar los puntos en {ruta}: {exc}")
            return None
        self.ctx.echo(f"Puntos guardados en {r} (se abren en el Georreferenciador de QGIS).")
        return r

    def _transformar(self) -> None:
        img = self._img
        if img is None or not img.is_alive:
            self.ctx.echo("La imagen ya no está en el dibujo.")
            self.ctx.finish()
            return
        t = filas_tabla(self._pares, self._metodo)
        if t["coef"] is None:
            self.ctx.echo("No se puede transformar: " + t["motivo"])
            if self._tabla:
                self.prompt(self.PEDIDO_TABLA)
            else:
                self._abrir_tabla()
            return
        coef = t["coef"]
        original = archivo_imagen(img, self._documento())
        if self._metodo in REHACEN:
            self._rehacer(img, coef, original, t["rms"])
            return
        salida = self._salida
        if salida != "dibujo" and (original is None or not original.exists()):
            self.ctx.echo("GeoCAD Yaguareté: no se encuentra el archivo de la imagen; "
                          "se ajusta sólo en el dibujo.")
            salida = "dibujo"
        copia = guardar_como = None
        if salida == "copia":
            try:
                copia = (destino_copia(self._copia_en, original) if self._copia_en is not None
                         else nombre_copia(original))
                shutil.copy2(original, copia)
                from .imagengeo import ruta_real

                copia = Path(ruta_real(copia))
            except OSError as exc:
                self.ctx.echo(f"GeoCAD Yaguareté: no se pudo copiar la imagen ({exc}); "
                              "se ajusta sólo en el dibujo.")
                copia, salida = None, "dibujo"
            else:
                guardar_como = nombre_en_dibujo(copia, img.image_def.dxf.filename, original)
        cmd = GeorrefCommand(img, matriz(img, coef), guardar_como)
        if not cmd.entities:
            self.ctx.echo("GeoCAD Yaguareté: IngeCAD no puede mover esta imagen.")
            if copia is not None:
                copia.unlink(missing_ok=True)
            self.ctx.finish()
            return
        self.ctx.execute(cmd)
        n = sum(1 for p in self._pares if p["on"])
        self.ctx.echo(f"Imagen ajustada con {METODOS[self._metodo][0]}: {n} puntos, error medio "
                      f"{_fmt(t['rms'])} ({describir(coef)}). U la vuelve a como estaba.")
        if salida != "dibujo":
            destino = copia if salida == "copia" else original
            try:
                hechos = escribir_mundo(destino, coef, crs_dibujo())
            except OSError as exc:
                self.ctx.echo(f"No se pudo escribir el archivo de mundo: {exc}")
            else:
                extra = " y " .join(h.name for h in hechos)
                if salida == "copia":
                    self.ctx.echo(f"Copia ajustada: {copia} ({extra}); el dibujo usa la copia y "
                                  f"{original.name} queda como estaba. QGIS la abre en su lugar.")
                else:
                    self.ctx.echo(f"Archivo de mundo junto a la original: {extra}. "
                                  "QGIS la abre en su lugar.")
        self._guardar()
        self.ctx.finish()

    def _rehacer(self, img, modelo, original, rms) -> None:
        """Proyectiva, Polinómica 2-3, TPS: la imagen nueva (una o dos, según
        el fondo), su archivo de mundo, y el dibujo pasa a usarla."""
        import time

        from . import georref_imagen as GI
        from . import georref_progreso as GP

        nombre = METODOS[self._metodo][0]
        ventana = getattr(self.ctx.services, "window", None)
        if original is None or not original.exists():
            self.ctx.echo(f"GeoCAD Yaguareté: no se encuentra el archivo de la imagen; {nombre} "
                          "necesita rehacerla. Elegí Lineal, Helmert o Polinómica 1.")
            self._volver_a_tabla()
            return
        w, h = tamano(img)
        mp = w * h / 1e6
        with GP.Progreso(ventana, "GEORREF") as prog:
            try:
                salidas = GI.rutas(original, self._fondo, self._copia_en)
                self.ctx.echo(f"Rehaciendo la imagen con {nombre}...")
                t0 = time.monotonic()
                coef, tam = prog.trabajo(
                    f"1/2  Rehaciendo la imagen con {nombre}",
                    lambda: GI.rehacer(original, salidas, modelo, self._remuestreo),
                    GP.estimar(mp, len(salidas)))
                GP.medir(tam[0] * tam[1] / 1e6, len(salidas), time.monotonic() - t0)
            except (OSError, AjusteError, ValueError) as exc:
                self.ctx.echo(f"GeoCAD Yaguareté: no se pudo rehacer la imagen ({exc}).")
                prog.cerrar()
                self._volver_a_tabla()
                return
            self._colocar(img, coef, tam, salidas, original, nombre, rms, prog, ventana)

    def _colocar(self, img, coef, tam, salidas, original, nombre, rms, prog, ventana) -> None:
        """La imagen rehecha en el dibujo (un solo U) y la pantalla al día."""
        usada = salidas[0][0]
        cmd = GeorrefCommand(img, matriz(img, coef, tam[1]),
                             nombre_en_dibujo(usada, img.image_def.dxf.filename, original), tam,
                             transparente=salidas[0][1] == "transparente")
        if not cmd.entities:
            self.ctx.echo("GeoCAD Yaguareté: IngeCAD no puede mover esta imagen.")
            self.ctx.finish()
            return
        self.ctx.execute(cmd)
        prog.regeneracion(ventana, img.dxf.handle)
        n = sum(1 for p in self._pares if p["on"])
        self.ctx.echo(f"Imagen rehecha con {nombre}: {n} puntos, error medio {_fmt(rms)}, "
                      f"{tam[0]} x {tam[1]} píxeles. U la vuelve a como estaba.")
        crs = crs_dibujo()
        for ruta, fondo in salidas:
            try:
                hechos = escribir_mundo(ruta, coef, crs)
            except OSError as exc:
                self.ctx.echo(f"No se pudo escribir el archivo de mundo de {ruta.name}: {exc}")
                continue
            uso = "la usa el dibujo" if ruta == usada else "otra copia"
            self.ctx.echo(f"  {ruta} (fondo {fondo}; {uso}) y {' y '.join(h.name for h in hechos)}.")
        self.ctx.echo(f"{original.name} queda como estaba. QGIS abre la copia en su lugar.")
        self._guardar()
        self.ctx.finish()

    def _volver_a_tabla(self) -> None:
        if self._tabla:
            self.prompt(self.PEDIDO_TABLA)
        else:
            self._abrir_tabla()

    # -- resaltado (lo dibuja dibujo.py) ---------------------------------------
    def _flecha(self, a, b, punta) -> list:
        segs = [(a, b)]
        L = math.dist(a, b)
        if L <= EPS:
            return segs
        k = min(punta, 0.35 * L) / L
        dx, dy = (b[0] - a[0]) * k, (b[1] - a[1]) * k
        for s in (1, -1):                         # dos rayitas a ±25°
            c, si = math.cos(math.radians(25)), s * math.sin(math.radians(25))
            segs.append((b, (b[0] - (dx * c - dy * si), b[1] - (dx * si + dy * c))))
        return segs

    def resaltado(self, cursor) -> dict:
        """Antes de elegir: la imagen bajo el cursor. Después: su marco, las
        flechas numeradas de cada par (apagadas, punteadas), el par a medio
        marcar hasta el cursor y, punteado, dónde quedaría la imagen."""
        out = {"cursor": [], "elegido": [], "vista": [], "flecha": [], "flecha_off": [],
               "puntos": [], "textos": []}
        img = self._img
        if img is None:
            if cursor is not None:
                i, _o = self._imagen_en(tuple(cursor))
                if i is not None:
                    out["cursor"] = marco(esquinas(i))
            return out
        if not img.is_alive:
            return out
        caja = esquinas(img)
        out["elegido"] = marco(caja)
        diag = math.dist(caja[0], caja[2])
        punta = 0.02 * diag
        for i, p in enumerate(self._pares, 1):
            a = pixel_a_mundo(img, (p["sx"], p["sy"]))
            b = (p["X"], p["Y"])
            out["flecha" if p["on"] else "flecha_off"] += self._flecha(a, b, punta)
            out["puntos"].append(a)
            out["textos"].append((a, str(i)))
        pares = list(self._pares)
        if self._pendiente is not None:
            out["puntos"].append(self._pendiente)
            out["textos"].append((self._pendiente, str(self._n())))
            if cursor is not None:
                c = (float(cursor[0]), float(cursor[1]))
                out["flecha"] += self._flecha(self._pendiente, c, punta)
                sx, sy = mundo_a_pixel(img, self._pendiente)
                pares.append({"sx": sx, "sy": sy, "X": c[0], "Y": c[1], "on": True})
        hab = [p for p in pares if p["on"]]
        if len(hab) >= METODOS[self._metodo][1]:
            try:
                coef = ajustar(self._metodo, [(p["sx"], p["sy"]) for p in hab],
                               [(p["X"], p["Y"]) for p in hab])
                out["vista"] = marco(esquinas(img, coef))
            except (AjusteError, ZeroDivisionError):
                pass
        return out


def activo() -> bool:
    return modulos.activo(PROGRAMA, "georref")
