# -*- coding: utf-8 -*-
"""Lista desplegable de capas de la barra 'Capas' de AutoCAD.

- Muestra la capa actual (o la de los objetos seleccionados).
- En la lista se puede pulsar la bombilla, el sol/copo y el candado sin cerrarla.
- Elegir una capa la define como actual; si hay objetos seleccionados,
  los mueve a esa capa (igual que en AutoCAD).
"""

from qgis.PyQt.QtCore import QEvent, QRect, QSize
from qgis.PyQt.QtGui import QColor, QIcon, QPen
from qgis.PyQt.QtWidgets import (QComboBox, QStyle, QStyledItemDelegate,
                                 QStyleOptionComboBox, QStylePainter)

from .compat import enum, qt
from .controller import dlog
from .icons import pixmap

ROLE = qt('ItemDataRole', 'UserRole')
_EV_PRESS = enum(QEvent, 'Type', 'MouseButtonPress')
_EV_RELEASE = enum(QEvent, 'Type', 'MouseButtonRelease')
_EV_DBL = enum(QEvent, 'Type', 'MouseButtonDblClick')
ZONES = (('on', 0), ('frozen', 20), ('locked', 40))
SWATCH_X = 62
NAME_X = 82


def _icons_for(lay):
    return [('bulb_on' if lay['on'] else 'bulb_off'),
            ('freeze' if lay['frozen'] else 'thaw'),
            ('lock_closed' if lay['locked'] else 'lock_open')]


def paint_layer(p, rect, lay, color, text_color):
    x, cy = rect.left() + 3, rect.center().y()
    for (key, dx), name in zip(ZONES, _icons_for(lay)):
        p.drawPixmap(x + dx, cy - 8, pixmap(name, 16))
    sw = QRect(x + SWATCH_X, cy - 6, 12, 12)
    p.fillRect(sw, color)
    p.setPen(QPen(QColor('#202020'), 1))
    p.drawRect(sw)
    p.setPen(text_color)
    tr = QRect(x + NAME_X, rect.top(), rect.width() - NAME_X - 6, rect.height())
    p.drawText(tr, qt('AlignmentFlag', 'AlignVCenter') | qt('AlignmentFlag', 'AlignLeft'), lay['name'])


class LayerItemDelegate(QStyledItemDelegate):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl

    def sizeHint(self, option, index):
        return QSize(max(option.rect.width(), 220), 22)

    def paint(self, p, option, index):
        lay = self.ctrl.find(index.data(ROLE), True)
        if lay is None:
            return super().paint(p, option, index)
        st = option.state
        selected = bool(st & enum(QStyle, 'StateFlag', 'State_Selected')) or \
            bool(st & enum(QStyle, 'StateFlag', 'State_MouseOver'))
        pal = option.palette
        if selected:
            p.fillRect(option.rect, pal.highlight())
            tc = pal.highlightedText().color()
        else:
            p.fillRect(option.rect, pal.base())
            tc = pal.text().color()
        p.save()
        if lay['name'] == self.ctrl.current:
            f = p.font()
            f.setBold(True)
            p.setFont(f)
        paint_layer(p, option.rect, lay, self.ctrl.preview_color(lay), tc)
        p.restore()


