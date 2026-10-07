# -*- coding: utf-8 -*-
"""
Bloques CAD al estilo AutoCAD.

  * Definiciones: tabla 'Bloques CAD def' (sin geometría) con una fila por entidad:
      NOMBRE, WKT (geometría original en coordenadas locales, punto base = 0,0),
      LINEAS (representación lineal para dibujar), KIND, LAYER_CODE, SRC_LAYER, SRC_NAME.
  * Inserciones: capa de puntos 'Bloques CAD' con NOMBRE, ESCALA_X, ESCALA_Y, ROTACION.
    Se dibujan con un generador de geometría (affine_transform) a partir de la
    definición: al redefinir un bloque se actualizan todas sus inserciones.
"""

import math
import os

from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsGeometry,
                       QgsPointXY, QgsProject, QgsVectorFileWriter, QgsVectorLayer,
                       QgsVectorLayerUtils)

from .auxlayers import find_or_create
from .compat import geometry_kind

try:
    from qgis.PyQt.QtGui import QTransform
except ImportError:  # pragma: no cover
    QTransform = None

BLOCK_FLAG = 'dibujo_cad/block_layer'
DEFS_FLAG = 'dibujo_cad/block_defs'
EXPR_KEY = 'dibujo_cad/block_expr'
INST_FIELDS = [('NOMBRE', 'string', 80), ('ESCALA_X', 'double', 0), ('ESCALA_Y', 'double', 0),
               ('ROTACION', 'double', 0)]
DEF_FIELDS = [('NOMBRE', 'string', 80), ('WKT', 'string', 0), ('LINEAS', 'string', 0),
              ('KIND', 'string', 10), ('LAYER_CODE', 'string', 50), ('SRC_LAYER', 'string', 254),
              ('SRC_NAME', 'string', 254)]
INVALID_NAME = '<>/\\":;?*|=`'


# ---------------------------------------------------------------- capas
def is_block_layer(layer):
    try:
        return layer is not None and layer.customProperty(BLOCK_FLAG) == '1'
    except (AttributeError, RuntimeError):
        return False


def find_flagged(flag):
    for lyr in QgsProject.instance().mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.customProperty(flag) == '1':
            return lyr
    return None


def defs_layer(iface=None, echo=None, create=False):
    lyr = find_flagged(DEFS_FLAG)
    if lyr is None and create:
        lyr = find_or_create(iface, 'Bloques CAD def', 'bloques_def', DEFS_FLAG, DEF_FIELDS,
                             echo or (lambda *_: None), geom='None')
    return lyr


def block_expression(defs):
    """Expresión del generador de geometría que dibuja cada inserción."""
    return ("affine_transform(collect_geometries(array_foreach("
            "aggregate(layer:='%s', aggregate:='array_agg', expression:=\"LINEAS\", "
            "filter:=\"NOMBRE\" = attribute(@parent, 'NOMBRE') AND \"LINEAS\" <> ''), "
            "geom_from_wkt(@element))), "
            "x($geometry), y($geometry), coalesce(\"ROTACION\", 0), "
            "coalesce(\"ESCALA_X\", 1), coalesce(\"ESCALA_Y\", 1))") % defs.id()


def generator_symbol(expr, color='0,0,0', width='0.25'):
    from qgis.core import (QgsGeometryGeneratorSymbolLayer, QgsLineSymbol, QgsMarkerSymbol)
    gen = QgsGeometryGeneratorSymbolLayer.create({'geometryModifier': expr})
    try:
        from qgis.core import Qgis
        gen.setSymbolType(Qgis.SymbolType.Line)
    except AttributeError:
        from qgis.core import QgsSymbol
        gen.setSymbolType(QgsSymbol.Line)
    gen.setSubSymbol(QgsLineSymbol.createSimple({'color': color, 'width': width, 'width_unit': 'MM',
                                                 'capstyle': 'round', 'joinstyle': 'round'}))
    sym = QgsMarkerSymbol()
    sym.changeSymbolLayer(0, gen)
    return sym


def setup_instance_symbol(layer, defs):
    from qgis.core import QgsSingleSymbolRenderer
    expr = block_expression(defs)
    layer.setCustomProperty(EXPR_KEY, expr)
    if layer.customProperty('cad_layer_manager/config'):
        layer.triggerRepaint()           # la simbología la gestiona Layer Properties
        return
    layer.setRenderer(QgsSingleSymbolRenderer(generator_symbol(expr)))
    layer.triggerRepaint()


