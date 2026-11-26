# -*- coding: utf-8 -*-
"""FILTRO (FI) en QGIS (3.97.0), el de IngeCAD.

Pedido de Fernando (26/11/2026): «debemos incorporar a QGIS la herramienta
FILTER (FI) de IngeCAD». La misma ventana (nucleo/filtro_ui.py) y las mismas
reglas (nucleo/filtro_base.py: condiciones, grupos Y/O/XO/NO, comodines);
acá, lo que es cada propiedad en una capa de QGIS con GeoCAD: el tipo de
objeto como lo muestra el panel Propiedades (Línea, Polilínea, Polígono,
Punto, Texto, Bloque), la capa CAD (LAYER_CODE), el color (CAD_COLOR, o
COLOR en los textos), el tipo y el grosor de línea, las medidas y los campos
de la tabla. Los filtros con nombre se guardan aparte de los de IngeCAD
(decidido con Fernando): ~/.config/geocad/filtros_qgis.json.

Sólo se filtran los objetos que QGIS dibuja: los de las capas CAD apagadas
no cuentan (como en IngeCAD).

Lo que no necesita QGIS (las propiedades y las cuentas) se prueba sin QGIS.
"""

import math
from pathlib import Path

from . import filtro_base as B
from .filtro_base import (GRUPOS, OPS, OPS_TEXTO, FiltroError, SIN_NOMBRE, _P,  # noqa: F401
                          _num, numero_de_color, pedido)

LINEA, POLILINEA, POLIGONO, PUNTO, TEXTO, BLOQUE = (
    'Línea', 'Polilínea', 'Polígono', 'Punto', 'Texto', 'Bloque')
LINEALES = (LINEA, POLILINEA, POLIGONO)

#: el catálogo, en el orden de la lista de la ventana
PROPIEDADES = (
    # tipos de objeto (como los muestra Propiedades)
    _P('bloque', 'Bloque', 'tipo', BLOQUE),
    _P('linea', 'Línea (2 vértices)', 'tipo', LINEA),
    _P('poligono', 'Polígono', 'tipo', POLIGONO),
    _P('polilinea', 'Polilínea', 'tipo', POLILINEA),
    _P('punto', 'Punto', 'tipo', PUNTO),
    _P('texto', 'Texto', 'tipo', TEXTO),
    _P('cerrada', 'Polilínea cerrada', 'tipo', POLILINEA),
    # geometría
    _P('inicio_linea', 'Inicio de línea', 'punto', LINEA, POLILINEA),
    _P('fin_linea', 'Fin de línea', 'punto', LINEA, POLILINEA),
    _P('pos_punto', 'Posición de punto', 'punto', PUNTO),
    _P('pos_texto', 'Posición de texto', 'punto', TEXTO),
    _P('pos_bloque', 'Posición de bloque', 'punto', BLOQUE),
    _P('centro', 'Centro (centroide)', 'punto'),
    _P('largo', 'Largo (líneas y polilíneas)', 'numero', LINEA, POLILINEA),
    _P('perimetro', 'Perímetro (polígonos)', 'numero', POLIGONO),
    _P('area', 'Área (polígonos y polilíneas cerradas)', 'numero', POLIGONO, POLILINEA),
    _P('vertices', 'Número de vértices', 'numero', LINEA, POLILINEA, POLIGONO),
    # textos y bloques
    _P('valor_texto', 'Valor de texto', 'texto', TEXTO),
    _P('altura_texto', 'Altura de texto', 'numero', TEXTO),
    _P('giro_texto', 'Giro de texto', 'numero', TEXTO),
    _P('fuente_texto', 'Fuente de texto', 'texto', TEXTO),
    _P('nombre_bloque', 'Nombre de bloque', 'texto', BLOQUE),
    # propiedades generales
    _P('color', 'Color', 'color'),
    _P('capa', 'Capa CAD', 'texto'),
    _P('tipo_linea', 'Tipo de línea', 'texto'),
    _P('grosor', 'Grosor de línea (mm)', 'numero'),
    _P('campo_qgis', 'Campo de la tabla', 'campo'),
    # grupos
    *B.PROP_GRUPOS,
)
POR_CLAVE = {p.clave: p for p in PROPIEDADES}

#: los valores que ofrece «Elegir...» en la ventana
ELEGIBLES = ('capa', 'tipo_linea', 'nombre_bloque', 'fuente_texto', 'valor_texto')


