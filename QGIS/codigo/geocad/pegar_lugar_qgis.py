# -*- coding: utf-8 -*-
"""PEGAR EN EL LUGAR en QGIS (3.66.0, PEGARORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «copiar en una las entidades seleccionadas y pegarlas en
la otra»; «crear en IngeCAD la herramienta PEGAR EN COORDENADAS ORIGINALES en
el menú EDIT debajo de PASTE y lo mismo en QGIS»; «ESO ES PEGAR EN EL LUGAR».

* Menú Edición, debajo de «Pegar objetos espaciales»: «Pegar en el lugar»
  (Ctrl+Alt+V). Pega en la capa activa lo copiado (Ctrl+C) en IngeCAD o en
  QGIS, en sus mismas coordenadas, con su capa CAD (LAYER_CODE), color, tipo y
  grosor (CAD_COLOR, CAD_LTYPE, CAD_LW). Las capas CAD nuevas llevan el aspecto
  de la capa de origen, como el Puente. La capa entra en edición si no lo
  estaba; la geometría que no es del tipo de la capa se saltea y se cuenta.
* Si el proyecto no tiene sistema de coordenadas toma el del dibujo (Fernando:
  «va a crear el mismo de forma automática»); lo pegado se lleva al de la capa.
* El Ctrl+C de QGIS (Copiar objetos espaciales) deja además en el portapapeles
  el mensaje de pegar_lugar.py para que IngeCAD lo pegue en el lugar. Lo de
  QGIS no cambia: su Pegar sigue igual.
* Por teclado (3.70.5; Fernando: «si nos manejamos por menú funcionan perfectamente»):
  el Ctrl+C y el Ctrl+V de QGIS no pasan por las acciones del menú: son QShortcut
  del mapa y del panel de capas, y hay que engancharse a ellos. Ctrl+V pega también
  lo copiado en IngeCAD. Esos atajos no llegan a la línea de comandos ni a Yaguá
  Capas: ahí los atiende AtajosFuera, sin quitar el pegado de texto en la línea.
* Ctrl+Alt+V es también de QGIS («Pegar como capa temporal»); con los dos habilitados
  no se dispara ninguno. Se le saca mientras dura el módulo, sin guardarlo en los
  atajos del usuario, y se le devuelve al apagarlo. Esa acción sigue en el menú.
"""
from __future__ import annotations

import json

from types import SimpleNamespace

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsField,
                       QgsGeometry, QgsProject, QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes)
from qgis.PyQt.QtCore import QEvent, QObject, Qt, QTimer
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import (QAbstractSpinBox, QAction, QApplication, QDockWidget, QLineEdit,
                                 QPlainTextEdit, QTextEdit)

from . import pegar_lugar
from .capas.compat import QShortcut, geometry_kind, string_field

CAMPO_CAPA = "LAYER_CODE"
CAMPOS = (("color", "CAD_COLOR"), ("tipo_linea", "CAD_LTYPE"), ("grosor", "CAD_LW"))
PROP_KEY = "cad_layer_manager/config"           # la configuración de Yaguá Capas
ES_TEXTO = "dibujo_cad/text_layer"
ACCION_QGIS_MISMO_ATAJO = "mActionPasteAsNewMemoryVector"     # Pegar como capa temporal
LINEA_COMANDOS = "CadCmdInput"
PANEL_CAPAS = "YaguaCapasDock"


# ------------------------------------------------------------------ colores
def _aci_hex(aci: int) -> str:
    from .capas.aci import aci_to_hex
    return "#000000" if int(aci) == 7 else aci_to_hex(int(aci)).lower()


def aci_de(color) -> int | None:
    """El ACI (1-255) si el color de QGIS es exactamente uno de ellos (7 = #000000)."""
    if not color:
        return None
    color = str(color).lower()
    for aci in range(1, 256):
        try:
            if _aci_hex(aci) == color:
                return aci
        except Exception:  # noqa: BLE001
            return None
    return None


_ESP = {"point": "punto", "line": "linea", "polygon": "poligono"}


def _tipo_geometria(g) -> str:
    return _ESP.get(geometry_kind(SimpleNamespace(geometryType=g.type)), "")


def _tipo_capa(layer) -> str:
    return _ESP.get(geometry_kind(layer), "")


# ------------------------------------------------------------------ QGIS -> mensaje
def _capas_cad(layer) -> dict:
    """{nombre: capa CAD} de Yaguá Capas de ``layer`` (vacío si no tiene)."""
    raw = layer.customProperty(PROP_KEY)
    if not raw:
        return {}
    try:
        cfg = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return {str(lay.get("name")): lay for lay in cfg.get("layers", []) if isinstance(lay, dict)}


