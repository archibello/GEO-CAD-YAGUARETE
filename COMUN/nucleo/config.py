# SPDX-License-Identifier: GPL-3.0-or-later
"""Configuración COMÚN entre IngeCAD y QGIS.

Un único archivo JSON que leen y escriben los dos programas:

    ~/.config/geocad/configuracion.json

Se usa ``Path.home()`` a propósito y no ``XDG_CONFIG_HOME``: dentro del
Flatpak de IngeCAD esa variable apunta a ~/.var/app/..., y QGIS no la
vería. Así los dos menús muestran siempre los mismos valores.

Este módulo es Python puro (sin Qt ni IngeCAD) para que el complemento de
QGIS use exactamente el mismo código y la misma lista de ajustes.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

VERSION = 1


def config_path() -> Path:
    return Path.home() / ".config" / "geocad" / "configuracion.json"


def old_config_path() -> Path:
    """Donde la guardaba el Puente IngeCAD-QGIS 1.x."""
    return Path.home() / ".config" / "ingecad-qgis" / "configuracion.json"


def migrar() -> bool:
    """La primera vez, trae la configuración del Puente 1.x (no la borra).
    True si copió algo."""
    nuevo, viejo = config_path(), old_config_path()
    if nuevo.exists() or not viejo.is_file():
        return False
    try:
        nuevo.parent.mkdir(parents=True, exist_ok=True)
        nuevo.write_bytes(viejo.read_bytes())
        return True
    except OSError:
        return False


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    kind: str                 # choice, text, int, float, bool
    default: object
    help: str = ""
    choices: tuple = ()       # ((valor, etiqueta), ...)
    minimum: float = 0
    maximum: float = 0


def _crs_choices():
    from .crs import DATUMS

    out = [("", "Automático: el de la primera capa conectada")]
    for name, base, _geo in DATUMS:
        for faja in range(1, 8):
            out.append((f"EPSG:{base + faja - 1}", f"{name} / faja {faja} (EPSG:{base + faja - 1})"))
    for zone in (19, 20, 21):
        out.append((f"EPSG:{32700 + zone}", f"WGS 84 / UTM {zone}S (EPSG:{32700 + zone})"))
    return tuple(out)


SETTINGS = (
    Setting("formato_trabajo", "Formato de trabajo", "choice", "gpkg",
            "En qué formato se mandan los datos de QGIS a IngeCAD.",
            (("gpkg", "GeoPackage (recomendado)"), ("shp", "Shapefile"))),
    Setting("envio_predeterminado", "Qué manda el botón «Enviar a IngeCAD» de QGIS", "choice",
            "seleccion", "Los otros modos siguen en el menú.",
            (("seleccion", "Los objetos seleccionados"),
             ("pantalla", "Lo que está en pantalla"),
             ("completa", "Las capas visibles completas"))),
    Setting("envio_capas_colores", "Mandar a IngeCAD las capas (LAYER_CODE) y los colores de QGIS",
            "bool", True, "Al guardar, los cambios de capa y color vuelven a LAYER_CODE y "
            "CAD_COLOR si la tabla tiene esos campos."),
    Setting("envio_rotulos", "Mandar los rótulos de QGIS como textos", "bool", True,
            "Texto, altura y giro como están en Propiedades de la capa > Etiquetas."),
    Setting("rotulos_visibles", "Rótulos: sólo los que QGIS muestra (si no, todos)", "bool", True,
            "QGIS esconde los que no entran o chocan con otros."),
    Setting("rotulos_cuales", "Qué rótulos mandar a IngeCAD", "choice", "visibles_resto",
            "Con «sólo los que QGIS muestra en pantalla» quedan afuera los de fuera de la pantalla.",
            (("visibles_resto", "Los que QGIS muestra en pantalla y todos los de fuera"),
             ("visibles_zona", "Los que QGIS mostraría en toda la zona enviada"),
             ("todos", "Todos (también los que QGIS no muestra)"),
             ("visibles", "Sólo los que QGIS muestra ahora en pantalla"))),
    Setting("envio_simbolos", "Mandar los puntos con su símbolo (forma, tamaño y giro de QGIS)",
            "bool", True),
    Setting("ajustar_a_parcela", "Achicar rótulos y símbolos que superan su parcela "
            "(si no, tamaño real)", "bool", False),
    Setting("preguntar_al_enviar", "Preguntar estas opciones cada vez que se envía a IngeCAD",
            "bool", True, "Las opciones de envío se eligen en una ventana al enviar."),
    Setting("escala_rotulos", "Escala para la altura de los rótulos (0 = la del mapa al enviar)",
            "int", 0, "Un rótulo de 2,5 mm a escala 1:1000 llega con 2,5 m de alto.", (), 0, 100000000),
    Setting("crs_proyecto", "Sistema de coordenadas del proyecto", "choice", "",
            "Si se fija, no se conecta ninguna capa en otro sistema.", _crs_choices()),
    Setting("confirmar_guardado", "Pedir confirmación antes de guardar", "bool", True),
    Setting("carpeta_respaldos", "Carpeta de respaldos (junto a los datos)", "text",
            "_respaldos_ingecad"),
    Setting("respaldos_a_conservar", "Respaldos a conservar por capa (0 = todos)", "int", 0,
            "Al pasar este número se borran los más viejos.", (), 0, 1000),
    Setting("tolerancia_arcos", "Ángulo máximo por tramo al convertir arcos (grados)",
            "float", 5.0, "Menor = más vértices y más fidelidad al arco.", (), 0.5, 45),
    Setting("altura_rotulos", "Altura de los rótulos (unidades del dibujo)", "float", 2.5,
            "Altura de texto que propone el comando de rótulos.", (), 0.01, 10000),
    Setting("bloquear_en_qgis", "En QGIS, solo lectura para las capas tomadas por IngeCAD",
            "bool", True),
    Setting("recargar_qgis", "Recargar la capa en QGIS cuando IngeCAD guarda", "bool", True),
    Setting("mostrar_botones", "Mostrar también botones (además del menú)", "bool", False,
            "El menú está siempre; los botones son opcionales."),
    Setting("carpeta_actualizaciones", "Carpeta de donde se actualiza GeoCAD Yaguareté", "text", "",
            "La carpeta del proyecto (o donde se copian las entregas). "
            "Se busca ahí la versión más nueva."),
)
BY_KEY = {s.key: s for s in SETTINGS}


def validate(key: str, value):
    """El valor convertido y verificado, o ValueError con el motivo."""
    s = BY_KEY[key]
    if s.kind == "bool":
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("1", "si", "sí", "s", "v", "true", "verdadero"):
                return True
            if low in ("0", "no", "n", "f", "false", "falso"):
                return False
            raise ValueError(f"{s.label}: use Sí o No")
        return bool(value)
    if s.kind == "int":
        try:
            v = int(str(value).strip())
        except ValueError:
            raise ValueError(f"{s.label}: debe ser un número entero")
        if not s.minimum <= v <= s.maximum:
            raise ValueError(f"{s.label}: entre {int(s.minimum)} y {int(s.maximum)}")
        return v
    if s.kind == "float":
        try:
            v = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"{s.label}: debe ser un número")
        if not s.minimum <= v <= s.maximum:
            raise ValueError(f"{s.label}: entre {s.minimum:g} y {s.maximum:g}")
        return v
    if s.kind == "choice":
        allowed = [c[0] for c in s.choices]
        if value not in allowed:
            raise ValueError(f"{s.label}: valor no válido")
        return value
    v = str(value).strip()
    if s.key == "carpeta_respaldos":
        if not v or "/" in v or "\\" in v or v in (".", ".."):
            raise ValueError("Carpeta de respaldos: un nombre simple, sin barras")
    return v


def load() -> dict:
    """Todos los ajustes (los que falten, con su valor por defecto). Un
    archivo dañado no rompe nada: se usan los valores por defecto."""
    values = {s.key: s.default for s in SETTINGS}
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return values
    for key, raw in data.items():
        if key in BY_KEY:
            try:
                values[key] = validate(key, raw)
            except ValueError:
                pass
    return values


def get(key: str):
    return load()[key]


def save(changes: dict, program: str) -> dict:
    """Guarda ``changes`` sobre lo que haya en el archivo (sin perder
    claves que agregue el otro programa) de forma atómica."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    for key, value in changes.items():
        data[key] = validate(key, value)
    data["_version"] = VERSION
    data["_modificado_por"] = program
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".configuracion-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return load()


def display(key: str, value) -> str:
    s = BY_KEY[key]
    if s.kind == "bool":
        return "Sí" if value else "No"
    if s.kind == "choice":
        return dict(s.choices).get(value, str(value))
    return str(value)