def instance_layer(iface, echo, create=True):
    lyr = find_flagged(BLOCK_FLAG)
    if lyr is not None or not create:
        return lyr
    defs = defs_layer(iface, echo, create=True)
    return find_or_create(iface, 'Bloques CAD', 'bloques_cad', BLOCK_FLAG, INST_FIELDS, echo,
                          setup=lambda l: setup_instance_symbol(l, defs))


def refresh_instances():
    LIB.invalidate()
    for lyr in QgsProject.instance().mapLayers().values():
        if is_block_layer(lyr):
            lyr.triggerRepaint()
    if SYNC is not None:
        SYNC.schedule()          # actualiza la geometría de referencia para el snapping


# ---------------------------------------------------------------- definiciones (caché)
class _Lib:
    def __init__(self):
        self.cache = {}

    def invalidate(self):
        self.cache = {}

    def names(self, defs=None):
        defs = defs or defs_layer()
        if defs is None:
            return []
        idx = defs.fields().indexOf('NOMBRE')
        try:
            return sorted({str(v) for v in defs.uniqueValues(idx) if v not in (None, '')})
        except Exception:  # noqa: BLE001
            return []

    def rows(self, name, defs=None):
        if name in self.cache:
            return self.cache[name]
        defs = defs or defs_layer()
        out = []
        if defs is not None:
            req = QgsFeatureRequest().setFilterExpression('"NOMBRE" = %s' % _quote(name))
            for f in defs.getFeatures(req):
                out.append(_row(f))
        self.cache[name] = out
        return out


LIB = _Lib()


def _quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def _row(f):
    def g(name):
        v = f[name]
        return '' if v is None else str(v)
    wkt, lines = g('WKT'), g('LINEAS')
    return {'name': g('NOMBRE'), 'kind': g('KIND'), 'layer_code': g('LAYER_CODE'),
            'src_layer': g('SRC_LAYER'), 'src_name': g('SRC_NAME'), 'wkt': wkt, 'lines': lines,
            'geom': QgsGeometry.fromWkt(wkt) if wkt else None,
            'lgeom': QgsGeometry.fromWkt(lines) if lines else None}


def line_representation(g):
    """Representación lineal de una geometría (para dibujar el bloque)."""
    from .compat import line_geometry_type, polygon_geometry_type
    t = g.type()
    if t == line_geometry_type():
        return QgsGeometry(g)
    if t == polygon_geometry_type():
        return QgsGeometry(g.constGet().boundary())
    return None


def kind_of(g):
    from .compat import line_geometry_type, polygon_geometry_type
    t = g.type()
    return 'line' if t == line_geometry_type() else 'polygon' if t == polygon_geometry_type() else 'point'


# ---------------------------------------------------------------- transformación
def place(g, x, y, sx=1.0, sy=1.0, rot=0.0):
    """Geometría local -> mundo: escala, giro (radianes, antihorario) y traslación."""
    c, s = math.cos(rot), math.sin(rot)
    g = QgsGeometry(g)
    g.transform(QTransform(sx * c, sx * s, -sy * s, sy * c, x, y))
    return g


def _num(v, d):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def instance_params(f):
    g = f.geometry()
    p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
    return (str(f['NOMBRE'] or ''), p.x(), p.y(), _num(f['ESCALA_X'], 1.0), _num(f['ESCALA_Y'], 1.0),
            math.radians(_num(f['ROTACION'], 0.0)))


def instance_geometry(f, lines_only=True):
    """Geometría (SRC de la capa de inserciones) de una inserción."""
    name, x, y, sx, sy, rot = instance_params(f)
    parts = []
    for r in LIB.rows(name):
        g = r['lgeom'] if lines_only else r['geom']
        if g is not None and not g.isEmpty():
            parts.append(place(g, x, y, sx, sy, rot))
    if not parts:
        return QgsGeometry.fromPointXY(QgsPointXY(x, y))
    return QgsGeometry.collectGeometry(parts)


def geometry_for_pick(layer, f):
    return instance_geometry(f) if is_block_layer(layer) else f.geometry()


