# -*- coding: utf-8 -*-
"""
Comandos de edición al estilo AutoCAD:
DESPLAZA, COPIA, GIRA, ALINEAR, ESTIRA, EQDIST, ALARGA y EMPALME.
"""

import math
from types import SimpleNamespace

from qgis.core import (QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle, QgsVectorLayer,
                       QgsVectorLayerUtils)

from .commands import _key
from .compat import geometry_kind
from .editkit import (EditCommand, GeomIO, affine, block_scale_fn, mirror_geom, mirror_matrix, mirror_text_attrs,
                      text_rotation_fn, text_scale_fn, cap_flat, conform, copy_feature, explode,
                      join_miter, nearest_part, pick_feature, query_geom, rebuild, replace_part,
                      search_radius, segments_from_geometry)
from .geomops import (GeomError, break_at, break_between, divide_distances, explode_segments,
                      extend_end, fillet_same, fillet_two, measure_distances, perpendicular_foot,
                      point_at, same,
                      prolong_segments, seg_seg, segments_of, split_at_distances, trim_polyline,
                      trim_removed)
from .settings import get_setting, set_setting
from .units import InputError, format_length, format_point, parse_degrees, parse_distance, parse_point

OPT_UNDO = ('H', 'U', 'DESHACER', 'UNDO')
OPT_EXIT = ('S', 'SALIR', 'E', 'EXIT')


def _vec(a, b):
    return b.x() - a.x(), b.y() - a.y()


def _translate(dx, dy):
    def fn(g):
        g = QgsGeometry(g)
        g.translate(dx, dy)
        return g
    return fn


def _rotation_from_text(text, units):
    v = parse_degrees(text, units)
    return math.radians(-v if units.angdir_cw else v)


def _point_angle(base, p, units):
    return math.atan2(p.y() - base.y(), p.x() - base.x()) - math.radians(units.angbase)


# ==========================================================================
class _BaseDisplacement(EditCommand):
    """Lógica común de 'punto base / segundo punto / desplazamiento'."""
    second_prompt = 'Precise segundo punto o'

    def after_selection(self):
        self.state = 'base'
        self.prompt()

    def step_prompt(self):
        st = self.state
        if st == 'base':
            self.cl.set_prompt('Precise punto base o', [('D', 'Desplazamiento')], 'Desplazamiento')
        elif st == 'disp':
            self.cl.set_prompt('Precise desplazamiento', None, '0,0')
        elif st == 'second':
            self.cl.set_prompt(self.second_prompt, None, 'usar primer punto como desplazamiento')

    def step_point(self, p):
        if self.state == 'base':
            self.base_pt = p
            self._set_last(p)
            self.state = 'second'
            self.prompt()
        elif self.state == 'second':
            self.do(*_vec(self.base_pt, p))

    def step_text(self, text):
        k = _key(text)
        if self.state == 'base' and k in ('D', 'DESPLAZAMIENTO', 'DISPLACEMENT'):
            self.state = 'disp'
            self.prompt()
        elif self.state == 'disp':
            pi = parse_point(text, self.mgr.units, (0.0, 0.0))
            if pi.kind != 'point':
                raise InputError('Escriba el desplazamiento como dx,dy o d<ángulo.')
            self.do(*pi.point)
        else:
            self._resolve_and_apply(text)

    def step_enter(self):
        if self.state == 'base':
            self.state = 'disp'
            self.prompt()
        elif self.state == 'second':
            self.do(self.base_pt.x(), self.base_pt.y())   # primer punto como desplazamiento
        else:
            self.end()

    def preview_geoms(self, cur):
        if self.state == 'second' and self.base_pt is not None:
            return self.transformed(_translate(*_vec(self.base_pt, cur)))
        return None


class MoveCommand(_BaseDisplacement):
    title = 'DESPLAZA'

    def do(self, dx, dy):
        n = self.apply_geoms(_translate(dx, dy), 'DESPLAZA')
        self.cl.echo('%d objeto(s) desplazado(s).' % n)
        self.end()


class CopyCommand(_BaseDisplacement):
    title = 'COPIA'

    def after_selection(self):
        self.state = 'base'
        self.array_n = None
        self.array_fit = False
        self.prompt()

    def step_prompt(self):
        st = self.state
        if st == 'second' and not self.marks:
            self.cl.set_prompt('Precise segundo punto o', [('M', 'Matriz')],
                               'usar primer punto como desplazamiento')
        elif st == 'second':
            self.cl.set_prompt('Precise segundo punto o', [('M', 'Matriz'), ('S', 'Salir'), ('H', 'desHacer')],
                               'Salir')
        elif st == 'array_n':
            self.cl.set_prompt('Indique número de elementos de la matriz')
        elif st == 'array_pt':
            self.cl.set_prompt('Precise segundo punto o', [('A', 'Ajustar')])
        else:
            super().step_prompt()

    def step_point(self, p):
        if self.state == 'array_pt':
            dx, dy = _vec(self.base_pt, p)
            n = self.array_n
            if self.array_fit:
                dx, dy = dx / (n - 1), dy / (n - 1)
            self.layer.beginEditCommand('COPIA matriz')
            for k in range(1, n):
                for fid, g in self.geoms.items():
                    ng = conform(self.io.to_layer(_translate(dx * k, dy * k)(g)), self.layer)
                    self.layer.addFeature(copy_feature(self.layer, self.feats[fid], ng))
            self.layer.endEditCommand()
            self.marks.append(self.layer.undoStack().index())
            self.layer.triggerRepaint()
            self.state = 'second'
            self.array_fit = False
            self.prompt()
            return
        if self.state == 'second':
            self.apply_geoms(_translate(*_vec(self.base_pt, p)), 'COPIA', copy=True)
            self.prompt()
            return
        super().step_point(p)

    def step_text(self, text):
        k = _key(text)
        if self.state == 'second' and k in ('M', 'MATRIZ', 'ARRAY'):
            self.state = 'array_n'
        elif self.state == 'second' and self.marks and k in OPT_UNDO:
            self.undo_last()
        elif self.state == 'second' and k in OPT_EXIT:
            self.end()
            return
        elif self.state == 'array_n':
            n = int(parse_distance(text))
            if n < 2:
                raise InputError('El número de elementos debe ser 2 o más.')
            self.array_n = n
            self.state = 'array_pt'
        elif self.state == 'array_pt' and k in ('A', 'AJUSTAR', 'FIT'):
            self.array_fit = True
            self.cl.set_prompt('Precise segundo punto')
            return
        elif self.state == 'disp':
            pi = parse_point(text, self.mgr.units, (0.0, 0.0))
            if pi.kind != 'point':
                raise InputError('Escriba el desplazamiento como dx,dy o d<ángulo.')
            self.apply_geoms(_translate(*pi.point), 'COPIA', copy=True)
            self.end()
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def step_enter(self):
        if self.state == 'second' and not self.marks:
            self.apply_geoms(_translate(self.base_pt.x(), self.base_pt.y()), 'COPIA', copy=True)
            self.end()
        elif self.state in ('second', 'array_n', 'array_pt'):
            self.end()
        else:
            super().step_enter()

    def preview_geoms(self, cur):
        if self.state == 'array_pt' and self.base_pt is not None:
            dx, dy = _vec(self.base_pt, cur)
            n = self.array_n
            if self.array_fit:
                dx, dy = dx / (n - 1), dy / (n - 1)
            out = []
            for k in range(1, min(n, 50)):
                out += self.transformed(_translate(dx * k, dy * k))
            return out
        return super().preview_geoms(cur)

    def do(self, dx, dy):
        self.apply_geoms(_translate(dx, dy), 'COPIA', copy=True)
        self.end()


