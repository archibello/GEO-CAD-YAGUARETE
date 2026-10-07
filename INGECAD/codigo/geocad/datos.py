# SPDX-License-Identifier: GPL-3.0-or-later
"""La "base de datos" de una capa conectada, sin Qt: lo que muestran la
tabla de atributos, las consultas, el temático y los rótulos.

* :class:`LayerData` junta los registros del archivo (SHP o GPKG) con los
  cambios pendientes del dibujo y los objetos nuevos aún sin guardar.
* :func:`parse_query` interpreta consultas en castellano o inglés:

      MANZANA = 12 Y SUP_M2 > 500
      TITULAR CONTIENE 'pérez' O PARTIDA EMPIEZA '01-'
      FECHA ENTRE 01/01/2024 Y 31/12/2024
      NO (EDIFICADO = V) Y OBS NO ES NULO

  Se evalúa en Python sobre los valores (con los pendientes aplicados):
  nunca se arma SQL con lo que escribe el usuario.
* Consultas por ubicación sobre la geometría actual del dibujo.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field

from . import enlace, shpio


# -- campos y valores ------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    name: str
    label: str
    family: str            # text int real date datetime bool other
    editable: bool
    required: bool = False


def _shp_family(f) -> str:
    if f.type == "C":
        return "text"
    if f.type in "NF":
        return "int" if (f.type == "N" and f.decimals == 0) else "real"
    if f.type == "D":
        return "date"
    if f.type == "L":
        return "bool"
    return "other"


def parse_date(text: str):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def typed(family: str, value):
    """Valor de Python comparable para un valor del archivo o un texto pendiente."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if family != "text" and s == "":
            return None
        if family == "int":
            try:
                return int(float(s.replace(",", ".")))
            except ValueError:
                return None
        if family == "real":
            try:
                return float(s.replace(",", "."))
            except ValueError:
                return None
        if family == "date":
            return parse_date(s)
        if family == "datetime":
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    return _dt.datetime.strptime(s[:19] + ("Z" if fmt.endswith("Z") else ""), fmt)
                except ValueError:
                    continue
            return s
        if family == "bool":
            low = s.lower()
            if low in ("1", "v", "s", "si", "sí", "t", "true", "verdadero", "y"):
                return True
            if low in ("0", "f", "n", "no", "false", "falso"):
                return False
            return None
        return value
    if family == "bool":
        return bool(value)
    if family == "date" and isinstance(value, _dt.date):
        return value
    return value


