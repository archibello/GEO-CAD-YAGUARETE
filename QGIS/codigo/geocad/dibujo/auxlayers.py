# -*- coding: utf-8 -*-
"""Capas auxiliares (textos, puntos) que crean los comandos cuando hacen falta."""

import os

from qgis.core import QgsProject, QgsVectorFileWriter, QgsVectorLayer


def find_or_create(iface, name, filename, flag, fields, echo, geom='Point', setup=None):
    """
    Busca una capa marcada con 'flag' en el proyecto; si no existe la crea como
    GeoPackage en la carpeta del proyecto (o temporal si el proyecto no está guardado).
    fields: lista de (nombre, tipo memory, longitud).
    """
    prj = QgsProject.instance()
    for lyr in prj.mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.customProperty(flag) == '1':
            return lyr
    crs = iface.mapCanvas().mapSettings().destinationCrs()
    uri = '%s?crs=%s' % (geom, crs.authid() or 'EPSG:4326')
    if fields:
        uri += '&' + '&'.join('field=%s:%s%s' % (n, t, '(%d)' % l if l else '') for n, t, l in fields)
    mem = QgsVectorLayer(uri, name, 'memory')
    layer = mem
    home = prj.homePath()
    if home and os.path.isdir(home):
        path = os.path.join(home, filename + '.gpkg')
        ok = os.path.exists(path)
        if not ok:
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = 'GPKG'
            opts.layerName = filename
            try:
                res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, path, prj.transformContext(), opts)
            except AttributeError:
                res = QgsVectorFileWriter.writeAsVectorFormatV2(mem, path, prj.transformContext(), opts)
            ok = os.path.exists(path)
        if ok:
            gl = QgsVectorLayer('%s|layername=%s' % (path, filename), name, 'ogr')
            if gl.isValid():
                layer = gl
                echo('Capa "%s" creada en %s' % (name, path))
    if layer is mem:
        echo('Capa temporal "%s" creada: guarde el proyecto y conviértala en permanente '
             '(clic derecho > Hacer permanente) para no perder los datos.' % name)
    prj.addMapLayer(layer)
    layer.setCustomProperty(flag, '1')
    if setup is not None:
        setup(layer)
    return layer


def setup_point_symbol(layer):
    """Puntos como en AutoCAD con PDMODE 3 (una X)."""
    try:
        from qgis.core import QgsMarkerSymbol
        sym = QgsMarkerSymbol.createSimple({'name': 'cross2', 'size': '2.5', 'size_unit': 'MM',
                                            'color': '255,255,255', 'outline_color': '230,0,0',
                                            'outline_width': '0.3'})
        from qgis.core import QgsSingleSymbolRenderer
        layer.setRenderer(QgsSingleSymbolRenderer(sym))
        layer.triggerRepaint()
    except Exception:  # noqa: BLE001
        pass


def point_layer(iface, echo):
    lyr = find_or_create(iface, 'Puntos CAD', 'puntos_cad', 'dibujo_cad/point_layer', [], echo,
                         setup=setup_point_symbol)
    if not lyr.isEditable():
        lyr.startEditing()
    return lyr


# ---------------------------------------------------------------- capas temporales -> permanentes
AUX_FLAGS = {
    'dibujo_cad/text_layer': 'textos_cad',
    'dibujo_cad/point_layer': 'puntos_cad',
    'dibujo_cad/block_layer': 'bloques_cad',
    'dibujo_cad/block_defs': 'bloques_def',
    'dibujo_cad/block_geom': 'bloques_ref',
}


def _free_path(home, base):
    path = os.path.join(home, base + '.gpkg')
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(home, '%s_%d.gpkg' % (base, n))
    return path


def persist_memory_layers(echo=None):
    """Convierte en GeoPackage (carpeta del proyecto) las capas auxiliares de Dibujo CAD
    que todavía son temporales. Las capas temporales NO guardan sus objetos en el proyecto:
    al cerrarlo se perderían los textos, puntos o bloques. Devuelve la cantidad convertida."""
    prj = QgsProject.instance()
    home = prj.homePath()
    if not home or not os.path.isdir(home):
        return 0
    done = 0
    for lyr in list(prj.mapLayers().values()):
        try:
            if not isinstance(lyr, QgsVectorLayer) or lyr.providerType() != 'memory':
                continue
            base = next((b for f, b in AUX_FLAGS.items() if lyr.customProperty(f) == '1'), None)
            if base is None:
                continue
            if lyr.isEditable() and not lyr.commitChanges():
                continue
            path = _free_path(home, base)
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = 'GPKG'
            opts.layerName = base
            try:
                QgsVectorFileWriter.writeAsVectorFormatV3(lyr, path, prj.transformContext(), opts)
            except AttributeError:
                QgsVectorFileWriter.writeAsVectorFormatV2(lyr, path, prj.transformContext(), opts)
            if not os.path.exists(path):
                continue
            lyr.setDataSource('%s|layername=%s' % (path, base), lyr.name(), 'ogr')
            done += 1
            if echo:
                echo('Capa "%s" guardada en %s (antes era temporal).' % (lyr.name(), path))
        except Exception as e:  # noqa: BLE001
            if echo:
                echo('No se pudo convertir en permanente "%s": %s' % (lyr.name(), e))
    return done
