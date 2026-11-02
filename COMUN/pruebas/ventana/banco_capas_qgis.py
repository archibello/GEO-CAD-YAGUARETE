"""Banco con el QGIS REAL (sin pantalla): el panel Capas y la barra de IngeCAD
en QGIS (3.60.0). Desde la 3.61.2, con el estilo Breeze y la letra de QGIS:
la barra con la letra y las filas del panel, justa, y los números de Grosor enteros.

Fernando, 01/11/2026: «reemplaces por completo el panel administrador de
capas de QGIS (Yaguá Capas) por el de IngeCAD y que adoptes todos sus
comportamientos». Comprueba la barra (lista de capa + Color, Tipo y Grosor,
nada más), el panel acoplado con las columnas de IngeCAD, nueva capa con el
nombre abierto, clic en bombilla / sol / candado / impresora, doble clic =
actual, renombrar, eliminar (0, actual, en uso), Buscar capa, filtros de
grupo (crear, poner capas, mostrar, estado de todas, CAPAP), columnas
ocultas que se recuerdan, y la regla de la barra: con selección cambia los
objetos, sin selección es lo actual para lo próximo; elegir capa = PorCapa.

Se corre como banco_botones_qgis.py. Termina en «TODO OK».
"""
import os, sys, tempfile, faulthandler
faulthandler.dump_traceback_later(180, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
# como el QGIS de Fernando (3.61.2): estilo Breeze y la letra de 11 pt que QGIS pone con
# una hoja de estilo para toda la aplicación (un setFont() solo no alcanza)
from qgis.PyQt.QtWidgets import QStyleFactory
if "Breeze" in QStyleFactory.keys():
    app.setStyle(QStyleFactory.create("Breeze"))
app.setStyleSheet("* { font-size: 11pt; }")
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidgetAction

iface = get_iface()
win = QMainWindow()
canvas = QgsMapCanvas(win)
win.setCentralWidget(canvas)
win.show()
iface.mainWindow.return_value = win
iface.mapCanvas.return_value = canvas
iface.addToolBar.side_effect = lambda nombre: win.addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: win.addDockWidget(area, dock)
iface.removeDockWidget.side_effect = lambda dock: win.removeDockWidget(dock)
mensajes = []
from qgis.PyQt.QtCore import Qt as _Qt
capas_qgis = QDockWidget("Capas", win)          # el panel Capas de QGIS
capas_qgis.setObjectName("Layers")
win.addDockWidget(_Qt.DockWidgetArea.LeftDockWidgetArea, capas_qgis)
iface.messageBar.return_value.pushMessage.side_effect = lambda *a, **k: mensajes.append(a[1])

fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def eventos():
    for _ in range(3):
        QApplication.processEvents()


capa = QgsVectorLayer("LineString?crs=EPSG:3857&field=id:integer", "Obra", "memory")
QgsProject.instance().addMapLayer(capa)
for i in range(2):
    f = QgsFeature(capa.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(i, 0), QgsPointXY(i, 10)]))
    f.setAttributes([i])
    capa.dataProvider().addFeatures([f])

from geocad.capas.plugin import LayerPropertiesPlugin
P = LayerPropertiesPlugin(iface)
P.initGui()
ctrl = P.ctrl
ctrl.attach(capa)
ctrl.ensure_initialized()
eventos()

# ---- 1. la barra de IngeCAD -----------------------------------------------------------
ids = [a.property("geocad_id") for a in P.toolbar.actions()]
comprobar(ids == ["capas:layprops", "capas:capa", "capas:color", "capas:linetype", "capas:lineweight"],
          "barra = botón del panel + capa + color + tipo + grosor (%s)" % ids)
comprobar(all(isinstance(a, QWidgetAction) for a in P.toolbar.actions()[1:]), "las cuatro son listas")
# 3.60.2: el panel aparece solo al arrancar, en pestaña junto al panel Capas de QGIS
comprobar(P.dock is not None and P.dock.isVisible() and P.a_props.isChecked(),
          "3.60.2: el panel Yaguá Capas está a la vista desde el arranque")
# 3.60.4: a la derecha y solo (en pestaña sumaba altura mínima y la ventana no entraba)
comprobar(int(win.dockWidgetArea(P.dock).value) == 2 and not win.tabifiedDockWidgets(P.dock),
          "3.60.4: a la derecha, solo, sin pestaña")
