# -*- coding: utf-8 -*-
"""
Infraestructura común de los comandos de edición:
SRC (capa <-> mapa), designación de objetos al estilo AutoCAD, conversión
de geometrías y operaciones afines.
"""

import math

from qgis.core import (QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
                       QgsPointXY, QgsProject, QgsRectangle, QgsTolerance,
                       QgsVectorLayerUtils, QgsWkbTypes)

from .commands import _DrawCommand, _key
from .compat import enum, line_geometry_type, polygon_geometry_type

try:
    from qgis.PyQt.QtGui import QTransform
except ImportError:  # pragma: no cover
    QTransform = None


# ---------------------------------------------------------------- SRC
class GeomIO:
    """Convierte geometrías entre el SRC de la capa y el del mapa."""

    def __init__(self, canvas, layer):
        self.ccrs = canvas.mapSettings().destinationCrs()
        self.lcrs = layer.crs()
        self.same = self.ccrs == self.lcrs
        if not self.same:
            prj = QgsProject.instance()
            self.to_c = QgsCoordinateTransform(self.lcrs, self.ccrs, prj)
            self.to_l = QgsCoordinateTransform(self.ccrs, self.lcrs, prj)

    def to_canvas(self, g):
        g = QgsGeometry(g)
        if not self.same:
            g.transform(self.to_c)
        return g

    def to_layer(self, g):
        g = QgsGeometry(g)
        if not self.same:
            g.transform(self.to_l)
        return g

    def point_to_layer(self, p):
        return QgsPointXY(p) if self.same else self.to_l.transform(p)

    def rect_to_layer(self, r):
        return QgsRectangle(r) if self.same else self.to_l.transformBoundingBox(r)


def transform_for(layer, canvas):
    return GeomIO(canvas, layer)


# ---------------------------------------------------------------- consultas
def _no_geom_flag():
    try:
        from qgis.core import Qgis
        return Qgis.FeatureRequestFlag.NoFlags
    except AttributeError:
        return enum(QgsFeatureRequest, 'Flag', 'NoFlags')


def search_radius(canvas):
    return QgsTolerance.vertexSearchRadius(canvas.mapSettings())


def _is_block(layer):
    try:
        return layer.customProperty('dibujo_cad/block_layer') == '1'
    except (AttributeError, RuntimeError):
        return False


def _pick_geom(layer, f, blocks):
    """En capas de bloques se designa por el dibujo del bloque, no por el punto de inserción."""
    if blocks:
        from .blocks import instance_geometry
        return instance_geometry(f)
    return f.geometry()


def pick_feature(canvas, io, layer, p, exclude=()):
    """Objeto más cercano al punto p (SRC del mapa) dentro de la tolerancia: (fid, feature) o (None, None)."""
    tol = search_radius(canvas)
    r = QgsRectangle(p.x() - tol, p.y() - tol, p.x() + tol, p.y() + tol)
    rl = io.rect_to_layer(r)
    pg = QgsGeometry.fromPointXY(io.point_to_layer(p))
    tol_l = max(rl.width(), rl.height()) / 2.0
    best, best_d = (None, None), None
    blocks = _is_block(layer)
    req = QgsFeatureRequest() if blocks else QgsFeatureRequest().setFilterRect(rl)
    for f in layer.getFeatures(req):
        if f.id() in exclude or not f.hasGeometry():
            continue
        d = _pick_geom(layer, f, blocks).distance(pg)
        if d <= tol_l and (best_d is None or d < best_d):
            best, best_d = (f.id(), f), d
    return best


def query_rect(io, layer, a, b, crossing):
    """Ventana (contiene) o captura (interseca) entre las esquinas a y b."""
    r = QgsRectangle(a, b)
    r.normalize()
    rl = io.rect_to_layer(r)
    rg = QgsGeometry.fromRect(rl)
    out = []
    blocks = _is_block(layer)
    req = QgsFeatureRequest() if blocks else QgsFeatureRequest().setFilterRect(rl)
    for f in layer.getFeatures(req):
        if not f.hasGeometry():
            continue
        g = _pick_geom(layer, f, blocks)
        if (crossing and g.intersects(rg)) or (not crossing and rg.contains(g)):
            out.append(f.id())
    return out


