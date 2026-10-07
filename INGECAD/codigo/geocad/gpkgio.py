# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoPackage (.gpkg) con el ``sqlite3`` que trae Python: sin GDAL.

* Geometría: el blob GPKG (cabecera ``GP`` + envolvente) seguido de WKB
  ISO. Se decodifica a partes de coordenadas y se vuelve a codificar
  conservando el tipo (Polygon / MultiPolygon...), las Z/M y el tipo de
  envolvente del original.
* El índice espacial que crean GDAL/QGIS se mantiene con disparadores que
  llaman a ``ST_IsEmpty`` y ``ST_MinX``...``ST_MaxY``. Esas funciones no
  existen en un sqlite3 pelado: se registran acá, y sin ellas ninguna
  escritura procede (falla antes de tocar nada).
* Lectura con la base abierta en sólo lectura; la escritura vive en
  ``gpkg_checkin`` dentro de una transacción.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import math
import re
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .shpio import ShapefileError as DataError  # mismo tipo de error para la GUI

# -- tipos WKB --------------------------------------------------------------------

POINT, LINESTRING, POLYGON = 1, 2, 3
MULTIPOINT, MULTILINESTRING, MULTIPOLYGON, COLLECTION = 4, 5, 6, 7
BASE_NAMES = {POINT: "POINT", LINESTRING: "LINESTRING", POLYGON: "POLYGON",
              MULTIPOINT: "MULTIPOINT", MULTILINESTRING: "MULTILINESTRING",
              MULTIPOLYGON: "MULTIPOLYGON", COLLECTION: "GEOMETRYCOLLECTION"}
NAME_TO_BASE = {v: k for k, v in BASE_NAMES.items()}
NAME_TO_BASE["GEOMETRY"] = 0

KIND_OF_BASE = {POINT: "point", MULTIPOINT: "point", LINESTRING: "line",
                MULTILINESTRING: "line", POLYGON: "polygon", MULTIPOLYGON: "polygon"}
SINGLE_OF = {MULTIPOINT: POINT, MULTILINESTRING: LINESTRING, MULTIPOLYGON: POLYGON}
MULTI_OF = {v: k for k, v in SINGLE_OF.items()}

#: tamaño de la envolvente según el código de los flags
_ENV_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}


@dataclass
class GGeom:
    """``parts``: listas de (x, y). En polígonos cada anillo es una parte y
    ``structure[i] = (polígono, anillo)``; el anillo 0 es el exterior."""

    base: int
    has_z: bool = False
    has_m: bool = False
    parts: list = field(default_factory=list)
    z: Optional[list] = None
    m: Optional[list] = None
    structure: Optional[list] = None
    srs_id: int = 0
    env_code: int = 1

    @property
    def is_empty(self) -> bool:
        return not self.parts

    @property
    def kind(self) -> str:
        return KIND_OF_BASE.get(self.base, "other")


# -- decodificar ---------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes, pos: int) -> None:
        self.data, self.pos = data, pos

    def take(self, fmt: str):
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return values


def _wkb_type(code: int):
    """(tipo base, z, m) para códigos ISO (1000/2000/3000) o EWKB."""
    z = m = False
    if code & 0x80000000:
        z = True
    if code & 0x40000000:
        m = True
    code &= 0x0FFFFFFF
    thousands, base = divmod(code, 1000)
    if thousands == 1:
        z = True
    elif thousands == 2:
        m = True
    elif thousands == 3:
        z = m = True
    return base, z, m


