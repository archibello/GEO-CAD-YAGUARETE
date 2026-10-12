# SPDX-License-Identifier: GPL-3.0-or-later
"""Uniones de los grosores en pantalla (pedido de Fernando, 12/10/2026).

Con LWT, IngeCAD dibuja cada tramo con grosor como un rectángulo suelto que
termina justo en el vértice: en cada esquina de una polilínea (o donde se
tocan dos líneas) quedaba una muesca del lado de afuera, en el modelo y en
el papel. AutoCAD une los tramos sin cortes.

Cada vértice de esos rectángulos guarda el punto del tramo y una dirección
que la pantalla multiplica por medio grosor (en cada cuadro, según el zoom).
Al armar la escena, donde se juntan exactamente dos puntas del mismo color y
grosor, las dos pasan a compartir el mismo borde, en inglete: la esquina
queda llena a cualquier zoom. No se agregan vértices: la escena pesa lo
mismo y el orden de dibujo, las tandas y lo oculto siguen igual. En ángulos
muy agudos el inglete se acorta (como el límite de inglete de AutoCAD). Los
cruces de tres o más tramos quedan como venían.
"""
from __future__ import annotations

from . import modulos

PROGRAMA = "ingecad"
#: largo máximo del inglete, en medios grosores (AutoCAD usa uno parecido)
LIMITE = 4.0
#: los seis vértices de cada tramo: (punta, signo) como los arma IngeCAD
INICIO = ((0, 1), (1, -1), (4, -1))
FINAL = ((2, 1), (3, 1), (5, -1))


def activo() -> bool:
    return modulos.activo(PROGRAMA, "uniones")


def _forma_conocida(data) -> bool:
    """Seis vértices por tramo con punto, dirección y color, como desde
    IngeCAD 0.6.5. Si algún día cambia, no se toca nada."""
    nombres = getattr(getattr(data, "dtype", None), "names", None) or ()
    return {"pos", "normal", "rgba"} <= set(nombres) and len(data) % 6 == 0


def unir(batch) -> int:
    """Une en inglete las puntas de los tramos que se tocan de a dos. Cambia
    ``batch.data`` en el lugar y devuelve cuántas uniones hizo."""
    import numpy as np

    data = getattr(batch, "data", None)
    if data is None or not len(data) or not _forma_conocida(data):
        return 0
    v = data.reshape(-1, 6)
    n = len(v)
    pos, normal = v["pos"], v["normal"]
    p0, p1 = pos[:, 0], pos[:, 2]
    nrm = normal[:, 0].astype(np.float64)                     # la dirección «+» del tramo
    if not np.allclose(normal[:, 2], nrm, atol=1e-5):         # no es la forma esperada
        return 0
    grosor = np.zeros(n, dtype=np.float32)
    for r in getattr(batch, "ranges", ()):
        grosor[r.first // 6:(r.first + r.count) // 6] = r.lineweight
    color = np.ascontiguousarray(v["rgba"][:, 0]).view(np.uint32).reshape(n)

    # las 2n puntas: (x, y) y (grosor, color) en dos enteros de 64 bits; las
    # que caen en el mismo lugar quedan juntas al ordenar
    bits = lambda f: np.ascontiguousarray(f, dtype=np.float32).view(np.uint32).astype(np.uint64)
    x = np.concatenate((p0[:, 0], p1[:, 0]))
    y = np.concatenate((p0[:, 1], p1[:, 1]))
    k1 = (bits(x) << np.uint64(32)) | bits(y)
    k2 = ((bits(np.concatenate((grosor, grosor))) << np.uint64(32))
          | np.concatenate((color, color)).astype(np.uint64))
    orden = np.lexsort((k2, k1))
    k1, k2 = k1[orden], k2[orden]
    corte = np.flatnonzero((k1[1:] != k1[:-1]) | (k2[1:] != k2[:-1])) + 1
    inicio = np.concatenate(([0], corte))
    tamano = np.diff(np.concatenate((inicio, [len(orden)])))
    pares = inicio[tamano == 2]
    if not len(pares):
        return 0
    de_a_dos = np.stack((orden[pares], orden[pares + 1]), axis=1)
    tramo = np.concatenate((np.arange(n), np.arange(n)))
    final = np.concatenate((np.zeros(n, bool), np.ones(n, bool)))
    a, b = de_a_dos[:, 0], de_a_dos[:, 1]
    ta, tb = tramo[a], tramo[b]
    sa = np.where(final[a], 1.0, -1.0)               # +1 si el tramo llega al vértice
    sb = np.where(final[b], 1.0, -1.0)
    n1 = sa[:, None] * nrm[ta]                       # el camino: A llega, B sale
    n2 = -sb[:, None] * nrm[tb]
    den = 1.0 + (n1 * n2).sum(axis=1)
    ok = (den > 1e-6) & (ta != tb)                   # no una vuelta atrás, no el mismo tramo
    m = (n1 + n2) / np.where(ok, den, 1.0)[:, None]
    largo = np.hypot(m[:, 0], m[:, 1])
    m *= np.minimum(1.0, LIMITE / np.maximum(largo, 1e-12))[:, None]
    for puntas, factor, tramos in ((a, sa, ta), (b, -sb, tb)):
        llega = final[puntas]
        for cual, vertices in ((ok & ~llega, INICIO), (ok & llega, FINAL)):
            filas, mm = tramos[cual], factor[cual][:, None] * m[cual]
            for i, signo in vertices:
                normal[filas, i] = signo * mm
    return int(ok.sum())


def _envolver_pack_thick(original):
    def _pack_thick(*args, **kwargs):
        batch = original(*args, **kwargs)
        if activo():
            try:
                unir(batch)
            except Exception:  # noqa: BLE001  (los tramos quedan como venían)
                pass
        return batch
    _pack_thick._puente_original = original
    _pack_thick._puente_fabrica = _envolver_pack_thick
    return _pack_thick


def instalar() -> None:
    """Se llama al cargar el plugin. El envoltorio mira ``activo()`` al armar
    la escena: prender o apagar el módulo se ve al regenerar."""
    try:
        from render import batches
    except Exception:  # noqa: BLE001
        return
    actual = getattr(batches, "_pack_thick", None)
    if actual is None or getattr(actual, "_puente_fabrica", None) is _envolver_pack_thick:
        return
    batches._pack_thick = _envolver_pack_thick(getattr(actual, "_puente_original", actual))
