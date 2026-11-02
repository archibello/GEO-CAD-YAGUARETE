# -*- coding: utf-8 -*-
"""Filtros de grupo del panel de capas, como los de IngeCAD 0.7.0 (3.60.0).

IngeCAD lee y guarda en el dibujo los filtros de capas de AutoCAD; acá viven
en la configuración de capas CAD de cada capa QGIS (``cfg['filters']``):

    [{'name': 'Filtro de grupo1', 'layers': ['Capa1', ...], 'children': [...]}]

Un grupo muestra sólo las capas que se le pusieron (no las de sus hijos),
los nombres de filtro no se repiten (sin mirar mayúsculas) y un *camino* es
la tupla de nombres desde arriba. Python puro: se prueba sin Qt.
"""

BASE = 'Filtro de grupo'


def normalize(raw):
    """Una lista de filtros limpia (lo dañado o repetido queda fuera)."""
    vistos = set()

    def limpiar(lista):
        salida = []
        for f in lista if isinstance(lista, list) else ():
            if not isinstance(f, dict):
                continue
            nombre = str(f.get('name') or '').strip()
            if not nombre or nombre.lower() in vistos:
                continue
            vistos.add(nombre.lower())
            capas = []
            for n in f.get('layers') or ():
                if isinstance(n, str) and n not in capas:
                    capas.append(n)
            salida.append({'name': nombre, 'layers': capas,
                           'children': limpiar(f.get('children'))})
        return salida
    return limpiar(raw)


def rows(filters):
    """El árbol aplanado en orden de pantalla: [(camino, profundidad, filtro)]."""
    salida = []

    def recorrer(lista, camino):
        for f in lista:
            propio = camino + (f['name'],)
            salida.append((propio, len(camino), f))
            recorrer(f['children'], propio)
    recorrer(filters, ())
    return salida


def find(filters, path):
    """El filtro de ``path`` o None."""
    lista, f = filters, None
    for nombre in path or ():
        f = next((x for x in lista if x['name'] == nombre), None)
        if f is None:
            return None
        lista = f['children']
    return f


def names(filters):
    """Los nombres de todos los filtros, en minúsculas."""
    return {f['name'].lower() for _c, _p, f in rows(filters)}


def unique_name(filters):
    tomados = names(filters)
    n = 1
    while ('%s%d' % (BASE, n)).lower() in tomados:
        n += 1
    return '%s%d' % (BASE, n)


def new_group(filters, parent=(), name=None, layers=()):
    """Agrega un grupo dentro de ``parent`` (arriba con ``()``); devuelve su camino
    o None si ``parent`` no existe o el nombre ya está."""
    name = (name or unique_name(filters)).strip()
    if not name or name.lower() in names(filters):
        return None
    if parent:
        padre = find(filters, parent)
        if padre is None:
            return None
        destino = padre['children']
    else:
        destino = filters
    destino.append({'name': name, 'layers': [n for i, n in enumerate(layers)
                                             if n not in list(layers)[:i]],
                    'children': []})
    return tuple(parent) + (name,)


def delete(filters, path):
    """Saca el filtro de ``path`` (con sus hijos). True si estaba."""
    if not path:
        return False
    lista = filters if len(path) == 1 else (find(filters, path[:-1]) or {}).get('children')
    if lista is None:
        return False
    for i, f in enumerate(lista):
        if f['name'] == path[-1]:
            del lista[i]
            return True
    return False


def rename(filters, path, new):
    """Cambia el nombre; devuelve un mensaje de error o None."""
    f = find(filters, path)
    new = (new or '').strip()
    if f is None or not new:
        return 'No existe el filtro.' if f is None else 'El nombre no puede estar vacío.'
    if new.lower() in names(filters) - {f['name'].lower()}:
        return 'Ya existe un filtro llamado %s.' % new
    f['name'] = new
    return None


def group_layers(filters, path, layer_names, add=True):
    """Pone (o saca) capas de un grupo. Devuelve cuántas cambiaron."""
    f = find(filters, path)
    if f is None:
        return 0
    n = 0
    for nombre in layer_names:
        if add and nombre not in f['layers']:
            f['layers'].append(nombre)
            n += 1
        elif not add and nombre in f['layers']:
            f['layers'].remove(nombre)
            n += 1
    return n


def rename_layer(filters, old, new):
    """Una capa cambió de nombre: los grupos la siguen."""
    for _c, _p, f in rows(filters):
        f['layers'] = [new if n == old else n for n in f['layers']]


def drop_layers(filters, layer_names):
    """Capas suprimidas: salen de todos los grupos."""
    fuera = set(layer_names)
    for _c, _p, f in rows(filters):
        f['layers'] = [n for n in f['layers'] if n not in fuera]
