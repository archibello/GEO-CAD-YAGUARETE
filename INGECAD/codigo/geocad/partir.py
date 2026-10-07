# SPDX-License-Identifier: GPL-3.0-or-later
"""PARTEENPUNTO (BREAKATPOINT) al estilo AutoCAD, para IngeCAD.

IngeCAD tiene PARTE (BREAK, dos puntos) pero no «partir en punto», que es la
que se usa todo el tiempo con datos SIG: cortar una línea justo en un cruce,
en el extremo de otra, en un punto medio. Ahí lo principal son las
referencias a objetos, así que esta herramienta:

  - elige el objeto y después el punto de corte CON referencias: además de
    las que estén activas, mientras se elige el punto se suman Punto final,
    Punto medio, Intersección y Cuadrante (si las referencias no están
    apagadas con F3);
  - lleva el punto SOBRE el objeto (proyección): una intersección, el extremo
    de otra línea que no llega o un punto cualquiera cortan exactamente en la
    línea elegida;
  - antes del clic muestra los dos pedazos que van a quedar, en dos colores,
    con el punto de corte y sus largos;
  - opción Múltiple: varios cortes seguidos sobre el mismo objeto, con
    Deshacer de a uno.

Y no tiene los defectos de usar PARTE con el mismo punto dos veces:
  - una polilínea cerrada se ABRE en ese punto (PARTE perdía el tramo de
    cierre);
  - cortar en un vértice no deja un vértice repetido;
  - un tramo en arco se parte en dos arcos exactos (PARTE lo volvía recto);
  - se conservan anchos, elevación, propiedades y el vínculo con QGIS: al
    devolver la capa, un pedazo conserva el registro y el otro pasa a ser un
    registro nuevo con los mismos atributos (como «Dividir objetos» de QGIS).
"""
from __future__ import annotations

import math

from core import actions
from core.i18n import tr
from tools.base import Tool

from .empalme import arco_en_tramos, tramo_en_segmentos, trazo

EPS = 1e-9


# -- geometría pura ------------------------------------------------------------------------
def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1e9 else f"{v:.6g}"


def _sobre_segmento(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll < EPS * EPS else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    q = (a[0] + t * dx, a[1] + t * dy)
    return q, t


def _arco_de_bulge(a, b, bulge):
    """(centro, radio, ángulo de a, barrido con signo) del tramo a->b con bulge."""
    theta = 4.0 * math.atan(bulge)                   # barrido con signo
    cuerda = math.dist(a, b)
    r = cuerda / (2.0 * math.sin(abs(theta) / 2.0))
    m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    h = r * math.cos(abs(theta) / 2.0)               # del punto medio al centro
    u = ((b[0] - a[0]) / cuerda, (b[1] - a[1]) / cuerda)
    n = (-u[1], u[0]) if bulge > 0 else (u[1], -u[0])  # el centro, a la izquierda si antihorario
    if abs(theta) > math.pi:                         # más de media vuelta: el centro cruza
        h = -h
    c = (m[0] + n[0] * h, m[1] + n[1] * h)
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    return c, r, a0, theta


def _sobre_arco(c, r, a0, barrido, p):
    """Punto del arco (desde a0, barrido con signo) más cercano a p, y la
    fracción del barrido donde está."""
    ang = math.atan2(p[1] - c[1], p[0] - c[0])
    d = (ang - a0) if barrido > 0 else (a0 - ang)
    d %= 2 * math.pi
    total = abs(barrido)
    if d <= total:
        f = d / total
    else:                                            # fuera del arco: el extremo más cercano
        f = 0.0 if (2 * math.pi - d) < (d - total) else 1.0
    a = a0 + barrido * f
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), f


def largo_tramo(a, b, bulge) -> float:
    if abs(bulge) <= EPS:
        return math.dist(a[:2], b[:2])
    theta = 4.0 * math.atan(bulge)
    cuerda = math.dist(a[:2], b[:2])
    return abs(theta) * cuerda / (2.0 * math.sin(abs(theta) / 2.0))


def largo_filas(filas, cerrada=False) -> float:
    n = len(filas)
    tramos = range(n if cerrada else n - 1)
    return sum(largo_tramo(filas[i], filas[(i + 1) % n], filas[i][4]) for i in tramos)


def posicion_polilinea(filas, cerrada, p):
    """(distancia, tramo, fracción, punto) del punto de la polilínea (con arcos)
    más cercano a p."""
    n = len(filas)
    mejor = None
    for i in range(n if cerrada else n - 1):
        a, b = filas[i], filas[(i + 1) % n]
        if abs(a[4]) <= EPS or math.dist(a[:2], b[:2]) < EPS:
            q, f = _sobre_segmento(a[:2], b[:2], p)
        else:
            c, r, a0, th = _arco_de_bulge(a[:2], b[:2], a[4])
            q, f = _sobre_arco(c, r, a0, th, p)
        d = math.dist(q, p)
        if mejor is None or d < mejor[0] - 1e-12:
            mejor = (d, i, f, q)
    return mejor


