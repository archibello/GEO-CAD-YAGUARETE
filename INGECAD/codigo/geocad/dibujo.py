# SPDX-License-Identifier: GPL-3.0-or-later
"""Dibujo al estilo de Fernando (el mismo que Dibujo CAD en QGIS).

Cada parte es un módulo de GeoCAD («Botón derecho = Enter», «Ángulos
relativos»): se elige al instalar y, apagado, IngeCAD se comporta como venía.

1. BOTÓN DERECHO = ENTER, siempre: termina la orden en curso, acepta lo que
   esté escrito en la línea de comandos y, sin orden activa, repite la
   última (aunque haya objetos seleccionados). Ctrl + botón derecho sigue
   mostrando el menú contextual; Mayús + botón derecho, el de referencias.

2. ÁNGULOS RELATIVOS AL TRAMO ANTERIOR en
   LÍNEA y POLILÍNEA, igual que Dibujo CAD:

       @distancia<ángulo   el ángulo es el INTERIOR en el vértice, medido en
                           sentido ANTIHORARIO desde el tramo anterior
                           (180 = seguir derecho, 90 = girar a la derecha,
                           270 = girar a la izquierda).
       @d<<ángulo          fuerza un ángulo absoluto (0 = este, antihorario).
       @d<30dI  @d<30dD    deflexión a la Izquierda / Derecha del tramo.
       @d<N45d30'15"E      rumbo: siempre absoluto.

   En el primer tramo no hay tramo anterior: el ángulo es absoluto.
   Los ángulos aceptan 45, 45.5, 45d30'15", 50g (centesimales) y 0.78r.
   ANGREL cambia el modo (Activar / Desactivar / Interior / Dirección).

IngeCAD no tiene ganchos para esto, así que el plugin envuelve dos métodos
(``ToolController.on_text`` y ``MainWindow.on_canvas_right_click``); el
envoltorio no hace nada si el plugin o el módulo están desactivados.
"""
from __future__ import annotations

import math

from . import modulos
from .angulos import AnguloError, direccion, grados, reescribir  # noqa: F401

PLUGIN_ID = "geocad"
PROGRAMA = "ingecad"

# --------------------------------------------------------------- ajustes
KEY_MODO = "geocad/dibujo/modo_relativo"            # "interior" / "direccion"
MODOS = ("interior", "direccion")

_memoria: dict = {}          # sin Qt (pruebas): los ajustes viven acá


def _settings():
    try:
        from PySide6.QtCore import QSettings
        return QSettings()
    except Exception:
        return None


def _get(key, default):
    s = _settings()
    if s is None:
        return _memoria.get(key, default)
    value = s.value(key, default)
    return default if value is None else value


def _set(key, value) -> None:
    s = _settings()
    if s is None:
        _memoria[key] = value
    else:
        s.setValue(key, value)


def relativo() -> bool:
    """Módulo «Ángulos relativos» (se elige al instalar; ANGREL lo cambia)."""
    return modulos.activo(PROGRAMA, "angulos_relativos")


def set_relativo(on: bool) -> None:
    modulos.poner(PROGRAMA, "angulos_relativos", on)


def boton_derecho() -> bool:
    """Módulo «Botón derecho = Enter» (se elige al instalar; BOTONDERECHO)."""
    return modulos.activo(PROGRAMA, "boton_derecho")


def set_boton_derecho(on: bool) -> None:
    modulos.poner(PROGRAMA, "boton_derecho", on)


def modo() -> str:
    value = str(_get(KEY_MODO, "interior"))
    return value if value in MODOS else "interior"


def set_modo(value: str) -> None:
    _set(KEY_MODO, value if value in MODOS else "interior")


# ------------------------------------------------------- tramo anterior
def tramo_anterior(tool):
    """Dirección (grados) del último tramo de una LÍNEA o POLILÍNEA en
    curso, o None (primer tramo, u otra orden)."""
    if tool is None:
        return None
    name = getattr(tool, "name", "")
    if name == "PLINE" and getattr(tool, "_segs", None):
        try:
            return float(tool._prev_dir())
        except Exception:
            return None
    if name == "LINE":
        pts = getattr(tool, "_points", None) or []
        if len(pts) >= 2:
            a, b = pts[-2], pts[-1]
            if math.dist(a, b) > 1e-12:
                return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return None


