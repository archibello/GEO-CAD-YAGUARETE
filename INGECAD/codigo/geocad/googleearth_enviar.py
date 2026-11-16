# SPDX-License-Identifier: GPL-3.0-or-later
"""ENVIARGE: «Enviar a Google Earth...» (GEOEARTHOPEN, 3.81.0; antes ABRIRGE
abría Google Earth con el enlace, y eso pasó a «Traer imagen de Google
Earth...»).

Una ventana pregunta qué se manda: lo seleccionado, lo que se ve en
pantalla o las capas elegidas (por ejemplo una imagen en una capa y los
polígonos en otra). Se arma el mismo KMZ que EXPORTARKML (kml.plan_kml:
WGS 84, una carpeta por capa, colores, rellenos, atributos e imágenes como
superposiciones), se guarda en la carpeta de GeoCAD (no se pregunta dónde)
y se abre en Google Earth, que lo pone en Lugares temporales. Para guardar
un KMZ propio sigue EXPORTARKML.

Qt recién al abrir la ventana: lo de acá arriba se prueba sin Qt."""
from __future__ import annotations

import re
from pathlib import Path

from . import googleearth as GE
from . import kml as KML

ORDEN = "Enviar a Google Earth"
SELECCION, PANTALLA, CAPAS = "seleccion", "pantalla", "capas"


def carpeta_envios() -> Path:
    """Donde quedan los KMZ enviados (junto al enlace de Google Earth)."""
    return GE.archivo_kml().parent / "enviados"


def ruta_envio(base: str) -> Path:
    """Un KMZ por dibujo: se reemplaza en cada envío."""
    limpio = re.sub(r"[^\w\- .]+", "_", base or "").strip(" .") or "dibujo"
    return carpeta_envios() / f"{limpio}.kmz"


def entidades_de(doc, que: str, seleccion=(), zona=None, capas=()) -> list:
    """Los objetos del modelo que van, según lo elegido en la ventana."""
    if que == SELECCION:
        return list(seleccion)
    msp = doc.modelspace()
    if que == CAPAS:
        capas = set(capas)
        return [e for e in msp if e.dxf.get("layer", "0") in capas]
    if que == PANTALLA:
        return KML.en_zona(msp, zona) if zona else []
    raise ValueError(f"qué mandar: {que!r}")


def capas_con_objetos(doc) -> list[str]:
    """Las capas que tienen algo en el modelo (las vacías no se ofrecen)."""
    return sorted({e.dxf.get("layer", "0") for e in doc.modelspace()}, key=str.lower)


def zona_de(window):
    """(xmin, ymin, xmax, ymax) de lo que se ve, o None."""
    try:
        view = window.viewport.view
        x0, y0 = view.screen_to_world(0, view.height)
        x1, y1 = view.screen_to_world(view.width, 0)
    except Exception:  # noqa: BLE001 -- sin ventana o sin dibujo
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def soltar_candado_si_cerrado() -> bool:
    """Si Google Earth quedó trabado de un cierre de golpe («Another
    instance»), se destraba antes de abrirlo (como en la ventanita, 3.33.6)."""
    from . import googleearth_vivo as V
    foto = None
    try:
        foto = V.Foto()
        return GE.soltar_candado(foto.ventana(visible=False) is not None)
    except Exception:  # noqa: BLE001 -- sin X11 ni Windows no se sabe si está abierto
        return False
    finally:
        if foto is not None:
            try:
                foto.cerrar()
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ la ventana
def _dialogo(QtCore, QtWidgets, doc, n_sel: int, hay_zona: bool, parent):
    Qt = QtCore.Qt
    from . import intercambio as IX

    class EnviarDialog(QtWidgets.QDialog):
        def __init__(self) -> None:
            super().__init__(parent)
            self.setWindowTitle("Enviar a Google Earth")
            self.setMinimumWidth(480)
            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(QtWidgets.QLabel(
                f"De <b>{IX.nombre(IX.sistema_del_dibujo(doc))}</b> (el sistema del dibujo) a "
                "<b>Google Earth</b>. Llega a Lugares temporales y Google Earth vuela hasta ahí."))
            g = QtWidgets.QGroupBox("Qué se envía")
            v = QtWidgets.QVBoxLayout(g)
            self.sel = QtWidgets.QRadioButton(f"Los elementos seleccionados ({n_sel} objeto(s))")
            self.pantalla = QtWidgets.QRadioButton("Lo que se ve en pantalla")
            self.capas = QtWidgets.QRadioButton("Las capas elegidas:")
            self.sel.setEnabled(n_sel > 0)
            self.pantalla.setEnabled(hay_zona)
            (self.sel if n_sel else self.pantalla if hay_zona else self.capas).setChecked(True)
            self.lista = QtWidgets.QListWidget()
            for capa in capas_con_objetos(doc):
                item = QtWidgets.QListWidgetItem(capa)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.lista.addItem(item)
            self.lista.setMaximumHeight(160)
            self.lista.itemChanged.connect(lambda *_a: self.capas.setChecked(True))
            for w in (self.sel, self.pantalla, self.capas, self.lista):
                v.addWidget(w)
            lay.addWidget(g)
            f = QtWidgets.QFormLayout()
            self.relleno = QtWidgets.QSpinBox()
            self.relleno.setRange(0, 100)
            self.relleno.setSuffix(" %")
            self.relleno.setValue(KML.RELLENO)
            f.addRow("Relleno de los polígonos (0 = sin relleno):", self.relleno)
            lay.addLayout(f)
            nota = QtWidgets.QLabel("Una carpeta por capa (se prenden y apagan en Google Earth); "
                                    "las imágenes van en su lugar. Para guardar un KMZ en otra "
                                    "carpeta: Exportar > KML / KMZ (EXPORTARKML).")
            nota.setWordWrap(True)
            lay.addWidget(nota)
            self.aviso = QtWidgets.QLabel("")
            self.aviso.setStyleSheet("color: #b00020")
            lay.addWidget(self.aviso)
            caja = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                              | QtWidgets.QDialogButtonBox.Cancel)
            caja.button(QtWidgets.QDialogButtonBox.Ok).setText("Enviar")
            caja.button(QtWidgets.QDialogButtonBox.Cancel).setText("Cancelar")
            caja.accepted.connect(self.accept)
            caja.rejected.connect(self.reject)
            lay.addWidget(caja)

        def que(self) -> str:
            return SELECCION if self.sel.isChecked() else PANTALLA if self.pantalla.isChecked() \
                else CAPAS

        def capas_elegidas(self) -> set:
            return {self.lista.item(i).text() for i in range(self.lista.count())
                    if self.lista.item(i).checkState() == Qt.Checked}

        def accept(self) -> None:
            if self.capas.isChecked() and not self.capas_elegidas():
                self.aviso.setText("Tilde al menos una capa.")
                return
            super().accept()

    return EnviarDialog()