def _ocs_plano(entity) -> bool:
    try:
        z = entity.dxf.get("extrusion", (0, 0, 1))
        return abs(z[0]) < 1e-12 and abs(z[1]) < 1e-12 and z[2] > 0
    except Exception:  # noqa: BLE001
        return True


def piezas(entity, p, tol=1e-7):
    """Lo que queda al partir ``entity`` en (la proyección de) ``p``.

    Devuelve (punto de corte, [piezas]) o un texto con el motivo. Cada pieza:
    ("LINE", a, b) | ("ARC", centro, radio, a0, a1) en grados |
    ("LWPOLYLINE", filas xyseb, cerrada)."""
    tipo = entity.dxftype()
    if tipo == "CIRCLE":
        return ("Un círculo no se parte en un solo punto (como en AutoCAD): "
                "use PARTE con dos puntos.")
    if tipo not in ("LINE", "ARC", "LWPOLYLINE"):
        return f"GeoCAD: {tipo} no se puede partir en un punto."
    extremo = "El punto cae en un extremo: no hay nada que partir."
    if tipo == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        a, b = (s.x, s.y), (e.x, e.y)
        q, t = _sobre_segmento(a, b, p)
        largo = math.dist(a, b)
        if t * largo <= tol or (1 - t) * largo <= tol:
            return extremo
        return q, [("LINE", a, q), ("LINE", q, b)]
    if tipo == "ARC":
        c, r = entity.dxf.center, entity.dxf.radius
        a0 = math.radians(entity.dxf.start_angle)
        a1 = math.radians(entity.dxf.end_angle)
        barrido = (a1 - a0) % (2 * math.pi) or 2 * math.pi
        q, f = _sobre_arco((c.x, c.y), r, a0, barrido, p)
        if f * barrido * r <= tol or (1 - f) * barrido * r <= tol:
            return extremo
        am = math.degrees(a0 + barrido * f)
        return q, [("ARC", (c.x, c.y), r, entity.dxf.start_angle, am),
                   ("ARC", (c.x, c.y), r, am, entity.dxf.end_angle)]
    # polilínea
    filas = [tuple(float(v) for v in f) for f in entity.get_points("xyseb")]
    cerrada = bool(entity.closed)
    n = len(filas)
    if n < 2:
        return "GeoCAD: la polilínea no tiene tramos."
    d, i, f, q = posicion_polilinea(filas, cerrada, p)
    a, b = filas[i], filas[(i + 1) % n]
    largo_i = largo_tramo(a, b, a[4])
    # ¿cae en un vértice? (se corta ahí, sin repetirlo)
    k = None
    if f * largo_i <= tol:
        k = i
    elif (1 - f) * largo_i <= tol:
        k = (i + 1) % n
    if k is not None:
        q = filas[k][:2]
        if not cerrada:
            if k in (0, n - 1):
                return extremo
            cabeza = [list(r) for r in filas[:k + 1]]
            cabeza[-1][4] = 0.0
            cola = [list(r) for r in filas[k:]]
            return q, [("LWPOLYLINE", cabeza, False), ("LWPOLYLINE", cola, False)]
        abierta = [list(r) for r in filas[k:] + filas[:k]] + [list(filas[k])]
        abierta[-1][4] = 0.0
        return q, [("LWPOLYLINE", abierta, False)]
    # en medio de un tramo: arco exacto y ancho interpolado
    theta = 4.0 * math.atan(a[4]) if abs(a[4]) > EPS else 0.0
    b1 = math.tan(theta * f / 4.0) if theta else 0.0
    b2 = math.tan(theta * (1 - f) / 4.0) if theta else 0.0
    w = a[2] + (a[3] - a[2]) * f
    previo = [a[0], a[1], a[2], w, b1]
    corte_fin = [q[0], q[1], 0.0, 0.0, 0.0]
    corte_ini = [q[0], q[1], w, a[3], b2]
    if not cerrada:
        cabeza = [list(r) for r in filas[:i]] + [previo, corte_fin]
        cola = [corte_ini] + [list(r) for r in filas[i + 1:]]
        return q, [("LWPOLYLINE", cabeza, False), ("LWPOLYLINE", cola, False)]
    resto = [list(r) for r in filas[i + 1:] + filas[:i]]
    abierta = [corte_ini] + resto + [previo, corte_fin]
    return q, [("LWPOLYLINE", abierta, False)]


