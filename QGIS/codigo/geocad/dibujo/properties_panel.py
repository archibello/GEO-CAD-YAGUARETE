# -*- coding: utf-8 -*-
"""Paleta PROPIEDADES (Ctrl+1) al estilo AutoCAD.

Muestra y modifica las propiedades de los objetos seleccionados en cualquier capa:
- General: capa CAD, color, tipo de línea y grosor (PorCapa o propios del objeto).
- Geometría: vértices, longitud, área, ángulo, posición.
- Texto: contenido, altura, rotación, fuente, negrita, justificación, color.
- Bloque: nombre, posición, escalas y rotación.

Color, tipo de línea y grosor propios se guardan en los campos CAD_COLOR, CAD_LTYPE y
CAD_LW (vacío = PorCapa); en las capas de textos, el color está en el campo COLOR.
Layer Properties los usa para dibujar.
"""

import json
import math

from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDockWidget, QHBoxLayout, QLabel,
                                 QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from qgis.core import (QgsCoordinateTransform, QgsFeatureRequest, QgsField, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorLayer, QgsWkbTypes)

from .compat import geometry_kind, qt
from .units import InputError, format_angle, format_length, parse_angle, parse_distance

VARIES = '*VARIAS*'
TEXT_FLAG = 'dibujo_cad/text_layer'
BLOCK_FLAG = 'dibujo_cad/block_layer'
SKIP_FLAGS = ('dibujo_cad/block_geom', 'dibujo_cad/block_defs')
CFG_KEY = 'cad_layer_manager/config'

COLORS = [('PorCapa', ''), ('1 Rojo', '#ff0000'), ('2 Amarillo', '#ffff00'), ('3 Verde', '#00ff00'),
          ('4 Cian', '#00ffff'), ('5 Azul', '#0000ff'), ('6 Magenta', '#ff00ff'),
          ('7 Blanco/Negro', '#000000'), ('8 Gris oscuro', '#414141'), ('9 Gris', '#808080')]
LINEWEIGHTS = [0.00, 0.05, 0.09, 0.13, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.53, 0.60,
               0.70, 0.80, 0.90, 1.00, 1.06, 1.20, 1.40, 1.58, 2.00, 2.11]
TYPE_ORDER = ['Línea', 'Polilínea', 'Polígono', 'Punto', 'Texto', 'Bloque']


def _linetypes():
    try:
        from Layer_Properties.linetypes import LINETYPES  # noqa: WPS433 - complemento hermano
        return [(n, lt.get('desc', n)) for n, lt in LINETYPES.items()]
    except Exception:  # noqa: BLE001
        return [(n, n) for n in ('Continuous', 'DASHED', 'DASHED2', 'HIDDEN', 'HIDDEN2', 'CENTER',
                                 'CENTER2', 'PHANTOM', 'DOT', 'DASHDOT', 'DIVIDE', 'BORDER')]


def _color_icon(value):
    pm = QPixmap(14, 14)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    if not value:
        p.fillRect(0, 0, 7, 14, QColor('#ffffff'))
        p.fillRect(7, 0, 7, 14, QColor('#000000'))
    elif value.lower() == '#000000':
        p.fillRect(0, 0, 14, 14, QColor('#ffffff'))
        p.fillRect(0, 7, 14, 7, QColor('#000000'))
    else:
        p.fillRect(0, 0, 14, 14, QColor(value))
    p.setPen(QColor('#606060'))
    p.drawRect(0, 0, 13, 13)
    p.end()
    return QIcon(pm)


def _str(v):
    if v is None:
        return ''
    try:
        from qgis.PyQt.QtCore import QVariant
        if isinstance(v, QVariant) and v.isNull():
            return ''
    except Exception:  # noqa: BLE001
        pass
    s = str(v)
    return '' if s in ('NULL', 'None') else s


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def kind_of(layer, feature):
    if layer.customProperty(TEXT_FLAG) == '1':
        return 'Texto'
    if layer.customProperty(BLOCK_FLAG) == '1':
        return 'Bloque'
    k = geometry_kind(layer)
    if k == 'point':
        return 'Punto'
    if k == 'polygon':
        return 'Polígono'
    g = feature.geometry()
    if g is not None and not g.isMultipart():
        try:
            if g.constGet().nCoordinates() == 2:
                return 'Línea'
        except Exception:  # noqa: BLE001
            pass
    return 'Polilínea'