# ==========================================================================
class RotateCommand(EditCommand):
    title = 'GIRA'

    def after_selection(self):
        self.state = 'base'
        self.copy = False
        self.ref = 0.0
        self.ref_p1 = None
        self.cl.echo('Ángulo positivo actual: %s  ANGBASE = %g'
                     % ('horario' if self.mgr.units.angdir_cw else 'antihorario', self.mgr.units.angbase))
        self.prompt()

    def step_prompt(self):
        st = self.state
        if st == 'base':
            self.cl.set_prompt('Precise punto base')
        elif st == 'angle':
            self.cl.set_prompt('Precise ángulo de rotación o', [('C', 'Copia'), ('R', 'Referencia')], '0')
        elif st == 'ref1':
            self.cl.set_prompt('Precise ángulo de referencia', None, '0')
        elif st == 'ref2':
            self.cl.set_prompt('Precise segundo punto')
        elif st == 'new':
            self.cl.set_prompt('Precise nuevo ángulo o', [('P', 'Puntos')], '0')
        elif st == 'new1':
            self.cl.set_prompt('Precise primer punto')
        elif st == 'new2':
            self.cl.set_prompt('Precise segundo punto')

    def base(self):
        if self.selecting:
            return None
        if self.state == 'ref2' or self.state == 'new2':
            return self.ref_p1
        return self.base_pt

    def _rot(self, theta):
        b = self.base_pt
        return lambda g: affine(g, 1.0, theta, b, b)

    def do(self, theta):
        attrs = text_rotation_fn(theta) if self.layer.fields().indexOf('ROTACION') != -1 else None
        n = self.apply_geoms(self._rot(theta), 'GIRA', copy=self.copy, attr_fn=attrs)
        self.cl.echo('%d objeto(s) %s.' % (n, 'copiado(s) y girado(s)' if self.copy else 'girado(s)'))
        self.end()

    def step_point(self, p):
        st, u = self.state, self.mgr.units
        if st == 'base':
            self.base_pt = p
            self._set_last(p)
            self.state = 'angle'
        elif st == 'angle':
            self.do(_point_angle(self.base_pt, p, u))
            return
        elif st == 'ref1':
            self.ref_p1 = p
            self.state = 'ref2'
        elif st == 'ref2':
            self.ref = math.atan2(p.y() - self.ref_p1.y(), p.x() - self.ref_p1.x())
            self.state = 'new'
        elif st == 'new':
            self.do(math.atan2(p.y() - self.base_pt.y(), p.x() - self.base_pt.x()) - self.ref)
            return
        elif st == 'new1':
            self.ref_p1 = p
            self.state = 'new2'
        elif st == 'new2':
            self.do(math.atan2(p.y() - self.ref_p1.y(), p.x() - self.ref_p1.x()) - self.ref)
            return
        self.prompt()

    def step_text(self, text):
        k, st, u = _key(text), self.state, self.mgr.units
        if st == 'angle' and k in ('C', 'COPIA', 'COPY'):
            self.copy = True
            self.cl.echo('Girando una copia de los objetos designados.')
        elif st == 'angle' and k in ('R', 'REFERENCIA', 'REFERENCE'):
            self.state = 'ref1'
        elif st == 'angle':
            self.do(_rotation_from_text(text, u))
            return
        elif st == 'ref1':
            self.ref = _rotation_from_text(text, u)
            self.state = 'new'
        elif st == 'new' and k in ('P', 'PUNTOS', 'POINTS'):
            self.state = 'new1'
        elif st == 'new':
            self.do(_rotation_from_text(text, u) - self.ref)
            return
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def step_enter(self):
        if self.state in ('angle', 'new'):
            self.do(0.0 - (self.ref if self.state == 'new' else 0.0))
        elif self.state == 'ref1':
            self.ref = 0.0
            self.state = 'new'
            self.prompt()
        else:
            self.end()

    def preview_geoms(self, cur):
        if self.state == 'angle':
            return self.transformed(self._rot(_point_angle(self.base_pt, cur, self.mgr.units)))
        if self.state == 'new':
            th = math.atan2(cur.y() - self.base_pt.y(), cur.x() - self.base_pt.x()) - self.ref
            return self.transformed(self._rot(th))
        return None


# ==========================================================================
class AlignCommand(EditCommand):
    """ALINEAR (AL). Opción Copia (C): deja el original y alinea una copia, como
    el Alinear y Duplicar de Fernando (se recuerda)."""
    title = 'ALINEAR'
    copia_fija = None          # ALINEARCOPIA: siempre copia

    def after_selection(self):
        self.state = 's1'
        self.pairs = []
        self.copia = self.copia_fija if self.copia_fija is not None else get_setting('align_copy', False, bool)
        self.prompt()

    def step_prompt(self):
        texts = {'s1': 'Precise primer punto de origen', 'd1': 'Precise primer punto de destino',
                 's2': 'Precise segundo punto de origen', 'd2': 'Precise segundo punto de destino'}
        if self.state == 's2':
            self.cl.set_prompt(texts['s2'], None, 'continuar')
        elif self.state == 's1':
            self.cl.set_prompt(texts['s1'] + ' o', [('C', 'Copia=' + ('Sí' if self.copia else 'No'))])
        elif self.state == 'scale':
            self.cl.set_prompt('¿Atribuir escala a objetos según puntos de alineación?',
                               [('S', 'Sí'), ('N', 'No')], 'N')
        else:
            self.cl.set_prompt(texts[self.state])

    def base(self):
        if self.selecting:
            return None
        if self.state == 'd1':
            return self.src1
        if self.state == 'd2':
            return self.src2
        return None

    def step_point(self, p):
        st = self.state
        self._set_last(p)
        if st == 's1':
            self.src1, self.state = p, 'd1'
        elif st == 'd1':
            self.dst1, self.state = p, 's2'
        elif st == 's2':
            self.src2, self.state = p, 'd2'
        elif st == 'd2':
            self.dst2, self.state = p, 'scale'
        self.prompt()

    def _transform(self, scale):
        s1, d1 = self.src1, self.dst1
        if getattr(self, 'dst2', None) is None:
            return lambda g: affine(g, 1.0, 0.0, s1, d1)
        s2, d2 = self.src2, self.dst2
        a_src = math.atan2(s2.y() - s1.y(), s2.x() - s1.x())
        a_dst = math.atan2(d2.y() - d1.y(), d2.x() - d1.x())
        k = 1.0
        if scale:
            ls = math.hypot(s2.x() - s1.x(), s2.y() - s1.y())
            if ls < 1e-12:
                raise InputError('Los puntos de origen coinciden.')
            k = math.hypot(d2.x() - d1.x(), d2.y() - d1.y()) / ls
        return lambda g: affine(g, k, a_dst - a_src, s1, d1)

    def step_text(self, text):
        k = _key(text)
        if self.state == 's1' and k in ('C', 'COPIA', 'COPY'):
            self.copia = not self.copia
            if self.copia_fija is None:
                set_setting('align_copy', self.copia)
            self.cl.echo('Copia = %s' % ('Sí' if self.copia else 'No'))
            self.prompt()
            return
        if self.state == 'scale':
            if k in ('S', 'SI', 'SÍ', 'Y', 'YES'):
                self.finish(True)
            elif k in ('N', 'NO'):
                self.finish(False)
            else:
                raise InputError('Responda Sí o No.')
            return
        self._resolve_and_apply(text)

    def step_enter(self):
        if self.state == 's2':
            self.dst2 = None
            self.finish(False)
        elif self.state == 'scale':
            self.finish(False)
        else:
            self.end()

    def _align_params(self, scale):
        s1, d1 = self.src1, self.dst1
        if getattr(self, 'dst2', None) is None:
            return 1.0, 0.0
        s2, d2 = self.src2, self.dst2
        th = math.atan2(d2.y() - d1.y(), d2.x() - d1.x()) - math.atan2(s2.y() - s1.y(), s2.x() - s1.x())
        k = 1.0
        if scale:
            k = math.hypot(d2.x() - d1.x(), d2.y() - d1.y()) / max(1e-12, math.hypot(s2.x() - s1.x(), s2.y() - s1.y()))
        return k, th

    def finish(self, scale):
        attrs = None
        if self.layer.fields().indexOf('ROTACION') != -1:
            k, th = self._align_params(scale)
            attrs = text_rotation_fn(th)
            if abs(k - 1.0) > 1e-12:
                attrs.update(text_scale_fn(k))
                attrs.update(block_scale_fn(k))
        n = self.apply_geoms(self._transform(scale), 'ALINEAR', copy=self.copia, attr_fn=attrs)
        self.cl.echo('%d objeto(s) alineado(s)%s.' % (n, ' (copias)' if self.copia else ''))
        self.end()

    def step_preview(self, cur):
        guide = []
        for a, b in ((getattr(self, 'src1', None), getattr(self, 'dst1', None)),
                     (getattr(self, 'src2', None), getattr(self, 'dst2', None))):
            if a is not None and b is not None:
                guide += [a, b]
        base = self.base()
        temp = [base, cur] if base is not None and cur is not None else []
        return [], False, temp, guide[:2] if len(guide) >= 2 else []

    def preview_geoms(self, cur):
        if self.state == 'd1':
            return self.transformed(lambda g: affine(g, 1.0, 0.0, self.src1, cur))
        if self.state == 'scale':
            return self.transformed(self._transform(False))
        return None


class AlignCopyCommand(AlignCommand):
    """ALINEARCOPIA: el Alinear y Duplicar de Fernando (ALINEAR que deja copias)."""
    copia_fija = True


# ==========================================================================
def _inside(w, v):
    if isinstance(w, QgsRectangle):
        return w.contains(QgsPointXY(v.x(), v.y()))
    return w.contains(QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y())))


class StretchCommand(_BaseDisplacement):
    title = 'ESTIRA'
    select_prompt = 'Designe objetos que desea estirar con una ventana de captura'
    accept_preselection = False

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.windows = []

    def begin(self):
        self.cl.echo('Designe objetos a estirar mediante una ventana de captura (de derecha a izquierda).')
        self.prompt()

    def on_window(self, a, b, crossing, polygon=None):
        if not crossing:
            return
        if polygon is not None:
            self.windows.append(polygon)          # polígono de captura (PC)
            return
        r = QgsRectangle(a, b)
        r.normalize()
        self.windows.append(r)

    def after_selection(self):
        if not self.windows:
            self.cl.echo('ESTIRA necesita al menos una ventana de captura.')
            self.end()
            return
        super().after_selection()

    def _stretch(self, dx, dy):
        wins = self.windows

        def fn(g):
            g = QgsGeometry(g)
            n = g.constGet().nCoordinates()
            orig = [g.vertexAt(i) for i in range(n)]
            for i, v in enumerate(orig):
                if any(_inside(w, v) for w in wins):
                    nv = v.clone()
                    nv.setX(v.x() + dx)
                    nv.setY(v.y() + dy)
                    g.moveVertex(nv, i)
            return g
        return fn

    def do(self, dx, dy):
        n = self.apply_geoms(self._stretch(dx, dy), 'ESTIRA')
        self.cl.echo('%d objeto(s) estirado(s).' % n)
        self.end()

    def preview_geoms(self, cur):
        if self.state == 'second' and self.base_pt is not None:
            return self.transformed(self._stretch(*_vec(self.base_pt, cur)))
        return None


