# -*- coding: utf-8 -*-
"""PEGAR EN EL LUGAR entre QGIS e IngeCAD (3.66.0, PEGARORIG / PASTEORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «copiar en una las entidades seleccionadas y pegarlas en
la otra»; «ESO ES PEGAR EN EL LUGAR». Lo copiado (Ctrl+C) en un programa se
pega en el otro en sus mismas coordenadas, con su capa CAD, su color, su tipo
y su grosor de línea (como el Puente).

Cada programa guarda este mensaje (JSON) en ``archivo_copia()``, junto con la
huella de lo que dejó en el portapapeles del sistema; el otro lo usa sólo si la
huella coincide con lo que hay ahora, así nunca pega una copia vieja. NO se
agrega al portapapeles: en GNOME 48 con Wayland, volver a escribirlo enseguida
lo deja vacío («No pega nada», Fernando, 04/11/2026). El mensaje:

    {"geocad": "pegar_lugar", "version": 1, "origen": "qgis" | "ingecad",
     "crs": "EPSG:xxxx" o "",
     "capas": {nombre: {"color": "#rrggbb" | None, "aci": n | None,
                        "tipo_linea": str | None, "grosor": mm | None}},
     "objetos": [{"wkt": ..., "capa": ..., "color": "#rrggbb" | None (PorCapa),
                  "aci": n | None, "tipo_linea": str | None (PorCapa),
                  "grosor": mm | -1 (Por defecto) | None (PorCapa)}],
     "salteados": {tipo: cantidad}}

«Si no está configurado el sistema de representación de coordenadas, esta
acción va a crear el mismo de forma automática» (Fernando): ver ``sistema``.
Sin Qt ni QGIS ni IngeCAD: lo prueba test_pegar_lugar.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

VERSION = 1
NOMBRE = "Pegar en el lugar"
ATAJO = "Ctrl+Alt+V"
FORMATO_TEXTO = "text/plain"            # lo que marca una copia de QGIS

# grosores de DXF (centésimas de mm); -1 PorCapa, -2 PorBloque, -3 Por defecto
GROSORES_DXF = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
                100, 106, 120, 140, 158, 200, 211)
POR_CAPA, POR_BLOQUE, POR_DEFECTO = -1, -2, -3


# ------------------------------------------------------------------ el mensaje
def empaquetar(origen: str, crs: str, objetos: list, capas: dict | None = None,
               salteados: dict | None = None) -> bytes:
    """El mensaje listo para guardar."""
    datos = {"geocad": "pegar_lugar", "version": VERSION, "origen": origen,
             "crs": crs or "", "capas": capas or {}, "objetos": list(objetos),
             "salteados": dict(salteados or {})}
    return json.dumps(datos, ensure_ascii=False).encode("utf-8")


def desempaquetar(datos) -> dict | None:
    """El mensaje leído, o None si no es de GeoCAD."""
    if not datos:
        return None
    try:
        msg = json.loads(bytes(datos).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("geocad") != "pegar_lugar" \
            or not isinstance(msg.get("objetos"), list):
        return None
    msg.setdefault("crs", "")
    msg.setdefault("capas", {})
    msg.setdefault("salteados", {})
    return msg


# ------------------------------------------------------------------ la copia guardada
def archivo_copia() -> Path:
    return Path.home() / ".config" / "geocad" / "pegar_lugar.json"


def _contenido(data, formato: str) -> bytes | None:
    """Lo que tiene el portapapeles (QMimeData) en ese formato, o None."""
    if formato == FORMATO_TEXTO:
        return data.text().encode("utf-8") if data.hasText() else None
    return bytes(data.data(formato)) if data.hasFormat(formato) else None


def _huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido.replace(b"\r\n", b"\n")).hexdigest()


def dejar_copia(mensaje: bytes, data, formato: str) -> bool:
    """Guarda el mensaje de la copia que está en el portapapeles (QMimeData)."""
    contenido = _contenido(data, formato)
    if not contenido:
        return False
    destino = archivo_copia()
    datos = {"formato": formato, "huella": _huella(contenido), "mensaje": mensaje.decode("utf-8")}
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".pegar_lugar-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False)
        os.replace(tmp, destino)
    except OSError:
        return False
    return True


def leer_copia(data) -> dict | None:
    """El mensaje guardado, si es de lo que está ahora en el portapapeles."""
    if data is None:
        return None
    try:
        datos = json.loads(archivo_copia().read_text(encoding="utf-8"))
        contenido = _contenido(data, datos["formato"])
        if not contenido or _huella(contenido) != datos["huella"]:
            return None
        return desempaquetar(datos["mensaje"].encode("utf-8"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def borrar_copia() -> None:
    """Módulo apagado: no queda rastro."""
    try:
        archivo_copia().unlink()
    except OSError:
        pass


def resumen(msg: dict) -> str:
    """«3 objeto(s) de QGIS» y lo que no viajó."""
    origen = {"qgis": "QGIS", "ingecad": "IngeCAD"}.get(msg.get("origen"), "otro programa")
    texto = "%d objeto(s) de %s" % (len(msg.get("objetos", [])), origen)
    salteados = msg.get("salteados") or {}
    if salteados:
        texto += " (no viajan: %s)" % ", ".join(
            "%d %s" % (n, t) for t, n in sorted(salteados.items()))
    return texto


# ------------------------------------------------------------------ el sistema de coordenadas
def sistema(destino: str, origen: str) -> tuple:
    """(definir, reproyectar) al pegar: si el destino no tiene sistema toma el del
    origen (Fernando: «va a crear el mismo de forma automática»); si los dos lo
    tienen y son distintos, lo pegado se reproyecta."""
    destino, origen = (destino or "").strip().upper(), (origen or "").strip().upper()
    if not origen:
        return "", False
    if not destino:
        return origen, False
    return "", destino != origen


# ------------------------------------------------------------------ grosor
def grosor_dxf(mm) -> int:
    """El grosor en mm como valor de DXF (el estándar más cercano). None = PorCapa,
    negativo = Por defecto."""
    if mm is None:
        return POR_CAPA
    mm = float(mm)
    if mm < 0:
        return POR_DEFECTO
    centesimas = mm * 100.0
    return min(GROSORES_DXF, key=lambda g: abs(g - centesimas))


def mm_de_dxf(valor) -> float | None:
    """El grosor de DXF en mm: None = PorCapa (o PorBloque), -1 = Por defecto."""
    if valor is None:
        return None
    valor = int(valor)
    if valor == POR_DEFECTO:
        return -1.0
    if valor < 0:
        return None
    return round(valor / 100.0, 2)


# ------------------------------------------------------------------ WKT
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def _pares(texto: str) -> list:
    """[(x, y), ...] de «x y [z [m]], x y ...»."""
    out = []
    for parte in texto.split(","):
        nums = re.findall(_NUM, parte)
        if len(nums) >= 2:
            out.append((float(nums[0]), float(nums[1])))
    return out


def _grupos(texto: str) -> list:
    """Lo de adentro de cada paréntesis del nivel más bajo, en orden."""
    return re.findall(r"\(([^()]*)\)", texto)


def tipo_wkt(wkt: str) -> str:
    """'punto', 'linea', 'poligono' o '' según el WKT."""
    cab = (wkt or "").lstrip().upper()
    if cab.startswith(("MULTIPOINT", "POINT")):
        return "punto"
    if cab.startswith(("MULTILINESTRING", "LINESTRING")):
        return "linea"
    if cab.startswith(("MULTIPOLYGON", "POLYGON")):
        return "poligono"
    return ""


def partes_wkt(wkt: str) -> tuple:
    """(tipo, partes): puntos [(x, y)], líneas [[(x, y)...]], polígonos
    [[anillo exterior, huecos...]]. Con Z o M se toman X e Y."""
    tipo = tipo_wkt(wkt)
    texto = (wkt or "").strip()
    if not tipo or texto.upper().endswith("EMPTY"):
        return tipo, []
    if tipo == "punto":
        return tipo, [p for g in _grupos(texto) for p in _pares(g)]
    if tipo == "linea":
        return tipo, [pts for pts in (_pares(g) for g in _grupos(texto)) if len(pts) >= 2]
    # polígonos: cada «((...),(...))» es uno; en MULTIPOLYGON van separados por «)),((»
    cuerpo = texto[texto.index("("):]
    if texto.upper().startswith("MULTIPOLYGON"):
        cuerpo = cuerpo[1:-1]
    poligonos = []
    for trozo in re.split(r"\)\s*\)\s*,\s*\(\s*\(", cuerpo):
        anillos = [pts for pts in (_pares(g) for g in _grupos("(" + trozo + ")")) if len(pts) >= 3]
        if anillos:
            poligonos.append(anillos)
    return tipo, poligonos
