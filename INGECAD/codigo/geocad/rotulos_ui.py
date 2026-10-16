# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventana de ROTULOSIG (3.26.0): campo, altura y cómo se ubican los
rótulos en polígonos, líneas y puntos (reglas en rotulos.py). Recuerda lo
último elegido."""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox,
                               QRadioButton, QVBoxLayout)

from . import rotulos as R


class RotulosDialog(QDialog):
    def __init__(self, campos, altura: float, op: R.OpcionesRotulo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rótulos desde un campo (ROTULOSIG)")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.campo = QComboBox()
        self.campo.addItems(list(campos))
        form.addRow("Campo para rotular:", self.campo)
        self.altura = QDoubleSpinBox()
        self.altura.setRange(0.01, 100000)
        self.altura.setDecimals(2)
        self.altura.setValue(altura)
        form.addRow("Altura del texto:", self.altura)
        lay.addLayout(form)
        self.grupos = {}
        for clave, titulo, opciones, actual in (
                ("poligono", "Polígonos cerrados: siempre dentro, en el centro. Los que no entran:",
                 R.POLIGONO, op.poligono),
                ("linea", "Líneas: según el eje, en la mitad", R.LINEA, op.linea),
                ("punto", "Puntos", R.PUNTO, op.punto)):
            g = QGroupBox(titulo)
            v = QVBoxLayout(g)
            botones = QButtonGroup(self)
            for valor, texto in opciones.items():
                b = QRadioButton(f"{valor}  {texto}" if clave == "poligono" else texto)
                b.setProperty("valor", valor)
                b.setChecked(valor == actual)
                botones.addButton(b)
                v.addWidget(b)
            self.grupos[clave] = botones
            lay.addWidget(g)
        caja = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        caja.button(QDialogButtonBox.Ok).setText("Rotular")
        caja.accepted.connect(self.accept)
        caja.rejected.connect(self.reject)
        lay.addWidget(caja)

    def opciones(self) -> R.OpcionesRotulo:
        elegido = {k: (g.checkedButton().property("valor") if g.checkedButton() else "")
                   for k, g in self.grupos.items()}
        return R.OpcionesRotulo(**elegido).validas()