# ------------------------------------------------------- los envoltorios
def _activo(window) -> bool:
    mgr = getattr(window, "plugins", None)
    if mgr is None:
        return True
    try:
        return bool(mgr.is_active(PLUGIN_ID))
    except Exception:
        return True


def _texto_libre(tool) -> bool:
    """El prompt pide texto libre (contenido de un TEXTO): no tocarlo."""
    fn = getattr(tool, "wants_raw_text", None)
    try:
        return bool(fn()) if callable(fn) else False
    except Exception:
        return False


def _envolver_on_text(original):
    def on_text(self, text, *args, **kwargs):
        from . import seleccion
        if seleccion.on_text(self, text):        # W, WP, CP, F... en «Select objects»
            return True
        tool = getattr(self, "tool", None)
        if (tool is not None and getattr(self, "_selecting_for", None) is None
                and not getattr(tool, "entity_picker", False)
                and not _texto_libre(tool)
                and "<" in text and relativo()
                and _activo(getattr(self, "window", None))):
            modifier = getattr(self, "_modifier", None)
            ref = None if modifier is not None else tramo_anterior(tool)
            primer_punto = getattr(tool, "last_point", None) is None
            try:
                nuevo = reescribir(
                    text, ref,
                    relativa_sin_arroba=bool(getattr(self, "dyn_on", False)) and not primer_punto,
                    rel=True, modo_rel=modo())
            except AnguloError as exc:
                try:
                    self.window.command_line.echo(f"Ángulo no válido: {exc}")
                except Exception:
                    pass
                return True
            if nuevo is not None:
                text = nuevo
        return original(self, text, *args, **kwargs)

    on_text._puente_original = original
    on_text._puente_fabrica = _envolver_on_text
    return on_text


def _ctrl_apretado() -> bool:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        return bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
    except Exception:
        return False


def _texto_escrito(window) -> str:
    try:
        return window.command_line.input.text()
    except Exception:
        return ""


