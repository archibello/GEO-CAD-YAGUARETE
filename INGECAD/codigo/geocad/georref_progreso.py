# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanita de progreso con cuenta regresiva para GEORREF (3.21.2).

Rehacer una imagen grande y volver a dibujar la pantalla lleva unos
segundos; sin nada que se mueva, el operario no sabe si el programa se
colgó. Dos etapas, en la misma ventanita:

  1/2 «Rehaciendo la imagen... faltan unos 4 s»: el trabajo con PIL corre
      en un hilo aparte (PIL suelta el intérprete mientras calcula) y la
      ventana cuenta hacia atrás con lo que tardó la última vez por
      megapíxel en esta computadora;
  2/2 «Actualizando la pantalla... faltan unos 2 s»: la regeneración de
      IngeCAD, con lo que tardó su última regeneración. La pide acá mismo
      si todavía no arrancó, y espera a que termine: así la imagen nueva
      siempre aparece sola.

Sin Qt (pruebas) el trabajo corre directo y no se muestra nada.
"""
from __future__ import annotations

import math
import threading
import time

#: segundos por megapíxel de imagen nueva, por cada archivo guardado (se
#: ajusta con lo medido en cada uso, mientras IngeCAD esté abierto)
_ritmo = [0.2]
#: tope de espera de la regeneración (después se sigue igual)
MAX_REGEN = 300.0


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return None
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtCore, QtWidgets


def estimar(megapixeles: float, archivos: int) -> float:
    return max(1.0, _ritmo[0] * megapixeles * max(1, archivos))


def texto_falta(estimado: float, pasado: float) -> str:
    """«faltan unos 4 s» / «falta 1 s» / «ya casi...» (si se pasó)."""
    resto = math.ceil(estimado - pasado)
    if resto <= 0:
        return "ya casi..."
    return "falta 1 s" if resto == 1 else f"faltan unos {resto} s"


class Progreso:
    """La ventanita (o nada, sin Qt). Uso:

        with Progreso(ventana, "GEORREF") as p:
            r = p.trabajo("Rehaciendo la imagen", fn, estimado)
            ...
            p.regeneracion(ventana)
    """

    def __init__(self, parent, titulo: str) -> None:
        self.parent, self.titulo = parent, titulo
        self.qt = _qt()
        self.dlg = None

    def __enter__(self):
        if self.qt is not None:
            QtCore, QtWidgets = self.qt
            d = QtWidgets.QProgressDialog(self.parent)
            d.setWindowTitle(f"{self.titulo} — GEO-CAD-YAGUARETÉ")
            d.setCancelButton(None)
            d.setRange(0, 100)
            d.setMinimumDuration(0)
            d.setMinimumWidth(420)
            d.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            d.setAutoClose(False)
            d.setAutoReset(False)
            d.show()
            self.dlg = d
            QtWidgets.QApplication.processEvents()
        return self

    def __exit__(self, *_exc):
        self.cerrar()
        return False

    def cerrar(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg = None

    def _mostrar(self, etapa: str, estimado: float, pasado: float, base: int, ancho: int,
                 hecho=None) -> None:
        if self.dlg is None:
            return
        if hecho is not None:
            # avance real (ASPECTOIMAGEN, 3.31.2): el trabajo dice cuánto lleva
            parte = min(1.0, max(0.0, float(hecho[0])))
            self.dlg.setLabelText(f"{etapa}... {int(parte * 100)} %")
            self.dlg.setValue(base + int(ancho * parte))
            return
        self.dlg.setLabelText(f"{etapa}... {texto_falta(estimado, pasado)}")
        avance = min(0.97, pasado / estimado) if estimado > 0 else 0.0
        self.dlg.setValue(base + int(ancho * avance))

    def _esperar(self, listo, etapa, estimado, base, ancho, tope=None, hecho=None) -> None:
        """Gira el bucle de Qt (la ventana se mueve) hasta que ``listo()``."""
        QtCore, QtWidgets = self.qt
        t0 = time.monotonic()
        while not listo():
            pasado = time.monotonic() - t0
            if tope is not None and pasado > tope:
                return
            self._mostrar(etapa, estimado, pasado, base, ancho, hecho)
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.05)

    def trabajo(self, etapa: str, fn, estimado: float, base: int = 0, ancho: int = 70,
                hecho=None):
        """Corre ``fn()`` (en un hilo, con la cuenta regresiva) y devuelve lo
        que devuelve; sus errores se levantan acá. Con ``hecho`` (una lista
        [0..1] que ``fn`` va llenando) la barra muestra el avance real."""
        if self.qt is None:
            return fn()
        out = {}

        def correr():
            try:
                out["r"] = fn()
            except BaseException as exc:  # noqa: BLE001 -- se levanta en el hilo principal
                out["e"] = exc

        hilo = threading.Thread(target=correr, daemon=True)
        hilo.start()
        self._esperar(lambda: not hilo.is_alive(), etapa, estimado, base, ancho, hecho=hecho)
        hilo.join()
        if "e" in out:
            raise out["e"]
        if self.dlg is not None:
            self.dlg.setValue(base + ancho)
        return out["r"]

    def regeneracion(self, ventana, handle=None, base: int = 70, ancho: int = 30,
                     etapa: str = "2/2  Actualizando la pantalla") -> None:
        """Espera a que IngeCAD vuelva a dibujar la pantalla con la imagen
        nueva; si no arrancó a regenerar, se lo pide (ocultando antes la
        textura vieja de la imagen)."""
        if self.qt is None or ventana is None or not hasattr(ventana, "regen_in_memory"):
            return
        _QtCore, QtWidgets = self.qt
        QtWidgets.QApplication.processEvents()          # lo que dejó pendiente el comando
        if getattr(ventana, "_regen_worker", None) is None:
            pedir_regeneracion(ventana, handle)
        capa = getattr(ventana, "_active_layout", None)
        ms = (getattr(ventana, "_regen_ms", None) or {}).get(capa)
        estimado = max(1.0, (ms or 2000.0) / 1000.0)
        self._esperar(lambda: getattr(ventana, "_regen_worker", None) is None,
                      etapa, estimado, base, ancho, tope=MAX_REGEN)
        if self.dlg is not None:
            self.dlg.setValue(100)


def pedir_regeneracion(ventana, handle=None) -> None:
    """Oculta la textura vieja de la imagen y regenera: IngeCAD sólo corre
    las esquinas de la textura que ya tiene y nunca relee el archivo."""
    if handle is not None:
        try:
            ventana.viewport.hide_handles([handle])
        except Exception:  # noqa: BLE001
            pass
    regen = getattr(ventana, "regen_in_background", None) or ventana.regen_in_memory
    regen()


def medir(megapixeles: float, archivos: int, segundos: float) -> None:
    """Aprende el ritmo de esta computadora para la próxima cuenta."""
    if megapixeles > 0.5 and segundos > 0:
        _ritmo[0] = segundos / (megapixeles * max(1, archivos))
