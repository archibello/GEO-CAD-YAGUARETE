# SPDX-License-Identifier: GPL-3.0-or-later
"""ASPECTOIMAGEN: las cuentas, sólo numpy (núcleo, 3.91.0).

Las usan IngeCAD (aspecto.py, con PIL para abrir y guardar) y QGIS
(dibujo/aspecto_qgis.py, con QImage): la misma cuenta en los dos programas.
Estaban en aspecto.py de IngeCAD (3.31.0 a 3.84.0); ver allí qué hace cada
valor (fondo transparente, blanco que se borra, líneas, opacidad, contraste,
imagen final y limpiar manchas). Sin Qt ni PIL.
"""
from __future__ import annotations

LINEAS = ("como", "negativo", "color")

#: los valores iniciales («Valores iniciales» en la ventana)
DEFECTO = {"transparente": True, "blanco": 25, "lineas": "como",
           "color": "#FF2020", "opacidad": 100, "contraste": 100, "final": False,
           "limpiar": False, "distancia": 8, "tolerancia": 30}
BLANCO_MAX = 80
OPACIDAD_MIN = 10
CONTRASTE_MAX = 400
SUFIJO_FINAL = "_final"
DISTANCIA_MIN, DISTANCIA_MAX = 2, 40     # píxeles del original
TOLERANCIA_MIN, TOLERANCIA_MAX = 5, 50   # % de una línea fina (50: nunca borra una línea)
ROJO = (255, 0, 0)                       # lo que se borra, en la vista previa


class AspectoError(Exception):
    """No se puede leer o procesar la imagen."""


# ------------------------------------------------------------------ los valores
def _color(texto) -> str:
    t = str(texto or "").strip().lstrip("#")
    if len(t) == 6:
        try:
            int(t, 16)
            return "#" + t.upper()
        except ValueError:
            pass
    return DEFECTO["color"]


def normalizar(valores) -> dict:
    """Los valores completos y dentro de sus márgenes."""
    v = dict(DEFECTO)
    v.update({k: x for k, x in dict(valores or {}).items() if k in DEFECTO})
    v["transparente"] = bool(v["transparente"])
    v["final"] = bool(v["final"])
    v["limpiar"] = bool(v["limpiar"])
    for k, lo, hi in (("distancia", DISTANCIA_MIN, DISTANCIA_MAX),
                      ("tolerancia", TOLERANCIA_MIN, TOLERANCIA_MAX)):
        try:
            v[k] = int(round(min(hi, max(lo, float(v[k])))))
        except (TypeError, ValueError):
            v[k] = DEFECTO[k]
    try:
        v["contraste"] = int(round(min(CONTRASTE_MAX, max(100, float(v["contraste"])))))
    except (TypeError, ValueError):
        v["contraste"] = DEFECTO["contraste"]
    try:
        v["blanco"] = int(round(min(BLANCO_MAX, max(0, float(v["blanco"])))))
    except (TypeError, ValueError):
        v["blanco"] = DEFECTO["blanco"]
    try:
        v["opacidad"] = int(round(min(100, max(OPACIDAD_MIN, float(v["opacidad"])))))
    except (TypeError, ValueError):
        v["opacidad"] = DEFECTO["opacidad"]
    if v["lineas"] not in LINEAS:
        v["lineas"] = DEFECTO["lineas"]
    v["color"] = _color(v["color"])
    return v


def rgb(color) -> tuple:
    t = _color(color).lstrip("#")
    return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)


def describir(valores) -> str:
    """Una línea para la línea de comandos."""
    v = normalizar(valores)
    partes = [f"fondo transparente (blanco que se borra {v['blanco']} %)" if v["transparente"]
              else "fondo como está"]
    partes.append({"como": "líneas como están", "negativo": "líneas en negativo",
                   "color": f"líneas de color {v['color']}"}[v["lineas"]])
    if v["contraste"] != 100:
        partes.append(f"contraste de las líneas {v['contraste']} %")
    partes.append(f"opacidad {v['opacidad']} %")
    if v["limpiar"]:
        partes.append(f"manchas limpiadas (distancia {v['distancia']} px, "
                      f"tolerancia {v['tolerancia']} %)")
    if v["final"]:
        partes.append("imagen final sobre papel blanco")
    return ", ".join(partes)


