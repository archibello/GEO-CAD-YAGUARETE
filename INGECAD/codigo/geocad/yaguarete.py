# SPDX-License-Identifier: GPL-3.0-or-later
"""La barra «Yaguareté Tools» y los carteles de los botones (3.13.0).

Barra: las herramientas de IngeCAD que GeoCAD mejoró pasan a una barra
propia y salen de la barra de IngeCAD donde estaban (Dibujo o Modificar),
para que se vea qué es de GeoCAD. Cada una depende de su módulo: apagado el
módulo, el botón vuelve a su barra de IngeCAD. Los menús de IngeCAD no se
tocan (ya llaman a la versión de GeoCAD). Sin GeoCAD, todo como venía.

Carteles: al dejar el cursor sobre un botón de cualquier barra, al segundo
aparece un cartel como el de AutoCAD: el nombre, qué hace y la orden.
IngeCAD ya ponía un cartel corto («Empalme (FILLET)») que Qt muestra a los
0,7 s; mientras GeoCAD está activo, se muestra éste en su lugar.

La parte sin Qt (qué va en la barra, el texto del cartel) se prueba sola.
"""
from __future__ import annotations

import html
import re

NOMBRE_BARRA = "Yaguareté Tools"
OBJETO_BARRA = "geocad_yaguarete_toolbar"
ESPERA_MS = 1000                      # el cartel sale al segundo, como AutoCAD

#: (orden, módulo que la mejora o "" = siempre con GeoCAD, barra de IngeCAD
#: de donde sale o None si es una orden nueva de GeoCAD), en el orden de la barra
HERRAMIENTAS = (
    ("RECTANG", "", "draw_toolbar"),
    ("TEXT", "texto", "draw_toolbar"),
    ("STRETCH", "estirar", "modify_toolbar"),
    ("BREAKATPOINT", "partir", None),
    ("CHAMFER", "chaflan", "modify_toolbar"),
    ("FILLET", "empalme", "modify_toolbar"),
)

#: el nombre del botón cuando no sale de una barra de IngeCAD
ETIQUETAS = {
    "FILLET": "AutoCAD-style fillet (FILLET)",
    "CHAMFER": "AutoCAD-style chamfer (CHAMFER)",
    "BREAKATPOINT": "Break at point (BREAKATPOINT)",
}

