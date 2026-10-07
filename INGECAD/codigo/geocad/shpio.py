# SPDX-License-Identifier: GPL-3.0-or-later
"""Lectura y escritura de Shapefile (.shp / .shx / .dbf) en Python puro.

Pensado para NO poner en riesgo los datos:

* Cada registro se guarda como los bytes originales del archivo. Un
  registro que no se editó se vuelve a escribir byte por byte igual.
* La cabecera de la .dbf (el esquema: nombres, tipos y anchos de campo)
  se conserva intacta; sólo se actualiza la cantidad de registros.
* Una celda de la .dbf se escribe con el ancho fijo del campo y se valida
  antes: un valor que no entra es un error, nunca se recorta en silencio.

No depende de GDAL ni de pyshp: corre dentro del Flatpak de IngeCAD tal
como viene.
"""
from __future__ import annotations

import codecs
import datetime as _dt
import hashlib
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# -- tipos de geometría ---------------------------------------------------------

NULL = 0
POINT, POLYLINE, POLYGON, MULTIPOINT = 1, 3, 5, 8
POINTZ, POLYLINEZ, POLYGONZ, MULTIPOINTZ = 11, 13, 15, 18
POINTM, POLYLINEM, POLYGONM, MULTIPOINTM = 21, 23, 25, 28
MULTIPATCH = 31

SHAPE_NAMES = {
    NULL: "Null", POINT: "Point", POLYLINE: "PolyLine", POLYGON: "Polygon",
    MULTIPOINT: "MultiPoint", POINTZ: "PointZ", POLYLINEZ: "PolyLineZ",
    POLYGONZ: "PolygonZ", MULTIPOINTZ: "MultiPointZ", POINTM: "PointM",
    POLYLINEM: "PolyLineM", POLYGONM: "PolygonM", MULTIPOINTM: "MultiPointM",
    MULTIPATCH: "MultiPatch",
}

POINT_TYPES = (POINT, POINTZ, POINTM)
LINE_TYPES = (POLYLINE, POLYLINEZ, POLYLINEM)
POLYGON_TYPES = (POLYGON, POLYGONZ, POLYGONM)
#: Lo que el prototipo sabe editar. MultiPoint y MultiPatch se leen,
#: pero el check-in los rechaza.
EDITABLE_TYPES = POINT_TYPES + LINE_TYPES + POLYGON_TYPES
Z_TYPES = (POINTZ, POLYLINEZ, POLYGONZ, MULTIPOINTZ, MULTIPATCH)
M_TYPES = (POINTM, POLYLINEM, POLYGONM, MULTIPOINTM)

#: Por debajo de esto, una M es "sin dato" (especificación ESRI).
M_NODATA = -1e38


class ShapefileError(Exception):
    """El archivo no es un Shapefile válido, o un valor no entra."""


def sidecars(shp_path) -> dict[str, Path]:
    """Las rutas de .shp .shx .dbf .prj .cpg respetando mayúsculas."""
    shp = Path(shp_path)
    out = {}
    for ext in ("shp", "shx", "dbf", "prj", "cpg", "qix", "sbn", "sbx", "qmd"):
        found = None
        for cand in (shp.with_suffix("." + ext), shp.with_suffix("." + ext.upper())):
            if cand.exists():
                found = cand
                break
        out[ext] = found if found is not None else shp.with_suffix("." + ext)
    return out


# -- geometría ------------------------------------------------------------------

