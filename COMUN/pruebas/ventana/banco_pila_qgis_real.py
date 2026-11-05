# -*- coding: utf-8 -*-
"""Objetos tapados con clics repetidos (módulo «Objetos tapados», 3.68), con QGIS real.

Clics de verdad sobre el mapa, con tres polígonos apilados en un shapefile y uno aparte: cada
clic pasa al siguiente y lo resalta; lo designado en otro lado se conserva; Mayús + clic, Esc y
otra capa; BORRA designando el tapado; y que ni el archivo, ni el modo edición, ni el estilo de
la capa cambian por elegir. Con el módulo apagado, repetir el clic da siempre el mismo.

Sin pantalla, en un perfil aparte, con GeoCAD instalado en ese perfil y la elección de módulos
ya guardada en <hogar> (ver el encabezado de banco_cursor_qgis_real.py):

    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen
        --env=HOME=<hogar> --env=BANCO_SALIDA=<carpeta>/f.txt
        org.qgis.qgis --nologo --noversioncheck --profiles-path <perfil>
        --code banco_pila_qgis_real.py
"""
import glob, hashlib, os, tempfile, time, traceback
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                       QgsRectangle, QgsVectorFileWriter, QgsVectorLayer)
from qgis.utils import iface, plugins
from qgis.PyQt.QtCore import QEvent, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtTest import QTest

canvas = iface.mapCanvas()
mw = iface.mainWindow()
lineas, fallas = [], []


def check(nombre, ok, extra=""):
    lineas.append("%s  %s %s" % ("ok" if ok else "MAL", nombre, extra))
    if not ok:
        fallas.append(nombre)


def pump(n=15):
    for _ in range(n):
        QApplication.processEvents()
        time.sleep(0.01)


def archivo(ruta):
    mem = QgsVectorLayer("Polygon?crs=EPSG:32721&field=z:integer", "m", "memory")
    feats = []
    for z, wkt in enumerate(("POLYGON((0 0,100 0,100 100,0 100,0 0))",
                             "POLYGON((20 20,80 20,80 80,20 80,20 20))",
                             "POLYGON((40 40,60 40,60 60,40 60,40 40))",
                             "POLYGON((300 0,400 0,400 100,300 100,300 0))")):
        f = QgsFeature(mem.fields())
        f.setAttribute("z", z)
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    op = QgsVectorFileWriter.SaveVectorOptions()
    op.driverName = "ESRI Shapefile"
    res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, ruta, QgsCoordinateTransformContext(), op)
    assert res[0] == QgsVectorFileWriter.WriterError.NoError, res