# ==========================================================================
class _PickCommand(EditCommand):
    """Comandos que designan objetos de a uno (EQDIST, ALARGA, EMPALME)."""
    uses_selection = False

    def pick(self, p, exclude=()):
        fid, f = pick_feature(self.canvas, self.io, self.layer, p, exclude)
        if fid is None:
            self.cl.echo('No se ha encontrado ningún objeto.')
        return fid, f

    def highlight(self, fids):
        self.layer.selectByIds(list(fids))

    def hover_geoms(self, cur, exclude=()):
        """El objeto bajo el cursor, para resaltarlo antes del clic (Fernando)."""
        if cur is None:
            return None
        fid, f = pick_feature(self.canvas, self.io, self.layer, cur, exclude)
        if fid is None:
            return None
        return [self.io.to_canvas(f.geometry())]


# ==========================================================================
# COPIABASE / PEGARENPUNTO: lo que CAD Copiar/Mover de Fernando agregaba a COPIA
# y DESPLAZA (COPYBASE y PASTECLIP de AutoCAD). La memoria vive mientras QGIS
# está abierto y no usa el portapapeles de QGIS (Ctrl+C / Ctrl+V siguen igual).
_MEMORIA = {}


class CopyBaseCommand(EditCommand):
    title = 'COPIABASE'

    def after_selection(self):
        self.prompt()

    def step_prompt(self):
        self.cl.set_prompt('Precise punto base')

    def step_point(self, p):
        if not self.geoms:
            self.end()
            return
        _MEMORIA.clear()
        _MEMORIA.update(geoms=[QgsGeometry(g) for g in self.geoms.values()],
                        feats=[QgsFeature(f) for f in self.feats.values()],
                        base=QgsPointXY(p), capa=self.layer.name())
        self.cl.echo('%d objeto(s) de "%s" guardado(s) con su punto base. PEGARENPUNTO los inserta.'
                     % (len(self.geoms), self.layer.name()))
        self.end()

    def step_text(self, text):
        self._resolve_and_apply(text)

    def step_enter(self):
        self.end()


def _por_nombre(layer, feat, geom):
    """Objeto nuevo en 'layer' con los datos de 'feat' que tengan el mismo nombre
    de campo (puede venir de otra capa)."""
    pk = set(layer.primaryKeyAttributes())
    origen = feat.fields()
    attrs = {}
    for i, campo in enumerate(layer.fields()):
        j = origen.indexOf(campo.name())
        if i not in pk and j != -1:
            attrs[i] = feat.attribute(j)
    return QgsVectorLayerUtils.createFeature(layer, geom, attrs, layer.createExpressionContext())


class PasteBaseCommand(_PickCommand):
    """PEGARENPUNTO: inserta lo guardado con COPIABASE en la capa activa, tomando
    el punto base como ancla; sigue pidiendo puntos (copia múltiple, como el de
    Fernando) hasta Intro o Esc."""
    title = 'PEGARENPUNTO'

    def begin(self):
        if not _MEMORIA.get('geoms'):
            self.cl.echo('No hay nada guardado: use primero COPIABASE.')
            self.end()
            return
        self.base_pt = _MEMORIA['base']
        self.cl.echo('%d objeto(s) de "%s".' % (len(_MEMORIA['geoms']), _MEMORIA['capa']))
        self.prompt()

    def step_prompt(self):
        self.cl.set_prompt('Precise punto de inserción o', [('H', 'desHacer')])

    def _movidas(self, p):
        b = _MEMORIA['base']
        out = []
        for g in _MEMORIA['geoms']:
            ng = QgsGeometry(g)
            ng.translate(p.x() - b.x(), p.y() - b.y())
            out.append(ng)
        return out

    def step_point(self, p):
        kind = geometry_kind(self.layer)
        lyr = self.layer
        lyr.beginEditCommand('PEGARENPUNTO')
        n = 0
        for g, f in zip(self._movidas(p), _MEMORIA['feats']):
            if geometry_kind(SimpleNamespace(geometryType=g.type)) != kind:
                continue
            if lyr.addFeature(_por_nombre(lyr, f, conform(self.io.to_layer(g), lyr))):
                n += 1
        if not n:
            lyr.destroyEditCommand()
            self.cl.echo('Lo guardado no es del tipo de la capa "%s".' % lyr.name())
            return
        lyr.endEditCommand()
        self.marks.append(lyr.undoStack().index())
        lyr.triggerRepaint()
        self.cl.echo('%d objeto(s) pegado(s).' % n)
        self.prompt()

    def step_text(self, text):
        if _key(text) in OPT_UNDO:
            self.undo_last()
            self.prompt()
            return
        self._resolve_and_apply(text)

    def step_enter(self):
        self.end()

    def preview_geoms(self, cur):
        if cur is None or not _MEMORIA.get('geoms'):
            return None
        return self._movidas(cur)


class OffsetCommand(_PickCommand):
    """EQDIST (OFFSET), con el comportamiento del Offset de Fernando: queda
    activo para hacer varias copias, resalta la línea bajo el cursor, muestra
    la copia antes del clic, y el clic derecho (o Intro) pide otra distancia
    sin salir. Se sale con Esc o S (Salir)."""
    title = 'EQDIST'

    def begin(self):
        self.dist = get_setting('offsetdist', -1.0, float)   # -1 = Punto a atravesar
        self.through = self.dist < 0
        self.state = 'dist'
        self.d_p1 = None
        self.cl.echo('Parámetros actuales: Borrar origen = No  Capa = Origen')
        self.prompt()

    def _dist_default(self):
        return 'Punto a atravesar' if self.through else format_length(self.dist, self.mgr.units)

    def step_prompt(self):
        st = self.state
        if st == 'dist':
            self.cl.set_prompt('Precise distancia de desfase o', [('P', 'Punto a atravesar')],
                               self._dist_default())
        elif st == 'dist2':
            self.cl.set_prompt('Precise segundo punto')
        elif st == 'pick':
            self.cl.set_prompt('Designe objeto a desplazar o',
                               [('D', 'Distancia'), ('S', 'Salir'), ('H', 'desHacer')], 'Distancia')
        elif st == 'side':
            txt = 'Precise punto a atravesar o' if self.through else 'Precise punto en lado de desfase o'
            self.cl.set_prompt(txt, [('D', 'Distancia'), ('S', 'Salir'), ('H', 'desHacer')], 'Distancia')

    def base(self):
        return self.d_p1 if self.state == 'dist2' else None

    def step_point(self, p):
        st = self.state
        if st == 'dist':
            self.d_p1 = p
            self.state = 'dist2'
        elif st == 'dist2':
            self._set_dist(math.hypot(p.x() - self.d_p1.x(), p.y() - self.d_p1.y()))
        elif st == 'pick':
            fid, f = self.pick(p)
            if fid is not None:
                self.cur_fid, self.cur_feat = fid, f
                self.highlight([fid])
                self.state = 'side'
        elif st == 'side':
            self._make(p)
            self.layer.removeSelection()
            self.state = 'pick'
        self.prompt()

    def _set_dist(self, d):
        if d <= 0:
            raise InputError('La distancia debe ser mayor que cero.')
        self.dist, self.through = d, False
        set_setting('offsetdist', d)
        self.state = 'pick'

    def step_text(self, text):
        k, st = _key(text), self.state
        if st == 'dist' and k in ('P', 'PUNTO', 'T', 'THROUGH'):
            self.through = True
            set_setting('offsetdist', -1.0)
            self.state = 'pick'
        elif st == 'dist':
            self._set_dist(parse_distance(text))
        elif st in ('pick', 'side') and k in OPT_EXIT:
            self.end()
            return
        elif st in ('pick', 'side') and k in ('D', 'DISTANCIA', 'DISTANCE'):
            self._otra_distancia()
            return
        elif st in ('pick', 'side') and k in OPT_UNDO:
            self.undo_last()
            self.layer.removeSelection()
            self.state = 'pick'
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def step_enter(self):
        if self.state == 'dist':
            if not self.through and self.dist <= 0:
                self.through = True
            self.state = 'pick'
            self.prompt()
        elif self.state == 'dist2':
            self.state = 'dist'
            self.prompt()
        else:
            self._otra_distancia()      # clic derecho = otra distancia, sin salir (Fernando)

    def _otra_distancia(self):
        self.layer.removeSelection()
        self.state = 'dist'
        self.d_p1 = None
        self.prompt()

    def _offset_geom(self, side):
        g = self.io.to_canvas(self.cur_feat.geometry())
        pg = QgsGeometry.fromPointXY(side)
        kind = geometry_kind(self.layer)
        d = g.distance(pg) if self.through else self.dist
        if d <= 0:
            raise InputError('El punto está sobre el objeto.')
        if kind == 'polygon':
            inside = g.contains(pg)
            res = g.buffer(-d if inside else d, 8, cap_flat(), join_miter(), 4.0)
        else:
            if g.isMultipart():
                k_, struct, flat, index = explode(g)
                k = nearest_part(flat, side)
                g = rebuild('line', [flat[k]])
            cands = [g.offsetCurve(s * d, 8, join_miter(), 4.0) for s in (1, -1)]
            cands = [c for c in cands if c is not None and not c.isEmpty()]
            if not cands:
                raise InputError('No se pudo desfasar el objeto.')
            res = min(cands, key=lambda c: c.distance(pg))
        if res is None or res.isEmpty():
            raise InputError('No se pudo desfasar el objeto con esa distancia.')
        return res

    def _make(self, side):
        res = self._offset_geom(side)
        ng = conform(self.io.to_layer(res), self.layer)
        self.layer.beginEditCommand('EQDIST')
        ok = self.layer.addFeature(copy_feature(self.layer, self.cur_feat, ng))
        self.layer.endEditCommand()
        if ok:
            self.marks.append(self.layer.undoStack().index())
            self.layer.triggerRepaint()

    def preview_geoms(self, cur):
        if self.state == 'side':
            try:
                return [self._offset_geom(cur)]
            except (InputError, GeomError):
                return None
        if self.state == 'pick':
            return self.hover_geoms(cur)
        return None


