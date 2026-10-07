# -*- coding: utf-8 -*-
"""Diálogo 'Unidades de dibujo' (UNIDADES / UNITS) y 'Control de dirección'."""

import math

from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QGridLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                 QRadioButton, QVBoxLayout)

from .compat import enum, exec_dialog, accepted_code
from .units import (RELMODE_LABELS, RELMODES, AUNITS_LABELS, DECIMAL, DMS, DMS_PRECISIONS, GRADS, RADIANS, SURVEYOR,
                    InputError, Units, format_angle, format_point, parse_degrees)

STYLE = """
QDialog { background: #3b4453; color: #e6e9ee; }
QLabel, QCheckBox, QRadioButton, QGroupBox { color: #e6e9ee; }
QGroupBox { border: 1px solid #20252d; margin-top: 9px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QComboBox, QLineEdit { background: #262b34; color: #e6e9ee; border: 1px solid #20252d; padding: 2px 4px; }
QComboBox QAbstractItemView { background: #262b34; color: #e6e9ee; selection-background-color: #3d6a99; }
QPushButton { background: #4a5466; color: #e6e9ee; border: 1px solid #20252d; padding: 4px 14px; }
QPushButton:hover { background: #46536a; }
QLabel#Sample { background: #262b34; border: 1px solid #20252d; padding: 6px; font-family: Consolas, monospace; }
"""


def _btns(dlg):
    box = QDialogButtonBox()
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Ok')).setText('Aceptar')
    box.addButton(enum(QDialogButtonBox, 'StandardButton', 'Cancel')).setText('Cancelar')
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


class DirectionDialog(QDialog):
    def __init__(self, parent, angbase):
        super().__init__(parent)
        self.setWindowTitle('Control de dirección')
        self.setStyleSheet(STYLE)
        v = QVBoxLayout(self)
        grp = QGroupBox('Ángulo base')
        g = QVBoxLayout(grp)
        self.group = QButtonGroup(self)
        self.radios = {}
        for val, label in ((0.0, 'Este       0d'), (90.0, 'Norte      90d'),
                           (180.0, 'Oeste      180d'), (270.0, 'Sur        270d'), (None, 'Otro')):
            r = QRadioButton(label)
            self.group.addButton(r)
            self.radios[val] = r
            g.addWidget(r)
        h = QHBoxLayout()
        h.addWidget(QLabel('Ángulo:'))
        self.edit = QLineEdit()
        h.addWidget(self.edit)
        g.addLayout(h)
        v.addWidget(grp)
        v.addWidget(_btns(self))
        match = None
        for val in (0.0, 90.0, 180.0, 270.0):
            if abs(angbase - val) < 1e-9:
                match = val
        self.radios[match].setChecked(True)
        self.edit.setText('' if match is not None else ('%g' % angbase))
        self.edit.textEdited.connect(lambda *_: self.radios[None].setChecked(True))

    def value(self):
        for val, r in self.radios.items():
            if r.isChecked() and val is not None:
                return val
        return parse_degrees(self.edit.text()) % 360.0

    def accept(self):
        try:
            self.value()
        except InputError as e:
            self.edit.setToolTip(str(e))
            self.edit.setFocus()
            return
        super().accept()


