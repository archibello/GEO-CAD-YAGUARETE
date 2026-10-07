# -*- coding: utf-8 -*-
"""Diálogos estilo AutoCAD: color, tipo de línea, grosor, transparencia y estados de capa."""

import json

from qgis.PyQt.QtCore import QRect, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .aci import ACI_RGB, aci_to_hex, color_display_name, color_hex, parse_color_text
from .compat import enum, exec_dialog, qt
from .icons import color_swatch, linetype_sample, lineweight_sample
from .linetypes import LINETYPE_ORDER, LINETYPES, LINEWEIGHTS, LW_DEFAULT, lineweight_text
from .theme import palette, stylesheet


def _event_pos(ev):
    return ev.position().toPoint() if hasattr(ev, 'position') else ev.pos()


def _buttons(dlg, ok=True, cancel=True):
    box = QDialogButtonBox()
    b_ok = enum(QDialogButtonBox, 'StandardButton', 'Ok')
    b_cancel = enum(QDialogButtonBox, 'StandardButton', 'Cancel')
    if ok:
        box.addButton(b_ok).setText('Aceptar')
    if cancel:
        box.addButton(b_cancel).setText('Cancelar')
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


class CadDialog(QDialog):
    def __init__(self, parent, title, theme='dark'):
        super().__init__(parent)
        self.setObjectName('CadDialog')
        self.setWindowTitle(title)
        self.theme = theme
        self.setStyleSheet(stylesheet(theme))


# --------------------------------------------------------------------------
# Seleccionar color (ACI + color verdadero)
# --------------------------------------------------------------------------
class AciGrid(QWidget):
    hovered = pyqtSignal(int)
    picked = pyqtSignal(int)
    doublePicked = pyqtSignal(int)

    CELL = 13

    def __init__(self, parent=None, theme='dark'):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.selected = None
        self.hover = None
        self.cells = []
        self.theme = theme
        c = self.CELL
        y0 = 0
        for blk, subs in enumerate(([0, 2, 4, 6, 8], [1, 3, 5, 7, 9])):
            for row, sub in enumerate(subs):
                for col in range(24):
                    idx = 10 + col * 10 + sub
                    self.cells.append((idx, QRect(col * c, y0 + row * c, c - 1, c - 1)))
            y0 += 5 * c + 8
        big = 20
        y0 += 4
        for i in range(1, 10):
            self.cells.append((i, QRect((i - 1) * (big + 3), y0, big, big)))
        gx = 9 * (big + 3) + 18
        for k, i in enumerate(range(250, 256)):
            self.cells.append((i, QRect(gx + k * (big + 3), y0, big, big)))
        self._size = QSize(24 * c, y0 + big + 2)
        self.setMinimumSize(self._size)

    def sizeHint(self):
        return self._size

    def index_at(self, pos):
        for idx, r in self.cells:
            if r.adjusted(0, 0, 1, 1).contains(pos):
                return idx
        return None

    def paintEvent(self, ev):
        p = QPainter(self)
        border = QColor(palette(self.theme)['border'])
        for idx, r in self.cells:
            p.fillRect(r, QColor(aci_to_hex(idx)))
            p.setPen(QPen(border, 1))
            p.drawRect(r)
        for idx, col, w in ((self.hover, '#9aa5b1', 1), (self.selected, '#ffffff', 2)):
            if idx is None:
                continue
            for i, r in self.cells:
                if i == idx:
                    p.setPen(QPen(QColor('#000000'), w + 2))
                    p.drawRect(r.adjusted(-1, -1, 1, 1))
                    p.setPen(QPen(QColor(col), w))
                    p.drawRect(r.adjusted(-1, -1, 1, 1))
        p.end()

    def mouseMoveEvent(self, ev):
        idx = self.index_at(_event_pos(ev))
        if idx != self.hover:
            self.hover = idx
            self.update()
            if idx is not None:
                self.hovered.emit(idx)

    def leaveEvent(self, ev):
        self.hover = None
        self.update()

    def mousePressEvent(self, ev):
        idx = self.index_at(_event_pos(ev))
        if idx is not None:
            self.selected = idx
            self.update()
            self.picked.emit(idx)

    def mouseDoubleClickEvent(self, ev):
        idx = self.index_at(_event_pos(ev))
        if idx is not None:
            self.doublePicked.emit(idx)


