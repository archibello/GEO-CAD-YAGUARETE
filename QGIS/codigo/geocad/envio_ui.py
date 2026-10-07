# -*- coding: utf-8 -*-
"""La ventana «Enviar a IngeCAD» (3.1.0): las opciones se eligen al enviar.

Arranca con lo elegido la última vez (configuración común) y lo recuerda.
Con «No volver a preguntar» se envía directo con esas opciones; se vuelve a
pedir en GeoCAD > Configuración común («Preguntar estas opciones...»).
"""
from __future__ import annotations

from qgis.PyQt import QtWidgets

from . import config

MODOS = (("seleccion", "Los objetos seleccionados"),
         ("pantalla", "Lo que está en pantalla"),
         ("completa", "Las capas visibles completas"))
ROTULOS = (("visibles_resto", "Los que QGIS muestra en pantalla + todos los de fuera (recomendado)"),
           ("visibles_zona", "Los que QGIS mostraría en toda la zona enviada (más lento)"),
           ("todos", "Todos (también los que QGIS no muestra)"),
           ("visibles", "Sólo los que QGIS muestra ahora en pantalla"),
           ("ninguno", "Ninguno"))
VISIBLES = ("visibles", "visibles_resto", "visibles_zona")


def from_config(modo: str) -> dict:
    """Las opciones guardadas, con el modo pedido."""
    # «rotulos_visibles» viene de 3.3.x: apagado = todos; prendido = el criterio
    # elegido, y si no hay ninguno, «en pantalla + todos los de fuera» (3.4.0)
    rot = config.get("rotulos_cuales") or "visibles_resto"
    if not config.get("rotulos_visibles"):
        rot = "todos"
    elif rot == "todos":
        rot = "visibles_resto"
    if not config.get("envio_rotulos"):
        rot = "ninguno"
    return {"modo": modo, "escala": int(config.get("escala_rotulos") or 0),
            "capas_colores": bool(config.get("envio_capas_colores")), "rotulos": rot,
            "simbolos": bool(config.get("envio_simbolos")),
            "ajustar": bool(config.get("ajustar_a_parcela")),
            "preguntar": bool(config.get("preguntar_al_enviar"))}


def remember(opts: dict) -> None:
    changes = {"escala_rotulos": int(opts["escala"]),
               "envio_capas_colores": bool(opts["capas_colores"]),
               "envio_rotulos": opts["rotulos"] != "ninguno",
               "rotulos_visibles": opts["rotulos"] in VISIBLES,
               "envio_simbolos": bool(opts["simbolos"]),
               "ajustar_a_parcela": bool(opts["ajustar"]),
               "preguntar_al_enviar": bool(opts["preguntar"])}
    if opts["rotulos"] != "ninguno":
        changes["rotulos_cuales"] = opts["rotulos"]
    if opts.get("modo") in dict(MODOS):
        changes["envio_predeterminado"] = opts["modo"]
    config.save(changes, "qgis")


def _enum(cls, group, name):
    return getattr(getattr(cls, group, cls), name)