#: qué hace cada orden, en una línea (la segunda del cartel)
DESCRIPCIONES = {
    # Dibujo
    "LINE": "Dibuja tramos de línea recta, uno detrás de otro.",
    "PLINE": "Dibuja una polilínea: tramos rectos y arcos en un solo objeto.",
    "CIRCLE": "Dibuja un círculo por centro y radio, diámetro o puntos.",
    "ARC": "Dibuja un arco de circunferencia.",
    "REVCLOUD": "Dibuja una nube de revisión alrededor de lo que se marca.",
    "SPLINE": "Dibuja una curva suave que pasa por los puntos elegidos.",
    "ELLIPSE": "Dibuja una elipse o un arco de elipse.",
    "RECTANG": "Dibuja un rectángulo con dos esquinas opuestas (con ORTO, como AutoCAD).",
    "POLYGON": "Dibuja un polígono regular inscrito o circunscrito.",
    "POINT": "Ubica un punto.",
    "TEXT": "Texto de una línea: 1er punto ubica, 2º da la altura, 3º la dirección.",
    "MTEXT": "Escribe un texto de varias líneas con formato.",
    "HATCH": "Rellena un área cerrada con un sombreado o un color.",
    # Modificar
    "ERASE": "Borra los objetos elegidos.",
    "COPY": "Copia objetos de un punto base a otro.",
    "MIRROR": "Refleja objetos respecto de un eje.",
    "OFFSET": "Hace una copia paralela a una distancia.",
    "ARRAY": "Copia objetos en filas y columnas o alrededor de un centro.",
    "MOVE": "Desplaza objetos de un punto base a otro.",
    "ROTATE": "Gira objetos alrededor de un punto base.",
    "SCALE": "Agranda o achica objetos desde un punto base.",
    "STRETCH": "Estira lo que toma la ventana de captura; muestra el resultado antes del clic.",
    "TRIM": "Recorta objetos contra los bordes elegidos.",
    "EXTEND": "Alarga objetos hasta los bordes elegidos.",
    "BREAK": "Quita el pedazo de un objeto entre dos puntos.",
    "JOIN": "Une objetos en uno solo.",
    "CHAMFER": "Bisela la esquina entre dos objetos; por defecto, ochava de largo dado.",
    "FILLET": "Redondea la esquina entre dos objetos; también polilíneas, del lado elegido.",
    "EXPLODE": "Descompone un objeto compuesto en sus partes.",
    # GeoCAD
    "BREAKATPOINT": "Corta un objeto en un punto elegido con referencias; muestra los dos pedazos.",
    "SELECT": "Elige objetos con las opciones de AutoCAD (W, C, WP, CP, F...).",
    "GEOFILTER": "Elige objetos por tipo, capa, color, medidas, textos y datos de QGIS.",
    "GEODRAWFRONT": "Lo elegido se dibuja encima de todo: líneas, sombreados, textos, bloques.",
    "GEODRAWBACK": "Lo elegido se dibuja debajo de todo: líneas, sombreados, textos, bloques.",
    "BLOCK": "Crea un bloque con los objetos elegidos y su punto base.",
    "INSERT": "Inserta un bloque, con vista previa.",
    "GEOREFEDIT": "Edita un bloque en el lugar (también con doble clic).",
    "GEOBLOCKBASE": "Cambia el punto base de un bloque.",
    "GEOPREVIEW": "Muestra la presentación como sale impresa.",
    "GEOPLOTSTYLES": "Edita la tabla de plumas (.ctb): color, grosor y tramado de impresión.",
    "GEODIMSETUP": "Arma un estilo de cota con la escala del papel.",
    "DIMLINEAR": "Acota una distancia horizontal o vertical.",
    "DIMALIGNED": "Acota una distancia paralela a los puntos elegidos.",
    "DIMANGULAR": "Acota el ángulo entre dos líneas o tramos.",
    "SHPTABLE": "Abre la tabla de atributos de la capa.",
    "SHPQUERY": "Elige objetos según sus atributos.",
    "SHPSPATIAL": "Elige objetos según dónde están respecto de otros.",
    "SHPTHEME": "Colorea los objetos según un campo (mapa temático).",
    "SHPLABEL": "Rotula los objetos con un campo.",
    "SHPNEW": "Dibuja un objeto nuevo y carga sus datos en un formulario.",
    "QGISSAVESEL": "Devuelve a QGIS sólo lo elegido.",
    "QGISSAVE": "Devuelve a QGIS todas las capas con los cambios.",
}

_ORDEN_AL_FINAL = re.compile(r"\s*\(([^()]+)\)\s*$")


def elegidas(estado: dict) -> list:
    """[(orden, barra de origen)] de la barra, según los módulos activos."""
    return [(orden, origen) for orden, modulo, origen in HERRAMIENTAS
            if not modulo or estado.get(modulo, False)]


def separar_orden(texto: str):
    """«Empalme (FILLET)» -> («Empalme», «FILLET»); sin orden, (texto, None)."""
    texto = (texto or "").strip()
    m = _ORDEN_AL_FINAL.search(texto)
    if m is None:
        return texto, None
    return texto[:m.start()].strip(), m.group(1).strip()


def nombre_local(orden: str, nombres=None) -> str:
    """La orden como se escribe en el idioma de IngeCAD (FILLET -> EMPALME)."""
    if nombres is None:
        try:
            from core.i18n import command_names
            nombres = command_names()
        except Exception:  # noqa: BLE001
            nombres = {}
    candidatas = [t for t, e in nombres.items() if e == orden]
    return max(candidatas, key=len) if candidatas else orden


def texto_cartel(nombre: str, orden: str | None, nombres=None) -> str:
    """El cartel, como el de AutoCAD: nombre en negrita, qué hace, la orden."""
    partes = [f"<b>{html.escape(nombre)}</b>"]
    if orden:
        descripcion = DESCRIPCIONES.get(orden)
        if descripcion:
            partes.append(html.escape(descripcion))
        partes.append(f"<span style='color:gray'>Orden: {html.escape(nombre_local(orden, nombres))}</span>")
    return "<br>".join(partes)


# -- Qt -------------------------------------------------------------------------------
def _orden_de(accion):
    """La orden de un botón de IngeCAD (su cartel termina en «(ORDEN)»)."""
    orden = accion.property("geocad_orden")
    if orden:
        return orden
    _nombre, orden = separar_orden(accion.toolTip())
    if orden:
        accion.setProperty("geocad_orden", orden)
    return orden


def _barras_ingecad(window):
    from PySide6.QtWidgets import QToolBar
    return {b.objectName(): b for b in window.findChildren(QToolBar)}