@dataclass
class Geometry:
    """``parts``: lista de partes, cada una lista de (x, y). Un punto es una
    parte con un vértice. ``z`` y ``m`` acompañan vértice a vértice, o son
    None si el tipo no los tiene."""

    shape_type: int
    parts: list = field(default_factory=list)
    z: Optional[list] = None
    m: Optional[list] = None

    @property
    def is_null(self) -> bool:
        return self.shape_type == NULL or not self.parts


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def parse_geometry(content: bytes) -> Geometry:
    if len(content) < 4:
        raise ShapefileError("registro de geometría vacío")
    (stype,) = struct.unpack_from("<i", content, 0)
    if stype == NULL:
        return Geometry(NULL)
    if stype in POINT_TYPES:
        x, y = struct.unpack_from("<2d", content, 4)
        z = m = None
        if stype == POINTZ:
            (zv,) = struct.unpack_from("<d", content, 20)
            z = [[zv]]
            if len(content) >= 36:
                (mv,) = struct.unpack_from("<d", content, 28)
                m = [[mv]]
        elif stype == POINTM:
            (mv,) = struct.unpack_from("<d", content, 20)
            m = [[mv]]
        return Geometry(stype, [[(x, y)]], z, m)
    if stype in (MULTIPOINT, MULTIPOINTZ, MULTIPOINTM):
        (n,) = struct.unpack_from("<i", content, 36)
        pts = struct.unpack_from(f"<{2 * n}d", content, 40)
        parts = [[(pts[2 * i], pts[2 * i + 1])] for i in range(n)]
        return Geometry(stype, parts)
    if stype in LINE_TYPES + POLYGON_TYPES + (MULTIPATCH,):
        nparts, npoints = struct.unpack_from("<2i", content, 36)
        off = 44
        starts = list(struct.unpack_from(f"<{nparts}i", content, off))
        off += 4 * nparts
        if stype == MULTIPATCH:
            off += 4 * nparts            # tipos de parte
        flat = struct.unpack_from(f"<{2 * npoints}d", content, off)
        off += 16 * npoints
        pts = [(flat[2 * i], flat[2 * i + 1]) for i in range(npoints)]
        bounds = starts + [npoints]
        parts = [pts[bounds[i]:bounds[i + 1]] for i in range(nparts)]

        def split(values):
            return [list(values[bounds[i]:bounds[i + 1]]) for i in range(nparts)]

        z = m = None
        if stype in (POLYLINEZ, POLYGONZ, MULTIPATCH):
            off += 16
            z = split(struct.unpack_from(f"<{npoints}d", content, off))
            off += 8 * npoints
            if len(content) >= off + 16 + 8 * npoints:
                off += 16
                m = split(struct.unpack_from(f"<{npoints}d", content, off))
        elif stype in (POLYLINEM, POLYGONM):
            off += 16
            m = split(struct.unpack_from(f"<{npoints}d", content, off))
        return Geometry(stype, parts, z, m)
    raise ShapefileError(f"tipo de geometría desconocido: {stype}")


def _range(values):
    values = list(values)
    vals = [v for v in values if v > M_NODATA] or values
    return (min(vals), max(vals)) if vals else (0.0, 0.0)


def encode_geometry(geom: Geometry, with_m: bool = False) -> bytes:
    """Bytes del contenido de un registro (sin la cabecera de 8 bytes).

    ``with_m``: en los tipos Z la M es opcional; se escribe si el archivo
    original la tiene.
    """
    st = geom.shape_type
    if geom.is_null:
        return struct.pack("<i", NULL)
    if st in POINT_TYPES:
        x, y = geom.parts[0][0]
        out = struct.pack("<i2d", st, x, y)
        if st == POINTZ:
            out += struct.pack("<d", geom.z[0][0])
            if with_m:
                mv = geom.m[0][0] if geom.m else -1e39
                out += struct.pack("<d", mv)
        elif st == POINTM:
            mv = geom.m[0][0] if geom.m else -1e39
            out += struct.pack("<d", mv)
        return out
    if st in LINE_TYPES + POLYGON_TYPES:
        pts = [p for part in geom.parts for p in part]
        starts, acc = [], 0
        for part in geom.parts:
            starts.append(acc)
            acc += len(part)
        out = struct.pack("<i4d2i", st, *_bbox(pts), len(geom.parts), len(pts))
        out += struct.pack(f"<{len(starts)}i", *starts)
        out += struct.pack(f"<{2 * len(pts)}d", *[c for p in pts for c in p])
        if st in (POLYLINEZ, POLYGONZ):
            zs = [v for part in geom.z for v in part]
            out += struct.pack("<2d", min(zs), max(zs))
            out += struct.pack(f"<{len(zs)}d", *zs)
            if with_m:
                ms = [v for part in geom.m for v in part] if geom.m else [-1e39] * len(pts)
                out += struct.pack("<2d", *_range(ms))
                out += struct.pack(f"<{len(ms)}d", *ms)
        elif st in (POLYLINEM, POLYGONM):
            ms = [v for part in geom.m for v in part] if geom.m else [-1e39] * len(pts)
            out += struct.pack("<2d", *_range(ms))
            out += struct.pack(f"<{len(ms)}d", *ms)
        return out
    raise ShapefileError(f"no se puede escribir el tipo {SHAPE_NAMES.get(st, st)}")


