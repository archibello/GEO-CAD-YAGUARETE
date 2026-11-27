# SPDX-License-Identifier: GPL-3.0-or-later
"""ESTIRA (STRETCH) al instante y con vista previa, para IngeCAD.

El STRETCH de IngeCAD estira bien, pero:
  - el resultado no se ve al terminar: el dibujo viejo queda en pantalla
    junto al nuevo hasta que se regenera todo el modelo («Regenerando...»).
    Causa: su orden (StretchCommand) no está entre las que la vista sabe
    actualizar al momento (ToolController._patchable), así que no esconde
    la copia vieja y además tira los índices de selección y referencias;
  - mientras se busca el segundo punto sólo se ve una línea elástica: no se
    ve cómo van a quedar los objetos.

Acá, como en AutoCAD:
  - lo que la ventana atrapa entero sigue al cursor (el mismo fantasma que
    usa DESPLAZA: los textos y bloques se ven tal cual);
  - lo que se estira (un lado de un rectángulo, el extremo de una línea o de
    un arco) se dibuja estirado, resaltado, hasta el clic;
  - al hacer clic el resultado queda en el momento, sin regenerar: la orden
    dice qué objetos tocó (``targets``) y la vista esconde los viejos y
    muestra los nuevos, igual que con DESPLAZA o BORRA. DESHACER también.

Sombreados (3.102.0, Fernando: «algo maravilloso sería que "Stretch" pudiera
modificar también los "hatch"»): el STRETCH de IngeCAD no los toca (no les da
puntos). Acá se estiran como una polilínea: atrapado entero, se mueve entero
(con el origen de Custom); en parte, se mueven sólo los vértices que caen en la
ventana, también los de las islas; un lado curvo sigue curvo (su comba, como
en una polilínea). Patrón, estilo, fondo, grosor e islas quedan; un U lo
deshace. Si una isla queda fuera del borde o el borde se cruza, avisa.

Se apaga con el módulo «estirar»: IngeCAD queda como venía.
"""
from __future__ import annotations

import math

from core import modify
from core.i18n import tr
from tools.modify import StretchTool

from .empalme import trazo

#: más objetos que se estiran (no los que se mueven enteros) y la vista
#: previa se deja: copiarlos y estirarlos en cada movimiento del ratón
#: frenaría el cursor en un plano grande
MAX_VISTA = 400


# -- sombreados (3.102.0) ------------------------------------------------------------
def _es_sombreado(e) -> bool:
    try:
        return e.dxftype() == "HATCH"
    except Exception:  # noqa: BLE001
        return False


def _p(v):
    return (float(v[0]), float(v[1]))


def _bordes(hatch):
    """Cada camino del borde: ("poli", camino de polilínea) o ("aristas", camino
    de aristas)."""
    for path in getattr(hatch, "paths", ()) or ():
        yield ("poli" if getattr(path, "vertices", None) is not None else "aristas"), path


def puntos_sombreado(hatch) -> list:
    """Los puntos que STRETCH mira en un sombreado: todos los vértices del borde
    y de las islas (de las aristas, sus puntas; de una elipse o spline, sus
    puntos de control)."""
    from ezdxf.entities.boundary_paths import ArcEdge, EllipseEdge, LineEdge, SplineEdge
    out = []
    for tipo, path in _bordes(hatch):
        if tipo == "poli":
            out += [_p(v) for v in path.vertices]
            continue
        for e in path.edges:
            if isinstance(e, LineEdge):
                out += [_p(e.start), _p(e.end)]
            elif isinstance(e, (ArcEdge, EllipseEdge)):
                out += [_p(e.start_point), _p(e.end_point)]
                if isinstance(e, EllipseEdge):
                    out.append(_p(e.center))
            elif isinstance(e, SplineEdge):
                out += [_p(c) for c in e.control_points]
    return out


def _arco_movido(e, dentro, dx, dy) -> None:
    """Una arista de arco con una de sus puntas movida: queda el arco con la misma
    comba (bulge) entre las puntas nuevas, como en una polilínea."""
    p0, p1 = _p(e.real_start_point), _p(e.real_end_point)
    barrido = (float(e.end_angle) - float(e.start_angle)) % 360.0 or 360.0
    b = math.tan(math.radians(barrido) / 4.0) * (1.0 if e.ccw else -1.0)
    if dentro(p0):
        p0 = (p0[0] + dx, p0[1] + dy)
    if dentro(p1):
        p1 = (p1[0] + dx, p1[1] + dy)
    cx, cy = p1[0] - p0[0], p1[1] - p0[1]
    c = math.hypot(cx, cy)
    if c <= 1e-12 or abs(b) <= 1e-12:
        return
    k = c * (1.0 - b * b) / (4.0 * b)
    centro = ((p0[0] + p1[0]) / 2.0 - cy / c * k, (p0[1] + p1[1]) / 2.0 + cx / c * k)
    r = math.hypot(p0[0] - centro[0], p0[1] - centro[1])
    a0 = math.degrees(math.atan2(p0[1] - centro[1], p0[0] - centro[0])) % 360.0
    a1 = math.degrees(math.atan2(p1[1] - centro[1], p1[0] - centro[0])) % 360.0
    e.center = centro
    e.radius = r
    e.start_angle, e.end_angle = (a0, a1) if e.ccw else (a1, a0)