#: filas por franja: la cuenta va por franjas para decir cuánto lleva (la
#: barra de progreso, 3.31.2) y no tener toda la imagen en decimales a la vez
FILAS_FRANJA = 256


def _franja(a, v, color):
    """El aspecto de una franja de filas (uint8 RGBA -> uint8 RGBA)."""
    import numpy as np
    f = a.astype(np.float32)
    colores = f[..., :3]
    alfa = f[..., 3] / 255.0
    k = v["contraste"] / 100.0
    if v["transparente"]:
        lum = (0.299 * colores[..., 0] + 0.587 * colores[..., 1] + 0.114 * colores[..., 2]) / 255.0
        t = 1.0 - v["blanco"] / 100.0
        tinta = np.clip((t - lum) / t, 0.0, 1.0)
        # contraste: lo que ya es línea se hace más opaco; el papel que se
        # borra sigue borrado (si no, el amarillento volvería a verse)
        alfa = alfa * np.minimum(1.0, tinta * k)
    if k != 1.0:
        # la «tinta» (lo que le falta para ser blanco) se multiplica: lo
        # blanco sigue blanco, lo tenue se refuerza, negro o de color
        colores = 255.0 - np.minimum(255.0, (255.0 - colores) * k)
    alfa = alfa * (v["opacidad"] / 100.0)
    if v["lineas"] == "negativo":
        colores = 255.0 - colores
    elif v["lineas"] == "color":
        colores = np.broadcast_to(color, colores.shape)
    if v["final"]:
        colores, alfa = _sobre_blanco(colores, alfa)
    salida = np.empty(a.shape, dtype=np.uint8)
    salida[..., :3] = np.clip(np.rint(colores), 0, 255).astype(np.uint8)
    salida[..., 3] = np.clip(np.rint(alfa * 255.0), 0, 255).astype(np.uint8)
    return salida


def _sobre_blanco(colores, alfa):
    """La entrega: todo sobre papel blanco, opaco (como se ve con la capa)."""
    import numpy as np
    a3 = alfa[..., None]
    return colores * a3 + 255.0 * (1.0 - a3), np.ones_like(alfa)


def _tinta(a, v):
    """1 donde una franja tiene tinta (más oscuro que «Blanco que se borra»,
    por tenue que sea: una línea clara cuenta igual que una negra), 0 en el
    papel (uint8)."""
    import numpy as np
    f = a.astype(np.float32)
    lum = (0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]) / 255.0
    t = 1.0 - v["blanco"] / 100.0
    return ((lum < t) & (a[..., 3] >= 128)).astype(np.uint8)


def _suma_filas(c, r, eje):
    """Suma en ventana [i-r, i+r] a lo largo de ``eje`` (los bordes cuentan
    sólo lo que hay adentro)."""
    import numpy as np
    n = c.shape[eje]
    acum = np.cumsum(c, axis=eje, dtype=np.int32)
    forma = list(acum.shape)
    forma[eje] = 1
    acum = np.concatenate([np.zeros(forma, dtype=np.int32), acum], axis=eje)
    i = np.arange(n)
    hi = np.minimum(n, i + r + 1)
    lo = np.maximum(0, i - r)
    return np.take(acum, hi, axis=eje) - np.take(acum, lo, axis=eje)