def show(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Verdadero" if value else "Falso"
    if isinstance(value, _dt.datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, _dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


@dataclass
class Row:
    fid: int
    values: dict                      # nombre -> valor de Python (pendientes aplicados)
    pending: set = field(default_factory=set)   # campos con cambios sin guardar
    new: bool = False                 # objeto nuevo aún no guardado
    connected: bool = True            # dibujado en esta conexión (se puede editar)


class LayerData:
    """Registros de una capa conectada + lo pendiente del dibujo."""

    def __init__(self, document, key: str) -> None:
        self.key = key
        self.link = enlace.read_links(document.doc)[key]
        self.fields: list[Field] = []
        self.rows: list[Row] = []
        self._load(document)

    def _load(self, document) -> None:
        link = self.link
        raw: dict[int, dict] = {}
        if link.fmt == "gpkg":
            from . import gpkgio as G

            conn = G.connect(link.path)
            try:
                layer = G.open_layer(conn, link.path, link.table)
                rows = G.read_rows(conn, layer)
            finally:
                conn.close()
            for c in layer.columns:
                fam = c.family
                self.fields.append(Field(c.name, c.label, fam, c.editable,
                                         c.notnull and c.default is None))
            for fid, (_blob, values) in rows.items():
                raw[fid] = {c.name: typed(c.family, v) if c.family in ("date", "datetime", "bool")
                            else v for c, v in zip(layer.columns, values)}
        else:
            sf = shpio.Shapefile(link.path)
            for f in sf.fields:
                dec = f".{f.decimals}" if f.decimals else ""
                self.fields.append(Field(f.name, f"{f.name} ({f.type}{f.size}{dec})",
                                         _shp_family(f), f.type in "CNFDL"))
            for fid in range(len(sf)):
                if not sf.is_deleted(fid):
                    raw[fid] = sf.attributes(fid)
        fam = {f.name: f.family for f in self.fields}
        tagged, _untagged = enlace.linked_entities(document, self.key)
        new_ids = sorted({t.fid for t, _e in tagged if t.fid < 0}, reverse=True)
        for fid in sorted(raw):
            values = dict(raw[fid])
            pend = link.pending.get(fid, {})
            for name, text in pend.items():
                values[name] = typed(fam.get(name, "text"), text)
            self.rows.append(Row(fid, values, set(pend), connected=fid in link.hashes))
        for fid in new_ids:
            pend = link.pending.get(fid, {})
            values = {f.name: typed(f.family, pend.get(f.name)) for f in self.fields}
            self.rows.append(Row(fid, values, set(pend), new=True))

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name.lower() == name.lower():
                return f
        raise KeyError(name)

    def row(self, fid: int):
        for r in self.rows:
            if r.fid == fid:
                return r
        return None

    def validate(self, name: str, text: str) -> None:
        """Lanza ShapefileError si el valor no entra en el campo."""
        from .fuentes import source_for

        src = source_for(self.link)
        src.validate(self.field(name).name, text)

    def entities_by_fid(self, document) -> dict:
        out: dict[int, list] = {}
        tagged, _ = enlace.linked_entities(document, self.key)
        for tag, e in tagged:
            out.setdefault(tag.fid, []).append(e)
        return out


def fid_label(fid: int) -> str:
    return "nuevo" if fid < 0 else str(fid)


# -- lenguaje de consulta ---------------------------------------------------------------

class QueryError(ValueError):
    pass


_TOKEN = re.compile(r"""
    \s*(?:
      (?P<num>-?\d+(?:[.,]\d+)?(?![\w/-]))         |
      (?P<date>\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}) |
      '(?P<s1>[^']*)'  |  "(?P<s2>[^"]*)"           |
      \[(?P<br>[^\]]+)\]                             |
      (?P<op><>|!=|>=|<=|==|=|<|>)                   |
      (?P<par>[()])                                  |
      (?P<word>[^\s()'"=<>!\[\]]+)
    )""", re.X)

_WORDS = {
    "y": "AND", "and": "AND", "o": "OR", "or": "OR", "no": "NOT", "not": "NOT",
    "contiene": "CONTAINS", "contains": "CONTAINS", "like": "CONTAINS",
    "empieza": "STARTS", "comienza": "STARTS", "starts": "STARTS",
    "termina": "ENDS", "ends": "ENDS",
    "es": "IS", "is": "IS", "nulo": "NULL", "null": "NULL", "vacio": "NULL", "vacío": "NULL",
    "entre": "BETWEEN", "between": "BETWEEN",
    "verdadero": "TRUE", "true": "TRUE", "falso": "FALSE", "false": "FALSE",
}


def _tokenize(text: str):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise QueryError(f"no entiendo «{text[pos:pos + 15]}»")
        pos = m.end()
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "num":
            out.append(("NUM", float(val.replace(",", "."))))
        elif kind == "date":
            out.append(("DATE", parse_date(val)))
        elif kind in ("s1", "s2"):
            out.append(("STR", val))
        elif kind == "br":
            out.append(("ID", val.strip()))
        elif kind == "op":
            out.append(("OP", {"==": "=", "<>": "!="}.get(val, val)))
        elif kind == "par":
            out.append((val, val))
        else:
            w = _WORDS.get(val.lower())
            out.append((w, val) if w else ("ID", val))
    return out


class _Parser:
    def __init__(self, tokens, fields) -> None:
        self.t, self.i = tokens, 0
        self.fields = {f.name.lower(): f for f in fields}

    def peek(self, *kinds):
        return self.i < len(self.t) and self.t[self.i][0] in kinds

    def take(self, *kinds):
        if not self.peek(*kinds):
            got = self.t[self.i][1] if self.i < len(self.t) else "el final"
            names = {"ID": "un campo", "NUM": "un número", "STR": "un texto", "DATE": "una fecha",
                     "AND": "Y", "NULL": "NULO", ")": "«)»", "(": "«(»"}
            want = " o ".join(dict.fromkeys(names.get(k, k) for k in kinds))
            raise QueryError(f"se esperaba {want} y vino «{got}»")
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.i != len(self.t):
            raise QueryError(f"sobra «{self.t[self.i][1]}»")
        return node

    def expr(self):
        node = self.term()
        while self.peek("OR"):
            self.take("OR")
            node = ("or", node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek("AND"):
            self.take("AND")
            node = ("and", node, self.factor())
        return node

    def factor(self):
        if self.peek("NOT"):
            self.take("NOT")
            return ("not", self.factor())
        if self.peek("("):
            self.take("(")
            node = self.expr()
            self.take(")")
            return node
        return self.comparison()

    def literal(self):
        kind, val = self.take("NUM", "STR", "DATE", "TRUE", "FALSE", "ID")
        if kind == "TRUE":
            return True
        if kind == "FALSE":
            return False
        if kind == "ID":            # palabra suelta: texto sin comillas (p. ej. V, F)
            return val
        return val

    def comparison(self):
        _k, name = self.take("ID")
        f = self.fields.get(name.lower())
        if f is None:
            raise QueryError(f"no hay un campo «{name}»")
        if self.peek("IS"):
            self.take("IS")
            neg = False
            if self.peek("NOT"):
                self.take("NOT")
                neg = True
            self.take("NULL")
            return ("notnull" if neg else "null", f)
        if self.peek("NOT"):              # CAMPO NO CONTIENE / NO ES NULO
            self.take("NOT")
            if self.peek("IS"):
                self.take("IS")
                self.take("NULL")
                return ("notnull", f)
            return ("not", self._op(f))
        return self._op(f)

    def _op(self, f):
        if self.peek("OP"):
            _k, op = self.take("OP")
            return ("cmp", f, op, self._coerce(f, self.literal()))
        if self.peek("CONTAINS", "STARTS", "ENDS"):
            kind, _v = self.take("CONTAINS", "STARTS", "ENDS")
            return (kind.lower(), f, str(self.literal()))
        if self.peek("BETWEEN"):
            self.take("BETWEEN")
            lo = self._coerce(f, self.literal())
            self.take("AND")
            hi = self._coerce(f, self.literal())
            return ("between", f, lo, hi)
        raise QueryError(f"después de «{f.name}» va un operador (=, >, CONTIENE, ES NULO...)")

    def _coerce(self, f, value):
        fam = f.family
        if fam in ("int", "real"):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
            try:
                return float(str(value).replace(",", "."))
            except ValueError:
                raise QueryError(f"«{f.name}» es numérico: «{value}» no es un número")
        if fam == "date":
            if isinstance(value, _dt.date):
                return value
            d = parse_date(str(value))
            if d is None:
                raise QueryError(f"«{f.name}» es fecha: use DD/MM/AAAA")
            return d
        if fam == "bool":
            if isinstance(value, bool):
                return value
            t = typed("bool", str(value))
            if t is None:
                raise QueryError(f"«{f.name}» es lógico: use V o F")
            return t
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)


def parse_query(text: str, fields):
    """Devuelve una función ``row -> bool``. QueryError si no se entiende."""
    if not text or not text.strip():
        return lambda row: True
    tree = _Parser(_tokenize(text), fields).parse()

    def norm(v):
        return v.casefold() if isinstance(v, str) else v

    def ev(node, row):
        op = node[0]
        if op == "and":
            return ev(node[1], row) and ev(node[2], row)
        if op == "or":
            return ev(node[1], row) or ev(node[2], row)
        if op == "not":
            return not ev(node[1], row)
        f = node[1]
        v = row.values.get(f.name)
        if op == "null":
            return v is None or v == ""
        if op == "notnull":
            return not (v is None or v == "")
        if v is None:
            return False
        if op in ("contains", "starts", "ends"):
            s, needle = show(v).casefold(), node[2].casefold()
            return (needle in s if op == "contains" else
                    s.startswith(needle) if op == "starts" else s.endswith(needle))
        if op == "between":
            try:
                return node[2] <= v <= node[3]
            except TypeError:
                return False
        cmpop, lit = node[2], node[3]
        a, b = norm(v), norm(lit)
        if isinstance(a, _dt.datetime) and isinstance(b, _dt.date) and not isinstance(b, _dt.datetime):
            a = a.date()
        try:
            return {"=": a == b, "!=": a != b, ">": a > b, "<": a < b,
                    ">=": a >= b, "<=": a <= b}[cmpop]
        except TypeError:
            return False

    return lambda row: ev(tree, row)


# -- geometría del dibujo y consultas por ubicación ------------------------------------------

def entity_rings(e):
    """Lista de (puntos, cerrado) que describen la entidad en planta."""
    from .checkin import GeometryError, entity_vertices

    t = e.dxftype()
    if t == "CIRCLE":
        c, r = e.dxf.center, e.dxf.radius
        n = 72
        pts = [(c.x + r * math.cos(2 * math.pi * k / n), c.y + r * math.sin(2 * math.pi * k / n))
               for k in range(n)]
        return [(pts, True)]
    try:
        pts, closed, _z, _a = entity_vertices(e)
    except GeometryError:
        return []
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts, closed = pts[:-1], True
    return [(pts, closed)]


def point_in_ring(pt, ring) -> bool:
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def _segments(pts, closed):
    segs = list(zip(pts, pts[1:]))
    if closed and len(pts) > 2:
        segs.append((pts[-1], pts[0]))
    return segs


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _cross(segs_a, segs_b) -> bool:
    from .checkin import _segments_intersect

    for a in segs_a:
        for b in segs_b:
            if _segments_intersect(a[0], a[1], b[0], b[1]):
                return True
    return False


def relation(feature_rings, zone_rings, mode: str, distance: float = 0.0) -> bool:
    """¿Cumple el objeto (sus partes) la condición respecto de la zona?
    ``mode``: "dentro", "toca" o "distancia"."""
    zone_polys = [pts for pts, closed in zone_rings if closed and len(pts) >= 3]
    zone_segs = [s for pts, closed in zone_rings for s in _segments(pts, closed)]
    if not zone_segs and mode != "distancia":
        return False

    def inside_zone(p):
        return any(point_in_ring(p, poly) for poly in zone_polys)

    feat_segs = [s for pts, closed in feature_rings for s in _segments(pts, closed)]
    feat_pts = [p for pts, _c in feature_rings for p in pts]
    if not feat_pts:
        return False
    if mode == "dentro":
        return (bool(zone_polys) and all(inside_zone(p) for p in feat_pts)
                and not _cross(feat_segs, zone_segs))
    touches = (any(inside_zone(p) for p in feat_pts)
               or _cross(feat_segs, zone_segs)
               or any(point_in_ring(zp, pts) for pts, closed in feature_rings if closed
                      for zpoly in zone_polys for zp in zpoly[:1]))
    if mode == "toca":
        return touches
    if touches:
        return True
    zone_pts = [p for pts, _c in zone_rings for p in pts]
    best = math.inf
    for p in feat_pts:
        for a, b in zone_segs or [(q, q) for q in zone_pts]:
            best = min(best, _seg_dist(p, a, b))
    for p in zone_pts:
        for a, b in feat_segs or [(q, q) for q in feat_pts]:
            best = min(best, _seg_dist(p, a, b))
    return best <= distance


def spatial_select(document, key: str, zone_entities, mode: str, distance: float = 0.0):
    """FIDs de la capa que cumplen la relación con alguna de las zonas."""
    zone = [r for e in zone_entities for r in entity_rings(e)]
    out = set()
    tagged, _ = enlace.linked_entities(document, key)
    by_fid: dict[int, list] = {}
    for tag, e in tagged:
        by_fid.setdefault(tag.fid, []).append(e)
    for fid, ents in by_fid.items():
        rings = [r for e in ents for r in entity_rings(e)]
        if relation(rings, zone, mode, distance):
            out.add(fid)
    return out


def label_point(rings):
    """Un punto para el rótulo: dentro del polígono (no en un hueco), en la
    mitad de una línea, o el punto mismo."""
    closed = [pts for pts, c in rings if c and len(pts) >= 3]
    if closed:
        from . import shpio as S

        outer = max(closed, key=lambda r: abs(S.signed_area(r)))
        holes = [r for r in closed if r is not outer and point_in_ring(r[0], outer)]
        a = S.signed_area(outer)
        cx = cy = 0.0
        n = len(outer)
        for i in range(n):
            x1, y1 = outer[i]
            x2, y2 = outer[(i + 1) % n]
            f = x1 * y2 - x2 * y1
            cx += (x1 + x2) * f
            cy += (y1 + y2) * f
        c = (cx / (6 * a), cy / (6 * a)) if a else outer[0]
        if point_in_ring(c, outer) and not any(point_in_ring(c, h) for h in holes):
            return c
        # el centro cae afuera (forma en L, hueco): tramo más ancho a esa altura
        y = c[1]
        xs = []
        for ring in [outer] + holes:
            m = len(ring)
            for i in range(m):
                (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % m]
                if (y1 > y) != (y2 > y):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        pairs = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
        if pairs:
            lo, hi = max(pairs, key=lambda p: p[1] - p[0])
            return ((lo + hi) / 2, y)
        return outer[0]
    for pts, _c in rings:
        if len(pts) == 1:
            return pts[0]
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if acc + seg >= total / 2 and seg > 0:
                t = (total / 2 - acc) / seg
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            acc += seg
        return pts[0]
    return None


# -- medidas -------------------------------------------------------------------------------

def feature_measures(entities):
    """(área, longitud) de un objeto: polígonos restan sus huecos."""
    from . import shpio as S

    rings = [pts for e in entities for pts, closed in entity_rings(e) if closed and len(pts) >= 3]
    area = 0.0
    for r in rings:
        # un anillo dentro de otro anillo del mismo objeto es un hueco
        hole = any(o is not r and point_in_ring(r[0], o) for o in rings)
        area += -abs(S.signed_area(r)) if hole else abs(S.signed_area(r))
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                 for e in entities for pts, closed in entity_rings(e)
                 for a, b in _segments(pts, closed))
    return area, length


# -- estado de la tabla (sin Qt: el panel sólo lo dibuja) ---------------------------------------

class TableState:
    """Filas visibles, columnas, orden y filtro de la tabla de atributos."""

    def __init__(self, document, key: str) -> None:
        self.document = document
        self.key = key
        self.query = ""
        self.only_selected = None          # set de fids o None
        self.only_connected = True         # conexión parcial: sólo lo conectado
        self.sort_col = 0
        self.sort_desc = False
        self.reload()

    def reload(self) -> None:
        self.data = LayerData(self.document, self.key)
        self.ents = self.data.entities_by_fid(self.document)
        kinds = self.data.link.kind
        self.measure = {"polygon": "Área", "line": "Longitud"}.get(kinds)
        self.columns = ["FID"] + [f.name for f in self.data.fields] + \
            ([self.measure] if self.measure else [])
        self._measures = {}
        if self.measure:
            for fid, ents in self.ents.items():
                a, l = feature_measures(ents)
                self._measures[fid] = a if self.measure == "Área" else l
        self.apply()

    def set_query(self, text: str) -> None:
        test = parse_query(text, self.data.fields)       # QueryError si no se entiende
        self.query = text
        self._test = test
        self.apply()

    def apply(self) -> None:
        test = getattr(self, "_test", None) or parse_query(self.query, self.data.fields)
        rows = [r for r in self.data.rows if test(r)]
        if self.only_connected:
            rows = [r for r in rows if r.connected or r.new]
        if self.only_selected is not None:
            rows = [r for r in rows if r.fid in self.only_selected]
        rows.sort(key=lambda r: self._sort_key(r), reverse=self.sort_desc)
        self.rows = rows

    def _sort_key(self, r):
        v = self.value(r, self.sort_col)
        if v is None or v == "":
            return (1, 0, "")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (0, 0, v)
        return (0, 1, show(v).casefold())

    def sort(self, col: int, desc: bool) -> None:
        self.sort_col, self.sort_desc = col, desc
        self.apply()

    # celdas
    def field_of(self, col: int):
        if 1 <= col <= len(self.data.fields):
            return self.data.fields[col - 1]
        return None

    def value(self, row: Row, col: int):
        if col == 0:
            return row.fid
        f = self.field_of(col)
        if f is not None:
            return row.values.get(f.name)
        return self._measures.get(row.fid)

    def text(self, row: Row, col: int) -> str:
        if col == 0:
            return fid_label(row.fid)
        v = self.value(row, col)
        if col > len(self.data.fields):
            return "" if v is None else f"{v:,.2f}".replace(",", " ")
        return show(v)

    def is_pending(self, row: Row, col: int) -> bool:
        f = self.field_of(col)
        return row.new or (f is not None and f.name in row.pending)

    def editable(self, col: int) -> bool:
        f = self.field_of(col)
        return f is not None and f.editable

    def cell_editable(self, row: Row, col: int) -> bool:
        """Sólo se editan registros conectados (o nuevos): los demás no tienen
        con qué controlar conflictos al guardar."""
        return self.editable(col) and (row.connected or row.new)

    def summary(self, selected_fids=()) -> str:
        sel = [r for r in self.rows if r.fid in set(selected_fids)]
        pend = sum(1 for r in self.data.rows if r.pending or r.new)
        conn = sum(1 for r in self.data.rows if r.connected)
        parts = [f"{len(self.rows)} de {len(self.data.rows)} registros"]
        if conn < len(self.data.rows):
            parts.append(f"{conn} conectados")
        if sel:
            parts.append(f"{len(sel)} seleccionados")
            if self.measure:
                total = sum(self._measures.get(r.fid, 0.0) for r in sel)
                parts.append(f"{self.measure.lower()} seleccionada: {total:,.2f}".replace(",", " "))
        if pend:
            parts.append(f"{pend} con cambios sin guardar")
        return " · ".join(parts)
