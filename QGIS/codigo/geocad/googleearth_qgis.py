# SPDX-License-Identifier: GPL-3.0-or-later
"""Google Earth en QGIS (módulo «googleearth», 3.33.0): menú GeoCAD >
Google Earth (Abrir Google Earth con GeoCAD, Capturar vista, Configurar
captura). Las cuentas, el servidor y la ventanita están en el núcleo
(googleearth*.py). Acá: el sistema del proyecto, el JPG con GDAL (QGIS no
trae PIL) y la imagen agregada como capa ráster. Las que manda IngeCAD
llegan por el Puente.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import buzon, modulos
from . import googleearth as GE

PROGRAMA = "qgis"


def _qt():
    from qgis.PyQt import QtCore, QtGui, QtWidgets

    return QtCore, QtGui, QtWidgets


class Programa:
    """Lo propio de QGIS para la ventanita (ver googleearth_ui)."""
    nombre = PROGRAMA

    def __init__(self, iface) -> None:
        self.iface = iface

    @staticmethod
    def sistema():
        from qgis.core import QgsProject

        crs = QgsProject.instance().crs()
        if not crs.isValid():
            return "", "el proyecto no tiene sistema"
        if crs.isGeographic():
            return "", f"el proyecto está en geográficas ({crs.authid()})"
        return crs.authid(), "del proyecto"

    def avisar(self, texto: str) -> None:
        from qgis.core import Qgis

        nivel = getattr(getattr(Qgis, "MessageLevel", Qgis), "Success")
        self.iface.messageBar().pushMessage("GeoCAD Yaguareté", texto, level=nivel, duration=10)

    def zona(self):
        """(xmin, ymin, xmax, ymax) de lo que se ve en el mapa, en el sistema
        del proyecto (3.33.1)."""
        try:
            e = self.iface.mapCanvas().extent()
            return (e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def escribir_jpg(a, ruta) -> None:
        from osgeo import gdal

        alto, ancho = a.shape[:2]
        mem = gdal.GetDriverByName("MEM").Create("", ancho, alto, 3, gdal.GDT_Byte)
        for i in range(3):
            mem.GetRasterBand(i + 1).WriteArray(a[..., i])
        gdal.GetDriverByName("JPEG").CreateCopy(str(ruta), mem, options=["QUALITY=92"])
        mem = None

    def insertar(self, ruta, crs: str = "") -> str:
        return agregar_capa(ruta, crs)

    @staticmethod
    def otro_disponible() -> bool:
        return buzon.is_alive("ingecad")

    @staticmethod
    def enviar_otro(ruta, crs: str) -> None:
        buzon.send("ingecad", GE.mensaje(ruta, crs), PROGRAMA)


def agregar_capa(ruta, crs: str = "") -> str:
    """La imagen como capa ráster del proyecto (con su sistema si GDAL no
    lo encuentra al lado)."""
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer

    ruta = Path(ruta)
    capa = QgsRasterLayer(str(ruta), ruta.stem)
    if not capa.isValid():
        return f"QGIS no pudo abrir {ruta.name}."
    if crs and not capa.crs().isValid():
        capa.setCrs(QgsCoordinateReferenceSystem(crs))
    QgsProject.instance().addMapLayer(capa)
    return f"Agregada al proyecto de QGIS como capa «{capa.name()}»."


def recibir(iface, msg: dict) -> str:
    """La captura que mandó IngeCAD (por el Puente): se agrega como capa."""
    if not modulos.activo(PROGRAMA, "googleearth"):
        return ""
    ruta = GE.ruta_de_mensaje(msg)
    if ruta is None:
        return ""
    return "IngeCAD mandó una captura de Google Earth. " + agregar_capa(ruta, msg.get("crs", ""))


def _ui(parent):
    try:
        QtCore, QtGui, QtWidgets = _qt()
        from . import googleearth_ui as UI
    except ImportError as exc:
        from qgis.PyQt.QtWidgets import QMessageBox

        QMessageBox.warning(parent, "GeoCAD Yaguareté", f"Falta algo para Google Earth: {exc}")
        return None
    return QtCore, QtGui, QtWidgets, UI


def abrir(iface, capturar: bool = False, abrir_ge: bool = False) -> None:
    parent = iface.mainWindow()
    r = _ui(parent)
    if r is not None:
        QtCore, QtGui, QtWidgets, UI = r
        UI.abrir(QtCore, QtGui, QtWidgets, parent, Programa(iface), capturar=capturar,
                 abrir_ge=abrir_ge)


def configurar(iface) -> None:
    parent = iface.mainWindow()
    r = _ui(parent)
    if r is not None:
        QtCore, QtGui, QtWidgets, UI = r
        UI.configurar(QtCore, QtGui, QtWidgets, parent, Programa(iface))


def apagar() -> None:
    """Módulo apagado o complemento descargado: ventanita, servidor, atajo
    y enlace fuera (sin rastro)."""
    ui = sys.modules.get(__name__.rsplit(".", 1)[0] + ".googleearth_ui")
    if ui is not None:
        ui.cerrar()
    else:
        try:
            GE.archivo_kml().unlink()
        except OSError:
            pass