def _read_geometry(r: _Reader, out: GGeom, poly_no: list) -> None:
    (order,) = r.take("B")
    e = "<" if order == 1 else ">"
    (code,) = r.take(e + "I")
    base, z, m = _wkb_type(code)
    dims = 2 + z + m

    def coords(n):
        flat = r.take(e + f"{n * dims}d")
        pts, zs, ms = [], [], []
        for i in range(n):
            c = flat[i * dims:(i + 1) * dims]
            pts.append((c[0], c[1]))
            if z:
                zs.append(c[2])
            if m:
                ms.append(c[2 + z])
        return pts, zs, ms

    def add(pts, zs, ms, struct_item=None):
        out.parts.append(pts)
        if out.has_z:
            out.z.append(zs)
        if out.has_m:
            out.m.append(ms)
        if struct_item is not None:
            out.structure.append(struct_item)

    if base == POINT:
        pts, zs, ms = coords(1)
        if not any(math.isnan(v) for v in pts[0]):
            add(pts, zs, ms)
    elif base == LINESTRING:
        (n,) = r.take(e + "I")
        if n:
            add(*coords(n))
    elif base == POLYGON:
        (nrings,) = r.take(e + "I")
        p = poly_no[0]
        for ring in range(nrings):
            (n,) = r.take(e + "I")
            add(*coords(n), (p, ring))
        if nrings:
            poly_no[0] += 1
    elif base in (MULTIPOINT, MULTILINESTRING, MULTIPOLYGON):
        (n,) = r.take(e + "I")
        for _ in range(n):
            _read_geometry(r, out, poly_no)
    else:
        raise DataError(f"geometría {BASE_NAMES.get(base, base)} no soportada")


def parse_blob(blob: bytes) -> GGeom:
    if blob is None:
        return None
    blob = bytes(blob)
    if blob[:2] != b"GP":
        raise DataError("el blob no es una geometría GeoPackage")
    flags = blob[3]
    header_e = "<" if flags & 1 else ">"
    env_code = (flags >> 1) & 0x07
    empty = bool(flags & 0x10)
    (srs_id,) = struct.unpack_from(header_e + "i", blob, 4)
    start = 8 + 8 * _ENV_DOUBLES.get(env_code, 0)
    order = blob[start]
    e = "<" if order == 1 else ">"
    (code,) = struct.unpack_from(e + "I", blob, start + 1)
    base, z, m = _wkb_type(code)
    g = GGeom(base, z, m, [], [] if z else None, [] if m else None,
              [] if base in (POLYGON, MULTIPOLYGON) else None, srs_id, env_code)
    if not empty:
        _read_geometry(_Reader(blob, start), g, [0])
    return g


# -- codificar ----------------------------------------------------------------------

def _type_code(base: int, z: bool, m: bool) -> int:
    return base + (1000 if z else 0) + (2000 if m else 0)


def _coords(g: GGeom, i: int) -> bytes:
    dims = 2 + g.has_z + g.has_m
    vals = []
    for k, (x, y) in enumerate(g.parts[i]):
        vals += [x, y]
        if g.has_z:
            vals.append(g.z[i][k])
        if g.has_m:
            vals.append(g.m[i][k])
    return struct.pack(f"<{len(vals)}d", *vals) if vals else b""


def _wkb(g: GGeom) -> bytes:
    z, m = g.has_z, g.has_m

    def head(base):
        return struct.pack("<BI", 1, _type_code(base, z, m))

    def point(i):
        return head(POINT) + _coords(g, i)

    def line(i):
        return head(LINESTRING) + struct.pack("<I", len(g.parts[i])) + _coords(g, i)

    def polygons():
        groups: dict[int, list[int]] = {}
        for i, (p, _ring) in enumerate(g.structure):
            groups.setdefault(p, []).append(i)
        out = []
        for p in sorted(groups):
            body = head(POLYGON) + struct.pack("<I", len(groups[p]))
            for i in groups[p]:
                body += struct.pack("<I", len(g.parts[i])) + _coords(g, i)
            out.append(body)
        return out

    b = g.base
    if b == POINT:
        if not g.parts:
            nan = [float("nan")] * (2 + z + m)
            return head(POINT) + struct.pack(f"<{len(nan)}d", *nan)
        return point(0)
    if b == LINESTRING:
        return line(0) if g.parts else head(LINESTRING) + struct.pack("<I", 0)
    if b == POLYGON:
        polys = polygons()
        if not polys:
            return head(POLYGON) + struct.pack("<I", 0)
        return polys[0]
    if b == MULTIPOINT:
        return head(MULTIPOINT) + struct.pack("<I", len(g.parts)) + b"".join(
            point(i) for i in range(len(g.parts)))
    if b == MULTILINESTRING:
        return head(MULTILINESTRING) + struct.pack("<I", len(g.parts)) + b"".join(
            line(i) for i in range(len(g.parts)))
    if b == MULTIPOLYGON:
        polys = polygons()
        return head(MULTIPOLYGON) + struct.pack("<I", len(polys)) + b"".join(polys)
    raise DataError(f"no se puede escribir {BASE_NAMES.get(b, b)}")


