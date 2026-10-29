# SPDX-License-Identifier: GPL-3.0-or-later
"""Perpendicular y Apparent Intersection con guías de puntos en IngeCAD (3.56.0).

Pedido de Fernando (29/10/2026): «extender las líneas con líneas de punto
hasta un punto flotante que se produce donde debería concretarse la
operación», en las dos plataformas. Con Perpendicular o Apparent
Intersection (del menú de Mayús + clic derecho, escritas PER / APP, o APP
entre las referencias activas):

- pasar por encima de una línea la usa al momento; detenerse medio segundo
  la TOMA y queda (marcada en verde) aunque el cursor se vaya; la tercera
  reemplaza a la más vieja (APP toma dos, PER una);
- la línea que no llega se prolonga con trazo de puntos hasta el punto
  flotante (el pie de la perpendicular, el cruce aparente), y el clic pone
  el punto ahí, aunque esté lejos del cursor;
- APP sale del gris en IngeCAD; con dos paralelas no hay punto.

Las cuentas están en guias.py (las mismas que en QGIS). Acá: envoltorios
de ToolController (on_hover, clear_tracking) y del Viewport (las guías y la
marca de APP), y Apparent Intersection disponible en core.osnap. Apagado
el módulo, IngeCAD queda como venía (APP en gris).
"""
from __future__ import annotations

import dataclasses

from . import guias as G
from . import modulos
from .dibujo import envolver

PROGRAMA = "ingecad"
COLOR_GUIA = (255, 170, 40)      # el de las guías de IngeCAD (TRACK_COLOR)
COLOR_TOMADA = (80, 200, 80)
_MODOS_ORIGINALES = None


def activo() -> bool:
    return modulos.activo(PROGRAMA, "referencias")


# ------------------------------------------------------------- APP disponible
def aplicar_modos(osnap=None) -> None:
    """Apparent Intersection disponible (módulo prendido) o en gris, como
    viene en IngeCAD (apagado). Cambia MODES, BY_KEY y AVAILABLE de core.osnap."""
    global _MODOS_ORIGINALES
    if osnap is None:
        try:
            from core import osnap
        except Exception:  # noqa: BLE001
            return
    if _MODOS_ORIGINALES is None or _MODOS_ORIGINALES[0] is not osnap:
        _MODOS_ORIGINALES = (osnap, osnap.MODES)
    originales = _MODOS_ORIGINALES[1]
    if activo():
        modos = tuple(dataclasses.replace(m, available=True, note="") if m.key == "APP" else m
                      for m in originales)
    else:
        modos = originales
    if osnap.MODES == modos:
        return
    osnap.MODES = modos
    osnap.BY_KEY = {m.key: m for m in modos}
    osnap.AVAILABLE = frozenset(m.key for m in modos if m.available)


# ------------------------------------------------------------- el cálculo
def tramos_cerca(ctrl, cursor, umbral):
    """Los tramos rectos del dibujo (y de lo que el comando está dibujando)
    cerca del cursor, en las coordenadas del espacio."""
    eng = getattr(ctrl, "snap_engine", None)
    salida = []
    cx, cy = cursor
    if eng is not None:
        if getattr(eng, "_dirty", False):
            eng._build()
        segs = getattr(eng, "_segs", ())
        b = getattr(eng, "_seg_bounds", None)
        if len(segs) and b is not None and len(b) == len(segs):
            cerca = ((b[:, 0] - umbral <= cx) & (b[:, 2] + umbral >= cx)
                     & (b[:, 1] - umbral <= cy) & (b[:, 3] + umbral >= cy))
            salida.extend(tuple(float(v) for v in s[:4]) for s in segs[cerca])
    tool = getattr(ctrl, "tool", None)
    fn = getattr(tool, "drawn_segments", None)
    if fn is not None:
        try:
            salida.extend(tuple(float(v) for v in s[:4]) for s in (fn() or ()))
        except Exception:  # noqa: BLE001
            pass
    return salida