class LayerCombo(QComboBox):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setMinimumWidth(260)
        self.setMaxVisibleItems(25)
        self.setToolTip('Control de capas: capa actual o capa de los objetos seleccionados.\n'
                        'Pulse la bombilla, el sol o el candado para cambiar el estado sin cerrar la lista.')
        self.setItemDelegate(LayerItemDelegate(ctrl, self))
        self._names = []
        self.view().viewport().installEventFilter(self)
        self.view().setMouseTracking(True)
        self.activated.connect(self._activated)
        ctrl.changed.connect(self.refresh)
        ctrl.attachedChanged.connect(self.refresh)
        ctrl.selectionChanged.connect(self.refresh)
        self._display = None
        self._pressed_in_view = False
        self.refresh()

    # ------------------------------------------------------------ datos
    def refresh(self):
        names = self.ctrl.names()
        self.setEnabled(self.ctrl.active)
        if names != self._names:
            self.blockSignals(True)
            self.clear()
            for i, n in enumerate(names):
                self.addItem(n)
                self.setItemData(i, n, ROLE)
            self._names = list(names)
            self.blockSignals(False)
        self._display = self._compute_display()
        self._sync_index()
        self.view().viewport().update()
        self.update()

    def _sync_index(self):
        shown = self.display_name()
        self.blockSignals(True)
        self.setCurrentIndex(self._names.index(shown) if shown in self._names else -1)
        self.blockSignals(False)

    def display_name(self):
        return self._display

    def _compute_display(self):
        """Capa a mostrar: la de la selección (si es única) o la actual."""
        if not self.ctrl.active:
            return None
        sel = self.ctrl.selected_layer_names(limit=5000)
        if sel is None:
            return self.ctrl.current
        return next(iter(sel)) if len(sel) == 1 else ''

    def showPopup(self):
        self._pressed_in_view = False
        self.ctrl.refresh()
        self._sync_index()
        super().showPopup()

    # ------------------------------------------------------------ pintado
    def paintEvent(self, ev):
        p = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ''
        opt.currentIcon = QIcon()
        p.drawComplexControl(enum(QStyle, 'ComplexControl', 'CC_ComboBox'), opt)
        rect = self.style().subControlRect(enum(QStyle, 'ComplexControl', 'CC_ComboBox'), opt,
                                           enum(QStyle, 'SubControl', 'SC_ComboBoxEditField'), self)
        name = self.display_name()
        tc = self.palette().text().color()
        if name is None:
            p.setPen(self.palette().placeholderText().color() if hasattr(self.palette(), 'placeholderText') else tc)
            p.drawText(rect.adjusted(4, 0, 0, 0), qt('AlignmentFlag', 'AlignVCenter'),
                       'Sin capa vectorial activa')
            return
        lay = self.ctrl.find(name, True) if name else None
        if lay is None:
            return  # selección en varias capas: casilla en blanco (como AutoCAD)
        paint_layer(p, rect.adjusted(-1, 0, 0, 0), lay, self.ctrl.preview_color(lay), tc)

    # ------------------------------------------------------------ eventos
    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.view().viewport() and t in (_EV_PRESS, _EV_RELEASE, _EV_DBL):
            pos = ev.position().toPoint() if hasattr(ev, 'position') else ev.pos()
            idx = self.view().indexAt(pos)
            if idx.isValid():
                x = pos.x() - self.view().visualRect(idx).left() - 3
                for key, dx in ZONES:
                    if dx - 2 <= x < dx + 18:
                        if t == _EV_RELEASE:
                            self._toggle(idx.data(ROLE), key)
                        return True
                if t == _EV_RELEASE and self._pressed_in_view:
                    self._pressed_in_view = False
                    # Clic sobre el nombre: se elige la capa directamente (sin depender de
                    # la señal 'activated' de Qt, que no siempre llega con la lista personalizada)
                    name = idx.data(ROLE)
                    dlog('lista: clic en "%s"' % name)
                    self.hidePopup()
                    self._choose(name)
                    return True
                if t == _EV_PRESS:
                    self._pressed_in_view = True    # la liberación del clic que abrió la lista no cuenta
                    return True
        return super().eventFilter(obj, ev)

    def _toggle(self, name, key):
        self.ctrl.toggle([name], key)
        self.view().viewport().update()

    def _activated(self, i):
        # elección con el teclado (flechas + Intro)
        self._choose(self.itemData(i, ROLE))

    def _choose(self, name):
        if not name:
            return
        dlog('lista: elegir "%s" (selección=%s)' % (name, self.ctrl.has_selection()))
        if self.ctrl.has_selection():
            self.ctrl.assign_selection(name)     # objetos seleccionados -> capa elegida
        else:
            self.ctrl.set_current(name)
        self.refresh()
