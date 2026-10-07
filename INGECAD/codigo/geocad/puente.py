# SPDX-License-Identifier: GPL-3.0-or-later
"""El puente con QGIS, del lado de IngeCAD.

Un temporizador de Qt (1 s) mira el buzón: cuando QGIS manda capas, las
conecta una por una con el mismo comando SHPCONNECT (sin abrir el diálogo
de archivos), hace zoom a lo que se estaba viendo en QGIS y trae la
ventana al frente. Además avisa "IngeCAD está abierto" y publica su ícono
para el botón de QGIS.
"""
from __future__ import annotations

from . import buzon

_state = {"timer": None, "window": None, "ticks": 0, "pending": []}



def _heartbeat() -> None:
    """Señal de vida, con la versión (QGIS avisa si no coincide con la suya)."""
    from . import VERSION

    buzon.heartbeat("ingecad", {"version": VERSION})

def ensure_started(window) -> None:
    """Arranca el puente una sola vez por ventana."""
    if window is None or _state["timer"] is not None:
        return
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    timer = QTimer(window)
    timer.setInterval(1000)
    timer.timeout.connect(_tick)
    timer.start()
    _state.update(timer=timer, window=window, ticks=0)
    _export_icon(window)
    try:
        _heartbeat()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(lambda: buzon.clear_heartbeat("ingecad"))
    except OSError:
        pass


def _export_icon(window) -> None:
    """El ícono de IngeCAD, para que QGIS lo muestre en su botón."""
    try:
        icon = window.windowIcon()
        if icon.isNull():
            return
        path = buzon.icon_path("ingecad")
        path.parent.mkdir(parents=True, exist_ok=True)
        icon.pixmap(64, 64).save(str(path), "PNG")
    except Exception:
        pass


def _echo(text: str) -> None:
    window = _state["window"]
    try:
        window.command_line.echo(text)
    except Exception:
        pass


PLUGIN_ID = "geocad"


def shutdown() -> None:
    """El plugin se desactivó: quitar todo lo que el puente agregó."""
    window = _state["window"]
    timer = _state["timer"]
    if timer is not None:
        timer.stop()
        timer.deleteLater()
    if window is not None:
        try:
            from .tabla import remove_table

            remove_table(window)
        except Exception:
            pass
    buzon.clear_heartbeat("ingecad")
    _state.update(timer=None, window=None, ticks=0)


def _tick() -> None:
    _state["ticks"] += 1
    window = _state["window"]
    manager = getattr(window, "plugins", None)
    if manager is not None and not manager.is_active(PLUGIN_ID):
        shutdown()                       # "sin rastro" al desactivar
        return
    try:
        if _state["ticks"] % 4 == 0:
            _heartbeat()
        for msg in buzon.receive("ingecad"):
            handle(msg)
    except Exception as exc:                       # el puente nunca tumba IngeCAD
        _echo(f"Puente QGIS: {type(exc).__name__}: {exc}")


def handle(msg: dict) -> None:
    window = _state["window"]
    if msg.get("tipo") == "actualizar" and window is not None:
        from . import actualizacion

        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: actualizacion.desde_qgis(window, msg, _echo))
        except ImportError:
            actualizacion.desde_qgis(window, msg, _echo)
        return
    if msg.get("tipo") != "conectar" or window is None:
        return
    capas = [c for c in msg.get("capas", []) if c.get("ruta")]
    if not capas:
        return
    _echo(f"QGIS mandó {len(capas)} capa(s).")
    for capa in capas:
        _state["pending"].append(capa)
        window.tools.start_tool("SHPCONNECT")
        _state["pending"].clear()
    ext = msg.get("extension")
    if ext and len(ext) == 4:
        try:
            vp = window.viewport
            vp.push_view()
            vp.view.zoom_extents(*[float(v) for v in ext])
            vp.update()
        except Exception:
            pass
    try:
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
    except Exception:
        pass


def take_request():
    """La capa que mandó QGIS, para SHPCONNECT (None si es un uso normal)."""
    if _state["pending"]:
        return _state["pending"].pop(0)
    return None


def notify(tipo: str, links, fids_by_key=None) -> None:
    """Avisa a QGIS (guardado / conectado / liberado). Con ``fids_by_key``
    QGIS deja seleccionados esos registros (los que se devolvieron)."""
    capas = []
    for link in links:
        ref = buzon.layer_ref(link.fmt, link.path, link.table)
        if fids_by_key and link.key in fids_by_key:
            ref["fids"] = sorted(fids_by_key[link.key])
        capas.append(ref)
    if not capas:
        return
    try:
        buzon.send("qgis", {"tipo": tipo, "capas": capas}, "ingecad")
    except OSError:
        pass


# -- la tabla de atributos (si está abierta) ------------------------------------------

_table = {"panel": None}


def register_table(panel) -> None:
    _table["panel"] = panel


def table_refresh() -> None:
    """Los datos cambiaron (edición, guardado, conexión): recargar la tabla."""
    panel = _table["panel"]
    if panel is not None:
        try:
            panel.reload()
        except Exception:
            pass


def table_selection_changed() -> None:
    panel = _table["panel"]
    if panel is not None:
        try:
            panel.sync_from_drawing()
        except Exception:
            pass