# ---------------------------------------------------------------- escritura
def write_definition(defs, name, entities):
    """entities: lista de dict(geom local, layer_code, src_layer, src_name)."""
    prov = defs.dataProvider()
    old = [f.id() for f in defs.getFeatures(QgsFeatureRequest().setFilterExpression(
        '"NOMBRE" = %s' % _quote(name)))]
    if old:
        prov.deleteFeatures(old)
    feats = []
    for e in entities:
        g = e['geom']
        lg = line_representation(g)
        f = QgsFeature(defs.fields())
        vals = {'NOMBRE': name, 'WKT': g.asWkt(10), 'LINEAS': lg.asWkt(10) if lg is not None else '',
                'KIND': kind_of(g), 'LAYER_CODE': e.get('layer_code', '') or '',
                'SRC_LAYER': e.get('src_layer', '') or '', 'SRC_NAME': e.get('src_name', '') or ''}
        for k, v in vals.items():
            idx = defs.fields().indexOf(k)
            if idx != -1:
                f.setAttribute(idx, v)
        feats.append(f)
    prov.addFeatures(feats)
    defs.reload() if hasattr(defs, 'reload') else None
    refresh_instances()
    return len(feats)


def add_instance(mgr, name, pt_canvas, sx, sy, rot_deg, echo):
    inst = instance_layer(mgr.iface, echo)
    if not inst.isEditable():
        inst.startEditing()
    ccrs = mgr.canvas.mapSettings().destinationCrs()
    p = pt_canvas
    if ccrs != inst.crs():
        p = QgsCoordinateTransform(ccrs, inst.crs(), QgsProject.instance()).transform(pt_canvas)
    f = QgsVectorLayerUtils.createFeature(inst, QgsGeometry.fromPointXY(QgsPointXY(p)), {},
                                          inst.createExpressionContext())
    for k, v in (('NOMBRE', name), ('ESCALA_X', float(sx)), ('ESCALA_Y', float(sy)),
                 ('ROTACION', round(float(rot_deg) % 360.0, 8))):
        idx = inst.fields().indexOf(k)
        if idx != -1:
            f.setAttribute(idx, v)
    inst.beginEditCommand('INSERT')
    ok = inst.addFeature(f)
    inst.endEditCommand()
    inst.triggerRepaint()
    return ok


def _target_layer(row, fallback):
    prj = QgsProject.instance()
    lyr = prj.mapLayer(row['src_layer']) if row['src_layer'] else None
    if lyr is None and row['src_name']:
        found = prj.mapLayersByName(row['src_name'])
        lyr = found[0] if found else None
    if lyr is None:
        lyr = fallback
    return lyr if isinstance(lyr, QgsVectorLayer) else None


def explode_rows(rows, x, y, sx, sy, rot, src_crs, fallback=None):
    """Crea las entidades del bloque en sus capas de origen. Devuelve (creadas, omitidas)."""
    from .editkit import conform
    prj = QgsProject.instance()
    made, skipped = 0, 0
    touched = set()
    for r in rows:
        g = r['geom']
        if g is None or g.isEmpty():
            continue
        lyr = _target_layer(r, fallback)
        if lyr is None or geometry_kind(lyr) != r['kind']:
            skipped += 1
            continue
        wg = place(g, x, y, sx, sy, rot)
        if src_crs != lyr.crs():
            wg.transform(QgsCoordinateTransform(src_crs, lyr.crs(), prj))
        wg = conform(wg, lyr)
        if not lyr.isEditable():
            lyr.startEditing()
        f = QgsVectorLayerUtils.createFeature(lyr, wg, {}, lyr.createExpressionContext())
        idx = lyr.fields().indexOf('LAYER_CODE')
        if idx != -1 and r['layer_code']:
            f.setAttribute(idx, r['layer_code'])
        if lyr.id() not in touched:
            lyr.beginEditCommand('DESCOMP bloque')
            touched.add(lyr.id())
        if lyr.addFeature(f):
            made += 1
    for lid in touched:
        l = prj.mapLayer(lid)
        l.endEditCommand()
        l.triggerRepaint()
    return made, skipped


# ---------------------------------------------------------------- biblioteca (WBLOQUE)
LIB_TABLE = 'bloques_def'


def read_library(path):
    """{nombre: [filas]} de un archivo de biblioteca .gpkg."""
    lyr = QgsVectorLayer('%s|layername=%s' % (path, LIB_TABLE), 'lib', 'ogr')
    out = {}
    if not lyr.isValid():
        return out
    for f in lyr.getFeatures():
        r = _row(f)
        out.setdefault(r['name'], []).append(r)
    return out