def mover_origen(hatch, dx: float, dy: float) -> None:
    """El origen guardado de Custom acompaña al sombreado movido entero (el
    patrón ya lo mueve ezdxf; el XDATA no)."""
    from . import sombreado as S
    c = S.leer_custom(hatch)
    if c is not None:
        c["origen"] = (c["origen"][0] + dx, c["origen"][1] + dy)
        S.guardar_custom(hatch, c)


def estirar_sombreado(hatch, rects, dx: float, dy: float) -> bool:
    """STRETCH sobre un sombreado. True si cambió."""
    from ezdxf.entities.boundary_paths import ArcEdge, LineEdge
    puntos = puntos_sombreado(hatch)
    if not puntos:
        return False

    def dentro(p) -> bool:
        return modify._inside(p, rects)

    marcas = [dentro(p) for p in puntos]
    if not any(marcas):
        return False
    if all(marcas):
        def lineas():
            return list(getattr(getattr(hatch, "pattern", None), "lines", None) or ())

        antes = [_p(l.base_point) for l in lineas()]
        modify._move_whole(hatch, dx, dy)
        # IngeCAD 0.7 y anteriores mueven el borde y rehacen el patrón donde estaba:
        # que no se corra (se miran las líneas de ahora, que pueden ser otras)
        for l, b in zip(lineas(), antes):
            if abs(float(l.base_point[0]) - b[0]) < 1e-12 and abs(float(l.base_point[1]) - b[1]) < 1e-12:
                l.base_point = (b[0] + dx, b[1] + dy)
        mover_origen(hatch, dx, dy)
        return True
    # en parte: una elipse o spline con unos puntos adentro y otros no no se
    # puede estirar sin inventarle la forma: el sombreado queda como estaba
    for tipo, path in _bordes(hatch):
        if tipo == "aristas":
            for e in path.edges:
                if not isinstance(e, (LineEdge, ArcEdge)):
                    from ezdxf.entities.boundary_paths import EllipseEdge
                    pts = ([_p(e.start_point), _p(e.end_point), _p(e.center)]
                           if isinstance(e, EllipseEdge) else [_p(c) for c in e.control_points])
                    m = [dentro(q) for q in pts]
                    if any(m) and not all(m):
                        return False
    for tipo, path in _bordes(hatch):
        if tipo == "poli":
            nuevos = []
            for v in path.vertices:
                x, y = float(v[0]), float(v[1])
                bulge = float(v[2]) if len(v) > 2 else 0.0
                if dentro((x, y)):
                    x, y = x + dx, y + dy
                nuevos.append((x, y, bulge))
            path.vertices = nuevos
            continue
        for e in path.edges:
            if isinstance(e, LineEdge):
                s, f = _p(e.start), _p(e.end)
                e.start = (s[0] + dx, s[1] + dy) if dentro(s) else s
                e.end = (f[0] + dx, f[1] + dy) if dentro(f) else f
            elif isinstance(e, ArcEdge):
                a, b = dentro(_p(e.real_start_point)), dentro(_p(e.real_end_point))
                if a and b:
                    c = _p(e.center)
                    e.center = (c[0] + dx, c[1] + dy)
                elif a or b:
                    _arco_movido(e, dentro, dx, dy)
            else:                                   # elipse / spline entera adentro
                from ezdxf.entities.boundary_paths import EllipseEdge
                if isinstance(e, EllipseEdge):
                    c = _p(e.center)
                    e.center = (c[0] + dx, c[1] + dy)
                else:
                    e.control_points = [(float(q[0]) + dx, float(q[1]) + dy) for q in e.control_points]
                    if getattr(e, "fit_points", None):
                        e.fit_points = [(float(q[0]) + dx, float(q[1]) + dy) for q in e.fit_points]
    return True


def lazos_sombreado(hatch, tolerancia: float = 0.01) -> list:
    """Cada camino del borde como polígono (los arcos en tramos)."""
    from ezdxf import path as ezpath
    out = []
    try:
        caminos = ezpath.from_hatch(hatch)
    except Exception:  # noqa: BLE001
        return out
    for c in caminos:
        try:
            pts = [(v.x, v.y) for v in c.flattening(tolerancia)]
        except Exception:  # noqa: BLE001
            continue
        if len(pts) >= 2:
            out.append(pts)
    return out


def tramos_sombreado(hatch) -> list:
    out = []
    for pts in lazos_sombreado(hatch):
        out += list(zip(pts, pts[1:]))
    return out