def query_geom(io, layer, geom_canvas, predicate):
    """Objetos contenidos en / que cortan una geometría (SRC del mapa)."""
    gl = io.to_layer(geom_canvas)
    out = []
    blocks = _is_block(layer)
    req = QgsFeatureRequest() if blocks else QgsFeatureRequest().setFilterRect(gl.boundingBox())
    for f in layer.getFeatures(req):
        if not f.hasGeometry():
            continue
        g = _pick_geom(layer, f, blocks)
        if (predicate == 'contains' and gl.contains(g)) or (predicate == 'intersects' and g.intersects(gl)):
            out.append(f.id())
    return out


# ---------------------------------------------------------------- geometría
def explode(g):
    """Geometría (lineal o poligonal) -> (tipo, estructura, lista plana de polilíneas, mapa índice)."""
    gt = g.type()
    xy = lambda pts: [(p.x(), p.y()) for p in pts]  # noqa: E731
    if gt == line_geometry_type():
        parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
        flat = [xy(p) for p in parts]
        return 'line', flat, flat, [(i,) for i in range(len(flat))]
    if gt == polygon_geometry_type():
        polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
        struct = [[xy(r) for r in poly] for poly in polys]
        flat, index = [], []
        for pi, poly in enumerate(struct):
            for ri, ring in enumerate(poly):
                flat.append(ring)
                index.append((pi, ri))
        return 'polygon', struct, flat, index
    raise ValueError('Tipo de geometría no admitido.')


def rebuild(kind, struct):
    P = lambda pts: [QgsPointXY(x, y) for x, y in pts]  # noqa: E731
    if kind == 'line':
        if len(struct) == 1:
            return QgsGeometry.fromPolylineXY(P(struct[0]))
        return QgsGeometry.fromMultiPolylineXY([P(p) for p in struct])
    if len(struct) == 1:
        return QgsGeometry.fromPolygonXY([P(r) for r in struct[0]])
    return QgsGeometry.fromMultiPolygonXY([[P(r) for r in poly] for poly in struct])


def replace_part(kind, struct, index, k, coords):
    """Devuelve una copia de struct con la polilínea/anillo k reemplazado."""
    import copy
    s = copy.deepcopy(struct)
    if kind == 'line':
        s[index[k][0]] = coords
    else:
        pi, ri = index[k]
        s[pi][ri] = coords
    return s


def nearest_part(flat, p):
    from .geomops import GeomError, closest_segment
    best, best_d = None, None
    for k, pts in enumerate(flat):
        if len(pts) < 2:
            continue
        try:
            d = closest_segment(pts, (p.x(), p.y()))[2]
        except GeomError:
            continue
        if best_d is None or d < best_d:
            best, best_d = k, d
    return best


def conform(g, layer):
    """Adapta la geometría al tipo de la capa (multi, Z, M)."""
    wkb = layer.wkbType()
    if QgsWkbTypes.isMultiType(wkb) and not g.isMultipart():
        g.convertToMultiType()
    if QgsWkbTypes.hasZ(wkb) and not QgsWkbTypes.hasZ(g.wkbType()):
        g.get().addZValue(0.0)
    if QgsWkbTypes.hasM(wkb) and not QgsWkbTypes.hasM(g.wkbType()):
        g.get().addMValue(0.0)
    return g


def affine(g, k=1.0, theta=0.0, src=None, dst=None):
    """p' = dst + k·R(theta)·(p - src). theta en radianes (antihorario)."""
    src = src or QgsPointXY(0, 0)
    dst = dst or src
    c, s = math.cos(theta) * k, math.sin(theta) * k
    dx = dst.x() - (c * src.x() - s * src.y())
    dy = dst.y() - (s * src.x() + c * src.y())
    g = QgsGeometry(g)
    if abs(k - 1.0) < 1e-12 and abs(theta) < 1e-12:
        g.translate(dx, dy)
        return g
    g.transform(QTransform(c, s, -s, c, dx, dy))
    return g