comprobar(P.dock.minimumSizeHint().height() <= 120, "poca altura mínima (%d)" % P.dock.minimumSizeHint().height())
comprobar(P.props[0].currentText() == "PorCapa" and P.props[1].currentText() == "PorCapa"
          and P.props[2].currentText() == "PorCapa", "sin selección: PorCapa")
# 3.61.2 (Fernando, 02/11/2026, QGIS 4.2.2: la lista de Grosor decía «Po…pa», «0…m»):
# la barra con la letra y las filas del panel, y todo el texto entero
from geocad.capas.medidas import FILA, LETRA_PX
from qgis.PyQt.QtWidgets import QStyle, QStyleOptionComboBox
for lista in [P.combo] + P.props:
    nombre = type(lista).__name__
    comprobar(lista.fontInfo().pixelSize() == LETRA_PX and lista.view().fontInfo().pixelSize() == LETRA_PX,
              "%s: letra de %d px como el panel (%d / %d)" % (nombre, LETRA_PX, lista.fontInfo().pixelSize(),
                                                          lista.view().fontInfo().pixelSize()))
    lista.showPopup()
    eventos()
    v = lista.view()
    comprobar(v.sizeHintForRow(0) == FILA, "%s: filas de %d (%d)" % (nombre, FILA, v.sizeHintForRow(0)))
    lista.hidePopup()
    eventos()
# Fernando: «el resto puede estar más justo»: capa, Color y Tipo con los anchos de IngeCAD 0.7.0
anchos = [P.combo.width(), P.props[0].width(), P.props[1].width()]
comprobar(anchos == [200, 96, 128], "capa, Color y Tipo con los anchos de IngeCAD %s" % anchos)
# «lo importante es que se vean los números para elegir los espesores de líneas»: en el
# desplegable de Grosor cada número entero; si no entra, se recorta la muestra, nunca el número
from geocad.capas.barra import GrosorDelegate
from qgis.PyQt.QtCore import QRect
grosor = P.props[2]
comprobar(isinstance(grosor.itemDelegate(), GrosorDelegate), "Grosor dibuja sus filas con el número primero")
grosor.showPopup()
eventos()
v = grosor.view()
fm = v.fontMetrics()
dg = grosor.itemDelegate()
textos = [grosor.itemText(i) for i in range(grosor.count())]
comprobar(textos[:2] == ["PorCapa", "Por defecto"] and "0.00 mm" in textos and "2.11 mm" in textos,
          "Grosor: PorCapa, Por defecto y de 0.00 a 2.11 mm")
for ancho in (v.viewport().width(), 90, 70, 50):
    cortados, sin_muestra = [], []
    for t in textos:
        mw, lugar = dg.partes(QRect(0, 0, ancho, FILA), fm, t)
        if lugar.width() < fm.horizontalAdvance(t):
            cortados.append(t)
        if mw == 0:
            sin_muestra.append(t)
    comprobar(not cortados, "Grosor a %d px: los números enteros %s" % (ancho, cortados or ""))
    if ancho == v.viewport().width():
        comprobar(not sin_muestra, "Grosor a %d px (el del desplegable): con muestra y número" % ancho)
grosor.hidePopup()
eventos()
opt = QStyleOptionComboBox()
grosor.initStyleOption(opt)
campo = grosor.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, opt,
                                      QStyle.SubControl.SC_ComboBoxEditField, grosor).width()
largos = [t for t in textos if fm.horizontalAdvance(t) + grosor.iconSize().width() + 4 > campo]
comprobar(not largos, "la casilla de Grosor (%d px) muestra entero %s" % (campo, largos or "cada valor"))
comprobar(P.props[2].findText("0.25 mm") >= 0 and P.props[2].findText("Por defecto") >= 0, "grosores con su nombre")
textos_menu = [a.text() for a, _m in P.actions]
comprobar("Panel Yaguá Capas (LAYER)" in textos_menu and "Aislar (LAYISO)" in textos_menu, "LAYER y LAYISO en el menú")

# ---- 2. el panel ---------------------------------------------------------------------
P.toggle_manager(True)
eventos()
dock = P.dock
panel = dock.panel
comprobar(isinstance(dock, QDockWidget) and not dock.isFloating(), "panel acoplado al costado")
comprobar(dock.windowTitle() == "Yaguá Capas · Obra", "título con la capa QGIS: %r" % dock.windowTitle())
t = panel.table
comprobar(t.fontInfo().pixelSize() == P.props[2].fontInfo().pixelSize(),
          "3.61.2: el panel y la barra con la misma letra (%d)" % t.fontInfo().pixelSize())
