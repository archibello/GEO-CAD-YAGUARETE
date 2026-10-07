# -*- coding: utf-8 -*-
"""Actualización de las composiciones al pasar a su ventana (como REGEN de AutoCAD).

Mientras se dibuja en el modelo no se redibuja nada; cuando la ventana de una
composición se activa y hubo cambios desde su última actualización, se
actualiza (equivale a pulsar F5 en la composición).
"""

from qgis.PyQt.QtCore import QEvent, QObject
from qgis.core import QgsProject

from .compat import enum


class LayoutAutoRefresh(QObject):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.layers = {}          # id de capa -> capa (para desconectar)
        self.windows = {}         # id(ventana) -> [ventana, diseñador, pendiente]
        self._ev_activate = enum(QEvent, 'Type', 'WindowActivate')
        prj = QgsProject.instance()
        prj.layersAdded.connect(self._watch_layers)
        prj.layersWillBeRemoved.connect(self._forget_layers)
        self._watch_layers(list(prj.mapLayers().values()))
        iface.layoutDesignerOpened.connect(self._opened)
        try:
            iface.layoutDesignerWillBeClosed.connect(self._closed)
        except AttributeError:
            pass
        try:
            for d in iface.openLayoutDesigners():
                self._opened(d)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ capas
    def _watch_layers(self, layers):
        for lyr in layers:
            try:
                if lyr.id() in self.layers:
                    continue
                lyr.repaintRequested.connect(self._changed)
                self.layers[lyr.id()] = lyr
            except (AttributeError, RuntimeError):
                pass

    def _forget_layers(self, ids):
        for lid in ids:
            self.layers.pop(lid, None)
        self._changed()

    def _changed(self, *args):
        for entry in self.windows.values():
            entry[2] = True

    # ------------------------------------------------------------ ventanas de composición
    def _opened(self, designer):
        try:
            win = designer.window()
        except Exception:  # noqa: BLE001
            return
        if win is None or id(win) in self.windows:
            return
        self.windows[id(win)] = [win, designer, False]
        win.installEventFilter(self)

    def _closed(self, designer):
        for key, (win, d, _p) in list(self.windows.items()):
            if d is designer:
                try:
                    win.removeEventFilter(self)
                except RuntimeError:
                    pass
                del self.windows[key]

    def eventFilter(self, obj, ev):
        if ev.type() == self._ev_activate:
            entry = self.windows.get(id(obj))
            if entry is not None and entry[0] is obj and entry[2]:
                entry[2] = False
                try:
                    entry[1].layout().refresh()
                except Exception:  # noqa: BLE001
                    pass
        return False

    # ------------------------------------------------------------ descarga
    def unload(self):
        prj = QgsProject.instance()
        for sig, slot in ((prj.layersAdded, self._watch_layers), (prj.layersWillBeRemoved, self._forget_layers),
                          (self.iface.layoutDesignerOpened, self._opened)):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            self.iface.layoutDesignerWillBeClosed.disconnect(self._closed)
        except (TypeError, RuntimeError, AttributeError):
            pass
        for lyr in self.layers.values():
            try:
                lyr.repaintRequested.disconnect(self._changed)
            except (TypeError, RuntimeError):
                pass
        for win, _d, _p in self.windows.values():
            try:
                win.removeEventFilter(self)
            except RuntimeError:
                pass
        self.layers, self.windows = {}, {}