def _props_capa_cad(lay: dict) -> dict:
    c = lay.get("color") or {}
    aci = c.get("aci")
    color = c.get("rgb") or (_aci_hex(aci) if aci else None)
    lw = lay.get("lineweight")
    return {"color": color, "aci": int(aci) if aci else None,
            "tipo_linea": lay.get("linetype") or "Continuous",
            "grosor": -1.0 if lw is None or float(lw) < 0 else float(lw)}


def _color_simbolo(layer):
    try:
        sym = layer.renderer().symbol()
        return sym.color().name() if sym is not None else None
    except Exception:  # noqa: BLE001 -- otra simbología: el color lo pone IngeCAD
        return None


def _valor(f, campo):
    idx = f.fields().indexOf(campo)
    if idx == -1:
        return None
    v = f.attribute(idx)
    if v is None or (hasattr(v, "isNull") and v.isNull()) or str(v) in ("", "NULL"):
        return None
    return v


def mensaje_de(layer, features) -> bytes:
    """El mensaje de pegar_lugar.py con los objetos copiados de ``layer``."""
    cad = _capas_cad(layer)
    objetos, capas, salteados = [], {}, {}
    texto = layer.customProperty(ES_TEXTO) == "1"
    for f in features:
        g = f.geometry()
        if texto:
            salteados["texto(s)"] = salteados.get("texto(s)", 0) + 1
            continue
        if g is None or g.isEmpty():
            salteados["sin geometría"] = salteados.get("sin geometría", 0) + 1
            continue
        if g.constGet().hasCurvedSegments():    # IngeCAD no lee CircularString y compañía
            g = QgsGeometry(g.constGet().segmentize())
        nombre = _valor(f, CAMPO_CAPA)
        nombre = str(nombre) if nombre is not None else layer.name()
        color = _valor(f, "CAD_COLOR")
        lw = _valor(f, "CAD_LW")
        objetos.append({"wkt": g.asWkt(9), "capa": nombre,
                        "color": str(color).lower() if color else None, "aci": aci_de(color),
                        "tipo_linea": _valor(f, "CAD_LTYPE"),
                        "grosor": float(lw) if lw is not None else None})
        if nombre not in capas:
            if nombre in cad:
                capas[nombre] = _props_capa_cad(cad[nombre])
            else:
                color = _color_simbolo(layer)
                capas[nombre] = {"color": color, "aci": aci_de(color), "tipo_linea": None,
                                 "grosor": None}
    return pegar_lugar.empaquetar("qgis", layer.crs().authid(), objetos, capas, salteados)


# ------------------------------------------------------------------ mensaje -> QGIS
def _partes(g, multi: bool):
    if multi or not g.isMultipart():
        return [g]
    return [QgsGeometry(p) for p in g.asGeometryCollection()]


def _asegurar_campo(layer, nombre, tipo):
    if layer.fields().indexOf(nombre) != -1:
        return True
    if tipo == "double":
        try:
            from qgis.PyQt.QtCore import QMetaType
            campo = QgsField(nombre, QMetaType.Type.Double)
        except (ImportError, AttributeError, TypeError):
            from qgis.PyQt.QtCore import QVariant
            campo = QgsField(nombre, QVariant.Double)
    else:
        campo = string_field(nombre, 50)
    return layer.addAttribute(campo) and layer.fields().indexOf(nombre) != -1


def _capa_cad_nueva(nombre, props):
    color = (props or {}).get("color")
    aci = (props or {}).get("aci")
    lw = (props or {}).get("grosor")
    return {"name": nombre, "description": "", "on": True, "frozen": False, "locked": False,
            "plot": True, "color": {"aci": int(aci) if aci else (None if color else 7),
                                    "rgb": None if aci else color},
            "linetype": (props or {}).get("tipo_linea") or "Continuous",
            "lineweight": -1.0 if lw is None or float(lw) < 0 else float(lw),
            "transparency": 0, "fill": None, "filltr": 0}


