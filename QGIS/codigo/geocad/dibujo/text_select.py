# -*- coding: utf-8 -*-
"""
Seleccionar texto: caja del texto con pinzamientos (como los grips de AutoCAD).

  ■ cuadrado  (punto de inserción)  -> arrastrar = mover   (usa REFENT; ORTO restringe)
  ● círculo   (a la derecha)         -> arrastrar = girar   (ORTO / Mayús: saltos de 15°)
  ▲ triángulo (arriba)               -> arrastrar = altura
  Arrastrar dentro de la caja        -> mover
  Doble clic                         -> editar el texto en el lugar
  Supr                               -> borrar el texto      Esc -> deseleccionar
"""

import math

from qgis.PyQt.QtCore import QEvent
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF
from qgis.PyQt.QtWidgets import QLineEdit
from qgis.core import QgsCoordinateReferenceSystem, QgsFeatureRequest, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker

from .compat import enum, polygon_geometry_type, qt
from .editkit import GeomIO, conform
from .text_tool import CAP_FACTOR, JUST, TextPreview, is_text_layer

GRIP_PX = 9


def _num(v, d):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _icon(name, fallback='ICON_X'):
    try:
        return enum(QgsVertexMarker, 'IconType', name)
    except AttributeError:
        return enum(QgsVertexMarker, 'IconType', fallback)


def text_metrics(info):
    """Caja local (sin girar, y hacia arriba) en unidades del mapa: x0, x1, y0, y1, baseline."""
    size = max(1e-9, info['height'] * CAP_FACTOR)
    f = QFont(info['font'])
    f.setPixelSize(100)
    f.setBold(info['bold'])
    fm = QFontMetricsF(f)
    s = size / 100.0
    txt = info['text'] or ' '
    w = (fm.horizontalAdvance(txt) if hasattr(fm, 'horizontalAdvance') else fm.width(txt)) * s
    cap = (fm.capHeight() if hasattr(fm, 'capHeight') else fm.ascent() * 0.7) * s
    desc = fm.descent() * s
    asc = fm.ascent() * s
    h, v = JUST.get(info['just'], ('Left', 'Base'))
    x0 = {'Left': 0.0, 'Center': -w / 2.0, 'Right': -w}[h]
    b = {'Base': 0.0, 'Bottom': desc, 'Half': -cap / 2.0, 'Cap': -cap, 'Top': -asc}[v]
    return x0, x0 + w, b - desc, b + cap, b, cap


def to_map(info, lx, ly):
    a = info['rot']
    ax, ay = info['anchor'].x(), info['anchor'].y()
    return QgsPointXY(ax + lx * math.cos(a) - ly * math.sin(a), ay + lx * math.sin(a) + ly * math.cos(a))


def to_local(info, p):
    a = info['rot']
    dx, dy = p.x() - info['anchor'].x(), p.y() - info['anchor'].y()
    return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)


def text_box(info):
    x0, x1, y0, y1, b, cap = text_metrics(info)
    pad = cap * 0.15
    return [to_map(info, x, y) for x, y in ((x0 - pad, y0 - pad), (x1 + pad, y0 - pad),
                                             (x1 + pad, y1 + pad), (x0 - pad, y1 + pad))]


def grips(info):
    x0, x1, y0, y1, b, cap = text_metrics(info)
    rot = to_map(info, x1 + max(cap, 1e-9) * 1.2, b + cap / 2.0)
    hy = y1 if abs(y1) >= abs(y0) else y0
    return {'move': info['anchor'], 'rot': rot, 'height': to_map(info, 0.0, hy + (cap * 0.3 if hy >= 0 else -cap * 0.3)),
            '_hy': hy}