def encode_blob(g: GGeom) -> bytes:
    """Blob GPKG little-endian. Envolvente: la misma clase que traía el
    original (sin envolvente para puntos, como GDAL)."""
    empty = g.is_empty
    env_code = 0 if (empty or g.base == POINT) else g.env_code
    env = b""
    if env_code:
        pts = [p for part in g.parts for p in part]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        vals = [min(xs), max(xs), min(ys), max(ys)]
        if env_code in (2, 4):
            zs = [v for part in g.z for v in part] if g.z else [0.0]
            vals += [min(zs), max(zs)]
        if env_code in (3, 4):
            ms = [v for part in g.m for v in part] if g.m else [0.0]
            vals += [min(ms), max(ms)]
        env = struct.pack(f"<{len(vals)}d", *vals)
    flags = 0x01 | (env_code << 1) | (0x10 if empty else 0)
    return b"GP" + bytes((0, flags)) + struct.pack("<i", g.srs_id) + env + _wkb(g)


def blob_bounds(blob):
    """(minx, maxx, miny, maxy) o None si vacía."""
    g = parse_blob(blob)
    if g is None or g.is_empty:
        return None
    pts = [p for part in g.parts for p in part]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


# -- funciones SQL del índice espacial ----------------------------------------------

def _bound(index):
    def fn(blob):
        if blob is None:
            return None
        try:
            b = blob_bounds(blob)
        except Exception:
            return None
        return None if b is None else b[index]
    return fn


def _is_empty(blob):
    if blob is None:
        return 1
    try:
        g = parse_blob(blob)
    except Exception:
        return 1
    return 1 if g.is_empty else 0


def _geometry_type(blob):
    try:
        return BASE_NAMES.get(parse_blob(blob).base)
    except Exception:
        return None


def _srid(blob):
    try:
        return parse_blob(blob).srs_id
    except Exception:
        return None


def _is_assignable(expected, actual):
    expected, actual = (expected or "").upper(), (actual or "").upper()
    if expected == "GEOMETRY" or expected == actual:
        return 1
    if expected == "MULTIPOINT" and actual == "POINT":
        return 1
    if expected == "MULTILINESTRING" and actual == "LINESTRING":
        return 1
    if expected == "MULTIPOLYGON" and actual == "POLYGON":
        return 1
    return 0


def register_functions(conn: sqlite3.Connection) -> None:
    det = {"deterministic": True}
    conn.create_function("ST_IsEmpty", 1, _is_empty, **det)
    conn.create_function("ST_MinX", 1, _bound(0), **det)
    conn.create_function("ST_MaxX", 1, _bound(1), **det)
    conn.create_function("ST_MinY", 1, _bound(2), **det)
    conn.create_function("ST_MaxY", 1, _bound(3), **det)
    conn.create_function("ST_GeometryType", 1, _geometry_type, **det)
    conn.create_function("ST_SRID", 1, _srid, **det)
    conn.create_function("GPKG_IsAssignable", 2, _is_assignable, **det)


def connect(path, readonly: bool = True) -> sqlite3.Connection:
    p = Path(path).resolve()
    if readonly:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(str(p), timeout=10, isolation_level=None)
    register_functions(conn)
    return conn