class ColorDialog(CadDialog):
    def __init__(self, parent, color, theme='dark'):
        super().__init__(parent, 'Seleccionar color', theme)
        self.original = dict(color)
        self.color = dict(color)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # pestaña índice
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel('Colores de índice de AutoCAD (ACI):'))
        self.grid = AciGrid(w, theme)
        v.addWidget(self.grid)
        info = QHBoxLayout()
        self.lbl_idx = QLabel('Índice de color:')
        self.lbl_rgb = QLabel('Rojo, Verde, Azul:')
        info.addWidget(self.lbl_idx)
        info.addStretch()
        info.addWidget(self.lbl_rgb)
        v.addLayout(info)
        tabs.addTab(w, 'Color de índice')

        # pestaña color verdadero
        self.qcd = QColorDialog(QColor(color_hex(color)))
        self.qcd.setOption(enum(QColorDialog, 'ColorDialogOption', 'NoButtons'), True)
        self.qcd.setOption(enum(QColorDialog, 'ColorDialogOption', 'DontUseNativeDialog'), True)
        self.qcd.setWindowFlags(qt('WindowType', 'Widget'))
        self.qcd.currentColorChanged.connect(self._true_changed)
        tabs.addTab(self.qcd, 'Color verdadero')
        tabs.setCurrentIndex(0 if color.get('aci') else 1)

        row = QHBoxLayout()
        row.addWidget(QLabel('Color:'))
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(self._text_changed)
        row.addWidget(self.edit, 1)
        self.sw_old = QLabel()
        self.sw_new = QLabel()
        row.addWidget(QLabel('Anterior'))
        row.addWidget(self.sw_old)
        row.addWidget(QLabel('Nuevo'))
        row.addWidget(self.sw_new)
        lay.addLayout(row)
        lay.addWidget(_buttons(self))

        self.grid.hovered.connect(self._show_info)
        self.grid.picked.connect(self._aci_picked)
        self.grid.doublePicked.connect(lambda i: (self._aci_picked(i), self.accept()))
        self.sw_old.setPixmap(color_swatch(color_hex(self.original), 34, 18))
        self._refresh()

    def _show_info(self, idx):
        r, g, b = ACI_RGB[idx]
        self.lbl_idx.setText('Índice de color: %d' % idx)
        self.lbl_rgb.setText('Rojo, Verde, Azul: %d,%d,%d' % (r, g, b))

    def _aci_picked(self, idx):
        self.color = {'aci': idx, 'rgb': None}
        self._refresh()

    def _true_changed(self, qc):
        if self.qcd.isVisible():
            self.color = {'aci': None, 'rgb': qc.name()}
            self._refresh(update_qcd=False)

    def _text_changed(self):
        c = parse_color_text(self.edit.text())
        if c:
            self.color = c
        self._refresh()

    def _refresh(self, update_qcd=True):
        self.edit.setText(color_display_name(self.color))
        self.grid.selected = self.color.get('aci')
        self.grid.update()
        if self.color.get('aci'):
            self._show_info(self.color['aci'])
        self.sw_new.setPixmap(color_swatch(color_hex(self.color), 34, 18))
        if update_qcd:
            self.qcd.blockSignals(True)
            self.qcd.setCurrentColor(QColor(color_hex(self.color)))
            self.qcd.blockSignals(False)


