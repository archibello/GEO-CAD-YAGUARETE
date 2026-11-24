# SPDX-License-Identifier: GPL-3.0-or-later
"""GEORREF: rehacer la imagen deformada sin PIL, con numpy (núcleo, 3.93.0).

Lo de georref_imagen.py de IngeCAD (3.21.0) para el GEORREF de QGIS, cuyo
Python no trae PIL. La imagen nueva queda derecha (norte arriba), con el
mismo tamaño de píxel en promedio, y cada píxel nuevo busca su color en la
original con la vuelta del ajuste (dibujo -> píxel):

  Proyectiva          exacta, píxel por píxel (lo de PERSPECTIVE de PIL);
  Polinómica 2-3/TPS  una malla de celdas de MALLA píxeles, cada celda con
                      interpolación bilineal de sus esquinas (lo de MESH de
                      PIL), como el transformador aproximado de GDAL.

Remuestreo Vecino / Lineal / Cúbica (la de transform() de PIL, a = −1). Fuera de la
imagen deformada: transparente; después se recorta justo a lo que tiene
contenido, y lo que ya era transparente en la original sigue transparente.
"""
from __future__ import annotations

import math

from . import georref_cuentas as G

#: lado de cada celda de la malla (píxeles de la imagen nueva)
MALLA = 32
#: la imagen nueva no puede pasar de tantas veces los píxeles de la original
MAX_CRECIMIENTO = 6
#: filas de la imagen nueva por tanda (memoria acotada con planos grandes)
FILAS = 256
COLOR_FONDO = {"transparente": (255, 255, 255), "blanco": (255, 255, 255), "negro": (0, 0, 0)}


class RehacerError(G.AjusteError):
    """No se puede rehacer la imagen."""


def marco_nuevo(modelo, ancho, alto):
    """(minX, maxY, píxel, ancho, alto) de la imagen nueva, derecha (como IngeCAD)."""
    if isinstance(modelo, G.Proyectiva):
        signos = {modelo.denominador(p) > 0 for p in G.borde_pixeles(ancho, alto)}
        if len(signos) > 1:
            raise RehacerError("con estos puntos la imagen se daría vuelta (pasa por el "
                               "horizonte): revisá el orden de los puntos")
    borde = [G.aplicar(modelo, s) for s in G.borde_pixeles(ancho, alto, modelo, 64)]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in G.marco(borde))) / 2
    if area <= G.EPS:
        raise RehacerError("con estos puntos la imagen quedaría aplastada")
    pix = math.sqrt(area / (ancho * alto))
    xs, ys = [p[0] for p in borde], [p[1] for p in borde]
    w = max(1, math.ceil((max(xs) - min(xs)) / pix))
    h = max(1, math.ceil((max(ys) - min(ys)) / pix))
    if w * h > MAX_CRECIMIENTO * ancho * alto:
        raise RehacerError(f"la imagen nueva quedaría de {w} x {h} píxeles (demasiado "
                           "deformada): revisá los puntos")
    return min(xs), max(ys), pix, w, h


def coef_nuevo(marco) -> tuple:
    """Los 6 coeficientes (píxel de QGIS -> dibujo) de la imagen nueva."""
    x0, y0, pix, _w, _h = marco
    return (x0, pix, 0.0, y0, 0.0, pix)


# ------------------------------------------------------------------ de la nueva a la original
def _perspectiva(modelo, marco):
    """La matriz 3x3: píxel (columna, fila) de la nueva -> píxel (columna, fila) de la original."""
    x0, y0, pix, _w, _h = marco
    O = [[pix, 0, x0], [0, -pix, y0], [0, 0, 1]]
    F = [[1, 0, 0], [0, -1, 0], [0, 0, 1]]
    return G._h_mult(F, G._h_mult(modelo.Hi, O))


def _nodos(modelo, marco):
    """Columnas y filas de la malla y dónde cae cada nodo en la original."""
    import numpy as np
    x0, y0, pix, w, h = marco
    cols = list(range(0, w, MALLA)) + [w]
    filas = list(range(0, h, MALLA)) + [h]
    nx = np.empty((len(filas), len(cols)))
    ny = np.empty_like(nx)
    for i, r in enumerate(filas):
        for j, c in enumerate(cols):
            try:
                sx, sy = modelo.inverso((x0 + pix * c, y0 - pix * r))
                nx[i, j], ny[i, j] = sx, -sy
            except (ZeroDivisionError, OverflowError):
                nx[i, j] = ny[i, j] = -1e9
    return np.array(cols, float), np.array(filas, float), nx, ny


