"""El título «GeoCAD Yaguareté» en la barra de menús, con el color de su menú
(Fernando, 12/11/2026: «para que se distinga de los del programa original»).

Sirve a los dos programas: IngeCAD (PySide6) y QGIS (qgis.PyQt); el Qt se toma
de la misma barra. Qt no deja pintar un solo ítem de la barra con hoja de
estilo, así que encima de NUESTRO ítem va un rótulo propio, transparente al
mouse (los clics y el resaltado siguen siendo de la barra). Los demás ítems
quedan como vienen. ``quitar`` lo saca sin dejar rastro.
"""
from __future__ import annotations

import importlib

# 3.78.2: las referencias van ACÁ y no colgadas de la barra. En QGIS la barra
# la crea C++: cuando Python suelta su envoltorio, lo colgado de él se pierde,
# el rótulo quedaba como un QWidget sin pintar (blanco) y con la medida vieja.
_VIVOS = []
_NOMBRE = "geocad_color_barra"          # rótulo y filtro, para hallar los de otra versión


def _qt(barra):
    paquete = type(barra).__module__.rsplit(".", 1)[0]       # PySide6 / PyQt5 / PyQt6
    return tuple(importlib.import_module(paquete + m) for m in (".QtCore", ".QtGui", ".QtWidgets"))


def _limpio(texto: str) -> str:
    return texto.replace("&&", "\0").replace("&", "").replace("\0", "&")


def accion_nuestra(barra, es_nuestro):
    for accion in barra.actions():
        if accion.menu() is not None and accion.isVisible() and es_nuestro(_limpio(accion.text())):
            return accion
    return None


def _clases(QtCore, QtGui, QtWidgets):
    class Rotulo(QtWidgets.QWidget):
        """Lo que se ve encima de nuestro ítem."""
        def __init__(self, barra):
            super().__init__(barra)
            self.setObjectName(_NOMBRE)
            self.barra, self.accion, self.colores = barra, None, ("#000", "#000", "#fff")
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            # pinta todo su rectángulo: la barra no se repinta debajo (si no, se llamarían en ronda)
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        def paintEvent(self, ev):  # noqa: N802 - nombre de Qt
            try:
                if self.accion is None:
                    return
                fondo, resaltado, letra = self.colores
                activo = self.barra.activeAction() is self.accion
                p = QtGui.QPainter(self)
                try:
                    p.fillRect(self.rect(), QtGui.QColor(resaltado if activo else fondo))
                    p.setPen(QtGui.QColor(letra))
                    p.setFont(self.barra.font())
                    p.drawText(self.rect(), int(QtCore.Qt.AlignmentFlag.AlignCenter), _limpio(self.accion.text()))
                finally:
                    p.end()
            except Exception:  # noqa: BLE001 - nunca tira abajo al programa
                pass

    class Filtro(QtCore.QObject):
        """Sigue a la barra: dónde quedó nuestro ítem y si está resaltado."""
        MOVER = {QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show, QtCore.QEvent.Type.LayoutRequest,
                 QtCore.QEvent.Type.ActionAdded, QtCore.QEvent.Type.ActionRemoved,
                 QtCore.QEvent.Type.ActionChanged, QtCore.QEvent.Type.FontChange,
                 QtCore.QEvent.Type.StyleChange}

        def __init__(self, barra, es_nuestro, colores):
            super().__init__(barra)
            self.setObjectName(_NOMBRE)
            self.barra, self.es_nuestro = barra, es_nuestro
            self.rotulo = Rotulo(barra)
            self.rotulo.colores = colores
            self._pendiente = False

        @property
        def colores(self):
            return self.rotulo.colores

        @colores.setter
        def colores(self, valor):
            self.rotulo.colores = valor

        def eventFilter(self, obj, ev):  # noqa: N802 - nombre de Qt
            try:
                if ev.type() in self.MOVER and not self._pendiente:
                    self._pendiente = True
                    QtCore.QTimer.singleShot(0, self.ubicar)
                elif ev.type() == QtCore.QEvent.Type.Paint:
                    self.rotulo.update()          # resaltado al pasar el mouse o abrir el menú
                    if not self._pendiente and self._corrido():
                        self._pendiente = True    # la barra cambió de medida sin avisar
                        QtCore.QTimer.singleShot(0, self.ubicar)
            except Exception:  # noqa: BLE001
                pass
            return False

        def _corrido(self):
            accion = accion_nuestra(self.barra, self.es_nuestro)
            if accion is not self.rotulo.accion:
                return True
            return accion is not None and self.barra.actionGeometry(accion) != self.rotulo.geometry()

        def ubicar(self):
            self._pendiente = False
            try:
                accion = accion_nuestra(self.barra, self.es_nuestro)
                rect = self.barra.actionGeometry(accion) if accion is not None else None
                self.rotulo.accion = accion
                if rect is None or rect.isEmpty():
                    self.rotulo.hide()
                    return
                if self.rotulo.geometry() != rect:
                    self.rotulo.setGeometry(rect)
                self.rotulo.show()
                self.rotulo.raise_()
                self.rotulo.update()
            except Exception:  # noqa: BLE001
                pass
    return Filtro


def _filtro_de(barra):
    """El filtro ya puesto en esta barra (y se olvidan los de barras que ya no existen)."""
    for filtro in list(_VIVOS):
        try:
            if filtro.barra is barra:
                return filtro
            filtro.barra.objectName()                 # ¿sigue viva?
        except RuntimeError:                          # la borró Qt (se cerró la ventana)
            _VIVOS.remove(filtro)
    return None


def _retirar_otros(barra) -> None:
    """Rótulos y filtros de otra carga del módulo (actualizar sin reiniciar)."""
    for hijo in list(barra.children()):
        if hijo.objectName() == _NOMBRE:
            barra.removeEventFilter(hijo)
            if hasattr(hijo, "hide"):
                hijo.hide()
            hijo.deleteLater()


def instalar(barra, es_nuestro, fondo: str, resaltado: str, letra: str) -> bool:
    """Pinta nuestro ítem de la barra (una sola vez por barra; los colores se
    actualizan si cambian)."""
    try:
        if barra is None:
            return False
        colores = (fondo, resaltado, letra)
        filtro = _filtro_de(barra)
        if filtro is not None:
            filtro.es_nuestro, filtro.colores = es_nuestro, colores
        else:
            _retirar_otros(barra)
            filtro = _clases(*_qt(barra))(barra, es_nuestro, colores)
            barra.installEventFilter(filtro)
            _VIVOS.append(filtro)
        filtro.ubicar()
        return True
    except Exception:  # noqa: BLE001
        return False


def quitar(barra) -> None:
    try:
        filtro = _filtro_de(barra)
        if filtro is not None:
            barra.removeEventFilter(filtro)
            _VIVOS.remove(filtro)
            filtro.rotulo.hide()
            filtro.rotulo.deleteLater()
            filtro.deleteLater()
            barra.update()
    except Exception:  # noqa: BLE001
        pass