def huella(ruta):
    h = hashlib.sha256()
    for f in sorted(glob.glob(ruta[:-4] + ".*")):
        with open(f, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def clic(x, y, mods=Qt.KeyboardModifier.NoModifier):
    vp = canvas.viewport()
    p = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
    q = QPointF(p.x(), p.y())
    izq = Qt.MouseButton.LeftButton
    for tipo, cual, apretados in ((QEvent.Type.MouseMove, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton),
                                  (QEvent.Type.MouseButtonPress, izq, izq),
                                  (QEvent.Type.MouseButtonRelease, izq, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(tipo, q, QPointF(vp.mapToGlobal(q.toPoint())), cual, apretados, mods))
        pump(3)


def correr():
    mw.show()
    pump(40)
    dib = plugins["geocad"].subs.activos["dibujo"][0]
    mgr, cad = dib.mgr, dib.mgr.tool
    ruta = os.path.join(tempfile.mkdtemp(prefix="banco-pila-"), "pila.shp")
    archivo(ruta)
    capa = QgsVectorLayer(ruta, "Pila", "ogr")
    assert capa.isValid() and capa.featureCount() == 4
    otra = QgsVectorLayer("Point?crs=EPSG:32721", "Otra", "memory")
    QgsProject.instance().addMapLayers([otra, capa])
    iface.setActiveLayer(capa)
    canvas.setExtent(QgsRectangle(-50, -50, 450, 150))
    canvas.refresh()
    pump(40)
    check("el cursor de GeoCAD está activo", canvas.mapTool() is cad, type(canvas.mapTool()).__name__)
    pila = mgr.pila
    check("el módulo está prendido", pila is not None)
    por_z = {f["z"]: f.id() for f in capa.getFeatures()}
    A, B, C, D = [por_z[i] for i in range(4)]
    estilo = capa.renderer().dump()
    antes = huella(ruta)

    def sel():
        return set(capa.selectedFeatureIds())

    def banda():
        return cad.rb_pila.numberOfVertices()

    # ---- pasar de uno a otro
    vistos = []
    clic(50, 50)
    primero = sel()
    check("primer clic: uno solo y resaltado", len(primero) == 1 and banda() > 0 and pila.activa(),
          "%s banda=%d" % (primero, banda()))
    vistos.append(primero)
    for _ in range(2):
        clic(50, 50)
        vistos.append(sel())
    check("cada clic pasa a otro: los tres, de a uno",
          all(len(s) == 1 for s in vistos) and set().union(*vistos) == {A, B, C}, str(vistos))
    clic(50, 50)
    check("cuarto clic: da la vuelta", sel() == primero, str(sel()))
    bb = cad.rb_pila.asGeometry().boundingBox()
    elegido = next(capa.getFeatures("$id = %d" % pila.actual())).geometry().boundingBox()
    check("el resaltado es el contorno del elegido", abs(bb.width() - elegido.width()) < 1e-6
          and abs(bb.xMinimum() - elegido.xMinimum()) < 1e-6)

    # ---- lo de otro lado se conserva; otro lugar empieza de nuevo
    capa.removeSelection()
    mgr.pila_olvidar()
    clic(350, 50)
    check("objeto sin nada encima: se elige y sin resaltado", sel() == {D} and banda() == 0 and not pila.activa())
    clic(50, 50)
    uno = sel() - {D}
    clic(50, 50)
    dos = sel() - {D}
    check("lo designado en otro lugar se conserva", D in sel() and len(uno) == 1 and len(dos) == 1 and uno != dos,
          str(sel()))
    # ---- Mayús + clic quita el tapado que esté designado
    clic(50, 50, Qt.KeyboardModifier.ShiftModifier)
    check("Mayús + clic quita el de la pila y conserva el otro", sel() == {D} and banda() == 0, str(sel()))

    # ---- Esc
    clic(50, 50)
    clic(50, 50)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    pump(5)
    check("Esc: limpia y saca el resaltado", not sel() and banda() == 0 and not pila.activa())

    # ---- deseleccionar por otro lado y cambiar de capa
    clic(50, 50)
    clic(50, 50)
    capa.removeSelection()
    clic(350, 50)
    check("tras deseleccionar por otro lado no queda resaltado", banda() == 0, str(banda()))
    capa.removeSelection()
    clic(50, 50)
    clic(50, 50)
    iface.setActiveLayer(otra)
    pump(3)
    mgr.refresh()
    pump(3)
    check("otra capa activa: sin resaltado", banda() == 0)
    iface.setActiveLayer(capa)
    capa.removeSelection()
    pump(3)

    # ---- elegir no escribe nada
    check("elegir no abre la edición", not capa.isEditable() and not capa.isModified())
    check("elegir no cambia el estilo", capa.renderer().dump() == estilo and not capa.renderer().orderByEnabled())
    check("elegir no cambia el archivo", huella(ruta) == antes)

    # ---- dentro de un comando
    mgr.run("BORRA")
    pump()
    check("BORRA pide designar", mgr.command is not None and banda() == 0, str(mgr.command))
    clic(50, 50)
    x = sel()
    clic(50, 50)
    y = sel()
    check("BORRA, el clic repetido pasa al siguiente", len(x) == 1 and len(y) == 1 and x != y, "%s %s" % (x, y))
    borrado = next(iter(y))
    mgr.enter()
    pump(10)
    quedan = {f.id() for f in capa.getFeatures()}
    check("BORRA borra el tapado elegido y sólo ése", quedan == {A, B, C, D} - {borrado} and banda() == 0,
          "%s" % quedan)
    capa.rollBack()
    pump()
    check("rollBack: el archivo sigue igual", huella(ruta) == antes)

    # ---- apagado, como venía
    from geocad import modulos
    modulos.guardar("qgis", {"apilados": False})
    dib.unload()
    pump(10)
    dib.initGui()
    pump(10)
    check("apagado: sin pila", dib.mgr.pila is None)
    canvas.setMapTool(dib.mgr.tool)
    pump()
    iface.setActiveLayer(capa)
    capa.removeSelection()
    clic(50, 50)
    s1 = sel()
    clic(50, 50)
    check("apagado: repetir el clic da el mismo", len(s1) == 1 and sel() == s1 and dib.mgr.tool.rb_pila.numberOfVertices() == 0,
          "%s %s" % (s1, sel()))


try:
    correr()
except Exception:  # noqa: BLE001
    fallas.append("excepción")
    lineas.append(traceback.format_exc())
lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
os._exit(0)