cabeza = [t.horizontalHeaderItem(c).toolTip() for c in range(t.columnCount())]
comprobar(cabeza == ["Estado", "Nombre", "Encendida/Apagada", "Inut", "Bloq", "Color", "Tipo de línea",
                     "Grosor de línea", "Imprimir", "Descripción"], "columnas de IngeCAD")
comprobar(t.isColumnHidden(9) and not t.isColumnHidden(5), "Descripción oculta de entrada")
comprobar(not panel.filters.isVisible(), "sin filtros: el árbol no se ve")
comprobar(panel._rows == ["0"] and t.item(0, 0).text() == "✓", "capa 0 actual (✓)")

# nueva capa: con el nombre abierto para escribir
panel.new_layer()
eventos()
comprobar("Capa1" in ctrl.names() and t.state() == t.State.EditingState, "nueva capa con el nombre abierto")
fila = panel._rows.index("Capa1")
t.closePersistentEditor(t.item(fila, 1))
eventos()

# clics en los estados
for col, prop, esperado in ((2, "on", False), (3, "frozen", True), (4, "locked", True), (8, "plot", False)):
    fila = panel._rows.index("Capa1")
    t.cellClicked.emit(fila, col)
    eventos()
    comprobar(ctrl.find("Capa1")[prop] is esperado, "clic en la columna %d: %s = %s" % (col, prop, esperado))
for col in (2, 3, 4, 8):
    t.cellClicked.emit(panel._rows.index("Capa1"), col)
    eventos()
lay = ctrl.find("Capa1")
comprobar(lay["on"] and not lay["frozen"] and not lay["locked"] and lay["plot"], "segundo clic: vuelve")

# doble clic = actual
t.cellDoubleClicked.emit(panel._rows.index("Capa1"), 0)
eventos()
comprobar(ctrl.current == "Capa1" and t.item(panel._rows.index("Capa1"), 0).text() == "✓",
          "doble clic: Capa1 actual")

# renombrar en la celda
fila = panel._rows.index("Capa1")
t.item(fila, 1).setText("Muros")
eventos()
comprobar("Muros" in ctrl.names() and ctrl.current == "Muros", "renombrada en la celda (sigue actual)")

# eliminar: la 0, la actual y la que tiene objetos no
mensajes.clear()
t.setCurrentCell(panel._rows.index("0"), 1)
panel.delete_layer()
t.setCurrentCell(panel._rows.index("Muros"), 1)
panel.delete_layer()
comprobar("0" in ctrl.names() and "Muros" in ctrl.names(), "no elimina la 0 ni la actual")
comprobar("La capa 0 no se puede suprimir." in mensajes and "No se puede eliminar la capa actual." in mensajes,
          "avisos de IngeCAD: %s" % mensajes)
panel.make_current("0")
eventos()
t.setCurrentCell(panel._rows.index("Muros"), 1)
panel.new_layer()                                     # Capa1, con las propiedades de Muros
eventos()
t.setCurrentCell(panel._rows.index("Capa1"), 1)
panel.delete_layer()
eventos()
comprobar("Capa1" not in ctrl.names(), "elimina una capa vacía")

# Buscar capa
panel.search.setText("mur")
eventos()
comprobar(panel._rows == ["Muros"], "Buscar capa: %s" % panel._rows)
panel.search.clear()
eventos()

# ---- 3. filtros de grupo ---------------------------------------------------------------
panel.new_group_filter()
eventos()
comprobar(panel.filters.isVisible() and ctrl.filters()[0]["name"] == "Filtro de grupo1",
          "nuevo filtro de grupo: el árbol aparece")
item = panel.filters.currentItem()
comprobar(item is not None and item.text(0) == "Filtro de grupo1", "el grupo nuevo queda elegido")
comprobar(panel._rows == [], "grupo vacío: sin capas")
panel.group_layers(("Filtro de grupo1",), ["Muros"], True)
eventos()
comprobar(panel._rows == ["Muros"], "capa puesta en el grupo: se muestra")
panel.set_filter_state("on", False)
eventos()
comprobar(not ctrl.find("Muros")["on"] and ctrl.find("0")["on"], "Desactivar capas: sólo las del grupo")
ctrl.layer_previous()
ctrl.layer_previous()                                 # CAPAP: deshace el estado y el poner en el grupo
eventos()
comprobar(ctrl.find("Muros")["on"] and ctrl.filters()[0]["layers"] == [], "CAPAP deshace (también grupos)")
item = panel.filters.currentItem()
item.setText(0, "Estructura")
eventos()
comprobar(ctrl.filters()[0]["name"] == "Estructura", "grupo renombrado en el árbol")
panel.filters.setCurrentItem(panel.filters.topLevelItem(0).child(0))      # Todas las capas utilizadas
eventos()
comprobar(panel._rows == ["0"], "Todas las capas utilizadas: %s" % panel._rows)
panel.filters.setCurrentItem(panel.filters.topLevelItem(0))
eventos()

