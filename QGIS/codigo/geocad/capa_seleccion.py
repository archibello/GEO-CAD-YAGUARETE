# SPDX-License-Identifier: GPL-3.0-or-later
"""CREAR CAPA A PARTIR DE ELEMENTOS SELECCIONADOS (3.73.0): las reglas, sin Qt ni QGIS.

Fernando, 08/11/2026: «quiero que incorpores a GeoCAD esta herramienta, y
reemplaces el complemento externo por completo».

La capa nueva es una vista filtrada de la misma fuente: no se escribe ningún
archivo. El filtro depende del proveedor de datos:

* memory, delimitedtext: el identificador propio de QGIS, $id;
* con una clave primaria simple (GeoPackage, PostGIS, SpatiaLite...): esa columna;
* ogr sin clave (shapefile, GeoJSON...): el FID de OGR;
* lo demás (sin clave, clave compuesta): no se puede filtrar y se avisa.

Lo que QGIS hace con el filtro lo mide capa_seleccion_qgis.py antes de agregar
la capa al proyecto. Lo prueba test_capa_seleccion.py.
"""
from __future__ import annotations

TITULO = "Crear capa a partir de elementos seleccionados"
SUFIJO = "_filtered"
CON_ID_PROPIO = ("memory", "delimitedtext")


def nombre_libre(base: str, usados) -> str:
    """«base_filtered», y si ya está, «base_filtered_1», «base_filtered_2»..."""
    usados = set(usados)
    nombre = primero = base + SUFIJO
    n = 1
    while nombre in usados:
        nombre = "%s_%d" % (primero, n)
        n += 1
    return nombre


def separar(ids) -> tuple:
    """(guardados, sin_guardar): QGIS numera en negativo lo agregado sin guardar,
    que todavía no existe en la fuente y por eso no se puede filtrar."""
    guardados, sin_guardar = [], []
    for i in sorted(ids):
        (guardados if i >= 0 else sin_guardar).append(i)
    return guardados, sin_guardar


def campo_sql(nombre: str) -> str:
    return '"%s"' % nombre.replace('"', '""')


def literal(valor) -> str | None:
    """El valor en SQL; None si no es un entero ni un texto."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, str):
        return "'%s'" % valor.replace("'", "''")
    return None


def _en_lista(campo: str, valores) -> str | None:
    literales = [literal(v) for v in valores]
    if not literales or None in literales:
        return None
    return "%s IN (%s)" % (campo, ",".join(literales))


def filtro(proveedor: str, ids, claves=(), valores=None) -> str | None:
    """La condición que deja sólo ``ids``, o None si la fuente no permite armarla.

    ``claves`` son las columnas de la clave primaria y ``valores`` los de la
    columna única para cada id, en el mismo orden."""
    ids = list(ids)
    if not ids:
        return None
    if proveedor in CON_ID_PROPIO:
        return _en_lista("$id", ids)
    claves = list(claves)
    if len(claves) == 1:
        valores = list(valores or ())
        if len(valores) != len(ids):
            return None
        return _en_lista(campo_sql(claves[0]), valores)
    if not claves and proveedor == "ogr":
        return _en_lista("FID", ids)
    return None
