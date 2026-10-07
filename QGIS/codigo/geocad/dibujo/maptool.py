# -*- coding: utf-8 -*-
"""Herramienta de mapa compartida por los comandos de dibujo."""

import math

from qgis.PyQt.QtCore import QEvent, QObject
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsCoordinateReferenceSystem, QgsGeometry, QgsPointLocator,
                       QgsSettings, QgsTolerance)
from qgis.gui import QgsMapTool, QgsRubberBand, QgsSnapIndicator, QgsVertexMarker

from .compat import enum, line_geometry_type, point_geometry_type, qt


def _digitizing_color():
    s = QgsSettings()
    try:
        r = int(s.value('qgis/digitizing/line_color_red', 255))
        g = int(s.value('qgis/digitizing/line_color_green', 0))
        b = int(s.value('qgis/digitizing/line_color_blue', 0))
        return QColor(r, g, b)
    except (TypeError, ValueError):
        return QColor(255, 0, 0)


def _band(canvas, color, width, style=None, vertices=False):
    rb = QgsRubberBand(canvas, line_geometry_type())
    rb.setColor(color)
    rb.setWidth(width)
    if style is not None:
        rb.setLineStyle(qt('PenStyle', style))
    if vertices:
        try:
            rb.setIcon(enum(QgsRubberBand, 'IconType', 'ICON_BOX'))
            rb.setIconSize(6)
        except Exception:
            pass
    return rb


class CadMapTool(QgsMapTool):
    def __init__(self, canvas, manager):
        super().__init__(canvas)
        self.canvas_ = canvas
        self.mgr = manager
        self.snap = QgsSnapIndicator(canvas)
        self.setCursor(qt('CursorShape', 'CrossCursor'))
        color = _digitizing_color()
        tc = QColor(color)
        tc.setAlpha(210)
        self.rb_path = _band(canvas, color, 2, vertices=True)          # tramos confirmados
        self.rb_temp = _band(canvas, tc, 1, 'DashLine')                 # tramo elástico
        self.rb_guide = _band(canvas, QColor(80, 160, 255, 170), 1, 'DotLine')
        gc = QColor(color)
        gc.setAlpha(150)
        self.rb_ghost = _band(canvas, gc, 1, 'DashLine')                 # objetos en movimiento
        self.rb_ghost_pts = QgsRubberBand(canvas, point_geometry_type())
        self.rb_ghost_pts.setColor(gc)
        self.rb_ghost_pts.setIconSize(6)
        self.own_marker = QgsVertexMarker(canvas)                       # referencia sobre el dibujo en curso
        self.own_marker.setIconType(enum(QgsVertexMarker, 'IconType', 'ICON_BOX'))
        self.own_marker.setColor(QColor(255, 0, 255))
        self.own_marker.setIconSize(12)
        self.own_marker.setPenWidth(2)
        self.own_marker.hide()

    # ------------------------------------------------------------ dibujo temporal
    @staticmethod
    def _set(rb, pts):
        pts = [p for p in pts if p is not None]
        if len(pts) >= 2:
            rb.setToGeometry(QgsGeometry.fromPolylineXY(pts), QgsCoordinateReferenceSystem())
        else:
            rb.reset(line_geometry_type())

    def show_path(self, pts, closed=False):
        pts = list(pts)
        if closed and len(pts) > 2:
            pts.append(pts[0])
        if len(pts) == 1:
            # primer clic: se marca el punto inicial
            self.rb_path.reset(line_geometry_type())
            self.rb_path.addPoint(pts[0], True)
            return
        self._set(self.rb_path, pts)

    def show_temp(self, pts):
        self._set(self.rb_temp, pts)

    def show_guide(self, pts):
        self._set(self.rb_guide, pts)

    def show_ghost(self, geoms):
        """Vista fantasma de los objetos transformados (SRC del mapa)."""
        lines, points = [], []
        for g in geoms or []:
            if g is None or g.isEmpty():
                continue
            gt = g.type()
            if gt == point_geometry_type():
                points.append(g)
            elif gt == line_geometry_type():
                lines.append(g)
            else:
                lines.append(QgsGeometry(g.constGet().boundary()))
        crs = QgsCoordinateReferenceSystem()
        if lines:
            self.rb_ghost.setToGeometry(QgsGeometry.collectGeometry(lines), crs)
        else:
            self.rb_ghost.reset(line_geometry_type())
        if points:
            self.rb_ghost_pts.setToGeometry(QgsGeometry.collectGeometry(points), crs)
        else:
            self.rb_ghost_pts.reset(point_geometry_type())

    def clear(self):
        self.show_ghost(None)
        for rb in (self.rb_path, self.rb_temp, self.rb_guide):
            rb.reset(line_geometry_type())
        self.snap.setMatch(QgsPointLocator.Match())
        self.own_marker.hide()

    def remove_items(self):
        scene = self.canvas_.scene()
        for item in (self.rb_path, self.rb_temp, self.rb_guide, self.rb_ghost,
                     self.rb_ghost_pts, self.own_marker):
            try:
                scene.removeItem(item)
            except Exception:
                pass

    # ------------------------------------------------------------ referencia a objetos
    def _own_snap(self, pt):
        """Referencia a los vértices del dibujo en curso (aún no están en la capa)."""
        if not self.mgr.osnap_enabled():
            return None, None
        pts = self.mgr.command.snap_points() if self.mgr.command is not None else []
        tol = QgsTolerance.vertexSearchRadius(self.canvas_.mapSettings())
        try:
            from .blocks import snap_candidates
            pts = list(pts) + snap_candidates(self.canvas_, pt, tol)   # extremos y medios de bloques
        except Exception:  # noqa: BLE001
            pass
        if not pts:
            return None, None
        best, best_d = None, None
        for p in pts:
            d = math.hypot(p.x() - pt.x(), p.y() - pt.y())
            if d <= tol and (best_d is None or d < best_d):
                best, best_d = p, d
        return best, best_d

    def _snapped(self, ev):
        raw = ev.mapPoint()
        match = self.canvas_.snappingUtils().snapToMap(raw)
        own, own_d = self._own_snap(raw)
        if own is not None and (not match.isValid() or own_d <= match.distance()):
            self.snap.setMatch(QgsPointLocator.Match())
            self.own_marker.setCenter(own)
            self.own_marker.show()
            return own, True
        self.own_marker.hide()
        self.snap.setMatch(match)
        if match.isValid():
            return match.point(), True
        return raw, False

    def _shift(self, ev):
        return bool(ev.modifiers() & qt('KeyboardModifier', 'ShiftModifier'))

    # ------------------------------------------------------------ eventos
    def canvasMoveEvent(self, ev):
        pt, snapped = self._snapped(ev)
        self.mgr.mouse_moved(pt, snapped, self._shift(ev))

    def canvasReleaseEvent(self, ev):
        if ev.button() == qt('MouseButton', 'RightButton'):
            self.mgr.enter()  # clic derecho = Intro (como AutoCAD)
            return
        if ev.button() != qt('MouseButton', 'LeftButton'):
            return
        pt, snapped = self._snapped(ev)
        self.mgr.point_clicked(pt, snapped, self._shift(ev))

    def keyPressEvent(self, ev):
        if ev.key() == qt('Key', 'Key_Delete') and self.mgr.command is None:
            lyr = self.mgr.iface.activeLayer()
            if lyr is not None and hasattr(lyr, 'selectedFeatureCount') and lyr.selectedFeatureCount():
                self.mgr.cmdline.echo('Comando: BORRA')
                self.mgr.run('BORRA')       # Supr con objetos designados = BORRA (como AutoCAD)
                ev.accept()
                return
        if self.mgr.cmdline.feed_key(ev):
            ev.accept()
            return
        ev.ignore()

    def deactivate(self):
        self.clear()
        self.mgr.tool_deactivated()
        super().deactivate()

    def isEditTool(self):
        return True