# columnas ocultas: se recuerdan
panel._toggle_column(6, False)
panel2 = type(panel)(ctrl)
comprobar(panel2.table.isColumnHidden(6) and panel2.table.isColumnHidden(9), "columnas ocultas recordadas")
panel._toggle_column(6, True)

# ---- 4. la barra: selección o lo próximo -----------------------------------------------
color, tipo, grosor = P.props
color.apply("#ff0000")
tipo.apply("DASHED")
eventos()
comprobar(ctrl.current_prop("color") == "#ff0000" and color.currentText() == "Rojo", "color actual Rojo")
attrs = ctrl.new_feature_attrs(capa)
idx_c, idx_t = capa.fields().indexOf("CAD_COLOR"), capa.fields().indexOf("CAD_LTYPE")
comprobar(attrs.get(idx_c) == "#ff0000" and attrs.get(idx_t) == "DASHED", "un objeto nuevo nace rojo y DASHED")
comprobar(capa.fields().indexOf("CAD_LW") == -1, "grosor PorCapa: no crea CAD_LW")
capa.selectByIds([next(capa.getFeatures()).id()])
eventos()
comprobar(color.currentText() == "PorCapa", "con selección muestra la de los objetos")
fid = list(capa.selectedFeatureIds())[0]
grosor.apply(0.5)
eventos()
comprobar(abs(capa.getFeature(fid)["CAD_LW"] - 0.5) < 1e-9, "con selección cambia los objetos (0.50 mm)")
comprobar(ctrl.current_prop("lineweight") is None, "y no toca lo actual")
comprobar(not capa.selectedFeatureCount(), "3.60.1: después de asignar la selección se quita")
capa.selectByIds([fid])
eventos()
color.apply("#00ff00")
eventos()
comprobar(capa.getFeature(fid)["CAD_COLOR"] == "#00ff00" and not capa.selectedFeatureCount(),
          "objeto verde, sin selección")
capa.selectByIds([fid])
eventos()
P.combo._choose("Muros")
eventos()
f = capa.getFeature(fid)
comprobar(f["LAYER_CODE"] == "Muros" and (f["CAD_COLOR"] in (None, "") or str(f["CAD_COLOR"]) == "NULL"),
          "elegir capa con selección: la capa y color PorCapa")
comprobar(not capa.selectedFeatureCount() and P.combo.display_name() == "0",
          "3.60.1: la selección se quita y la lista vuelve a la capa actual")
eventos()
P.combo._choose("0")
eventos()
comprobar(ctrl.current == "0" and ctrl.current_prop("color") is None, "elegir capa sin selección: color PorCapa")
comprobar(capa.isEditable(), "los cambios quedan en edición, para deshacer con QGIS")
capa.rollBack()

# ---- 4b. 3.60.2 (Fernando): una capa sin capas CAD y con su propio estilo -------------
# «Nueva capa borrador» de Fernando: polígonos con CAD_COLOR, categorizados por CAD_COLOR con
# colores al azar. La barra escribía el valor pero el mapa seguía con el color al azar.
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsMapRendererSequentialJob,
                       QgsMapSettings, QgsRendererCategory)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
borr = QgsVectorLayer("Polygon?crs=EPSG:3857&field=CAD_COLOR:string(20)", "Nueva capa borrador", "memory")
QgsProject.instance().addMapLayer(borr)
fb = QgsFeature(borr.fields())
fb.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(100, 0), QgsPointXY(100, 100),
                                           QgsPointXY(0, 100), QgsPointXY(0, 0)]]))
fb.setAttributes(["#0000ff"])
borr.dataProvider().addFeatures([fb])
azul_al_azar = QgsFillSymbol.createSimple({"color": "0,200,0", "outline_color": "0,200,0",
                                           "outline_width": "3"})
borr.setRenderer(QgsCategorizedSymbolRenderer("CAD_COLOR", [QgsRendererCategory("#0000ff", azul_al_azar,
                                                                                "#0000ff")]))