# ==========================================================================
class PerpendicularCommand(_PickCommand):
    """PERPENDICULAR, la Tool Perpendicular de Fernando: un punto de origen (con
    las referencias a objetos) y después una línea; se dibuja la perpendicular
    desde el origen hasta la línea o hasta su prolongación. Antes del clic se
    ve cómo queda. Sigue con otra; Intro (o clic derecho) con origen lo suelta,
    sin origen sale; Esc sale."""
    title = 'PERPENDICULAR'

    def begin(self):
        self.p0 = None
        self.prompt()

    def step_prompt(self):
        if self.p0 is None:
            self.cl.set_prompt('Precise punto de origen o', [('H', 'desHacer')])
        else:
            self.cl.set_prompt('Designe línea (o su prolongación) para la perpendicular')

    def _foot(self, p, quiet=False):
        fid, f = pick_feature(self.canvas, self.io, self.layer, p) if quiet else self.pick(p)
        if fid is None:
            return None
        kind, _s, flat, _i = explode(self.io.to_canvas(f.geometry()))
        if kind not in ('line', 'polygon'):
            return None
        k = nearest_part(flat, p)
        if k is None or len(flat[k]) < 2:
            return None
        return perpendicular_foot(flat[k], (self.p0.x(), self.p0.y()), (p.x(), p.y()))

    def step_point(self, p):
        if self.p0 is None:
            self.p0 = p
            self.prompt()
            return
        foot = self._foot(p)
        if foot is None:
            self.cl.echo('El origen ya está sobre esa línea, o no hay una línea ahí.')
            return
        if self.mgr.add_feature(self.layer, [self.p0, QgsPointXY(*foot)], title='PERPENDICULAR'):
            self.marks.append(self.layer.undoStack().index())
        self.p0 = None                    # como la de Fernando: lista para la siguiente
        self.prompt()

    def step_text(self, text):
        if _key(text) in OPT_UNDO and self.p0 is None:
            self.undo_last()
            self.prompt()
            return
        self._resolve_and_apply(text)

    def step_enter(self):
        if self.p0 is not None:
            self.p0 = None
            self.prompt()
        else:
            self.end()

    def preview_geoms(self, cur):
        if cur is None:
            return None
        if self.p0 is None:
            return None
        foot = self._foot(cur, quiet=True)
        if foot is None:
            return None
        return [QgsGeometry.fromPolylineXY([self.p0, QgsPointXY(*foot)])]


# ==========================================================================
class ExtendCommand(_PickCommand):
    """ALARGA (EXTEND), con el comportamiento del Extend de Fernando: primero se
    designan las líneas de llegada (quedan marcadas), después cada clic alarga
    hasta la más cercana, con vista previa bajo el cursor; los contornos no se
    alargan. Intro (o clic derecho) sin designar = todos los objetos visibles."""
    title = 'ALARGA'
    select_prompt = 'Designe objetos de contorno o <todos>'
    all_text = 'Contornos: todos los objetos visibles.'
    trims = False          # clic: alarga; Mayús + clic: recorta (en RECORTA, al revés)

    def begin(self):
        self.boundary = None
        self.cl.echo('Parámetros actuales: Contornos = designar (Intro = todos los objetos visibles)')
        self._designar_contornos()

    def _designar_contornos(self):
        self._pv = {}
        self.selecting = True
        self.sel = []
        self.prompt()

    def step_prompt(self):
        self.cl.set_prompt('Designe objeto que desea alargar o', [('C', 'Contornos'), ('H', 'desHacer')])

    def step_text(self, text):
        k = _key(text)
        if k in ('C', 'CONTORNOS', 'B', 'BOUNDARY'):
            self._designar_contornos()
        elif k in OPT_UNDO:
            self.undo_last()
            self.prompt()
        else:
            self._resolve_and_apply(text)

    def on_enter(self):
        if self.selecting and not self.sel:
            self.selecting = False
            self.boundary = None
            self.cl.echo(self.all_text)
            self.prompt()
            return
        super().on_enter()

    def after_selection(self):
        self.boundary = list(self.sel)
        self._pv = {}
        self.cl.echo('%d objeto(s) de contorno.' % len(self.boundary))
        self.prompt()               # quedan designados: se ven cuáles son

    def _boundaries(self, rect, exclude=None):
        """Segmentos de corte (SRC del mapa). exclude = fid de esta capa que no actúa como contorno."""
        segs = []
        if self.boundary:
            req = QgsFeatureRequest().setFilterFids(self.boundary)
            for f in self.layer.getFeatures(req):
                if f.hasGeometry() and f.id() != exclude:
                    segs += segments_from_geometry(self.io.to_canvas(f.geometry()))
            return segs
        for lyr in self.canvas.layers():
            if not isinstance(lyr, QgsVectorLayer) or geometry_kind(lyr) not in ('line', 'polygon'):
                continue
            io = GeomIO(self.canvas, lyr)
            req = QgsFeatureRequest().setFilterRect(io.rect_to_layer(rect))
            req.setLimit(20000)
            same_layer = lyr is self.layer
            for f in lyr.getFeatures(req):
                if f.hasGeometry() and not (same_layer and f.id() == exclude):
                    segs += segments_from_geometry(io.to_canvas(f.geometry()))
        return segs

    def _cut_segments(self, rect, exclude):
        """Contra qué se recorta (RECORTA prolonga las aristas designadas)."""
        return self._boundaries(rect, exclude)

    def _far(self):
        return max(self.canvas.fullExtent().width(), self.canvas.fullExtent().height(),
                   self.canvas.extent().width()) * 4.0

    def _pick_quiet(self, p, quiet):
        if quiet:
            return pick_feature(self.canvas, self.io, self.layer, p)
        return self.pick(p)

    # ------------------------------------------------ recortar (RECORTA, o Mayús en ALARGA)
    def _trim_calc(self, p, fid=None, f=None, quiet=False):
        """Lo que haría RECORTA en p, sin tocar la capa; None si no hay nada que recortar."""
        if fid is None:
            fid, f = self._pick_quiet(p, quiet)
            if fid is None:
                return None
        g = self.io.to_canvas(f.geometry())
        kind, struct, flat, index = explode(g)
        if kind != 'line':
            if not quiet:
                self.cl.echo('Solo se pueden recortar objetos lineales.')
            return None
        k = nearest_part(flat, p)
        if k is None:
            return None
        pts = flat[k]
        xs, ys = [c[0] for c in pts], [c[1] for c in pts]
        bb = QgsRectangle(QgsPointXY(min(xs), min(ys)), QgsPointXY(max(xs), max(ys)))
        bb.grow(max(bb.width(), bb.height()) * 0.01 + 1e-6)
        segs = self._cut_segments(bb, fid)
        for j, other in enumerate(flat):            # las otras partes del mismo objeto también cortan
            if j != k:
                segs += segments_of(other)
        parts = trim_polyline(pts, (p.x(), p.y()), segs)
        if parts == [] and self.boundary:
            parts = None        # con aristas designadas, lo que no las cruza no se borra (Fernando)
        if parts is None:
            if not quiet:
                self.cl.echo('El objeto no corta ningún contorno.')
            return None
        return fid, f, kind, struct, flat, index, k, parts, segs

    def _trim_at(self, p, title='RECORTA', fid=None, f=None, quiet=False):
        """Recorta el tramo del objeto designado en p entre los contornos más cercanos."""
        r = self._trim_calc(p, fid, f, quiet)
        if r is None:
            return False
        fid, f, kind, struct, flat, index, k, parts, _segs = r
        lyr = self.layer
        if not parts:
            rest = [q for j, q in enumerate(flat) if j != k]
            lyr.beginEditCommand(title)
            if rest:
                lyr.changeGeometry(fid, conform(self.io.to_layer(rebuild('line', rest)), lyr))
            else:
                lyr.deleteFeature(fid)        # sin intersecciones: AutoCAD lo borra
            lyr.endEditCommand()
            self.marks.append(lyr.undoStack().index())
            lyr.triggerRepaint()
            return True
        _replace_with_parts(self, fid, f, kind, struct, index, k, parts, title)
        return True

    def step_point(self, p):
        if self.mgr.shift:
            self._trim_at(p)          # Mayús + clic: recorta (como AutoCAD)
            return
        self._extend_at(p)

    # ------------------------------------------------ alargar
    def _extend_calc(self, p, quiet=False):
        """(fid, geometría nueva en la capa, tramo agregado) o None."""
        fid, f = self._pick_quiet(p, quiet)
        if fid is None:
            return None
        if self.boundary and fid in self.boundary:
            if not quiet:
                self.cl.echo('Es un contorno: designe otra línea para alargar.')
            return None
        kind, struct, flat, index = explode(self.io.to_canvas(f.geometry()))
        if kind != 'line':
            if not quiet:
                self.cl.echo('Solo se pueden alargar objetos lineales.')
            return None
        k = nearest_part(flat, p)
        if k is None:
            return None
        pts = flat[k]
        if same(pts[0], pts[-1]):
            if not quiet:
                self.cl.echo('El objeto está cerrado y no se puede alargar.')
            return None
        pk = (p.x(), p.y())
        at_start = math.hypot(pk[0] - pts[0][0], pk[1] - pts[0][1]) < \
            math.hypot(pk[0] - pts[-1][0], pk[1] - pts[-1][1])
        clave = (fid, k, at_start, self.layer.undoStack().index())
        if clave in self._pv:                     # la vista previa no recalcula en cada movimiento
            return self._pv[clave]
        e, n = (pts[0], pts[1]) if at_start else (pts[-1], pts[-2])
        L = self._far()
        dx, dy = e[0] - n[0], e[1] - n[1]
        ln = math.hypot(dx, dy)
        far = (e[0] + dx / ln * L, e[1] + dy / ln * L)
        rect = QgsRectangle(QgsPointXY(*e), QgsPointXY(*far))
        rect.normalize()
        rect.grow(max(rect.width(), rect.height()) * 0.01 + 1e-6)
        new = extend_end(pts, pk, self._boundaries(rect))
        if new is None:
            if not quiet:
                self.cl.echo('El objeto no corta ningún contorno.')
            res = None
        else:
            ng = conform(self.io.to_layer(rebuild('line', replace_part(kind, struct, index, k, new))),
                         self.layer)
            res = (fid, ng, [new[0], pts[0]] if at_start else [pts[-1], new[-1]])
        if len(self._pv) > 200:
            self._pv = {}
        self._pv[clave] = res
        return res

    def _extend_at(self, p):
        r = self._extend_calc(p)
        if r is None:
            return
        fid, ng, _tramo = r
        self.layer.beginEditCommand('ALARGA')
        self.layer.changeGeometry(fid, ng)
        self.layer.endEditCommand()
        self.marks.append(self.layer.undoStack().index())
        self.layer.triggerRepaint()

    def preview_geoms(self, cur):
        """Bajo el cursor: el tramo que se agrega (alargar) o el que se quita (recortar)."""
        if self.selecting or getattr(self, 'fence', None) is not None or getattr(self, 'edge_ask', False):
            return None
        if self.mgr.shift != self.trims:
            r = self._trim_calc(cur, quiet=True)
            if r is None:
                return None
            flat, k, segs = r[4], r[6], r[8]
            tramo = trim_removed(flat[k], (cur.x(), cur.y()), segs)
        else:
            r = self._extend_calc(cur, quiet=True)
            tramo = r[2] if r is not None else None
        if not tramo or len(tramo) < 2:
            return None
        return [QgsGeometry.fromPolylineXY([QgsPointXY(*c) for c in tramo])]

    def step_enter(self):
        self.end()