class UnitsDialog(QDialog):
    def __init__(self, parent, units):
        super().__init__(parent)
        self.setWindowTitle('Unidades de dibujo')
        self.setStyleSheet(STYLE)
        self.angbase = units.angbase
        v = QVBoxLayout(self)
        top = QHBoxLayout()

        gl = QGroupBox('Longitud')
        l = QGridLayout(gl)
        l.addWidget(QLabel('Tipo:'), 0, 0)
        ltype = QComboBox()
        ltype.addItem('Decimales (unidades del SRC del mapa)')
        ltype.setEnabled(False)
        l.addWidget(ltype, 1, 0)
        l.addWidget(QLabel('Precisión:'), 2, 0)
        self.lprec = QComboBox()
        for i in range(9):
            self.lprec.addItem('0' if i == 0 else '0.' + '0' * i)
        self.lprec.setCurrentIndex(units.luprec)
        l.addWidget(self.lprec, 3, 0)
        top.addWidget(gl)

        ga = QGroupBox('Ángulo')
        a = QGridLayout(ga)
        a.addWidget(QLabel('Tipo:'), 0, 0)
        self.atype = QComboBox()
        self.atype.addItems(AUNITS_LABELS)
        self.atype.setCurrentIndex(units.aunits)
        a.addWidget(self.atype, 1, 0)
        a.addWidget(QLabel('Precisión:'), 2, 0)
        self.aprec = QComboBox()
        a.addWidget(self.aprec, 3, 0)
        self.cw = QCheckBox('Sentido horario')
        self.cw.setChecked(units.angdir_cw)
        a.addWidget(self.cw, 4, 0)
        top_rel = QGroupBox('Ángulos relativos al último tramo (modo REL)')
        r = QVBoxLayout(top_rel)
        self.relmode = QComboBox()
        self.relmode.addItems(RELMODE_LABELS)
        self.relmode.setCurrentIndex(RELMODES.index(units.relmode))
        r.addWidget(self.relmode)
        r.addWidget(QLabel('El sentido (antihorario u horario) es el definido arriba. '
                           'Con REL activo, <<ang fuerza un ángulo absoluto.'))
        self._rel_box = top_rel
        top.addWidget(ga)
        v.addLayout(top)
        v.addWidget(self._rel_box)

        gs = QGroupBox('Muestra de salida')
        s = QVBoxLayout(gs)
        self.sample = QLabel()
        self.sample.setObjectName('Sample')
        s.addWidget(self.sample)
        v.addWidget(gs)

        bottom = QHBoxLayout()
        b_dir = QPushButton('Dirección...')
        b_dir.clicked.connect(self._direction)
        bottom.addWidget(b_dir)
        bottom.addStretch()
        bottom.addWidget(_btns(self))
        v.addLayout(bottom)

        self._fill_aprec(units.auprec)
        self.atype.currentIndexChanged.connect(lambda *_: self._fill_aprec(None))
        for w in (self.lprec, self.aprec, self.atype):
            w.currentIndexChanged.connect(lambda *_: self._update_sample())
        self.cw.toggled.connect(lambda *_: self._update_sample())
        self._update_sample()

    def _fill_aprec(self, current):
        t = self.atype.currentIndex()
        self.aprec.blockSignals(True)
        self.aprec.clear()
        vals = []
        if t in (DMS, SURVEYOR):
            for val, label in DMS_PRECISIONS:
                lab = label if t == DMS else 'N%sE' % label
                self.aprec.addItem(lab, val)
                vals.append(val)
        else:
            suffix = {GRADS: 'g', RADIANS: 'r'}.get(t, '')
            for i in range(9):
                self.aprec.addItem(('0' if i == 0 else '0.' + '0' * i) + suffix, i)
                vals.append(i)
        idx = 0
        if current is not None:
            for i, val in enumerate(vals):
                if val <= current:
                    idx = i
        self.aprec.setCurrentIndex(idx)
        self.aprec.blockSignals(False)
        self._update_sample()

    def units(self):
        return Units(luprec=self.lprec.currentIndex(), aunits=self.atype.currentIndex(),
                     auprec=self.aprec.currentData() or 0, angbase=self.angbase,
                     angdir_cw=self.cw.isChecked(),
                     relmode=RELMODES[max(0, self.relmode.currentIndex())])

    def _update_sample(self):
        u = self.units()
        ang = math.radians(u.angbase + (-45 if u.angdir_cw else 45))
        self.sample.setText('%s,0\n3<%s' % (format_point(1.5, 2.0039, u), format_angle(ang, u)))

    def _direction(self):
        dlg = DirectionDialog(self, self.angbase)
        if exec_dialog(dlg) == accepted_code():
            self.angbase = dlg.value()
            self._update_sample()


__all__ = ['UnitsDialog', 'DECIMAL']