class Objeto:
    """Lo que el filtro necesita de un objeto, sin QGIS: tipo, campos
    ({NOMBRE EN MAYÚSCULAS: valor}) y geometría (partes: listas de (x, y))."""

    def __init__(self, fid, tipo, campos, partes=(), punto=None):
        self.fid = fid
        self.tipo = tipo
        self.campos = {str(k).upper(): v for k, v in (campos or {}).items()}
        self.partes = [list(p) for p in partes]
        self.punto = punto

    def campo(self, nombre, defecto=None):
        v = self.campos.get(str(nombre).upper(), defecto)
        return defecto if v is None or str(v) in ('NULL',) else v


# ------------------------------------------------------------------- medidas
def _largo(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _area(pts):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _cerrada_pts(pts):
    return len(pts) > 2 and tuple(pts[0]) == tuple(pts[-1])


def cerrada(o) -> bool:
    return o.tipo == POLILINEA and bool(o.partes) and all(_cerrada_pts(p) for p in o.partes)


#: los colores de la lista de Propiedades (también sin el módulo Capas)
BASICOS = {'#ff0000': 1, '#ffff00': 2, '#00ff00': 3, '#00ffff': 4, '#0000ff': 5, '#ff00ff': 6,
           '#414141': 8, '#808080': 9}


def _aci_de_hex(texto):
    """'#rrggbb' -> número ACI si es uno de la paleta (7 = blanco o negro);
    '' -> 256 (PorCapa); otro -> None."""
    t = str(texto or '').strip().lower()
    if t in ('', 'null', 'none', 'porcapa', 'bylayer'):
        return 256
    if t in ('#000000', '#ffffff'):
        return 7
    if t in BASICOS:
        return BASICOS[t]
    try:
        from .capas.aci import aci_to_hex
    except Exception:  # noqa: BLE001
        aci_to_hex = None
    if aci_to_hex is not None:
        for i in range(1, 256):
            try:
                if str(aci_to_hex(i)).lower() == t:
                    return i
            except Exception:  # noqa: BLE001
                break
    n = numero_de_color(t)
    return n


def valor(o, clave):
    """El valor de una propiedad del objeto (None si no la tiene)."""
    if clave == 'capa':
        return o.campo('LAYER_CODE') or '0'
    if clave == 'color':
        return _aci_de_hex(o.campo('COLOR' if o.tipo == TEXTO else 'CAD_COLOR', ''))
    if clave == 'tipo_linea':
        return o.campo('CAD_LTYPE') or 'PorCapa'
    if clave == 'grosor':
        return _num(o.campo('CAD_LW'))
    if clave == 'valor_texto':
        return o.campo('TEXTO')
    if clave == 'altura_texto':
        return _num(o.campo('ALTURA'))
    if clave == 'giro_texto':
        return _num(o.campo('ROTACION'))
    if clave == 'fuente_texto':
        return o.campo('FUENTE')
    if clave == 'nombre_bloque':
        return o.campo('NOMBRE')
    pts = [p for parte in o.partes for p in parte]
    if clave in ('inicio_linea', 'fin_linea'):
        if not o.partes or not o.partes[0]:
            return None
        return tuple(o.partes[0][0] if clave == 'inicio_linea' else o.partes[-1][-1])
    if clave in ('pos_punto', 'pos_texto', 'pos_bloque'):
        return tuple(o.punto) if o.punto is not None else (tuple(pts[0]) if pts else None)
    if clave == 'centro':
        if o.punto is not None:
            return tuple(o.punto)
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    if clave == 'largo':
        return sum(_largo(p) for p in o.partes)
    if clave == 'perimetro':
        return sum(_largo(p) for p in o.partes)
    if clave == 'area':
        if o.tipo == POLIGONO:
            return o.campos.get('__AREA__', sum(_area(p[:-1] if _cerrada_pts(p) else p)
                                                for p in o.partes))
        return sum(_area(p[:-1]) for p in o.partes) if cerrada(o) else None
    if clave == 'vertices':
        return sum(len(p) - (1 if _cerrada_pts(p) else 0) for p in o.partes)
    return None


def cumple(o, cond):
    """¿El objeto cumple una condición (no un grupo)?"""
    clave = cond.get('p')
    prop = POR_CLAVE.get(clave)
    if prop is None:
        raise FiltroError('propiedad desconocida: %s' % clave)
    if prop.clase == 'tipo':
        if clave == 'cerrada':
            return cerrada(o)
        return o.tipo in prop.tipos
    if prop.tipos and o.tipo not in prop.tipos:
        return False
    if prop.clase == 'campo':
        nombre = str(cond.get('campo', '')).strip().upper()
        if nombre not in o.campos:
            return False
        return B.cumple_campo(o.campos.get(nombre), cond)
    return B.cumple_valor(prop, cond, valor(o, clave))


def arbol(conds):
    return B.arbol(conds, POR_CLAVE)


def filtrar(objetos, conds, document=None):
    """Los objetos que cumplen el filtro (todos si la lista está vacía)."""
    raiz = arbol(conds)
    return [o for o in objetos if B.evaluar(o, raiz, cumple)]


def describir(cond):
    return B.describir(cond, POR_CLAVE)


sangrias = B.sangrias


def de_objeto(o):
    """Las condiciones que describen ``o`` («Agregar objeto seleccionado»):
    el tipo, la capa CAD, el color y lo propio de su tipo."""
    out = []
    for p in PROPIEDADES:
        if p.clase == 'tipo' and p.clave != 'cerrada' and o.tipo in p.tipos:
            out.append({'p': p.clave})
            break
    out.append({'p': 'capa', 'op': '=', 'v': valor(o, 'capa')})
    c = valor(o, 'color')
    if c is not None:
        out.append({'p': 'color', 'op': '=', 'v': c})
    for clave in ('valor_texto', 'altura_texto', 'nombre_bloque'):
        if o.tipo in POR_CLAVE[clave].tipos:
            v = valor(o, clave)
            if v not in (None, ''):
                out.append({'p': clave, 'op': '=', 'v': round(v, 6) if isinstance(v, float) else v})
    return out


def valores_en(objetos, clave):
    """Los valores distintos de una propiedad de texto en la capa."""
    out = set()
    for o in objetos:
        try:
            v = valor(o, clave)
        except Exception:  # noqa: BLE001
            continue
        if v not in (None, ''):
            out.add(str(v))
    return sorted(out, key=str.upper)


def campos_en(capa):
    """Los campos de la tabla de la capa (``capa``: QgsVectorLayer o lista de nombres)."""
    if capa is None:
        return []
    if isinstance(capa, (list, tuple)):
        return list(capa)
    try:
        return [f.name() for f in capa.fields()]
    except Exception:  # noqa: BLE001
        return []


# ----------------------------------------------------------------- guardados
def _archivo():
    return Path.home() / '.config' / 'geocad' / 'filtros_qgis.json'


_GUARDADOS = B.Guardados(lambda: _archivo(), POR_CLAVE)


def guardados():
    return _GUARDADOS.todos()


def guardar(nombre, conds):
    _GUARDADOS.guardar(nombre, conds)


def borrar(nombre):
    return _GUARDADOS.borrar(nombre)


def buscar(nombre):
    return _GUARDADOS.buscar(nombre)


def recordar(conds):
    _GUARDADOS.recordar(conds)


def ultimo():
    return _GUARDADOS.ultimo()


# ------------------------------------------------------------- en QGIS
def objeto(layer, feature):
    """El Objeto de un objeto de QGIS (coordenadas de la capa)."""
    from .dibujo.properties_panel import kind_of
    tipo = kind_of(layer, feature)
    campos = {fl.name(): feature.attribute(fl.name()) for fl in layer.fields()}
    partes, punto = [], None
    g = feature.geometry()
    if g is not None and not g.isEmpty():
        if tipo in (PUNTO, TEXTO, BLOQUE):
            try:
                p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
                punto = (p.x(), p.y())
            except Exception:  # noqa: BLE001
                punto = None
        else:
            try:
                from .dibujo.editkit import explode
                _k, _s, partes, _i = explode(g)
            except Exception:  # noqa: BLE001
                partes = []
            if tipo == POLIGONO:
                campos['__AREA__'] = g.area()
    return Objeto(feature.id(), tipo, campos, partes, punto)


def candidatos(canvas, layer, fids=None):
    """Los objetos de la capa (o de ``fids``) que QGIS dibuja: los de capas CAD
    apagadas no cuentan."""
    from qgis.core import QgsFeatureRequest
    from .dibujo.editkit import Visibles
    req = QgsFeatureRequest() if fids is None else QgsFeatureRequest().setFilterFids(list(fids))
    with Visibles(canvas, layer) as ve:
        return [objeto(layer, f) for f in layer.getFeatures(req) if ve(f)]