def armar(window, iconos=None) -> None:
    """Arma (o rearma) la barra según los módulos activos y saca esos
    botones de sus barras de IngeCAD. ``iconos``: {orden: ruta} propios."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import QToolBar

    from core.i18n import tr
    from views.icons import command_icon

    from . import modulos

    quitar(window)
    barras = _barras_ingecad(window)
    ocultas = []
    bar = QToolBar(NOMBRE_BARRA, window)
    bar.setObjectName(OBJETO_BARRA)
    bar.setMovable(True)
    for orden, origen in elegidas(modulos.estado("ingecad")):
        nativa = None
        for a in (barras[origen].actions() if origen in barras else ()):
            if _orden_de(a) == orden:
                nativa = a
                break
        if nativa is not None:
            icono, etiqueta = nativa.icon(), nativa.text()
            nativa.setVisible(False)
            ocultas.append(nativa)
        else:
            ruta = (iconos or {}).get(orden)
            icono = QIcon(str(ruta)) if ruta else command_icon(orden)
            etiqueta, _o = separar_orden(tr(ETIQUETAS.get(orden, orden)))
        act = QAction(icono, etiqueta, window)
        act.setToolTip(f"{etiqueta} ({orden})")
        act.setProperty("geocad_orden", orden)
        act.triggered.connect(lambda _=False, n=orden: window._invoke_command(n))
        bar.addAction(act)
    window.addToolBar(Qt.TopToolBarArea, bar)
    window._geocad_yaguarete = (bar, ocultas)
    instalar_carteles(window)


def quitar(window) -> None:
    """Saca la barra y devuelve los botones a sus barras de IngeCAD."""
    bar, ocultas = getattr(window, "_geocad_yaguarete", (None, []))
    for a in ocultas:
        try:
            a.setVisible(True)
        except RuntimeError:          # la acción ya no existe
            pass
    if bar is not None:
        window.removeToolBar(bar)
        bar.setParent(None)
        bar.deleteLater()
    window._geocad_yaguarete = (None, [])


def _filtro_carteles():
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QToolTip

    class Carteles(QObject):
        """Cuenta el segundo desde que el cursor entra al botón; el cartel
        corto de IngeCAD (evento ToolTip) no se muestra mientras tanto."""

        def __init__(self, parent):
            super().__init__(parent)
            self.botones = []
            self._boton = None
            self._reloj = QTimer(self)
            self._reloj.setSingleShot(True)
            self._reloj.setInterval(ESPERA_MS)
            self._reloj.timeout.connect(self._mostrar)

        def eventFilter(self, obj, ev):
            t = ev.type()
            if t == QEvent.Enter:
                self._boton = obj
                self._reloj.start()
            elif t == QEvent.ToolTip:
                if obj is self._boton and not self._reloj.isActive():
                    self._mostrar()           # sigue encima: el mismo cartel
                return True
            elif t in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Hide):
                if obj is self._boton:
                    self._reloj.stop()
                    self._boton = None
                    QToolTip.hideText()
            return False

        def _mostrar(self):
            b = self._boton
            try:
                if b is None or not b.underMouse():
                    return
                act = b.defaultAction()
            except RuntimeError:              # el botón ya no existe
                return
            if act is None:
                return
            nombre, orden = separar_orden(act.toolTip() or act.text())
            orden = act.property("geocad_orden") or orden
            QToolTip.showText(QCursor.pos(), texto_cartel(nombre or act.text(), orden), b)

    return Carteles


def instalar_carteles(window) -> None:
    """Pone el cartel en cada botón de cada barra (las que se agreguen
    después lo reciben al volver a llamar)."""
    from PySide6.QtWidgets import QToolBar, QToolButton

    filtro = getattr(window, "_geocad_carteles", None)
    if filtro is None:
        filtro = _filtro_carteles()(window)
        window._geocad_carteles = filtro
    for bar in window.findChildren(QToolBar):
        for act in bar.actions():
            b = bar.widgetForAction(act)
            if isinstance(b, QToolButton) and b not in filtro.botones:
                b.installEventFilter(filtro)
                filtro.botones.append(b)


def quitar_carteles(window) -> None:
    filtro = getattr(window, "_geocad_carteles", None)
    if filtro is None:
        return
    for b in filtro.botones:
        try:
            b.removeEventFilter(filtro)
        except RuntimeError:
            pass
    filtro.botones = []
    window._geocad_carteles = None
    filtro.deleteLater()