def _sumar_capas_cad(layer, msg, usadas) -> list:
    """Agrega a Yaguá Capas de ``layer`` las capas CAD que llegan y no tiene."""
    raw = layer.customProperty(PROP_KEY)
    try:
        cfg = json.loads(raw) if raw else {"layers": [], "current": "0"}
    except (ValueError, TypeError):
        return []
    conocidas = {str(lay.get("name")) for lay in cfg.get("layers", [])}
    nuevas = [n for n in usadas if n not in conocidas]
    for n in nuevas:
        cfg.setdefault("layers", []).append(_capa_cad_nueva(n, (msg.get("capas") or {}).get(n)))
    if nuevas or not raw:
        layer.setCustomProperty(PROP_KEY, json.dumps(cfg, ensure_ascii=False))
    return nuevas


def _refrescar_capas(layer):
    """Que Yaguá Capas lea lo nuevo y aplique la simbología, si está prendida."""
    try:
        from qgis.utils import plugins
        ctrl = getattr(plugins.get("Layer_Properties"), "ctrl", None)
        if ctrl is not None:
            ctrl.attach(layer)
            ctrl.ensure_initialized()
            ctrl.refresh()
            # los símbolos usan CAD_COLOR, CAD_LTYPE y CAD_LW sólo si el campo ya existía al
            # armarlos: recién creados, lo pegado salía con el aspecto de la capa
            ctrl._apply_all()
    except Exception:  # noqa: BLE001 -- sin Capas CAD quedan los campos
        pass


def pegar(iface, msg, layer=None) -> str:
    """Pega ``msg`` en la capa activa; devuelve lo que se informa."""
    layer = layer or iface.activeLayer()
    if not isinstance(layer, QgsVectorLayer) or not layer.isSpatial():
        return "Pegar en el lugar: elija primero (activa) una capa vectorial donde pegar."
    if layer.customProperty(ES_TEXTO) == "1":
        return "Pegar en el lugar: la capa activa es de textos; elija una de puntos, líneas o polígonos."
    proyecto = QgsProject.instance()
    avisos = []
    crs_origen = msg.get("crs") or ""
    definir, _rep = pegar_lugar.sistema(proyecto.crs().authid() if proyecto.crs().isValid() else "",
                                        crs_origen)
    if definir:
        nuevo = QgsCoordinateReferenceSystem(definir)
        if nuevo.isValid():
            proyecto.setCrs(nuevo)
            avisos.append("El proyecto no tenía sistema de coordenadas: ahora es %s (el del dibujo)."
                          % definir)
    origen = QgsCoordinateReferenceSystem(crs_origen) if crs_origen else proyecto.crs()
    transformar = None
    if origen.isValid() and layer.crs().isValid() and origen != layer.crs():
        transformar = QgsCoordinateTransform(origen, layer.crs(), proyecto)
    if not layer.isEditable():
        if not layer.startEditing():
            return "Pegar en el lugar: la capa «%s» no se puede editar." % layer.name()
        avisos.append("La capa «%s» entró en edición." % layer.name())
    tipo = _tipo_capa(layer)
    multi = QgsWkbTypes.isMultiType(layer.wkbType())
    from .dibujo.editkit import conform

    layer.beginEditCommand("Pegar en el lugar")
    validos, otro_tipo, contornos = [], 0, 0
    for obj in msg.get("objetos", []):
        g = QgsGeometry.fromWkt(obj.get("wkt", ""))
        if g is None or g.isNull() or g.isEmpty():
            continue
        if _tipo_geometria(g) == "poligono" and tipo == "linea":
            # lo cerrado de IngeCAD (polilínea, círculo) viaja como polígono: va su contorno
            g = QgsGeometry(g.constGet().boundary())
            contornos += 1
        elif _tipo_geometria(g) != tipo:
            otro_tipo += 1
            continue
        validos.append((obj, g))
    # primero los campos que hagan falta (agregados después, los objetos ya armados
    # quedaban con menos columnas y QGIS no los aceptaba)
    hay_campos = {CAMPO_CAPA: bool(validos) and _asegurar_campo(layer, CAMPO_CAPA, "string")}
    for clave, campo in CAMPOS:
        if any(o.get(clave) is not None for o, _g in validos) and not (clave == "tipo_linea" and tipo == "punto"):
            hay_campos[campo] = _asegurar_campo(layer, campo, "double" if clave == "grosor" else "string")
    nuevos, usadas = [], []
    for obj, g in validos:
        if transformar is not None:
            g.transform(transformar)
        attrs = {}
        capa = obj.get("capa") or "0"
        if hay_campos[CAMPO_CAPA]:
            attrs[layer.fields().indexOf(CAMPO_CAPA)] = capa
            if capa not in usadas:
                usadas.append(capa)
        for clave, campo in CAMPOS:
            valor = obj.get(clave)
            if valor is not None and hay_campos.get(campo):
                attrs[layer.fields().indexOf(campo)] = valor
        for parte in _partes(g, multi):
            f = QgsVectorLayerUtils.createFeature(layer, conform(parte, layer), attrs,
                                                  layer.createExpressionContext())
            nuevos.append(f)
    if not nuevos:
        layer.destroyEditCommand()
        texto = "Pegar en el lugar: nada para pegar en «%s»" % layer.name()
        if otro_tipo:
            texto += " (%d objeto(s) de otro tipo de geometría)" % otro_tipo
        return texto + "."
    if not layer.addFeatures(nuevos):
        layer.destroyEditCommand()
        return "Pegar en el lugar: QGIS no aceptó los objetos en «%s»." % layer.name()
    layer.endEditCommand()
    nuevas_cad = _sumar_capas_cad(layer, msg, usadas) if usadas else []
    if usadas:
        _refrescar_capas(layer)
    layer.triggerRepaint()
    texto = "Pegado en el lugar en «%s»: %s." % (layer.name(), pegar_lugar.resumen(msg))
    if contornos:
        texto += " %d cerrado(s), como contorno." % contornos
    if otro_tipo:
        texto += " %d de otro tipo de geometría no van en esta capa." % otro_tipo
    if nuevas_cad:
        texto += " Capas CAD nuevas: %s." % ", ".join(nuevas_cad)
    return " ".join([texto] + avisos)