def write_library(path, name, rows):
    """Agrega (o reemplaza) el bloque 'name' en la biblioteca."""
    if os.path.exists(path):
        lyr = QgsVectorLayer('%s|layername=%s' % (path, LIB_TABLE), 'lib', 'ogr')
        if lyr.isValid():
            entities = [{'geom': r['geom'], 'layer_code': r['layer_code'], 'src_layer': '',
                         'src_name': r['src_name']} for r in rows if r['geom'] is not None]
            write_definition(lyr, name, entities)
            return True
    uri = 'None?' + '&'.join('field=%s:%s%s' % (n, t, '(%d)' % l if l else '') for n, t, l in DEF_FIELDS)
    mem = QgsVectorLayer(uri, 'lib', 'memory')
    write_definition(mem, name, [{'geom': r['geom'], 'layer_code': r['layer_code'], 'src_layer': '',
                                  'src_name': r['src_name']} for r in rows if r['geom'] is not None])
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = 'GPKG'
    opts.layerName = LIB_TABLE
    prj = QgsProject.instance()
    try:
        QgsVectorFileWriter.writeAsVectorFormatV3(mem, path, prj.transformContext(), opts)
    except AttributeError:
        QgsVectorFileWriter.writeAsVectorFormatV2(mem, path, prj.transformContext(), opts)
    return os.path.exists(path)


# ---------------------------------------------------------------- referencia a objetos
def snap_candidates(canvas, pt, tol, limit=3000):
    """Extremos, vértices y puntos medios de las inserciones cercanos a pt (SRC del mapa)."""
    out = []
    ccrs = canvas.mapSettings().destinationCrs()
    for lyr in canvas.layers():
        if not is_block_layer(lyr):
            continue
        tr = None if lyr.crs() == ccrs else QgsCoordinateTransform(lyr.crs(), ccrs, QgsProject.instance())
        req = QgsFeatureRequest()
        req.setLimit(limit)
        for f in lyr.getFeatures(req):
            if not f.hasGeometry():
                continue
            g = instance_geometry(f)
            if tr is not None:
                g.transform(tr)
            bb = g.boundingBox()
            if pt.x() < bb.xMinimum() - tol or pt.x() > bb.xMaximum() + tol or \
                    pt.y() < bb.yMinimum() - tol or pt.y() > bb.yMaximum() + tol:
                continue
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for part in parts:
                for i, v in enumerate(part):
                    if abs(v.x() - pt.x()) <= tol and abs(v.y() - pt.y()) <= tol:
                        out.append(QgsPointXY(v.x(), v.y()))
                    if i:
                        a = part[i - 1]
                        mx, my = (a.x() + v.x()) / 2.0, (a.y() + v.y()) / 2.0
                        if abs(mx - pt.x()) <= tol and abs(my - pt.y()) <= tol:
                            out.append(QgsPointXY(mx, my))
    return out


# ---------------------------------------------------------------- snapping (capa de referencia)
GEOM_FLAG = 'dibujo_cad/block_geom'
GEOM_FIELDS = [('INST_FID', 'integer', 0), ('NOMBRE', 'string', 80)]


def _setup_geom_layer(layer):
    """Capa auxiliar: solo sirve para que el snapping de QGIS 'vea' los bloques.
    Se dibuja con un trazo totalmente transparente (con renderizador nulo QGIS la
    consideraría invisible y no se engancharía en ella)."""
    try:
        from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer
        sym = QgsLineSymbol.createSimple({'color': '0,0,0,0', 'width': '0.1'})
        layer.setRenderer(QgsSingleSymbolRenderer(sym))
    except ImportError:
        pass
    layer.setReadOnly(True)
    ensure_all_layers_snapping()


def ensure_all_layers_snapping():
    """Como en AutoCAD, la referencia a objetos debe considerar todos los objetos."""
    try:
        from qgis.core import QgsSnappingConfig
        prj = QgsProject.instance()
        cfg = prj.snappingConfig()
        try:
            from qgis.core import Qgis
            active, all_layers = Qgis.SnappingMode.ActiveLayer, Qgis.SnappingMode.AllLayers
        except AttributeError:
            active, all_layers = QgsSnappingConfig.ActiveLayer, QgsSnappingConfig.AllLayers
        if cfg.mode() == active:
            cfg.setMode(all_layers)
            prj.setSnappingConfig(cfg)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