class EnvioDialog(getattr(QtWidgets, "QDialog", object)):
    def __init__(self, parent, opts: dict, map_scale: float, show_mode: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enviar a IngeCAD")
        self.setMinimumWidth(480)
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        lay.addLayout(form)

        self.modo = QtWidgets.QComboBox()
        for key, text in MODOS:
            self.modo.addItem(text, key)
        self.modo.setVisible(show_mode)
        if show_mode:
            form.addRow("Qué mandar:", self.modo)

        row = QtWidgets.QHBoxLayout()
        self.escala_mapa = QtWidgets.QRadioButton(f"La del mapa (1:{round(map_scale):,})".replace(",", "."))
        self.escala_otra = QtWidgets.QRadioButton("Otra: 1:")
        self.escala = QtWidgets.QSpinBox()
        self.escala.setRange(1, 100000000)
        self.escala.setValue(int(map_scale) or 1000)
        row.addWidget(self.escala_mapa)
        row.addWidget(self.escala_otra)
        row.addWidget(self.escala)
        form.addRow("Escala (tamaño de rótulos y símbolos):", row)

        self.capas = QtWidgets.QCheckBox("Capas (LAYER_CODE) y colores de QGIS")
        form.addRow("", self.capas)
        self.rotulos = QtWidgets.QComboBox()
        for key, text in ROTULOS:
            self.rotulos.addItem(text, key)
        self.rotulos.setToolTip(
            "En pantalla: lo que QGIS dibuja ahora.\n"
            "+ todos los de fuera: lo de fuera de la pantalla va siempre (y se achica si "
            "está elegido).\n"
            "Toda la zona: QGIS calcula sus etiquetas en toda la zona enviada, a la "
            "escala elegida, por tramos del tamaño de la pantalla.")
        form.addRow("Rótulos:", self.rotulos)
        self.simbolos = QtWidgets.QCheckBox("Puntos con su símbolo de QGIS (forma, tamaño y giro)")
        form.addRow("", self.simbolos)
        row = QtWidgets.QVBoxLayout()
        self.tam_real = QtWidgets.QRadioButton("Tamaño real, aunque supere la parcela")
        self.ajustar = QtWidgets.QRadioButton("Achicarlos hasta que entren en su parcela")
        row.addWidget(self.tam_real)
        row.addWidget(self.ajustar)
        form.addRow("Rótulos y símbolos:", row)

        self.no_preguntar = QtWidgets.QCheckBox(
            "No volver a preguntar (se cambia en GeoCAD > Configuración común)")
        lay.addWidget(self.no_preguntar)
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
        self._groups = []                    # cada par de opciones, por separado
        for pair in ((self.escala_mapa, self.escala_otra), (self.tam_real, self.ajustar)):
            group = QtWidgets.QButtonGroup(self)
            for button in pair:
                group.addButton(button)
            self._groups.append(group)
        self.escala_otra.toggled.connect(self.escala.setEnabled)
        self.set_values(opts)

    def set_values(self, opts: dict) -> None:
        i = self.modo.findData(opts.get("modo"))
        self.modo.setCurrentIndex(max(i, 0))
        own = int(opts.get("escala") or 0)
        self.escala_otra.setChecked(own > 0)
        self.escala_mapa.setChecked(own <= 0)
        if own > 0:
            self.escala.setValue(own)
        self.escala.setEnabled(own > 0)
        self.capas.setChecked(bool(opts.get("capas_colores")))
        self.rotulos.setCurrentIndex(max(self.rotulos.findData(opts.get("rotulos")), 0))
        self.simbolos.setChecked(bool(opts.get("simbolos")))
        self.ajustar.setChecked(bool(opts.get("ajustar")))
        self.tam_real.setChecked(not opts.get("ajustar"))
        self.no_preguntar.setChecked(not opts.get("preguntar", True))

    def values(self) -> dict:
        return {"modo": self.modo.currentData(),
                "escala": self.escala.value() if self.escala_otra.isChecked() else 0,
                "capas_colores": self.capas.isChecked(), "rotulos": self.rotulos.currentData(),
                "simbolos": self.simbolos.isChecked(), "ajustar": self.ajustar.isChecked(),
                "preguntar": not self.no_preguntar.isChecked()}


def ask(parent, modo: str, map_scale: float, show_mode: bool = True):
    """Las opciones del envío (recordadas), o None si se canceló. Si está
    apagado «preguntar», devuelve las guardadas sin mostrar nada."""
    opts = from_config(modo)
    if not opts["preguntar"]:
        return opts
    dlg = EnvioDialog(parent, opts, map_scale, show_mode)
    run = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
    if not run():
        return None
    got = dlg.values()
    if not show_mode:
        got["modo"] = None                       # la capa activa: no cambia el botón
    remember(got)
    got["modo"] = got["modo"] or modo
    return got
