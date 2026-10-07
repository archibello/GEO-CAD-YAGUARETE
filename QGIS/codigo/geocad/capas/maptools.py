# -*- coding: utf-8 -*-
"""Herramienta de mapa para 'designar objeto' (como en AutoCAD)."""

from qgis.core import QgsFeature
from qgis.gui import QgsMapToolIdentifyFeature

from .compat import qt


class PickFeatureTool(QgsMapToolIdentifyFeature):
    def __init__(self, iface, layer, callback, prompt='Designe objeto'):
        super().__init__(iface.mapCanvas(), layer)
        self.iface = iface
        self.layer_ = layer
        self.callback = callback
        self.prompt = prompt
        self.previous = iface.mapCanvas().mapTool()
        try:
            self.featureIdentified[QgsFeature].connect(self._picked)
        except (KeyError, TypeError, AttributeError):
            self.featureIdentified.connect(self._picked)
        self.setCursor(qt('CursorShape', 'CrossCursor'))

    def activate(self):
        super().activate()
        self.iface.statusBarIface().showMessage(self.prompt + '  (Esc o clic derecho para cancelar)')

    def deactivate(self):
        self.iface.statusBarIface().clearMessage()
        super().deactivate()

    def _picked(self, feature):
        if not isinstance(feature, QgsFeature):
            feature = self.layer_.getFeature(feature)
        cb = self.callback
        self.finish()
        if cb:
            cb(feature)

    def canvasReleaseEvent(self, ev):
        if ev.button() == qt('MouseButton', 'RightButton'):
            self.finish()
            return
        super().canvasReleaseEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == qt('Key', 'Key_Escape'):
            self.finish()
            return
        super().keyPressEvent(ev)

    def finish(self):
        self.callback = None
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self:
            if self.previous is not None and self.previous is not self:
                canvas.setMapTool(self.previous)
            else:
                canvas.unsetMapTool(self)
