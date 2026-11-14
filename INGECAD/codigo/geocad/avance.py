# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanita de avance por etapas para los trabajos largos (3.79.0).

SHPLABEL tarda unos 6 s en ubicar 1373 rótulos y IMPORTARSHP, con 20 000
polígonos con base de datos, unos 11 s entre leer, agregar y redibujar: sin
nada que se mueva, el operario no sabe si el programa responde. Esto muestra
la etapa, cuántos objetos van y el porcentaje:

    «1/3  Ubicando rótulos... 640 de 1373 (47 %)»

* Todo corre en el hilo principal (nada toca el dibujo desde otro hilo): el
  trabajo llama a ``paso()`` por cada objeto y cada décima de segundo la
  ventana se vuelve a pintar.
* Cancelar: sólo en las etapas que todavía no escribieron nada. ``paso()``
  levanta :class:`Cancelado` y el dibujo queda como estaba. En las que
  escriben o redibujan, el botón queda apagado.
* La ventana aparece recién si el trabajo pasa de ``demora`` segundos: lo
  corto no parpadea.

Sin Qt (pruebas) no se muestra nada, pero se cuenta igual (``registro``) y
``cancelar()`` simula el botón.
"""
from __future__ import annotations

import time

#: cada cuánto se repinta la ventana mientras se trabaja
REFRESCO = 0.1
#: tope de espera del redibujo de IngeCAD (después se sigue igual)
MAX_REGEN = 300.0


class Cancelado(Exception):
    """El operario apretó Cancelar en una etapa que no escribió nada."""


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return None
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtCore, QtWidgets


def texto_etapa(numero: int, etapas: int, texto: str, hechos: int, total: int) -> str:
    """«1/3  Ubicando rótulos... 640 de 1373 (47 %)»; sin total, sólo «...»."""
    cabeza = f"{numero}/{etapas}  {texto}..." if etapas > 1 else f"{texto}..."
    if total > 0:
        hechos = min(hechos, total)
        return f"{cabeza} {hechos} de {total} ({int(100 * hechos / total)} %)"
    return cabeza


class Avance:
    """Uso:

        with Avance(ventana, "SHPLABEL", etapas=2) as av:
            av.etapa("Ubicando rótulos", total=len(items))
            for ...:
                av.paso()                 # puede levantar Cancelado
            av.etapa("Escribiendo en el dibujo", cancelable=False)
            ...
            av.pantalla(ventana)          # espera el redibujo de IngeCAD
    """

    def __init__(self, parent, titulo: str, etapas: int = 1, demora: float = 0.4,
                 cancelar: bool = True) -> None:
        """``cancelar=False`` (3.80.0): ninguna etapa se puede cancelar (lo que
        llega de QGIS: el resto de la carga sigue igual)."""
        self.parent, self.titulo, self.etapas, self.demora = parent, titulo, etapas, demora
        self.permite_cancelar = cancelar
        self.qt = _qt()
        self.dlg = None
        self.numero = 0
        self.texto = ""
        self.total = 0
        self.hechos = 0
        self.cancelable = True
        self._cancelado = False
        self._t0 = time.monotonic()
        self._ultimo = 0.0
        self.registro: list = []          # [(número, texto, total)] de cada etapa (pruebas)

    # ------------------------------------------------------------ contexto
    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *_exc):
        self.cerrar()
        return False

    def cerrar(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg = None

    # ------------------------------------------------------------ trabajo
    def cancelar(self) -> None:
        """Lo que hace el botón Cancelar (sólo vale en etapas cancelables)."""
        if self.cancelable:
            self._cancelado = True

    @property
    def cancelado(self) -> bool:
        return self._cancelado

    def etapa(self, texto: str, total: int = 0, cancelable: bool = True) -> None:
        self.numero += 1
        self.texto, self.total, self.hechos = texto, max(0, int(total)), 0
        self.cancelable = cancelable and self.permite_cancelar
        self.registro.append((self.numero, texto, self.total))
        self._refrescar(forzar=True)

    def paso(self, hechos: int | None = None) -> None:
        """Un objeto más (o ``hechos`` en total). Levanta Cancelado si el
        operario canceló en una etapa cancelable."""
        self.hechos = self.hechos + 1 if hechos is None else int(hechos)
        ahora = time.monotonic()
        if ahora - self._ultimo >= REFRESCO:
            self._refrescar()
        if self._cancelado and self.cancelable:
            raise Cancelado()

    def contar(self, fabrica):
        """Envuelve una fábrica de AddToModelCommand: cada objeto que se
        agrega al dibujo cuenta un paso (la etapa que escribe)."""
        def make(msp):
            entidad = fabrica(msp)
            self.paso()
            return entidad
        return make

    # ------------------------------------------------------------ pantalla
    def _crear(self) -> None:
        QtCore, QtWidgets = self.qt
        # sin ventana (lo que llega de QGIS): sobre la ventana activa de IngeCAD
        d = QtWidgets.QProgressDialog(self.parent or QtWidgets.QApplication.activeWindow())
        d.setWindowTitle(f"{self.titulo} — GEO-CAD-YAGUARETÉ")
        d.setRange(0, 100)
        d.setMinimumDuration(0)
        d.setMinimumWidth(460)
        d.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        d.setAutoClose(False)
        d.setAutoReset(False)
        boton = QtWidgets.QPushButton("Cancelar")
        d.setCancelButton(boton)
        try:
            d.canceled.disconnect()       # que no se cierre sola: lo decide paso()
        except (RuntimeError, TypeError):
            pass
        d.canceled.connect(self.cancelar)
        d.show()
        self.dlg = d
        self._boton = boton

    def _refrescar(self, forzar: bool = False) -> None:
        self._ultimo = time.monotonic()
        if self.qt is None:
            return
        if self.dlg is None:
            if self._ultimo - self._t0 < self.demora:
                return
            self._crear()
        QtCore, QtWidgets = self.qt
        self.dlg.setLabelText(texto_etapa(self.numero, self.etapas, self.texto,
                                          self.hechos, self.total))
        if self.total > 0:
            self.dlg.setRange(0, 100)
            self.dlg.setValue(int(100 * min(self.hechos, self.total) / self.total))
        else:
            self.dlg.setRange(0, 0)       # sin cuenta: la barra va y viene
        self._boton.setEnabled(self.cancelable and not self._cancelado)
        # mientras se escribe, nada de clics sobre el dibujo a medio hacer
        bandera = (QtCore.QEventLoop.ProcessEventsFlag.AllEvents if self.cancelable
                   else QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        QtWidgets.QApplication.processEvents(bandera)

    def pantalla(self, ventana, texto: str = "Actualizando la pantalla", pedir: bool = True) -> None:
        """Etapa final: espera a que IngeCAD termine de redibujar. Con
        ``pedir``, si todavía no arrancó, se lo pide (una sola vez: antes
        IMPORTARSHP pedía un segundo redibujo encima del que IngeCAD ya había
        lanzado). Sin ``pedir`` (SHPLABEL) sólo espera el de IngeCAD."""
        self.etapa(texto, cancelable=False)
        if ventana is None:
            return
        if self.qt is None:
            if pedir:
                pedir_redibujo(ventana)
            return
        QtCore, QtWidgets = self.qt
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        if pedir:
            pedir_redibujo(ventana)
        t0 = time.monotonic()
        capa = getattr(ventana, "_active_layout", None)
        ms = (getattr(ventana, "_regen_ms", None) or {}).get(capa)
        estimado = max(1.0, (ms or 2000.0) / 1000.0)
        while getattr(ventana, "_regen_worker", None) is not None:
            pasado = time.monotonic() - t0
            if pasado > MAX_REGEN:
                break
            if self.dlg is None and time.monotonic() - self._t0 >= self.demora:
                self._crear()
            if self.dlg is not None:
                self._boton.setEnabled(False)
                self.dlg.setRange(0, 100)
                self.dlg.setValue(int(100 * min(0.97, pasado / estimado)))
                cabeza = f"{self.numero}/{self.etapas}  {texto}..." if self.etapas > 1 else f"{texto}..."
                resto = int(estimado - pasado + 0.999)
                self.dlg.setLabelText(cabeza + (f" faltan unos {resto} s" if resto > 1
                                                else " ya casi..."))
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)
            time.sleep(0.03)
        if self.dlg is not None:
            self.dlg.setValue(100)


def pedir_redibujo(ventana) -> None:
    """Redibuja si IngeCAD no está redibujando ya (en segundo plano si puede)."""
    if getattr(ventana, "_regen_worker", None) is not None:
        return
    regen = getattr(ventana, "regen_in_background", None) or getattr(ventana, "regen_in_memory", None)
    if callable(regen):
        try:
            regen()
        except Exception:  # noqa: BLE001
            pass
