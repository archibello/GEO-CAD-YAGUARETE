# SPDX-License-Identifier: GPL-3.0-or-later
"""Sombreados como polígonos: TRIM y JOIN (3.100.0, módulo «sombreado»).

Pedido de Fernando (27/11/2026): «poder cortar con trim los hatch y poder unir
con join»; «sólo podemos unir hatch con el mismo diseño o estilo», «o otorgar el
diseño del de mayor superficie al de menor superficie».

TRIM: con bordes de corte que atraviesan un sombreado, el clic borra la parte
del sombreado donde se hizo; el resto queda en el mismo sombreado (mismo patrón,
fondo, datos de Custom), con su borde nuevo y sus islas. La cuenta: los bordes
del sombreado y los de corte se parten en sus cruces; las caras que quedan son
los pedazos; se borra la cara del clic (diferencia, con la misma clasificación
de tramos que usa la unión de UNIR: se queda cada tramo que tiene sombreado de
un solo lado).

JOIN: los sombreados que se tocan quedan en uno, con la unión de UNIR con
polígonos (combinar.py, Python puro): se rellenan las ranuras encerradas entre
ellos, los huecos propios se respetan y los grupos aislados quedan aparte. Sólo
se unen sombreados del mismo estilo; con estilos distintos se pregunta si se
unen con el del de mayor superficie.

Los arcos de los bordes vuelven a ser arcos (como BOUNDARY). Sin Qt.
"""
from __future__ import annotations

import math

from . import combinar as C
from . import sombreado as S

CURVAS = ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE")


# -- de los objetos a líneas ---------------------------------------------------------------------
def _caja_de(puntos):
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    return min(xs), min(ys), max(xs), max(ys)


def paso_de(hatches) -> float:
    """La flecha de las curvas pasadas a tramos: muy chica respecto del sombreado."""
    pts = [p for h in hatches for r in anillos(h, None) for p in r]
    if not pts:
        return 1e-3
    x0, y0, x1, y1 = _caja_de(pts)
    return max(math.hypot(x1 - x0, y1 - y0) * 2e-5, 1e-9)


def anillos(hatch, paso) -> list:
    """Los bordes del sombreado como anillos de (x, y), abiertos."""
    from ezdxf import path as P
    out = []
    try:
        caminos = list(P.from_hatch(hatch))
    except Exception:  # noqa: BLE001
        caminos = []
    for c in caminos:
        try:
            pts = [(v.x, v.y) for v in (c.flattening(paso) if paso else c.control_vertices())]
        except Exception:  # noqa: BLE001
            continue
        pts = C.abierto(pts)
        if len(pts) >= 3:
            out.append(pts)
    return out


def lineas_de(entidad, paso) -> list:
    """Un objeto de corte como polilíneas de (x, y)."""
    from ezdxf import path as P
    try:
        c = P.make_path(entidad)
        partes = list(c.sub_paths()) if hasattr(c, "sub_paths") else [c]
        return [[(v.x, v.y) for v in p.flattening(paso)] for p in partes]
    except Exception:  # noqa: BLE001
        return []


def fuentes(hatch) -> list:
    """Objetos de más (no van al dibujo) con las curvas del sombreado, para que
    ``con_arcos`` devuelva los arcos de sus bordes."""
    from ezdxf.entities import LWPolyline
    out = []
    for path in getattr(hatch, "paths", ()) or ():
        vertices = getattr(path, "vertices", None)
        if vertices is None or len(vertices) < 2:
            continue
        if not any(len(v) > 2 and abs(float(v[2])) > 1e-12 for v in vertices):
            continue
        e = LWPolyline.new()
        e.set_points([(float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0)
                      for v in vertices], format="xyb")
        e.closed = True
        out.append(e)
    return out


# -- la cuenta: tramos partidos, caras y la diferencia -------------------------------------------
def _grafo(polilineas, tol):
    """Los tramos de todas las polilíneas partidos en sus cruces: (puntos, aristas)."""
    puntos = C._Puntos(tol)
    segs = []
    for pl, cerrada in polilineas:
        ids = [puntos.id(p, original=True) for p in pl]
        n = len(pl)
        for i in range(n if cerrada else n - 1):
            u, v = ids[i], ids[(i + 1) % n]
            if u != v:
                segs.append((puntos.xy[u], puntos.xy[v]))
    aristas = set()
    for lista in C._cortes(segs, tol):
        lista.sort(key=lambda t: t[0])
        ids = []
        for _t, p in lista:
            k = puntos.id(p)
            if not ids or ids[-1] != k:
                ids.append(k)
        for u, v in zip(ids, ids[1:]):
            if u != v:
                aristas.add((u, v) if u < v else (v, u))
    return puntos, aristas


