# SPDX-License-Identifier: GPL-3.0-or-later
"""La base de datos de lo que trajo IMPORTARSHP (3.25.1), sin Qt.

Cada objeto importado guarda en su XDATA propia (``GEOCAD_ATRIB``) el
nombre de su tabla (el archivo de origen), el número de registro y los
valores con el esquema del .dbf (tipo, ancho, decimales). Las partes de un
mismo registro (los huecos de un polígono, las partes de una multilínea)
llevan el mismo número: son UNA fila.

:class:`ImportedData` lo presenta igual que ``datos.LayerData`` presenta una
capa conectada, así lo usan la Tabla de atributos, CONSULTASIG, UBICACIONSIG,
TEMATICO y ROTULOSIG. No hay archivo detrás: los cambios quedan en el dibujo
(con deshacer) y vuelven a salir con EXPORTARSHP.
"""
from __future__ import annotations

from core.commands import Command

from . import shpio

APPID_ATRIB = "GEOCAD_ATRIB"
MARCA_ATRIB = "ATRIBUTOS"
#: largo máximo de un texto en XDATA (grupo 1000)
LARGO_XDATA = 250


# ------------------------------------------------------------------ XDATA de cada objeto

def poner_atributos(entity, origen: str, campos, valores: dict, fid=None) -> None:
    """Guarda en el objeto los atributos que trae: ``campos`` = [DbfField]."""
    doc = entity.doc
    if doc is not None and APPID_ATRIB not in doc.appids:
        doc.appids.add(APPID_ATRIB)
    tags = [(1000, MARCA_ATRIB), (1000, origen[:LARGO_XDATA])]
    if fid is not None:
        tags.append((1071, int(fid)))
    for f in campos:
        tags += [(1000, f.name), (1000, f"{f.type},{f.size},{f.decimals}"),
                 (1000, shpio.display_value(valores.get(f.name))[:LARGO_XDATA])]
    entity.set_xdata(APPID_ATRIB, tags)


def _leer(entity):
    """(origen, fid o None, [(nombre, (tipo, ancho, decimales), texto)]) o None."""
    try:
        tags = list(entity.get_xdata(APPID_ATRIB))
    except Exception:  # noqa: BLE001 -- sin XDATA nuestra
        return None
    if len(tags) < 2 or tags[0][1] != MARCA_ATRIB:
        return None
    fid = None
    resto = tags[2:]
    if resto and resto[0][0] == 1071:
        fid = int(resto[0][1])
        resto = resto[1:]
    resto = [v for _c, v in resto]
    out = []
    for i in range(0, len(resto) - 2, 3):
        nombre_c, tipo, texto = resto[i], resto[i + 1], resto[i + 2]
        try:
            t, ancho, dec = tipo.split(",")
            out.append((str(nombre_c), (t, int(ancho), int(dec)), str(texto)))
        except ValueError:
            out.append((str(nombre_c), ("C", 254, 0), str(texto)))
    return str(tags[1][1]), fid, out


def atributos(entity) -> tuple[str, list]:
    """(origen, [(nombre, (tipo, ancho, decimales), texto)]) o ("", [])."""
    leido = _leer(entity)
    return ("", []) if leido is None else (leido[0], leido[2])


def _cambiar_valor(entity, campo: str, texto: str) -> None:
    origen, fid, at = _leer(entity)
    campos = [shpio.DbfField(n, t, a, d, 0) for n, (t, a, d), _x in at]
    valores = {n: (texto if n == campo else x) for n, _t, x in at}
    poner_atributos(entity, origen, campos, valores, fid)


# ------------------------------------------------------------------ tablas del dibujo

def objetos(doc, key=None):
    """[(origen, fid, entidad)] del espacio modelo, en orden. Lo importado
    antes de 3.25.1 no trae número de registro: cada objeto es una fila."""
    out, sueltos = [], {}
    for e in doc.modelspace():
        leido = _leer(e)
        if leido is None or (key is not None and leido[0] != key):
            continue
        origen, fid, _at = leido
        if fid is None:
            fid = 1_000_000 + sueltos.get(origen, 0)
            sueltos[origen] = sueltos.get(origen, 0) + 1
        out.append((origen, fid, e))
    return out


