# SPDX-License-Identifier: GPL-3.0-or-later
"""CREAR CAPA A PARTIR DE ELEMENTOS SELECCIONADOS en QGIS (3.73.0).

Menú Vectorial y clic derecho sobre la capa, antes de «Duplicar capa»; de
respaldo en Administrar Herramientas. Actúa sobre las capas elegidas en el
panel de capas: de cada una con selección sale una capa nueva, con su mismo
estilo, que muestra sólo esos elementos. Es un filtro: no crea archivos ni
escribe en la fuente, y la capa original queda como estaba.

La capa nueva se arma y se mide aparte; sólo entra al proyecto si muestra
exactamente lo elegido. Las reglas del filtro están en capa_seleccion.py.
"""
from __future__ import annotations

from pathlib import Path

from qgis.core import Qgis, QgsFeatureRequest, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from . import capa_seleccion as CS


def _condicion(capa, ids):
    """(filtro, motivo): el filtro para ``ids``, o por qué no se puede armar."""
    fuente = capa.dataProvider()
    if fuente is None or not capa.isValid():
        return None, "la capa no está disponible"
    if not fuente.supportsSubsetString():
        return None, "su fuente de datos no admite filtros"
    proveedor = capa.providerType()
    if proveedor in CS.CON_ID_PROPIO:
        return CS.filtro(proveedor, ids), ""
    if proveedor == "ogr" and capa.subsetString().lstrip()[:6].upper() == "SELECT":
        return None, "ya tiene un filtro con una consulta SELECT propia"
    indices = list(fuente.pkAttributeIndexes())
    if not indices and proveedor != "ogr":
        return None, "no tiene clave primaria"
    if len(indices) > 1:
        return None, "su clave primaria es compuesta"
    claves, valores = [], None
    if indices:
        claves = [fuente.fields().at(indices[0]).name()]
        pedido = QgsFeatureRequest().setFilterFids(ids).setSubsetOfAttributes(indices)
        por_id = {f.id(): f.attribute(indices[0]) for f in fuente.getFeatures(pedido)}
        valores = [por_id.get(i) for i in ids]
    condicion = CS.filtro(proveedor, ids, claves, valores)
    return condicion, "" if condicion else "no se pudo armar el filtro con su clave primaria"


def crear_capa(capa, proyecto=None):
    """(capa nueva, sin guardar, motivo). La capa nueva es None si no se creó."""
    proyecto = proyecto or QgsProject.instance()
    ids, sin_guardar = CS.separar(capa.selectedFeatureIds())
    if not ids:
        return None, len(sin_guardar), "sus elementos elegidos todavía no se guardaron"
    condicion, motivo = _condicion(capa, ids)
    if condicion is None:
        return None, len(sin_guardar), motivo
    nueva = capa.clone()
    if nueva is None or not nueva.isValid():
        return None, len(sin_guardar), "no se pudo duplicar"
    if not nueva.setSubsetString(condicion):
        return None, len(sin_guardar), "su fuente de datos rechazó el filtro"
    # antes de agregarla: un FID que choca con un campo propio elegiría otros
    if set(nueva.allFeatureIds()) != set(ids):
        return None, len(sin_guardar), "el filtro no devolvió exactamente lo elegido"
    nueva.setName(CS.nombre_libre(capa.name(), (c.name() for c in proyecto.mapLayers().values())))
    proyecto.addMapLayer(nueva)
    return nueva, len(sin_guardar), ""


class CapaSeleccionQgis:
    """La entrada del menú Vectorial y la del clic derecho en el panel de capas."""

    def __init__(self, iface):
        self.iface = iface
        mw = iface.mainWindow()
        self.icono_ = QIcon(str(Path(__file__).parent / "iconos" / "capa_seleccion.png"))
        self.accion = QAction(self.icono_, CS.TITULO, mw)
        self.accion.setObjectName("geocad_capa_seleccion")
        self.accion.triggered.connect(self.crear)
        self.accion_capas = QAction(self.icono_, CS.TITULO, mw)
        self.accion_capas.setObjectName("geocad_capa_seleccion_capas")
        self.accion_capas.triggered.connect(self.crear)
        iface.vectorMenu().addAction(self.accion)
        iface.layerTreeView().contextMenuAboutToShow.connect(self._al_menu_capas)

    def icono(self):
        return self.icono_

    def _capas(self) -> list:
        return [c for c in self.iface.layerTreeView().selectedLayers() if isinstance(c, QgsVectorLayer)]

    def _al_menu_capas(self, menu) -> None:
        capas = self._capas()
        if not capas:
            return
        self.accion_capas.setEnabled(any(c.selectedFeatureCount() for c in capas))
        duplicar = {"Duplicate Layer",
                    QCoreApplication.translate("QgsAppLayerTreeViewMenuProvider", "&Duplicate Layer").replace("&", "")}
        antes = next((a for a in menu.actions() if a.text().replace("&", "") in duplicar), None)
        if antes is not None:
            menu.insertAction(antes, self.accion_capas)
        else:
            menu.addSeparator()
            menu.addAction(self.accion_capas)

    def _aviso(self, texto: str, nivel) -> None:
        self.iface.messageBar().pushMessage("GeoCAD", texto, level=nivel, duration=8)

    def crear(self, _marcado=False) -> list:
        """Crea una capa por cada capa elegida con selección; devuelve las nuevas."""
        capas = [c for c in self._capas() if c.selectedFeatureCount()]
        if not capas:
            self._aviso("Elegí en el panel de capas una capa vectorial con elementos seleccionados.",
                        Qgis.MessageLevel.Warning)
            return []
        nuevas, problemas = [], []
        for capa in capas:
            nueva, sin_guardar, motivo = crear_capa(capa)
            if nueva is None:
                problemas.append("«%s»: %s" % (capa.name(), motivo))
                continue
            nuevas.append(nueva)
            if sin_guardar:
                problemas.append("«%s»: %d sin guardar no entraron" % (capa.name(), sin_guardar))
        if nuevas:
            self._aviso("Capa creada: " + ", ".join("«%s» (%d)" % (c.name(), c.featureCount()) for c in nuevas) + ".",
                        Qgis.MessageLevel.Success)
        if problemas:
            self._aviso("No se pudo completar: " + "; ".join(problemas) + ".", Qgis.MessageLevel.Warning)
        return nuevas

    def unload(self) -> None:
        try:
            self.iface.layerTreeView().contextMenuAboutToShow.disconnect(self._al_menu_capas)
        except Exception:  # noqa: BLE001 - ya desconectada
            pass
        try:
            self.iface.vectorMenu().removeAction(self.accion)
        except Exception:  # noqa: BLE001 - QGIS se está cerrando
            pass
        for accion in (self.accion, self.accion_capas):
            accion.deleteLater()