class BlockSync:
    """
    Mantiene la capa 'Bloques CAD (referencia)' con el trazado real de cada inserción,
    para que todos los modos de referencia a objetos de QGIS funcionen sobre los bloques
    (extremo, punto medio, intersección, cercano...), también con herramientas nativas.
    """

    def __init__(self, iface):
        from qgis.PyQt.QtCore import QTimer
        self.iface = iface
        self.watched = set()
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.rebuild)
        prj = QgsProject.instance()
        prj.layersAdded.connect(self._layers_added)
        try:
            iface.projectRead.connect(self.schedule)
        except Exception:  # noqa: BLE001
            pass
        self._layers_added(list(prj.mapLayers().values()))

    def unload(self):
        try:
            QgsProject.instance().layersAdded.disconnect(self._layers_added)
        except (TypeError, RuntimeError):
            pass
        try:
            self.iface.projectRead.disconnect(self.schedule)
        except (TypeError, RuntimeError):
            pass
        self.timer.stop()

    def _layers_added(self, layers):
        for lyr in layers:
            if is_block_layer(lyr) and lyr.id() not in self.watched:
                self.watched.add(lyr.id())
                for sig in (lyr.featureAdded, lyr.featureDeleted, lyr.geometryChanged,
                            lyr.attributeValueChanged, lyr.afterRollBack, lyr.afterCommitChanges):
                    sig.connect(self.schedule)
                self.schedule()

    def schedule(self, *args):
        self.timer.start()

    def geom_layer(self, create=True):
        lyr = find_flagged(GEOM_FLAG)
        if lyr is not None and lyr.customProperty('dibujo_cad/geom_v') != '2':
            _setup_geom_layer(lyr)
            lyr.setCustomProperty('dibujo_cad/geom_v', '2')
        if lyr is None and create:
            lyr = find_or_create(self.iface, 'Bloques CAD (referencia)', 'bloques_ref', GEOM_FLAG,
                                 GEOM_FIELDS, lambda *_: None, geom='MultiLineString',
                                 setup=_setup_geom_layer)
            try:
                from qgis.core import Qgis
                self.iface.messageBar().pushMessage(
                    'Bloques CAD',
                    'Se creó la capa invisible "Bloques CAD (referencia)" para que la referencia a objetos '
                    'funcione sobre los bloques. Manténgala activada en el panel Capas y use el snapping '
                    'en "Todas las capas" (o inclúyala en la configuración avanzada).',
                    Qgis.MessageLevel.Info if hasattr(Qgis, 'MessageLevel') else Qgis.Info, 10)
            except Exception:  # noqa: BLE001
                pass
        return lyr

    def rebuild(self):
        prj = QgsProject.instance()
        block_layers = [l for l in prj.mapLayers().values() if is_block_layer(l)]
        if not block_layers:
            return
        LIB.invalidate()
        gl = self.geom_layer(create=True)
        if gl is None:
            return
        if gl.isEditable():                 # nunca se edita a mano: se descarta y se protege
            gl.rollBack()
            gl.setReadOnly(True)
        prov = gl.dataProvider()
        old = [f.id() for f in gl.getFeatures()]
        if old:
            prov.deleteFeatures(old)
        feats = []
        for bl in block_layers:
            tr = None if bl.crs() == gl.crs() else QgsCoordinateTransform(bl.crs(), gl.crs(), prj)
            for f in bl.getFeatures():
                if not f.hasGeometry():
                    continue
                g = instance_geometry(f)
                if g is None or g.isEmpty() or g.type() != _line_type():
                    continue
                if tr is not None:
                    g.transform(tr)
                if not g.isMultipart():
                    g.convertToMultiType()
                nf = QgsFeature(gl.fields())
                nf.setGeometry(g)
                # por nombre: en GeoPackage el primer campo es 'fid'
                i_fid, i_nom = gl.fields().indexOf('INST_FID'), gl.fields().indexOf('NOMBRE')
                if i_fid != -1:
                    fid = int(f.id())
                    nf.setAttribute(i_fid, fid if -2147483648 <= fid <= 2147483647 else None)
                if i_nom != -1:
                    nf.setAttribute(i_nom, str(f['NOMBRE'] or ''))
                feats.append(nf)
        if feats:
            prov.addFeatures(feats)
        gl.updateExtents()
        try:
            gl.dataChanged.emit()           # el índice de snapping de QGIS se reconstruye
        except Exception:  # noqa: BLE001
            pass
        gl.triggerRepaint()


def _line_type():
    from .compat import line_geometry_type
    return line_geometry_type()


SYNC = None


def start_sync(iface):
    global SYNC
    if SYNC is None:
        SYNC = BlockSync(iface)
    return SYNC


def stop_sync():
    global SYNC
    if SYNC is not None:
        SYNC.unload()
        SYNC = None