def record_bounds(content: bytes):
    """(xmin, ymin, xmax, ymax) de un registro leyendo sólo su cabecera, o None."""
    if len(content) < 4:
        return None
    (st,) = struct.unpack_from("<i", content, 0)
    if st == NULL:
        return None
    if st in POINT_TYPES:
        x, y = struct.unpack_from("<2d", content, 4)
        return (x, y, x, y)
    if len(content) >= 36:
        return struct.unpack_from("<4d", content, 4)
    return None


def bbox_overlaps(a, b) -> bool:
    return a is not None and a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def signed_area(ring) -> float:
    """Positiva en sentido antihorario."""
    a = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2.0


# -- DBF ------------------------------------------------------------------------

@dataclass(frozen=True)
class DbfField:
    name: str
    type: str          # C N F D L M ...
    size: int
    decimals: int
    offset: int        # dentro del registro, contando el byte de borrado


_LDID = {0x01: "cp437", 0x02: "cp850", 0x03: "cp1252", 0x57: "cp1252",
         0x58: "cp1252", 0x59: "cp1252", 0x64: "cp852", 0x65: "cp866",
         0x7D: "cp1255", 0x7E: "cp1256", 0xC8: "cp1250", 0xC9: "cp1251",
         0xCA: "cp1254", 0xCB: "cp1253"}


def encoding_for(cpg_text: Optional[str], ldid: int) -> str:
    """La codificación con la que QGIS/GDAL leen la .dbf: primero la .cpg,
    después el byte LDID, y si no hay nada, ISO-8859-1 (el default de GDAL)."""
    if cpg_text:
        raw = cpg_text.strip().upper().replace("-", "").replace("_", "")
        if raw in ("UTF8", "65001"):
            return "utf-8"
        if raw.isdigit():
            cand = {"88591": "latin-1", "885915": "iso8859-15"}.get(raw, "cp" + raw)
        elif raw.startswith("ISO8859"):
            cand = "iso8859-" + raw[7:]
        elif raw.startswith(("CP", "WINDOWS")):
            cand = "cp" + raw.lstrip("CPWINDOWS")
        else:
            cand = cpg_text.strip()
        try:
            return codecs.lookup(cand).name
        except LookupError:
            pass
    if ldid in _LDID:
        return _LDID[ldid]
    return "latin-1"


def decode_value(fld: DbfField, raw: bytes, encoding: str):
    """Valor de Python de una celda: str, int, float, date, bool o None."""
    t = fld.type
    if t == "C":
        text = raw.decode(encoding, errors="replace").rstrip(" \x00")
        return text
    text = raw.decode("ascii", errors="replace").strip(" \x00")
    if t in "NF":
        if not text or set(text) <= {"*"}:
            return None
        try:
            if fld.decimals == 0 and "." not in text and "e" not in text.lower():
                return int(text)
            return float(text)
        except ValueError:
            return None
    if t == "D":
        if not text or text.strip("0") == "":
            return None
        try:
            return _dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        except ValueError:
            return None
    if t == "L":
        if text in ("T", "t", "Y", "y"):
            return True
        if text in ("F", "f", "N", "n"):
            return False
        return None
    return text


def display_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, _dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Verdadero" if value else "Falso"
    return str(value)


def encode_value(fld: DbfField, text: str, encoding: str) -> bytes:
    """Celda de ancho fijo para lo que el usuario escribió.

    Levanta ShapefileError con un mensaje claro si no entra o no es del
    tipo del campo. Un texto vacío es "sin dato".
    """
    t, size = fld.type, fld.size
    text = "" if text is None else str(text)
    if t == "C":
        data = text.encode(encoding)
        if len(data) > size:
            raise ShapefileError(
                f"«{fld.name}» admite {size} caracteres; el valor tiene {len(data)}")
        return data.ljust(size, b" ")
    stripped = text.strip()
    if t in "NF":
        if not stripped:
            return b" " * size
        try:
            num = float(stripped.replace(",", "."))
        except ValueError:
            raise ShapefileError(f"«{fld.name}» es numérico: «{text}» no es un número")
        if not math.isfinite(num):
            raise ShapefileError(f"«{fld.name}»: valor no válido")
        if fld.decimals == 0:
            if num != int(num):
                raise ShapefileError(f"«{fld.name}» es entero: «{text}» tiene decimales")
            out = str(int(num))
        else:
            out = f"{num:.{fld.decimals}f}"
        if len(out) > size:
            raise ShapefileError(
                f"«{fld.name}» admite {size} dígitos; «{out}» no entra")
        return out.rjust(size).encode("ascii")
    if t == "D":
        if not stripped:
            return b" " * size
        date = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y%m%d", "%d-%m-%Y"):
            try:
                date = _dt.datetime.strptime(stripped, fmt).date()
                break
            except ValueError:
                continue
        if date is None:
            raise ShapefileError(f"«{fld.name}» es fecha: use DD/MM/AAAA")
        return date.strftime("%Y%m%d").encode("ascii").ljust(size, b" ")
    if t == "L":
        low = stripped.lower()
        if low in ("", "?"):
            return b"?".ljust(size)
        if low in ("t", "v", "s", "y", "si", "sí", "true", "verdadero", "1"):
            return b"T".ljust(size)
        if low in ("f", "n", "no", "false", "falso", "0"):
            return b"F".ljust(size)
        raise ShapefileError(f"«{fld.name}» es lógico: use V o F")
    raise ShapefileError(f"«{fld.name}» (tipo {t}) no se puede editar")


