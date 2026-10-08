# SPDX-License-Identifier: GPL-3.0-or-later
"""EMPALME (FILLET) al estilo AutoCAD, para IngeCAD.

El FILLET de IngeCAD hace bien líneas sueltas, arcos y círculos, pero:
  - no acepta polilíneas (y casi todo lo que llega de QGIS son polilíneas);
  - con dos líneas que se cruzan no respeta el lado que se tocó.

Este empalme hereda del nativo todas sus opciones (Deshacer, Polilínea,
Radio, Recortar, Múltiple, Mayús = esquina) y agrega, como AutoCAD:

  - dos tramos contiguos de una misma polilínea: se redondea ese vértice;
  - línea + tramo extremo de una polilínea: quedan unidas en una polilínea;
  - dos polilíneas por sus tramos extremos: quedan unidas en una sola;
  - líneas que se cruzan: se conserva el lado donde se hizo clic.

Con el módulo «Empalme estilo AutoCAD» activo, F / EMPALME / FILLET abren
este empalme; apagado, vuelve el de IngeCAD tal cual.
"""
from __future__ import annotations

import math

from core import actions
from core.i18n import tr
from tools.edit import FilletTool

EPS = 1e-9


# -- geometría pura ------------------------------------------------------------------------
def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > EPS else None


