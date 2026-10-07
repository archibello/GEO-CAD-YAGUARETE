# SPDX-License-Identifier: GPL-3.0-or-later
"""GIS to CAD / CAD to GIS: capas, colores y rótulos de QGIS en el dibujo.

Con cada capa, QGIS manda su «presentación» (QGIS/.../presentacion.py):

    {"campo_capa": "LAYER_CODE" o "",   # los campos que tiene la tabla
     "campo_color": "CAD_COLOR" o "",
     "capas": {código: {"color": ACI, "rgb": "#rrggbb" o None,
                        "tipo": "Continuous", "grosor": mm o -1}},
     "objetos": {"fid": [código, "#rrggbb" o "" (= PorCapa)]},
     "rotulos": {"fid": [texto, x, y, altura, giro, "c"|"i", "#rrggbb"]},
     "simbolos": {"fid": [forma, tamaño, giro]}}          # sólo puntos (3.1.0)

* QGIS -> IngeCAD: cada código de LAYER_CODE es una capa CAD con el color,
  tipo de línea y grosor del administrador de Capas; cada objeto lleva su
  color propio (CAD_COLOR o el de la simbología de QGIS) y los rótulos
  llegan como textos con la altura y el giro que tienen en QGIS.
* IngeCAD -> QGIS: al guardar, si la tabla tiene LAYER_CODE / CAD_COLOR, el
  objeto que se pasó de capa o cambió de color lleva el cambio a esos campos,
  y lo que se dibuja sobre una de esas capas nace con su LAYER_CODE.
"""
from __future__ import annotations

import math
import re

from core.actions import AddEntityCommand
from core.commands import Command, CompositeCommand
from core.layers import NewLayerCommand
from core.xdata import APPID, ensure_appid

from . import enlace

INVALID = r'[<>/\\":;?*|=`,]'


# -- colores ------------------------------------------------------------------------------

def _palette():
    from ezdxf.colors import DXF_DEFAULT_COLORS

    return DXF_DEFAULT_COLORS


