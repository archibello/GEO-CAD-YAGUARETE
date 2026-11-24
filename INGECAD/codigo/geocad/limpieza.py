# SPDX-License-Identifier: GPL-3.0-or-later
"""Las cuentas de LIMPIARPLANO (3.86.0): limpiar un plano antiguo escaneado.

Receta probada el 19/11/2026 con un plano de mensura de 1958 (manchas de
humedad, pliegues, rumbos chicos, un sello violeta tenue); Fernando: «QUEDO
PERFECTO». Sólo numpy y PIL: el Flatpak de IngeCAD no trae scipy. Desde la 3.92.0
está en el núcleo y la usa también QGIS, sin PIL (limpiar_arreglo).

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


# ------------------------------------------------------------------ sin PIL (3.92.0)
# El Python de QGIS no trae PIL: los tres pasos que lo usaban (gris, ampliar con
# LANCZOS y el desenfoque gaussiano) hechos con numpy como los hace PIL, con el
# redondeo a 8 bits de cada pasada. El resto de la receta es el mismo.
def gris_arreglo(rgba):
    """Gris (uint8) de un arreglo RGBA (lo transparente, sobre papel blanco), con la
    fórmula de PIL (convert("L"))."""
    np = _np()
    a = rgba.astype(np.int64)
    if rgba.shape[2] >= 4 and (rgba[..., 3] < 255).any():
        al = a[..., 3:4]
        a = (a[..., :3] * al + 255 * (255 - al) + 127) // 255
    return ((a[..., 0] * 19595 + a[..., 1] * 38470 + a[..., 2] * 7471 + 0x8000) >> 16).astype(np.uint8)


def _lanczos(x):
    np = _np()
    x = np.abs(x)
    out = np.sinc(x) * np.sinc(x / 3.0)
    return np.where(x < 3.0, out, 0.0)


def _ampliar_eje(a, esc: int, eje: int):
    """Una pasada de la ampliación LANCZOS de PIL a lo largo de ``eje`` (redondeo a 8 bits)."""
    np = _np()
    n = a.shape[eje]
    m = n * esc
    centro = (np.arange(m) + 0.5) / esc
    lo = np.clip((centro - 3.0 + 0.5).astype(int), 0, n)
    hi = np.clip((centro + 3.0 + 0.5).astype(int), 0, n)
    k = int((hi - lo).max())
    idx = lo[:, None] + np.arange(k)[None, :]
    w = _lanczos((idx - centro[:, None] + 0.5))
    w = np.where(idx < hi[:, None], w, 0.0)
    w /= w.sum(axis=1, keepdims=True)
    idx = np.minimum(idx, n - 1)
    b = np.moveaxis(a.astype(np.float64), eje, -1)
    out = np.zeros(b.shape[:-1] + (m,), np.float64)
    for j in range(k):
        out += b[..., idx[:, j]] * w[:, j]
    out = np.clip(np.floor(out + 0.5), 0, 255)
    return np.moveaxis(out, -1, eje)


def ampliar_arreglo(g, esc: int = ESCALA):
    """``g`` (gris uint8) ampliada ×esc con LANCZOS, como PIL (primero filas, después columnas)."""
    if esc == 1:
        return g.copy()
    return _ampliar_eje(_ampliar_eje(g, esc, 1), esc, 0).astype(_np().uint8)


def desenfocar_arreglo(g, radio: float):
    """GaussianBlur(radio) de PIL: tres pasadas de caja (radio fraccionario) por eje,
    con los bordes repetidos y redondeo a 8 bits en cada una."""
    np = _np()
    sigma2 = radio * radio / 3.0
    L = (12.0 * sigma2 + 1.0) ** 0.5
    l = int((L - 1.0) // 2)
    a = (2 * l + 1) * (l * (l + 1) - 3 * sigma2) / (6 * (sigma2 - (l + 1) * (l + 1)))
    r = l + a
    ww = 1.0 / (2.0 * r + 1.0)
    fw = (1.0 - (2 * l + 1) * ww) / 2.0
    out = g.astype(np.float64)
    for eje in (1, 0):
        for _ in range(3):
            p = np.pad(out, [(l + 1, l + 1) if e == eje else (0, 0) for e in range(2)], mode="edge")
            n = out.shape[eje]
            acc = np.zeros_like(out)
            for d in range(-l, l + 1):
                acc += np.take(p, np.arange(n) + l + 1 + d, axis=eje) * ww
            acc += (np.take(p, np.arange(n), axis=eje) + np.take(p, np.arange(n) + 2 * l + 2, axis=eje)) * fw
            out = np.clip(np.floor(acc + 0.5), 0, 255)
    return out.astype(np.float32)


def preparar_arreglo(g0, esc: int = ESCALA, suav: float = 0.3):
    """Lo de preparar() sin PIL: ampliada ×esc y apenas desenfocada (float32)."""
    return desenfocar_arreglo(ampliar_arreglo(g0, esc), suav * esc)


def limpiar_arreglo(rgba, zonas_sello=(), esc: int = ESCALA, avance=None):
    """limpiar() sin PIL (QGIS): de un arreglo RGBA, (gris limpio uint8 ×esc, alfa ×esc
    o None). Misma receta y mismos umbrales."""
    np = _np()
    paso = avance or (lambda f: None)
    g0 = gris_arreglo(rgba)
    paso(0.05)
    g = preparar_arreglo(g0, esc, NORMAL["suav"])
    paso(0.20)
    out = _receta(g, (g0.shape[1], g0.shape[0]), zonas_sello, esc, paso)
    alfa = None
    if rgba.shape[2] >= 4 and (rgba[..., 3] < 255).any():
        alfa = np.repeat(np.repeat(rgba[..., 3], esc, axis=0), esc, axis=1)
    return out.astype(np.uint8), alfa


def _receta(g, tam, zonas_sello, esc, paso):
    """Pasos 2 a 5 (papel local, contraste, histéresis, tono) y las zonas de sello."""
    papel = papel_local(g, esc)
    paso(0.45)
    out = proceso(g, papel, esc, **NORMAL)
    paso(0.75)
    zonas = [z for z in (_zona(z, tam) for z in zonas_sello or ()) if z]
    if zonas:
        s = proceso(g, papel, esc, **SELLO)
        for x0, y0, x1, y1 in zonas:
            out[y0 * esc:y1 * esc, x0 * esc:x1 * esc] = s[y0 * esc:y1 * esc, x0 * esc:x1 * esc]
        del s
    paso(0.95)
    return out


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
    out = _receta(g, g0.size, zonas_sello, esc, paso)
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