def interseccion(a, b, c, d):
    """Cruce de las rectas AB y CD (infinitas), o None si son paralelas."""
    d1 = (b[0] - a[0], b[1] - a[1])
    d2 = (d[0] - c[0], d[1] - c[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < EPS * max(1.0, math.hypot(*d1) * math.hypot(*d2)):
        return None
    t = ((c[0] - a[0]) * d2[1] - (c[1] - a[1]) * d2[0]) / den
    return (a[0] + t * d1[0], a[1] + t * d1[1])


def lado(p, a, b, pick):
    """Dirección unitaria, desde el cruce p, hacia el lado de la recta AB donde
    está el clic (proyectado sobre la recta)."""
    u = _unit(b[0] - a[0], b[1] - a[1])
    s = (pick[0] - p[0]) * u[0] + (pick[1] - p[1]) * u[1]
    return u if s >= 0 else (-u[0], -u[1])


def lejano(p, u, a, b):
    """El extremo de AB que queda más lejos del cruce hacia u, y esa distancia."""
    da = (a[0] - p[0]) * u[0] + (a[1] - p[1]) * u[1]
    db = (b[0] - p[0]) * u[0] + (b[1] - p[1]) * u[1]
    return (a, da) if da >= db else (b, db)


def esquina(p, u1, u2, radio):
    """El empalme entre dos semirrectas que salen de p hacia u1 y u2.

    Devuelve (t1, t2, centro, bulge, d): puntos de tangencia, centro del arco,
    bulge del arco recorrido de t1 a t2 (para una polilínea que llega por la
    rama 1 y sale por la 2) y distancia d de p a cada tangencia. Con radio 0:
    t1 = t2 = p, sin arco. None si las ramas son colineales."""
    cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    theta = math.acos(cos_t)                     # ángulo entre las ramas
    if theta < 1e-7 or math.pi - theta < 1e-7:
        return None
    if radio <= 0:
        return p, p, None, 0.0, 0.0
    d = radio / math.tan(theta / 2.0)
    t1 = (p[0] + u1[0] * d, p[1] + u1[1] * d)
    t2 = (p[0] + u2[0] * d, p[1] + u2[1] * d)
    bis = _unit(u1[0] + u2[0], u1[1] + u2[1])
    h = radio / math.sin(theta / 2.0)
    centro = (p[0] + bis[0] * h, p[1] + bis[1] * h)
    # se llega por la rama 1 (dirección -u1) y se sale por la 2 (u2)
    giro = (-u1[0]) * u2[1] - (-u1[1]) * u2[0]
    barrido = math.pi - theta
    bulge = math.tan(barrido / 4.0) * (1.0 if giro > 0 else -1.0)
    return t1, t2, centro, bulge, d


def angulos_arco(centro, t1, t2, bulge):
    """(inicio, fin) en grados de un ARC antihorario entre t1 y t2."""
    a1 = math.degrees(math.atan2(t1[1] - centro[1], t1[0] - centro[0]))
    a2 = math.degrees(math.atan2(t2[1] - centro[1], t2[0] - centro[0]))
    return (a1, a2) if bulge > 0 else (a2, a1)


def tramo_cercano(puntos, cerrada, pick):
    """Índice del tramo de la polilínea más cercano al clic."""
    n = len(puntos)
    tramos = n if cerrada else n - 1
    mejor, mejor_d = None, float("inf")
    for i in range(tramos):
        a, b = puntos[i], puntos[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = dx * dx + dy * dy
        t = 0.0 if ll < EPS else max(0.0, min(1.0, ((pick[0] - a[0]) * dx + (pick[1] - a[1]) * dy) / ll))
        d = math.hypot(pick[0] - (a[0] + t * dx), pick[1] - (a[1] + t * dy))
        if d < mejor_d:
            mejor, mejor_d = i, d
    return mejor


def invertir(filas):
    """Filas (x, y, ancho0, ancho1, bulge) de una polilínea abierta, al revés."""
    n = len(filas)
    out = []
    for k in range(n):
        x, y = filas[n - 1 - k][0], filas[n - 1 - k][1]
        prev = filas[n - 2 - k] if k < n - 1 else None
        if prev is None:
            out.append((x, y, 0.0, 0.0, 0.0))
        else:
            out.append((x, y, prev[3], prev[2], -prev[4]))
    return out


def arco_en_tramos(centro, radio, a0, a1, paso=7.5):
    """Un arco antihorario de a0 a a1 (radianes) como segmentos, para dibujarlo."""
    while a1 <= a0:
        a1 += 2 * math.pi
    n = max(2, int(math.degrees(a1 - a0) / paso) + 1)
    pts = [(centro[0] + radio * math.cos(a0 + (a1 - a0) * k / n),
            centro[1] + radio * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    return list(zip(pts[:-1], pts[1:]))


def tramo_en_segmentos(a, b, bulge):
    """Un tramo de polilínea (recto o con bulge) como segmentos."""
    if abs(bulge) <= EPS:
        return [(tuple(a[:2]), tuple(b[:2]))]
    from ezdxf.math import bulge_to_arc

    c, a0, a1, r = bulge_to_arc(a[:2], b[:2], bulge)
    return arco_en_tramos((c.x, c.y), r, a0, a1)


def trazo(entity, pick=None):
    """Lo que se resalta de un objeto: la línea, el arco o el círculo entero;
    de una polilínea, sólo el tramo bajo ``pick`` (o toda, sin pick)."""
    tipo = entity.dxftype()
    if tipo == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        return [((s.x, s.y), (e.x, e.y))]
    if tipo in ("ARC", "CIRCLE"):
        c, r = entity.dxf.center, entity.dxf.radius
        if tipo == "CIRCLE":
            return arco_en_tramos((c.x, c.y), r, 0.0, 2 * math.pi)
        return arco_en_tramos((c.x, c.y), r, math.radians(entity.dxf.start_angle),
                              math.radians(entity.dxf.end_angle))
    if tipo == "LWPOLYLINE":
        filas = [tuple(f) for f in entity.get_points("xyseb")]
        n = len(filas)
        if n < 2:
            return []
        tramos = range(n if entity.closed else n - 1)
        if pick is not None:
            i = tramo_cercano([(f[0], f[1]) for f in filas], entity.closed, pick)
            tramos = [] if i is None else [i]
        out = []
        for i in tramos:
            out += tramo_en_segmentos(filas[i], filas[(i + 1) % n], filas[i][4])
        return out
    return []


# -- la herramienta ------------------------------------------------------------------------
class EmpalmeTool(FilletTool):
    """FILLET de IngeCAD + polilíneas + lado elegido (ver el encabezado)."""

    def start(self) -> None:
        super().start()
        self.name = "FILLET"

    #: lo que cambia entre el empalme y el chaflán (ver chaflan.py)
    NOMBRE = "FILLET"
    NO_ENTRA = "Radius does not fit."
    PROMPT_SEGUNDO = "Select second object or shift-select to apply corner:"
    MSG_TIPO = None              # None: el texto del FILLET de IngeCAD

    def _radio_actual(self, shift=None) -> float:
        """El radio de este empalme: 0 (esquina) con Mayús."""
        shift = getattr(self, "shift", False) if shift is None else shift
        return 0.0 if shift else type(self).radius

    def _esquina(self, p, u1, u2, radio):
        """(t1, t2, centro, bulge, d1, d2) del corte entre las ramas que salen
        de p hacia u1 (primer objeto) y u2 (segundo); None si son colineales."""
        r = esquina(p, u1, u2, radio)
        if r is None:
            return None
        t1, t2, centro, bulge, d = r
        return t1, t2, centro, bulge, d, d

    def _union(self, c, fuente):
        """La pieza que une t1 con t2 (un arco), o None si es una esquina."""
        return self._arco_suelto(c["centro"], c["t1"], c["t2"], c["bulge"], c["radio"], fuente)

    def _paralelas(self, segundo, pick2, radio) -> bool:
        return super()._fillet_lines(segundo, pick2, radio)

    def _otros(self, point):
        """Arcos y círculos: el empalme de IngeCAD."""
        return super().on_point(point)

    def on_point(self, point) -> None:
        if self._await == "polyline":
            return self._polilinea_entera(point)
        entity = self.ctx.services.pick_entity(point)
        tipo = entity.dxftype() if entity is not None else None
        if tipo not in self.TIPOS:
            self.ctx.echo(self.MSG_TIPO or (tr("FILLET joins lines, arcs and circles.") + " "
                                            + "(GeoCAD Yaguareté: también polilíneas)"))
            return
        if self._first is None:
            if tipo == "LWPOLYLINE" and not self._tramo_recto(entity, point):
                return
            self._first, self._first_pick = entity, point
            self.prompt(self.PROMPT_SEGUNDO)
            return
        primero = self._first
        radio = self._radio_actual()
        tipos = {primero.dxftype(), tipo}
        hecho = None
        if entity is primero and tipo == "LWPOLYLINE":
            hecho = self._misma_polilinea(entity, self._first_pick, point, radio)
        elif entity is primero:
            self.ctx.echo(tr("Pick a different object."))
            return
        elif tipos <= {"LINE", "LWPOLYLINE"}:
            if tipo == "LWPOLYLINE" and not self._tramo_recto(entity, point):
                return
            hecho = self._rectos(entity, point, radio)
        elif "LWPOLYLINE" in tipos:
            self.ctx.echo("GeoCAD Yaguareté: una polilínea se empalma con líneas u otras polilíneas, "
                          "no con arcos ni círculos.")
            hecho = False
        else:
            return self._otros(point)
        if hecho:
            self._after_fillet()
        else:
            self._first_prompt() if self._multiple else self.ctx.finish()

    def _polilinea_entera(self, point):
        """Opción Polilínea: la del FILLET de IngeCAD."""
        return FilletTool.on_point(self, point)

    # -- ayudas ------------------------------------------------------------------------
    def _tramo_recto(self, pl, pick) -> bool:
        filas = pl.get_points("xyseb")
        i = tramo_cercano([(f[0], f[1]) for f in filas], pl.closed, pick)
        if i is None or abs(filas[i][4]) > EPS:
            self.ctx.echo("GeoCAD Yaguareté: ese tramo de la polilínea es un arco; elija un tramo recto.")
            return False
        return True

    def _recto(self, entity, pick):
        """(a, b, info) del tramo recto tocado: info = None (línea) o
        (filas, índice) para una polilínea."""
        if entity.dxftype() == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            return (s.x, s.y), (e.x, e.y), None
        filas = [tuple(f) for f in entity.get_points("xyseb")]
        pts = [(f[0], f[1]) for f in filas]
        i = tramo_cercano(pts, entity.closed, pick)
        return pts[i], pts[(i + 1) % len(pts)], (filas, i)

    def _reemplazar(self, olds, fabricas, arco):
        """Como el nativo: con Recortar apagado quedan los originales y sólo
        se agrega el arco."""
        from core import trimmode

        if trimmode.trimmode():
            fabricas = list(fabricas) + ([arco] if arco else [])
        else:
            olds, fabricas = [], ([arco] if arco else [])
        if fabricas:
            self.ctx.execute(actions.ReplaceEntitiesCommand(self.NOMBRE, olds, fabricas))

    def _arco_suelto(self, centro, t1, t2, bulge, radio, fuente):
        from core.modify import inherit_style

        if radio <= 0 or centro is None:
            return None
        a0, a1 = angulos_arco(centro, t1, t2, bulge)
        return lambda msp: inherit_style(msp.add_arc(centro, radio, a0, a1), fuente)

    # -- dos tramos de la misma polilínea ----------------------------------------------
    def _calculo_misma(self, pl, pick1, pick2, radio):
        """Geometría del redondeo de un vértice de la polilínea: dict o texto."""
        filas = [list(f) for f in pl.get_points("xyseb")]
        pts = [(f[0], f[1]) for f in filas]
        n = len(pts)
        i = tramo_cercano(pts, pl.closed, pick1)
        j = tramo_cercano(pts, pl.closed, pick2)
        if i == j:
            return tr("Pick a different object.")
        # el tramo k va del vértice k al k+1: son contiguos si comparten vértice
        if (pl.closed and (i + 1) % n == j) or (not pl.closed and i + 1 == j):
            v = (i + 1) % n
        elif (pl.closed and (j + 1) % n == i) or (not pl.closed and j + 1 == i):
            v = (j + 1) % n
        else:
            return "GeoCAD Yaguareté: elija dos tramos contiguos de la polilínea."
        ant, sig = (v - 1) % n, (v + 1) % n
        if abs(filas[ant][4]) > EPS or abs(filas[v][4]) > EPS:
            return "GeoCAD Yaguareté: uno de los tramos es un arco; elija tramos rectos."
        p = pts[v]
        u_ant = _unit(pts[ant][0] - p[0], pts[ant][1] - p[1])
        u_sig = _unit(pts[sig][0] - p[0], pts[sig][1] - p[1])
        # la rama 1 es la del PRIMER tramo tocado (el chaflán mide ahí la distancia 1)
        primero_ant = (i == ant)
        r = self._esquina(p, u_ant, u_sig, radio) if primero_ant else \
            self._esquina(p, u_sig, u_ant, radio)
        if r is None:
            return "GeoCAD Yaguareté: los tramos están alineados."
        if primero_ant:
            t1, t2, centro, bulge, d_ant, d_sig = r
        else:
            t2, t1, centro, bulge, d_sig, d_ant = r
            bulge = -bulge                    # la polilínea va de ant a sig
        if math.dist(t1, t2) <= EPS:
            return "GeoCAD Yaguareté: con radio (o distancias) 0 ese vértice ya es una esquina."
        if d_ant > math.dist(p, pts[ant]) + 1e-9 or d_sig > math.dist(p, pts[sig]) + 1e-9:
            return tr(self.NO_ENTRA)
        return dict(filas=filas, v=v, p=p, t1=t1, t2=t2, centro=centro, bulge=bulge, radio=radio)

    def _misma_polilinea(self, pl, pick1, pick2, radio) -> bool:
        c = self._calculo_misma(pl, pick1, pick2, radio)
        if isinstance(c, str):
            self.ctx.echo(c)
            return False
        filas, v = c["filas"], c["v"]
        t1, t2, centro, bulge = c["t1"], c["t2"], c["centro"], c["bulge"]
        fila = filas[v]
        nuevas = filas[:v] + [[t1[0], t1[1], fila[2], fila[3], bulge],
                              [t2[0], t2[1], fila[2], fila[3], fila[4]]] + filas[v + 1:]
        from core import trimmode

        if not trimmode.trimmode():
            self._reemplazar([], [], self._union(c, pl))
            return True

        def fabrica(msp, e=pl, rows=nuevas):
            clon = e.copy()
            clon.set_points([tuple(r) for r in rows], format="xyseb")
            msp.add_entity(clon)
            return clon

        self.ctx.execute(actions.ReplaceEntitiesCommand(self.NOMBRE, [pl], [fabrica]))
        return True

    # -- líneas y polilíneas (objetos distintos) ---------------------------------------
    def _calculo_rectos(self, primero, pick1, segundo, pick2, radio):
        """La geometría del empalme entre dos objetos rectos, sin tocar nada.
        Devuelve un dict, un texto (por qué no se puede) o "paralelas" (dos
        líneas paralelas: las resuelve el nativo). La usan el empalme y la
        vista previa, así lo que se ve es lo que va a quedar."""
        a1, b1, info1 = self._recto(primero, pick1)
        a2, b2, info2 = self._recto(segundo, pick2)
        p = interseccion(a1, b1, a2, b2)
        if p is None:
            if info1 is None and info2 is None:
                return "paralelas"
            return "GeoCAD Yaguareté: los tramos son paralelos."

        def rama(a, b, info, pick, ent):
            """Dirección desde el cruce hacia lo que se conserva y el extremo lejano."""
            if info is None:
                u = lado(p, a, b, pick)
                fin, largo = lejano(p, u, a, b)
                return u, fin, largo, None
            filas, i = info
            if ent.closed:
                return None
            n = len(filas)
            if n == 2:
                # un solo tramo: como una línea, se conserva el lado tocado
                # (antes se conservaba siempre el del vértice 1: dependía del
                # sentido en que se dibujó)
                u = lado(p, a, b, pick)
                fin, largo = lejano(p, u, a, b)
                extremo = 1 if math.dist(fin, a) < math.dist(fin, b) else 0
                return u, fin, largo, extremo
            if i == 0:                       # primer tramo: se conserva hacia el vértice 1
                interior = (filas[1][0], filas[1][1])
                extremo = 0
            elif i == n - 2:                 # último tramo: hacia el vértice n-2
                interior = (filas[n - 2][0], filas[n - 2][1])
                extremo = n - 1
            else:
                return None
            u = _unit(interior[0] - p[0], interior[1] - p[1])
            if u is None:
                return None
            tocado = lado(p, a, b, pick)
            if tocado[0] * u[0] + tocado[1] * u[1] < 0:
                # se tocó el lado de afuera: conservarlo cortaría el resto de la polilínea
                return ("GeoCAD Yaguareté: de una polilínea se conserva el lado que sigue hacia el resto "
                        "de la polilínea; toque ese lado (o use PARTEENPUNTO antes).")
            largo = (interior[0] - p[0]) * u[0] + (interior[1] - p[1]) * u[1]
            return u, interior, largo, extremo

        r1 = rama(a1, b1, info1, pick1, primero)
        r2 = rama(a2, b2, info2, pick2, segundo)
        for r in (r1, r2):
            if isinstance(r, str):
                return r
        if r1 is None or r2 is None:
            return ("GeoCAD Yaguareté: de una polilínea abierta se empalma un tramo EXTREMO "
                    "(el primero o el último); las cerradas, por sus vértices.")
        u1, fin1, largo1, ext1 = r1
        u2, fin2, largo2, ext2 = r2
        res = self._esquina(p, u1, u2, radio)
        if res is None:
            return "GeoCAD Yaguareté: los tramos están alineados."
        t1, t2, centro, bulge, d1, d2 = res
        if largo1 < d1 - 1e-9 or largo2 < d2 - 1e-9:
            return tr(self.NO_ENTRA)
        return dict(p=p, info1=info1, info2=info2, fin1=fin1, fin2=fin2, ext1=ext1, ext2=ext2,
                    t1=t1, t2=t2, centro=centro, bulge=bulge, radio=radio)

    def _rectos(self, segundo, pick2, radio) -> bool:
        from core.modify import common_style_source, inherit_style

        primero, pick1 = self._first, self._first_pick
        c = self._calculo_rectos(primero, pick1, segundo, pick2, radio)
        if c == "paralelas":
            return self._paralelas(segundo, pick2, radio)
        if isinstance(c, str):
            self.ctx.echo(c)
            return False
        info1, info2, fin1, fin2 = c["info1"], c["info2"], c["fin1"], c["fin2"]
        ext1, ext2 = c["ext1"], c["ext2"]
        t1, t2, centro, bulge = c["t1"], c["t2"], c["centro"], c["bulge"]
        fuente = common_style_source([primero, segundo])
        arco = self._union(c, fuente)
        hay_union = math.dist(t1, t2) > EPS

        if info1 is None and info2 is None:              # dos líneas
            self._reemplazar(
                [primero, segundo],
                [lambda msp, a=fin1, b=t1: inherit_style(msp.add_line(a, b), primero),
                 lambda msp, a=t2, b=fin2: inherit_style(msp.add_line(a, b), segundo)],
                arco)
            return True

        # con polilínea: todo queda unido en una polilínea (como AutoCAD)
        def filas_hacia_cruce(ent, info, extremo):
            """Las filas de la polilínea orientadas para terminar en el tramo tocado."""
            filas = [tuple(f) for f in info[0]]
            if extremo == 0:
                filas = invertir(filas)
            return [list(f) for f in filas[:-1]]       # sin el vértice que se recorta

        cuerpo = []
        if info1 is None:
            cuerpo.append([fin1[0], fin1[1], 0.0, 0.0, 0.0])
        else:
            cuerpo += filas_hacia_cruce(primero, info1, ext1)
        cuerpo.append([t1[0], t1[1], 0.0, 0.0, bulge if hay_union else 0.0])
        if hay_union:
            cuerpo.append([t2[0], t2[1], 0.0, 0.0, 0.0])
        if info2 is None:
            cuerpo.append([fin2[0], fin2[1], 0.0, 0.0, 0.0])
        else:
            cuerpo += [list(f) for f in self._resto_desde_cruce(info2, ext2)]
        base = primero if info1 is not None else segundo

        from core import trimmode

        if not trimmode.trimmode():
            self._reemplazar([], [], arco)
            return True

        def fabrica(msp, e=base, rows=cuerpo):
            clon = e.copy()
            clon.closed = False
            clon.set_points([tuple(r) for r in rows], format="xyseb")
            msp.add_entity(clon)
            return clon

        self.ctx.execute(actions.ReplaceEntitiesCommand(self.NOMBRE, [primero, segundo], [fabrica]))
        if info1 is not None and info2 is not None:
            self.ctx.echo("GeoCAD Yaguareté: las dos polilíneas quedaron unidas en una.")
        return True

    @staticmethod
    def _resto_desde_cruce(info, extremo):
        """Las filas de la segunda polilínea orientadas para EMPEZAR en el tramo
        tocado, sin el vértice que se recorta."""
        filas = [tuple(f) for f in info[0]]
        if extremo == len(filas) - 1:
            filas = invertir(filas)
        return [list(f) for f in filas[1:]]

    # -- resaltado (lo dibuja dibujo.py sobre la vista de IngeCAD) ----------------------
    TIPOS = ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")

    def _bajo_cursor(self, cursor):
        """El objeto bajo el cursor, sin avanzar el ciclo de selección."""
        s = self.ctx.services
        idx = getattr(s, "index", None)
        if idx is None:
            return None
        tol = getattr(s, "_pick_tolerance", None) or 1.0
        try:
            handles = idx.pick_all(cursor, tol)
        except Exception:  # noqa: BLE001 -- índice reconstruyéndose: sin resaltado
            return None
        for h in handles or ():
            e = idx.entity(h)
            if e is not None and e.is_alive and e.dxftype() in self.TIPOS:
                return e
        return None

    def resaltado(self, cursor) -> dict:
        """Qué resaltar con el cursor en ``cursor`` (coordenadas del espacio):

            elegido  el primer objeto (o tramo) ya tocado: queda marcado
            cursor   el objeto (o tramo) que tomaría un clic ahí
            vista    el arco (o la esquina) que va a quedar, antes del clic

        Todo como listas de segmentos ((x1, y1), (x2, y2))."""
        out = {"elegido": [], "cursor": [], "vista": []}
        primero = self._first
        if primero is not None and getattr(primero, "is_alive", True):
            pick = self._first_pick if primero.dxftype() == "LWPOLYLINE" else None
            out["elegido"] = trazo(primero, pick)
        if cursor is None:
            return out
        e = self._bajo_cursor(cursor)
        if e is None:
            return out
        if self._await == "polyline":
            if e.dxftype() == "LWPOLYLINE":
                out["cursor"] = trazo(e)
            return out
        if e is primero and e.dxftype() != "LWPOLYLINE":
            return out
        out["cursor"] = trazo(e, cursor if e.dxftype() == "LWPOLYLINE" else None)
        if primero is not None:
            out["vista"] = self._vista(primero, e, cursor)
        return out

    def _vista(self, primero, segundo, cursor) -> list:
        """El empalme que dejaría un clic en ``cursor``; [] si no se puede."""
        radio = self._radio_actual(bool(getattr(self.ctx.services, "shift_held", False)))
        tipos = {primero.dxftype(), segundo.dxftype()}
        try:
            if segundo is primero:
                c = self._calculo_misma(primero, self._first_pick, cursor, radio)
            elif tipos <= {"LINE", "LWPOLYLINE"}:
                c = self._calculo_rectos(primero, self._first_pick, segundo, cursor, radio)
            else:
                return []
        except Exception:  # noqa: BLE001 -- geometría degenerada: sin vista previa
            return []
        if not isinstance(c, dict):
            return []
        if math.dist(c["t1"], c["t2"]) > EPS and c["centro"] is None:     # chaflán: el bisel
            return [(tuple(c["t1"]), tuple(c["t2"]))]
        if c["radio"] > 0 and c["centro"] is not None:
            a0, a1 = angulos_arco(c["centro"], c["t1"], c["t2"], c["bulge"])
            return arco_en_tramos(c["centro"], c["radio"], math.radians(a0), math.radians(a1))
        # radio 0: la esquina, desde cada lado hasta el cruce
        p = c["p"]
        return [(tuple(c["fin1"]), p), (p, tuple(c["fin2"]))] if "fin1" in c else []
