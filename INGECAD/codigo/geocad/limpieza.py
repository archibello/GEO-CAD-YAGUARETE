# SPDX-License-Identifier: GPL-3.0-or-later
"""Las cuentas de LIMPIARPLANO (3.86.0): limpiar un plano antiguo escaneado.

Receta probada el 19/11/2026 con un plano de mensura de 1958 (manchas de
humedad, pliegues, rumbos chicos, un sello violeta tenue); Fernando: «QUEDO
PERFECTO». Sólo numpy y PIL: el Flatpak de IngeCAD no trae scipy.

  1. gris, ampliar ×esc (LANCZOS) y desenfoque gaussiano de 0,3·esc px: a 1x
     los rumbos chicos (unos 6 px de alto) se empastan;
  2. «papel local»: CIERRE en gris (máximo y después mínimo) con una
     ventana algo mayor que el trazo más grueso (13 px a 1x): borra la tinta
     y deja el papel con sus manchas;
  3. contraste RELATIVO r = (papel − imagen) / papel: dentro de una mancha
     r ≈ 0, y la tinta que cae encima de la mancha conserva su contraste;
  4. máscara de tinta por HISTÉRESIS: los grupos conexos (8 vecinos) de
     r > débil que tocan r > fuerte y tienen al menos min_px píxeles; se
     dilata 1 px (cruz). Se van el granulado y los bordes de las manchas;
  5. tono: n = imagen / papel estirado entre lo y hi dentro de la máscara;
     afuera, blanco. Sale en gris (con su antialias), no en blanco y negro.

Zonas de sello (rectángulos que marca el usuario): se repite con umbrales
suaves (SELLO) y se pega sólo esa zona; el sello violeta se perdía con los
normales.

Cómo se hace sin scipy:
  * máximo y mínimo en ventana: separables (filas y columnas), por
    duplicación (ventanas de 1, 2, 4, 8, 16 y una de solapamiento), con los
    bordes reflejados como ``ndimage`` (modo «reflect» = numpy «symmetric»);
  * grupos conexos: tramos de cada fila (run-length) unidos con los de la
    fila siguiente que se tocan (8 vecinos) y union-find vectorizado
    (propagar el mínimo + saltar punteros); el tamaño y si tocan «fuerte»
    salen de sumas por tramo.
"""
from __future__ import annotations

#: umbrales normales y de sello (los del prototipo aprobado)
NORMAL = dict(fuerte=0.45, debil=0.15, lo=0.20, hi=0.75, suav=0.3)
SELLO = dict(fuerte=0.22, debil=0.08, lo=0.35, hi=0.85, suav=0.3, min_px=60)
ESCALA = 2
_LADO_TRAZO = 13     # ventana del cierre a 1x (algo más que el trazo más grueso)


class LimpiezaError(Exception):
    pass


def _np():
    try:
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        raise LimpiezaError("falta numpy para limpiar la imagen") from exc
    return np


def _pil():
    try:
        from PIL import Image, ImageFilter
    except Exception as exc:  # noqa: BLE001
        raise LimpiezaError("falta PIL (Pillow) para limpiar la imagen") from exc
    Image.MAX_IMAGE_PIXELS = None
    return Image, ImageFilter


# ------------------------------------------------------------------ morfología
def _ventana_1d(a, k: int, eje: int, f):
    """Máximo (f = np.maximum) o mínimo de una ventana centrada de k (impar)
    a lo largo de ``eje``, con los bordes reflejados (como ndimage)."""
    np = _np()
    r = k // 2
    pad = [(0, 0)] * a.ndim
    pad[eje] = (r, r)
    b = np.pad(a, pad, mode="symmetric")
    n = b.shape[eje]

    def tramo(x, ini, largo):
        s = [slice(None)] * x.ndim
        s[eje] = slice(ini, ini + largo)
        return x[tuple(s)]

    # w[i] = f de b[i : i+ancho]; se duplica el ancho mientras quepa
    w, ancho = b, 1
    while ancho * 2 <= k:
        largo = n - 2 * ancho + 1
        w = f(tramo(w, 0, largo), tramo(w, ancho, largo))
        ancho *= 2
    if ancho < k:                      # dos ventanas solapadas cubren k
        largo = n - k + 1
        w = f(tramo(w, 0, largo), tramo(w, k - ancho, largo))
    else:
        w = tramo(w, 0, n - k + 1)
    return w


