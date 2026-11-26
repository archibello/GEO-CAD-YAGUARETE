# SPDX-License-Identifier: GPL-3.0-or-later
"""CREAR CAPA A PARTIR DE ELEMENTOS SELECCIONADOS en QGIS (3.73.0).

Menú Vectorial y clic derecho sobre la capa, antes de «Duplicar capa»; de
respaldo en Administrar Herramientas. Actúa sobre las capas elegidas en el
panel de capas: de cada una con selección sale una capa nueva, con su mismo
estilo, que muestra sólo esos elementos. Es un filtro: no crea archivos ni
escribe en la fuente, y la capa original queda como estaba.

La capa nueva se arma y se mide aparte; sólo entra al proyecto si muestra
exactamente lo elegido. Las reglas del filtro están en capa_seleccion.py.

3.97.1 (Fernando, 26/11/2026: «es muy importante esta operación para luego
utilizar las selecciones para crear nuevos layers»): si entre lo elegido hay
elementos todavía SIN GUARDAR (por ejemplo, lo que deja FILTRO en una capa
en edición), no se puede filtrar: se crea una COPIA aparte, un GeoPackage
con todos los elegidos y sus datos, con el mismo estilo. La original no se
toca ni se guarda. Decidido con Fernando («Crea una copia aparte»).
"""
from __future__ import annotations

from pathlib import Path

import os

from qgis.core import (Qgis, QgsFeature, QgsFeatureRequest, QgsFields, QgsProject,
                       QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes)
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


def copiar_seleccion(capa, proyecto=None):
    """(capa nueva, ruta, motivo): una copia aparte de lo elegido, en un
    GeoPackage junto al proyecto (o a la capa; si no, Documentos/GeoCAD),
    con sus datos y el estilo de la original. La original no se toca."""
    from . import combinar as C
    proyecto = proyecto or QgsProject.instance()
    elegidos = list(capa.selectedFeatureIds())
    if not elegidos:
        return None, "", "no tiene elementos elegidos"
    nombre = CS.nombre_libre(capa.name(), (c.name() for c in proyecto.mapLayers().values()))
    carpeta = C.carpeta_para(proyecto.fileName(), capa.source() if capa.providerType() == "ogr" else "")
    try:
        os.makedirs(carpeta, exist_ok=True)
    except OSError as e:
        return None, "", "no se pudo crear la carpeta %s (%s)" % (carpeta, e)
    ruta = C.archivo_libre(carpeta, nombre)
    pk = set(capa.primaryKeyAttributes())
    campos = QgsFields()
    for i, f in enumerate(capa.fields()):
        if i in pk or f.name().lower() == "fid":
            continue
        campos.append(f)
    uri = "%s?crs=%s" % (QgsWkbTypes.displayString(capa.wkbType()), capa.crs().authid() or "EPSG:4326")
    mem = QgsVectorLayer(uri, nombre, "memory")
    if not capa.crs().authid():
        mem.setCrs(capa.crs())
    mem.dataProvider().addAttributes(campos.toList())
    mem.updateFields()
    copias = []
    for f in capa.getFeatures(QgsFeatureRequest().setFilterFids(elegidos)):   # con la edición sin guardar
        n = QgsFeature(mem.fields())
        n.setGeometry(f.geometry())
        for c in campos:
            n.setAttribute(c.name(), f.attribute(c.name()))
        copias.append(n)
    mem.dataProvider().addFeatures(copias)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = nombre
    opts.fileEncoding = "UTF-8"
    try:
        res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, ruta, proyecto.transformContext(), opts)
    except AttributeError:
        res = QgsVectorFileWriter.writeAsVectorFormatV2(mem, ruta, proyecto.transformContext(), opts)
    if res[0] != QgsVectorFileWriter.NoError:
        return None, "", "no se pudo escribir %s" % ruta
    nueva = QgsVectorLayer("%s|layername=%s" % (ruta, nombre), nombre, "ogr")
    if not nueva.isValid() or nueva.featureCount() != len(copias):
        return None, "", "la copia no quedó con lo elegido"
    try:
        nueva.setRenderer(capa.renderer().clone())
    except Exception:  # noqa: BLE001 - queda el estilo de fábrica
        pass
    for prop in capa.customPropertyKeys():              # sólo las capas CAD (Layer Properties):
        if not str(prop).startswith("cad_layer_manager/"):   # no las marcas de textos o bloques
            continue
        try:
            nueva.setCustomProperty(prop, capa.customProperty(prop))
        except Exception:  # noqa: BLE001
            pass
    proyecto.addMapLayer(nueva)
    return nueva, ruta, ""


def crear_capa(capa, proyecto=None):
    """(capa nueva, sin guardar, motivo). La capa nueva es None si no se creó.
    3.97.1: con elegidos sin guardar, una copia aparte (``sin guardar`` = 0)."""
    proyecto = proyecto or QgsProject.instance()
    ids, sin_guardar = CS.separar(capa.selectedFeatureIds())
    if sin_guardar:
        nueva, _ruta, motivo = copiar_seleccion(capa, proyecto)
        return nueva, 0, motivo
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
            def como(c):
                copia = c.providerType() == "ogr" and c.source().split("|")[0].endswith(".gpkg") \
                    and not c.subsetString()
                return "«%s» (%d%s)" % (c.name(), c.featureCount(),
                                        ", copia aparte: había elegidos sin guardar" if copia else "")
            self._aviso("Capa creada: " + ", ".join(como(c) for c in nuevas) + ".",
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