def q(name: str) -> str:
    """Identificador SQL entre comillas."""
    return '"' + name.replace('"', '""') + '"'


# -- columnas y valores ---------------------------------------------------------------

@dataclass(frozen=True)
class Column:
    name: str
    type: str          # declarado, en mayúsculas: TEXT(20), INTEGER, REAL, DATE...
    notnull: bool
    default: object

    @property
    def family(self) -> str:
        t = self.type
        if t.startswith(("TEXT", "VARCHAR", "CHAR")):
            return "text"
        if t in ("BOOLEAN", "BOOL"):
            return "bool"
        if t in ("INTEGER", "INT", "MEDIUMINT", "SMALLINT", "TINYINT", "BIGINT"):
            return "int"
        if t in ("REAL", "DOUBLE", "FLOAT", "NUMERIC"):
            return "real"
        if t == "DATE":
            return "date"
        if t == "DATETIME":
            return "datetime"
        if t == "":
            return "text"
        return "other"

    @property
    def max_length(self) -> Optional[int]:
        m = re.match(r"(?:TEXT|VARCHAR|CHAR)\s*\((\d+)\)", self.type)
        return int(m.group(1)) if m else None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.type or 'TEXT'}{', obligatorio' if self.notnull else ''})"

    @property
    def editable(self) -> bool:
        return self.family != "other"


def to_value(col: Column, text: str):
    """Valor para SQLite a partir de lo que escribió el usuario, validado."""
    text = "" if text is None else str(text)
    s = text.strip()
    if s == "":
        if col.notnull:
            raise DataError(f"«{col.name}» es obligatorio")
        return None
    fam = col.family
    if fam == "text":
        n = col.max_length
        if n is not None and len(text) > n:
            raise DataError(f"«{col.name}» admite {n} caracteres; el valor tiene {len(text)}")
        return text
    if fam == "int":
        try:
            num = float(s.replace(",", "."))
        except ValueError:
            raise DataError(f"«{col.name}» es entero: «{text}» no es un número")
        if num != int(num):
            raise DataError(f"«{col.name}» es entero: «{text}» tiene decimales")
        return int(num)
    if fam == "real":
        try:
            num = float(s.replace(",", "."))
        except ValueError:
            raise DataError(f"«{col.name}» es numérico: «{text}» no es un número")
        if not math.isfinite(num):
            raise DataError(f"«{col.name}»: valor no válido")
        return num
    if fam == "bool":
        low = s.lower()
        if low in ("1", "v", "s", "si", "sí", "t", "true", "verdadero", "y"):
            return 1
        if low in ("0", "f", "n", "no", "false", "falso"):
            return 0
        raise DataError(f"«{col.name}» es lógico: use V o F")
    if fam == "date":
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return _dt.datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        raise DataError(f"«{col.name}» es fecha: use DD/MM/AAAA")
    if fam == "datetime":
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return _dt.datetime.strptime(s, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
        if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$", s):
            return s
        raise DataError(f"«{col.name}» es fecha y hora: use DD/MM/AAAA HH:MM")
    raise DataError(f"«{col.name}» ({col.type}) no se puede editar")


def display(col: Column, value) -> str:
    if value is None:
        return ""
    fam = col.family
    if fam == "bool":
        return "Verdadero" if value else "Falso"
    if fam == "date" and isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}$", value):
        y, mth, d = value.split("-")
        return f"{d}/{mth}/{y}"
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)


def _canon(value) -> bytes:
    if value is None:
        return b"N"
    if isinstance(value, bytes):
        return b"B" + value
    if isinstance(value, int):
        return b"I" + str(value).encode()
    if isinstance(value, float):
        return b"F" + repr(value).encode()
    return b"S" + str(value).encode("utf-8", "surrogatepass")


def row_hash(blob, values) -> str:
    h = hashlib.sha1()
    h.update(_canon(None if blob is None else bytes(blob)))
    for v in values:
        h.update(b"\x00|")
        h.update(_canon(v))
    return h.hexdigest()[:20]


