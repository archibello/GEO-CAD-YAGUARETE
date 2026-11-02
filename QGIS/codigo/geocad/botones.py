# SPDX-License-Identifier: GPL-3.0-or-later
"""Administrar botones: categorías propias para los botones de GeoCAD (3.38.0).

Pedido de Fernando (24/10/2026): crear categorías y agrupar en ellas los
botones de la misma familia, en IngeCAD y en QGIS. Cada categoría es una
barra separada; los botones se pueden ocultar y reordenar. Cada programa
tiene sus categorías (los botones no son los mismos), en un solo archivo:

    ~/.config/geocad/botones.json

Sin nada guardado para un programa valen las categorías de fábrica
(``DEFECTO``, desde la 3.39.0 las de Fernando; los botones que no figuran
quedan en su barra de siempre). Si lo elegido es igual a la fábrica no se
guarda nada. Apagado GeoCAD, las barras de siempre (botones_barras.py).

Python puro (sin Qt): lo usan los dos programas. Un *modelo* es la lista
``[(categoría, [(botón, visible), ...]), ...]``; la *fábrica* es
``[(barra, [botón, ...]), ...]`` con los botones que hay hoy.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .buzon import _reemplazar      # reintenta en Windows si el otro programa lo está leyendo

VERSION = 1

#: las categorías de fábrica: el último estado de Fernando (25/10/2026: «la
#: configuración por defecto, para versiones futuras, siempre va a ser el último
#: estado»; al armar cada versión se copia de nuevo). Los botones que no figuran
#: quedan en su barra de siempre. De fábrica todas las barras están APAGADAS
#: (3.47.0: «el estado inicial por defecto es de todas las barras apagadas»).
DEFECTO = {
    "ingecad": (
        ("Yaguá GEO", ("GEOCRS", "GEOREPROJECT")),
        ("Yaguá Dibujo", ("RECTANG", "TEXT", "SHPNEW", "SHPLABEL", "SHPTHEME")),
        ("Yaguá Imagenes", (
            "INSERTARGEO", "GEORREF", "EXPORTARGEO", "ASPECTOIMAGEN", "GEOPASTEIMAGE",)),
        ("Yaguá Blocks", ("BLOCK", "INSERT", "GEOREFEDIT", "GEOBLOCKBASE")),
        ("Yaguá Cotas", ("GEODIMSETUP", "DIMLINEAR", "DIMALIGNED", "DIMANGULAR")),
        ("Yaguá Print", ("GEOPREVIEW", "GEOPLOTSTYLES")),
        ("Yaguá Select", ("SELECT", "GEOFILTER")),
        ("Yaguá Tablas", ("SHPTABLE", "SHPQUERY", "SHPSPATIAL", "GEOPASTETABLE")),
        ("Yaguá interacción", (
            "GEOIMPORTSHP", "GEOEXPORTSHP", "GEOEXPORTKML", "GEOIMPORTKML", "QGISEXPORT",)),
        ("Yaguá Edición", (
            "GEODRAWFRONT", "GEODRAWBACK", "STRETCH", "BREAKATPOINT", "CHAMFER", "FILLET",
            "MATCHPROP",)),
    ),
    "qgis": (
        ("Yaguá Dibujo", (
            "dibujo:line", "dibujo:pline", "dibujo:arc", "dibujo:circle", "dibujo:rect",
            "dibujo:rumbos", "dibujo:relangle", "dibujo:gmsblocks",)),
        ("Yaguá Edición", (
            "dibujo:select", "dibujo:move", "dibujo:copy", "dibujo:rotate", "dibujo:erase",
            "dibujo:mirror", "dibujo:align", "dibujo:stretch", "dibujo:offset", "dibujo:trim",
            "dibujo:extend", "dibujo:chamfer", "dibujo:fillet", "dibujo:perp", "dibujo:breakpt", "dibujo:break",
            "dibujo:explode", "dibujo:divide", "dibujo:measure", "dibujo:copybase",
            "dibujo:pastebase", "dibujo:aligncopy",)),
        ("Yaguá Texto", (
            "dibujo:dtext", "dibujo:edittext", "dibujo:seltext", "dibujo:bold", "dibujo:font",
            "dibujo:size", "dibujo:textcolor",)),
        ("Yaguá Bloques", ("dibujo:block", "dibujo:insert", "dibujo:wblock", "dibujo:purge")),
        ("Yaguá Impresión", ("dibujo:plot", "dibujo:layout", "dibujo:mview")),
        # 3.60.0: la barra de IngeCAD (Fernando, 01/11/2026), lista de capa + propiedades;
        # 3.60.2: y primero el botón del panel Yaguá Capas
        ("Yaguá Capas", ("capas:layprops", "capas:capa", "capas:color", "capas:linetype",
                         "capas:lineweight")),
        ("Yaguá-IngeCAD", ("puente:send",)),
        ("Yaguá Setting", (
            "dibujo:units", "dibujo:osnap", "dibujo:ortho", "dibujo:properties", "dibujo:cmdline",)),
    ),
}

#: los botones ocultos de fábrica (el último estado de Fernando, 25/10/2026)
OCULTOS = {
    "ingecad": ("SHPTHEME", "GEOPREVIEW", "GEOPLOTSTYLES", "SHPQUERY", "SHPSPATIAL"),
}

#: lo único a la vista desde el primer momento: los botones de IngeCAD que GeoCAD
#: reconfiguró y sacó de sus barras (yaguarete.HERRAMIENTAS con barra de origen).
#: Fernando, 25/10/2026: «solo los botones que geocad reconfiguró de ingecad deben
#: permanecer por defecto desde el primer momento, para que otros usuarios no se
#: confundan». Sus categorías arrancan prendidas con sólo ellos tildados.
PRENDIDOS = {
    "ingecad": ("RECTANG", "TEXT", "STRETCH", "CHAMFER", "FILLET", "MATCHPROP"),
}


#: los bancos de respaldo (3.60.7, Fernando, 02/11/2026: «dos listados de botones
#: de respaldo que permanecerán apagados por defecto ... un banco de botones para
#: recurrir en caso de recuperación, para armar las barras de herramientas
#: personalizadas»): en la fábrica, ``(BANCO + título, [botones])`` con TODOS los
#: botones de un submenú (Dibujo CAD, Capas CAD), también los que ya están en una
#: categoría. Nunca son una categoría ni una barra: de ahí se traen botones.
BANCO = "banco:"


def es_banco(nombre: str) -> bool:
    return str(nombre).startswith(BANCO)


def de_fabrica(programa: str):
    """Las categorías de fábrica de ``programa`` como si estuvieran guardadas
    (o None: sin categorías de fábrica, las barras de siempre). Todas
    apagadas, también las de los botones que no figuran (``"todas"``),
    menos las que tienen botones de ``PRENDIDOS``: prendidas con sólo ésos."""
    cats = DEFECTO.get(programa)
    if not cats:
        return None
    prendidos = set(PRENDIDOS.get(programa, ()))
    prendidas = [n for n, b in cats if prendidos & set(b)]
    ocultos = list(OCULTOS.get(programa, ()))
    ocultos += [x for n, b in cats if n in prendidas for x in b
                if x not in prendidos and x not in ocultos]
    return {"categorias": [{"nombre": n, "botones": list(b)} for n, b in cats],
            "ocultos": ocultos, "apagadas": [], "todas": True, "prendidas": prendidas}


#: conversiones de lo guardado, una sola vez cada una (se anotan en «migraciones»).
#: «capas-ingecad» (3.60.0): Yaguá Capas pasa a ser la barra de IngeCAD; la lista
#: de capa sale de donde estuviera (los botones viejos de capas ya no son botones).
CAPAS_INGECAD = ("capas:capa", "capas:color", "capas:linetype", "capas:lineweight")
#: «capas-panel» (3.60.2): el botón del panel Yaguá Capas, primero en Yaguá Capas.
#: «capas-banco» (3.60.7): los comandos que la 3.60.0 sacó de la barra de capas
#: vuelven a ser botones, pero sólo en el banco Capas CAD (Fernando, 02/11/2026:
#: «quedan en el banco»): fuera de lo guardado antes, para que no reaparezcan solos.
CAPAS_BANCO = tuple("capas:" + c for c in (
    "laymcur", "layerp", "laymch", "layiso", "layuniso", "layoff", "layfrz", "laylck",
    "layulk", "layon", "laythw", "lwdisplay"))
MIGRACIONES = {"qgis": ("capas-ingecad", "capas-panel", "capas-banco")}


def _migrar(programa: str, crudo: dict) -> bool:
    """Aplica a ``crudo`` las conversiones pendientes; True si cambió algo."""
    hechas = list(crudo.get("migraciones") or ())
    cambio = False
    for nombre in MIGRACIONES.get(programa, ()):
        if nombre in hechas:
            continue
        hechas.append(nombre)
        cambio = True
        if nombre == "capas-ingecad":
            cats = [c for c in crudo.get("categorias") or () if isinstance(c, dict)]
            for c in cats:
                c["botones"] = [b for b in c.get("botones") or () if b not in CAPAS_INGECAD]
            destino = next((c for c in cats if c.get("nombre") == "Yaguá Capas"), None)
            if destino is None:
                destino = {"nombre": "Yaguá Capas", "botones": []}
                cats.append(destino)
            destino["botones"] = list(CAPAS_INGECAD) + destino["botones"]
            crudo["categorias"] = cats
            crudo["ocultos"] = [b for b in crudo.get("ocultos") or () if b not in CAPAS_INGECAD]
        elif nombre == "capas-panel":
            cats = [c for c in crudo.get("categorias") or () if isinstance(c, dict)]
            for c in cats:
                c["botones"] = [b for b in c.get("botones") or () if b != "capas:layprops"]
            destino = next((c for c in cats if c.get("nombre") == "Yaguá Capas"), None)
            if destino is None:
                destino = {"nombre": "Yaguá Capas", "botones": []}
                cats.append(destino)
            destino["botones"] = ["capas:layprops"] + destino["botones"]
            crudo["categorias"] = cats
            crudo["ocultos"] = [b for b in crudo.get("ocultos") or () if b != "capas:layprops"]
        elif nombre == "capas-banco":
            for c in crudo.get("categorias") or ():
                if isinstance(c, dict):
                    c["botones"] = [b for b in c.get("botones") or () if b not in CAPAS_BANCO]
            crudo["ocultos"] = [b for b in crudo.get("ocultos") or () if b not in CAPAS_BANCO]
    crudo["migraciones"] = hechas
    return cambio


def archivo() -> Path:
    return Path.home() / ".config" / "geocad" / "botones.json"


def _leer_todo() -> dict:
    try:
        data = json.loads(archivo().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def leer(programa: str):
    """Lo guardado para ``programa`` ({"categorias": [...], "ocultos": [...]})
    o None si está como de fábrica (o el archivo está dañado)."""
    data = _leer_todo()
    crudo = data.get(programa)
    if not isinstance(crudo, dict) or not isinstance(crudo.get("categorias"), list):
        return None
    if _migrar(programa, crudo):
        try:
            _escribir(data)
        except OSError:
            pass
    categorias, vistos = [], set()
    for cat in crudo["categorias"]:
        if not isinstance(cat, dict):
            continue
        nombre = str(cat.get("nombre") or "").strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)
        botones = [str(b) for b in cat.get("botones") or () if isinstance(b, str)]
        categorias.append({"nombre": nombre, "botones": botones})
    ocultos = [str(b) for b in crudo.get("ocultos") or () if isinstance(b, str)]
    # sin «apagadas» (guardado antes de la 3.47.0): todas prendidas, como estaban
    apagadas = [str(n) for n in crudo.get("apagadas") or () if isinstance(n, str)]
    return {"categorias": categorias, "ocultos": ocultos, "apagadas": apagadas}


def _escribir(data: dict) -> None:
    ruta = archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    data["_version"] = VERSION
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".botones-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    _reemplazar(tmp, ruta)


def distribuir(fabrica, guardado=None, programa=None) -> list:
    """El modelo completo: lo guardado, con los botones que ya no existen
    fuera y los que no estaban (módulos nuevos, versiones nuevas) en la
    categoría de su barra de siempre (al final, creada si no está). Sin
    nada guardado, las categorías de fábrica de ``programa``; sin ellas,
    las barras de siempre tal cual. Las categorías vacías se conservan."""
    if guardado is None and programa:
        guardado = de_fabrica(programa)
    existen = {}
    for barra, botones in fabrica:
        for b in botones:
            existen.setdefault(b, barra)
    # lo que sólo está en un banco no va a ninguna categoría hasta que se lo traiga
    fabrica = [(barra, botones) for barra, botones in fabrica if not es_banco(barra)]
    if guardado is None:
        return [(barra, [(b, True) for b in botones if existen.get(b) == barra])
                for barra, botones in fabrica]
    ocultos = set(guardado.get("ocultos") or ())
    modelo, puestos = [], set()
    for cat in guardado.get("categorias") or ():
        fila = []
        for b in cat["botones"]:
            if b in existen and b not in puestos:
                puestos.add(b)
                fila.append((b, b not in ocultos))
        modelo.append((cat["nombre"], fila))
    for barra, botones in fabrica:
        faltan = [b for b in botones if b not in puestos and existen.get(b) == barra]
        if not faltan:
            continue
        destino = next((fila for nombre, fila in modelo if nombre == barra), None)
        if destino is None:
            destino = []
            modelo.append((barra, destino))
        for b in faltan:
            puestos.add(b)
            destino.append((b, b not in ocultos))
    return modelo


def apagadas_de(modelo, guardado) -> set:
    """Las categorías apagadas de ``modelo`` (todas, si ``guardado`` es la fábrica)."""
    if not guardado:
        return set()
    if guardado.get("todas"):
        return {n for n, _f in modelo} - set(guardado.get("prendidas") or ())
    return {n for n, _f in modelo} & set(guardado.get("apagadas") or ())


def apagadas(programa: str, modelo) -> set:
    """Las categorías apagadas de ``modelo``, según lo guardado o la fábrica."""
    return apagadas_de(modelo, leer(programa) or de_fabrica(programa))


def config_de(modelo, apagadas=()) -> dict:
    return {"categorias": [{"nombre": n, "botones": [b for b, _v in fila]} for n, fila in modelo],
            "ocultos": [b for _n, fila in modelo for b, v in fila if not v],
            "apagadas": [n for n, _f in modelo if n in set(apagadas)]}


def es_fabrica(modelo, fabrica, programa=None, apagadas=None) -> bool:
    """¿Igual a la fábrica? ``apagadas`` None: no se mira (sin barras apagadas
    en la fábrica se pide que no haya ninguna)."""
    if [(n, list(fila)) for n, fila in modelo] != distribuir(fabrica, None, programa):
        return False
    if apagadas is None:
        return True
    return set(apagadas) == apagadas_de(modelo, de_fabrica(programa) if programa else None)


def guardar(programa: str, modelo, fabrica, apagadas=()) -> None:
    """Guarda el modelo de ``programa`` (sin tocar el del otro). Si es igual a
    la fábrica (también en lo apagado), borra lo guardado: las barras vuelven
    a ser las de fábrica. ``apagadas``: las categorías sin barra."""
    data = _leer_todo()
    if es_fabrica(modelo, fabrica, programa, apagadas):
        data.pop(programa, None)
    else:
        nuevo = config_de(modelo, apagadas)
        # los botones de un módulo apagado no están hoy: siguen en su
        # categoría para cuando el módulo se vuelva a prender
        existen = {b for _barra, botones in fabrica for b in botones}
        anterior = leer(programa) or de_fabrica(programa) or {"categorias": [], "ocultos": []}
        por_nombre = {c["nombre"]: c["botones"] for c in nuevo["categorias"]}
        for cat in anterior["categorias"]:
            if cat["nombre"] in por_nombre:
                por_nombre[cat["nombre"]] += [b for b in cat["botones"] if b not in existen
                                              and b not in por_nombre[cat["nombre"]]]
        nuevo["ocultos"] += [b for b in anterior["ocultos"] if b not in existen]
        nuevo["migraciones"] = list(MIGRACIONES.get(programa, ()))   # ya están aplicadas
        data[programa] = nuevo
    _escribir(data)


def restablecer(programa: str) -> None:
    data = _leer_todo()
    if programa in data:
        data.pop(programa)
        _escribir(data)


def barras(programa: str, fabrica):
    """[(categoría, [botones visibles])] de las categorías prendidas, para
    armar las barras ([] = todas apagadas: ninguna barra), o None si quedan
    las barras de siempre (nada que cambiar)."""
    modelo = distribuir(fabrica, leer(programa), programa)
    fuera = apagadas(programa, modelo)
    if not fuera and [(n, list(fila)) for n, fila in modelo] == distribuir(fabrica):
        return None
    return [(n, [b for b, v in fila if v]) for n, fila in modelo if n not in fuera]


def por_temas(modelo, tema_de, nombres=None) -> list:
    """Una categoría por tema (``tema_de(botón)``), en el orden en que
    aparecen; lo oculto sigue oculto. ``nombres``: {tema: nombre visible}."""
    nombres = nombres or {}
    salida, indice = [], {}
    for _n, fila in modelo:
        for b, v in fila:
            tema = tema_de(b) or "otros"
            nombre = nombres.get(tema, str(tema).capitalize())
            if nombre not in indice:
                indice[nombre] = []
                salida.append((nombre, indice[nombre]))
            indice[nombre].append((b, v))
    return salida


def objeto_barra(nombre: str) -> str:
    """El objectName de la barra de una categoría (estable: el programa
    recuerda dónde quedó cada barra)."""
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return "GeoCADCategoria_" + (re.sub(r"[^A-Za-z0-9]+", "_", plano).strip("_") or "sin_nombre")
