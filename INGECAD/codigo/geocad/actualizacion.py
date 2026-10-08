# SPDX-License-Identifier: GPL-3.0-or-later
"""QGISUPDATE (ACTUALIZARGEOCAD): actualiza GeoCAD desde su menú.

Busca la versión más nueva en la carpeta de actualizaciones (configuración
común), muestra sus cambios, pide confirmación y corre el mismo instalador
que se usaba con APPLOAD. Después le avisa a QGIS, que ofrece actualizarse
desde la misma carpeta (si QGIS está cerrado, el aviso lo espera).
"""
from __future__ import annotations

from pathlib import Path

from . import actualizar, buzon, config


def version_instalada() -> str:
    from . import PLUGIN

    return PLUGIN.version


# -- diálogos (las pruebas los reemplazan) ------------------------------------------
def _pedir_carpeta(window, actual: str):
    try:
        from PySide6.QtWidgets import QFileDialog
    except ImportError:
        return None
    carpeta = QFileDialog.getExistingDirectory(
        window, "Carpeta de donde se actualiza GeoCAD Yaguareté (la del proyecto)", actual or str(Path.home()))
    return carpeta or None


def _preguntar(window, titulo: str, texto: str) -> bool:
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        return False
    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    return QMessageBox.question(window, titulo, texto, yes | no, yes) == yes


def _diferir(funcion) -> None:
    """Corre ``funcion`` cuando termine el comando actual (el instalador
    reemplaza este mismo plugin)."""
    try:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, funcion)
    except ImportError:
        funcion()


def _correr_instalador(window, ruta: Path, echo) -> None:
    from core import scripting

    _cuenta, error = scripting.run_python(ruta, window)
    if error:
        echo(f"Actualizar GeoCAD Yaguareté: {error}")


# -- el comando --------------------------------------------------------------------
def carpeta_de_actualizaciones(window, echo, cambiar: bool = False):
    carpeta = config.get("carpeta_actualizaciones")
    if cambiar or not carpeta or not Path(carpeta).is_dir():
        if carpeta and not cambiar:
            echo(f"La carpeta de actualizaciones no está disponible: {carpeta}")
        elegida = _pedir_carpeta(window, carpeta)
        if not elegida:
            echo("Actualizar GeoCAD Yaguareté: cancelado (falta la carpeta de actualizaciones).")
            return None
        config.save({"carpeta_actualizaciones": elegida}, "IngeCAD")
        carpeta = elegida
    return carpeta


def actualizar_ingecad(window, echo, carpeta: str, avisar_qgis: bool = True,
                       silencioso: bool = False) -> bool:
    """True si se lanzó la instalación de una versión nueva."""
    actual = version_instalada()
    cand = actualizar.mas_nueva(carpeta, "ingecad", actual)
    if avisar_qgis:
        try:
            buzon.send("qgis", {"tipo": "actualizar", "carpeta": carpeta}, "ingecad")
        except OSError:
            pass
    if cand is None:
        if not silencioso:
            echo(f"GeoCAD Yaguareté para IngeCAD ya está en la última versión ({actual}). "
                 f"Carpeta: {carpeta}")
        return False
    texto = (f"Hay una versión nueva de GeoCAD Yaguareté para IngeCAD:\n\n"
             f"    instalada: {actual}\n    nueva:     {cand.version}\n"
             f"    archivo:   {cand.nombre}\n")
    detalle = actualizar.cambios(cand)
    if detalle:
        texto += "\n" + detalle + "\n"
    texto += "\n¿Instalarla ahora?"
    if not _preguntar(window, "Actualizar GeoCAD Yaguareté", texto):
        echo("Actualizar GeoCAD Yaguareté: no se instaló nada.")
        return False
    ruta = actualizar.extraer(cand)
    echo(f"Instalando GeoCAD Yaguareté {cand.version} desde {cand.nombre}...")
    _diferir(lambda: _correr_instalador(window, ruta, echo))
    return True


def cmd_actualizar(ctx, *args) -> None:
    """ACTUALIZARGEOCAD [C]: busca e instala la versión nueva. Con C, elige
    otra carpeta de actualizaciones."""
    window = ctx.host
    cambiar = bool(args) and args[0].strip().upper() in ("C", "CARPETA")
    carpeta = carpeta_de_actualizaciones(window, ctx.echo, cambiar)
    if carpeta:
        actualizar_ingecad(window, ctx.echo, carpeta)


def desde_qgis(window, msg: dict, echo) -> None:
    """QGIS se actualizó y avisa: si en su carpeta hay una versión nueva
    para IngeCAD, se ofrece (sin volver a avisarle a QGIS)."""
    carpeta = msg.get("carpeta") or config.get("carpeta_actualizaciones")
    if not carpeta or not Path(carpeta).is_dir():
        return
    actualizar_ingecad(window, echo, carpeta, avisar_qgis=False, silencioso=True)
