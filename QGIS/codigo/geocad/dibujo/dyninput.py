# -*- coding: utf-8 -*-
"""Entrada dinámica (F12, como DYNMODE de AutoCAD).

Junto al cursor se ve la solicitud del comando en curso, lo que se está escribiendo
y la información de la barra (longitud, ángulo). Lo escrito sigue yendo a la línea
de comandos: es la misma entrada, vista también al lado del cursor.
"""

import html

from qgis.PyQt.QtCore import QEvent, QObject, QPoint
from qgis.PyQt.QtWidgets import QLabel

from .compat import enum, qt
from .settings import get_setting, set_setting

STYLE = ('QLabel { background: rgba(255, 255, 255, 235); color: #1a1a1a; border: 1px solid #8a8a8a; '
         'padding: 2px 5px; font-family: Consolas, monospace; }')


class DynamicInput(QObject):
    def __init__(self, canvas, cmdline, mgr):
        super().__init__()
        self.canvas = canvas
        self.cl = cmdline
        self.mgr = mgr
        self.on = get_setting('dyn_input', True, bool)
        self.pos = None
        self.label = QLabel(canvas.viewport())
        self.label.setStyleSheet(STYLE)
        self.label.setTextFormat(qt('TextFormat', 'RichText'))
        try:
            self.label.setAttribute(qt('WidgetAttribute', 'WA_TransparentForMouseEvents'), True)
        except Exception:  # noqa: BLE001
            pass
        self.label.hide()
        self._ev_move = enum(QEvent, 'Type', 'MouseMove')
        self._ev_leave = enum(QEvent, 'Type', 'Leave')
        canvas.viewport().installEventFilter(self)
        cmdline.input.textChanged.connect(self.update)
        cmdline.promptChanged.connect(self.update)
        cmdline.dynToggled.connect(self.toggle)

    def unload(self):
        try:
            self.canvas.viewport().removeEventFilter(self)
        except RuntimeError:
            pass
        for sig, slot in ((self.cl.input.textChanged, self.update), (self.cl.promptChanged, self.update),
                          (self.cl.dynToggled, self.toggle)):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            self.label.deleteLater()
        except RuntimeError:
            pass

    def toggle(self):
        self.on = not self.on
        set_setting('dyn_input', self.on)
        self.cl.echo('<Entrada dinámica %s>' % ('activada' if self.on else 'desactivada'))
        self.update()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == self._ev_move:
            try:
                p = ev.position().toPoint() if hasattr(ev, 'position') else ev.pos()
            except Exception:  # noqa: BLE001
                p = None
            self.pos = p
            self.update()
        elif t == self._ev_leave:
            self.pos = None
            self.label.hide()
        return False

    def _active(self):
        """Solo con una herramienta de Dibujo CAD en el mapa (comando en curso o reposo CAD)."""
        try:
            return self.canvas.mapTool() is self.mgr.tool
        except Exception:  # noqa: BLE001
            return False

    def update(self, *args):
        typed = self.cl.input.text()
        busy = self.mgr.command is not None
        if not self.on or self.pos is None or not self._active() or (not busy and not typed):
            self.label.hide()
            return
        prompt = self.cl.prompt.text()          # texto enriquecido (opciones como enlaces)
        if prompt.endswith(':'):
            prompt = prompt[:-1]
        if not busy:
            prompt = 'Comando'
        line = '%s: <b>%s</b>&#9612;' % (prompt, html.escape(typed))
        info = self.cl.info.text() if busy else ''
        if info:
            line += '<br><span style="color:#606060;">%s</span>' % html.escape(info)
        self.label.setText(line)
        self.label.adjustSize()
        vp = self.canvas.viewport()
        x, y = self.pos.x() + 18, self.pos.y() + 18
        if x + self.label.width() > vp.width():
            x = max(0, self.pos.x() - self.label.width() - 12)
        if y + self.label.height() > vp.height():
            y = max(0, self.pos.y() - self.label.height() - 12)
        self.label.move(QPoint(x, y))
        self.label.show()
        self.label.raise_()
