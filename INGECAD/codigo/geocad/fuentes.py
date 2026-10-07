# SPDX-License-Identifier: GPL-3.0-or-later
"""Lo que los comandos necesitan saber de una capa conectada, sin importar
si es un shapefile o una capa de GeoPackage: sus campos, sus atributos,
cómo validar un valor y en qué sistema de coordenadas está."""
from __future__ import annotations

from dataclasses import dataclass

from . import crs as crs_mod
from . import shpio

EDITABLE_DBF = "CNFDL"


@dataclass
class FieldInfo:
    name: str
    label: str
    editable: bool


class ShpSource:
    def __init__(self, link) -> None:
        self.sf = shpio.Shapefile(link.path)

    def fields(self):
        out = []
        for f in self.sf.fields:
            dec = f".{f.decimals}" if f.decimals else ""
            out.append(FieldInfo(f.name, f"{f.name} ({f.type}{f.size}{dec})",
                                 f.type in EDITABLE_DBF))
        return out

    def attributes(self, fid) -> dict:
        return {k: shpio.display_value(v) for k, v in self.sf.attributes(fid).items()}

    def validate(self, name, text) -> None:
        shpio.encode_value(self.sf.field(name), text, self.sf.encoding)


class GpkgSource:
    def __init__(self, link) -> None:
        from . import gpkgio as G

        self.G = G
        conn = G.connect(link.path)
        try:
            self.layer = G.open_layer(conn, link.path, link.table)
            self._rows = None
            self._conn_path = link.path
        finally:
            conn.close()

    def fields(self):
        return [FieldInfo(c.name, c.label, c.editable) for c in self.layer.columns]

    def attributes(self, fid) -> dict:
        G = self.G
        conn = G.connect(self._conn_path)
        try:
            row = G.read_rows(conn, self.layer, [fid]).get(fid)
        finally:
            conn.close()
        if row is None:
            raise KeyError(f"FID {fid} ya no existe en el GeoPackage")
        return {c.name: G.display(c, v) for c, v in zip(self.layer.columns, row[1])}

    def validate(self, name, text) -> None:
        self.G.to_value(self.layer.column(name), text)


def source_for(link):
    return GpkgSource(link) if link.fmt == "gpkg" else ShpSource(link)


def shp_crs(shp_path) -> crs_mod.Crs:
    prj = shpio.sidecars(shp_path)["prj"]
    return crs_mod.identify(prj.read_text(errors="replace") if prj.exists() else None)


def gpkg_crs(conn, srs_id: int) -> crs_mod.Crs:
    from . import gpkgio as G

    row = G.srs_info(conn, srs_id)
    if row is None or srs_id in (0, -1):
        return crs_mod.Crs(None, "sin sistema de coordenadas definido")
    org, code, definition = row
    definition = definition or ""
    geographic = definition.strip().upper().startswith(("GEOGCS", "GEOGCRS"))
    if (org or "").upper() == "EPSG" and code:
        return crs_mod.Crs(int(code), crs_mod.KNOWN.get(int(code), f"EPSG:{code}"), geographic)
    return crs_mod.identify(definition)


def link_crs(link) -> crs_mod.Crs:
    if link.fmt == "gpkg":
        from . import gpkgio as G

        conn = G.connect(link.path)
        try:
            layer = G.open_layer(conn, link.path, link.table)
            return gpkg_crs(conn, layer.srs_id)
        finally:
            conn.close()
    return shp_crs(link.path)
