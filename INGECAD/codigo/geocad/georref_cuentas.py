# SPDX-License-Identifier: GPL-3.0-or-later
"""GEORREF: las cuentas, sin Qt ni ezdxf (núcleo, 3.93.0).

Las usan IngeCAD (georref.py) y QGIS (dibujo/georref_qgis.py): los mismos
métodos con los nombres del Georreferenciador de QGIS (Lineal, Helmert,
Polinómica 1-3, Thin Plate Spline, Proyectiva), los residuos y el error
medio, la tabla de puntos, el archivo «.points» de QGIS y el archivo de
mundo. Estaban en georref.py de IngeCAD (3.18.0 a 3.21.x). Python puro.

Píxel «de QGIS»: (columna, −fila), arriba a la izquierda = (0, 0), como los
.points del Georreferenciador.
"""
from __future__ import annotations

import math
import re  # noqa: F401
import shutil
from pathlib import Path


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
    "negro": "Negro (el mismo formato de la original)",
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


def texto_mundo(coef) -> str:
    """Las 6 líneas del archivo de mundo: tamaño del píxel en X, giro, giro,
    tamaño en Y (negativo), X e Y del CENTRO del píxel de arriba a la
    izquierda. Lineal, Helmert y Polinómica 1 entran exactos (giro y sesgo)."""
    a, b, c, d, e, f = coef
    x0, y0 = aplicar(coef, (0.5, -0.5))
    return "\n".join(repr(float(v)) for v in (b, e, -c, -f, x0, y0)) + "\n"


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