def segments_from_geometry(g):
    from .geomops import segments_of
    try:
        kind, struct, flat, index = explode(g)
    except ValueError:
        return []
    out = []
    for pts in flat:
        out.extend(segments_of(pts))
    return out


def copy_feature(layer, feature, geom):
    """Nuevo objeto con los atributos del original (sin clave primaria)."""
    pk = set(layer.primaryKeyAttributes())
    attrs = {i: feature.attribute(i) for i in range(layer.fields().count()) if i not in pk}
    return QgsVectorLayerUtils.createFeature(layer, geom, attrs, layer.createExpressionContext())


def join_miter():
    try:
        from qgis.core import Qgis
        return Qgis.JoinStyle.Miter
    except AttributeError:
        return QgsGeometry.JoinStyleMiter


def cap_flat():
    try:
        from qgis.core import Qgis
        return Qgis.EndCapStyle.Flat
    except AttributeError:
        return QgsGeometry.CapFlat


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def text_rotation_fn(theta):
    """ROTACION (grados, antihorario) + theta (radianes)."""
    return {'ROTACION': lambda old: round((_num(old, 0.0) + math.degrees(theta)) % 360.0, 8)}


def mirror_matrix(p1, p2):
    """Simetría respecto de la recta p1-p2 como (c, s, dx, dy) para QTransform."""
    phi = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
    c, s = math.cos(2 * phi), math.sin(2 * phi)
    dx = p1.x() - (c * p1.x() + s * p1.y())
    dy = p1.y() - (s * p1.x() - c * p1.y())
    return c, s, dx, dy, phi


def mirror_geom(g, p1, p2):
    c, s, dx, dy, _ = mirror_matrix(p1, p2)
    g = QgsGeometry(g)
    g.transform(QTransform(c, s, s, -c, dx, dy))
    return g


_JUST_H = {'I': 'D', 'D': 'I', 'SI': 'SD', 'SD': 'SI', 'MI': 'MD', 'MD': 'MI', 'II': 'ID', 'ID': 'II'}
_JUST_V = {'I': 'SI', 'C': 'SC', 'D': 'SD', 'SI': 'I', 'SC': 'C', 'SD': 'D',
           'II': 'SI', 'IC': 'SC', 'ID': 'SD'}


def mirror_text_attrs(rot_deg, just, phi):
    """Texto legible tras la simetría (como MIRRTEXT = 0 en AutoCAD)."""
    d = math.radians(2 * math.degrees(phi) - rot_deg)          # dirección reflejada
    deg = math.degrees(d) % 360.0
    readable = deg <= 90.0 or deg > 270.0
    if readable:
        new_rot, new_just = deg, _JUST_V.get(just, just)      # se invierte arriba/abajo
    else:
        new_rot, new_just = (deg + 180.0) % 360.0, _JUST_H.get(just, just)   # se invierte izq./der.
    return round(new_rot, 8), new_just


def block_scale_fn(k):
    return {'ESCALA_X': lambda old: _num(old, 1.0) * k, 'ESCALA_Y': lambda old: _num(old, 1.0) * k}


def text_scale_fn(k):
    return {'ALTURA': lambda old: _num(old, 2.5) * k}


