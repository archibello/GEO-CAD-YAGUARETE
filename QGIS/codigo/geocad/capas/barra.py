# -*- coding: utf-8 -*-
"""Barra de propiedades de IngeCAD en QGIS (3.60.0): Color, Tipo de línea y
Grosor de línea, al lado de la lista de capa (layer_combo.py).

La regla de IngeCAD (y de AutoCAD): con objetos seleccionados, la lista los
cambia; sin selección, elige con qué se dibuja el PRÓXIMO objeto ($CECOLOR,
$CELTYPE, $CELWEIGHT). Muestra el valor de la selección (en blanco si es
mixto) o el actual. Los valores van a los campos CAD_COLOR, CAD_LTYPE y
CAD_LW de Dibujo CAD (vacío = PorCapa); en las capas de textos, a COLOR.
PorBloque no se ofrece: en QGIS no hay de dónde heredarlo.
"""
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QComboBox

from .aci import aci_to_hex
from .compat import accepted_code, exec_dialog
from .dialogs import ColorDialog, LinetypeDialog
from .icons import color_swatch, linetype_sample, lineweight_sample
from .linetypes import LINETYPE_ORDER, LINEWEIGHTS, LW_DEFAULT

ACI_NAMES = {1: 'Rojo', 2: 'Amarillo', 3: 'Verde', 4: 'Cian', 5: 'Azul',
             6: 'Magenta', 7: 'Blanco', 8: 'Gris', 9: 'Gris claro'}
PICK, OTHER = '__elegir__', '__otro__'
BYLAYER = None
_MIXED = object()


def aci_hex(aci):
    """El valor de CAD_COLOR de un color ACI (el 7 se guarda negro: blanco o negro según el fondo)."""
    return '#000000' if int(aci) == 7 else aci_to_hex(aci)


def color_label(value):
    if value is None:
        return 'PorCapa'
    for aci, name in ACI_NAMES.items():
        if aci_hex(aci) == str(value).lower():
            return name
    return str(value)


def lineweight_label(value):
    if value is None:
        return 'PorCapa'
    if value < 0:
        return 'Por defecto'
    return '%.2f mm' % value


class _PropCombo(QComboBox):
    prop = ''
    tip = ''

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setToolTip(self.tip)
        self.setMaxVisibleItems(16)
        self.setIconSize(QSize(40, 12))
        self._loading = False
        self._fill()
        self.activated.connect(self._activated)
        ctrl.changed.connect(self.refresh)
        ctrl.attachedChanged.connect(self.refresh)
        ctrl.selectionChanged.connect(self.refresh)
        self.refresh()

    def _fill(self):
        raise NotImplementedError

    def _value_at(self, index):
        data = self.itemData(index)
        return None if data == '' else data

    def _find(self, value):
        for i in range(self.count()):
            if self.itemData(i) in (PICK, OTHER):
                continue
            v = self._value_at(i)
            if v == value or (isinstance(v, float) and isinstance(value, float)
                              and abs(v - value) < 1e-6):
                return i
        return -1

    def refresh(self, *args):
        self._loading = True
        try:
            self.setEnabled(self.ctrl.active)
            if not self.ctrl.active:
                self.setCurrentIndex(-1)
                return
            if self.ctrl.has_selection():
                value = self.ctrl.selection_prop(self.prop)
                if value is False:          # mixto: en blanco, como AutoCAD
                    self.setCurrentIndex(-1)
                    return
            else:
                value = self.ctrl.current_prop(self.prop)
            index = self._find(value)
            if index < 0 and value is not None:
                index = self._add(value)
            self.setCurrentIndex(index)
        finally:
            self._loading = False

    def _add(self, value):
        return -1

    def _ask(self, data):
        """Seleccionar color... / Otro...: el valor elegido o _MIXED si se canceló."""
        return _MIXED

    def _activated(self, index):
        if self._loading:
            return
        data = self.itemData(index)
        if data in (PICK, OTHER):
            value = self._ask(data)
            if value is _MIXED:
                self.refresh()
                return
            found = self._find(value)
            if found < 0:
                self._add(value)
        else:
            value = self._value_at(index)
        self.apply(value)

    def apply(self, value):
        """Con selección la cambia; sin selección, es lo actual para lo próximo."""
        if not self.ctrl.active:
            return
        if self.ctrl.has_selection():
            self.ctrl.set_selection_prop(self.prop, value)
            self.ctrl.clear_selection()          # que se vea el resultado (3.60.1)
        else:
            self.ctrl.set_current_prop(self.prop, value)
            from .panel import echo
            echo(self.ctrl, '%s actual: %s' % (self.tip, self.label(value)))
        self.refresh()

    def label(self, value):
        return str(value)


class ColorCombo(_PropCombo):
    prop = 'color'
    tip = 'Color'

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, parent)
        self.setFixedWidth(110)

    def _fill(self):
        self.addItem('PorCapa', '')
        for aci, name in ACI_NAMES.items():
            self.addItem(QIcon(color_swatch(aci_to_hex(aci), 12, 12)), name, aci_hex(aci))
        self.addItem('Seleccionar color...', PICK)

    def _add(self, value):
        at = self.count() - 1                       # antes de «Seleccionar color...»
        self.insertItem(at, QIcon(color_swatch(value, 12, 12)), color_label(value), value)
        return at

    def _ask(self, data):
        current = self.ctrl.current_prop('color') or '#ffffff'
        dlg = ColorDialog(self.window(), {'aci': None, 'rgb': current})
        if exec_dialog(dlg) != accepted_code():
            return _MIXED
        c = dlg.color
        return aci_hex(c['aci']) if c.get('aci') else (c.get('rgb') or '#000000').lower()

    def label(self, value):
        return color_label(value)


class LinetypeCombo(_PropCombo):
    prop = 'linetype'
    tip = 'Tipo de línea'

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, parent)
        self.setFixedWidth(150)

    def _fill(self):
        fg = self.palette().text().color().name()
        self.addItem(QIcon(linetype_sample('Continuous', 40, 12, fg)), 'PorCapa', '')
        for name in LINETYPE_ORDER:
            self.addItem(QIcon(linetype_sample(name, 40, 12, fg)), name, name)
        self.addItem('Otro...', OTHER)

    def _ask(self, data):
        dlg = LinetypeDialog(self.window(), self.ctrl.current_prop('linetype') or 'Continuous')
        if exec_dialog(dlg) != accepted_code() or not dlg.value():
            return _MIXED
        return dlg.value()

    def label(self, value):
        return 'PorCapa' if value is None else value


class LineweightCombo(_PropCombo):
    prop = 'lineweight'
    tip = 'Grosor de línea'

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, parent)
        self.setFixedWidth(130)

    def _fill(self):
        fg = self.palette().text().color().name()
        self.addItem(QIcon(lineweight_sample(0.25, 40, 12, fg)), 'PorCapa', '')
        for lw in [float(LW_DEFAULT)] + LINEWEIGHTS:
            self.addItem(QIcon(lineweight_sample(0.25 if lw < 0 else lw, 40, 12, fg)),
                         lineweight_label(lw), float(lw))

    def label(self, value):
        return lineweight_label(value)