# ==========================================================================
class FilletCommand(_PickCommand):
    """EMPALME (FILLET). Como el Fillet de Fernando: el lado que queda de cada
    línea es el del clic (ángulo interno), la línea bajo el cursor se resalta
    y, elegida la primera, antes del segundo clic se ve cómo quedan las dos.
    Conserva lo de Dibujo: Radio (R), Múltiple (M), desHacer (H), Mayús =
    esquina (radio 0), polilíneas y dos tramos del mismo objeto."""
    title = 'EMPALME'

    def begin(self):
        self.radius = get_setting('filletrad', 0.0, float)
        self.multiple = False
        self.state = 'first'
        self.first = None
        self.cl.echo('Parámetros actuales: Modo = RECORTAR, Radio = %s'
                     % format_length(self.radius, self.mgr.units))
        self.prompt()

    def step_prompt(self):
        if self.state == 'first':
            self.cl.set_prompt('Designe primer objeto o', [('H', 'desHacer'), ('R', 'Radio'), ('M', 'Múltiple')])
        elif self.state == 'second':
            self.cl.set_prompt('Designe segundo objeto o mantenga pulsada Mayús y designe objeto '
                               'para aplicar esquina')
        elif self.state == 'radius':
            self.cl.set_prompt('Precise radio de empalme', None, format_length(self.radius, self.mgr.units))

    def step_text(self, text):
        k = _key(text)
        if self.state == 'radius':
            r = parse_distance(text)
            if r < 0:
                raise InputError('El radio no puede ser negativo.')
            self.radius = r
            set_setting('filletrad', r)
            self.state = 'first'
        elif self.state == 'first' and k in ('R', 'RADIO', 'RADIUS'):
            self.state = 'radius'
        elif self.state == 'first' and k in ('M', 'MULTIPLE', 'MÚLTIPLE'):
            self.multiple = True
        elif self.state == 'first' and k in OPT_UNDO:
            self.undo_last()
        else:
            self._resolve_and_apply(text)
            return
        self.prompt()

    def step_enter(self):
        if self.state == 'radius':
            self.state = 'first'
            self.prompt()
        else:
            self.end()

    def step_point(self, p):
        fid, f = self.pick(p)
        if fid is None:
            return
        if self.state == 'first':
            self.first = (fid, f, p)
            self.highlight([fid])
            self.state = 'second'
            self.prompt()
            return
        r = 0.0 if self.mgr.shift else self.radius
        try:
            self._fillet(self.first, (fid, f, p), r)
        except GeomError as e:
            self.cl.echo(str(e))
        self.layer.removeSelection()
        self.first = None
        self.state = 'first'
        if self.multiple:
            self.prompt()
        else:
            self.end()

    def _fillet(self, a, b, r):
        fid1, f1, p1 = a
        fid2, f2, p2 = b
        g1 = self.io.to_canvas(f1.geometry())
        kind1, s1, flat1, idx1 = explode(g1)
        P1, P2 = (p1.x(), p1.y()), (p2.x(), p2.y())
        k1 = nearest_part(flat1, p1)
        self.layer.beginEditCommand('EMPALME')
        try:
            if fid1 == fid2:
                k2 = nearest_part(flat1, p2)
                if k1 != k2:
                    raise GeomError('Designe dos segmentos de la misma parte del objeto.')
                pts = flat1[k1]
                closed = kind1 == 'polygon' or same(pts[0], pts[-1])
                new = fillet_same(pts, P1, P2, r, closed)
                ng = rebuild(kind1, replace_part(kind1, s1, idx1, k1, new))
                self.layer.changeGeometry(fid1, conform(self.io.to_layer(ng), self.layer))
            else:
                if kind1 != 'line':
                    raise GeomError('EMPALME entre objetos distintos solo funciona en capas de líneas.')
                g2 = self.io.to_canvas(f2.geometry())
                kind2, s2, flat2, idx2 = explode(g2)
                k2 = nearest_part(flat2, p2)
                n1, n2, arc = fillet_two(flat1[k1], P1, flat2[k2], P2, r)
                ng1 = rebuild('line', replace_part('line', s1, idx1, k1, n1))
                ng2 = rebuild('line', replace_part('line', s2, idx2, k2, n2))
                self.layer.changeGeometry(fid1, conform(self.io.to_layer(ng1), self.layer))
                self.layer.changeGeometry(fid2, conform(self.io.to_layer(ng2), self.layer))
                if arc:
                    ga = conform(self.io.to_layer(rebuild('line', [arc])), self.layer)
                    self.layer.addFeature(copy_feature(self.layer, f1, ga))
        except Exception:
            self.layer.destroyEditCommand()
            raise
        self.layer.endEditCommand()
        self.marks.append(self.layer.undoStack().index())
        self.layer.triggerRepaint()

    def snap_points(self):
        return []

    def preview(self, cur):
        return [], False, [], []

    def preview_geoms(self, cur):
        if cur is None or self.state not in ('first', 'second'):
            return None
        if self.state == 'first' or self.first is None:
            return self.hover_geoms(cur)
        fid, f = pick_feature(self.canvas, self.io, self.layer, cur)
        if fid is None:
            return None
        try:
            return self._fillet_result(self.first, (fid, f, cur), 0.0 if self.mgr.shift else self.radius)
        except (GeomError, InputError, ValueError, ZeroDivisionError):
            return None

    def _fillet_result(self, a, b, r):
        """Cómo quedarían los objetos (SRC del mapa), sin tocar la capa."""
        fid1, f1, p1 = a
        fid2, f2, p2 = b
        kind1, s1, flat1, idx1 = explode(self.io.to_canvas(f1.geometry()))
        P1, P2 = (p1.x(), p1.y()), (p2.x(), p2.y())
        k1 = nearest_part(flat1, p1)
        if fid1 == fid2:
            if nearest_part(flat1, p2) != k1:
                return None
            pts = flat1[k1]
            closed = kind1 == 'polygon' or same(pts[0], pts[-1])
            return [rebuild(kind1, replace_part(kind1, s1, idx1, k1, fillet_same(pts, P1, P2, r, closed)))]
        if kind1 != 'line':
            return None
        kind2, s2, flat2, idx2 = explode(self.io.to_canvas(f2.geometry()))
        if kind2 != 'line':
            return None
        n1, n2, arc = fillet_two(flat1[k1], P1, flat2[nearest_part(flat2, p2)], P2, r)
        out = [QgsGeometry.fromPolylineXY([QgsPointXY(*c) for c in n1]),
               QgsGeometry.fromPolylineXY([QgsPointXY(*c) for c in n2])]
        if arc:
            out.append(QgsGeometry.fromPolylineXY([QgsPointXY(*c) for c in arc]))
        return out