def manchas(a, v, escala: float = 1.0):
    """Lo que la limpieza borra (bool, alto x ancho) de un arreglo RGBA:
    los píxeles con algo de tinta cuya vecindad (2r+1)² tiene menos tinta
    que Tolerancia % de una línea fina de 2r+1 píxeles. ``escala``: la
    imagen está reducida (vista previa): la distancia se achica igual."""
    import numpy as np
    alto, ancho = a.shape[:2]
    r = max(1, int(round(v["distancia"] * escala)))
    minimo = v["tolerancia"] / 100.0 * (2 * r + 1)
    pesos = np.empty((alto, ancho), dtype=np.uint8)
    for y in range(0, alto, FILAS_FRANJA):
        pesos[y:y + FILAS_FRANJA] = _tinta(a[y:y + FILAS_FRANJA], v)
    horiz = np.empty((alto, ancho), dtype=np.uint8)        # <= 2·40+1
    for y in range(0, alto, FILAS_FRANJA):
        horiz[y:y + FILAS_FRANJA] = _suma_filas(pesos[y:y + FILAS_FRANJA], r, 1)
    borrar = np.empty((alto, ancho), dtype=bool)
    paso = 1024
    for x in range(0, ancho, paso):
        cuenta = _suma_filas(horiz[:, x:x + paso], r, 0)
        borrar[:, x:x + paso] = (cuenta < minimo) & (pesos[:, x:x + paso] > 0)
    # el halo claro de una mancha (sin tinta) también se va
    return borrar | _halo(a, v, borrar)


def _halo(a, v, borrar):
    """Los píxeles claros que no llegan a tinta, pegados a lo que se borra."""
    import numpy as np
    if not borrar.any():
        return borrar
    cerca = np.zeros_like(borrar)
    cerca[1:] |= borrar[:-1]
    cerca[:-1] |= borrar[1:]
    cerca[:, 1:] |= borrar[:, :-1]
    cerca[:, :-1] |= borrar[:, 1:]
    return cerca & ~borrar & (a[..., 3] > 0) & (a[..., :3].min(axis=2) < 255)


def procesar_arreglo(a, valores, hecho=None, escala: float = 1.0, marcar: bool = False):
    """El aspecto de un arreglo RGBA (alto x ancho x 4, uint8) -> otro igual. La
    transparencia sale de la oscuridad de cada píxel: alfa = (T - L) / T, con L la
    luminancia (0 negro, 1 blanco) y T = 1 - blanco/100: lo más claro que T queda
    invisible. Se multiplica por el alfa propio de la imagen y por la opacidad. Con
    ``hecho`` (una lista [0..1]) va diciendo cuánto lleva. Con la limpieza (3.84.0),
    lo borrado queda transparente (o blanco); ``marcar`` lo pinta en rojo (la vista
    previa); ``escala``: ver manchas()."""
    import numpy as np
    v = normalizar(valores)
    color = np.array(rgb(v["color"]), dtype=np.float32)
    salida = np.empty(a.shape, dtype=np.uint8)
    alto = a.shape[0]
    limpiar = v["limpiar"]
    vf = dict(v, final=False) if limpiar else v
    tramo = 0.6 if limpiar else 1.0
    for y in range(0, alto, FILAS_FRANJA):
        salida[y:y + FILAS_FRANJA] = _franja(a[y:y + FILAS_FRANJA], vf, color)
        if hecho is not None:
            hecho[0] = tramo * min(alto, y + FILAS_FRANJA) / alto
    if limpiar:
        borrar = manchas(a, v, escala)
        if hecho is not None:
            hecho[0] = 0.85
        if marcar:
            salida[borrar] = (*ROJO, 255)
        elif v["transparente"]:
            salida[borrar, 3] = 0
        else:
            salida[borrar, :3] = 255
        if v["final"]:
            for y in range(0, alto, FILAS_FRANJA):
                s = salida[y:y + FILAS_FRANJA]
                c, al = _sobre_blanco(s[..., :3].astype(np.float32), s[..., 3] / 255.0)
                s[..., :3] = np.clip(np.rint(c), 0, 255).astype(np.uint8)
                s[..., 3] = 255
        if hecho is not None:
            hecho[0] = 1.0
    return salida