def largo_pieza(pz) -> float:
    if pz[0] == "LINE":
        return math.dist(pz[1], pz[2])
    if pz[0] == "ARC":
        return pz[2] * math.radians((pz[4] - pz[3]) % 360.0)
    return largo_filas(pz[1], pz[2])


def segmentos_pieza(pz) -> list:
    if pz[0] == "LINE":
        return [(tuple(pz[1]), tuple(pz[2]))]
    if pz[0] == "ARC":
        return arco_en_tramos(pz[1], pz[2], math.radians(pz[3]), math.radians(pz[4]))
    filas = pz[1]
    out = []
    for k in range(len(filas) - 1):
        out += tramo_en_segmentos(filas[k], filas[k + 1], filas[k][4])
    return out


def fabrica(entity, pz):
    """Una copia del objeto (capa, color, anchos, elevación, vínculo SIG...)
    con la geometría de la pieza."""
    def construir(msp, e=entity, pz=pz):
        clon = e.copy()
        if pz[0] == "LINE":
            clon.dxf.start = (pz[1][0], pz[1][1], e.dxf.start.z)
            clon.dxf.end = (pz[2][0], pz[2][1], e.dxf.end.z)
        elif pz[0] == "ARC":
            clon.dxf.start_angle, clon.dxf.end_angle = pz[3], pz[4]
        else:
            clon.set_points([tuple(r) for r in pz[1]], format="xyseb")
            clon.closed = pz[2]
        msp.add_entity(clon)
        return clon
    return construir


def poligono_sig(entity) -> bool:
    """¿Es un polígono (polilínea cerrada) vinculado a una capa de QGIS?"""
    if entity.dxftype() != "LWPOLYLINE" or not entity.closed:
        return False
    return _etiqueta_sig(entity)


def _etiqueta_sig(entity) -> bool:
    try:
        from .enlace import feat_tag
    except Exception:  # noqa: BLE001
        return False
    return feat_tag(entity) is not None