# ------------------------------------------------------------------ el portapapeles
def mensaje_en_portapapeles():
    return pegar_lugar.leer_copia(QApplication.clipboard().mimeData())


def dejar_copia(extra: bytes) -> None:
    # el portapapeles no se vuelve a escribir: ver nucleo/pegar_lugar.py
    data = QApplication.clipboard().mimeData()
    if data is not None:
        pegar_lugar.dejar_copia(extra, data, pegar_lugar.FORMATO_TEXTO)


class AtajosFuera(QObject):
    """Ctrl+C y Ctrl+V de objetos con el foco en la línea de comandos vacía o en Yaguá Capas,
    donde no llegan los QShortcut de QGIS. El resto de las teclas sigue su camino."""

    def __init__(self, modulo):
        super().__init__()
        self.modulo = modulo
        self._press = getattr(QEvent, "Type", QEvent).KeyPress
        self._key = getattr(Qt, "Key", Qt)
        self._ctrl = getattr(Qt, "KeyboardModifier", Qt).ControlModifier

    def _atendible(self, w) -> bool:
        if w.objectName() == LINEA_COMANDOS:
            return not w.text()                 # con algo escrito, es texto
        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return False
        dock = self.modulo.iface.mainWindow().findChild(QDockWidget, PANEL_CAPAS)
        return dock is not None and dock.isAncestorOf(w)

    def eventFilter(self, obj, ev):  # noqa: N802
        try:
            if ev.type() != self._press or ev.modifiers() != self._ctrl:
                return False
            if ev.key() not in (self._key.Key_C, self._key.Key_V):
                return False
            if obj is not QApplication.focusWidget() or not self._atendible(obj):
                return False
            return self.modulo.copiar_objetos() if ev.key() == self._key.Key_C \
                else self.modulo.pegar_objetos()
        except Exception:  # noqa: BLE001 -- nunca romper el teclado
            return False


