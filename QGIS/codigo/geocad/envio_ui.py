# -*- coding: utf-8 -*-
"""La ventana «Enviar a IngeCAD» (3.1.0; 3.50.1 simple, pedido de Fernando).

Dos opciones y la altura de los textos, nada más: lo seleccionado o la capa
activa entera. Capas, colores y temático van siempre; los rótulos van todos y
IngeCAD los ubica como ROTULOSIG, con círculo (texto + 10 % en diagonal), y
los que hay que achicar quedan con la altura del más chico. Arranca con lo
elegido la última vez y lo recuerda.
"""
from __future__ import annotations

from qgis.PyQt import QtWidgets

from . import config

MODOS = (("seleccion", "Lo seleccionado"),
         ("capa", "La capa activa entera"))
ALTURA = 2.5
NOTA = ("Los rótulos se ubican en IngeCAD como ROTULOSIG, cada uno en un círculo "
        "(el texto + 10 % en diagonal). Los que no entran en su parcela se achican "
        "y quedan todos con la altura del más chico, en su círculo al 90 % del lugar.")


def from_config() -> dict:
    """Lo elegido la última vez."""
    modo = config.get("envio_predeterminado")
    altura = float(config.get("envio_altura") or 0)
    return {"modo": modo if modo in dict(MODOS) else "seleccion",
            "altura": altura if altura > 0 else ALTURA}


def remember(opts: dict) -> None:
    config.save({"envio_predeterminado": opts["modo"], "envio_altura": float(opts["altura"])},
                "qgis")


def _enum(cls, group, name):
    return getattr(getattr(cls, group, cls), name)


class EnvioDialog(getattr(QtWidgets, "QDialog", object)):
    def __init__(self, parent, opts: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enviar a IngeCAD")
        self.setMinimumWidth(420)
        lay = QtWidgets.QVBoxLayout(self)
        self.botones = {}
        group = QtWidgets.QButtonGroup(self)
        for key, text in MODOS:
            button = QtWidgets.QRadioButton(text)
            group.addButton(button)
            lay.addWidget(button)
            self.botones[key] = button
        self._group = group
        form = QtWidgets.QFormLayout()
        lay.addLayout(form)
        self.altura = QtWidgets.QDoubleSpinBox()
        self.altura.setDecimals(2)
        self.altura.setRange(0.01, 100000.0)
        form.addRow("Altura de los textos:", self.altura)
        nota = QtWidgets.QLabel(NOTA)
        nota.setWordWrap(True)
        lay.addWidget(nota)
        buttons = QtWidgets.QDialogButtonBox(self)
        std = _enum(QtWidgets.QDialogButtonBox, "StandardButton", "Ok") | \
            _enum(QtWidgets.QDialogButtonBox, "StandardButton", "Cancel")
        buttons.setStandardButtons(std)
        ok = buttons.button(_enum(QtWidgets.QDialogButtonBox, "StandardButton", "Ok"))
        if ok is not None:
            ok.setText("Enviar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.set_values(opts)

    def set_values(self, opts: dict) -> None:
        self.botones.get(opts.get("modo"), self.botones["seleccion"]).setChecked(True)
        self.altura.setValue(float(opts.get("altura") or ALTURA))

    def values(self) -> dict:
        modo = next((k for k, b in self.botones.items() if b.isChecked()), "seleccion")
        return {"modo": modo, "altura": round(self.altura.value(), 6)}


def ask(parent):
    """Lo elegido en la ventana (y recordado), o None si se canceló."""
    dlg = EnvioDialog(parent, from_config())
    run = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
    if not run():
        return None
    got = dlg.values()
    remember(got)
    return got
