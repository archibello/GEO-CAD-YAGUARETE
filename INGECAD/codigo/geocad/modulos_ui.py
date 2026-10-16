# SPDX-License-Identifier: GPL-3.0-or-later
"""La ventana «Módulos de GeoCAD»: una casilla por módulo.

Sirve a los dos programas: IngeCAD le pasa PySide6.QtWidgets y QGIS
qgis.PyQt.QtWidgets (misma forma de uso). Se abre al instalar (o la primera
vez que se abre GeoCAD en QGIS) y desde el menú GeoCAD > Módulos...
"""
from __future__ import annotations

from . import modulos


def _exec(dialog):
    run = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return run()


def elegir(QtWidgets, parent, programa: str, primera_vez: bool = False):
    """Muestra la ventana. Devuelve el nuevo estado {clave: bool} si se
    aceptó, o None si se canceló (en la primera vez, cancelar = valores por
    defecto, para que no vuelva a preguntar en cada inicio)."""
    nombre_prog = "IngeCAD" if programa == "ingecad" else "QGIS"
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(f"Módulos de GEO-CAD-YAGUARETÉ en {nombre_prog}")
    dlg.setMinimumWidth(560)
    lay = QtWidgets.QVBoxLayout(dlg)
    intro = ("Elegí qué partes de GeoCAD Yaguareté querés usar en " + nombre_prog + ". "
             "Lo que quede sin tildar no aparece en ningún menú ni cambia nada "
             "del programa. Se puede cambiar cuando quieras en GeoCAD Yaguareté > Módulos...")
    if primera_vez:
        intro = "GEO-CAD-YAGUARETÉ quedó instalado. " + intro
    nuevos = modulos.nuevos(programa)
    if nuevos and not primera_vez:
        nombres = [m.nombre for m in modulos.catalogo(programa) if m.clave in nuevos]
        intro = ("Esta versión de GeoCAD Yaguareté trae módulos nuevos: " + ", ".join(nombres)
                 + ". " + intro)
    label = QtWidgets.QLabel(intro, dlg)
    label.setWordWrap(True)
    lay.addWidget(label)
    # Aceptar arriba, junto al texto (pedido de Fernando, 16/10/2026): con
    # muchos módulos la ventana se alarga y el botón quedaba fuera de la vista.
    botones = QtWidgets.QDialogButtonBox(dlg)
    ok_role = getattr(QtWidgets.QDialogButtonBox, "StandardButton", QtWidgets.QDialogButtonBox)
    botones.setStandardButtons(ok_role.Ok | ok_role.Cancel)
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    lay.addWidget(botones)
    # la lista, con barra de desplazamiento: la ventana entra en la pantalla
    zona = QtWidgets.QScrollArea(dlg)
    zona.setWidgetResizable(True)
    lista = QtWidgets.QWidget()
    lay_lista = QtWidgets.QVBoxLayout(lista)
    zona.setWidget(lista)
    zona.setMinimumHeight(360)
    lay.addWidget(zona, 1)
    est = modulos.estado(programa)
    cajas = {}
    for m in modulos.catalogo(programa):
        texto = m.nombre + ("  (cambia el comportamiento del programa)" if m.cambia_programa else "")
        if not m.disponible:
            texto += "  — próximamente"
        caja = QtWidgets.QCheckBox(texto, lista)
        caja.setChecked(bool(est.get(m.clave)))
        caja.setEnabled(m.disponible)
        caja.setToolTip(m.detalle)
        lay_lista.addWidget(caja)
        detalle = QtWidgets.QLabel("      " + m.detalle, lista)
        detalle.setWordWrap(True)
        detalle.setEnabled(m.disponible)
        lay_lista.addWidget(detalle)
        cajas[m.clave] = caja

    def _dependencias(*_):
        for m in modulos.catalogo(programa):
            if m.requiere and m.disponible:
                ok = cajas[m.requiere].isChecked()
                cajas[m.clave].setEnabled(ok)
                if not ok:
                    cajas[m.clave].setChecked(False)
    for caja in cajas.values():
        caja.toggled.connect(_dependencias)
    _dependencias()
    lay_lista.addStretch(1)
    pantalla = getattr(dlg, "screen", lambda: None)()
    alto = pantalla.availableGeometry().height() if pantalla is not None else 900
    dlg.resize(780, min(760, int(alto * 0.85)))

    aceptado = bool(_exec(dlg))
    if not aceptado:
        if primera_vez and not modulos.elegido(programa):
            return modulos.guardar(programa, modulos.estado(programa))
        return None
    return modulos.guardar(programa, {k: c.isChecked() for k, c in cajas.items()})