def _modo(ctrl, kinds):
    """"PER", "APP" o None: lo que la guía tiene que resolver ahora."""
    override = getattr(ctrl, "osnap_override", None)
    if override is not None:
        for m in ("APP", "PER"):
            if m in override:
                return m
        return None
    # entre las referencias activas: sólo APP (PER activo sigue como en IngeCAD)
    return "APP" if "APP" in kinds else None


def _estado(ctrl, modo):
    """Las líneas tomadas del controlador, para este modo."""
    t = getattr(ctrl, "_geocad_tomadas", None)
    if t is None or t.modo != modo:
        t = G.Tomadas(modo)
        ctrl._geocad_tomadas = t
    return t


def _reloj(ctrl):
    r = getattr(ctrl, "_geocad_reloj", None)
    if r is None:
        from PySide6.QtCore import QTimer

        r = QTimer(ctrl)
        r.setSingleShot(True)
        r.setInterval(G.TOMA_MS)
        r.timeout.connect(lambda: _tomar(ctrl))
        ctrl._geocad_reloj = r
    return r


def _tomar(ctrl) -> None:
    t = getattr(ctrl, "_geocad_tomadas", None)
    if t is None or not t.tomar():
        return
    ultimo = getattr(ctrl, "_geocad_ultimo", None)
    if ultimo is not None:
        args, kwargs = ultimo
        ctrl.on_hover(*args, **kwargs)
    try:
        ctrl.changed.emit()
    except Exception:  # noqa: BLE001
        pass


def guiar(ctrl, reloj=None) -> None:
    """Después del on_hover de IngeCAD: el punto flotante de PER / APP y sus
    guías. ``reloj``: un reemplazo del QTimer (las pruebas sin Qt)."""
    ctrl._geocad_guias = ([], [])
    if not activo():
        return
    cursor = getattr(ctrl, "_cursor", None)
    if cursor is None or getattr(ctrl, "snap_engine", None) is None or ctrl.tool is None:
        return
    kinds = ctrl.snap_kinds()
    modo = _modo(ctrl, kinds)
    if modo is None:
        ctrl._geocad_tomadas = None
        return
    umbral = getattr(ctrl, "_track_tolerance", None) or 0.0
    tomadas = _estado(ctrl, modo)
    encima = G.tramo_cercano(cursor, umbral, tramos_cerca(ctrl, cursor, umbral))
    r = reloj if reloj is not None else _reloj(ctrl)
    if tomadas.esperar(encima):
        r.start()
    elif tomadas.espera is None:
        r.stop()
    previo = ctrl.anchor_point() if hasattr(ctrl, "anchor_point") else ctrl.tool.last_point
    res = G.calcular(modo, tomadas, encima, previo)
    if res is None:
        ctrl._geocad_guias = ([], list(tomadas.lista))
        return              # lo que IngeCAD encontró queda (APP: el cruce real, INT)
    actual = ctrl.snap_hit
    override = getattr(ctrl, "osnap_override", None) is not None
    if not override and actual is not None:
        ctrl._geocad_guias = ([], list(tomadas.lista))
        return              # APP activa: otra referencia más cerca gana
    from core.snap import SnapHit

    (x, y), guias, _usados = res
    ctrl.snap_hit = SnapHit(float(x), float(y), modo)
    ctrl._geocad_guias = (guias, list(tomadas.lista))


