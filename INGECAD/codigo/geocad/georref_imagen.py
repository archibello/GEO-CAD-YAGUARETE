# SPDX-License-Identifier: GPL-3.0-or-later
"""Rehacer la imagen para los métodos de GEORREF que la deforman (3.21.0):
Proyectiva, Polinómica 2-3 y Thin Plate Spline.

La IMAGE de IngeCAD sólo se mueve, escala, gira o sesga (un punto de
inserción y dos vectores): para deformarla hay que hacer una imagen nueva.
Se hace con PIL (viene con IngeCAD), como GDAL en el Georreferenciador de
QGIS: la imagen nueva queda derecha (norte arriba), con el mismo tamaño de
píxel en promedio, y cada píxel nuevo busca su color en la original con la
vuelta del ajuste (dibujo -> píxel):

  Proyectiva          exacta, píxel por píxel (PERSPECTIVE de PIL);
  Polinómica 2-3/TPS  una malla de celdas de MALLA píxeles (MESH de PIL),
                      como el transformador aproximado de GDAL.

Fuera de la imagen deformada, el fondo: transparente (PNG, o TIFF si la
original lo es) o blanco (el mismo formato de la original).
"""
from __future__ import annotations

import math
from pathlib import Path

from . import georref as G

#: lado de cada celda de la malla (píxeles de la imagen nueva)
MALLA = 32
#: la imagen nueva no puede pasar de tantas veces los píxeles de la original
#: (una Proyectiva casi al horizonte la haría enorme)
MAX_CRECIMIENTO = 6


class RehacerError(G.AjusteError):
    """No se puede rehacer la imagen (falta PIL, el archivo, o quedaría rara)."""


def _pil():
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        raise RehacerError("falta PIL (Pillow) para rehacer la imagen") from exc
    return Image


def extension(original, fondo: str) -> str:
    """La extensión de la imagen rehecha: transparente -> .png (o .tif si la
    original es TIFF); blanco -> la de la original."""
    suf = Path(original).suffix.lower()
    if fondo == "transparente":
        return Path(original).suffix if suf in (".tif", ".tiff", ".png") else ".png"
    return Path(original).suffix


def rutas(original, fondo: str, elegida=None) -> list:
    """[(ruta, fondo), ...] de las imágenes a hacer; la primera es la que usa
    el dibujo. Sin ``elegida`` (Guardar copia geo como...), nombres que no
    pisan nada (plano_georref.png, plano_georref2.png...)."""
    original = Path(original)
    fondos = ("transparente", "blanco") if fondo == "ambos" else (fondo,)
    out = []
    for f in fondos:
        ext = extension(original, f)
        if elegida is not None:
            base = Path(elegida).expanduser()
            r = base.with_name(base.stem + ext) if base.suffix else base.with_name(base.name + ext)
        else:
            r = G.nombre_copia(original, ext)
        if any(r == o for o, _f in out):           # los dos con la misma extensión
            r = (r.with_name(f"{r.stem}_blanco{r.suffix}") if elegida is not None
                 else G.nombre_copia(original.with_name(original.stem + "_blanco" + original.suffix), ext))
        if r.resolve() == original.resolve():
            raise RehacerError("la copia no puede ser la imagen original")
        if not r.parent.is_dir():
            raise RehacerError(f"no existe la carpeta {r.parent}")
        out.append((r, f))
    return out


def marco_nuevo(modelo, ancho, alto):
    """Dónde queda la imagen deformada y con qué píxel: (minX, maxY, píxel,
    ancho, alto) de la imagen nueva, derecha. El píxel: el tamaño medio con
    que queda la original (raíz del área sobre la cantidad de píxeles)."""
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


def _a_original(modelo, marco):
    """Píxel de PIL de la nueva (columna, fila) -> píxel de PIL de la original."""
    x0, y0, pix, _w, _h = marco

    def f(c, r):
        sx, sy = modelo.inverso((x0 + pix * c, y0 - pix * r))
        return sx, -sy
    return f


def _datos_perspectiva(modelo, marco):
    """Los 8 coeficientes de PERSPECTIVE: nueva -> dibujo -> original, todo
    proyectivo, así que es una sola matriz (exacta)."""
    x0, y0, pix, _w, _h = marco
    O = [[pix, 0, x0], [0, -pix, y0], [0, 0, 1]]
    F = [[1, 0, 0], [0, -1, 0], [0, 0, 1]]
    M = G._h_mult(F, G._h_mult(modelo.Hi, O))
    k = M[2][2]
    return tuple(M[i][j] / k for i, j in ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2),
                                          (2, 0), (2, 1)))


def _datos_malla(modelo, marco):
    _x0, _y0, _pix, w, h = marco
    f = _a_original(modelo, marco)
    cols = list(range(0, w, MALLA)) + [w]
    filas = list(range(0, h, MALLA)) + [h]
    nodo = {}
    for r in filas:
        for c in cols:
            try:
                nodo[c, r] = f(c, r)
            except (ZeroDivisionError, OverflowError):
                nodo[c, r] = (-1e9, -1e9)
    malla = []
    for r0, r1 in zip(filas, filas[1:]):
        for c0, c1 in zip(cols, cols[1:]):
            quad = nodo[c0, r0] + nodo[c0, r1] + nodo[c1, r1] + nodo[c1, r0]
            malla.append(((c0, r0, c1, r1), quad))
    return malla


def _preparar(im, fondo):
    """La imagen en el modo que hace falta y el color del fondo."""
    if fondo == "transparente":
        # blanco con alfa 0: si algo ignora la transparencia, se ve blanco y no negro
        return im.convert("RGBA"), (255, 255, 255, 0)
    if im.mode in ("1", "L"):
        return im.convert("L"), 255
    return im.convert("RGB"), (255, 255, 255)


def rehacer(original, salidas, modelo, remuestreo: str = "vecino"):
    """Hace cada imagen de ``salidas`` ([(ruta, fondo), ...], de :func:`rutas`)
    y devuelve (coef de la nueva, (ancho, alto))."""
    Image = _pil()
    filtro = {"vecino": Image.Resampling.NEAREST, "lineal": Image.Resampling.BILINEAR,
              "cubica": Image.Resampling.BICUBIC}[remuestreo]
    limite = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None              # planos escaneados grandes: son del usuario
    try:
        with Image.open(original) as im:
            im.load()
            ancho, alto = im.size
            marco = marco_nuevo(modelo, ancho, alto)
            w, h = marco[3], marco[4]
            if isinstance(modelo, G.Proyectiva):
                metodo, datos = Image.Transform.PERSPECTIVE, _datos_perspectiva(modelo, marco)
            else:
                metodo, datos = Image.Transform.MESH, _datos_malla(modelo, marco)
            for ruta, fondo in salidas:
                fuente, relleno = _preparar(im, fondo)
                nueva = fuente.transform((w, h), metodo, datos, resample=filtro, fillcolor=relleno)
                opciones = {}
                suf = Path(ruta).suffix.lower()
                if suf in (".jpg", ".jpeg"):
                    opciones = {"quality": 95}
                elif suf in (".tif", ".tiff"):
                    opciones = {"compression": "tiff_lzw"}
                nueva.save(ruta, **opciones)
    finally:
        Image.MAX_IMAGE_PIXELS = limite
    return coef_nuevo(marco), (w, h)
