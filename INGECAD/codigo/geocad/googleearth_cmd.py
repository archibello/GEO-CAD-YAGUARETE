# SPDX-License-Identifier: GPL-3.0-or-later
"""Google Earth en IngeCAD (módulo «googleearth», 3.33.0): menú GeoCAD >
Google Earth.

    ABRIRGE        (GEOEARTHOPEN)     Abrir Google Earth con GeoCAD
    CAPTURARGE     (GEOEARTHCAPTURE)  Capturar vista (Ctrl+Alt+G)
    CONFIGURARGE   (GEOEARTHSETUP)    Configurar captura

Las cuentas, el servidor y la ventanita están en el núcleo (googleearth*.py).
Acá: el sistema del dibujo (SISTEMAGEO, o el del proyecto en Opciones), el
JPG con PIL, y la imagen insertada en su lugar como INSERTARGEO (un U la
quita). Las que manda QGIS llegan por el Puente.

No se importa nada de la ventanita al cargar: http.server, ctypes y el resto
recién al abrirla (la AppImage de IngeCAD no trae todo, 3.31.3).
"""
from __future__ import annotations

import sys

from . import googleearth as GE
from . import imagengeo
from . import modulos

PROGRAMA = "ingecad"
_PENDIENTES: list = []


def _qt():
    from PySide6 import QtCore, QtGui, QtWidgets

    return QtCore, QtGui, QtWidgets


def _echo(window, texto: str) -> None:
    try:
        window.command_line.echo(texto)
    except Exception:  # noqa: BLE001
        pass


class Programa:
    """Lo propio de IngeCAD para la ventanita (ver googleearth_ui)."""
    nombre = PROGRAMA

    def __init__(self, window) -> None:
        self.window = window

    def sistema(self):
        from . import config, intercambio

        # el dibujo de ezdxf de la pestaña activa (3.33.2: se pasaba la
        # pestaña y el sistema salía siempre vacío)
        doc = getattr(getattr(self.window, "document", None), "doc", None)
        crs = intercambio.sistema_del_dibujo(doc) if doc is not None else ""
        if crs:
            return crs, "del dibujo"
        crs = str(config.get("crs_proyecto") or "")
        if crs:
            return crs, "del proyecto (GeoCAD > Configuración compartida)"
        return "", "el dibujo no tiene sistema"

    def avisar(self, texto: str) -> None:
        _echo(self.window, texto)

    def zona(self):
        """(xmin, ymin, xmax, ymax) de lo que se ve en el dibujo (3.33.1)."""
        try:
            view = self.window.viewport.view
            x0, y0 = view.screen_to_world(0, view.height)
            x1, y1 = view.screen_to_world(view.width, 0)
        except Exception:  # noqa: BLE001 -- sin ventana o sin dibujo
            return None
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @staticmethod
    def escribir_jpg(a, ruta) -> None:
        from PIL import Image

        Image.fromarray(a).save(ruta, "JPEG", quality=92)

    def insertar(self, ruta, crs: str = "") -> str:
        tools = getattr(self.window, "tools", None)
        if tools is None:
            return "Sin dibujo abierto: la imagen quedó en la carpeta."
        _PENDIENTES.append(str(ruta))
        tools.start_tool("GEOEARTHINSERT")
        return "Insertada en el dibujo de IngeCAD (U la quita)."

    @staticmethod
    def otro_disponible() -> bool:
        from . import buzon

        return buzon.is_alive("qgis")

    @staticmethod
    def enviar_otro(ruta, crs: str) -> None:
        from . import buzon

        buzon.send("qgis", GE.mensaje(ruta, crs), PROGRAMA)


class InsertarCapturaTool(imagengeo.InsertarGeoTool):
    """GEOEARTHINSERT: la captura recién guardada, en su lugar (sin preguntar)."""

    def start(self) -> None:
        self.name = "GEOEARTHINSERT"
        doc = getattr(getattr(self.ctx.services, "window", None), "document", None)
        while _PENDIENTES:
            ruta = _PENDIENTES.pop(0)
            if doc is None:
                self.ctx.echo(f"GeoCAD Yaguareté: no hay un dibujo abierto; la captura quedó en {ruta}.")
                continue
            self.insertar(ruta)
        self.ctx.finish()


def recibir(window, msg: dict) -> bool:
    """La captura que mandó QGIS (por el Puente): se inserta en el dibujo."""
    if not modulos.activo(PROGRAMA, "googleearth"):
        return False
    ruta = GE.ruta_de_mensaje(msg)
    if ruta is None:
        return False
    _echo(window, f"QGIS mandó una captura de Google Earth: {ruta.name}")
    Programa(window).insertar(ruta)
    return True


def _abrir(ctx, **kw) -> None:
    window = getattr(ctx, "host", None)
    try:
        QtCore, QtGui, QtWidgets = _qt()
        from . import googleearth_ui as UI
    except ImportError as exc:
        ctx.echo(f"Google Earth: este IngeCAD no trae lo necesario ({exc}).")
        return
    if window is None:
        ctx.echo("Google Earth necesita la ventana de IngeCAD.")
        return
    UI.abrir(QtCore, QtGui, QtWidgets, window, Programa(window), **kw)


def cmd_abrir(ctx, *args) -> None:
    _abrir(ctx, abrir_ge=True)


def cmd_capturar(ctx, *args) -> None:
    _abrir(ctx, capturar=True)


def cmd_configurar(ctx, *args) -> None:
    window = getattr(ctx, "host", None)
    try:
        QtCore, QtGui, QtWidgets = _qt()
        from . import googleearth_ui as UI
    except ImportError as exc:
        ctx.echo(f"Google Earth: este IngeCAD no trae lo necesario ({exc}).")
        return
    UI.configurar(QtCore, QtGui, QtWidgets, window, Programa(window))


def apagar() -> None:
    """Módulo apagado: ventanita, servidor, atajo y enlace fuera (sin rastro).
    Si la ventanita nunca se abrió no hay nada que cerrar."""
    ui = sys.modules.get(__name__.rsplit(".", 1)[0] + ".googleearth_ui")
    if ui is not None:
        ui.cerrar()
    else:
        try:
            GE.archivo_kml().unlink()
        except OSError:
            pass


COMMANDS = {
    "GEOEARTHOPEN": cmd_abrir,
    "GEOEARTHCAPTURE": cmd_capturar,
    "GEOEARTHSETUP": cmd_configurar,
}