def _apretar_enter_en_linea(window) -> None:
    """Lo escrito en la línea de comandos se acepta como con Enter (con su
    historial, eco y todo)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier)
    window.command_line.input.keyPressEvent(event)


def _envolver_clic_derecho(original):
    def on_canvas_right_click(self, global_pos, *args, **kwargs):
        if not _activo(self) or not boton_derecho():
            return original(self, global_pos, *args, **kwargs)
        if _ctrl_apretado():
            return self.show_canvas_context_menu(global_pos)
        if _texto_escrito(self).strip():
            _apretar_enter_en_linea(self)
            return None
        tools = self.tools
        if tools.active() or tools._selecting_for is not None \
                or self.dispatcher.pending_prompt is not None:
            return original(self, global_pos, *args, **kwargs)
        self.dispatcher.submit("")       # repite la última orden, como Enter
        return None

    on_canvas_right_click._puente_original = original
    return on_canvas_right_click


#: comandos de IngeCAD que GeoCAD reemplaza mientras su módulo está activo
REEMPLAZOS = {"FILLET": ("empalme", "GEOFILLET"), "CHAMFER": ("chaflan", "GEOCHAMFER"),
              "BLOCK": ("bloques", "GEOBLOCK"), "INSERT": ("bloques", "GEOINSERT"),
              "STRETCH": ("estirar", "GEOSTRETCH"), "TEXT": ("texto", "GEOTEXT")}


def herramienta_para(nombre: str, window=None, registradas=None) -> str:
    """El nombre de herramienta a arrancar: el de GeoCAD si su módulo está
    activo (y el plugin también); si no, el de IngeCAD tal cual."""
    clave = REEMPLAZOS.get(str(nombre).upper())
    if clave is None or not _activo(window):
        return nombre
    modulo, propia = clave
    if not modulos.activo(PROGRAMA, modulo):
        return nombre
    if registradas is not None and propia not in registradas:
        return nombre
    return propia


def _envolver_start_tool(original):
    def start_tool(self, name, *args, **kwargs):
        try:
            from views.tool_controller import ALL_TOOL_CLASSES
        except Exception:
            ALL_TOOL_CLASSES = {}       # sin IngeCAD real: siempre el nativo
        name = herramienta_para(name, getattr(self, "window", None), ALL_TOOL_CLASSES)
        return original(self, name, *args, **kwargs)

    start_tool._puente_original = original
    return start_tool


def envolver(cls, nombre: str, fabrica, reemplazar: bool = False) -> bool:
    """Envuelve ``cls.nombre`` una sola vez. Con ``reemplazar``, un
    envoltorio de una versión anterior del plugin se cambia por el nuevo
    (al actualizar sin reiniciar IngeCAD)."""
    actual = getattr(cls, nombre, None)
    if actual is not None and hasattr(actual, "_puente_original"):
        if not reemplazar:
            return False
        actual = actual._puente_original
    if actual is None:
        return False
    setattr(cls, nombre, fabrica(actual))
    return True


def desenvolver(cls, nombre: str) -> None:
    actual = getattr(cls, nombre, None)
    original = getattr(actual, "_puente_original", None)
    if original is not None:
        setattr(cls, nombre, original)


def deshacer_ajuste_1x() -> None:
    """El Puente 1.3/1.4 dejaba el botón derecho de IngeCAD en «Enter» en sus
    propias Opciones. En GeoCAD eso lo maneja el módulo, así que se vuelve a
    dejar IngeCAD como venía (una sola vez)."""
    s = _settings()
    viejo = "puente_qgis/dibujo/boton_derecho_inicial"
    if s is None or str(s.value(viejo, "")) != "1":
        return
    try:
        from views.options_dialog import RIGHT_CLICK_MENU, SETTING_RIGHT_CLICK
        s.setValue(SETTING_RIGHT_CLICK, RIGHT_CLICK_MENU)
    except Exception:
        pass
    for key in (viejo, "puente_qgis/dibujo/angulo_relativo"):
        s.remove(key)


# ------------------------------------------------------------- resaltado
#: (color RGBA, ancho en píxeles, punteado) de cada capa del resaltado, en el
#: orden en que se dibujan
ESTILO_RESALTADO = {
    "cursor": ((60, 170, 255, 150), 5, False),    # lo que tomaría un clic: más grueso
    "elegido": ((60, 170, 255, 255), 3, False),   # lo ya elegido: azul de selección
    "vista": ((255, 170, 40, 255), 2, True),      # el empalme que va a quedar
    "pieza_a": ((60, 170, 255, 255), 4, False),   # partir: un pedazo en azul...
    "pieza_b": ((90, 220, 120, 255), 4, False),   # ...y el otro en verde
    "fantasma": ((143, 184, 216, 220), 1, False),  # el bloque que sigue al cursor
    "estirado": ((255, 170, 40, 255), 2, False),   # ESTIRA: cómo queda lo que se estira
    "sel_ventana": ((60, 120, 255, 255), 1, False),  # W / WP: azul, continuo
    "sel_captura": ((60, 200, 90, 255), 1, True),    # C / CP: verde, punteado
    "sel_borde": ((255, 170, 40, 255), 2, True),     # F: naranja, punteado
}
MARCA = (255, 220, 0, 255)                        # el punto de corte (amarillo de referencias)


def _cursor_resuelto(delegate):
    """Donde caería el clic: con la referencia a objetos si la hay (para las
    herramientas que eligen objetos, el cursor tal cual)."""
    cursor = getattr(delegate, "_cursor", None)
    if cursor is None:
        return None
    fn = getattr(delegate, "resolved_point", None)
    if fn is None:
        return cursor
    try:
        return fn(*cursor)
    except Exception:  # noqa: BLE001
        return cursor


def dibujar_resaltado(viewport, painter, qt=None) -> int:
    """Dibuja lo que la herramienta activa pide resaltar (``tool.resaltado``).
    Devuelve cuántos trazos dibujó. ``qt`` = (QPen, QColor, QPointF, Qt)
    para las pruebas; en IngeCAD se importan de PySide6."""
    from . import seleccion

    delegate = getattr(viewport, "tool_delegate", None)
    tool = getattr(delegate, "tool", None)
    fn = getattr(tool, "resaltado", None)
    datos = dict(fn(_cursor_resuelto(delegate))) if fn is not None else {}
    if seleccion.en_modo(delegate):        # la ventana / polígono / borde de la selección
        datos.update(seleccion.resaltado(delegate, getattr(delegate, "_cursor", None)))
    if not any(datos.values()):
        return 0
    if qt is None:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QPen
    else:
        QPen, QColor, QPointF, Qt = qt
    hechos = 0
    painter.save()
    try:
        for capa, (rgba, ancho, punteado) in ESTILO_RESALTADO.items():
            segs = datos.get(capa) or ()
            if not segs:
                continue
            painter.setPen(QPen(QColor(*rgba), ancho, Qt.DashLine if punteado else Qt.SolidLine))
            for (ax, ay), (bx, by) in segs:
                x1, y1 = viewport._space_to_screen(ax, ay)
                x2, y2 = viewport._space_to_screen(bx, by)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                hechos += 1
        puntos = datos.get("puntos") or ()
        if puntos:
            painter.setPen(QPen(QColor(*MARCA), 2, Qt.SolidLine))
            for x, y in puntos:                       # una X de 6 px en el corte
                sx, sy = viewport._space_to_screen(x, y)
                painter.drawLine(QPointF(sx - 6, sy - 6), QPointF(sx + 6, sy + 6))
                painter.drawLine(QPointF(sx - 6, sy + 6), QPointF(sx + 6, sy - 6))
                hechos += 1
        for (x, y), texto in datos.get("textos") or ():
            sx, sy = viewport._space_to_screen(x, y)
            painter.drawText(QPointF(sx + 12, sy + 22), texto)   # debajo, a la derecha
            hechos += 1
    finally:
        painter.restore()
    return hechos


def _envolver_snap_kinds(original):
    """Las herramientas de GeoCAD pueden sumar referencias a las activas
    mientras piden un punto (``tool.referencias_extra()``): PARTEENPUNTO suma
    Punto final, Medio, Intersección y Cuadrante. Con las referencias
    apagadas (F3) o una referencia de una vez (FIN, INT...) no se toca nada."""
    def snap_kinds(self):
        kinds = original(self)
        tool = getattr(self, "tool", None)
        extra = getattr(tool, "referencias_extra", None)
        if extra is None or getattr(self, "osnap_override", None) is not None:
            return kinds
        if not getattr(self, "osnap_on", False) and not getattr(tool, "REFERENCIAS_SIEMPRE", False):
            return kinds
        try:
            return frozenset(kinds) | frozenset(extra())
        except Exception:  # noqa: BLE001
            return kinds

    snap_kinds._puente_original = original
    snap_kinds._puente_fabrica = _envolver_snap_kinds
    return snap_kinds


def orto_suelto(tool) -> bool:
    """RECTANG pidiendo la otra esquina: ORTO no se aplica, como en AutoCAD.
    IngeCAD la llevaba a la horizontal o vertical de la primera esquina y el
    rectángulo quedaba sin alto o sin ancho («Zero-size rectangle»)."""
    return (type(tool).__name__ == "RectangTool"
            and getattr(tool, "_first", None) is not None
            and getattr(tool, "_await", None) is None)


def _envolver_resolved_point(original):
    def resolved_point(self, wx, wy, *args, **kwargs):
        tool = getattr(self, "tool", None)
        if (tool is None or not orto_suelto(tool)
                or not _activo(getattr(self, "window", None))):
            return original(self, wx, wy, *args, **kwargs)
        orto = getattr(self, "ortho_on", False)
        self.ortho_on = getattr(self, "shift_held", False)   # ORTO efectivo = apagado
        try:
            return original(self, wx, wy, *args, **kwargs)
        finally:
            self.ortho_on = orto

    resolved_point._puente_original = original
    resolved_point._puente_fabrica = _envolver_resolved_point
    return resolved_point


def _envolver_vista(original):
    def _draw_tool_preview(self, p):
        original(self, p)
        try:
            dibujar_resaltado(self, p)
        except Exception:  # noqa: BLE001 -- un resaltado nunca rompe el dibujo
            pass

    _draw_tool_preview._puente_original = original
    _draw_tool_preview._puente_fabrica = _envolver_vista
    return _draw_tool_preview


def instalar() -> None:
    """Se llama al cargar el plugin. Sin interfaz (pruebas) no hace nada."""
    try:
        from views.tool_controller import ToolController
        from views.main_window import MainWindow
    except Exception:
        return
    if getattr(ToolController.on_text, "_puente_fabrica", None) is _envolver_on_text:
        return                       # ya está, y es de este mismo módulo
    deshacer_ajuste_1x()
    envolver(ToolController, "on_text", _envolver_on_text, reemplazar=True)
    envolver(MainWindow, "on_canvas_right_click", _envolver_clic_derecho, reemplazar=True)
    from . import bloques
    envolver(MainWindow, "on_canvas_double_click", bloques._envolver_doble_clic, reemplazar=True)
    envolver(MainWindow, "_cmd_undo", bloques._envolver_deshacer, reemplazar=True)
    envolver(MainWindow, "_write_document", bloques._envolver_escribir, reemplazar=True)
    envolver(MainWindow, "maybe_save_changes", bloques._envolver_cerrar, reemplazar=True)
    envolver(ToolController, "start_tool", _envolver_start_tool, reemplazar=True)
    envolver(ToolController, "snap_kinds", _envolver_snap_kinds, reemplazar=True)
    envolver(ToolController, "resolved_point", _envolver_resolved_point, reemplazar=True)
    try:
        from views.viewport import Viewport
    except Exception:
        return
    envolver(Viewport, "_draw_tool_preview", _envolver_vista, reemplazar=True)


# ------------------------------------------------------------- comandos
def _estado() -> str:
    if not relativo():
        return "Ángulos relativos: DESACTIVADOS (ángulo absoluto, 0 = este, antihorario)."
    if modo() == "interior":
        return ("Ángulos relativos: ACTIVADOS, ángulo INTERIOR desde el tramo anterior, "
                "antihorario (180 = recto). @d<<a fuerza absoluto.")
    return ("Ángulos relativos: ACTIVADOS, desde la DIRECCIÓN del tramo anterior, "
            "antihorario (0 = recto). @d<<a fuerza absoluto.")


def cmd_angrel(ctx, *args) -> None:
    """ANGREL [A | D | I | DIR]: activa o desactiva los ángulos relativos,
    o elige el modo. Sin argumento, alterna activado/desactivado."""
    arg = (args[0] if args else "").strip().upper()
    if arg in ("A", "ACTIVAR", "ON", "SI", "SÍ"):
        set_relativo(True)
    elif arg in ("D", "DESACTIVAR", "OFF", "NO"):
        set_relativo(False)
    elif arg in ("I", "INTERIOR"):
        set_relativo(True)
        set_modo("interior")
    elif arg in ("DIR", "DIRECCION", "DIRECCIÓN"):
        set_relativo(True)
        set_modo("direccion")
    elif arg == "":
        set_relativo(not relativo())
    else:
        ctx.echo("ANGREL: opciones A (activar), D (desactivar), I (interior), DIR (dirección).")
    ctx.echo(_estado())


def cmd_boton_derecho(ctx, *args) -> None:
    """BOTONDERECHO: prende o apaga «botón derecho = Enter»."""
    set_boton_derecho(not boton_derecho())
    if boton_derecho():
        ctx.echo("Botón derecho = Enter (repite la última orden). Ctrl + botón derecho: menú.")
    else:
        ctx.echo("Botón derecho como venía en IngeCAD (Herramientas > Opciones).")


COMMANDS = {"ANGREL": cmd_angrel, "RIGHTCLICK": cmd_boton_derecho}