# ==========================================================================
class TrimCommand(ExtendCommand):
    """RECORTA (TRIM), con el comportamiento del Trim de Fernando: primero las
    aristas de corte (quedan marcadas) y cada una corta también por su
    prolongación, aunque no llegue a la línea (Arista = Prolongación). Intro
    sin designar = modo rápido de AutoCAD: todos los objetos visibles cortan,
    tal como están."""
    title = 'RECORTA'
    select_prompt = 'Designe aristas de corte o <todos>'
    all_text = 'Aristas: todos los objetos visibles (modo rápido).'
    trims = True
    EDGES = {'E': 'Prolongación', 'N': 'No prolongación'}

    def begin(self):
        self.boundary = None
        self.fence = None
        self.edge_ask = False
        self.mark_steps = {}
        self.edge = 'N' if str(get_setting('trimedge', 'E', str)).upper() == 'N' else 'E'
        self.cl.echo('Parámetros actuales: Proyección = SCP  Arista = %s' % self.EDGES[self.edge])
        self._designar_contornos()

    def _cut_segments(self, rect, exclude):
        segs = self._boundaries(rect, exclude)
        if self.boundary and self.edge == 'E':
            segs = prolong_segments(segs, self._far())
        return segs

    def step_prompt(self):
        if self.edge_ask:
            self.cl.set_prompt('Precise modo de prolongación implícito de arista',
                               [('P', 'Prolongación'), ('N', 'No prolongación')], self.EDGES[self.edge])
            return
        if self.fence is not None:
            if not self.fence:
                self.cl.set_prompt('Precise primer punto de borde')
            else:
                self.cl.set_prompt('Precise punto final de línea o', [('H', 'desHacer')])
            return
        self.cl.set_prompt('Designe objeto que desea recortar o mantenga pulsada Mayús y designe objeto '
                           'para alargar o', [('C', 'Contornos'), ('B', 'Borde'), ('A', 'Arista'),
                                              ('H', 'desHacer')])

    def step_text(self, text):
        k = _key(text)
        if self.edge_ask:
            if k in ('P', 'PROLONGACION', 'PROLONGACIÓN', 'E', 'EXTEND'):
                self.edge = 'E'
            elif k in ('N', 'NO', 'NOPROLONGACION', 'NOPROLONGACIÓN', 'NOEXTEND'):
                self.edge = 'N'
            else:
                raise InputError('Escriba P (Prolongación) o N (No prolongación).')
            set_setting('trimedge', self.edge)
            self.edge_ask = False
            self._pv = {}
            self.cl.echo('Arista = %s' % self.EDGES[self.edge])
            self.prompt()
            return
        if self.fence is not None:
            if k in OPT_UNDO and self.fence:
                self.fence.pop()
                self.prompt()
            else:
                self._resolve_and_apply(text)
            return
        if k in ('B', 'BORDE', 'F', 'FENCE'):
            self.fence = []
            self.prompt()
            return
        if k in ('A', 'ARISTA', 'E', 'EDGE'):
            self.edge_ask = True
            self.prompt()
            return
        super().step_text(text)

    def step_point(self, p):
        self.edge_ask = False
        if self.fence is not None:
            self.fence.append(p)
            self.prompt()
            return
        if self.mgr.shift:
            self._extend_at(p)        # Mayús + clic: alarga
        else:
            self._trim_at(p)
        self.prompt()

    def step_enter(self):
        if self.edge_ask:
            self.edge_ask = False
            self.prompt()
            return
        if self.fence is not None:
            pts, self.fence = self.fence, None
            if len(pts) >= 2:
                n = self._trim_fence(pts)
                self.cl.echo('%d tramo(s) recortado(s).' % n if n else 'El borde no corta ningún objeto recortable.')
            self.prompt()
            return
        self.end()

    def _trim_fence(self, pts):
        """Recorta cada objeto en cada punto donde lo cruza el borde."""
        fence_segs = [((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(pts, pts[1:])]
        geom = QgsGeometry.fromPolylineXY(list(pts))
        fids = query_geom(self.io, self.layer, geom, 'intersects')
        hits = []
        req = QgsFeatureRequest().setFilterFids(fids) if fids else None
        for f in (self.layer.getFeatures(req) if req is not None else []):
            if not f.hasGeometry():
                continue
            for seg in segments_from_geometry(self.io.to_canvas(f.geometry())):
                for a0, a1 in fence_segs:
                    r = seg_seg(a0, a1, seg[0], seg[1])
                    if r is not None:
                        hits.append(QgsPointXY(*r[1]))
        n = 0
        tol = search_radius(self.canvas) * 0.05
        stack = self.layer.undoStack()
        start = stack.index()
        for hp in hits:
            # el objeto puede haber cambiado (o perdido ese tramo) con un recorte anterior
            fid, f = pick_feature(self.canvas, self.io, self.layer, hp)
            if fid is None:
                continue
            if self.io.to_canvas(f.geometry()).distance(QgsGeometry.fromPointXY(hp)) > tol:
                continue
            if self._trim_at(hp, fid=fid, f=f, quiet=True):
                n += 1
        if n:
            # un único desHacer para todo el borde
            self.marks = [m for m in self.marks if m <= start] + [stack.index()]
            self.mark_steps[stack.index()] = stack.index() - start
        return n

    def undo_last(self):
        stack = self.layer.undoStack()
        if self.marks and stack.index() == self.marks[-1]:
            steps = self.mark_steps.pop(self.marks[-1], 1)
            for _ in range(steps):
                if stack.canUndo():
                    stack.undo()
            self.marks.pop()
            self.layer.triggerRepaint()
            return True
        self.cl.echo('No hay nada que deshacer en este comando.')
        return False

    def step_preview(self, cur):
        if self.fence:
            return [], False, list(self.fence) + ([cur] if cur is not None else []), []
        return [], False, [], []


# ==========================================================================
def _replace_with_parts(cmd, fid, feat, kind, struct, index, k, parts, title):
    """Reemplaza la parte k por parts[0] y crea objetos nuevos con el resto."""
    if not parts:
        raise GeomError('No queda ninguna parte del objeto.')
    lyr = cmd.layer
    lyr.beginEditCommand(title)
    try:
        ng = conform(cmd.io.to_layer(rebuild(kind, replace_part(kind, struct, index, k, parts[0]))), lyr)
        lyr.changeGeometry(fid, ng)
        for extra in parts[1:]:
            g = conform(cmd.io.to_layer(rebuild('line', [extra])), lyr)
            lyr.addFeature(copy_feature(lyr, feat, g))
    except Exception:
        lyr.destroyEditCommand()
        raise
    lyr.endEditCommand()
    cmd.marks.append(lyr.undoStack().index())
    lyr.triggerRepaint()


class _LinePick(_PickCommand):
    """Designa un objeto lineal y recuerda la parte más cercana al punto."""

    def take(self, p):
        fid, f = self.pick(p)
        if fid is None:
            return False
        kind, struct, flat, index = explode(self.io.to_canvas(f.geometry()))
        if kind != 'line':
            self.cl.echo('El objeto designado no es lineal.')
            return False
        self.obj = (fid, f, kind, struct, flat, index, nearest_part(flat, p))
        self.highlight([fid])
        return True


class BreakAtPointCommand(_LinePick):
    title = 'PARTEENPUNTO'

    def begin(self):
        self.state = 'obj'
        self.prompt()

    def step_prompt(self):
        self.cl.set_prompt('Designe objeto' if self.state == 'obj' else 'Precise punto de ruptura')

    def step_point(self, p):
        if self.state == 'obj':
            if self.take(p):
                self.state = 'pt'
            self.prompt()
            return
        fid, f, kind, struct, flat, index, k = self.obj
        parts = break_at(flat[k], (p.x(), p.y()))
        _replace_with_parts(self, fid, f, kind, struct, index, k, parts, 'PARTEENPUNTO')
        self.cl.echo('Objeto partido en %d.' % len(parts) if len(parts) > 1 else 'Objeto cerrado abierto en el punto.')
        self.end()

    def step_enter(self):
        self.end()


class BreakCommand(_LinePick):
    title = 'PARTE'

    def begin(self):
        self.state = 'obj'
        self.p1 = None
        self.prompt()

    def step_prompt(self):
        st = self.state
        if st == 'obj':
            self.cl.set_prompt('Designe objeto')
        elif st == 'second':
            self.cl.set_prompt('Precise segundo punto de ruptura o', [('P', 'Primer punto')])
        elif st == 'first':
            self.cl.set_prompt('Precise primer punto de ruptura')

    def base(self):
        return self.p1 if self.state == 'second' else None

    def step_point(self, p):
        st = self.state
        if st == 'obj':
            if self.take(p):
                self.p1 = p          # el punto de designación es el primer punto (como AutoCAD)
                self.state = 'second'
        elif st == 'first':
            self.p1 = p
            self.state = 'second'
        elif st == 'second':
            fid, f, kind, struct, flat, index, k = self.obj
            parts = break_between(flat[k], (self.p1.x(), self.p1.y()), (p.x(), p.y()))
            _replace_with_parts(self, fid, f, kind, struct, index, k, parts, 'PARTE')
            self.end()
            return
        self.prompt()

    def step_text(self, text):
        if self.state == 'second' and _key(text) in ('P', 'PRIMER', 'F', 'FIRST'):
            self.state = 'first'
            self.prompt()
            return
        self._resolve_and_apply(text)

    def step_enter(self):
        self.end()


class ExplodeCommand(EditCommand):
    title = 'DESCOMP'

    def start(self):
        from .blocks import is_block_layer
        if self.kind == 'point' and not is_block_layer(self.layer):
            self.cl.echo('DESCOMP: en capas de puntos solo se descomponen inserciones de bloque.')
            _DrawCommand_end(self)
            return
        super().start()

    def after_selection(self):
        from .blocks import LIB, explode_rows, instance_params, is_block_layer
        if is_block_layer(self.layer):
            lyr, made, skipped, n = self.layer, 0, 0, 0
            done = []
            for fid, f in list(self.feats.items()):
                try:
                    name, x, y, sx, sy, rot = instance_params(f)
                except Exception:  # noqa: BLE001 - inserción sin geometría o sin nombre
                    skipped += 1
                    continue
                rows = LIB.rows(name)
                if not rows:
                    self.cl.echo('No se encontró la definición del bloque "%s".' % name)
                    skipped += 1
                    continue
                m_, s_ = explode_rows(rows, x, y, sx, sy, rot, lyr.crs())
                made, skipped = made + m_, skipped + s_
                if m_:
                    done.append(fid)
                    n += 1
            self.feats = {}
            self.geoms = {}
            lyr.removeSelection()
            if done:
                if not lyr.isEditable():
                    lyr.startEditing()
                lyr.beginEditCommand('DESCOMP bloque')
                lyr.deleteFeatures(done)
                lyr.endEditCommand()
            lyr.triggerRepaint()
            msg = '%d bloque(s) descompuesto(s) en %d objeto(s).' % (n, made)
            if skipped:
                msg += ' %d entidad(es) sin capa de destino compatible.' % skipped
            self.cl.echo(msg)
            self.end()
            return
        lyr = self.layer
        n_in, n_out, skipped = 0, 0, 0
        lyr.beginEditCommand('DESCOMP')
        try:
            for fid, g in self.geoms.items():
                kind, struct, flat, index = explode(g)
                f = self.feats[fid]
                if kind == 'line':
                    pieces = []
                    for part in flat:
                        pieces += explode_segments(part)
                    geoms = [rebuild('line', [p]) for p in pieces]
                else:
                    geoms = [rebuild('polygon', [poly]) for poly in struct]
                if len(geoms) < 2:
                    skipped += 1
                    continue
                lyr.changeGeometry(fid, conform(self.io.to_layer(geoms[0]), lyr))
                for g2 in geoms[1:]:
                    lyr.addFeature(copy_feature(lyr, f, conform(self.io.to_layer(g2), lyr)))
                n_in += 1
                n_out += len(geoms)
        except Exception:
            lyr.destroyEditCommand()
            raise
        lyr.endEditCommand()
        lyr.triggerRepaint()
        msg = '%d objeto(s) descompuesto(s) en %d.' % (n_in, n_out)
        if skipped:
            msg += ' %d no se pueden descomponer.' % skipped
        self.cl.echo(msg)
        self.end()


class DivideCommand(_LinePick):
    title = 'DIVIDE'
    measure = False

    def begin(self):
        self.state = 'obj'
        self.split = False
        self.prompt()

    def step_prompt(self):
        if self.state == 'obj':
            self.cl.set_prompt('Designe objeto a %s' % ('graduar' if self.measure else 'dividir'))
        elif self.measure:
            self.cl.set_prompt('Precise longitud de segmento o', [('P', 'Partir')] if not self.split else None)
        else:
            self.cl.set_prompt('Indique el número de segmentos o', [('P', 'Partir')] if not self.split else None)

    def step_point(self, p):
        if self.state == 'obj':
            if self.take(p):
                self.state = 'value'
            self.prompt()
            return
        if self.measure and self.state == 'value':
            # longitud indicada con dos puntos: el primero es el designado
            raise InputError('Escriba la longitud del segmento.')

    def step_text(self, text):
        k = _key(text)
        if self.state != 'value':
            self._resolve_and_apply(text)
            return
        if k in ('P', 'PARTIR', 'SPLIT'):
            self.split = True
            self.cl.echo('Modo Partir: el objeto se dividirá en partes.')
            self.prompt()
            return
        v = parse_distance(text)
        fid, f, kind, struct, flat, index, kk = self.obj
        pts = flat[kk]
        if self.measure:
            ds = measure_distances(pts, v)
        else:
            if abs(v - round(v)) > 1e-9:
                raise InputError('Indique un número entero.')
            ds = divide_distances(pts, int(round(v)))
        if not ds:
            self.cl.echo('El objeto es más corto que la longitud indicada.')
            self.end()
            return
        if self.split:
            if same(pts[0], pts[-1]):
                ds = [d for d in ds if d > 1e-9]
            parts = split_at_distances(pts, ds)
            _replace_with_parts(self, fid, f, kind, struct, index, kk, parts, self.title)
            self.cl.echo('Objeto partido en %d partes.' % len(parts))
        else:
            from .auxlayers import point_layer
            pl = point_layer(self.mgr.iface, self.cl.echo)
            geoms = [QgsGeometry.fromPointXY(QgsPointXY(*point_at(pts, d))) for d in ds]
            n = self.mgr.add_geometries(pl, geoms, self.title)
            self.cl.echo('%d punto(s) creado(s) en "%s".' % (n, pl.name()))
        self.end()

    def step_enter(self):
        self.end()


class MeasureCommand(DivideCommand):
    title = 'GRADUA'
    measure = True


# ==========================================================================
class MirrorCommand(EditCommand):
    """SIMETRIA (MIRROR): copia simétrica o reflejo de los objetos."""
    title = 'SIMETRIA'

    def after_selection(self):
        self.state = 'p1'
        self.p1 = self.p2 = None
        self.prompt()

    def step_prompt(self):
        if self.state == 'p1':
            self.cl.set_prompt('Precise primer punto de línea de simetría')
        elif self.state == 'p2':
            self.cl.set_prompt('Precise segundo punto de línea de simetría')
        else:
            self.cl.set_prompt('¿Borrar objetos de origen?', [('S', 'Sí'), ('N', 'No')], 'No')

    def base(self):
        return self.p1 if (not self.selecting and self.state == 'p2') else None

    def step_point(self, p):
        if self.state == 'p1':
            self.p1 = p
            self._set_last(p)
            self.state = 'p2'
        elif self.state == 'p2':
            if abs(p.x() - self.p1.x()) < 1e-12 and abs(p.y() - self.p1.y()) < 1e-12:
                raise InputError('Los dos puntos de la línea de simetría coinciden.')
            self.p2 = p
            self._set_last(p)
            self.state = 'erase'
        self.prompt()

    def step_text(self, text):
        if self.state == 'erase':
            k = _key(text)
            if k in ('S', 'SI', 'SÍ', 'Y', 'YES'):
                self.finish(True)
            elif k in ('N', 'NO'):
                self.finish(False)
            else:
                raise InputError('Responda Sí o No.')
            return
        self._resolve_and_apply(text)

    def step_enter(self):
        if self.state == 'erase':
            self.finish(False)
        else:
            self.end()

    def finish(self, erase):
        p1, p2 = self.p1, self.p2
        attrs_for = None
        if self.layer.fields().indexOf('ESCALA_Y') != -1:
            phi = mirror_matrix(p1, p2)[4]
            ir = self.layer.fields().indexOf('ROTACION')
            iy = self.layer.fields().indexOf('ESCALA_Y')

            def attrs_for(f):
                def num(i, d):
                    try:
                        return float(f.attribute(i))
                    except (TypeError, ValueError):
                        return d
                return {'ROTACION': round((2 * math.degrees(phi) - num(ir, 0.0)) % 360.0, 8),
                        'ESCALA_Y': -num(iy, 1.0)}
        elif self.layer.fields().indexOf('ROTACION') != -1:
            phi = mirror_matrix(p1, p2)[4]
            ir = self.layer.fields().indexOf('ROTACION')
            ij = self.layer.fields().indexOf('JUST')

            def attrs_for(f):
                try:
                    rot = float(f.attribute(ir))
                except (TypeError, ValueError):
                    rot = 0.0
                just = str(f.attribute(ij) or 'I') if ij != -1 else 'I'
                r, j = mirror_text_attrs(rot, just, phi)
                out = {'ROTACION': r}
                if ij != -1:
                    out['JUST'] = j
                return out
        n = self.apply_geoms(lambda g: mirror_geom(g, p1, p2), 'SIMETRIA', copy=not erase,
                             attrs_for=attrs_for)
        self.cl.echo('%d objeto(s) %s.' % (n, 'reflejado(s)' if erase else 'copiado(s) en simetría'))
        self.end()

    def step_preview(self, cur):
        if self.state == 'p2' and cur is not None:
            return [], False, [self.p1, cur], []
        if self.state == 'erase':
            return [], False, [], [self.p1, self.p2]
        return [], False, [], []

    def preview_geoms(self, cur):
        if self.state == 'p2' and cur is not None and (cur.x() != self.p1.x() or cur.y() != self.p1.y()):
            return self.transformed(lambda g: mirror_geom(g, self.p1, cur))
        if self.state == 'erase':
            return self.transformed(lambda g: mirror_geom(g, self.p1, self.p2))
        return None


# ==========================================================================
class EraseCommand(EditCommand):
    """BORRA (ERASE): suprime los objetos designados. UPS (OOPS) los recupera."""
    title = 'BORRA'

    def after_selection(self):
        lyr = self.layer
        keep = [QgsFeature(self.feats[f]) for f in self.sel if f in self.feats]
        lyr.beginEditCommand('BORRA')
        n = 0
        for fid in list(self.sel):
            if lyr.deleteFeature(fid):
                n += 1
        lyr.endEditCommand()
        lyr.triggerRepaint()
        self.mgr.last_erased = (lyr, keep)
        self.cl.echo('%d objeto(s) borrado(s).  (UPS para recuperarlos)' % n)
        self.end()


def oops(mgr):
    """UPS (OOPS): recupera los objetos borrados por el último BORRA."""
    data = getattr(mgr, 'last_erased', None)
    if not data:
        mgr.cmdline.echo('No hay objetos borrados que recuperar.')
        return
    lyr, feats = data
    try:
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand('UPS')
        n = 0
        for f in feats:
            nf = copy_feature(lyr, f, QgsGeometry(f.geometry()))
            if lyr.addFeature(nf):
                n += 1
        lyr.endEditCommand()
        lyr.triggerRepaint()
    except RuntimeError:
        mgr.cmdline.echo('La capa de los objetos borrados ya no existe.')
        mgr.last_erased = None
        return
    mgr.last_erased = None
    mgr.cmdline.echo('%d objeto(s) recuperado(s).' % n)


# ==========================================================================
class SelectCommand(EditCommand):
    """DESIGNA (SELECT): crea una selección con cualquier modo (PV, PC, Borde...)
    y la deja activa para el próximo comando (y como selección Previa)."""
    title = 'DESIGNA'

    def start(self):
        self.sel = list(self.layer.selectedFeatureIds())    # se suma a la selección actual
        self.selecting = True
        if self.sel:
            self.cl.echo('%d objeto(s) ya designado(s).' % len(self.sel))
        self.prompt()

    def after_selection(self):
        self.layer.selectByIds(list(self.sel))
        self.cl.echo('%d objeto(s) designado(s). Quedan como preselección y como selección Previa (P).'
                     % len(self.sel))
        _DrawCommand_end(self)

    def end(self):
        if self.selecting:          # Esc durante la designación: se descarta
            super().end()
        else:
            _DrawCommand_end(self)


def _DrawCommand_end(cmd):
    """Termina sin borrar la selección (a diferencia del resto de los comandos de edición)."""
    if cmd.mgr.command is cmd:
        cmd.mgr.end_command()


# ==========================================================================
# (nombre, alias, clase, título, tipos de capa, descripción, icono)
EDIT_COMMANDS = [
    ('MOVE', ('DESPLAZA', 'DESPLAZAR', 'MOVER', 'D', 'M'), MoveCommand, 'DESPLAZA',
     ('line', 'polygon', 'point'), 'Desplaza objetos', 'move'),
    ('COPY', ('COPIA', 'COPIAR', 'CO', 'CP'), CopyCommand, 'COPIA',
     ('line', 'polygon', 'point'), 'Copia objetos (múltiple y matriz)', 'copy'),
    ('ROTATE', ('GIRA', 'GIRAR', 'ROTAR', 'GI', 'RO'), RotateCommand, 'GIRA',
     ('line', 'polygon', 'point'), 'Gira objetos (copia y referencia)', 'rotate'),
    ('SELECT', ('DESIGNA', 'SELECCIONAR', 'SELECCION', 'SEL'), SelectCommand, 'DESIGNA',
     ('line', 'polygon', 'point'), 'Designar objetos (PV, PC, Borde...) y dejarlos seleccionados', 'select'),
    ('ERASE', ('BORRA', 'BORRAR', 'BO', 'E', 'SUPR'), EraseCommand, 'BORRA',
     ('line', 'polygon', 'point'), 'Borra los objetos designados (UPS los recupera)', 'erase'),
    ('MIRROR', ('SIMETRIA', 'SIMETRÍA', 'SI', 'MI', 'ESPEJO'), MirrorCommand, 'SIMETRÍA',
     ('line', 'polygon', 'point'), 'Copia o refleja objetos respecto de una línea', 'mirror'),
    ('ALIGN', ('ALINEAR', 'AL'), AlignCommand, 'ALINEAR',
     ('line', 'polygon', 'point'), 'Alinea objetos con 1 o 2 pares de puntos (Copia = deja el original)',
     'align'),
    ('ALIGNCOPY', ('ALINEARCOPIA', 'ALINEARYDUPLICAR', 'ALC'), AlignCopyCommand, 'ALINEARCOPIA',
     ('line', 'polygon', 'point'), 'Alinear y duplicar: alinea una copia, el original queda', 'aligncopy'),
    ('COPYBASE', ('COPIABASE', 'COPIARCONBASE', 'CB'), CopyBaseCommand, 'COPIABASE',
     ('line', 'polygon', 'point'), 'Guarda los objetos designados con un punto base', 'copybase'),
    ('PASTECLIP', ('PEGARENPUNTO', 'PEGARBASE', 'PB'), PasteBaseCommand, 'PEGARENPUNTO',
     ('line', 'polygon', 'point'), 'Pega lo guardado con COPIABASE en un punto (en la capa activa)', 'pastebase'),
    ('STRETCH', ('ESTIRA', 'ESTIRAR', 'EI', 'S'), StretchCommand, 'ESTIRA',
     ('line', 'polygon'), 'Estira vértices dentro de una ventana de captura', 'stretch'),
    ('OFFSET', ('EQDIST', 'DESFASE', 'EQ', 'O'), OffsetCommand, 'EQDIST',
     ('line', 'polygon'), 'Crea objetos paralelos a una distancia', 'offset'),
    ('TRIM', ('RECORTA', 'RECORTAR', 'TR', 'RR'), TrimCommand, 'RECORTA',
     ('line',), 'Recorta objetos en las aristas de corte (Mayús = alarga)', 'trim'),
    ('EXTEND', ('ALARGA', 'ALARGAR', 'EXTENDER', 'AA', 'EX'), ExtendCommand, 'ALARGA',
     ('line',), 'Alarga líneas hasta los contornos (Mayús = recorta)', 'extend'),
    ('FILLET', ('EMPALME', 'EMPALMAR', 'EMP', 'F'), FilletCommand, 'EMPALME',
     ('line', 'polygon'), 'Empalme con radio (0 = esquina; paralelas = semicírculo)', 'fillet'),
    ('PERPENDICULAR', ('PERP', 'PERPEND'), PerpendicularCommand, 'PERPENDICULAR',
     ('line',), 'Línea perpendicular desde un punto a otra línea o a su prolongación', 'perp'),
    ('BREAKATPOINT', ('PARTEENPUNTO', 'PARTEPUNTO', 'BAP', 'PP'), BreakAtPointCommand, 'PARTEENPUNTO',
     ('line',), 'Parte un objeto en un punto', 'breakpt'),
    ('BREAK', ('PARTE', 'PARTIR', 'BR', 'PA'), BreakCommand, 'PARTE',
     ('line',), 'Elimina el tramo entre dos puntos', 'break'),
    ('EXPLODE', ('DESCOMP', 'DESCOMPONER', 'X', 'DE'), ExplodeCommand, 'DESCOMP',
     ('line', 'polygon', 'point'), 'Descompone bloques, polilíneas en tramos y multipartes en partes',
     'explode'),
    ('DIVIDE', ('DIVIDIR', 'DIV'), DivideCommand, 'DIVIDE',
     ('line',), 'Puntos a intervalos iguales (opción Partir)', 'divide'),
    ('MEASURE', ('GRADUA', 'GRADÚA', 'MEDIR', 'ME'), MeasureCommand, 'GRADÚA',
     ('line',), 'Puntos cada cierta longitud (opción Partir)', 'measure'),
]

__all__ = ['EDIT_COMMANDS', 'format_point']