def maximo(a, k: int):
    np = _np()
    return _ventana_1d(_ventana_1d(a, k, 0, np.maximum), k, 1, np.maximum)


def minimo(a, k: int):
    np = _np()
    return _ventana_1d(_ventana_1d(a, k, 0, np.minimum), k, 1, np.minimum)


def cierre(a, k: int):
    """``ndimage.grey_closing(a, size=(k, k))`` con k impar."""
    return minimo(maximo(a, k), k)


def dilatar_cruz(m):
    """``ndimage.binary_dilation(m)`` (cruz de 4 vecinos, una vez)."""
    np = _np()
    d = m.copy()
    d[1:, :] |= m[:-1, :]
    d[:-1, :] |= m[1:, :]
    d[:, 1:] |= m[:, :-1]
    d[:, :-1] |= m[:, 1:]
    return d


# ------------------------------------------------------------------ grupos conexos
def tramos(m):
    """Los tramos horizontales de ``m``: (fila, inicio, fin) con fin incluido."""
    np = _np()
    h, w = m.shape
    p = np.zeros((h, w + 2), np.int8)
    p[:, 1:-1] = m
    d = np.diff(p, axis=1)
    fi, ini = np.nonzero(d == 1)
    _ff, fin = np.nonzero(d == -1)
    return fi.astype(np.int64), ini.astype(np.int64), fin.astype(np.int64) - 1


def _uniones(fi, ini, fin, ancho):
    """Pares de tramos de filas vecinas que se tocan (8 vecinos)."""
    np = _np()
    if fi.size == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    K = ancho + 3
    clave_ini = fi * K + ini            # crecientes: tramos ordenados por fila y columna
    clave_fin = fi * K + fin
    lo = np.searchsorted(clave_fin, (fi + 1) * K + ini - 1, side="left")
    hi = np.searchsorted(clave_ini, (fi + 1) * K + fin + 1, side="right")
    cuenta = np.maximum(hi - lo, 0)
    a = np.repeat(np.arange(fi.size, dtype=np.int64), cuenta)
    # b = lo[a] + 0, 1, 2... dentro de cada grupo
    base = np.repeat(lo - np.concatenate(([0], np.cumsum(cuenta)[:-1])), cuenta)
    b = base + np.arange(a.size, dtype=np.int64)
    return a, b


def raices(n: int, a, b):
    """Union-find vectorizado: el representante (el menor) de cada tramo."""
    np = _np()
    lab = np.arange(n, dtype=np.int64)
    if a.size == 0:
        return lab
    while True:
        la, lb = lab[a], lab[b]
        m = np.minimum(la, lb)
        cambio = (la != m) | (lb != m)
        if not cambio.any():
            break
        # se baja también el representante de cada uno (une los árboles)
        np.minimum.at(lab, la, m)
        np.minimum.at(lab, lb, m)
        while True:                      # saltar punteros hasta la raíz
            nuevo = lab[lab]
            if np.array_equal(nuevo, lab):
                break
            lab = nuevo
    return lab


def histeresis(debil_m, fuerte_m, min_px: int):
    """Los grupos conexos (8 vecinos) de ``debil_m`` que tocan ``fuerte_m`` y
    tienen al menos ``min_px`` píxeles (como el prototipo con ndimage.label)."""
    np = _np()
    h, w = debil_m.shape
    fi, ini, fin = tramos(debil_m)
    if fi.size == 0:
        return np.zeros_like(debil_m)
    a, b = _uniones(fi, ini, fin, w)
    raiz = raices(fi.size, a, b)
    largo = fin - ini + 1
    tam = np.bincount(raiz, weights=largo, minlength=fi.size)
    plano = fi * w + ini
    acum = np.concatenate(([0], np.cumsum((fuerte_m & debil_m).ravel(), dtype=np.int64)))
    fuertes = acum[plano + largo] - acum[plano]
    toca = np.bincount(raiz, weights=fuertes, minlength=fi.size) > 0
    ok = (toca & (tam >= min_px))[raiz]
    # pintar los tramos elegidos: +1 al empezar, −1 después del final
    d = np.zeros(h * w + 1, np.int32)
    np.add.at(d, plano[ok], 1)
    np.add.at(d, plano[ok] + largo[ok], -1)
    return (np.cumsum(d[:-1]) > 0).reshape(h, w)