# --------------------------------------------------------------------------
# Seleccionar tipo de línea
# --------------------------------------------------------------------------
class LinetypeDialog(CadDialog):
    def __init__(self, parent, current, theme='dark'):
        super().__init__(parent, 'Seleccionar tipo de línea', theme)
        self.resize(560, 380)
        fg = palette(theme)['text']
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('Tipos de línea cargados'))
        self.tree = QTreeWidget()
        self.tree.setObjectName('CadList')
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels(['Tipo de línea', 'Aspecto', 'Descripción'])
        self.tree.setIconSize(QSize(120, 12))
        self.tree.setAlternatingRowColors(True)
        for name in LINETYPE_ORDER:
            it = QTreeWidgetItem([name, '', LINETYPES[name]['desc']])
            it.setIcon(1, _icon(linetype_sample(name, color=fg)))
            self.tree.addTopLevelItem(it)
            if name == current:
                self.tree.setCurrentItem(it)
        self.tree.setColumnWidth(0, 130)
        self.tree.setColumnWidth(1, 140)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.tree)
        lay.addWidget(_buttons(self))

    def value(self):
        it = self.tree.currentItem()
        return it.text(0) if it else None


def _icon(pm):
    from qgis.PyQt.QtGui import QIcon
    return QIcon(pm)


# --------------------------------------------------------------------------
# Grosor de línea
# --------------------------------------------------------------------------
class LineweightDialog(CadDialog):
    def __init__(self, parent, current, theme='dark'):
        super().__init__(parent, 'Grosor de línea', theme)
        self.resize(300, 420)
        fg = palette(theme)['text']
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('Grosores de línea:'))
        self.list = QListWidget()
        self.list.setObjectName('CadList')
        self.list.setIconSize(QSize(44, 14))
        for lw in [LW_DEFAULT] + LINEWEIGHTS:
            it = QListWidgetItem(_icon(lineweight_sample(0.25 if lw < 0 else lw, color=fg)),
                                 lineweight_text(lw))
            it.setData(qt('ItemDataRole', 'UserRole'), lw)
            self.list.addItem(it)
            if abs(lw - (current if current is not None else LW_DEFAULT)) < 1e-6:
                self.list.setCurrentItem(it)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list)
        self.lbl = QLabel()
        lay.addWidget(QLabel('Original: %s' % lineweight_text(current)))
        lay.addWidget(self.lbl)
        self.list.currentItemChanged.connect(self._upd)
        self._upd()
        lay.addWidget(_buttons(self))

    def _upd(self, *a):
        v = self.value()
        self.lbl.setText('Nuevo: %s' % (lineweight_text(v) if v is not None else ''))

    def value(self):
        it = self.list.currentItem()
        return it.data(qt('ItemDataRole', 'UserRole')) if it else None


# --------------------------------------------------------------------------
# Transparencia
# --------------------------------------------------------------------------
class TransparencyDialog(CadDialog):
    def __init__(self, parent, current, theme='dark'):
        super().__init__(parent, 'Transparencia de capa', theme)
        lay = QFormLayout(self)
        self.spin = QSpinBox()
        self.spin.setRange(0, 90)
        self.spin.setValue(int(current))
        lay.addRow('Transparencia (0-90):', self.spin)
        lay.addRow(_buttons(self))

    def value(self):
        return self.spin.value()


# --------------------------------------------------------------------------
# Administrador de estados de capa
# --------------------------------------------------------------------------
PROP_LABELS = [('on', 'Act./Desact.'), ('frozen', 'Inutilizar/Reutilizar'),
               ('locked', 'Bloquear/Desbloquear'), ('plot', 'Trazar/No trazar'),
               ('color', 'Color'), ('linetype', 'Tipo de línea'),
               ('lineweight', 'Grosor de línea'), ('transparency', 'Transparencia')]