def caras(pts, aristas) -> list:
    """Los ciclos de las caras (la cara a la izquierda): [(lista de puntos, área)]."""
    salen = {}
    for u, v in aristas:
        salen.setdefault(u, []).append(v)
        salen.setdefault(v, []).append(u)
    ang = {}
    for u, vs in salen.items():
        vs.sort(key=lambda w: math.atan2(pts[w][1] - pts[u][1], pts[w][0] - pts[u][0]))
        for i, w in enumerate(vs):
            ang[(u, w)] = i
    usadas = set()
    out = []
    for u0, vs in salen.items():
        for v0 in vs:
            if (u0, v0) in usadas:
                continue
            ciclo = []
            u, v = u0, v0
            while (u, v) not in usadas:
                usadas.add((u, v))
                ciclo.append(u)
                # la siguiente: la primera en sentido horario desde la vuelta (v -> u)
                lista = salen[v]
                k = ang[(v, u)]
                w = lista[(k - 1) % len(lista)]
                u, v = v, w
            anillo = [pts[k] for k in ciclo]
            out.append((anillo, C.area_con_signo(anillo)))
    return out


def _cara_de(p, caras_pos):
    """La cara (la más chica de las de área positiva) donde cae el punto."""
    for i, (anillo, _a) in enumerate(caras_pos):
        if C.dentro_anillo(p, anillo):
            return i
    return None


def _encadenar(pts, salen, originales, tol):
    """Los tramos que quedaron (salen: u -> [v], el polígono a la izquierda) como
    polígonos [[borde, huecos...]] (lo mismo que hace la unión de UNIR)."""
    usadas = set()
    lazos = []
    for u0 in list(salen):
        for v0 in list(salen[u0]):
            if (u0, v0) in usadas:
                continue
            camino = [u0]
            u, v = u0, v0
            while (u, v) not in usadas:
                usadas.add((u, v))
                camino.append(v)
                din = (pts[v][0] - pts[u][0], pts[v][1] - pts[u][1])
                libres = [w for w in salen.get(v, ()) if (v, w) not in usadas]
                if not libres:
                    break
                w = min(libres, key=lambda w: C._giro(din, (pts[w][0] - pts[v][0], pts[w][1] - pts[v][1])))
                u, v = v, w
            if camino[-1] == camino[0]:
                camino.pop()
            lazos.extend(C._lazos(camino))
    bordes, huecos = [], []
    for lazo in lazos:
        lazo = C._sin_alineados(list(lazo), pts, originales, tol)
        anillo = [pts[k] for k in lazo]
        a = C.area_con_signo(anillo)
        if abs(a) <= tol * tol:
            continue
        (bordes if a > 0 else huecos).append((anillo, abs(a)))
    polis = [[b] for b, _a in bordes]
    sup = [a for _b, a in bordes]
    for h, _a in huecos:
        q = C.punto_interior([h])
        dueno = None
        for i, p in enumerate(polis):
            if q is not None and C.dentro_anillo(q, p[0]) and (dueno is None or sup[i] < sup[dueno]):
                dueno = i
        if dueno is not None:
            polis[dueno].append(h)
    return polis


def recortar(hatch, punto, cortadores, paso=None):
    """TRIM: los polígonos que quedan del sombreado sin la parte del clic.

    Devuelve [[borde, huecos...]] (puede ser [] si se borra todo), o None si
    ningún borde de corte atraviesa el sombreado en ese lugar."""
    if paso is None:
        paso = paso_de([hatch])
    rings = anillos(hatch, paso)
    if not rings:
        return None
    H = C._Objeto("H", rings)
    if not H.contiene(punto):
        return None
    tol = max(C.tolerancia({"H": rings}), paso * 1e-3)
    cortes = []
    for e in cortadores:
        for pl in lineas_de(e, paso):
            if len(pl) >= 2:
                cortes.append((pl, False))
    if not cortes:
        return None
    puntos, aristas = _grafo([(r, True) for r in rings] + cortes, tol)
    pts = puntos.xy
    positivas = sorted([(a, s) for a, s in caras(pts, aristas) if s > tol * tol],
                       key=lambda t: t[1])
    f = _cara_de(punto, positivas)
    if f is None:
        return None
    sup_h = sum(s for _a, s in H.partes())

    def dentro(p):
        return H.contiene(p) and _cara_de(p, positivas) != f

    salen = {}
    for u, v in aristas:
        a, b = pts[u], pts[v]
        largo = math.dist(a, b)
        if largo == 0.0:
            continue
        off = min(tol * 0.5, largo * 0.25)
        nx, ny = -(b[1] - a[1]) / largo, (b[0] - a[0]) / largo
        m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        izq = dentro((m[0] + nx * off, m[1] + ny * off))
        der = dentro((m[0] - nx * off, m[1] - ny * off))
        if izq == der:
            continue
        if izq:
            salen.setdefault(u, []).append(v)
        else:
            salen.setdefault(v, []).append(u)
    polis = _encadenar(pts, salen, puntos.originales, tol)
    if not polis:
        return None                       # la cara del clic es todo el sombreado: nada lo corta ahí
    if abs(sum(C.area_con_signo(p[0]) - sum(abs(C.area_con_signo(h)) for h in p[1:]) for p in polis)
           - sup_h) <= sup_h * 1e-9:
        return None                       # no cambió nada
    return polis


