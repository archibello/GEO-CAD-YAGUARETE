# -*- coding: utf-8 -*-
"""IGUALARPROP (MATCHPROP / MA) en Dibujo de QGIS (3.61.0): qué se copia, sin Qt.

Como nuestro IGUALARPROP de IngeCAD (3.17.0): el objeto de origen queda
resaltado, Intro lo confirma y después se designan los destinos con todas las
opciones de «Designe objetos» (V C PV PC B T U P, E quita, A agrega, H
deshace); cada paso se ve al momento y E / H devuelven a esos objetos lo que
tenían. Intro termina.

Se copia lo que guarda Dibujo en los campos de cada objeto (Fernando,
02/11/2026): capa CAD (LAYER_CODE), color (CAD_COLOR; en las capas de textos,
COLOR), tipo de línea (CAD_LTYPE) y grosor (CAD_LW); entre textos, además,
altura, fuente y negrita. Vacío = PorCapa, y se copia así. Entre polígonos,
también el relleno y su transparencia (CAD_FILL, CAD_FILLTR; 3.64.1).
"""

#: campo, tipo (para crearlo si falta) y largo
CAMPOS = {
    'LAYER_CODE': ('string', 50),
    'CAD_COLOR': ('string', 20),
    'COLOR': ('string', 20),
    'CAD_LTYPE': ('string', 40),
    'CAD_LW': ('double', 0),
    'CAD_FILL': ('string', 20),
    'CAD_FILLTR': ('double', 0),
    'ALTURA': ('double', 0),
    'FUENTE': ('string', 80),
    'NEGRITA': ('string', 4),
}
#: entre textos, además de lo CAD (las capas de textos ya los tienen)
CAMPOS_TEXTO = ('ALTURA', 'FUENTE', 'NEGRITA')

PEDIDO_ORIGEN = 'Designe objeto de origen'
PEDIDO_CONFIRMAR = 'Origen elegido (resaltado). Intro confirma; clic en otro objeto lo cambia'
PEDIDO_DESTINO = 'Designe objetos de destino (V C PV PC B T U P, E quita, H deshace, ? ayuda; Intro termina)'


def _vacio(v):
    return v is None or (isinstance(v, str) and not v.strip())


def color_campo(es_texto):
    return 'COLOR' if es_texto else 'CAD_COLOR'


def a_copiar(origen, origen_texto, destino_texto, destino_campos=None, destino_punto=False,
              destino_poligono=False):
    """{campo: valor} que el destino toma del origen.

    ``origen`` = {campo: valor} del objeto de origen (sólo los campos que su capa
    tiene); ``destino_campos`` = los campos que ya tiene la capa de destino (los
    de texto no se crean); a los puntos no va el tipo de línea (como en el panel
    Propiedades); el relleno, sólo a los polígonos. Lo que el origen no tiene (una capa sin campos CAD)
    no se toca; lo vacío se copia como PorCapa (None)."""
    out = {}
    if 'LAYER_CODE' in origen:
        v = origen['LAYER_CODE']
        out['LAYER_CODE'] = '0' if _vacio(v) else str(v)
    src = color_campo(origen_texto)
    if src in origen:
        v = origen[src]
        out[color_campo(destino_texto)] = None if _vacio(v) else str(v).lower()
    if not destino_texto:
        for campo in ('CAD_LTYPE', 'CAD_LW'):
            if campo in origen and not (destino_punto and campo == 'CAD_LTYPE'):
                v = origen[campo]
                out[campo] = None if _vacio(v) else v
    if destino_poligono:
        if 'CAD_FILL' in origen:
            v = origen['CAD_FILL']
            out['CAD_FILL'] = None if _vacio(v) else str(v).lower()
        if 'CAD_FILLTR' in origen:
            v = origen['CAD_FILLTR']
            out['CAD_FILLTR'] = None if _vacio(v) else v
    if origen_texto and destino_texto:
        for campo in CAMPOS_TEXTO:
            if campo in origen and (destino_campos is None or campo in destino_campos):
                out[campo] = origen[campo]
    return out


__all__ = ['CAMPOS', 'CAMPOS_TEXTO', 'PEDIDO_ORIGEN', 'PEDIDO_CONFIRMAR', 'PEDIDO_DESTINO',
           'color_campo', 'a_copiar']