class LayerStatesDialog(CadDialog):
    def __init__(self, parent, ctrl, theme='dark'):
        super().__init__(parent, 'Administrador de estados de capa', theme)
        self.ctrl = ctrl
        self.resize(620, 420)
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel('Estados de capa'))
        self.tree = QTreeWidget()
        self.tree.setObjectName('CadList')
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels(['Nombre', 'Capa actual', 'Descripción'])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(lambda *_: self._restore())
        left.addWidget(self.tree)
        self.chk_off = QCheckBox('Desactivar capas no encontradas en el estado')
        left.addWidget(self.chk_off)
        grp = QGroupBox('Propiedades que restaurar')
        g = QGridLayout(grp)
        self.checks = {}
        for i, (k, label) in enumerate(PROP_LABELS):
            cb = QCheckBox(label)
            cb.setChecked(True)
            self.checks[k] = cb
            g.addWidget(cb, i // 2, i % 2)
        left.addWidget(grp)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        for text, fn in (('Nuevo...', self._new), ('Actualizar', self._update),
                         ('Cambiar nombre', self._rename), ('Suprimir', self._delete),
                         (None, None), ('Importar...', self._import), ('Exportar...', self._export),
                         (None, None), ('Restaurar', self._restore), ('Cerrar', self.accept)):
            if text is None:
                right.addSpacing(12)
                continue
            b = QPushButton(text)
            b.clicked.connect(fn)
            right.addWidget(b)
        right.addStretch()
        root.addLayout(right)
        self._load()

    def _load(self):
        self.tree.clear()
        for name, st in sorted(self.ctrl.cfg['states'].items()):
            self.tree.addTopLevelItem(QTreeWidgetItem([name, st.get('current', ''), st.get('description', '')]))
        self.tree.resizeColumnToContents(0)

    def _sel(self):
        it = self.tree.currentItem()
        return it.text(0) if it else None

    def _new(self):
        name, ok = QInputDialog.getText(self, 'Nuevo estado de capa', 'Nombre del estado:')
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.ctrl.cfg['states'] and not self._confirm('El estado "%s" ya existe. ¿Reemplazarlo?' % name):
            return
        desc, _ = QInputDialog.getText(self, 'Nuevo estado de capa', 'Descripción (opcional):')
        self.ctrl.save_state(name, desc)
        self._load()

    def _update(self):
        n = self._sel()
        if n:
            desc = self.ctrl.cfg['states'][n].get('description', '')
            self.ctrl.save_state(n, desc)
            self._load()

    def _rename(self):
        n = self._sel()
        if not n:
            return
        new, ok = QInputDialog.getText(self, 'Cambiar nombre', 'Nuevo nombre:', text=n)
        new = new.strip()
        if ok and new and new != n and new not in self.ctrl.cfg['states']:
            states = self.ctrl.cfg['states']
            states[new] = states.pop(n)
            self.ctrl._save()
            self._load()

    def _delete(self):
        n = self._sel()
        if n and self._confirm('¿Suprimir el estado de capa "%s"?' % n):
            self.ctrl.delete_state(n)
            self._load()

    def _restore(self):
        n = self._sel()
        if not n:
            return
        props = tuple(k for k, cb in self.checks.items() if cb.isChecked())
        self.ctrl.restore_state(n, props, self.chk_off.isChecked())
        self.ctrl.msg('Estado de capa "%s" restaurado.' % n)

    def _export(self):
        n = self._sel()
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar estados de capa',
                                              (n or 'estados') + '.json', 'Estados de capa (*.json)')
        if path:
            states = {n: self.ctrl.cfg['states'][n]} if n else self.ctrl.cfg['states']
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({'states': states}, fh, ensure_ascii=False, indent=2)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Importar estados de capa', '', 'Estados de capa (*.json)')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            states = data.get('states', {})
            if not isinstance(states, dict):
                raise ValueError('formato no válido')
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, 'Importar', 'No se pudo leer el archivo:\n%s' % e)
            return
        self.ctrl.cfg['states'].update(states)
        self.ctrl._save()
        self._load()

    def _confirm(self, text):
        yes = enum(QMessageBox, 'StandardButton', 'Yes')
        no = enum(QMessageBox, 'StandardButton', 'No')
        return QMessageBox.question(self, 'Estados de capa', text, yes | no) == yes


__all__ = ['ColorDialog', 'LinetypeDialog', 'LineweightDialog', 'TransparencyDialog',
           'LayerStatesDialog', 'exec_dialog', 'QAbstractItemView']