def enviar(ctx) -> None:
    """La orden: ventana, KMZ y Google Earth."""
    if ctx.document is None:
        ctx.echo(f"{ORDEN}: no hay un dibujo abierto.")
        return
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from . import intercambio_ui as IU
        from . import avance as AV
    except ImportError as exc:
        ctx.echo(f"{ORDEN}: este IngeCAD no trae lo necesario ({exc}).")
        return
    doc = ctx.document.doc
    try:
        if not IU._asegurar_sistema(ctx):
            return
    except IU.IX.SinProj:
        ctx.echo(f"{ORDEN}: este IngeCAD no trae pyproj (PROJ); no se puede pasar a WGS 84.")
        return
    elegidos = IU._seleccion(ctx)
    zona = zona_de(ctx.host)
    dlg = _dialogo(QtCore, QtWidgets, doc, len(elegidos), zona is not None, ctx.host)
    if not dlg.exec():
        return
    entidades = entidades_de(doc, dlg.que(), elegidos, zona, dlg.capas_elegidas())
    if not entidades:
        ctx.echo(f"{ORDEN}: no hay nada en lo elegido.")
        return
    archivo = getattr(ctx.document, "path", None)
    base = Path(str(archivo)).stem if archivo else "dibujo"
    destino = ruta_envio(base)
    try:
        with AV.Avance(ctx.host, ORDEN, etapas=3) as av:     # preparar, escribir, guardar
            plan = KML.plan_kml(entidades, doc, base, True, dlg.relleno.value(), True, "",
                                archivo, avance=av)
            if not plan.marcas and not plan.superposiciones:
                ctx.echo(f"{ORDEN}: no hay nada que Google Earth pueda mostrar en lo elegido.")
                return
            av.etapa("Escribiendo las marcas", total=len(plan.marcas) + len(plan.superposiciones))
            destino.parent.mkdir(parents=True, exist_ok=True)
            KML.escribir(plan, destino, av)
    except AV.Cancelado:
        ctx.echo(f"{ORDEN}: cancelado; no se envió nada.")
        return
    except Exception as exc:  # noqa: BLE001
        ctx.echo(f"{ORDEN}: {exc}")
        return
    soltado = soltar_candado_si_cerrado()
    if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(destino))):
        QtWidgets.QMessageBox.information(
            ctx.host, "GeoCAD Yaguareté",
            f"Abrí este archivo con Google Earth Pro (Archivo > Abrir):\n{destino}")
    texto = KML.resumen(plan, destino).replace(" Ábralo en Google Earth.", "")
    ctx.echo(f"{ORDEN}: {texto} Enviado a Google Earth (Lugares temporales)."
             + (" (Estaba trabado de un cierre de golpe: destrabado.)" if soltado else ""))