class PegarLugarQgis:
    """«Pegar en el lugar» en el menú Edición y la copia para IngeCAD en el Ctrl+C."""

    def __init__(self, iface):
        self.iface = iface
        mw = iface.mainWindow()
        self.accion = QAction("Pegar en el lugar", mw)
        self.accion.setObjectName("geocad_pegar_lugar")
        self.accion.setShortcut(QKeySequence(pegar_lugar.ATAJO))
        self.accion.setToolTip("Pegar en el lugar (PEGARORIG): lo copiado en IngeCAD o en QGIS, "
                               "en sus coordenadas originales, en la capa activa")
        self.accion.triggered.connect(self.pegar)
        self.menu = iface.editMenu()
        siguiente = None
        acciones = self.menu.actions()
        pegar_qgis = iface.actionPasteFeatures()
        if pegar_qgis in acciones:
            i = acciones.index(pegar_qgis)
            siguiente = acciones[i + 1] if i + 1 < len(acciones) else None
        self.menu.insertAction(siguiente, self.accion)
        mw.addAction(self.accion)
        self.copiar = iface.actionCopyFeatures()
        self.copiar.triggered.connect(self._al_copiar)
        self.pegar_qgis = pegar_qgis
        self._atajos = self._enganchar_atajos()
        self._accion_sin_atajo = self._liberar_atajo()
        self._filtro = AtajosFuera(self)
        QApplication.instance().installEventFilter(self._filtro)

    def _enganchar_atajos(self) -> list:
        """El Ctrl+C y el Ctrl+V de QGIS, que no pasan por las acciones del menú."""
        mw = self.iface.mainWindow()
        dueños = (self.iface.mapCanvas(), self.iface.layerTreeView())
        tablas = ((QKeySequence("Ctrl+C"), self._al_copiar), (QKeySequence("Ctrl+V"), self._al_pegar_atajo))
        atajos = []
        for atajo in mw.findChildren(QShortcut):
            if atajo.parent() not in dueños:
                continue
            for tecla, funcion in tablas:
                if atajo.key() == tecla:
                    atajo.activated.connect(funcion)
                    atajos.append((atajo, funcion))
        return atajos

    def _liberar_atajo(self):
        """Saca Ctrl+Alt+V a la acción de QGIS que lo comparte. No se guarda en los atajos del usuario."""
        accion = self.iface.mainWindow().findChild(QAction, ACCION_QGIS_MISMO_ATAJO)
        if accion is None or accion.shortcut() != QKeySequence(pegar_lugar.ATAJO):
            return None                         # el usuario lo cambió, o esta QGIS no la tiene
        accion.setShortcut(QKeySequence())
        return accion

    def copiar_objetos(self) -> bool:
        layer = self.iface.activeLayer()
        if (not isinstance(layer, QgsVectorLayer) or not layer.selectedFeatureCount()
                or not self.copiar.isEnabled()):
            return False
        self.copiar.trigger()
        return True

    def pegar_objetos(self) -> bool:
        """Sólo si hay objetos copiados; si no, Ctrl+V sigue siendo pegar texto."""
        msg = mensaje_en_portapapeles()
        if msg is None:
            return False
        if msg.get("origen") == "ingecad":
            self.pegar()
            return True
        if not self.pegar_qgis.isEnabled():
            return False
        self.pegar_qgis.trigger()
        return True

    def _al_pegar_atajo(self, *_a):
        """QGIS no entiende lo copiado en IngeCAD: su Ctrl+V no pega nada y va éste."""
        msg = mensaje_en_portapapeles()
        if msg is not None and msg.get("origen") == "ingecad":
            self.pegar()

    def _al_copiar(self, *_a):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.selectedFeatureCount():
            return
        try:
            extra = mensaje_de(layer, list(layer.selectedFeatures()))
        except Exception:  # noqa: BLE001 -- ante cualquier duda, la copia de QGIS como venía
            return
        # QGIS escribe el portapapeles en su propia respuesta al clic: después, lo nuestro
        QTimer.singleShot(0, lambda: dejar_copia(extra))

    def pegar(self, *_a):
        msg = mensaje_en_portapapeles()
        if msg is None:
            texto = ("Pegar en el lugar: el portapapeles no tiene objetos copiados con GeoCAD. "
                     "Copie (Ctrl+C) en IngeCAD o en QGIS y vuelva a pegar.")
            nivel = Qgis.MessageLevel.Warning
        else:
            texto = pegar(self.iface, msg)
            nivel = Qgis.MessageLevel.Info if texto.startswith("Pegado") else Qgis.MessageLevel.Warning
        self.iface.messageBar().pushMessage("GeoCAD", texto, level=nivel, duration=8)
        return texto

    def unload(self):
        try:
            self.copiar.triggered.disconnect(self._al_copiar)
        except Exception:  # noqa: BLE001
            pass
        for atajo, funcion in self._atajos:
            try:
                atajo.activated.disconnect(funcion)
            except Exception:  # noqa: BLE001
                pass
        self._atajos = []
        try:
            QApplication.instance().removeEventFilter(self._filtro)
        except Exception:  # noqa: BLE001
            pass
        if self._accion_sin_atajo is not None:
            try:
                self._accion_sin_atajo.setShortcut(QKeySequence(pegar_lugar.ATAJO))
            except Exception:  # noqa: BLE001
                pass
            self._accion_sin_atajo = None
        try:
            self.menu.removeAction(self.accion)
            self.iface.mainWindow().removeAction(self.accion)
        except Exception:  # noqa: BLE001
            pass
        self.accion.deleteLater()
