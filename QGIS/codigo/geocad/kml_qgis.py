# SPDX-License-Identifier: GPL-3.0-or-later
"""EXPORTAR A GOOGLE EARTH (KML/KMZ) desde QGIS (3.74.0).

Sólo en el banco de Administrar Herramientas, nunca en el menú GeoCAD
(Fernando, 09/11/2026). Dos herramientas, con el módulo Google Earth:

* «Exportar a Google Earth (KML/KMZ)...»: elige capas y archivo.
* «Ver en Google Earth»: un clic, las capas visibles van a Google Earth.

La escritura es la misma de EXPORTARKML de IngeCAD (kmlformato.py, en el
núcleo). Lo de acá es pasar las capas a marcas, y antes controlar el sistema:

* Capa sin sistema: se pregunta, proponiendo la faja según las X.
* Las X no son de la faja declarada: se avisa y se ofrece corregir.
* Lo que se elige vale para esta exportación: la capa no se toca.

Los colores salen de lo que QGIS dibuja para cada objeto (symbolForFeature):
sirve igual para símbolo único, categorizado, por expresión, graduado y reglas.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCsException, QgsExpression,
                       QgsExpressionContext, QgsExpressionContextUtils, QgsFeatureRequest, QgsGeometry, QgsProject,
                       QgsRenderContext, QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtCore import QDate, QDateTime, QSettings, Qt, QTime, QUrl, QVariant
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                                 QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from . import crs as CRS
from . import googleearth as GE
from . import kmlformato as F

TITULO = "Exportar a Google Earth"
WGS84 = "EPSG:4326"
MUESTRA_X = 20000          # objetos que se miran para decir la faja
CLAVE_CARPETA = "geocad/kml_carpeta"
NOMBRES = ("nombre", "name", "denominacion", "denominación", "rotulo", "rótulo", "etiqueta", "label")


# ------------------------------------------------------------------ el sistema de cada capa
@dataclass
class Revision:
    """Qué se sabe del sistema de una capa antes de exportarla."""
    capa: object
    codigo: str                 # el declarado, como «EPSG:5348» ("" = sin sistema válido)
    sugerido: str = ""          # el que dicen las X, si no es el declarado


def ids_a_exportar(capa, solo_seleccion: bool):
    """Los elementos de ``capa``: los seleccionados si se pidió y los hay."""
    if solo_seleccion and capa.selectedFeatureCount():
        return capa.selectedFeatureIds()
    return None


def _pedido(ids):
    pedido = QgsFeatureRequest()
    if ids is not None:
        pedido.setFilterFids(list(ids))
    return pedido


def este_de(capa, ids=None) -> list:
    """Las X (centro de cada objeto), en las unidades de la capa."""
    pedido = _pedido(ids).setNoAttributes().setLimit(MUESTRA_X)
    xs = []
    for f in capa.getFeatures(pedido):
        g = f.geometry()
        if g is not None and not g.isNull() and not g.isEmpty():
            xs.append(g.boundingBox().center().x())
    return xs


def revisar(capa, ids=None) -> Revision:
    crs = capa.crs()
    codigo = crs.authid() if crs.isValid() else ""
    if crs.isValid() and not codigo:
        return Revision(capa, "personalizado")     # válido, sin código: no se puede comparar la faja
    if codigo and crs.isGeographic():
        return Revision(capa, codigo)
    return Revision(capa, codigo, CRS.faja_sugerida(codigo, este_de(capa, ids)))


def nombre_sistema(codigo: str) -> str:
    n = CRS._epsg_de(codigo)
    return CRS.KNOWN.get(n, codigo) if n else codigo


def preguntar(parent, rev: Revision):
    """El QgsCoordinateReferenceSystem a usar; None = saltear esta capa;
    False = cancelar toda la exportación. Sin problema, no pregunta."""
    actual = rev.capa.crs()
    if rev.codigo and not rev.sugerido:
        return actual
    caja = QMessageBox(parent)
    caja.setWindowTitle(TITULO)
    caja.setIcon(QMessageBox.Icon.Warning)
    usar = None
    if rev.codigo:
        faja = CRS.faja_de(rev.sugerido)[0]
        caja.setText(f"«{rev.capa.name()}» está declarada en {nombre_sistema(rev.codigo)}, pero sus X son "
                     f"de la faja {faja}.\n\nSi se exporta así, en Google Earth cae cientos de kilómetros "
                     "corrida.\n\nLo que elijas vale sólo para esta exportación: la capa no se toca.")
        usar = caja.addButton(f"Usar faja {faja}", QMessageBox.ButtonRole.AcceptRole)
        dejar = caja.addButton("Dejar como está", QMessageBox.ButtonRole.DestructiveRole)
        cancelar = caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(usar)
        caja.exec()
        boton = caja.clickedButton()
        if boton is usar:
            return QgsCoordinateReferenceSystem(rev.sugerido)
        return actual if boton is dejar else False
    texto = (f"«{rev.capa.name()}» no tiene sistema de coordenadas y Google Earth necesita saber dónde está.")
    if rev.sugerido:
        faja = CRS.faja_de(rev.sugerido)[0]
        texto += (f"\n\nPor las X es de la faja {faja}. El marco (POSGAR 2007, Campo Inchauspe...) "
                  "lo sabe el plano.")
        usar = caja.addButton(f"Usar {nombre_sistema(rev.sugerido)}", QMessageBox.ButtonRole.AcceptRole)
    caja.setText(texto + "\n\nLo que elijas vale sólo para esta exportación: la capa no se toca.")
    elegir = caja.addButton("Elegir sistema...", QMessageBox.ButtonRole.ActionRole)
    caja.addButton("Saltear esta capa", QMessageBox.ButtonRole.RejectRole)
    caja.exec()
    boton = caja.clickedButton()
    if usar is not None and boton is usar:
        return QgsCoordinateReferenceSystem(rev.sugerido)
    if boton is elegir:
        from qgis.gui import QgsProjectionSelectionDialog
        dlg = QgsProjectionSelectionDialog(parent)
        if rev.sugerido:
            dlg.setCrs(QgsCoordinateReferenceSystem(rev.sugerido))
        if dlg.exec() and dlg.crs().isValid():
            return dlg.crs()
    return None


# ------------------------------------------------------------------ cómo se ve cada objeto
def _hex(color) -> str:
    return color.name()


def _grosor(mm) -> int:
    try:
        return max(1, int(round(float(mm) * 100)))
    except (TypeError, ValueError):
        return F.GROSOR_NORMAL


def aspecto_de(simbolo, tipo: str, opacidad: float) -> dict:
    """Color, grosor y relleno que dibuja QGIS. Un símbolo que no es el
    relleno simple (contorno sólo, degradado...) también tiene su color."""
    if tipo != "poligono":
        grosor = _grosor(simbolo.width()) if tipo == "linea" else F.GROSOR_NORMAL
        return {"color": _hex(simbolo.color()), "grosor": grosor}
    capa = simbolo.symbolLayer(0)
    if hasattr(capa, "strokeColor") and hasattr(capa, "strokeWidth"):
        sin_borde = hasattr(capa, "strokeStyle") and capa.strokeStyle() == Qt.PenStyle.NoPen
        sin_fondo = hasattr(capa, "brushStyle") and capa.brushStyle() == Qt.BrushStyle.NoBrush
        fondo = capa.color()
        relleno = 0 if sin_fondo else round(fondo.alphaF() * simbolo.opacity() * opacidad * 100)
        borde = fondo if sin_borde else capa.strokeColor()
        return {"color": _hex(borde), "grosor": _grosor(capa.strokeWidth()),
                "color_relleno": _hex(fondo), "relleno": relleno}
    if hasattr(capa, "width"):                  # «contorno: línea simple»
        return {"color": _hex(capa.color()), "grosor": _grosor(capa.width()), "relleno": 0}
    return {"color": _hex(simbolo.color()), "grosor": F.GROSOR_NORMAL}


def texto_de(valor) -> str:
    """El valor de un campo como texto: un 0 es un 0; NULL queda vacío."""
    if valor is None or (isinstance(valor, QVariant) and valor.isNull()):
        return ""
    if isinstance(valor, (QDateTime, QDate, QTime)):
        return valor.toString(Qt.DateFormat.ISODate)
    return str(valor).strip()


def expresion_nombre(capa) -> str:
    """De dónde sale el nombre: el rótulo de la capa o un campo «nombre»."""
    try:
        if capa.labelsEnabled() and capa.labeling().type() == "simple":
            pal = capa.labeling().settings()
            if pal.fieldName:
                return pal.fieldName if pal.isExpression else QgsExpression.quotedColumnRef(pal.fieldName)
    except (AttributeError, RuntimeError):
        pass
    for f in capa.fields():
        if f.name().lower() in NOMBRES:
            return QgsExpression.quotedColumnRef(f.name())
    return ""


def _num(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _en_rango(geom) -> bool:
    caja = geom.boundingBox()
    return all(math.isfinite(v) for v in (caja.xMinimum(), caja.xMaximum(), caja.yMinimum(), caja.yMaximum())) \
        and -180.000001 <= caja.xMinimum() and caja.xMaximum() <= 180.000001 \
        and -90.000001 <= caja.yMinimum() and caja.yMaximum() <= 90.000001


def _ll(puntos) -> list:
    return [(p.x(), p.y()) for p in puntos]


# ------------------------------------------------------------------ de la capa a las marcas
def marcas_de(capa, sistema, carpeta: str, ids=None, ajustes=None, proyecto=None, salteados=None) -> list:
    """Las marcas de ``capa``, en WGS 84, con ``sistema`` como sistema de origen."""
    proyecto = proyecto or QgsProject.instance()
    salteados = salteados if salteados is not None else Counter()
    destino = QgsCoordinateReferenceSystem(WGS84)
    transformar = QgsCoordinateTransform(sistema, destino, proyecto.transformContext())
    tipo_capa = QgsWkbTypes.geometryType(capa.wkbType())
    tipo = {QgsWkbTypes.GeometryType.PointGeometry: "punto", QgsWkbTypes.GeometryType.LineGeometry: "linea",
            QgsWkbTypes.GeometryType.PolygonGeometry: "poligono"}.get(tipo_capa)
    if tipo is None:
        return []
    ctx = QgsRenderContext.fromMapSettings(ajustes) if ajustes is not None else QgsRenderContext()
    exp_ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(capa))
    ctx.setExpressionContext(exp_ctx)
    render = capa.renderer().clone() if capa.renderer() is not None else None
    origen_nombre = expresion_nombre(capa)
    nombre_exp = QgsExpression(origen_nombre) if origen_nombre else None
    if nombre_exp is not None:
        nombre_exp.prepare(exp_ctx)
    opacidad = capa.opacity()
    campos = [f.name() for f in capa.fields()]
    marcas, n = [], 0
    if render is not None:
        render.startRender(ctx, capa.fields())
    try:
        for feat in capa.getFeatures(_pedido(ids)):
            geom = QgsGeometry(feat.geometry())
            if geom.isNull() or geom.isEmpty():
                salteados["sin geometría"] += 1
                continue
            aspecto = {"color": "#ffffff", "grosor": F.GROSOR_NORMAL}
            ctx.expressionContext().setFeature(feat)
            if render is not None:
                simbolo = render.symbolForFeature(feat, ctx)
                if simbolo is None:             # QGIS tampoco lo dibuja
                    salteados["sin símbolo en la capa"] += 1
                    continue
                aspecto = aspecto_de(simbolo, tipo, opacidad)
            area = geom.area() if tipo == "poligono" else 0.0
            largo = geom.length()
            if QgsWkbTypes.isCurvedType(geom.wkbType()):
                geom.convertToStraightSegment()
            try:
                geom.transform(transformar)
            except QgsCsException:
                salteados["fuera del sistema"] += 1
                continue
            if not _en_rango(geom):
                salteados["fuera del sistema"] += 1
                continue
            n += 1
            nombre = ""
            if nombre_exp is not None:
                nombre = texto_de(nombre_exp.evaluate(ctx.expressionContext()))
            if tipo != "punto":
                nombre = nombre or f"{carpeta} {n}"
            datos = [(c, texto_de(feat[c])) for c in campos]
            desc = f"Capa {carpeta}"
            if not sistema.isGeographic():
                if tipo == "linea":
                    desc += f". Largo {_num(largo)} m"
                elif tipo == "poligono":
                    desc += f". Área {_num(area)} m², perímetro {_num(largo)} m"
            partes = geom.asGeometryCollection()
            if tipo == "punto":
                for p in partes:
                    pt = p.asPoint()
                    marcas.append(F.Marca("punto", [(pt.x(), pt.y())], nombre, carpeta,
                                          aspecto["color"], aspecto["grosor"], desc, datos))
            elif tipo == "linea":
                for p in partes:
                    marcas.append(F.Marca("linea", _ll(p.asPolyline()), nombre, carpeta, descripcion=desc, datos=datos,
                                          **aspecto))
            else:
                grupos = [(_ll(a[0]), [_ll(h) for h in a[1:]]) for a in (p.asPolygon() for p in partes) if a]
                marcas.append(F.Marca("poligono", grupos, nombre, carpeta, descripcion=desc, datos=datos, **aspecto))
    finally:
        if render is not None:
            render.stopRender(ctx)
    return marcas


@dataclass
class Resultado:
    ruta: object = None
    objetos: int = 0
    carpetas: int = 0
    salteados: Counter = field(default_factory=Counter)
    saltadas: list = field(default_factory=list)    # capas que no fueron
    avisos: list = field(default_factory=list)
    cancelado: bool = False


def carpetas_de(capas, proyecto=None) -> dict:
    """{capa: nombre de carpeta}: «Grupo - Capa», sin repetir."""
    proyecto = proyecto or QgsProject.instance()
    salida, usados = {}, set()
    for capa in capas:
        nodo = proyecto.layerTreeRoot().findLayer(capa.id())
        grupos = []
        padre = nodo.parent() if nodo is not None else None
        while padre is not None and padre.parent() is not None:
            grupos.insert(0, padre.name())
            padre = padre.parent()
        base = " - ".join(grupos + [capa.name()])
        nombre, k = base, 2
        while nombre.lower() in usados:
            nombre, k = f"{base} ({k})", k + 1
        usados.add(nombre.lower())
        salida[capa] = nombre
    return salida


def exportar(capas, ruta, solo_seleccion=False, responder=None, parent=None, ajustes=None, proyecto=None) -> Resultado:
    """Las ``capas`` a ``ruta``. ``responder(rev)``: lo que devuelve preguntar()."""
    proyecto = proyecto or QgsProject.instance()
    responder = responder or (lambda rev: preguntar(parent, rev))
    res = Resultado()
    nombres = carpetas_de(capas, proyecto)
    marcas, sistemas = [], []
    for capa in capas:
        ids = ids_a_exportar(capa, solo_seleccion)
        rev = revisar(capa, ids)
        sistema = responder(rev)
        if sistema is False:
            res.cancelado = True
            return res
        if sistema is None:
            res.saltadas.append(capa.name())
            continue
        marcas += marcas_de(capa, sistema, nombres[capa], ids, ajustes, proyecto, res.salteados)
        sistemas.append(sistema)
        detalle = QgsCoordinateTransform(sistema, QgsCoordinateReferenceSystem(WGS84),
                                         proyecto.transformContext()).instantiatedCoordinateOperationDetails()
        if detalle.accuracy and detalle.accuracy > 1:
            aviso = f"{sistema.description()}: precisión de la conversión ≈ {detalle.accuracy:g} m"
            if aviso not in res.avisos:
                res.avisos.append(aviso)
    if not marcas:
        return res
    codigos = {s.authid() for s in sistemas}
    origen = codigos.pop() if len(codigos) == 1 else ""
    titulo = Path(ruta).stem
    plan = F.PlanKml(marcas, res.salteados, origen, titulo,
                     nombre_origen=nombre_sistema(origen) if origen else "varios sistemas")
    res.ruta = F.escribir(plan, ruta)
    res.objetos, res.carpetas = len(marcas), len(plan.carpetas())
    return res


def capas_del_proyecto(proyecto=None) -> list:
    """[(capa, visible)]: las vectoriales con geometría, en el orden del panel."""
    proyecto = proyecto or QgsProject.instance()
    salida = []
    for nodo in proyecto.layerTreeRoot().findLayers():
        capa = nodo.layer()
        if isinstance(capa, QgsVectorLayer) and capa.isValid() and capa.isSpatial():
            salida.append((capa, nodo.isVisible()))
    return salida


def resumen(res: Resultado) -> str:
    texto = f"{res.objetos} objeto(s) a {Path(res.ruta).name}, en {res.carpetas} carpeta(s)."
    if res.salteados:
        texto += " No se exportaron: " + ", ".join(f"{k} {v}" for k, v in sorted(res.salteados.items())) + "."
    if res.saltadas:
        texto += " Capas salteadas: " + ", ".join(res.saltadas) + "."
    if res.avisos:
        texto += " " + "; ".join(res.avisos) + "."
    return texto


def con_extension(texto: str) -> Path:
    p = Path(texto.strip())
    return p if p.suffix.lower() in (".kmz", ".kml") else p.with_name(p.name + ".kmz")


# ------------------------------------------------------------------ la ventana
class ExportarDialog(QDialog):
    def __init__(self, capas, ruta: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar a Google Earth (KML/KMZ)")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Capas (una carpeta por capa en Google Earth):"))
        self.lista = QListWidget()
        for capa, visible in capas:
            crs = capa.crs()
            sistema = crs.authid() if crs.isValid() else "sin sistema"
            it = QListWidgetItem(f"{capa.name()}  ({sistema})")
            it.setData(Qt.ItemDataRole.UserRole, capa.id())
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
            self.lista.addItem(it)
        lay.addWidget(self.lista)
        hay_sel = any(c.selectedFeatureCount() for c, _v in capas)
        self.solo_sel = QCheckBox("Sólo los elementos seleccionados (en las capas que tengan selección)")
        self.solo_sel.setEnabled(hay_sel)
        lay.addWidget(self.solo_sel)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Archivo:"))
        self.ruta = QLineEdit(ruta)
        fila.addWidget(self.ruta)
        examinar = QPushButton("Examinar...")
        examinar.clicked.connect(self._examinar)
        fila.addWidget(examinar)
        lay.addLayout(fila)
        self.abrir = QCheckBox("Abrir en Google Earth al terminar")
        self.abrir.setChecked(True)
        lay.addWidget(self.abrir)
        self.aviso = QLabel("")
        lay.addWidget(self.aviso)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def _examinar(self) -> None:
        ruta, _f = QFileDialog.getSaveFileName(self, TITULO, self.ruta.text(),
                                               "Google Earth KMZ (*.kmz);;KML (*.kml)")
        if ruta:
            self.ruta.setText(ruta)

    def ids_elegidos(self) -> list:
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.CheckState.Checked]

    def accept(self) -> None:
        if not self.ids_elegidos():
            self.aviso.setText("Tildá al menos una capa.")
            return
        if not self.ruta.text().strip():
            self.aviso.setText("Elegí el archivo.")
            return
        super().accept()


class KmlQgis:
    """Las dos herramientas del banco. No tocan menús ni barras."""

    def __init__(self, iface) -> None:
        self.iface = iface

    def _aviso(self, texto: str, nivel=Qgis.MessageLevel.Info) -> None:
        self.iface.messageBar().pushMessage("GeoCAD", texto, level=nivel, duration=10)

    def _terminar(self, res: Resultado, abrir: bool) -> None:
        if res.cancelado:
            self._aviso("Exportación cancelada: no se escribió nada.")
            return
        if res.ruta is None:
            self._aviso("No hay nada que exportar en las capas elegidas.", Qgis.MessageLevel.Warning)
            return
        self._aviso(resumen(res), Qgis.MessageLevel.Success)
        if abrir and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(res.ruta))):
            QMessageBox.information(self.iface.mainWindow(), TITULO,
                                    f"Abrí este archivo con Google Earth Pro (Archivo > Abrir):\n{res.ruta}")

    def _ejecutar(self, capas, ruta, solo_sel, abrir) -> Resultado:
        try:
            res = exportar(capas, ruta, solo_sel, parent=self.iface.mainWindow(),
                           ajustes=self.iface.mapCanvas().mapSettings())
        except OSError as exc:
            self._aviso(f"No se pudo escribir {Path(ruta).name} ({exc}). El archivo anterior quedó como estaba.",
                        Qgis.MessageLevel.Critical)
            return Resultado(cancelado=True)
        self._terminar(res, abrir)
        return res

    def ruta_inicial(self) -> str:
        proyecto = QgsProject.instance()
        carpeta = QSettings().value(CLAVE_CARPETA, "") or proyecto.homePath() or str(Path.home())
        return str(Path(carpeta) / ((proyecto.baseName() or "GeoCAD") + ".kmz"))

    def exportar(self, _marcado=False):
        capas = capas_del_proyecto()
        if not capas:
            self._aviso("El proyecto no tiene capas vectoriales.", Qgis.MessageLevel.Warning)
            return None
        dlg = ExportarDialog(capas, self.ruta_inicial(), self.iface.mainWindow())
        if not dlg.exec():
            return None
        ruta = con_extension(dlg.ruta.text())
        if ruta.exists() and QMessageBox.question(self.iface.mainWindow(), TITULO,
                                                  f"Ya existe {ruta.name}. ¿Reemplazarlo?") \
                != QMessageBox.StandardButton.Yes:
            return None
        QSettings().setValue(CLAVE_CARPETA, str(ruta.parent))
        elegidas = set(dlg.ids_elegidos())
        return self._ejecutar([c for c, _v in capas if c.id() in elegidas], ruta,
                              dlg.solo_sel.isChecked(), dlg.abrir.isChecked())

    def ver(self, _marcado=False):
        """Las capas visibles, directo a Google Earth."""
        capas = [c for c, visible in capas_del_proyecto() if visible]
        if not capas:
            self._aviso("No hay capas vectoriales visibles.", Qgis.MessageLevel.Warning)
            return None
        ruta = GE.archivo_kml().parent / "GeoCAD desde QGIS.kmz"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        return self._ejecutar(capas, ruta, False, True)