# -- capas -----------------------------------------------------------------------------

@dataclass
class Layer:
    path: str
    table: str
    geom_col: str
    geom_type: str      # POINT, MULTIPOLYGON, GEOMETRY...
    srs_id: int
    z_flag: int         # 0 prohibido, 1 obligatorio, 2 opcional
    m_flag: int
    pk: str
    columns: list       # Column, sin la clave ni la geometría
    schema: str         # huella de la estructura de la tabla
    kind: str = "other"

    def select_sql(self, where: str = "") -> str:
        cols = ", ".join(q(c.name) for c in self.columns)
        cols = (", " + cols) if cols else ""
        return f"SELECT {q(self.pk)}, {q(self.geom_col)}{cols} FROM {q(self.table)} {where}"

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name.lower() == name.lower():
                return c
        raise KeyError(name)


def list_layers(conn) -> list[tuple[str, str]]:
    """[(tabla, tipo de geometría)] de las capas vectoriales."""
    rows = conn.execute(
        "SELECT c.table_name, g.geometry_type_name FROM gpkg_contents c "
        "JOIN gpkg_geometry_columns g ON lower(g.table_name) = lower(c.table_name) "
        "WHERE c.data_type = 'features' ORDER BY c.table_name").fetchall()
    return [(r[0], (r[1] or "").upper()) for r in rows]


def open_layer(conn, path, table: str) -> Layer:
    row = conn.execute(
        "SELECT table_name, column_name, geometry_type_name, srs_id, z, m "
        "FROM gpkg_geometry_columns WHERE lower(table_name) = lower(?)", (table,)).fetchone()
    if row is None:
        raise DataError(f"la capa «{table}» no existe en el GeoPackage")
    table, gcol, gtype, srs, zf, mf = row
    info = conn.execute(f"PRAGMA table_info({q(table)})").fetchall()
    pk = [r[1] for r in info if r[5] == 1]
    if len(pk) != 1:
        raise DataError(f"la capa «{table}» no tiene una clave primaria simple")
    pk = pk[0]
    cols = [Column(r[1], (r[2] or "").upper(), bool(r[3]), r[4])
            for r in info if r[1] != pk and r[1].lower() != gcol.lower()]
    schema = hashlib.sha1(repr([tuple(r) for r in info]).encode()).hexdigest()[:20]
    layer = Layer(str(Path(path).resolve()), table, gcol, (gtype or "GEOMETRY").upper(),
                  int(srs), int(zf), int(mf), pk, cols, schema)
    base = NAME_TO_BASE.get(layer.geom_type, -1)
    if base > 0:
        layer.kind = KIND_OF_BASE.get(base, "other")
    elif base == 0:            # GEOMETRY genérica: mira lo que hay
        kinds = set()
        for (blob,) in conn.execute(f"SELECT {q(gcol)} FROM {q(table)} "
                                    f"WHERE {q(gcol)} IS NOT NULL LIMIT 1000"):
            g = parse_blob(blob)
            if not g.is_empty:
                kinds.add(g.kind)
        layer.kind = kinds.pop() if len(kinds) == 1 else "other"
    return layer


def read_rows(conn, layer: Layer, fids=None):
    """{fid: (blob, (valores...))}"""
    if fids is None:
        cur = conn.execute(layer.select_sql())
    else:
        fids = list(fids)
        if not fids:
            return {}
        out = {}
        for i in range(0, len(fids), 500):
            chunk = fids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for r in conn.execute(layer.select_sql(f"WHERE {q(layer.pk)} IN ({marks})"), chunk):
                out[r[0]] = (r[1], tuple(r[2:]))
        return out
    return {r[0]: (r[1], tuple(r[2:])) for r in cur}


def srs_info(conn, srs_id: int):
    row = conn.execute("SELECT organization, organization_coordsys_id, definition "
                       "FROM gpkg_spatial_ref_sys WHERE srs_id = ?", (srs_id,)).fetchone()
    return row