def norm_hex(text) -> str:
    """'#rrggbb' en minúsculas, o "" si no es un color."""
    text = str(text or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return text
    if re.fullmatch(r"#[0-9a-f]{8}", text):          # #aarrggbb de Qt
        return "#" + text[3:]
    return ""


def color_of_hex(text):
    """(ACI, color verdadero o None) para un '#rrggbb'; None si está vacío.
    El negro es el color 7 (como en Capas: blanco sobre fondo oscuro)."""
    text = norm_hex(text)
    if not text:
        return None
    value = int(text[1:], 16)
    if value in (0x000000, 0xFFFFFF):
        return (7, None)
    pal = _palette()
    for aci in range(1, 256):
        if pal[aci] == value:
            return (aci, None)
    return (nearest_aci(value), value)


def label_color(text):
    """Como color_of_hex, pero los casi negros y casi blancos (los que en
    QGIS se leen gracias al contorno) son el color 7: se ven en fondo oscuro
    y salen negros al imprimir."""
    text = norm_hex(text)
    if not text:
        return None
    r, g, b = (int(text[i:i + 2], 16) for i in (1, 3, 5))
    if max(r, g, b) <= 0x40 or min(r, g, b) >= 0xE0:
        return (7, None)
    return color_of_hex(text)


def nearest_aci(value: int) -> int:
    pal = _palette()
    r, g, b = value >> 16, (value >> 8) & 255, value & 255

    def dist(i):
        c = pal[i]
        return ((c >> 16) - r) ** 2 + (((c >> 8) & 255) - g) ** 2 + ((c & 255) - b) ** 2
    return min(range(1, 256), key=dist)


def hex_of_entity(e) -> str:
    """El color propio de la entidad como lo guarda Capas ("" = PorCapa)."""
    if e.dxf.hasattr("true_color"):
        return "#%06x" % e.dxf.true_color
    aci = e.dxf.get("color", 256)
    if aci in (0, 256):
        return ""
    if aci == 7:
        return "#000000"
    return "#%06x" % _palette()[aci]


# -- símbolos de puntos (3.1.0) -------------------------------------------------------------
# Cada forma de QGIS es un bloque de tamaño 1 (centrado en 0,0, color PorBloque);
# cada punto es un INSERT de ese bloque, escalado y girado como en QGIS. El
# INSERT ES el objeto: moverlo mueve el punto al guardar.

SYMBOL_BLOCK = "GEOCAD-SIMBOLO-"
_REGULAR = {"triangle": 3, "equilateraltriangle": 3, "pentagon": 5, "hexagon": 6,
            "octagon": 8, "decagon": 10}


def _ngon(n, r=0.5, start=90.0):
    return [(r * math.cos(math.radians(start + 360.0 * k / n)),
             r * math.sin(math.radians(start + 360.0 * k / n))) for k in range(n)]


def symbol_shape(shape: str):
    """[(puntos, cerrada)] de la forma en tamaño 1, o None = círculo."""
    shape = (shape or "").lower()
    if shape in ("square", "roundedsquare", "squarewithcorners"):
        return [([(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)], True)]
    if shape == "diamond":
        return [([(0, .5), (.5, 0), (0, -.5), (-.5, 0)], True)]
    if shape in _REGULAR:
        return [(_ngon(_REGULAR[shape]), True)]
    if shape in ("star", "diamondstar"):
        pts = []
        for k in range(10):
            r = 0.5 if k % 2 == 0 else 0.2
            a = math.radians(90 + 36 * k)
            pts.append((r * math.cos(a), r * math.sin(a)))
        return [(pts, True)]
    if shape in ("cross", "crossfill"):
        return [([(-.5, 0), (.5, 0)], False), ([(0, -.5), (0, .5)], False)]
    if shape in ("cross2", "asteriskfill"):
        return [([(-.35, -.35), (.35, .35)], False), ([(-.35, .35), (.35, -.35)], False)]
    if shape == "line":
        return [([(0, -.5), (0, .5)], False)]
    if shape in ("arrow", "arrowhead", "arrowheadfilled"):
        return [([(-.3, .1), (0, .5), (.3, .1)], False), ([(0, .5), (0, -.5)], False)]
    return None


def symbol_block(shape: str) -> str:
    name = shape.lower() if symbol_shape(shape) is not None else "circle"
    return SYMBOL_BLOCK + re.sub(r"[^a-z0-9]", "_", name).upper()


class SymbolBlockCommand(Command):
    """Define el bloque de una forma si el dibujo no lo tiene; deshacer lo quita."""

    name = "GeoCAD symbol"

    def __init__(self, shape: str) -> None:
        self.shape = shape
        self.block = symbol_block(shape)
        self._created = False

    def do(self, document) -> None:
        doc = document.doc
        if self.block in doc.blocks:
            return
        blk = doc.blocks.new(self.block)
        attribs = {"layer": "0", "color": 0}               # PorBloque
        parts = symbol_shape(self.shape)
        if parts is None:
            blk.add_circle((0, 0), 0.5, dxfattribs=attribs)
        for pts, closed in parts or ():
            blk.add_lwpolyline(pts, format="xy", close=closed, dxfattribs=attribs)
        self._created = True
        document.dirty = True

    def undo(self, document) -> None:
        if self._created and self.block in document.doc.blocks:
            document.doc.blocks.delete_block(self.block, safe=False)
        self._created = False
        document.dirty = True


# -- QGIS -> IngeCAD ----------------------------------------------------------------------

def _layer_names(doc, link, codes, links) -> dict:
    """{código: capa CAD}. El código vacío va a la capa de la conexión; los
    demás se llaman como el código, salvo que esa capa ya exista en el dibujo
    sin ser de esta conexión (entonces <conexión>-<código>)."""
    mine = {code: name for name, code in link.capas.items()}
    out = {"": link.key}
    for code in sorted(c for c in codes if c):
        if code in mine:
            out[code] = mine[code]
            continue
        base = re.sub(INVALID, "_", code)
        name, n = base, 2
        taken = lambda nm: (nm in doc.layers or enlace.owner_of_layer(links, nm) is not None
                            or nm in out.values())                       # noqa: E731
        if taken(name):
            name = base = f"{link.key}-{base}"
            while taken(name):
                name = f"{base}-{n}"
                n += 1
        out[code] = name
    return out


def _new_layer(doc, name, props) -> NewLayerCommand:
    color = props.get("color")
    rgb = norm_hex(props.get("rgb"))
    if not isinstance(color, int) or not 1 <= color <= 255:
        color = color_of_hex(rgb)[0] if rgb else 7
    ltype = props.get("tipo") or "Continuous"
    if ltype not in doc.linetypes:
        ltype = "Continuous"
    try:
        mm = float(props.get("grosor", -1))
    except (TypeError, ValueError):
        mm = -1
    lw = -3 if mm < 0 else int(round(mm * 100))
    return NewLayerCommand(name, color=color, linetype=ltype, lineweight=lw)


def presentacion(document, link, data, fids) -> dict:
    """Prepara lo que manda QGIS para los registros ``fids`` que se van a
    dibujar. Completa ``link`` (campos, capas propias, valores originales) y
    devuelve {"capas": [comandos], "objetos": {fid: (capa, color)},
    "despues": [comandos de rótulos]} para enlace.build/extend_connect."""
    out = {"capas": [], "objetos": {}, "simbolos": {}, "despues": []}
    if not isinstance(data, dict):
        return out
    doc = document.doc
    objetos = data.get("objetos") or {}
    tabla = data.get("capas") or {}
    link.campo_capa = link.campo_capa or str(data.get("campo_capa") or "")
    link.campo_color = link.campo_color or str(data.get("campo_color") or "")
    wanted = {}
    for fid in fids:
        raw = objetos.get(str(fid))
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            wanted[fid] = (str(raw[0] or ""), norm_hex(raw[1]))
    names = _layer_names(doc, link, {c for c, _h in wanted.values()} if link.campo_capa else set(),
                         enlace.read_links(doc))
    for code, name in names.items():
        if code and name not in doc.layers:
            out["capas"].append(_new_layer(doc, name, tabla.get(code) or {}))
        if code:
            link.capas[name] = code
    for fid, (code, color) in wanted.items():
        layer = names.get(code, link.key) if link.campo_capa else link.key
        out["objetos"][fid] = (layer, color_of_hex(color))
        if link.campo_capa or link.campo_color:
            link.estilo[fid] = [code if link.campo_capa else "",
                                color if link.campo_color else ""]
    if link.kind == "point":
        shapes = set()
        for fid in fids:
            raw = (data.get("simbolos") or {}).get(str(fid))
            try:
                shape, size, angle = str(raw[0]), float(raw[1]), float(raw[2])
            except (TypeError, ValueError, IndexError):
                continue
            if size > 0:
                out["simbolos"][fid] = (symbol_block(shape), size, angle)
                shapes.add(shape if symbol_shape(shape) is not None else "circle")
        out["capas"] += [SymbolBlockCommand(sh) for sh in sorted(shapes)
                         if symbol_block(sh) not in doc.blocks]
    out["despues"] = label_commands(document, link.key, data.get("rotulos") or {}, set(fids))
    return out


def label_commands(document, key, rotulos: dict, fids) -> list:
    """Textos de los rótulos de QGIS, en la capa <conexión>-ROTULOS, marcados
    como los de ROTULOSIG (QUITARROTULOS los borra)."""
    from .herramientas_datos import LABEL_TAG, label_layer

    commands: list = []
    layer = label_layer(key)
    for sfid, raw in sorted(rotulos.items(), key=lambda kv: kv[0]):
        try:
            fid = int(sfid)
            text, x, y, height, angle = str(raw[0]), float(raw[1]), float(raw[2]), \
                float(raw[3]), float(raw[4])
        except (TypeError, ValueError, IndexError):
            continue
        if fid not in fids or not text.strip() or height <= 0:
            continue
        align = raw[5] if len(raw) > 5 else "c"
        color = label_color(raw[6]) if len(raw) > 6 else None

        def make(msp, text=text, pt=(x, y), height=height, angle=angle, align=align,
                 color=color, fid=fid):
            from ezdxf.enums import TextEntityAlignment

            ensure_appid(msp.doc)
            entity = msp.add_text(text, height=height, rotation=angle)
            entity.set_placement(pt, align=TextEntityAlignment.MIDDLE_LEFT if align == "i"
                                 else TextEntityAlignment.MIDDLE_CENTER)
            if color is not None:
                entity.dxf.color = color[0]
                if color[1] is not None:
                    entity.dxf.true_color = color[1]
            entity.set_xdata(APPID, [(1000, LABEL_TAG), (1000, key), (1071, fid),
                                     (1000, "QGIS")])
            return entity

        commands.append(AddEntityCommand("SHP label", make, layer=layer))
        bg = _background(raw[7] if len(raw) > 7 else None, key, fid)
        if bg is not None:
            commands.append(AddEntityCommand("SHP label background", bg, layer=layer))
    if commands and layer not in document.doc.layers:
        commands.insert(0, NewLayerCommand(layer, color=7))
    return commands


# -- IngeCAD -> QGIS ----------------------------------------------------------------------

def _background(raw, key, fid):
    """La función que dibuja el fondo de un rótulo ([forma, x, y, ancho, alto,
    giro, color]): círculo, elipse o rectángulo cerrado; None si no sirve."""
    from .herramientas_datos import LABEL_TAG

    try:
        shape, cx, cy, w, h, angle = str(raw[0]), float(raw[1]), float(raw[2]), \
            float(raw[3]), float(raw[4]), float(raw[5])
    except (TypeError, ValueError, IndexError):
        return None
    if w <= 0 or h <= 0 or shape not in ("circle", "ellipse", "square", "rectangle"):
        return None
    color = label_color(raw[6]) if len(raw) > 6 else None

    def make(msp):
        ensure_appid(msp.doc)
        a = math.radians(angle)
        if shape == "circle":
            entity = msp.add_circle((cx, cy), radius=max(w, h) / 2.0)
        elif shape == "ellipse":
            if h > w:                                     # el eje mayor va vertical
                a += math.pi / 2.0
            major, ratio = max(w, h) / 2.0, min(w, h) / max(w, h)
            entity = msp.add_ellipse((cx, cy), major_axis=(major * math.cos(a),
                                                           major * math.sin(a), 0), ratio=ratio)
        else:
            ca, sa = math.cos(a), math.sin(a)
            pts = [(cx + x * ca - y * sa, cy + x * sa + y * ca)
                   for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            entity = msp.add_lwpolyline(pts, close=True)
        if color is not None:
            entity.dxf.color = color[0]
            if color[1] is not None:
                entity.dxf.true_color = color[1]
        entity.set_xdata(APPID, [(1000, LABEL_TAG), (1000, key), (1071, fid), (1000, "QGIS")])
        return entity
    return make


def code_of_layer(link, layer: str) -> str:
    """El LAYER_CODE que corresponde a una capa CAD."""
    if layer in link.capas:
        return link.capas[layer]
    if layer in (link.key, "0"):
        return ""
    return layer


def differences(document, key, scope=None):
    """Lo que cambió de capa o de color desde que llegó de QGIS (o desde el
    último guardado): ([(fid, campo, valor)], [(entidad, código)] nuevas
    dibujadas sobre una capa de LAYER_CODE). Sólo si la tabla tiene esos campos."""
    link = enlace.read_links(document.doc)[key]
    if not (link.campo_capa or link.campo_color):
        return [], []
    tagged, untagged = enlace.linked_entities(document, key)
    edits, seen = [], set()
    for tag, e in sorted(tagged, key=lambda te: (te[0].fid, te[0].part)):
        if tag.fid in seen or (scope is not None and e.dxf.handle not in scope):
            continue
        seen.add(tag.fid)
        pending = link.pending.get(tag.fid, {})
        if tag.fid >= 0:
            if tag.fid not in link.estilo:
                continue
            orig_code, orig_color = link.estilo[tag.fid]
        else:
            orig_code = pending.get(link.campo_capa, "")
            orig_color = pending.get(link.campo_color, "")
        now = []
        if link.campo_capa:
            now.append((link.campo_capa, code_of_layer(link, e.dxf.get("layer", "0")), orig_code))
        if link.campo_color:
            now.append((link.campo_color, hex_of_entity(e), orig_color))
        for name, value, orig in now:
            if value != orig and pending.get(name) != value:
                edits.append((tag.fid, name, value))
    news = []
    if link.campo_capa:
        for e in untagged:
            layer = e.dxf.get("layer", "0")
            if layer != key and (scope is None or e.dxf.handle in scope):
                news.append((e, code_of_layer(link, layer)))
    return edits, news


class TagNewCommand(Command):
    """Lo dibujado sobre una capa de LAYER_CODE pasa a ser un objeto nuevo
    de la conexión con ese LAYER_CODE (y su color, si hay CAD_COLOR). La
    entidad no cambia de capa. Deshacer la deja como estaba."""

    name = "SHP new on layer"

    def __init__(self, key: str, items) -> None:
        self.key = key
        self.items = list(items)            # (entidad, id provisorio, {campo: valor})

    def do(self, document) -> None:
        link = enlace.read_links(document.doc)[self.key]
        for e, tmp, values in self.items:
            enlace.set_feat_tag(e, self.key, tmp, 0)
            link.pending[tmp] = dict(values)
        enlace.write_link(document.doc, link)
        document.dirty = True

    def undo(self, document) -> None:
        link = enlace.read_links(document.doc).get(self.key)
        for e, tmp, _v in self.items:
            enlace.clear_feat_tag(e)
            if link is not None:
                link.pending.pop(tmp, None)
        if link is not None:
            enlace.write_link(document.doc, link)
        document.dirty = True


def prepare_save(document, key, scope=None):
    """El paso de deshacer que deja en los atributos pendientes los cambios
    de capa y color (None si no hay). Se ejecuta justo antes de guardar."""
    from .herramientas_datos import next_temp_ids

    edits, news = differences(document, key, scope)
    if not edits and not news:
        return None
    link = enlace.read_links(document.doc)[key]
    commands: list = [enlace.AttrEditCommand(key, fid, name, value) for fid, name, value in edits]
    if news:
        ids = next_temp_ids(document, key, len(news))
        items = []
        for (e, code), tmp in zip(news, ids):
            values = {link.campo_capa: code}
            if link.campo_color:
                values[link.campo_color] = hex_of_entity(e)
            items.append((e, tmp, values))
        commands.append(TagNewCommand(key, items))
    return CompositeCommand("SHP layer/color", commands)


def remember_saved(document, key, fids) -> None:
    """Después de guardar: los valores de capa y color de ``fids`` pasan a ser
    los «originales» (lo que ahora tiene el archivo)."""
    links = enlace.read_links(document.doc)
    link = links.get(key)
    if link is None or not (link.campo_capa or link.campo_color):
        return
    fids = set(fids)
    tagged, _ = enlace.linked_entities(document, key)
    for tag, e in sorted(tagged, key=lambda te: (te[0].fid, te[0].part)):
        if tag.fid in fids:
            fids.discard(tag.fid)
            link.estilo[tag.fid] = [
                code_of_layer(link, e.dxf.get("layer", "0")) if link.campo_capa else "",
                hex_of_entity(e) if link.campo_color else ""]
    for fid in fids:                       # borrados
        link.estilo.pop(fid, None)
    enlace.write_link(document.doc, link)