ctrl.attach(borr)
eventos()
borr.selectAll()
eventos()
color.apply("#ff0000")
grosor.apply(2.11)
eventos()
fb = next(borr.getFeatures())
comprobar(fb["CAD_COLOR"] == "#ff0000", "el valor se escribe")
comprobar(borr.fields().indexOf("LAYER_CODE") != -1 and borr.customProperty("cad_layer_manager/config"),
          "la capa queda preparada con capas CAD")


def pintado(lyr):
    ms = QgsMapSettings()
    ms.setLayers([lyr])
    ms.setDestinationCrs(lyr.crs())
    ms.setExtent(lyr.extent().buffered(20))
    ms.setOutputSize(QSize(200, 200))
    ms.setBackgroundColor(QColor(255, 255, 255))
    job = QgsMapRendererSequentialJob(ms)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    colores = set()
    for x in range(0, 200, 2):
        for y in range(0, 200, 2):
            c = img.pixelColor(x, y)
            colores.add((c.red() > 200 and c.green() < 60 and c.blue() < 60, c.green() > 150 and c.red() < 60))
    return colores


vistos = pintado(borr)
comprobar(any(r for r, _g in vistos), "el mapa lo dibuja rojo")
comprobar(not any(g for _r, g in vistos), "y ya no con el color al azar")

# ---- 4c. 3.60.2 (Fernando): «could not convert string to float: '#00ff00'» -------------
# capa en edición con CAD_COLOR nuevo sin guardar y sin LAYER_CODE: al prepararla, LAYER_CODE
# entraba por el proveedor y los valores se corrían de columna (el color quedaba en CAD_LW)
from qgis.core import QgsField
from qgis.PyQt.QtCore import QMetaType
ed = QgsVectorLayer("Polygon?crs=EPSG:3857&field=id:integer", "Borrador en edición", "memory")
QgsProject.instance().addMapLayer(ed)
fe = QgsFeature(ed.fields())
fe.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(9, 0), QgsPointXY(9, 9),
                                           QgsPointXY(0, 0)]]))
fe.setAttributes([1])
ed.dataProvider().addFeatures([fe])
ed.startEditing()
ed.addAttribute(QgsField("CAD_COLOR", QMetaType.Type.QString))
ed.addAttribute(QgsField("CAD_LW", QMetaType.Type.Double))
fid_e = next(ed.getFeatures()).id()
ed.changeAttributeValue(fid_e, ed.fields().indexOf("CAD_COLOR"), "#00ff00")
ctrl.attach(ed)
eventos()
ed.selectAll()
eventos()
errores_barra = []
try:
    grosor.apply(2.11)
    ed.selectAll()
    grosor.refresh()
    color.refresh()
except Exception as e:  # noqa: BLE001
    errores_barra.append(repr(e))
eventos()
fe = ed.getFeature(fid_e)
comprobar(not errores_barra, "sin error en la barra %s" % errores_barra)
comprobar(fe["CAD_COLOR"] == "#00ff00" and abs(float(fe["CAD_LW"]) - 2.11) < 1e-9
          and fe["LAYER_CODE"] in (None, "0") or str(fe["LAYER_CODE"]) == "NULL",
          "los valores siguen en su columna (%s)" % fe.attributes())
comprobar(color.currentText() == "Verde", "la barra muestra el verde del objeto")
# 3.60.3: LAYER_CODE recién agregado en la edición no tiene nombre de tipo: sin aviso falso
mensajes.clear()
ed.selectAll()
eventos()
P.combo._choose("0")
eventos()
comprobar(not [m for m in mensajes if "debe ser texto" in m], "sin el aviso falso del tipo (%s)" % mensajes)
ed.rollBack()
ctrl.attach(capa)
eventos()

# cerrado con la ×: se recuerda
P.dock.close()
eventos()
comprobar(not P.a_props.isChecked() and ctrl.setting("panel/visible", True, bool) is False,
          "cerrado con la ×: el botón se apaga y se recuerda")
P.a_props.trigger()
eventos()
comprobar(P.dock.isVisible() and ctrl.setting("panel/visible", False, bool) is True, "el botón lo vuelve a abrir")

# ---- 5. descargar -----------------------------------------------------------------------
P.unload()
from qgis.PyQt.QtCore import QCoreApplication, QEvent
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
eventos()
comprobar(not [d for d in win.findChildren(QDockWidget) if d.objectName() == "YaguaCapasDock"
               and d.isVisible()], "al descargar el panel se va")
print("TODO OK" if not fallas else "FALLAS: %s" % fallas)
sys.exit(1 if fallas else 0)