def _se_cruzan(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = o(c, d, a), o(c, d, b), o(a, b, c), o(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and \
        min(abs(d1), abs(d2), abs(d3), abs(d4)) > 1e-12


#: más tramos que esto y no se revisa si el borde se cruza (sería lento)
MAX_REVISAR = 3000


def problemas(hatch) -> list:
    """Avisos después de estirar: un borde que se cruza solo, o una isla que
    quedó fuera del borde exterior (o lo cruza)."""
    from . import sombreado as S
    lazos = [l for l in lazos_sombreado(hatch, 0.05) if len(l) >= 4]
    avisos = []
    if not lazos or sum(len(l) for l in lazos) > MAX_REVISAR:
        return avisos
    for l in lazos:
        lados = list(zip(l, l[1:]))
        n = len(lados)
        if any(_se_cruzan(*lados[i], *lados[j]) for i in range(n) for j in range(i + 2, n)
               if not (i == 0 and j == n - 1)):
            avisos.append("el borde se cruza")
            break
    exterior = max(lazos, key=lambda l: abs(S.area(l)))
    lados_ext = list(zip(exterior, exterior[1:]))
    for l in lazos:
        if l is exterior:
            continue
        afuera = any(not S.adentro(p, exterior) for p in l[:-1])
        cruza = any(_se_cruzan(*u, *w) for u in zip(l, l[1:]) for w in lados_ext)
        if afuera or cruza:
            avisos.append("una isla quedó fuera del borde")
            break
    return avisos


class EstirarCommand(modify.StretchCommand):
    """El StretchCommand de IngeCAD, diciendo qué objetos toca: con
    ``targets`` la vista los actualiza al momento en vez de regenerar. Además
    estira los sombreados (3.102.0), que el de IngeCAD deja como están."""

    def __init__(self, entities, rects, dx: float, dy: float) -> None:
        super().__init__(entities, rects, dx, dy)
        self.targets = self.entities
        self.avisos: list = []

    def do(self, document) -> None:
        super().do(document)       # la foto para deshacer incluye los sombreados
        self.avisos = []
        for e in self.entities:
            if not _es_sombreado(e):
                continue
            try:
                if estirar_sombreado(e, self.rects, self.dx, self.dy):
                    for a in problemas(e):
                        if a not in self.avisos:
                            self.avisos.append(a)
            except Exception:  # noqa: BLE001 -- un sombreado raro no corta la orden
                pass
        document.dirty = True


def clasificar(entities, rects):
    """(enteros, estirados): los que la ventana atrapa enteros (se mueven) y
    los que tienen sólo algunos puntos adentro (se estiran). Los que no
    tienen ningún punto adentro no cambian y no van en ninguna lista."""
    enteros, estirados = [], []
    for e in entities:
        try:
            puntos = puntos_sombreado(e) if _es_sombreado(e) else modify.stretch_points(e)
        except Exception:  # noqa: BLE001 -- un objeto raro no corta la orden
            continue
        dentro = [modify._inside(p, rects) for p in puntos]
        if not puntos or not any(dentro):
            continue
        (enteros if all(dentro) else estirados).append(e)
    return enteros, estirados


def estirado(entity, rects, dx: float, dy: float) -> list:
    """Los trazos de cómo queda ``entity`` estirado (sobre una copia)."""
    try:
        copia = entity.copy()
        if _es_sombreado(entity):
            estirar_sombreado(copia, rects, dx, dy)
            return tramos_sombreado(copia)
        modify.stretch_entity(copia, rects, dx, dy)
        return trazo(copia)
    except Exception:  # noqa: BLE001 -- sin vista previa, nunca un error
        return []


class EstirarTool(StretchTool):
    """STRETCH de IngeCAD con vista previa y resultado al momento."""

    def start(self) -> None:
        super().start()
        self._estirados: list = []
        self.ghost_entities = None
        self.ghost_base = None

    def on_point(self, point) -> None:
        primero = self._base is None
        super().on_point(point)
        if primero and self._base is not None:
            enteros, self._estirados = clasificar(self._entities, self._rects)
            if len(self._estirados) > MAX_VISTA:
                self._estirados = []
            # lo atrapado entero: el fantasma de DESPLAZA, que sigue al cursor
            self.ghost_entities = enteros or None
            self.ghost_base = self._base

    def resaltado(self, cursor) -> dict:
        """Lo que se estira, ya estirado hasta el cursor."""
        out = {"estirado": []}
        if self._base is None or cursor is None:
            return out
        dx, dy = cursor[0] - self._base[0], cursor[1] - self._base[1]
        for e in self._estirados:
            out["estirado"] += estirado(e, self._rects, dx, dy)
        return out

    def _commit(self, dx: float, dy: float) -> None:
        self.ghost_entities = None
        orden = EstirarCommand(self._entities, self._rects, dx, dy)
        self.ctx.execute(orden)
        self.ctx.echo(tr("{count} stretched.", count=len(self._entities)))
        for a in getattr(orden, "avisos", ()):
            self.ctx.echo(f"Atención: en un sombreado {a}.")
        self.ctx.finish()

