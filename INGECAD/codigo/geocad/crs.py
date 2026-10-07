# SPDX-License-Identifier: GPL-3.0-or-later
"""Qué sistema de coordenadas declara el .prj de una capa.

Reconoce por nombre los sistemas oficiales de Argentina en sus siete
fajas Gauss-Krüger -- POSGAR 2007, POSGAR 98, POSGAR 94 y Campo
Inchauspe -- además de cualquier .prj que traiga su código EPSG.

Nunca reproyecta: sólo identifica, para avisar si en un mismo dibujo se
mezclan capas de sistemas distintos (Campo Inchauspe y POSGAR difieren
en decenas a cientos de metros) y para declarar la georreferencia del
dibujo, que usa el complemento Terreno (imágenes satelitales, KML).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: (nombre, EPSG de la faja 1, EPSG geográfico). La faja f es base + f - 1.
#: Fuente: registro EPSG (epsg.io) e IGN.
DATUMS = (
    ("POSGAR 2007", 5343, 5340),
    ("POSGAR 98", 22171, 4190),
    ("POSGAR 94", 22181, 4694),
    ("Campo Inchauspe", 22191, 4221),
)

#: meridiano central de cada faja
FAJA_MERIDIAN = {1: -72, 2: -69, 3: -66, 4: -63, 5: -60, 6: -57, 7: -54}


def _known() -> dict[int, str]:
    out = {}
    for name, base, geo in DATUMS:
        out[geo] = f"{name} (geográficas)"
        for faja in range(1, 8):
            out[base + faja - 1] = f"{name} / Argentina faja {faja}"
    for zone in (18, 19, 20, 21, 22):
        out[32700 + zone] = f"WGS 84 / UTM {zone}S"
    out[4326] = "WGS 84 (geográficas)"
    return out


KNOWN = _known()


@dataclass(frozen=True)
class Crs:
    epsg: Optional[int]
    label: str
    geographic: bool = False

    @property
    def code(self) -> str:
        return f"EPSG:{self.epsg}" if self.epsg else ""


def _datum_from_text(text: str) -> Optional[tuple[str, int, int]]:
    t = re.sub(r"[\s_\-]+", " ", text.upper())
    if "INCHAUSPE" in t:
        return DATUMS[3]
    if re.search(r"POSGAR ?(2007|07)\b", t):
        return DATUMS[0]
    if re.search(r"POSGAR ?(1998|98)\b", t):
        return DATUMS[1]
    if re.search(r"POSGAR ?(1994|94)\b", t):
        return DATUMS[2]
    return None            # "POSGAR" sin año es ambiguo: mejor no adivinar


def identify(prj_text: Optional[str]) -> Crs:
    if not prj_text or not prj_text.strip():
        return Crs(None, "sin .prj (sistema desconocido)")
    text = prj_text.strip()
    upper = text.upper()
    geographic = not upper.startswith(("PROJCS", "PROJCRS"))

    # 1. el código EPSG del sistema proyectado (el ÚLTIMO AUTHORITY del WKT1
    #    es el del PROJCS; en WKT2 el ID va al final igual)
    codes = re.findall(r'(?:AUTHORITY|ID)\[\s*"EPSG"\s*,\s*"?(\d+)"?\s*\]', text, re.I)
    if codes:
        code = int(codes[-1])
        return Crs(code, KNOWN.get(code, f"EPSG:{code}"), geographic)

    # 2. por el nombre: "POSGAR_2007_Argentina_5", "Campo Inchauspe / Argentina 3"
    head = re.match(r'\s*\w+\[\s*"([^"]*)"', text)
    name = head.group(1) if head else ""
    utm = re.search(r"WGS[\s_]*(?:19)?84[\s_/]*UTM[\s_]*ZONE[\s_]*(\d{1,2})\s*([NS])",
                    name, re.I)
    if utm:
        code = (32600 if utm.group(2).upper() == "N" else 32700) + int(utm.group(1))
        return Crs(code, KNOWN.get(code, f"WGS 84 / UTM {utm.group(1)}{utm.group(2).upper()}"))
    datum = _datum_from_text(name) or _datum_from_text(text)
    if datum is not None:
        dname, base, geo = datum
        if geographic:
            return Crs(geo, KNOWN[geo], True)
        faja = None
        m = re.search(r"ARGENTINA[\s_]*(?:ZONE|FAJA)?[\s_]*([1-7])\b", name.upper())
        if m:
            faja = int(m.group(1))
        else:
            # 3. por los parámetros: meridiano central o falso este
            cm = re.search(r'PARAMETER\[\s*"central_meridian"\s*,\s*(-?[\d.]+)', text, re.I)
            fe = re.search(r'PARAMETER\[\s*"false_easting"\s*,\s*([\d.]+)', text, re.I)
            if cm:
                for f, mer in FAJA_MERIDIAN.items():
                    if abs(float(cm.group(1)) - mer) < 1e-6:
                        faja = f
            if faja is None and fe:
                v = float(fe.group(1))
                if v >= 1_000_000 and (v - 500_000) % 1_000_000 == 0:
                    f = int((v - 500_000) // 1_000_000)
                    faja = f if 1 <= f <= 7 else None
        if faja is not None:
            code = base + faja - 1
            return Crs(code, KNOWN[code], False)
        return Crs(None, f"{dname} (faja no reconocida)", geographic)
    return Crs(None, name or "sistema no reconocido", geographic)


def compatible(a: Crs, b: Crs) -> bool:
    """Dos capas pueden convivir en el dibujo sin reproyectar."""
    if a.epsg and b.epsg:
        return a.epsg == b.epsg
    return True        # si uno es desconocido no se puede afirmar lo contrario


def faja_check(crs: Crs, xmin: float, xmax: float) -> Optional[str]:
    """Aviso si las coordenadas Este no caen en la faja que dice el .prj
    (el error típico: un .prj de faja 5 para datos de faja 4)."""
    if not crs.epsg or crs.geographic:
        return None
    for _name, base, _geo in DATUMS:
        if base <= crs.epsg <= base + 6:
            faja = crs.epsg - base + 1
            lo, hi = faja * 1_000_000, (faja + 1) * 1_000_000
            if not (lo <= xmin and xmax < hi):
                return (f"las coordenadas Este ({xmin:,.0f} a {xmax:,.0f}) no "
                        f"corresponden a la faja {faja} del .prj")
    return None