def tablas(doc) -> dict[str, int]:
    """{tabla: cantidad de registros} de lo importado con base de datos."""
    regs: dict[str, set] = {}
    for origen, fid, _e in objetos(doc):
        regs.setdefault(origen, set()).add(fid)
    return {k: len(v) for k, v in regs.items()}


def nombre_libre(base: str, usados) -> str:
    """«parcelas», o «parcelas (2)» si ya hay una tabla con ese nombre."""
    usados = {u.lower() for u in usados}
    if base.lower() not in usados:
        return base
    n = 2
    while f"{base} ({n})".lower() in usados:
        n += 1
    return f"{base} ({n})"


def _tipo_de(ents) -> str:
    tipos = {e.dxftype() for e in ents}
    if tipos <= {"POINT", "INSERT", "TEXT", "MTEXT"}:
        return "point"
    if all(e.dxftype() == "LWPOLYLINE" and e.closed for e in ents):
        return "polygon"
    return "line"


class ImportedData:
    """Una tabla importada con la misma cara que ``datos.LayerData``."""

    def __init__(self, document, key: str) -> None:
        from . import datos

        self.key = key
        self.fields = []
        self.rows = []
        self._por_fid: dict[int, list] = {}
        self._esquema: dict[str, tuple] = {}
        valores: dict[int, dict] = {}
        for _o, fid, e in objetos(document.doc, key):
            self._por_fid.setdefault(fid, []).append(e)
            if fid in valores:
                continue
            valores[fid] = {}
            for nombre_c, esquema, texto in _leer(e)[2]:
                if nombre_c not in self._esquema:
                    self._esquema[nombre_c] = esquema
                    t, ancho, dec = esquema
                    f = shpio.DbfField(nombre_c, t, ancho, dec, 0)
                    sufijo = f".{dec}" if dec else ""
                    self.fields.append(datos.Field(nombre_c, f"{nombre_c} ({t}{ancho}{sufijo})",
                                                   datos._shp_family(f), t in "CNFDL"))
                valores[fid][nombre_c] = texto
        if not self._por_fid:
            raise KeyError(key)
        fam = {f.name: f.family for f in self.fields}
        for fid in sorted(valores):
            self.rows.append(datos.Row(fid, {n: datos.typed(fam[n], x)
                                             for n, x in valores[fid].items()}))
        self.kind = _tipo_de([e for ents in self._por_fid.values() for e in ents])

    def field(self, name: str):
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
        """Lanza ShapefileError si el valor no entra en el campo (como en el .dbf)."""
        f = self.field(name)
        t, ancho, dec = self._esquema[f.name]
        shpio.encode_value(shpio.DbfField(f.name, t, ancho, dec, 0), text, "utf-8")

    def entities_by_fid(self, document) -> dict:
        return {fid: list(ents) for fid, ents in self._por_fid.items()}


class EditarAtributoCommand(Command):
    """Cambia un valor de una fila importada en todas sus partes. Deshacer
    devuelve la XDATA tal como estaba."""

    name = "atributo importado"

    def __init__(self, key: str, fid: int, campo: str, texto: str) -> None:
        self.key, self.fid, self.campo, self.texto = key, fid, campo, str(texto)
        self._antes = []

    def do(self, document) -> None:
        self._antes = []
        for _o, fid, e in objetos(document.doc, self.key):
            if fid == self.fid:
                self._antes.append((e, list(e.get_xdata(APPID_ATRIB))))
                _cambiar_valor(e, self.campo, self.texto[:LARGO_XDATA])

    def undo(self, document) -> None:
        for e, tags in self._antes:
            e.set_xdata(APPID_ATRIB, tags)
