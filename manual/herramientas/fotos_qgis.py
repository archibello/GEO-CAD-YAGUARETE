"""Capturas del manual con la APLICACIÓN QGIS real, sin pantalla.

Corre dentro de QGIS con --code, como los bancos de COMUN/pruebas/ventana:
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=FOTOS_SALIDA=<carpeta de imágenes> --env=FOTOS_CODIGO=<carpeta con geocad> \\
      --env=FOTOS_DATOS=<carpeta con parcelas.shp> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
No envía nada a IngeCAD ni abre Google Earth: abre cada ventana, la fotografía y la cierra.
"""
import os, sys, tempfile, traceback
import math
from qgis.core import (QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsFillSymbol,
                       QgsLayoutItemMap, QgsPalLayerSettings, QgsPointXY, QgsPrintLayout, QgsProject,
                       QgsRectangle, QgsRendererCategory, QgsTextFormat, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes)
from qgis.PyQt.QtCore import QPoint, QTimer
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QWidget
from qgis.utils import iface

sys.path.insert(0, os.environ["FOTOS_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="fotos-home-")
SALIDA = os.environ["FOTOS_SALIDA"]
DATOS = os.environ["FOTOS_DATOS"]
log = []
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)


def esperar(ms=300):
    QTest.qWait(ms)
    QApplication.processEvents()


def foto(widget, nombre):
    esperar(200)
    widget.grab().save(os.path.join(SALIDA, nombre + ".png"))
    log.append("foto " + nombre)


def ruta_neutra(dlg):
    from qgis.PyQt.QtWidgets import QLineEdit
    for e in dlg.findChildren(QLineEdit):
        if "/" in e.text():
            e.setText("Manzana12.kmz")


def foto_modal(abrir, nombre, antes=None):
    """Abre una ventana modal con «abrir», la fotografía y la cierra."""
    def tomar():
        w = QApplication.activeModalWidget()
        if w is None:
            vis = [x for x in QApplication.topLevelWidgets() if isinstance(x, QDialog) and x.isVisible()]
            w = vis[-1] if vis else None
        if w is None:
            log.append("SIN VENTANA " + nombre)
            return
        if antes:
            antes(w)
        foto(w, nombre)
        w.reject() if isinstance(w, QDialog) else w.close()
    QTimer.singleShot(1200, tomar)
    try:
        abrir()
    except Exception as exc:              # noqa: BLE001
        log.append("error %s: %s" % (nombre, exc))


def capa_parcelas():
    lyr = QgsVectorLayer(os.path.join(DATOS, "parcelas.shp"), "Parcelas", "ogr")
    assert lyr.isValid()
    colores = {"Residencial": "#f2dfb3", "Comercial": "#f4a582", "Mixto": "#c2a5cf", "Baldío": "#d9f0d3"}
    cats = []
    for uso, col in colores.items():
        s = QgsFillSymbol.createSimple({"color": col, "outline_color": "#5b4a2f", "outline_width": "0.3"})
        cats.append(QgsRendererCategory(uso, s, uso))
    lyr.setRenderer(QgsCategorizedSymbolRenderer("USO", cats))
    pal = QgsPalLayerSettings()
    pal.fieldName = "LOTE"
    fmt = QgsTextFormat()
    fmt.setFont(QFont("DejaVu Sans"))
    fmt.setSize(8)
    pal.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    lyr.setLabelsEnabled(True)
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def correr():
    from geocad import classFactory, modulos

    modulos.guardar("qgis", {m.clave: True for m in modulos.catalogo("qgis")})
    QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:5348"))
    lyr = capa_parcelas()
    mw = iface.mainWindow()
    mw.resize(1500, 920)
    mw.show()
    plug = classFactory(iface)
    plug.initGui()
    esperar(500)
    if hasattr(plug, "_cargar_subs"):
        plug._cargar_subs()
    esperar(500)
    iface.setActiveLayer(lyr)
    manzana = [f for f in lyr.getFeatures() if f["MANZANA"] == "12"]
    r = QgsRectangle(manzana[0].geometry().boundingBox())
    for f in manzana[1:]:
        r.combineExtentWith(f.geometry().boundingBox())
    r.grow(35)
    can = iface.mapCanvas()
    can.setExtent(r)
    can.refresh()
    can.waitWhileRendering()
    esperar(1500)
    iface.messageBar().clearWidgets()
    esperar(300)
    foto(mw, "qgis_ventana")

    menu = plug.menu
    menu.popup(mw.mapToGlobal(QPoint(300, 30)))
    esperar(500)
    foto(menu, "qgis_menu_geocad")
    menu.hide()

    foto_modal(plug.choose_modules, "qgis_modulos")
    foto_modal(plug._options, "qgis_enviar_ingecad")
    foto_modal(plug.administrar_botones, "qgis_administrar_herramientas")
    act = plug.actions.get("ge_exportar")
    if act is not None:
        foto_modal(act.trigger, "qgis_exportar_google_earth", ruta_neutra)
    else:
        log.append("sin acción ge_exportar: " + ", ".join(sorted(plug.actions)))

    rumbos(plug, lyr, manzana, can)
    composicion(plug, lyr, r)


def dms(a):
    a = a % 360
    g = int(a); m = int((a - g) * 60); s = round(((a - g) * 60 - m) * 60)
    if s == 60:
        s, m = 0, m + 1
    if m == 60:
        m, g = 0, g + 1
    return "%dd%02d'%02d\"" % (g, m, s)


def rumbo(p, q):
    return math.degrees(math.atan2(q.y() - p.y(), q.x() - p.x()))


def rumbos(plug, lyr, manzana, can):
    """RUMBOS con un lote real de la manzana 12: el de más vértices."""
    mgr = plug.subs.activos["dibujo"][0].mgr
    lote = max(manzana, key=lambda f: len(list(f.geometry().vertices())))
    v = [QgsPointXY(p.x(), p.y()) for p in lote.geometry().vertices()][:-1]
    if sum(v[i].x() * v[(i + 1) % len(v)].y() - v[(i + 1) % len(v)].x() * v[i].y() for i in range(len(v))) > 0:
        v.reverse()                            # horario: así el ángulo interior de RUMBOS da 90 en las esquinas
    tramos = []
    for i in range(len(v)):
        a, b, c = v[i - 1], v[i], v[(i + 1) % len(v)]
        ang = rumbo(b, c) - rumbo(a, b) - 180
        tramos.append((b.distance(c), ang % 360))
    with open(os.path.join(SALIDA, "rumbos_lote.txt"), "w", encoding="utf-8") as sal:
        sal.write("lote %s, manzana %s, %d vertices\n" % (lote["LOTE"], lote["MANZANA"], len(v)))
        for d, ang in tramos:
            sal.write("%.2f<%s\n" % (d, dms(ang)))
    mensura = QgsVectorLayer("Polygon?crs=EPSG:5348", "Mensura", "memory")
    sim = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#c0392b", "outline_width": "0.8"})
    mensura.renderer().setSymbol(sim)
    QgsProject.instance().addMapLayer(mensura)
    mensura.startEditing()
    iface.setActiveLayer(mensura)
    r = lote.geometry().boundingBox()
    r.grow(25)
    can.setExtent(r)
    can.refresh()
    can.waitWhileRendering()
    mgr.run("RUMBOS")
    mgr.point_clicked(v[-1], False, False)     # tramo base: el último lado
    mgr.point_clicked(v[0], False, False)
    for d, ang in tramos[:-1]:
        mgr.submit("%.2f<%s" % (d, dms(ang).replace("d", "d")))
        esperar(150)
    can.refresh()
    can.waitWhileRendering()
    esperar(800)
    foto(iface.mainWindow(), "qgis_rumbos")
    mgr.submit("C")
    esperar(300)
    geoms = [f.geometry() for f in mensura.getFeatures()]
    if geoms:
        dif = geoms[0].symDifference(lote.geometry()).area()
        log.append("rumbos: diferencia con el lote real %.4f m2" % dif)
    else:
        log.append("rumbos: no quedó el polígono")
    mensura.commitChanges()
    can.refresh()
    can.waitWhileRendering()
    esperar(500)
    foto(iface.mainWindow(), "qgis_rumbos_cerrado")
    iface.setActiveLayer(lyr)


def composicion(plug, lyr, r):
    lay = QgsPrintLayout(QgsProject.instance())
    lay.initializeDefaults()
    lay.setName("Manzana 12 A3")
    from qgis.core import QgsLayoutItemPage
    lay.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)
    mapa = QgsLayoutItemMap(lay)
    mapa.attemptMove(QgsLayoutPoint(10, 10, QgsUnitTypes.LayoutMillimeters))
    mapa.attemptResize(QgsLayoutSize(400, 277, QgsUnitTypes.LayoutMillimeters))
    mapa.setExtent(r)
    lay.addLayoutItem(mapa)
    QgsProject.instance().layoutManager().addLayout(lay)
    d = iface.openLayoutDesigner(lay)
    w = d.window()
    w.resize(1400, 900)
    w.show()
    esperar(1500)
    foto(w, "qgis_composicion")


try:
    correr()
    log.append("FIN")
except Exception:                          # noqa: BLE001
    log.append(traceback.format_exc())
with open(os.path.join(SALIDA, "fotos_qgis.txt"), "w", encoding="utf-8") as sal:
    sal.write("\n".join(log) + "\n")
QApplication.instance().exit(0)
os._exit(0)
