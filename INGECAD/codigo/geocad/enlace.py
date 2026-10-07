# SPDX-License-Identifier: GPL-3.0-or-later
"""El vínculo entre el dibujo y un shapefile.

Dónde vive cada cosa:

* El **manifiesto** de cada conexión es un XRECORD en el diccionario
  ``INGECAD_SHP`` del dibujo: ruta del .shp, tipo, huella del esquema,
  cantidad de registros y, por cada registro dibujado, la huella que tenía
  al conectar. También guarda los cambios de atributos pendientes.
* Cada entidad dibujada lleva XDATA bajo el APPID ``INGECAD``:
  ``SHP-FEAT``, la clave de la conexión, el FID y el número de parte.

Todo es DXF plano: otro CAD lo conserva y no lo malinterpreta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.actions import AddEntityCommand
from core.commands import Command, CompositeCommand
from core.layers import NewLayerCommand
from core.xdata import APPID, ensure_appid

from . import shpio

DICT_NAME = "INGECAD_SHP"
FEAT_TAG = "SHP-FEAT"
VERSION = "v2"

#: color ACI de la capa según el tipo de geometría
LAYER_COLORS = {"point": 1, "line": 5, "polygon": 3}


def kind_of(shape_type: int) -> str:
    if shape_type in shpio.POINT_TYPES:
        return "point"
    if shape_type in shpio.LINE_TYPES:
        return "line"
    if shape_type in shpio.POLYGON_TYPES:
        return "polygon"
    return "other"


@dataclass
class Link:
    key: str                                   # = nombre de la capa CAD
    path: str
    shape_type: int
    schema: str
    count: int
    hashes: dict = field(default_factory=dict)        # fid -> huella al conectar
    pending: dict = field(default_factory=dict)       # fid -> {campo: texto}
    fmt: str = "shp"                                  # "shp" o "gpkg"
    table: str = ""                                   # capa dentro del .gpkg
    # presentación que mandó QGIS (ver estilo.py)
    campo_capa: str = ""                              # "LAYER_CODE" si la tabla lo tiene
    campo_color: str = ""                             # "CAD_COLOR" si la tabla lo tiene
    capas: dict = field(default_factory=dict)         # capa CAD propia -> LAYER_CODE
    estilo: dict = field(default_factory=dict)        # fid -> [LAYER_CODE, color] guardados

    # -- XRECORD ------------------------------------------------------------
    def to_tags(self) -> list:
        tags = [(1, VERSION), (1, self.fmt), (1, self.table or "-"), (1, self.path),
                (90, self.shape_type), (1, self.schema), (90, self.count)]
        for fid in sorted(self.hashes):
            tags += [(91, fid), (2, self.hashes[fid])]
        for fid in sorted(self.pending):
            for name, value in self.pending[fid].items():
                tags += [(92, fid), (3, name), (4, "=" + value)]
        if self.campo_capa or self.campo_color or self.capas or self.estilo:
            tags += [(93, 1), (300, "=" + self.campo_capa), (301, "=" + self.campo_color)]
        for name in sorted(self.capas):
            tags += [(94, 0), (302, "=" + name), (303, "=" + self.capas[name])]
        for fid in sorted(self.estilo):
            code, color = self.estilo[fid]
            tags += [(95, fid), (304, "=" + code), (305, "=" + color)]
        return tags

    @classmethod
    def from_tags(cls, key: str, tags) -> "Link":
        tags = [(t.code, t.value) for t in tags]
        if tags and tags[0] == (1, "v1"):          # sólo shapefile
            link = cls(key, tags[1][1], int(tags[2][1]), tags[3][1], int(tags[4][1]))
            i = 5
        elif tags and tags[0] == (1, VERSION):
            table = tags[2][1]
            link = cls(key, tags[3][1], int(tags[4][1]), tags[5][1], int(tags[6][1]),
                       fmt=tags[1][1], table="" if table == "-" else table)
            i = 7
        else:
            raise ValueError("manifiesto de conexión desconocido")
        while i < len(tags):
            code, value = tags[i]
            if code == 91:
                link.hashes[int(value)] = tags[i + 1][1]
                i += 2
            elif code == 92:
                name, text = tags[i + 1][1], tags[i + 2][1][1:]
                link.pending.setdefault(int(value), {})[name] = text
                i += 3
            elif code == 93:
                link.campo_capa, link.campo_color = tags[i + 1][1][1:], tags[i + 2][1][1:]
                i += 3
            elif code == 94:
                link.capas[tags[i + 1][1][1:]] = tags[i + 2][1][1:]
                i += 3
            elif code == 95:
                link.estilo[int(value)] = [tags[i + 1][1][1:], tags[i + 2][1][1:]]
                i += 3
            else:
                i += 1
        return link

    @property
    def kind(self) -> str:
        return kind_of(self.shape_type)

    @property
    def name(self) -> str:
        if self.fmt == "gpkg":
            return f"{Path(self.path).name} · {self.table}"
        return Path(self.path).name

    @property
    def lock_target(self) -> str:
        """Lo que se bloquea: el .shp, o la capa dentro del .gpkg."""
        return f"{self.path}.{self.table}" if self.fmt == "gpkg" else self.path


def _dict(doc, create: bool = False):
    if create:
        return doc.rootdict.get_required_dict(DICT_NAME)
    return doc.rootdict.get(DICT_NAME)


def read_links(doc) -> dict[str, Link]:
    d = _dict(doc)
    out = {}
    if d is None:
        return out
    for key, xrec in d.items():
        try:
            out[key] = Link.from_tags(key, xrec.tags)
        except Exception:
            continue
    return out


def write_link(doc, link: Link) -> None:
    d = _dict(doc, create=True)
    xrec = d.get(link.key)
    if xrec is None:
        xrec = d.add_xrecord(link.key)
    xrec.reset(link.to_tags())


def remove_link(doc, key: str) -> None:
    d = _dict(doc)
    if d is None or key not in d:
        return
    record = d.get(key)
    d.discard(key)
    if record is not None:
        doc.objects.delete_entity(record)
    if len(d) == 0:
        doc.rootdict.discard(DICT_NAME)
        doc.objects.delete_entity(d)


# -- XDATA de las entidades ---------------------------------------------------------

@dataclass(frozen=True)
class FeatTag:
    key: str
    fid: int
    part: int


def feat_tag(entity):
    try:
        values = [v for _c, v in entity.get_xdata(APPID)]
    except Exception:
        return None
    if len(values) >= 4 and values[0] == FEAT_TAG:
        try:
            return FeatTag(str(values[1]), int(values[2]), int(values[3]))
        except (TypeError, ValueError):
            return None
    return None


def set_feat_tag(entity, key: str, fid: int, part: int) -> None:
    ensure_appid(entity.doc)
    entity.set_xdata(APPID, [(1000, FEAT_TAG), (1000, key), (1071, fid), (1071, part)])


def clear_feat_tag(entity) -> None:
    try:
        entity.discard_xdata(APPID)
    except Exception:
        pass


# -- comandos con deshacer exacto ---------------------------------------------------

class LinkCommand(Command):
    """Crea (o borra, con ``link=None``) el manifiesto de una conexión."""

    name = "SHP link"

    def __init__(self, key: str, link) -> None:
        self.key = key
        self.link = link
        self._old = None

    def do(self, document) -> None:
        doc = document.doc
        self._old = read_links(doc).get(self.key)
        if self.link is None:
            remove_link(doc, self.key)
        else:
            write_link(doc, self.link)
        document.dirty = True

    def undo(self, document) -> None:
        doc = document.doc
        if self._old is None:
            remove_link(doc, self.key)
        else:
            write_link(doc, self._old)
        document.dirty = True


class AttrEditCommand(Command):
    """Un valor de atributo pendiente de devolver al .dbf. Deshacer
    restaura sólo ese valor, nunca el resto del manifiesto."""

    name = "SHP attribute"

    def __init__(self, key: str, fid: int, field_name: str, value: str) -> None:
        self.key, self.fid, self.field_name, self.value = key, fid, field_name, value
        self._had = False
        self._old = None

    def _apply(self, document, value, present: bool) -> None:
        doc = document.doc
        link = read_links(doc)[self.key]
        row = link.pending.setdefault(self.fid, {})
        if present:
            row[self.field_name] = value
        else:
            row.pop(self.field_name, None)
            if not row:
                link.pending.pop(self.fid, None)
        write_link(doc, link)
        document.dirty = True

    def do(self, document) -> None:
        link = read_links(document.doc)[self.key]
        row = link.pending.get(self.fid, {})
        self._had = self.field_name in row
        self._old = row.get(self.field_name)
        self._apply(document, self.value, True)

    def undo(self, document) -> None:
        self._apply(document, self._old, self._had)


# -- conectar (check-out) -------------------------------------------------------------

def layer_key(doc, shp_path, prefix: str = "SHP", name: str = "") -> str:
    """Nombre de capa para la conexión: ``SHP-<nombre>``, único."""
    import re

    raw = name or Path(shp_path).stem
    base = f"{prefix}-" + re.sub(r'[<>/\\":;?*|=`,]', "_", raw)
    links = read_links(doc)
    key, n = base, 2
    while key in links or key in doc.layers:
        key = f"{base}-{n}"
        n += 1
    return key


def _ring_open(part):
    """Un anillo de polígono sin el vértice de cierre repetido."""
    if len(part) > 1 and part[0] == part[-1]:
        return part[:-1]
    return part


def _factory(kind: str, key: str, fid: int, part_no: int, pts, z, color=None, symbol=None):
    def make(msp):
        if kind == "point" and symbol is not None:     # (bloque, tamaño, giro): el bloque ES el punto
            x, y = pts[0]
            entity = msp.add_blockref(symbol[0], (x, y, z if z is not None else 0.0),
                                      dxfattribs={"xscale": symbol[1], "yscale": symbol[1],
                                                  "rotation": symbol[2]})
        elif kind == "point":
            x, y = pts[0]
            entity = msp.add_point((x, y, z if z is not None else 0.0))
        elif kind == "polygon":
            entity = msp.add_lwpolyline(_ring_open(pts), format="xy", close=True)
        else:
            entity = msp.add_lwpolyline(pts, format="xy")
        if color is not None:                   # (ACI, color verdadero o None)
            entity.dxf.color = color[0]
            if color[1] is not None:
                entity.dxf.true_color = color[1]
        set_feat_tag(entity, key, fid, part_no)
        return entity
    return make


def connect_commands(document, sf: shpio.Shapefile, key: str):
    """Capa + manifiesto + una entidad por parte, como UN paso de deshacer.

    Devuelve (comando, cantidad de entidades, registros sin geometría)."""
    link = Link(key, str(Path(sf.shp_path).resolve()), sf.shape_type,
                sf.schema_hash, len(sf))
    features, skipped = [], 0
    for fid in range(len(sf)):
        if sf.is_deleted(fid):
            skipped += 1
            continue
        geom = sf.geometry(fid)
        if geom.is_null:
            skipped += 1
            continue
        features.append((fid, sf.hash(fid), geom.parts, geom.z))
    return build_connect(link, features, skipped)


def _feature_commands(link: Link, features, pres=None):
    kind, key = link.kind, link.key
    where = (pres or {}).get("objetos", {})
    symbols = (pres or {}).get("simbolos", {})
    commands, n = [], 0
    for fid, h, parts, zs in features:
        link.hashes[fid] = h
        layer, color = where.get(fid, (key, None))
        for part_no, pts in enumerate(parts):
            z = zs[part_no][0] if (kind == "point" and zs) else None
            commands.append(AddEntityCommand(
                "SHP feature", _factory(kind, key, fid, part_no, pts, z, color, symbols.get(fid)),
                layer=layer))
            n += 1
    return commands, n


def build_connect(link: Link, features, skipped: int, pres=None):
    """``features``: [(fid, huella, partes, z por parte o None)].
    ``pres``: la presentación de QGIS ya resuelta (estilo.presentacion)."""
    pres = pres or {}
    commands: list = [NewLayerCommand(link.key, color=LAYER_COLORS.get(link.kind, 7))]
    commands += pres.get("capas", [])
    more, n_entities = _feature_commands(link, features, pres)
    commands += more
    commands += pres.get("despues", [])
    commands.append(LinkCommand(link.key, link))
    return CompositeCommand("SHP connect", commands), n_entities, skipped


def extend_connect(link: Link, features, pres=None):
    """Suma a una conexión existente los registros que todavía no estaban
    dibujados (un solo paso de deshacer). Devuelve (comando, registros, entidades)."""
    import copy

    pres = pres or {}
    new = copy.deepcopy(link)
    fresh = [f for f in features if f[0] not in link.hashes]
    commands = list(pres.get("capas", []))
    more, n = _feature_commands(new, fresh, pres)
    commands += more + pres.get("despues", [])
    commands.append(LinkCommand(link.key, new))
    return CompositeCommand("SHP extend", commands), len(fresh), n


def linked_entities(document, key: str):
    """Las entidades del espacio modelo que pertenecen a la conexión
    (etiquetadas con su clave, o sin etiqueta pero sobre su capa)."""
    msp = document.doc.modelspace()
    link = read_links(document.doc).get(key)
    layers = {key} | set(link.capas if link is not None else ())
    tagged, untagged = [], []
    for e in msp:
        tag = feat_tag(e)
        if tag is not None and tag.key == key:
            tagged.append((tag, e))
        elif tag is None and e.dxf.get("layer") in layers:
            untagged.append(e)
    return tagged, untagged


def owner_of_layer(links: dict, layer: str):
    """La clave de la conexión dueña de una capa CAD (la suya o una de las
    que creó para sus LAYER_CODE), o None."""
    if layer in links:
        return layer
    for key, link in links.items():
        if layer in link.capas:
            return key
    return None