# ---------------------------------------------------------------- comando base
class EditCommand(_DrawCommand):
    """Base de los comandos de edición con designación de objetos."""
    select_prompt = 'Designe objetos'
    uses_selection = True
    accept_preselection = True
    max_preview = 300

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.canvas = mgr.canvas
        self.io = GeomIO(self.canvas, layer)
        self.sel = []
        self.selecting = self.uses_selection
        self.win = None
        self.base_pt = None
        self.geoms = {}
        self.feats = {}
        self.marks = []

    # ---------------------------------------------------- ciclo
    def start(self):
        pre = list(self.layer.selectedFeatureIds()) if self.uses_selection else []
        if pre and self.accept_preselection:
            self.sel = pre
            self.cl.echo('%d encontrado(s)' % len(pre))
            self._selection_done()
            return
        if self.uses_selection:
            self.layer.removeSelection()
        self.selecting = self.uses_selection
        self.begin()

    def begin(self):
        self.prompt()

    # ---------------------------------------------------- modos de designación
    # clave -> modo (castellano e inglés, como AutoCAD)
    SEL_MODES = {
        'V': 'window', 'VENTANA': 'window', 'W': 'window', 'WINDOW': 'window',
        'C': 'crossing', 'CAPTURA': 'crossing', 'CROSSING': 'crossing',
        'CU': 'box', 'CUADRO': 'box', 'BOX': 'box',
        'PV': 'wpoly', 'POLIGONOV': 'wpoly', 'WP': 'wpoly', 'WPOLYGON': 'wpoly',
        'PC': 'cpoly', 'POLIGONOC': 'cpoly', 'CP': 'cpoly', 'CPOLYGON': 'cpoly',
        'B': 'fence', 'BORDE': 'fence', 'F': 'fence', 'FENCE': 'fence',
    }
    SEL_HELP = ('Opciones: Ventana(V) Captura(C) CUadro(CU) PolígonoV(PV) PolígonoC(PC) '
                'Borde(B) Todo(T) Último(U) Previo(P) Añadir(A) Eliminar(E) desHacer(H)')

    def _sel_init(self):
        if not hasattr(self, 'sel_mode'):
            self.sel_mode = 'auto'      # auto | window | crossing | box | wpoly | cpoly | fence
            self.poly = []
            self.removing = False
            self.sel_undo = []

    def prompt(self):
        if self.selecting:
            self._sel_init()
            m = self.sel_mode
            if m in ('wpoly', 'cpoly', 'fence'):
                if not self.poly:
                    self.cl.set_prompt('Precise primer punto de %s' % ('borde' if m == 'fence' else 'polígono'))
                else:
                    self.cl.set_prompt('Precise punto final de línea o', [('H', 'desHacer')])
            elif self.win is not None:
                self.cl.set_prompt('Precise esquina opuesta')
            elif m in ('window', 'crossing', 'box'):
                self.cl.set_prompt('Precise primera esquina')
            else:
                self.cl.set_prompt('Eliminar objetos' if self.removing else self.select_prompt)
        else:
            self.step_prompt()

    def base(self):
        return None if self.selecting else self.base_pt

    def snap_points(self):
        return [self.base_pt] if self.base_pt is not None else []

    def ref_direction(self):
        return None

    def end(self):
        try:
            self.layer.removeSelection()
        except Exception:
            pass
        super().end()

    def escape(self):
        self.end()

    # ---------------------------------------------------- entrada
    def on_point(self, p):
        if self.selecting:
            self._sel_init()
            if self.sel_mode in ('wpoly', 'cpoly', 'fence'):
                self.poly.append(p)
                self.prompt()
                return
            self._select_point(p)
        else:
            self.step_point(p)

    def on_text(self, text):
        if not self.selecting:
            self.step_text(text)
            return
        self._sel_init()
        k = _key(text)
        if self.sel_mode in ('wpoly', 'cpoly', 'fence') and self.poly and k in ('H', 'U', 'DESHACER', 'UNDO'):
            self.poly.pop()
        elif k in self.SEL_MODES and not self.poly and self.win is None:
            self.sel_mode = self.SEL_MODES[k]
        elif k in ('TODO', 'T', 'ALL'):
            self._add([f.id() for f in self.layer.getFeatures()])
        elif k in ('U', 'ULTIMO', 'ÚLTIMO', 'L', 'LAST'):
            last = self.mgr.last_added.get(self.layer.id()) if hasattr(self.mgr, 'last_added') else None
            if last is None:
                self.cl.echo('No hay un último objeto creado en esta capa.')
            else:
                self._add([last])
        elif k in ('P', 'PREVIO', 'PREVIOUS'):
            self._add(self.mgr.prev_selection.get(self.layer.id(), []))
        elif k in ('E', 'ELIMINAR', 'R', 'REMOVE'):
            self.removing = True
        elif k in ('A', 'AÑADIR', 'ANADIR', 'ADD'):
            self.removing = False
        elif k in ('H', 'DESHACER', 'UNDO'):
            if self.sel_undo:
                self.sel = self.sel_undo.pop()
                self.layer.selectByIds(list(self.sel))
                self.cl.echo('%d en total' % len(self.sel))
            else:
                self.cl.echo('Todas las designaciones ya se han deshecho.')
        elif k == '?':
            self.cl.echo(self.SEL_HELP)
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def on_enter(self):
        if self.selecting:
            self._sel_init()
            if self.sel_mode in ('wpoly', 'cpoly', 'fence') and self.poly:
                self._finish_poly()
                return
            if self.win is not None:
                self.win = None
                self.prompt()
                return
            if not self.sel:
                self.end()
                return
            self._selection_done()
        else:
            self.step_enter()

    # ---------------------------------------------------- designación
    def _select_point(self, p):
        remove = self.mgr.shift or self.removing
        mode = self.sel_mode
        if self.win is None:
            if mode == 'auto':
                fid, _f = pick_feature(self.canvas, self.io, self.layer, p)
                if fid is not None:
                    self._add([fid], remove)
                    return
            self.win = p
            self.prompt()
            return
        if mode == 'window':
            crossing = False
        elif mode == 'crossing':
            crossing = True
        else:
            crossing = p.x() < self.win.x()
        fids = query_rect(self.io, self.layer, self.win, p, crossing)
        self.on_window(self.win, p, crossing)
        self.win = None
        if mode in ('window', 'crossing', 'box'):
            self.sel_mode = 'auto'
        self._add(fids, remove)

    def _finish_poly(self):
        mode, pts = self.sel_mode, list(self.poly)
        self.poly = []
        self.sel_mode = 'auto'
        if mode == 'fence':
            if len(pts) < 2:
                self.cl.echo('El borde necesita al menos dos puntos.')
                self.prompt()
                return
            geom = QgsGeometry.fromPolylineXY(pts)
            fids = query_geom(self.io, self.layer, geom, 'intersects')
        else:
            if len(pts) < 3:
                self.cl.echo('El polígono necesita al menos tres puntos.')
                self.prompt()
                return
            geom = QgsGeometry.fromPolygonXY([pts + [pts[0]]])
            fids = query_geom(self.io, self.layer, geom, 'contains' if mode == 'wpoly' else 'intersects')
            if mode == 'cpoly':
                bb = geom.boundingBox()
                self.on_window(QgsPointXY(bb.xMinimum(), bb.yMinimum()),
                               QgsPointXY(bb.xMaximum(), bb.yMaximum()), True, polygon=geom)
        self._add(fids, self.mgr.shift or self.removing)

    def on_window(self, a, b, crossing, polygon=None):
        pass

    def _add(self, fids, remove=False):
        self._sel_init()
        before = len(self.sel)
        self.sel_undo.append(list(self.sel))
        if remove:
            drop = set(fids)
            self.sel = [f for f in self.sel if f not in drop]
        else:
            have = set(self.sel)
            self.sel += [f for f in fids if f not in have]
        self.layer.selectByIds(list(self.sel))
        ok = set(self.layer.selectedFeatureIds())     # respeta capas bloqueadas/inutilizadas
        self.sel = [f for f in self.sel if f in ok]
        if remove:
            self.cl.echo('%d eliminado(s), %d en total' % (before - len(self.sel), len(self.sel)))
        else:
            self.cl.echo('%d encontrado(s), %d en total' % (len(self.sel) - before, len(self.sel)))
        self.prompt()

    def _selection_done(self):
        self.selecting = False
        self.mgr.prev_selection[self.layer.id()] = list(self.sel)
        self.load_geoms()
        self.after_selection()

    def load_geoms(self):
        self.geoms, self.feats = {}, {}
        if not self.sel:
            return
        req = QgsFeatureRequest().setFilterFids(list(self.sel))
        for f in self.layer.getFeatures(req):
            if f.hasGeometry():
                self.feats[f.id()] = f
                self.geoms[f.id()] = self.io.to_canvas(f.geometry())

    # ---------------------------------------------------- vista previa
    def preview(self, cur):
        if self.selecting:
            self._sel_init()
            mode = self.sel_mode
            if mode in ('wpoly', 'cpoly', 'fence') and self.poly:
                pts = list(self.poly) + ([cur] if cur is not None else [])
                if mode == 'fence':
                    return [], False, pts, []
                closed = pts + [pts[0]]
                return (closed, False, [], []) if mode == 'wpoly' else ([], False, closed, [])
            if self.win is not None and cur is not None:
                a = self.win
                rect = [a, type(a)(cur.x(), a.y()), cur, type(a)(a.x(), cur.y()), a]
                crossing = mode == 'crossing' or (mode in ('auto', 'box') and cur.x() < a.x())
                if crossing:
                    return [], False, rect, []          # captura: discontinua
                return rect, False, [], []              # ventana: continua
            return [], False, [], []
        return self.step_preview(cur)

    def step_preview(self, cur):
        if self.base_pt is not None and cur is not None:
            return [], False, [self.base_pt, cur], []
        return [], False, [], []

    def transformed(self, fn):
        out = []
        for i, g in enumerate(self.geoms.values()):
            if i >= self.max_preview:
                break
            out.append(fn(g))
        return out

    # ---------------------------------------------------- aplicar cambios
    def apply_geoms(self, fn, title, copy=False, attr_fn=None, attrs_for=None):
        """Aplica fn(geom_mapa) a la selección; con copy=True crea copias.
        attr_fn: {nombre_campo: función(valor_anterior) -> valor_nuevo} (p. ej. ROTACION de textos)."""
        if not self.geoms:
            return 0
        attr_idx = {}
        for name, f in (attr_fn or {}).items():
            idx = self.layer.fields().indexOf(name)
            if idx != -1:
                attr_idx[idx] = f
        self.layer.beginEditCommand(title)
        n = 0
        try:
            for fid, g in self.geoms.items():
                ng = conform(self.io.to_layer(fn(g)), self.layer)
                extra = {}
                if attrs_for is not None:
                    for name, v in attrs_for(self.feats[fid]).items():
                        idx = self.layer.fields().indexOf(name)
                        if idx != -1:
                            extra[idx] = v
                if copy:
                    nf = copy_feature(self.layer, self.feats[fid], ng)
                    for idx, f in attr_idx.items():
                        nf.setAttribute(idx, f(self.feats[fid].attribute(idx)))
                    for idx, v in extra.items():
                        nf.setAttribute(idx, v)
                    if self.layer.addFeature(nf):
                        n += 1
                elif self.layer.changeGeometry(fid, ng):
                    for idx, f in attr_idx.items():
                        self.layer.changeAttributeValue(fid, idx, f(self.feats[fid].attribute(idx)))
                    for idx, v in extra.items():
                        self.layer.changeAttributeValue(fid, idx, v)
                    n += 1
        except Exception:
            self.layer.destroyEditCommand()
            raise
        self.layer.endEditCommand()
        self.marks.append(self.layer.undoStack().index())
        self.layer.triggerRepaint()
        return n

    def undo_last(self):
        stack = self.layer.undoStack()
        if self.marks and stack.index() == self.marks[-1]:
            stack.undo()
            self.marks.pop()
            self.layer.triggerRepaint()
            return True
        self.cl.echo('No hay nada que deshacer en este comando.')
        return False

    # ---------------------------------------------------- a implementar
    def after_selection(self):
        self.prompt()

    def step_prompt(self):
        pass

    def step_point(self, p):
        pass

    def step_text(self, text):
        self._resolve_and_apply(text)

    def step_enter(self):
        self.end()
