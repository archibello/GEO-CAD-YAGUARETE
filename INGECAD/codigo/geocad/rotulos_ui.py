# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventana de ROTULOSIG (3.26.0): campo, altura y cómo se ubican los
rótulos en polígonos, líneas y puntos (reglas en rotulos.py). Recuerda lo
último elegido. 3.48.0: la casilla «Encerrar en un círculo» (polígonos).
3.48.1: polígonos siempre en el epicentro y según el eje (sin A-E); la
altura (la pedida o la del más chico) y qué pasa con los rótulos anteriores."""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
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

        g = QGroupBox("Polígonos cerrados")
        v = QVBoxLayout(g)
        nota = QLabel("En el epicentro (el centroide) y según el eje más largo del polígono. "
                      "Los que no entran se achican ahí mismo.")
        nota.setWordWrap(True)
        v.addWidget(nota)
        self.circulo = QCheckBox(
            "Encerrar en un círculo: el texto + 10 %, dentro del polígono con 10 % de aire.\n"
            "Si no entra, el círculo más grande que entra y el texto achicado adentro.")
        self.circulo.setChecked(op.circulo == "si")
        v.addWidget(self.circulo)
        lay.addWidget(g)

        self.grupos = {}
        for clave, titulo, opciones, actual in (
                ("linea", "Líneas: según el eje, en la mitad", R.LINEA, op.linea),
                ("punto", "Puntos", R.PUNTO, op.punto),
                ("altura", "Altura de los rótulos", R.ALTURA, op.altura),
                ("anteriores", "Si esos objetos ya tienen rótulos", R.ANTERIORES, op.anteriores)):
            g = QGroupBox(titulo)
            v = QVBoxLayout(g)
            botones = QButtonGroup(self)
            for valor, texto in opciones.items():
                b = QRadioButton(texto)
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
        elegido["circulo"] = "si" if self.circulo.isChecked() else "no"
        return R.OpcionesRotulo(**elegido).validas()