class PropertiesPanel(QDockWidget):
    def __init__(self, iface, mgr, parent=None):
        super().__init__('Propiedades', parent)
        self.setObjectName('DibujoCADProperties')
        self.iface = iface
        self.mgr = mgr
        self.canvas = iface.mapCanvas()
        self.items = []            # [(capa, fid, tipo)]
        self.group = 'Todo'
        self.vertex = 0
        self._layers = []
        self._building = False
        self._cache = {}

        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(3, 3, 3, 3)
        v.setSpacing(3)
        top = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._group_changed)
        top.addWidget(self.combo, 1)
        v.addLayout(top)
        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers
                                   if hasattr(self.table, 'EditTrigger') else self.table.NoEditTriggers)
        self.table.setShowGrid(True)
        v.addWidget(self.table, 1)
        self.note = QLabel('')
        self.note.setWordWrap(True)
        self.note.setStyleSheet('color: #806000;')
        v.addWidget(self.note)
        self.setWidget(root)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.refresh)
        self.canvas.selectionChanged.connect(self.schedule)
        self.visibilityChanged.connect(lambda vis: vis and self.schedule())

    # ------------------------------------------------------------ ciclo
    def unload(self):
        self.timer.stop()
        try:
            self.canvas.selectionChanged.disconnect(self.schedule)
        except (TypeError, RuntimeError):
            pass
        self._unwatch()

    def schedule(self, *args):
        if self.isVisible():
            self.timer.start()

    def _unwatch(self):
        for lyr in self._layers:
            for sig in (lyr.geometryChanged, lyr.attributeValueChanged):
                try:
                    sig.disconnect(self.schedule)
                except (TypeError, RuntimeError):
                    pass
        self._layers = []

    def _collect(self):
        self._unwatch()
        items = []
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if not isinstance(lyr, QgsVectorLayer) or not lyr.isSpatial() or not lyr.selectedFeatureCount():
                    continue
                if any(lyr.customProperty(f) == '1' for f in SKIP_FLAGS):
                    continue
            except RuntimeError:
                continue
            req = QgsFeatureRequest().setFilterFids(list(lyr.selectedFeatureIds()))
            for f in lyr.getFeatures(req):
                items.append((lyr, f.id(), kind_of(lyr, f)))
            for sig in (lyr.geometryChanged, lyr.attributeValueChanged):
                sig.connect(self.schedule)
            self._layers.append(lyr)
        return items

    def refresh(self):
        if self._building:
            return
        self.items = self._collect()
        counts = {}
        for _l, _f, t in self.items:
            counts[t] = counts.get(t, 0) + 1
        self._building = True
        try:
            self.combo.clear()
            if not self.items:
                self.combo.addItem('Sin selección', 'Todo')
            else:
                self.combo.addItem('Todo (%d)' % len(self.items), 'Todo')
                for t in TYPE_ORDER:
                    if counts.get(t):
                        self.combo.addItem('%s (%d)' % (t, counts[t]), t)
            types = [t for t in TYPE_ORDER if counts.get(t)]
            want = self.group if self.group in counts else ('Todo' if len(types) != 1 else types[0])
            idx = max(0, self.combo.findData(want))
            self.combo.setCurrentIndex(idx)
            self.group = self.combo.itemData(idx) or 'Todo'
        finally:
            self._building = False
        self._build()

    def _group_changed(self, i):
        if self._building:
            return
        self.group = self.combo.itemData(i) or 'Todo'
        self.vertex = 0
        self._build()

    def current(self):
        if self.group == 'Todo':
            return list(self.items)
        return [it for it in self.items if it[2] == self.group]

    def _kind(self, sel):
        types = {t for _l, _f, t in sel}
        return next(iter(types)) if len(types) == 1 else None

    # ------------------------------------------------------------ lectura de valores
    def _feat(self, lyr, fid):
        key = (lyr.id(), fid)
        f = self._cache.get(key)
        if f is None:
            f = self._cache[key] = lyr.getFeature(fid)
        return f

    def _common(self, sel, getter):
        vals = set()
        for lyr, fid, _t in sel:
            vals.add(getter(lyr, self._feat(lyr, fid)))
            if len(vals) > 1:
                return None
        return next(iter(vals)) if vals else None

    def _attr(self, field):
        def g(lyr, f):
            i = lyr.fields().indexOf(field)
            return _str(f.attribute(i)) if i != -1 else ''
        return g

    def _to_canvas(self, lyr):
        dst = self.canvas.mapSettings().destinationCrs()
        if lyr.crs() == dst:
            return None
        return QgsCoordinateTransform(lyr.crs(), dst, QgsProject.instance())

    def _to_layer(self, lyr):
        dst = self.canvas.mapSettings().destinationCrs()
        if lyr.crs() == dst:
            return None
        return QgsCoordinateTransform(dst, lyr.crs(), QgsProject.instance())

    def _geom_canvas(self, lyr, f):
        g = QgsGeometry(f.geometry())
        tr = self._to_canvas(lyr)
        if tr is not None:
            g.transform(tr)
        return g

    # ------------------------------------------------------------ escritura
    def _ensure_field(self, lyr, name, kind='string', length=20):
        if lyr.fields().indexOf(name) != -1:
            return True
        try:
            from qgis.PyQt.QtCore import QMetaType
            t = QMetaType.Type.Double if kind == 'double' else QMetaType.Type.QString
            fld = QgsField(name, t, len=length if kind == 'string' else 0)
        except (ImportError, AttributeError, TypeError):
            from qgis.PyQt.QtCore import QVariant
            fld = QgsField(name, QVariant.Double if kind == 'double' else QVariant.String,
                           len=length if kind == 'string' else 0)
        ok = False
        if lyr.isEditable():
            ok = lyr.addAttribute(fld)
        else:
            try:
                ok = lyr.dataProvider().addAttributes([fld])
                lyr.updateFields()
            except Exception:  # noqa: BLE001
                ok = False
        ok = ok and lyr.fields().indexOf(name) != -1
        if not ok:
            self.mgr.cmdline.echo('No se pudo crear el campo %s en "%s".' % (name, lyr.name()))
            return False
        self._restyle(lyr)
        return True

    def _restyle(self, lyr):
        """Que Layer Properties vuelva a armar la simbología (incluye los campos nuevos)."""
        try:
            from qgis.utils import plugins
            ctrl = getattr(plugins.get('Layer_Properties'), 'ctrl', None)
            if ctrl is not None and lyr.customProperty(CFG_KEY):
                ctrl._apply_to(lyr, ctrl._load(lyr))
        except Exception:  # noqa: BLE001
            pass

    def _write(self, sel, field, value, kind='string', title='Propiedades'):
        by_layer = {}
        for lyr, fid, _t in sel:
            by_layer.setdefault(lyr, []).append(fid)
        for lyr, fids in by_layer.items():
            if not self._ensure_field(lyr, field, kind):
                continue
            idx = lyr.fields().indexOf(field)
            if not lyr.isEditable():
                lyr.startEditing()
            lyr.beginEditCommand(title)
            for fid in fids:
                lyr.changeAttributeValue(fid, idx, value)
            lyr.endEditCommand()
            lyr.triggerRepaint()
        self.schedule()

    def _write_geom(self, lyr, fid, geom_canvas, title='Propiedades'):
        g = QgsGeometry(geom_canvas)
        tr = self._to_layer(lyr)
        if tr is not None:
            g.transform(tr)
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand(title)
        lyr.changeGeometry(fid, g)
        lyr.endEditCommand()
        lyr.triggerRepaint()
        self.schedule()

    # ------------------------------------------------------------ tabla
    def _build(self):
        self._cache = {}
        self._building = True
        try:
            self.table.setRowCount(0)
            self.note.setText('')
            sel = self.current()
            if not sel:
                self._section('Sin objetos seleccionados')
                return
            kind = self._kind(sel)
            self._general(sel, kind)
            if kind in ('Línea', 'Polilínea', 'Polígono'):
                self._geometry(sel, kind)
            elif kind == 'Punto':
                self._position(sel, 'Geometría')
            elif kind == 'Texto':
                self._text(sel)
            elif kind == 'Bloque':
                self._block(sel)
            unmanaged = {l.name() for l, _f, _t in sel if not l.customProperty(CFG_KEY)}
            if unmanaged:
                self.note.setText('Sin Layer Properties en: %s. Color, tipo de línea y grosor propios se '
                                  'guardan, pero esas capas no los dibujan.' % ', '.join(sorted(unmanaged)))
            self.table.resizeColumnToContents(0)
        finally:
            self._building = False

    def _section(self, title):
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(title)
        f = QFont(it.font())
        f.setBold(True)
        it.setFont(f)
        it.setBackground(QBrush(QColor(128, 128, 128, 60)))
        self.table.setItem(r, 0, it)
        self.table.setSpan(r, 0, 1, 2)

    def _row(self, label, widget):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem('  ' + label))
        self.table.setCellWidget(r, 1, widget)

    def _text_row(self, label, value, commit=None):
        ed = QLineEdit(VARIES if value is None else value)
        ed.setFrame(False)
        if commit is None:
            ed.setReadOnly(True)
            ed.setStyleSheet('color: gray;')
        else:
            orig = ed.text()

            def done():
                if self._building or ed.text() == orig or ed.text() == VARIES:
                    return
                try:
                    commit(ed.text())
                except (InputError, ValueError) as e:
                    self.mgr.cmdline.echo('Propiedades: %s' % e)
                    self.schedule()
            ed.editingFinished.connect(done)
        self._row(label, ed)
        return ed

    def _combo_row(self, label, items, current, commit, icons=False, editable=False):
        cb = QComboBox()
        cb.setFrame(False)
        if current is None:
            cb.addItem(VARIES, None)
        for text, data in items:
            if icons:
                cb.addItem(_color_icon(data) if data != '__other__' else QIcon(), text, data)
            else:
                cb.addItem(text, data)
        if current is not None:
            i = cb.findData(current)
            if i == -1:
                cb.addItem(_color_icon(current) if icons else QIcon(), str(current), current)
                i = cb.count() - 1
            cb.setCurrentIndex(i)
        cb.setEditable(editable)

        def chosen(i):
            if self._building:
                return
            data = cb.itemData(i)
            if data is None and cb.itemText(i) == VARIES:
                return
            try:
                commit(data if data is not None else cb.itemText(i))
            except (InputError, ValueError) as e:
                self.mgr.cmdline.echo('Propiedades: %s' % e)
                self.schedule()
        cb.activated.connect(chosen)
        self._row(label, cb)
        return cb

    # ------------------------------------------------------------ secciones
    def _general(self, sel, kind):
        self._section('General')
        # capa CAD
        names = []
        for lyr in {l for l, _f, _t in sel}:
            raw = lyr.customProperty(CFG_KEY)
            try:
                for l in json.loads(raw)['layers'] if raw else []:
                    if l['name'] not in names:
                        names.append(l['name'])
            except (ValueError, KeyError, TypeError):
                pass
        if '0' not in names:
            names.insert(0, '0')
        cur = self._common(sel, lambda l, f: self._attr('LAYER_CODE')(l, f) or '0')
        self._combo_row('Capa', [(n, n) for n in names], cur, lambda v: self._set_cad_layer(sel, v))
        # color
        def color_field(lyr):
            return 'COLOR' if lyr.customProperty(TEXT_FLAG) == '1' else 'CAD_COLOR'
        cur = self._common(sel, lambda l, f: self._attr(color_field(l))(l, f).lower())
        self._combo_row('Color', COLORS + [('Seleccionar color...', '__other__')], cur,
                        lambda v: self._set_color(sel, v, color_field), icons=True)
        if kind not in ('Texto',):
            if kind != 'Punto':
                lts = [('PorCapa', '')] + [(n, n) for n, _d in _linetypes()]
                cur = self._common(sel, self._attr('CAD_LTYPE'))
                self._combo_row('Tipo de línea', lts, cur,
                                lambda v: self._write(sel, 'CAD_LTYPE', v or None, title='Tipo de línea'))
            lws = [('PorCapa', ''), ('Predeterminado', '-1')] + [('%.2f mm' % w, '%.2f' % w) for w in LINEWEIGHTS]
            cur = self._common(sel, lambda l, f: self._lw_key(self._attr('CAD_LW')(l, f)))
            self._combo_row('Grosor de línea', lws, cur, lambda v: self._write(
                sel, 'CAD_LW', float(v) if v not in ('', None) else None, kind='double', title='Grosor de línea'))
        qnames = sorted({l.name() for l, _f, _t in sel})
        self._text_row('Capa QGIS', ', '.join(qnames))

    def _set_cad_layer(self, sel, name):
        """Cambia la capa CAD; si la capa QGIS no la tiene definida, la agrega con las mismas
        propiedades que tenga en otra capa (si no, los objetos quedarían sin dibujar)."""
        defs = {}
        for lyr in {l for l, _f, _t in sel}:
            try:
                for l in json.loads(lyr.customProperty(CFG_KEY) or '{}').get('layers', []):
                    defs.setdefault(l['name'], l)
            except (ValueError, TypeError, AttributeError):
                pass
        for lyr in {l for l, _f, _t in sel}:
            raw = lyr.customProperty(CFG_KEY)
            if not raw:
                continue
            try:
                cfg = json.loads(raw)
                if any(l['name'] == name for l in cfg['layers']):
                    continue
                if name in defs:
                    cfg['layers'].append(dict(defs[name]))
                else:
                    from Layer_Properties.controller import new_layer
                    cfg['layers'].append(new_layer(name))
                lyr.setCustomProperty(CFG_KEY, json.dumps(cfg, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
        by_layer_len = 50
        for lyr in {l for l, _f, _t in sel}:
            self._ensure_field(lyr, 'LAYER_CODE', 'string', by_layer_len)
        self._write(sel, 'LAYER_CODE', name, title='Cambiar capa CAD')
        for lyr in {l for l, _f, _t in sel}:
            self._restyle(lyr)

    @staticmethod
    def _lw_key(raw):
        v = _num(raw)
        if v is None:
            return ''
        return '-1' if v < 0 else '%.2f' % v

    def _set_color(self, sel, v, color_field):
        if v == '__other__':
            c = QColorDialog.getColor(QColor('#ffffff'), self, 'Color del objeto')
            if not c.isValid():
                self.schedule()
                return
            v = c.name()
        by_field = {}
        for it in sel:
            by_field.setdefault(color_field(it[0]), []).append(it)
        for field, items in by_field.items():
            self._write(items, field, v or None, title='Color')
        for lyr in {l for l, _f, _t in sel if l.customProperty(TEXT_FLAG) == '1'}:
            try:
                from .text_tool import refresh_text_colors
                refresh_text_colors(lyr)
            except Exception:  # noqa: BLE001
                pass

    def _fmt(self, v):
        return format_length(v, self.mgr.units)

    def _geometry(self, sel, kind):
        self._section('Geometría')
        u = self.mgr.units
        if len(sel) != 1:
            total_len = 0.0
            total_area = 0.0
            for lyr, fid, _t in sel:
                g = self._geom_canvas(lyr, self._feat(lyr, fid))
                total_len += g.length()
                total_area += g.area()
            self._text_row('Longitud total', self._fmt(total_len))
            if kind == 'Polígono':
                self._text_row('Área total', self._fmt(total_area))
            return
        lyr, fid, _t = sel[0]
        g = self._geom_canvas(lyr, self._feat(lyr, fid))
        pts = [QgsPointXY(v.x(), v.y()) for v in g.vertices()]
        closed = kind == 'Polígono' or (len(pts) > 2 and pts[0] == pts[-1])
        if kind == 'Línea' and len(pts) == 2:
            a, b = pts
            self._text_row('Inicio X', self._fmt(a.x()), lambda t: self._move_vertex(lyr, fid, g, 0, x=t))
            self._text_row('Inicio Y', self._fmt(a.y()), lambda t: self._move_vertex(lyr, fid, g, 0, y=t))
            self._text_row('Fin X', self._fmt(b.x()), lambda t: self._move_vertex(lyr, fid, g, 1, x=t))
            self._text_row('Fin Y', self._fmt(b.y()), lambda t: self._move_vertex(lyr, fid, g, 1, y=t))
            self._text_row('Delta X', self._fmt(b.x() - a.x()))
            self._text_row('Delta Y', self._fmt(b.y() - a.y()))
            self._text_row('Longitud', self._fmt(g.length()), lambda t: self._set_length(lyr, fid, a, b, t))
            self._text_row('Ángulo', format_angle(math.atan2(b.y() - a.y(), b.x() - a.x()), u))
            return
        n = len(pts) - (1 if closed and len(pts) > 1 and pts[0] == pts[-1] else 0)
        self.vertex = min(self.vertex, max(0, n - 1))
        spin = QSpinBox()
        spin.setRange(1, max(1, n))
        spin.setValue(self.vertex + 1)
        spin.setFrame(False)
        spin.valueChanged.connect(lambda val: self._set_vertex(val - 1))
        self._row('Vértice', spin)
        if n:
            p = pts[self.vertex]
            k = self.vertex
            self._text_row('Vértice X', self._fmt(p.x()), lambda t: self._move_vertex(lyr, fid, g, k, x=t))
            self._text_row('Vértice Y', self._fmt(p.y()), lambda t: self._move_vertex(lyr, fid, g, k, y=t))
        self._text_row('Número de vértices', str(n))
        self._text_row('Cerrada', 'Sí' if closed else 'No')
        self._text_row('Longitud' if kind != 'Polígono' else 'Perímetro', self._fmt(g.length()))
        if closed:
            area = g.area() if kind == 'Polígono' else QgsGeometry.fromPolygonXY([pts]).area()
            self._text_row('Área', self._fmt(area))

    def _set_vertex(self, k):
        if self._building:
            return
        self.vertex = k
        QTimer.singleShot(0, self._build)

    def _move_vertex(self, lyr, fid, g, k, x=None, y=None):
        pts = [QgsPointXY(v.x(), v.y()) for v in g.vertices()]
        p = pts[k]
        nx = parse_distance(x) if x is not None else p.x()
        ny = parse_distance(y) if y is not None else p.y()
        g2 = QgsGeometry(g)
        if not g2.moveVertex(nx, ny, k):
            raise InputError('No se pudo mover el vértice.')
        self._write_geom(lyr, fid, g2, 'Mover vértice')

    def _set_length(self, lyr, fid, a, b, text):
        L = parse_distance(text)
        if L <= 0:
            raise InputError('La longitud debe ser mayor que cero.')
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        nb = QgsPointXY(a.x() + L * math.cos(ang), a.y() + L * math.sin(ang))
        g = self._geom_canvas(lyr, self._feat(lyr, fid))
        g.moveVertex(nb.x(), nb.y(), 1)
        self._write_geom(lyr, fid, g, 'Longitud')

    def _position(self, sel, title):
        self._section(title)
        if len(sel) != 1:
            self._text_row('Posición X', None)
            self._text_row('Posición Y', None)
            return
        lyr, fid, _t = sel[0]
        g = self._geom_canvas(lyr, self._feat(lyr, fid))
        p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]

        def move(x=None, y=None):
            nx = parse_distance(x) if x is not None else p.x()
            ny = parse_distance(y) if y is not None else p.y()
            self._write_geom(lyr, fid, QgsGeometry.fromPointXY(QgsPointXY(nx, ny)), 'Mover')
        self._text_row('Posición X', self._fmt(p.x()), lambda t: move(x=t))
        self._text_row('Posición Y', self._fmt(p.y()), lambda t: move(y=t))

    def _angle_row(self, sel, label, field):
        u = self.mgr.units
        cur = self._common(sel, lambda l, f: round(_num(f.attribute(l.fields().indexOf(field)), 0.0) % 360.0, 8)
                           if l.fields().indexOf(field) != -1 else 0.0)
        txt = None if cur is None else format_angle(math.radians(cur), u)
        self._text_row(label, txt, lambda t: self._write(
            sel, field, round(math.degrees(parse_angle(t, u)) % 360.0, 8), kind='double', title=label))

    def _num_row(self, sel, label, field, positive=True):
        cur = self._common(sel, lambda l, f: _num(f.attribute(l.fields().indexOf(field)))
                           if l.fields().indexOf(field) != -1 else None)

        def commit(t):
            v = parse_distance(t)
            if positive and v <= 0:
                raise InputError('El valor debe ser mayor que cero.')
            self._write(sel, field, v, kind='double', title=label)
        self._text_row(label, None if cur is None else self._fmt(cur), commit)

    def _text(self, sel):
        self._section('Texto')
        cur = self._common(sel, self._attr('TEXTO'))
        self._text_row('Contenido', cur, lambda t: self._write(sel, 'TEXTO', t, title='Contenido'))
        self._num_row(sel, 'Altura', 'ALTURA')
        self._angle_row(sel, 'Rotación', 'ROTACION')
        cur = self._common(sel, self._attr('FUENTE'))
        try:
            from qgis.PyQt.QtGui import QFontDatabase
            fams = list(QFontDatabase.families()) if hasattr(QFontDatabase, 'families') else \
                list(QFontDatabase().families())
        except Exception:  # noqa: BLE001
            fams = ['Arial']
        self._combo_row('Fuente', [(f, f) for f in fams], cur,
                        lambda v: self._write(sel, 'FUENTE', v, title='Fuente'))
        cur = self._common(sel, lambda l, f: bool(_num(self._attr('NEGRITA')(l, f), 0)))
        chk = QCheckBox()
        chk.setTristate(cur is None)
        if cur is not None:
            chk.setChecked(cur)
        else:
            chk.setCheckState(qt('CheckState', 'PartiallyChecked'))
        chk.clicked.connect(lambda on: self._write(sel, 'NEGRITA', 1 if chk.isChecked() else 0,
                                                   kind='string', title='Negrita') if not self._building else None)
        self._row('Negrita', chk)
        try:
            from .text_tool import JUST_NAMES
        except ImportError:
            JUST_NAMES = {}
        cur = self._common(sel, lambda l, f: self._attr('JUST')(l, f) or 'I')
        self._combo_row('Justificación', [(v, k) for k, v in JUST_NAMES.items()], cur,
                        lambda v: self._write(sel, 'JUST', v, title='Justificación'))
        self._position(sel, 'Posición')

    def _block(self, sel):
        self._section('Bloque')
        try:
            from .blocks import LIB
            names = LIB.names()
        except Exception:  # noqa: BLE001
            names = []
        cur = self._common(sel, self._attr('NOMBRE'))
        self._combo_row('Nombre', [(n, n) for n in names], cur,
                        lambda v: self._write(sel, 'NOMBRE', v, title='Bloque'))
        self._position(sel, 'Inserción')
        self._section('Escala y rotación')
        self._num_row(sel, 'Escala X', 'ESCALA_X', positive=False)
        self._num_row(sel, 'Escala Y', 'ESCALA_Y', positive=False)
        self._angle_row(sel, 'Rotación', 'ROTACION')