# ------------------------------------------------------------------ la receta
def gris(imagen):
    """La imagen en gris (lo transparente, sobre papel blanco)."""
    Image, _f = _pil()
    if imagen.mode in ("RGBA", "LA", "PA") or (imagen.mode == "P" and "transparency" in imagen.info):
        fondo = Image.new("RGBA", imagen.size, (255, 255, 255, 255))
        fondo.alpha_composite(imagen.convert("RGBA"))
        imagen = fondo
    return imagen.convert("L")


def preparar(g0, esc: int = ESCALA, suav: float = 0.3):
    """Ampliada ×esc y apenas desenfocada (float32)."""
    np = _np()
    Image, ImageFilter = _pil()
    w, h = g0.size
    g = g0.resize((w * esc, h * esc), Image.LANCZOS) if esc != 1 else g0
    return np.asarray(g.filter(ImageFilter.GaussianBlur(suav * esc)), np.float32)


def papel_local(g, esc: int = ESCALA):
    v = _LADO_TRAZO * esc + 1 - (_LADO_TRAZO * esc) % 2
    return cierre(g, v)


def proceso(g, papel, esc: int = ESCALA, debil=0.15, fuerte=0.45, min_px=None,
            lo=0.20, hi=0.75, suav=0.3):
    """El resultado (float, 0 a 255) para una imagen ya preparada."""
    np = _np()
    min_px = min_px or 30 * esc * esc
    r = (papel - g) / np.maximum(papel, 20)
    m = dilatar_cruz(histeresis(r > debil, r > fuerte, min_px))
    del r
    n = np.clip(g / np.maximum(papel, 1), 0, 1)
    t = np.clip((n - lo) / (hi - lo), 0, 1)
    return np.where(m, 255 * t, 255)


def limpiar(imagen, zonas_sello=(), esc: int = ESCALA, avance=None):
    """La imagen limpia (PIL, gris, ×esc). ``zonas_sello``: rectángulos
    (x0, y0, x1, y1) en píxeles de la imagen original. ``avance(f)``: 0 a 1."""
    np = _np()
    Image, _f = _pil()
    paso = avance or (lambda f: None)
    g0 = gris(imagen)
    paso(0.05)
    g = preparar(g0, esc, NORMAL["suav"])
    paso(0.20)
    papel = papel_local(g, esc)
    paso(0.45)
    out = proceso(g, papel, esc, **NORMAL)
    paso(0.75)
    zonas = [z for z in (_zona(z, g0.size) for z in zonas_sello or ()) if z]
    if zonas:
        s = proceso(g, papel, esc, **SELLO)
        for x0, y0, x1, y1 in zonas:
            out[y0 * esc:y1 * esc, x0 * esc:x1 * esc] = s[y0 * esc:y1 * esc, x0 * esc:x1 * esc]
        del s
    paso(0.95)
    hecha = Image.fromarray(out.astype(np.uint8))
    alfa = _alfa(imagen)
    if alfa is not None:
        # lo recortado (transparente) sigue transparente
        hecha.putalpha(alfa.resize(hecha.size, Image.NEAREST))
    return hecha


def _alfa(imagen):
    """El canal alfa si la imagen tiene algo transparente, o None."""
    if imagen.mode not in ("RGBA", "LA", "PA") and not (
            imagen.mode == "P" and "transparency" in imagen.info):
        return None
    a = imagen.convert("RGBA").getchannel("A")
    return a if a.getextrema()[0] < 255 else None


def _zona(z, tam):
    """Rectángulo ordenado y dentro de la imagen, en enteros, o None."""
    try:
        x0, y0, x1, y1 = (float(c) for c in z)
    except (TypeError, ValueError):
        return None
    w, h = tam
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    x0, y0 = max(0, int(round(x0))), max(0, int(round(y0)))
    x1, y1 = min(w, int(round(x1))), min(h, int(round(y1)))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None
