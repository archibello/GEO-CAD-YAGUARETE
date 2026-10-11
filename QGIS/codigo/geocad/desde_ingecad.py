# -*- coding: utf-8 -*-
"""CAD to GIS: lo que IngeCAD manda con ENVIARQGIS (3.20.0).

Llega un mensaje «capas_nuevas» con los objetos elegidos en IngeCAD, ya
separados en puntos, líneas, polígonos y textos (ver aqgis.py de IngeCAD).
QGIS pregunta si van al proyecto abierto o a un proyecto nuevo y arma una
capa temporal (en memoria) por tipo, dentro de un grupo «Desde IngeCAD».
Cada objeto se ve con su color de CAD. Los textos llegan como líneas
cortas del ancho del texto, en su dirección, con el texto en «etiqueta»:
QGIS las rotula sobre la línea, así el rótulo queda en el lugar, con la
dirección y el tamaño (altura en unidades del mapa) del texto de CAD. Las capas temporales se pierden al
cerrar QGIS si no se guardan (QGIS ofrece «Hacer permanente»).

La parte sin QGIS (campos, nombres, la dirección de cada capa) se prueba sola.
"""
from __future__ import annotations

import time

TIPO_MENSAJE = "capas_nuevas"

#: en el orden del grupo, de arriba hacia abajo
TIPOS = ("textos", "puntos", "lineas", "poligonos")
GEOMETRIA = {"textos": "LineString", "puntos": "Point", "lineas": "LineString",
             "poligonos": "Polygon"}
NOMBRES = {"textos": "Textos", "puntos": "Puntos", "lineas": "Líneas",
           "poligonos": "Polígonos"}

_COMUNES = (("capa", "string"), ("color", "string"), ("tipo_cad", "string"))
CAMPOS = {
    "puntos": _COMUNES + (("bloque", "string"), ("giro", "double"), ("escala", "double")),
    "lineas": _COMUNES,
    "poligonos": _COMUNES,
    "textos": _COMUNES + (("etiqueta", "string"), ("altura", "double"), ("giro", "double")),
}

DESTINO_ABIERTO, DESTINO_NUEVO = "abierto", "nuevo"


def uri(tipo: str, crs: str) -> str:
    """La dirección de la capa en memoria, con sus campos."""
    partes = [f"crs={crs}"] if crs else []
    partes += [f"field={nombre}:{clase}" for nombre, clase in CAMPOS[tipo]]
    return GEOMETRIA[tipo] + "?" + "&".join(partes)


def nombre_grupo(dibujo: str, cuando: float | None = None) -> str:
    hora = time.strftime("%H:%M:%S", time.localtime(cuando if cuando is not None else time.time()))
    dibujo = (dibujo or "").strip()
    return f"Desde IngeCAD - {dibujo} ({hora})" if dibujo else f"Desde IngeCAD ({hora})"


def capas_del_mensaje(msg: dict) -> list:
    """[(tipo, nombre de la capa, [elementos])] en el orden del grupo."""
    capas = msg.get("capas") or {}
    return [(t, NOMBRES[t], capas[t]) for t in TIPOS if capas.get(t)]


def valores(tipo: str, elemento: dict) -> list:
    """Los atributos de un elemento en el orden de los campos."""
    out = []
    for nombre, clase in CAMPOS[tipo]:
        v = elemento.get(nombre)
        if clase == "double":
            try:
                v = float(v) if v is not None else None
            except (TypeError, ValueError):
                v = None
        elif v is not None:
            v = str(v)
        out.append(v)
    return out


def resumen(msg: dict) -> str:
    partes = [f"{len(lista)} {nombre.lower()}" for _t, nombre, lista in capas_del_mensaje(msg)]
    return ", ".join(partes)


# -- lo que necesita QGIS ------------------------------------------------------------

def _enum(clase, *nombres):
    """Un valor que cambió de lugar entre QGIS 3 y 4: Clase.Property.X,
    Clase.PropertyX o Clase.X."""
    for nombre in nombres:
        grupo = getattr(clase, "Property", None)
        if grupo is not None and hasattr(grupo, nombre):
            return getattr(grupo, nombre)
        for candidato in ("Property" + nombre, nombre):
            if hasattr(clase, candidato):
                return getattr(clase, candidato)
    raise AttributeError(nombres[0])


def _unidad_mapa():
    from qgis.core import Qgis
    try:
        return Qgis.RenderUnit.MapUnits
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return QgsUnitTypes.RenderMapUnits


def _color_por_objeto(layer, tipo: str) -> None:
    """Cada objeto con su color de CAD (el campo «color»)."""
    from qgis.core import QgsProperty, QgsSymbolLayer

    renderer = layer.renderer()
    simbolo = renderer.symbol() if renderer is not None and hasattr(renderer, "symbol") else None
    if simbolo is None:
        return
    color = QgsProperty.fromField("color")
    for i in range(simbolo.symbolLayerCount()):
        capa = simbolo.symbolLayer(i)
        if tipo == "lineas":
            capa.setDataDefinedProperty(_enum(QgsSymbolLayer, "StrokeColor"), color)
            continue
        capa.setDataDefinedProperty(_enum(QgsSymbolLayer, "StrokeColor"), color)
        if tipo == "poligonos":     # relleno del mismo color, casi transparente
            capa.setDataDefinedProperty(
                _enum(QgsSymbolLayer, "FillColor"),
                QgsProperty.fromExpression("set_color_part(\"color\", 'alpha', 50)"))
        else:
            capa.setDataDefinedProperty(_enum(QgsSymbolLayer, "FillColor"), color)


def _probar(*pasos) -> None:
    """Cada ajuste por separado: lo que esta versión de QGIS no tiene se
    deja como viene."""
    for paso in pasos:
        try:
            paso()
        except Exception:
            pass


