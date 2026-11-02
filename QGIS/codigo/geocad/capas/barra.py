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
from qgis.PyQt.QtCore import QRect, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QStyle, QStyleOptionViewItem

from .aci import aci_to_hex
from .compat import accepted_code, enum, exec_dialog, qt
from .dialogs import ColorDialog, LinetypeDialog
from .icons import color_swatch, linetype_sample, lineweight_sample
from .linetypes import LINETYPE_ORDER, LINEWEIGHTS, LW_DEFAULT
from .medidas import FilaDelegate, ajustar_desplegable, ancho_casilla, preparar_lista

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
    ancho = 0           # el de la barra de IngeCAD 0.7.0
    entero = False      # True: casilla y desplegable a la medida del texto (sólo Grosor)
    muestra = (40, 12)  # la muestra de cada renglón (la de tipo de línea necesita el largo)

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setToolTip(self.tip)
        self.setMaxVisibleItems(16)
        self.setIconSize(QSize(*self.muestra))
        self._loading = False
        # la letra y las filas del panel Yaguá Capas (3.61.2, Fernando: «Po…pa», «0…m»)
        preparar_lista(self)
        self._fill()
        if self.entero:
            textos = [self.itemText(i) for i in range(self.count()) if self.itemData(i) not in (PICK, OTHER)]
            self.setFixedWidth(ancho_casilla(self, textos, minimo=self.ancho))
        else:
            self.setFixedWidth(self.ancho)   # Fernando: «el resto puede estar más justo»
        self.activated.connect(self._activated)
        ctrl.changed.connect(self.refresh)
        ctrl.attachedChanged.connect(self.refresh)
        ctrl.selectionChanged.connect(self.refresh)
        self.refresh()

    def _fill(self):
        raise NotImplementedError

    def showPopup(self):
        if self.entero:
            ajustar_desplegable(self)
        super().showPopup()

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
    ancho = 96
    muestra = (12, 12)

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
    ancho = 128

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


class GrosorDelegate(FilaDelegate):
    """Cada fila del desplegable de Grosor con su número ENTERO; si no entra todo, se
    recorta la muestra de la línea, nunca el número (Fernando, 02/11/2026: «lo
    importante es que se vean los números para elegir los espesores de líneas»)."""

    MARGEN, ENTRE = 4, 6

    def __init__(self, muestra, parent=None):
        super().__init__(parent)
        self.muestra = muestra

    def partes(self, rect, fm, texto):
        """(ancho de la muestra, lugar del número) dentro de la fila."""
        tw = fm.horizontalAdvance(texto)
        libre = rect.width() - 2 * self.MARGEN - tw - self.ENTRE
        mw = max(0, min(self.muestra[0], libre))
        x = rect.left() + self.MARGEN + (mw + self.ENTRE if mw else 0)
        return mw, QRect(x, rect.top(), max(tw, rect.right() - x), rect.height())

    def paint(self, p, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        texto, ico = opt.text, QIcon(opt.icon)       # copia: opt.icon es una referencia
        opt.text, opt.icon = '', QIcon()
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(enum(QStyle, 'ControlElement', 'CE_ItemViewItem'), opt, p, opt.widget)
        mw, lugar = self.partes(opt.rect, opt.fontMetrics, texto)
        p.save()
        if mw and not ico.isNull():
            w, h = self.muestra
            pm = ico.pixmap(QSize(w, h))
            r = pm.devicePixelRatio()
            y = opt.rect.center().y() - h // 2
            p.drawPixmap(QRect(opt.rect.left() + self.MARGEN, y, mw, h), pm, QRect(0, 0, int(mw * r), int(h * r)))
        selected = bool(opt.state & enum(QStyle, 'StateFlag', 'State_Selected'))
        p.setPen(opt.palette.highlightedText().color() if selected else opt.palette.text().color())
        p.setFont(opt.font)
        p.drawText(lugar, qt('AlignmentFlag', 'AlignVCenter') | qt('AlignmentFlag', 'AlignLeft'), texto)
        p.restore()


class LineweightCombo(_PropCombo):
    prop = 'lineweight'
    tip = 'Grosor de línea'
    ancho = 104
    muestra = (28, 12)
    entero = True

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, parent)
        self.setItemDelegate(GrosorDelegate(self.muestra, self))
        ajustar_desplegable(self)

    def _fill(self):
        fg = self.palette().text().color().name()
        w, h = self.muestra
        self.addItem(QIcon(lineweight_sample(0.25, w, h, fg)), 'PorCapa', '')
        for lw in [float(LW_DEFAULT)] + LINEWEIGHTS:
            self.addItem(QIcon(lineweight_sample(0.25 if lw < 0 else lw, w, h, fg)),
                         lineweight_label(lw), float(lw))

    def label(self, value):
        return lineweight_label(value)