# -- el conjunto ------------------------------------------------------------------

def record_hash(content: bytes, dbf_record: bytes) -> str:
    """Huella de un registro: geometría + fila de atributos, tal cual en disco."""
    return hashlib.sha1(content + b"\x00|\x00" + dbf_record).hexdigest()[:20]


def file_hash(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Shapefile:
    """Un shapefile leído completo en memoria, como bytes."""

    def __init__(self, shp_path) -> None:
        self.paths = sidecars(shp_path)
        self.shp_path = self.paths["shp"]
        for ext in ("shp", "shx", "dbf"):
            if not self.paths[ext].exists():
                raise ShapefileError(f"falta el archivo .{ext}")
        self._read_shp()
        self._read_dbf()
        if len(self.dbf_records) != len(self.contents):
            raise ShapefileError(
                f"la .shp tiene {len(self.contents)} registros y la .dbf "
                f"{len(self.dbf_records)}: el shapefile está desalineado")

    # .shp / .shx
    def _read_shp(self) -> None:
        shp = self.paths["shp"].read_bytes()
        shx = self.paths["shx"].read_bytes()
        if len(shp) < 100 or struct.unpack_from(">i", shp, 0)[0] != 9994:
            raise ShapefileError("la .shp no tiene cabecera de shapefile")
        self.shp_header = shp[:100]
        (self.shape_type,) = struct.unpack_from("<i", shp, 32)
        self.contents: list[bytes] = []
        n = (len(shx) - 100) // 8
        for i in range(n):
            offset_w, length_w = struct.unpack_from(">2i", shx, 100 + 8 * i)
            start = offset_w * 2 + 8
            end = start + length_w * 2
            if end > len(shp):
                raise ShapefileError(f"el registro {i} sale del final de la .shp")
            self.contents.append(shp[start:end])
        self.has_m = self._detect_m()

    def _detect_m(self) -> bool:
        """En PointZ/PolyLineZ/PolygonZ la M es opcional: ¿la trae el archivo?"""
        st = self.shape_type
        if st in M_TYPES:
            return True
        if st not in Z_TYPES:
            return False
        for c in self.contents:
            if len(c) < 8 or struct.unpack_from("<i", c, 0)[0] == NULL:
                continue
            if st == POINTZ:
                return len(c) >= 36
            nparts, npoints = struct.unpack_from("<2i", c, 36)
            base = 44 + 4 * nparts + 16 * npoints + 16 + 8 * npoints
            return len(c) >= base + 16 + 8 * npoints
        return False

    # .dbf
    def _read_dbf(self) -> None:
        dbf = self.paths["dbf"].read_bytes()
        if len(dbf) < 32:
            raise ShapefileError("la .dbf está vacía")
        nrec, hlen, rlen = struct.unpack_from("<IHH", dbf, 4)
        self.dbf_header = dbf[:hlen]
        self.ldid = dbf[29]
        cpg = self.paths["cpg"]
        cpg_text = cpg.read_text(errors="replace") if cpg.exists() else None
        self.encoding = encoding_for(cpg_text, self.ldid)
        fields, pos, off = [], 32, 1
        while pos + 32 <= hlen and dbf[pos] != 0x0D:
            d = dbf[pos:pos + 32]
            name = d[:11].split(b"\x00")[0].decode(self.encoding, errors="replace").strip()
            ftype = chr(d[11])
            size, dec = d[16], d[17]
            fields.append(DbfField(name, ftype, size, dec, off))
            off += size
            pos += 32
        self.fields: list[DbfField] = fields
        self.record_length = rlen
        body = dbf[hlen:]
        self.dbf_records = []
        for i in range(nrec):
            rec = body[i * rlen:(i + 1) * rlen]
            if len(rec) < rlen:
                raise ShapefileError("la .dbf está truncada")
            self.dbf_records.append(rec)
        self.dbf_tail = body[nrec * rlen:]

    # lectura
    def __len__(self) -> int:
        return len(self.contents)

    @property
    def schema_hash(self) -> str:
        """Huella del esquema de atributos (descriptores de campo)."""
        return hashlib.sha1(self.dbf_header[32:]).hexdigest()[:20]

    def field(self, name: str) -> DbfField:
        for f in self.fields:
            if f.name.upper() == name.upper():
                return f
        raise KeyError(name)

    def geometry(self, i: int) -> Geometry:
        return parse_geometry(self.contents[i])

    def attributes(self, i: int) -> dict:
        rec = self.dbf_records[i]
        return {f.name: decode_value(f, rec[f.offset:f.offset + f.size], self.encoding)
                for f in self.fields}

    def hash(self, i: int) -> str:
        return record_hash(self.contents[i], self.dbf_records[i])

    def is_deleted(self, i: int) -> bool:
        return self.dbf_records[i][:1] == b"*"

    # escritura de una fila
    def patch_record(self, rec: bytes, values: dict) -> bytes:
        buf = bytearray(rec)
        for name, text in values.items():
            fld = self.field(name)
            buf[fld.offset:fld.offset + fld.size] = encode_value(fld, text, self.encoding)
        return bytes(buf)

    def blank_record(self) -> bytes:
        buf = bytearray(b" " * self.record_length)
        for f in self.fields:
            if f.type == "L":
                buf[f.offset:f.offset + 1] = b"?"
        return bytes(buf)


def build_files(sf: Shapefile, rows: list[tuple[bytes, bytes]]):
    """Los bytes nuevos de .shp, .shx y .dbf para ``rows`` = [(contenido de
    geometría, fila dbf)], en el orden final. La cabecera de la .dbf se
    copia tal cual salvo la cantidad de registros."""
    # .shp y .shx
    shp_body, shx_body = bytearray(), bytearray()
    offset_w = 50
    xs, ys, zs, ms = [], [], [], []
    for number, (content, _rec) in enumerate(rows, start=1):
        length_w = len(content) // 2
        shp_body += struct.pack(">2i", number, length_w) + content
        shx_body += struct.pack(">2i", offset_w, length_w)
        offset_w += 4 + length_w
        geom = parse_geometry(content)
        if not geom.is_null:
            for part in geom.parts:
                for x, y in part:
                    xs.append(x)
                    ys.append(y)
            if geom.z:
                zs.extend(v for part in geom.z for v in part)
            if geom.m:
                ms.extend(v for part in geom.m for v in part if v > M_NODATA)
    header = bytearray(sf.shp_header)
    if xs:
        struct.pack_into("<4d", header, 36, min(xs), min(ys), max(xs), max(ys))
    else:
        struct.pack_into("<4d", header, 36, 0.0, 0.0, 0.0, 0.0)
    if sf.shape_type in Z_TYPES:
        struct.pack_into("<2d", header, 68, *(_range(zs) if zs else (0.0, 0.0)))
    if (sf.has_m or sf.shape_type in M_TYPES) and ms:
        # sin ninguna M válida se deja el rango que trae el archivo
        # (cada programa escribe ahí su propio "sin dato")
        struct.pack_into("<2d", header, 84, *_range(ms))
    shp_header = bytearray(header)
    struct.pack_into(">i", shp_header, 24, (100 + len(shp_body)) // 2)
    shx_header = bytearray(header)
    struct.pack_into(">i", shx_header, 24, (100 + len(shx_body)) // 2)
    shp = bytes(shp_header) + bytes(shp_body)
    shx = bytes(shx_header) + bytes(shx_body)
    # .dbf
    dbf_header = bytearray(sf.dbf_header)
    struct.pack_into("<I", dbf_header, 4, len(rows))
    today = _dt.date.today()
    dbf_header[1:4] = bytes((today.year - 1900, today.month, today.day))
    dbf = bytes(dbf_header) + b"".join(rec for _c, rec in rows) + sf.dbf_tail
    return shp, shx, dbf
