# -*- coding: utf-8 -*-
"""UNIR (J) con polígonos en QGIS (3.96.0): como «Combinar objetos espaciales».

La cuenta (unión, huecos encerrados que se rellenan, islas y quién da los
datos) está en el núcleo, ``combinar.py``, la misma que usa IngeCAD. Acá:
dejar el resultado en la capa original (de fábrica, un solo U) o, con N, en
la capa «combinados de <capa>», un GeoPackage con los mismos campos; la
original no se toca y las UNIR siguientes sobre la misma capa con N se
agregan a esa misma capa combinada (3.96.1).
"""

import os

from qgis.core import (QgsFeature, QgsFields, QgsProject, QgsVectorFileWriter, QgsVectorLayer,
                       QgsWkbTypes)

from .editkit import conform, copy_feature, explode, rebuild
from .. import combinar as C


def _cerrada(pts):
    return len(pts) >= 4 and tuple(pts[0]) == tuple(pts[-1])


def objetos_de(geoms):
    """{fid: [anillos]} de los polígonos (en coordenadas del mapa): los de una
    capa de polígonos y, como en IngeCAD (3.97.3), las POLILÍNEAS CERRADAS de
    una capa de líneas (todas sus partes cerradas)."""
    out = {}
    for fid, g in geoms.items():
        try:
            kind, struct, flat, _idx = explode(g)
        except ValueError:
            continue
        if kind == 'polygon':
            anillos = [r for poly in struct for r in poly if len(r) >= 4]
        elif kind == 'line':
            anillos = list(flat) if flat and all(_cerrada(p) for p in flat) else []
        else:
            anillos = []
        if anillos:
            out[fid] = anillos
    return out


def _cerrar(anillo):
    pts = list(anillo)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _de_lineas(layer):
    from .compat import geometry_kind
    return geometry_kind(layer) == 'line'


def geometria(io, isla, layer):
    """La isla en la capa (su sistema, multi/Z/M): polígono en una capa de
    polígonos; polilínea cerrada en una de líneas (3.97.3; con huecos que se
    respetan, una parte por anillo si la capa es multi, si no sólo el borde)."""
    anillos = [_cerrar(r) for r in isla['anillos']]
    if _de_lineas(layer):
        if not QgsWkbTypes.isMultiType(layer.wkbType()):
            anillos = anillos[:1]
        return conform(io.to_layer(rebuild('line', anillos)), layer)
    return conform(io.to_layer(rebuild('polygon', [anillos])), layer)


def en_original(cmd, islas):
    """Cambia la capa de la orden; un solo paso de deshacer. Devuelve
    (cambiados, creados, borrados)."""
    lyr = cmd.layer
    cambiar, crear, borrar = C.plan_original(islas)
    if not lyr.isEditable():
        lyr.startEditing()
    lyr.beginEditCommand('UNIR')
    try:
        for fid, isla in cambiar:
            lyr.changeGeometry(fid, geometria(cmd.io, isla, lyr))
        for fid, isla in crear:
            lyr.addFeature(copy_feature(lyr, cmd.feats[fid], geometria(cmd.io, isla, lyr)))
        if borrar:
            lyr.deleteFeatures(borrar)
    except Exception:
        lyr.destroyEditCommand()
        raise
    lyr.endEditCommand()
    lyr.triggerRepaint()
    return len(cambiar), len(crear), len(borrar)


def _campos(lyr):
    """Los campos de la capa sin su clave (el GeoPackage pone la suya)."""
    pk = set(lyr.primaryKeyAttributes())
    campos = QgsFields()
    for i, f in enumerate(lyr.fields()):
        if i in pk or f.name().lower() == 'fid':
            continue
        campos.append(f)
    return campos


def pintar_rojo(capa):
    """3.96.1 (Fernando): la capa combinada con el borde del polígono en rojo,
    para diferenciarla de la original; el rojo nunca va al relleno (sin relleno).
    En una capa de líneas (3.97.3), la línea en rojo."""
    try:
        from qgis.core import QgsFillSymbol, QgsLineSymbol, QgsSingleSymbolRenderer
        if _de_lineas(capa):
            sim = QgsLineSymbol.createSimple({'line_color': '255,0,0,255', 'line_width': '0.5'})
        else:
            sim = QgsFillSymbol.createSimple({'style': 'no', 'color': '0,0,0,0',
                                              'outline_color': '255,0,0,255', 'outline_width': '0.5'})
        capa.setRenderer(QgsSingleSymbolRenderer(sim))
    except Exception:
        pass