# ------------------------------------------------------------- envoltorios
def _envolver_on_hover(original):
    def on_hover(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._geocad_ultimo = (args, kwargs)
        try:
            guiar(self)
        except Exception:  # noqa: BLE001 -- una guía nunca traba el cursor
            self._geocad_guias = ([], [])

    on_hover._puente_original = original
    on_hover._puente_fabrica = _envolver_on_hover
    return on_hover


def _envolver_clear_tracking(original):
    def clear_tracking(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self._geocad_tomadas = None        # con el punto se sueltan las tomadas
        self._geocad_guias = ([], [])
        r = getattr(self, "_geocad_reloj", None)
        if r is not None:
            r.stop()

    clear_tracking._puente_original = original
    clear_tracking._puente_fabrica = _envolver_clear_tracking
    return clear_tracking


def _envolver_menu(original):
    def osnap_override_menu(self, *args, **kwargs):
        aplicar_modos()
        return original(self, *args, **kwargs)

    osnap_override_menu._puente_original = original
    osnap_override_menu._puente_fabrica = _envolver_menu
    return osnap_override_menu


def dibujar_guias(viewport, p, delegate, qt=None) -> int:
    """Las líneas tomadas (verde) y las prolongaciones de puntos hasta el
    punto flotante. Devuelve cuántos trazos dibujó. ``qt`` = (QPen, QColor,
    QPointF, Qt) para las pruebas."""
    guias, tomadas = getattr(delegate, "_geocad_guias", None) or ([], [])
    if not guias and not tomadas:
        return 0
    if qt is None:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QPen
    else:
        QPen, QColor, QPointF, Qt = qt
    n = 0
    p.save()
    try:
        p.setPen(QPen(QColor(*COLOR_TOMADA), 3))
        for t in tomadas:
            a = viewport._space_to_screen(t[0], t[1])
            b = viewport._space_to_screen(t[2], t[3])
            p.drawLine(QPointF(*a), QPointF(*b))
            n += 1
        p.setPen(QPen(QColor(*COLOR_GUIA), 2, Qt.DotLine))
        for a, b in guias:
            p.drawLine(QPointF(*viewport._space_to_screen(*a)),
                       QPointF(*viewport._space_to_screen(*b)))
            n += 1
    finally:
        p.restore()
    return n


def _envolver_draw_tracking(original):
    def _draw_tracking(self, p, delegate, *args, **kwargs):
        original(self, p, delegate, *args, **kwargs)
        try:
            dibujar_guias(self, p, delegate)
        except Exception:  # noqa: BLE001 -- una guía nunca rompe el dibujo
            pass

    _draw_tracking._puente_original = original
    _draw_tracking._puente_fabrica = _envolver_draw_tracking
    return _draw_tracking


def _envolver_marca(original):
    def _draw_snap_marker(self, p, kind, x, y, *args, **kwargs):
        if kind != "APP":
            return original(self, p, kind, x, y, *args, **kwargs)
        # la marca de AutoCAD para Apparent Intersection: un cuadrado con una X
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPen

        s = self.MARKER_SIZE / 2.0
        p.setPen(QPen(self.MARKER_COLOR, 2))
        p.drawRect(x - s, y - s, 2 * s, 2 * s)
        p.drawLine(QPointF(x - s, y - s), QPointF(x + s, y + s))
        p.drawLine(QPointF(x - s, y + s), QPointF(x + s, y - s))

    _draw_snap_marker._puente_original = original
    _draw_snap_marker._puente_fabrica = _envolver_marca
    return _draw_snap_marker


def instalar() -> None:
    """Se llama al abrir un dibujo. Los envoltorios miran ``activo()``."""
    try:
        from views.tool_controller import ToolController
        from views.main_window import MainWindow
        from views.viewport import Viewport
    except Exception:  # noqa: BLE001
        return
    aplicar_modos()
    envolver(ToolController, "on_hover", _envolver_on_hover, reemplazar=True)
    envolver(ToolController, "clear_tracking", _envolver_clear_tracking, reemplazar=True)
    envolver(MainWindow, "osnap_override_menu", _envolver_menu, reemplazar=True)
    envolver(Viewport, "_draw_tracking", _envolver_draw_tracking, reemplazar=True)
    envolver(Viewport, "_draw_snap_marker", _envolver_marca, reemplazar=True)