# -- el sombreado nuevo ---------------------------------------------------------------------------
def factoria(modelo, polis, extras=()):
    """Un sombreado igual a ``modelo`` (patrón, fondo, Custom, capa...) con los
    bordes de ``polis``; los arcos vuelven a ser arcos."""
    from ezdxf.lldxf.const import BOUNDARY_PATH_EXTERNAL
    fuentes_arcos = list(fuentes(modelo)) + list(extras)

    def factory(msp):
        doc = msp.doc
        nuevo = modelo.copy()
        doc.entitydb.add(nuevo)
        msp.add_entity(nuevo)
        nuevo.paths.clear()
        for p in polis:
            for r in p:
                anillo = S.con_arcos(r, fuentes_arcos) if fuentes_arcos else \
                    [(x, y, 0.0) for x, y in r]
                S.agregar_borde(nuevo, anillo, BOUNDARY_PATH_EXTERNAL)
        try:
            nuevo.dxf.discard("n_seed_points")
            nuevo.set_seed_points([])
        except Exception:  # noqa: BLE001
            pass
        return nuevo
    return factory


# -- JOIN -----------------------------------------------------------------------------------------
def estilo(hatch) -> tuple:
    """Lo que hace igual a dos sombreados (el origen no cuenta: sólo corre las líneas)."""
    d = hatch.dxf
    solido = int(d.get("solid_fill", 0) or 0)
    try:
        fondo = hatch.bgcolor
    except Exception:  # noqa: BLE001
        fondo = None
    r = lambda v: round(float(v or 0.0), 6)
    return (solido, str(d.get("pattern_name", "") or "").upper() if not solido else "SOLID",
            r(d.get("pattern_scale", 1.0)) if not solido else 0.0,
            r(float(d.get("pattern_angle", 0.0) or 0.0) % 360.0) if not solido else 0.0,
            int(d.get("pattern_double", 0) or 0) if not solido else 0,
            int(d.get("color", 256)), d.get("true_color", None), fondo,
            int(d.get("lineweight", -1)))


def superficie(hatch, paso=None) -> float:
    return sum(s for _a, s in C._Objeto("x", anillos(hatch, paso or paso_de([hatch]))).partes())


def plan_unir(hatches, con_el_mayor: bool):
    """[(modelo, miembros, anillos, rellenos)] de las islas que cambian, y la lista
    de los sombreados que quedan aparte por estilo distinto."""
    paso = paso_de(hatches)
    sup = {id(h): superficie(h, paso) for h in hatches}
    if con_el_mayor:
        grupos = [list(hatches)]
    else:
        por = {}
        for h in hatches:
            por.setdefault(estilo(h), []).append(h)
        grupos = list(por.values())
    aparte = [h for g in grupos if len(g) < 2 for h in g]
    cambios = []
    for g in grupos:
        if len(g) < 2:
            continue
        objetos = {i: anillos(h, paso) for i, h in enumerate(g)}
        for isla in C.combinar(objetos):
            if isla["sin_cambio"] or len(isla["miembros"]) < 2:
                continue
            miembros = [g[i] for i in isla["miembros"]]
            modelo = g[isla["jefe"]]          # el de mayor superficie de la isla
            cambios.append((modelo, miembros, isla["anillos"], isla["rellenos"]))
    return cambios, aparte


def orden_unir(cambios):
    from core import actions
    viejos, fabricas = [], []
    for modelo, miembros, anillos_isla, _r in cambios:
        extras = [f for m in miembros for f in fuentes(m)]
        viejos.extend(miembros)
        fabricas.append(factoria(modelo, [anillos_isla], extras))
    return actions.ReplaceEntitiesCommand("JOIN", viejos, fabricas)