def _rotulos(layer) -> None:
    """Los textos: el campo «etiqueta» rotulado SOBRE cada línea (paralelo,
    centrado), con la altura en unidades del mapa y el color de CAD. La
    dirección la da la línea; al revés también se muestra (como en CAD).
    La línea no se dibuja: queda para mover o editar el rótulo."""
    from qgis.core import (Qgis, QgsNullSymbolRenderer, QgsPalLayerSettings, QgsProperty,
                           QgsTextFormat, QgsVectorLayerSimpleLabeling)

    ajustes = QgsPalLayerSettings()
    ajustes.fieldName = "etiqueta"
    ajustes.enabled = True
    formato = QgsTextFormat()
    formato.setSize(1.0)
    formato.setSizeUnit(_unidad_mapa())
    ajustes.setFormat(formato)
    try:
        ajustes.placement = Qgis.LabelPlacement.Line
    except AttributeError:
        ajustes.placement = QgsPalLayerSettings.Line

    def sobre_la_linea():
        from qgis.core import QgsLabeling
        ajustes.lineSettings().setPlacementFlags(QgsLabeling.LinePlacementFlag.OnLine)

    def sobre_la_linea_viejo():
        ajustes.placementFlags = QgsPalLayerSettings.OnLine

    def centrado():
        from qgis.core import QgsLabelLineSettings
        ajustes.lineSettings().setLineAnchorPercent(0.5)
        ajustes.lineSettings().setAnchorType(QgsLabelLineSettings.AnchorType.Strict)

    def al_reves_tambien():
        try:
            ajustes.upsidedownLabels = Qgis.UpsideDownLabelHandling.AlwaysAllowUpsideDown
        except AttributeError:
            ajustes.upsidedownLabels = QgsPalLayerSettings.ShowAll

    def siempre_visible():
        try:
            ajustes.placementSettings().setOverlapHandling(
                Qgis.LabelOverlapHandling.AllowOverlapIfRequired)
        except AttributeError:
            ajustes.displayAll = True

    def puede_pasarse():
        # si la letra de QGIS es más ancha que la de CAD, el rótulo puede
        # pasarse de la línea en vez de desaparecer
        ajustes.lineSettings().setOverrunDistance(0.0)
        ajustes.lineSettings().setOverrunDistanceUnit(_unidad_mapa())

    _probar(sobre_la_linea)
    if not hasattr(ajustes, "lineSettings"):
        _probar(sobre_la_linea_viejo)
    _probar(centrado, al_reves_tambien, siempre_visible, puede_pasarse)
    dd = ajustes.dataDefinedProperties()
    dd.setProperty(_enum(QgsPalLayerSettings, "Size"), QgsProperty.fromField("altura"))
    dd.setProperty(_enum(QgsPalLayerSettings, "Color"), QgsProperty.fromField("color"))
    _probar(lambda: dd.setProperty(_enum(QgsPalLayerSettings, "OverrunDistance"),
                                   QgsProperty.fromExpression('length($geometry)')))
    ajustes.setDataDefinedProperties(dd)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(ajustes))
    layer.setLabelsEnabled(True)
    layer.setRenderer(QgsNullSymbolRenderer())


def crear_capa(tipo: str, nombre: str, elementos: list, crs: str):
    """(capa en memoria, cuántos elementos no se pudieron leer)."""
    from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer

    layer = QgsVectorLayer(uri(tipo, crs), nombre, "memory")
    feats, malos = [], 0
    for elemento in elementos:
        geom = QgsGeometry.fromWkt(elemento.get("wkt") or "")
        if geom is None or geom.isNull():
            malos += 1
            continue
        f = QgsFeature(layer.fields())
        f.setGeometry(geom)
        f.setAttributes(valores(tipo, elemento))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    try:
        if tipo == "textos":
            _rotulos(layer)
        else:
            _color_por_objeto(layer, tipo)
    except Exception:
        pass                       # sin estilo: igual se ve con el de QGIS
    return layer, malos


def cargar(iface, msg: dict, destino: str) -> tuple:
    """Arma las capas en el proyecto abierto o en uno nuevo.
    Devuelve (nombre del grupo, [capas], elementos no leídos) o None si se
    canceló el proyecto nuevo."""
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                           QgsProject, QgsRectangle)

    crs = msg.get("crs") or ""
    if destino == DESTINO_NUEVO:
        if not iface.newProject(True):          # pregunta si guarda el actual
            return None
        if crs:
            QgsProject.instance().setCrs(QgsCoordinateReferenceSystem(crs))
    proyecto = QgsProject.instance()
    if not crs:
        crs = proyecto.crs().authid()
    grupo = proyecto.layerTreeRoot().insertGroup(0, nombre_grupo(msg.get("dibujo", "")))
    capas, malos = [], 0
    extension = None
    for tipo, nombre, elementos in capas_del_mensaje(msg):
        layer, m = crear_capa(tipo, nombre, elementos, crs)
        malos += m
        proyecto.addMapLayer(layer, False)
        grupo.addLayer(layer)
        capas.append(layer)
        try:
            caja = QgsCoordinateTransform(layer.crs(), proyecto.crs(), proyecto) \
                .transformBoundingBox(layer.extent())
            if extension is None:
                extension = QgsRectangle(caja)
            else:
                extension.combineExtentWith(caja)
        except Exception:
            pass
    if extension is not None and not extension.isEmpty():
        extension.scale(1.1)
        iface.mapCanvas().setExtent(extension)
        iface.mapCanvas().refresh()
    elif extension is not None:                  # un solo punto
        iface.mapCanvas().setCenter(extension.center())
        iface.mapCanvas().refresh()
    return grupo.name(), capas, malos