# -- la herramienta ------------------------------------------------------------------------
class PartirTool(Tool):
    """PARTEENPUNTO: un objeto, un punto (con referencias) y queda en dos."""

    entity_picker = True
    TIPOS = ("LINE", "ARC", "LWPOLYLINE", "CIRCLE")
    #: referencias que se suman mientras se elige el punto de corte
    REFERENCIAS = frozenset({"END", "MID", "INT", "QUA"})
    PROMPT_PUNTO = "Punto de corte [Múltiple/Deshacer/Objeto]:"

    def start(self) -> None:
        self.name = "BREAKATPOINT"
        self._ent = None
        self._piezas = []            # objetos que se pueden seguir partiendo (Múltiple)
        self._historia = []          # para Deshacer: listas de piezas anteriores
        self._multiple = False
        self._avisado_sig = False
        self.entity_picker = True
        self.prompt("Select object:")

    # -- referencias (las suma dibujo.py a las activas) ----------------------
    def referencias_extra(self) -> frozenset:
        return self.REFERENCIAS if self._ent is not None else frozenset()

    # -- entrada ---------------------------------------------------------------
    def on_option(self, text: str) -> bool:
        t = text.strip().upper().lstrip("_")
        if self._ent is None:
            return False
        if t in ("M", "MULTIPLE", "MÚLTIPLE", "MULTIPLO"):
            self._multiple = True
            self.ctx.echo("Múltiple: cada punto parte el pedazo donde cae. Enter para terminar.")
            self.prompt(self.PROMPT_PUNTO)
            return True
        if t in ("D", "U", "DESHACER", "UNDO"):
            if self._historia:
                self.ctx.undo_last()
                self._piezas = self._historia.pop()
                self.ctx.echo("Se deshizo el último corte.")
            else:
                self.ctx.echo("No hay cortes para deshacer.")
            self.prompt(self.PROMPT_PUNTO)
            return True
        if t in ("O", "OBJETO", "OBJECT"):
            self._ent, self._piezas, self._historia = None, [], []
            self.entity_picker = True
            self.prompt("Select object:")
            return True
        return False

    def on_enter(self) -> None:
        self.ctx.finish()

    def _candidatos(self):
        vivos = [e for e in self._piezas if getattr(e, "is_alive", True)]
        return vivos or ([self._ent] if self._ent is not None else [])

    def _objetivo(self, p):
        """El pedazo (de los que se pueden partir) más cercano a p."""
        mejor = None
        for e in self._candidatos():
            r = piezas(e, p)
            d = math.dist(r[0], p) if not isinstance(r, str) else float("inf")
            if mejor is None or d < mejor[0]:
                mejor = (d, e, r)
        if mejor is None:
            return None, "Nada para partir."
        if math.isinf(mejor[0]):        # ninguno se puede partir ahí: el motivo del más cercano
            return mejor[1], piezas(self._candidatos()[0], p) if len(self._candidatos()) == 1 else mejor[2]
        return mejor[1], mejor[2]

    def on_point(self, point) -> None:
        if self._ent is None:
            services = self.ctx.services
            e = services.pick_entity(point) if services else None
            if e is None:
                self.prompt("Nada designado. Designe objeto:")
                return
            if e.dxftype() not in self.TIPOS:
                self.ctx.echo(f"GeoCAD: {e.dxftype()} no se puede partir en un punto.")
                return
            if e.dxftype() == "CIRCLE":
                self.ctx.echo(piezas(e, point))
                return
            if poligono_sig(e):
                self.ctx.echo("GeoCAD: es un polígono de una capa de QGIS; partirlo en un "
                              "punto lo dejaría abierto (y no sería un polígono).")
                return
            self._ent, self._piezas = e, [e]
            self.entity_picker = False         # el punto, con referencias
            self.prompt(self.PROMPT_PUNTO)
            return
        e, r = self._objetivo(point)
        if isinstance(r, str):
            self.ctx.echo(r)
            self.prompt(self.PROMPT_PUNTO)
            return
        q, pzs = r
        if not _ocs_plano(e):
            # objeto en un plano girado: el corte de IngeCAD (en coordenadas universales)
            from core import modify

            cmd = modify.break_entity(e, q, q)
        else:
            cmd = actions.ReplaceEntitiesCommand("BREAKATPOINT", [e], [fabrica(e, pz) for pz in pzs])
        if cmd is None:
            self.ctx.echo(f"GeoCAD: {e.dxftype()} no se puede partir.")
            self.ctx.finish()
            return
        self.ctx.execute(cmd)
        largos = " y ".join(_fmt(largo_pieza(pz)) for pz in pzs)
        if len(pzs) == 1:
            self.ctx.echo(f"Polilínea abierta en ({_fmt(q[0])}, {_fmt(q[1])}): largo {largos}.")
        else:
            self.ctx.echo(f"Partido en ({_fmt(q[0])}, {_fmt(q[1])}): quedan {largos}.")
        if _etiqueta_sig(e) and not self._avisado_sig:
            self._avisado_sig = True
            self.ctx.echo("Capa de QGIS: al devolver, un pedazo conserva el registro y el otro "
                          "pasa a ser un registro nuevo con los mismos atributos.")
        nuevos = list(getattr(cmd, "new_entities", []) or [])
        self._historia.append(list(self._piezas))
        self._piezas = [x for x in self._piezas if x is not e] + nuevos
        if self._multiple:
            self.prompt(self.PROMPT_PUNTO)
        else:
            self.ctx.finish()

    # -- resaltado (lo dibuja dibujo.py) ---------------------------------------
    def _bajo_cursor(self, cursor):
        s = self.ctx.services
        idx = getattr(s, "index", None)
        if idx is None:
            return None
        tol = getattr(s, "_pick_tolerance", None) or 1.0
        try:
            handles = idx.pick_all(cursor, tol)
        except Exception:  # noqa: BLE001
            return None
        for h in handles or ():
            e = idx.entity(h)
            if e is not None and e.is_alive and e.dxftype() in self.TIPOS[:3]:
                return e
        return None

    def resaltado(self, cursor) -> dict:
        """Antes de elegir: el objeto bajo el cursor. Después: el objeto elegido
        y, con el punto (ya con la referencia) donde está el cursor, los dos
        pedazos que van a quedar, el punto de corte y sus largos."""
        out = {"elegido": [], "cursor": [], "vista": [], "pieza_a": [], "pieza_b": [],
               "puntos": [], "textos": []}
        if cursor is None:
            return out
        if self._ent is None:
            e = self._bajo_cursor(cursor)
            if e is not None and not poligono_sig(e):
                out["cursor"] = trazo(e)
            return out
        for e in self._candidatos():
            out["elegido"] += trazo(e)
        try:
            e, r = self._objetivo(cursor)
        except Exception:  # noqa: BLE001 -- geometría degenerada: sin vista previa
            return out
        if isinstance(r, str):
            return out
        q, pzs = r
        out["pieza_a"] = segmentos_pieza(pzs[0])
        if len(pzs) > 1:
            out["pieza_b"] = segmentos_pieza(pzs[1])
        out["puntos"] = [tuple(q)]
        out["textos"] = [(tuple(q), "  |  ".join(_fmt(largo_pieza(pz)) for pz in pzs))]
        return out