# --------------------------------------------------------------------------
class KeyGuard(QObject):
    """
    Aísla el teclado mientras se usan las herramientas CAD.

    Qt consulta primero los atajos de la aplicación (ShortcutOverride) y el mapa
    procesa algunas teclas por su cuenta (Espacio = desplazar). Mientras una
    herramienta CAD está activa, este filtro reclama las teclas de escritura y
    las envía a la línea de comandos / al texto, sin disparar otros comandos.
    Ctrl/Alt + tecla y las flechas siguen funcionando para QGIS.
    """

    SPECIAL = ('Key_Space', 'Key_Return', 'Key_Enter', 'Key_Escape', 'Key_Backspace',
               'Key_Delete', 'Key_F2', 'Key_F3', 'Key_F8', 'Key_F12', 'Key_Tab')

    def __init__(self, canvas, mgr):
        super().__init__(canvas)
        self.canvas = canvas
        self.mgr = mgr
        self.tools = []
        self._special = {qt('Key', k) for k in self.SPECIAL}
        self._ev_press = enum(QEvent, 'Type', 'KeyPress')
        self._ev_override = enum(QEvent, 'Type', 'ShortcutOverride')
        canvas.installEventFilter(self)
        canvas.viewport().installEventFilter(self)

    def remove(self):
        for w in (self.canvas, self.canvas.viewport()):
            try:
                w.removeEventFilter(self)
            except (RuntimeError, TypeError):
                pass

    def _wanted(self, ev):
        mods = ev.modifiers()
        for m in ('ControlModifier', 'AltModifier', 'MetaModifier'):
            if mods & qt('KeyboardModifier', m):
                return False
        if ev.key() in self._special:
            return True
        txt = ev.text()
        return bool(txt) and txt.isprintable()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t != self._ev_press and t != self._ev_override:
            return False
        tool = self.canvas.mapTool()
        if tool is None or not any(tool is x for x in self.tools):
            return False
        if not self._wanted(ev):
            return False
        if t == self._ev_override:
            ev.accept()          # la tecla es nuestra: no se disparan atajos de QGIS
            return True
        ev.setAccepted(False)
        tool.keyPressEvent(ev)
        if not ev.isAccepted() and getattr(self.mgr, 'cmdline', None) is not None:
            if self.mgr.cmdline.feed_key(ev):
                ev.accept()
        return True              # el mapa no la procesa (Espacio no desplaza)