def _a_original(cc, rr, modelo, marco, datos):
    """(x, y) continuos en la original (0 = borde izquierdo / de arriba) de los centros
    de píxel ``cc``, ``rr`` (arreglos) de la nueva."""
    import numpy as np
    if isinstance(modelo, G.Proyectiva):
        M = datos
        X = M[0][0] * cc + M[0][1] * rr + M[0][2]
        Y = M[1][0] * cc + M[1][1] * rr + M[1][2]
        Z = M[2][0] * cc + M[2][1] * rr + M[2][2]
        with np.errstate(divide="ignore", invalid="ignore"):
            return X / Z, Y / Z
    cols, filas, nx, ny = datos
    j = np.clip(np.searchsorted(cols, cc, side="right") - 1, 0, len(cols) - 2)
    i = np.clip(np.searchsorted(filas, rr, side="right") - 1, 0, len(filas) - 2)
    u = (cc - cols[j]) / (cols[j + 1] - cols[j])
    v = (rr - filas[i]) / (filas[i + 1] - filas[i])

    def bil(n):
        return (n[i, j] * (1 - u) * (1 - v) + n[i, j + 1] * u * (1 - v)
                + n[i + 1, j] * (1 - u) * v + n[i + 1, j + 1] * u * v)
    return bil(nx), bil(ny)


def _cubica(t):
    import numpy as np
    a = -1.0                                        # la de transform() de PIL
    t = np.abs(t)
    return np.where(t <= 1, (a + 2) * t ** 3 - (a + 3) * t ** 2 + 1,
                    np.where(t < 2, a * t ** 3 - 5 * a * t ** 2 + 8 * a * t - 4 * a, 0.0))


def _muestrear(src, x, y, remuestreo):
    """Los colores RGBA (float) de ``src`` en (x, y) continuos; fuera: transparente."""
    import numpy as np
    h, w = src.shape[:2]
    adentro = (x >= 0) & (x < w) & (y >= 0) & (y < h) & np.isfinite(x) & np.isfinite(y)
    x = np.where(adentro, x, 0.0)
    y = np.where(adentro, y, 0.0)
    if remuestreo == "vecino":
        out = src[np.clip(y.astype(int), 0, h - 1), np.clip(x.astype(int), 0, w - 1)].astype(np.float64)
    else:
        fx, fy = x - 0.5, y - 0.5
        ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - ix, fy - iy
        if remuestreo == "lineal":
            pesos_x = [(0, 1 - tx), (1, tx)]
            pesos_y = [(0, 1 - ty), (1, ty)]
        else:
            pesos_x = [(k, _cubica(tx - k)) for k in (-1, 0, 1, 2)]
            pesos_y = [(k, _cubica(ty - k)) for k in (-1, 0, 1, 2)]
        out = np.zeros(x.shape + (src.shape[2],))
        for ky, wy in pesos_y:
            yy = np.clip(iy + ky, 0, h - 1)
            fila = np.zeros_like(out)
            for kx, wx in pesos_x:
                xx = np.clip(ix + kx, 0, w - 1)
                fila += src[yy, xx] * wx[..., None]
            out += fila * wy[..., None]
    out[~adentro] = (255, 255, 255, 0)
    return out


def rehacer_arreglo(rgba, modelo, remuestreo="vecino", avance=None):
    """La imagen deformada (arreglo RGBA uint8, recortada a su contenido), sus
    coeficientes (píxel de QGIS -> dibujo) y su tamaño. ``avance(f)``: 0 a 1."""
    import numpy as np
    alto, ancho = rgba.shape[:2]
    marco = marco_nuevo(modelo, ancho, alto)
    w, h = marco[3], marco[4]
    datos = _perspectiva(modelo, marco) if isinstance(modelo, G.Proyectiva) else _nodos(modelo, marco)
    nueva = np.empty((h, w, 4), np.uint8)
    cc = np.arange(w, dtype=np.float64) + 0.5
    for r0 in range(0, h, FILAS):
        r1 = min(h, r0 + FILAS)
        C, R = np.meshgrid(cc, np.arange(r0, r1, dtype=np.float64) + 0.5)
        x, y = _a_original(C, R, modelo, marco, datos)
        nueva[r0:r1] = np.clip(np.rint(_muestrear(rgba, x, y, remuestreo)), 0, 255).astype(np.uint8)
        if avance is not None:
            avance(r1 / h)
    filas = np.nonzero(nueva[..., 3].any(axis=1))[0]
    cols = np.nonzero(nueva[..., 3].any(axis=0))[0]
    if not len(filas):
        raise RehacerError("la imagen quedaría vacía (es toda transparente)")
    arriba, abajo, izq, der = filas[0], filas[-1] + 1, cols[0], cols[-1] + 1
    x0, y0, pix, _w, _h = marco
    marco = (x0 + pix * izq, y0 - pix * arriba, pix, int(der - izq), int(abajo - arriba))
    return nueva[arriba:abajo, izq:der].copy(), coef_nuevo(marco), (marco[3], marco[4])


def con_fondo(nueva, fondo):
    """La imagen con su fondo: transparente queda RGBA; blanco o negro, pintado detrás."""
    import numpy as np
    if fondo == "transparente":
        return nueva
    a = nueva[..., 3:4].astype(np.float64) / 255.0
    out = nueva.copy()
    out[..., :3] = np.clip(np.rint(nueva[..., :3] * a + np.array(COLOR_FONDO[fondo]) * (1 - a)),
                           0, 255).astype(np.uint8)
    out[..., 3] = 255
    return out