class TextSelectTool(QgsMapTool):
    def __init__(self, iface, mgr):
        canvas = iface.mapCanvas()
        super().__init__(canvas)
        self.iface = iface
        self.mgr = mgr
        self.canvas_ = canvas
        self.setCursor(qt('CursorShape', 'ArrowCursor'))
        self.box = QgsRubberBand(canvas, polygon_geometry_type())
        self.box.setStrokeColor(QColor(30, 144, 255))
        self.box.setFillColor(QColor(30, 144, 255, 25))
        self.box.setWidth(1)
        self.hover = QgsRubberBand(canvas, polygon_geometry_type())
        self.hover.setStrokeColor(QColor(30, 144, 255, 150))
        self.hover.setFillColor(QColor(0, 0, 0, 0))
        self.hover.setLineStyle(qt('PenStyle', 'DashLine'))
        self.markers = {}
        for key, icon, color in (('move', 'ICON_BOX', QColor(30, 110, 255)),
                                 ('rot', 'ICON_CIRCLE', QColor(0, 190, 90)),
                                 ('height', 'ICON_TRIANGLE', QColor(255, 140, 0))):
            m = QgsVertexMarker(canvas)
            m.setIconType(_icon(icon))
            m.setColor(color)
            try:
                m.setFillColor(color)
            except AttributeError:
                pass
            m.setIconSize(GRIP_PX + 2)
            m.setPenWidth(2)
            m.hide()
            self.markers[key] = m
        self.preview = TextPreview(canvas)
        self.sel = None
        self.drag = None
        self.editor = None

    # ------------------------------------------------------------ datos
    def _text_layers(self):
        return [l for l in self.canvas_.layers() if is_text_layer(l)]

    def _info(self, lyr, f, io):
        g = io.to_canvas(f.geometry())
        p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
        return {'layer': lyr, 'fid': f.id(), 'io': io, 'anchor': QgsPointXY(p),
                'text': str(f['TEXTO'] if f['TEXTO'] is not None else ''),
                'font': str(f['FUENTE'] or 'Arial'), 'height': _num(f['ALTURA'], 2.5),
                'rot': math.radians(_num(f['ROTACION'], 0.0)), 'bold': _num(f['NEGRITA'], 0) == 1,
                'just': str(f['JUST'] or 'I')}

    def text_at(self, p):
        best, best_area = None, None
        ext = self.canvas_.extent()
        for lyr in self._text_layers():
            io = GeomIO(self.canvas_, lyr)
            req = QgsFeatureRequest().setFilterRect(io.rect_to_layer(ext))
            req.setLimit(5000)
            for f in lyr.getFeatures(req):
                if not f.hasGeometry():
                    continue
                info = self._info(lyr, f, io)
                x0, x1, y0, y1, b, cap = text_metrics(info)
                lx, ly = to_local(info, p)
                pad = cap * 0.15
                if x0 - pad <= lx <= x1 + pad and y0 - pad <= ly <= y1 + pad:
                    area = (x1 - x0) * (y1 - y0)
                    if best_area is None or area < best_area:
                        best, best_area = info, area
        return best

    def _refresh_sel(self):
        if self.sel is None:
            return
        lyr, fid = self.sel['layer'], self.sel['fid']
        f = lyr.getFeature(fid)
        if not f.isValid():
            self.select(None)
            return
        self.sel = self._info(lyr, f, self.sel['io'])
        self._draw(self.sel)

    # ------------------------------------------------------------ dibujo
    def _set_poly(self, rb, pts):
        if pts:
            rb.setToGeometry(QgsGeometry.fromPolygonXY([pts + [pts[0]]]), QgsCoordinateReferenceSystem())
        else:
            rb.reset(polygon_geometry_type())

    def _draw(self, info):
        if info is None:
            self._set_poly(self.box, None)
            for m in self.markers.values():
                m.hide()
            return
        self._set_poly(self.box, text_box(info))
        gp = grips(info)
        for k, m in self.markers.items():
            m.setCenter(gp[k])
            m.show()

    def select(self, info):
        if self.sel is not None and (info is None or self.sel['layer'] is not info['layer']):
            self.sel['layer'].removeSelection()
        self.sel = info
        self._draw(info)
        if info is not None:
            info['layer'].selectByIds([info['fid']])
            self.mgr.cmdline.set_info('Texto: "%s"  Altura: %.4g  Rotación: %.4g°'
                                      % (info['text'], info['height'], math.degrees(info['rot']) % 360))

    # ------------------------------------------------------------ eventos
    def _grip_at(self, p):
        if self.sel is None:
            return None
        mupp = self.canvas_.mapUnitsPerPixel() or 1.0
        gp = grips(self.sel)
        for k in ('move', 'rot', 'height'):
            q = gp[k]
            if math.hypot(q.x() - p.x(), q.y() - p.y()) / mupp <= GRIP_PX:
                return k
        return None

    def _shift(self, ev):
        return bool(ev.modifiers() & qt('KeyboardModifier', 'ShiftModifier'))

    def canvasPressEvent(self, ev):
        if ev.button() == qt('MouseButton', 'RightButton'):
            if self.drag is None and self.editor is None:
                self.mgr.enter()        # clic derecho = Intro: repite el último comando
            return
        if ev.button() != qt('MouseButton', 'LeftButton'):
            return
        self._close_editor(commit=True)
        p = ev.mapPoint()
        grip = self._grip_at(p)
        if grip is None and self.sel is not None:
            x0, x1, y0, y1, b, cap = text_metrics(self.sel)
            lx, ly = to_local(self.sel, p)
            if x0 <= lx <= x1 and y0 <= ly <= y1:
                grip = 'body'
        if grip is not None:
            s = self.sel
            self.drag = {'mode': grip, 'press': p, 'anchor0': QgsPointXY(s['anchor']), 'rot0': s['rot'],
                         'h0': s['height'], 'a_press': math.atan2(p.y() - s['anchor'].y(), p.x() - s['anchor'].x()),
                         'proj0': None, 'info': dict(s)}
            if grip == 'height':
                hy = grips(s)['_hy']
                self.drag['proj0'] = hy if abs(hy) > 1e-12 else None
            return
        self.select(self.text_at(p))

    def canvasMoveEvent(self, ev):
        p = ev.mapPoint()
        if self.drag is None:
            info = self.text_at(p)
            self._set_poly(self.hover, text_box(info) if info is not None and
                           (self.sel is None or info['fid'] != self.sel['fid'] or info['layer'] is not self.sel['layer'])
                           else None)
            g = self._grip_at(p)
            self.setCursor(qt('CursorShape', 'SizeAllCursor' if g in ('move', 'body') else
                              'CrossCursor' if g in ('rot', 'height') else 'ArrowCursor'))
            return
        info = self._dragged(p, self._shift(ev))
        self._draw(info)
        self.preview.set(info['anchor'], info['text'], info['height'], info['rot'],
                         info['font'], info['bold'], info['just'])
        self.mgr.cmdline.set_info('Altura: %.4g   Rotación: %.4g°   %s'
                                  % (info['height'], math.degrees(info['rot']) % 360,
                                     '[ORTO]' if self.mgr.ortho != self._shift(ev) else ''))

    def _dragged(self, p, shift):
        d = self.drag
        info = dict(d['info'])
        ortho = self.mgr.ortho != shift
        mode = d['mode']
        if mode in ('move', 'body'):
            target = p
            if mode == 'move':
                m = self.canvas_.snappingUtils().snapToMap(p)
                if m.isValid():
                    info['anchor'] = QgsPointXY(m.point())
                    return info
            dx, dy = target.x() - d['press'].x(), target.y() - d['press'].y()
            if ortho:
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0
            info['anchor'] = QgsPointXY(d['anchor0'].x() + dx, d['anchor0'].y() + dy)
        elif mode == 'rot':
            a = math.atan2(p.y() - d['anchor0'].y(), p.x() - d['anchor0'].x())
            r = d['rot0'] + (a - d['a_press'])
            if ortho:
                step = math.radians(15)
                r = round(r / step) * step
            info['rot'] = r % (2 * math.pi)
        elif mode == 'height' and d['proj0']:
            lx, ly = to_local(d['info'], p)
            info['height'] = max(1e-6, d['h0'] * ly / d['proj0'])
        return info

    def canvasReleaseEvent(self, ev):
        if self.drag is None:
            return
        info = self._dragged(ev.mapPoint(), self._shift(ev))
        d, self.drag = self.drag, None
        self.preview.clear()
        moved = (info['anchor'].x() != d['anchor0'].x() or info['anchor'].y() != d['anchor0'].y())
        if d['mode'] in ('move', 'body') and moved:
            self._commit(info, geometry=True)
        elif d['mode'] == 'rot' and abs(info['rot'] - d['rot0']) > 1e-12:
            self._commit(info, attrs={'ROTACION': round(math.degrees(info['rot']) % 360.0, 8)})
        elif d['mode'] == 'height' and abs(info['height'] - d['h0']) > 1e-12:
            self._commit(info, attrs={'ALTURA': info['height']})
            self.mgr.text_style.height = info['height']
        self._refresh_sel()

    def canvasDoubleClickEvent(self, ev):
        info = self.text_at(ev.mapPoint())
        if info is None:
            return
        self.select(info)
        self._open_editor(info)

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == qt('Key', 'Key_Delete') and self.sel is not None:
            lyr = self.sel['layer']
            self._ensure_edit(lyr)
            lyr.beginEditCommand('Borrar texto')
            lyr.deleteFeature(self.sel['fid'])
            lyr.endEditCommand()
            lyr.triggerRepaint()
            self.select(None)
            ev.accept()
            return
        if key == qt('Key', 'Key_Escape'):
            if self.drag is not None:
                self.drag = None
                self.preview.clear()
                self._draw(self.sel)
            else:
                self.select(None)
            ev.accept()
            return
        if key in (qt('Key', 'Key_F2'), qt('Key', 'Key_Return'), qt('Key', 'Key_Enter')) and self.sel is not None:
            self._open_editor(self.sel)
            ev.accept()
            return
        if self.mgr.cmdline.feed_key(ev):
            ev.accept()
            return
        ev.ignore()

    # ------------------------------------------------------------ escritura
    def _ensure_edit(self, lyr):
        if not lyr.isEditable():
            lyr.startEditing()

    def _commit(self, info, geometry=False, attrs=None):
        lyr = info['layer']
        self._ensure_edit(lyr)
        lyr.beginEditCommand('Modificar texto')
        if geometry:
            g = conform(QgsGeometry.fromPointXY(info['io'].point_to_layer(info['anchor'])), lyr)
            lyr.changeGeometry(info['fid'], g)
        for name, v in (attrs or {}).items():
            idx = lyr.fields().indexOf(name)
            if idx != -1:
                lyr.changeAttributeValue(info['fid'], idx, v)
        lyr.endEditCommand()
        lyr.triggerRepaint()

    # ------------------------------------------------------------ edición en el lugar
    def _open_editor(self, info):
        self._close_editor(commit=False)
        vp = self.canvas_.viewport()
        px = self.canvas_.getCoordinateTransform().transform(info['anchor'])
        mupp = self.canvas_.mapUnitsPerPixel() or 1.0
        fpx = int(max(11, min(info['height'] * CAP_FACTOR / mupp, 64)))
        ed = QLineEdit(vp)
        f = QFont(info['font'])
        f.setPixelSize(fpx)
        f.setBold(info['bold'])
        ed.setFont(f)
        ed.setText(info['text'])
        ed.setStyleSheet('QLineEdit { background: rgba(255,255,255,235); color: black; '
                         'border: 1px solid #1e90ff; padding: 1px 3px; }')
        fm = QFontMetricsF(f)
        w = (fm.horizontalAdvance(info['text'] + 'MM') if hasattr(fm, 'horizontalAdvance')
             else fm.width(info['text'] + 'MM'))
        ed.resize(int(max(160, w + 20)), fpx + 10)
        h, v = JUST.get(info['just'], ('Left', 'Base'))
        x = int(px.x()) - {'Left': 0, 'Center': ed.width() // 2, 'Right': ed.width()}[h]
        ed.move(max(0, x), max(0, int(px.y()) - fpx - 4))
        ed.installEventFilter(self)
        ed.returnPressed.connect(lambda: self._close_editor(commit=True))
        self.editor = (ed, info)
        ed.show()
        ed.setFocus()
        ed.selectAll()
        self.mgr.cmdline.set_info('Editando texto: Intro para aceptar, Esc para cancelar')

    def _close_editor(self, commit=True):
        if self.editor is None:
            return
        ed, info = self.editor
        self.editor = None
        new = ed.text()
        ed.hide()
        ed.deleteLater()
        if commit and new != info['text']:
            self._commit(info, attrs={'TEXTO': new})
            self._refresh_sel()
        self.canvas_.setFocus()

    def eventFilter(self, obj, ev):
        if self.editor is not None and obj is self.editor[0]:
            t = ev.type()
            if t == enum(QEvent, 'Type', 'KeyPress') and ev.key() == qt('Key', 'Key_Escape'):
                self._close_editor(commit=False)
                return True
            if t == enum(QEvent, 'Type', 'FocusOut'):
                self._close_editor(commit=True)
                return False
        return False

    # ------------------------------------------------------------ ciclo de vida
    def activate(self):
        super().activate()
        self.canvas_.setFocus()
        self.mgr.cmdline.echo('Seleccionar texto: clic = seleccionar, arrastrar ■ mover, ● girar, '
                              '▲ altura, doble clic = editar, Supr = borrar, Esc = deseleccionar.')

    def deactivate(self):
        self._close_editor(commit=True)
        self.drag = None
        self.preview.clear()
        self._set_poly(self.hover, None)
        if self.sel is not None:
            self.sel['layer'].removeSelection()
        self.sel = None
        self._draw(None)
        self.mgr.cmdline.set_info('')
        super().deactivate()

    def remove_items(self):
        scene = self.canvas_.scene()
        for item in [self.box, self.hover, self.preview] + list(self.markers.values()):
            try:
                scene.removeItem(item)
            except Exception:  # noqa: BLE001
                pass