PROP_ORIGEN = 'geocad_combinados_de'      # en la capa combinada: el id de la capa original


def _rasgos(cmd, islas, capa, campos):
    nuevos = []
    for isla in islas:
        origen = cmd.feats[isla['jefe']]
        f = QgsFeature(capa.fields())
        f.setGeometry(geometria(cmd.io, isla, capa))
        for c in campos:
            if capa.fields().indexOf(c.name()) >= 0:
                f.setAttribute(c.name(), origen.attribute(c.name()))
        nuevos.append(f)
    return nuevos


def capa_combinada(lyr, carpeta=None):
    """La capa «combinados de <capa>» de esta capa, si ya existe (3.96.1): la
    del proyecto que la recuerda o, si no está cargada, el GeoPackage con ese
    nombre en la carpeta. None si todavía no hay."""
    prj = QgsProject.instance()
    for c in prj.mapLayers().values():
        if (isinstance(c, QgsVectorLayer) and c.isValid()
                and c.customProperty(PROP_ORIGEN) == lyr.id()):
            return c
    nombre = C.nombre_combinados(lyr.name())
    if carpeta is None:
        carpeta = C.carpeta_para(prj.fileName(), lyr.source() if lyr.providerType() == 'ogr' else '')
    ruta = os.path.join(carpeta, nombre + '.gpkg')
    if os.path.exists(ruta):
        c = QgsVectorLayer('%s|layername=%s' % (ruta, nombre), nombre, 'ogr')
        if c.isValid() and QgsWkbTypes.geometryType(c.wkbType()) == QgsWkbTypes.geometryType(lyr.wkbType()):
            pintar_rojo(c)
            c.setCustomProperty(PROP_ORIGEN, lyr.id())
            prj.addMapLayer(c)
            return c
    return None


def en_capa_nueva(cmd, islas):
    """Pone las islas en «combinados de <capa>»: si ya existe (de una UNIR
    anterior sobre la misma capa) se agregan ahí; si no, se crea el
    GeoPackage y se agrega al proyecto. Devuelve (capa, ruta, nueva)."""
    lyr = cmd.layer
    nombre = C.nombre_combinados(lyr.name())
    prj = QgsProject.instance()
    carpeta = C.carpeta_para(prj.fileName(), lyr.source() if lyr.providerType() == 'ogr' else '')
    campos = _campos(lyr)
    hecha = capa_combinada(lyr, carpeta)
    if hecha is not None:
        nuevos = _rasgos(cmd, islas, hecha, campos)
        if hecha.isEditable():
            hecha.beginEditCommand('UNIR')
            hecha.addFeatures(nuevos)
            hecha.endEditCommand()
        elif not hecha.dataProvider().addFeatures(nuevos)[0]:
            raise IOError('no se pudo agregar a %s' % hecha.source())
        hecha.updateExtents()
        hecha.triggerRepaint()
        return hecha, hecha.source().split('|')[0], False
    os.makedirs(carpeta, exist_ok=True)
    ruta = C.archivo_libre(carpeta, nombre)
    uri = '%s?crs=%s' % (QgsWkbTypes.displayString(lyr.wkbType()), lyr.crs().authid() or 'EPSG:4326')
    mem = QgsVectorLayer(uri, nombre, 'memory')
    if not lyr.crs().authid():
        mem.setCrs(lyr.crs())
    dp = mem.dataProvider()
    dp.addAttributes(campos.toList())
    mem.updateFields()
    dp.addFeatures(_rasgos(cmd, islas, mem, campos))
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = 'GPKG'
    opts.layerName = nombre
    opts.fileEncoding = 'UTF-8'
    try:
        res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, ruta, prj.transformContext(), opts)
    except AttributeError:
        res = QgsVectorFileWriter.writeAsVectorFormatV2(mem, ruta, prj.transformContext(), opts)
    if res[0] != QgsVectorFileWriter.NoError:
        raise IOError('no se pudo escribir %s: %s' % (ruta, res[1] if len(res) > 1 else res[0]))
    nueva = QgsVectorLayer('%s|layername=%s' % (ruta, nombre), nombre, 'ogr')
    if not nueva.isValid():
        raise IOError('no se pudo abrir %s' % ruta)
    pintar_rojo(nueva)
    nueva.setCustomProperty(PROP_ORIGEN, lyr.id())
    prj.addMapLayer(nueva)
    return nueva, ruta, True
