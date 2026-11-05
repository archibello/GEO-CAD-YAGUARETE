# -*- coding: utf-8 -*-
"""Agarres de vértices y Esc en la herramienta de vértices de QGIS (3.69), con QGIS real.

Clics y teclas de verdad sobre el mapa: aparecen y desaparecen los agarres; mover con clic, con
@dx,dy, con @d<ángulo, con una distancia, con ORTO y con referencia a objetos; marcar varios;
agregar y borrar vértices, y que un borrado que deja sin forma se rechace; edición topológica;
deshacer; que nada se guarda solo; Esc en Vértices de QGIS; y el módulo apagado.

Sin pantalla, en un perfil aparte, con GeoCAD instalado en ese perfil y la elección de módulos
ya guardada en <hogar> (ver el encabezado de banco_cursor_qgis_real.py):

    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen
        --env=HOME=<hogar> --env=BANCO_SALIDA=<carpeta>/f.txt
        org.qgis.qgis --nologo --noversioncheck --profiles-path <perfil>
        --code banco_agarres_qgis_real.py
"""
import faulthandler, glob, hashlib, os, tempfile, time, traceback
faulthandler.enable(open(os.environ["BANCO_SALIDA"] + ".falla", "w"))
from qgis.core import (QgsCoordinateTransformContext, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                       QgsRectangle, QgsSnappingConfig, QgsTolerance, QgsVectorFileWriter, QgsVectorLayer)
from qgis.utils import iface, plugins
from qgis.PyQt.QtCore import QEvent, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtTest import QTest

canvas = iface.mapCanvas()
mw = iface.mainWindow()
lineas, fallas = [], []
NADA = Qt.KeyboardModifier.NoModifier
MAYUS = Qt.KeyboardModifier.ShiftModifier


def check(nombre, ok, extra=""):
    lineas.append("%s  %s %s" % ("ok" if ok else "MAL", nombre, extra))
    if not ok:
        fallas.append(nombre)
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:   # si QGIS se cae, queda hasta dónde
        fh.write("\n".join(lineas) + "\n")


def pump(n=15):
    for _ in range(n):
        QApplication.processEvents()
        time.sleep(0.01)


def mouse(tipo, x, y, cual, apretados, mods=NADA):
    vp = canvas.viewport()
    p = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
    q = QPointF(p.x(), p.y())
    QApplication.sendEvent(vp, QMouseEvent(tipo, q, QPointF(vp.mapToGlobal(q.toPoint())), cual, apretados, mods))
    pump(3)


def mover(x, y):
    mouse(QEvent.Type.MouseMove, x, y, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)


def clic(x, y, mods=NADA):
    izq = Qt.MouseButton.LeftButton
    mover(x, y)
    mouse(QEvent.Type.MouseButtonPress, x, y, izq, izq, mods)
    mouse(QEvent.Type.MouseButtonRelease, x, y, izq, Qt.MouseButton.NoButton, mods)
    pump(5)


def huella(ruta):
    h = hashlib.sha256()
    for f in sorted(glob.glob(ruta[:-4] + ".*")):
        with open(f, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def archivo(ruta, tipo, wkts):
    mem = QgsVectorLayer("%s?crs=EPSG:32721&field=z:integer" % tipo, "m", "memory")
    feats = []
    for z, wkt in enumerate(wkts):
        f = QgsFeature(mem.fields())
        f.setAttribute("z", z)
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    op = QgsVectorFileWriter.SaveVectorOptions()
    op.driverName = "ESRI Shapefile"
    res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, ruta, QgsCoordinateTransformContext(), op)
    assert res[0] == QgsVectorFileWriter.WriterError.NoError, res
    lay = QgsVectorLayer(ruta, os.path.basename(ruta), "ogr")
    assert lay.isValid()
    return lay


def correr():
    mw.show()
    pump(40)
    dib = plugins["geocad"].subs.activos["dibujo"][0]
    mgr, cl, cad, ag = dib.mgr, dib.cmdline, dib.mgr.tool, dib.agarres
    check("el módulo está prendido", ag is not None)
    carpeta = tempfile.mkdtemp(prefix="banco-agarres-")
    ruta = os.path.join(carpeta, "pol.shp")
    # dos cuadrados que comparten el lado x=100, y uno aparte
    lay = archivo(ruta, "MultiPolygon", ["POLYGON((0 0,100 0,100 100,0 100,0 0))",
                                         "POLYGON((100 0,200 0,200 100,100 100,100 0))",
                                         "POLYGON((400 0,500 0,500 100,400 100,400 0))"])
    QgsProject.instance().addMapLayer(lay)
    iface.setActiveLayer(lay)
    canvas.setExtent(QgsRectangle(-100, -100, 600, 300))
    canvas.refresh()
    pump(40)
    A, B, C = [f.id() for f in lay.getFeatures()]
    antes = huella(ruta)

    def geom(fid):
        return lay.getFeature(fid).geometry()

    def cuantos(g):
        return g.constGet().nCoordinates()

    def tiene(fid, x, y):
        g = geom(fid)                  # vertices() no sostiene una geometría temporal
        return any(abs(v.x() - x) < 1e-6 and abs(v.y() - y) < 1e-6 for v in g.vertices())

    def cerca(fid, x, y):
        """Con el ratón se cae en un píxel, no en el valor exacto."""
        tol = canvas.mapUnitsPerPixel() * 1.5
        g = geom(fid)
        return any(abs(v.x() - x) <= tol and abs(v.y() - y) <= tol for v in g.vertices())

    def escribir(texto):
        cl.input.setFocus()
        pump(2)
        for ch in texto:
            QTest.keyClicks(cl.input, ch)
        QTest.keyClick(cl.input, Qt.Key.Key_Return)
        pump(10)

    def tiene_y(fid, y):
        g = geom(fid)
        return any(abs(v.y() - y) < 1e-6 and abs(v.x() - 130) < 5 for v in g.vertices())

    def deshacer():
        lay.undoStack().undo()
        pump(10)

    def designar(*fids):
        lay.startEditing()
        canvas.setMapTool(cad)
        lay.selectByIds(list(fids))
        pump(10)

    # ---- Esc en la herramienta de vértices de QGIS
    lay.startEditing()
    iface.actionVertexTool().trigger()
    pump(10)
    canvas.setFocus()
    pump(3)
    check("Vértices está activa", canvas.mapTool().metaObject().className() == "QgsVertexTool")
    lay.selectAll()
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    pump(10)
    check("Vértices, Esc sin arrastre: limpia y vuelve", canvas.mapTool() is cad and not lay.selectedFeatureCount(),
          canvas.mapTool().metaObject().className())
    def arrastrar_vertices(x, y):
        canvas.setFocus()
        pump(60)                       # QGIS arma su índice de la capa aparte
        mover(x - 5, y - 5)
        mover(x, y)
        pump(40)
        clic(x, y)
        pump(30)

    iface.actionVertexTool().trigger()
    pump(10)
    arrastrar_vertices(100, 100)
    mover(120, 130)
    clic(120, 130)
    pump(40)
    check("Vértices: su arrastre anda", cerca(A, 120, 130), geom(A).asWkt(0))
    lay.undoStack().undo()
    pump(20)
    arrastrar_vertices(100, 100)
    mover(120, 130)
    pump(5)
    foco = QApplication.focusWidget()
    lineas.append("    foco arrastrando en Vértices: %s" % (foco.metaObject().className() if foco else None))
    QTest.keyClick(foco or canvas, Qt.Key.Key_Escape)
    pump(10)
    check("Vértices, Esc arrastrando: cancela y vuelve", canvas.mapTool() is cad and tiene(A, 100, 100),
          "%s %s" % (canvas.mapTool().metaObject().className(), geom(A).asWkt(0)))
    iface.actionVertexTool().trigger()
    pump(10)
    arrastrar_vertices(100, 100)
    mover(120, 130)
    clic(120, 130)
    pump(40)
    check("Vértices, después del Esc: sigue andando", cerca(A, 120, 130) and canvas.mapTool() is not cad, geom(A).asWkt(0))
    lay.rollBack()
    pump(10)

    # ---- aparecen y desaparecen
    check("sin selección, sin agarres", not ag.lista and ag.band.numberOfVertices() == 0)
    canvas.setMapTool(cad)
    lay.selectByIds([A])
    pump(10)
    check("sin edición, designado: sin agarres", not lay.isEditable() and not ag.lista and ag.band.numberOfVertices() == 0)
    clic(100, 100)
    check("sin edición, clic en el vértice: no arranca ni abre la edición", mgr.command is None and not lay.isEditable())
    lay.selectByIds([A])
    pump(10)
    lay.startEditing()
    pump(10)
    check("al prender la edición aparecen, sin volver a designar", len(ag.lista) == 8 and ag.band.numberOfVertices() > 0, str(len(ag.lista)))
    lay.rollBack()
    pump(10)
    check("al apagarla desaparecen", not ag.lista and ag.band.numberOfVertices() == 0 and lay.selectedFeatureCount() == 1)
    lay.removeSelection()
    pump(10)
    designar(A)
    vert = [a for a in ag.lista if not a.medio]
    medios = [a for a in ag.lista if a.medio]
    check("cuadrado: 4 vértices y 4 medios", len(vert) == 4 and len(medios) == 4, "%d %d" % (len(vert), len(medios)))
    check("se dibujan", ag.band.numberOfVertices() > 0 and ag.band_medios.numberOfVertices() > 0)
    iface.actionPan().trigger()
    pump(10)
    check("con otra herramienta, sin agarres", not ag.lista and ag.band.numberOfVertices() == 0)
    designar(A)
    lay.removeSelection()
    pump(10)
    check("al deseleccionar, sin agarres", not ag.lista)
    designar(A)

    # ---- mover con clic y cancelar
    clic(100, 100)
    check("clic en el agarre: comando", mgr.command is not None and lay.isEditable(), str(mgr.command))
    check("el teclado va a la línea", QApplication.focusWidget() is cl.input, type(QApplication.focusWidget()).__name__)
    mover(120, 130)
    pump(5)
    check("la vista previa se ve", cad.rb_ghost.numberOfVertices() > 0)
    check("en la vista previa el objeto no cambió", tiene(A, 100, 100))
    QTest.keyClick(cl.input, Qt.Key.Key_Escape)
    pump(10)
    check("Esc cancela sin cambios", mgr.command is None and tiene(A, 100, 100) and not lay.undoStack().count())
    designar(A)
    ultimo = mgr.last_cmd
    clic(100, 100)
    clic(120, 130)
    check("mover con clic: el vértice va ahí", cerca(A, 120, 130) and not tiene(A, 100, 100), geom(A).asWkt(0))
    check("cierra en reposo con el mismo número de vértices", mgr.command is None and cuantos(geom(A)) == 5)
    check("Intro no repite AGARRE", mgr.last_cmd == ultimo, str(mgr.last_cmd))
    pump(5)
    check("los agarres siguen a la selección", any(abs(a.x - 120) < canvas.mapUnitsPerPixel() * 1.5 for a in ag.lista))
    deshacer()
    check("Deshacer lo vuelve", tiene(A, 100, 100) and any(abs(a.x - 100) < 1e-6 for a in ag.lista))

    # ---- lo escrito
    designar(A)
    clic(100, 100)
    escribir("@10,20")
    check("@dx,dy", tiene(A, 110, 120), geom(A).asWkt(0))
    deshacer()
    relativo = mgr.relative
    mgr.set_relative(False)
    designar(A)
    clic(100, 100)
    escribir("@50<0")
    check("@d<ángulo", tiene(A, 150, 100), geom(A).asWkt(0))
    deshacer()
    mgr.set_relative(True)
    designar(A)
    clic(100, 100)
    escribir("@50<180")
    check("ángulos relativos: 180 sigue recto el tramo que llega", tiene(A, 150, 100), geom(A).asWkt(0))
    deshacer()
    mgr.set_relative(relativo)
    designar(A)
    clic(100, 100)
    mover(100, 200)
    escribir("25")
    check("distancia sola, hacia el cursor", cerca(A, 100, 125), geom(A).asWkt(0))
    deshacer()
    designar(A)
    clic(100, 100)
    escribir("300,300")
    check("coordenada absoluta", tiene(A, 300, 300), geom(A).asWkt(0))
    deshacer()

    # ---- ORTO y referencia a objetos
    mgr.set_ortho(True)
    designar(A)
    clic(100, 100)
    clic(130, 110)
    check("ORTO: sólo en X", cerca(A, 130, 100) and tiene_y(A, 100), geom(A).asWkt(0))
    mgr.set_ortho(False)
    deshacer()
    proy = QgsProject.instance()
    cfg = proy.snappingConfig()
    cfg.setEnabled(True)
    cfg.setMode(Qgis_todas())
    cfg.setTypeFlag(tipo_vertice())
    cfg.setTolerance(15)
    cfg.setUnits(QgsTolerance.UnitType.Pixels)
    proy.setSnappingConfig(cfg)
    canvas.snappingUtils().setConfig(cfg)
    pump(20)
    designar(A)
    clic(100, 100)
    mover(402, 2)
    pump(5)
    clic(402, 2)
    check("referencia a objetos: engancha en el vértice ajeno", tiene(A, 400, 0), geom(A).asWkt(1))
    deshacer()
    cfg.setEnabled(False)
    proy.setSnappingConfig(cfg)
    pump(5)

    # ---- marcar varios
    designar(A)
    clic(100, 100, MAYUS)
    clic(0, 100, MAYUS)
    check("Mayús marca dos, en rojo", len(ag.marcas) == 2 and ag.band_marcas.numberOfVertices() > 0 and mgr.command is None)
    clic(0, 100, MAYUS)
    clic(0, 100, MAYUS)
    check("Mayús desmarca y vuelve a marcar", len(ag.marcas) == 2)
    clic(100, 100)
    escribir("@0,50")
    check("mover marcados: los dos", tiene(A, 100, 150) and tiene(A, 0, 150), geom(A).asWkt(0))
    deshacer()
    check("Deshacer vuelve los dos", tiene(A, 100, 100) and tiene(A, 0, 100), geom(A).asWkt(0))
    designar(A)
    clic(100, 100, MAYUS)
    clic(0, 0)
    escribir("@-5,0")
    check("clic en otro agarre: sólo ése", tiene(A, -5, 0) and tiene(A, 100, 100), geom(A).asWkt(0))
    deshacer()

    # ---- agregar
    designar(A)
    clic(50, 0)
    check("agarre del medio: comando", mgr.command is not None)
    escribir("@0,-10")
    check("agrega un vértice en su lugar del anillo", cuantos(geom(A)) == 6 and tiene(A, 50, -10)
          and geom(A).isGeosValid(), geom(A).asWkt(0))
    pump(5)
    check("agrega: ahora 5 vértices", len([a for a in ag.lista if not a.medio]) == 5)
    deshacer()
    # el tramo que cierra el anillo
    designar(A)
    clic(0, 50)
    escribir("@-10,0")
    check("agrega en el tramo que cierra", cuantos(geom(A)) == 6 and tiene(A, -10, 50) and geom(A).isGeosValid(),
          geom(A).asWkt(0))
    deshacer()

    # ---- borrar
    designar(A)
    clic(50, 0)
    clic(50, -10)
    designar(A)
    clic(50, -10, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("Supr borra sólo el vértice marcado", cuantos(geom(A)) == 5 and not tiene(A, 50, -10) and A in {f.id() for f in lay.getFeatures()},
          geom(A).asWkt(0))
    deshacer()
    deshacer()
    designar(A)
    clic(0, 0, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("Supr en el vértice de cierre del anillo", cuantos(geom(A)) == 4 and not tiene(A, 0, 0) and geom(A).isGeosValid(),
          geom(A).asWkt(0))
    pump(5)
    designar(A)
    for x, y in ((100, 0), (100, 100)):
        clic(x, y, MAYUS)
    n0 = cuantos(geom(A))
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("borrar hasta dejar sin forma: se rechaza", cuantos(geom(A)) == n0 and geom(A).isGeosValid(), geom(A).asWkt(0))
    deshacer()
    designar(A)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    pump(5)
    designar(C)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("Supr sin marcados: BORRA el objeto, como antes", C not in {f.id() for f in lay.getFeatures()})
    lay.rollBack()
    pump(10)
    check("rollBack: el archivo sigue igual", huella(ruta) == antes and tiene(C, 400, 0))

    # ---- compartidos
    proy.setTopologicalEditing(False)
    designar(A)
    clic(100, 100)
    escribir("@5,5")
    check("sin topológica: sólo el designado", tiene(A, 105, 105) and tiene(B, 100, 100))
    deshacer()
    proy.setTopologicalEditing(True)
    designar(A)
    clic(100, 100)
    escribir("@5,5")
    check("con topológica: también el vecino", tiene(A, 105, 105) and tiene(B, 105, 105) and not tiene(B, 100, 100),
          geom(B).asWkt(0))
    lay.undoStack().undo()
    pump(10)
    check("deshacer devuelve los dos", tiene(A, 100, 100) and tiene(B, 100, 100))
    designar(A)
    clic(100, 50)
    escribir("@10,0")
    check("con topológica, agregar: también el vecino", cuantos(geom(A)) == 6 and cuantos(geom(B)) == 6
          and tiene(A, 110, 50) and tiene(B, 110, 50) and geom(B).isGeosValid(), geom(B).asWkt(0))
    lay.undoStack().undo()
    pump(10)
    designar(A)
    clic(100, 100, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("con topológica, borrar: también el vecino", not tiene(A, 100, 100) and not tiene(B, 100, 100))
    lay.undoStack().undo()
    pump(10)
    proy.setTopologicalEditing(False)
    # los dos designados, sin topológica: el agarre del lugar común mueve los dos
    designar(A, B)
    check("dos designados: agarres del lugar común, uno solo", len([a for a in ag.lista if not a.medio]) == 6)
    clic(100, 0)
    escribir("@0,-5")
    check("dos designados: mueve los dos", tiene(A, 100, -5) and tiene(B, 100, -5))
    lay.rollBack()
    pump(10)
    check("nada se guardó en el archivo", huella(ruta) == antes)

    # ---- línea abierta y cerrada, y puntos
    rutal = os.path.join(carpeta, "lin.shp")
    lin = archivo(rutal, "LineString", ["LINESTRING(0 200,100 200,200 200)",
                                        "LINESTRING(300 200,400 200,400 280,300 200)"])
    QgsProject.instance().addMapLayer(lin)
    iface.setActiveLayer(lin)
    pump(10)
    L, K = [f.id() for f in lin.getFeatures()]
    canvas.setMapTool(cad)
    lin.startEditing()
    lin.selectByIds([L])
    pump(10)
    check("línea: 3 vértices y 2 medios", len([a for a in ag.lista if not a.medio]) == 3 and len([a for a in ag.lista if a.medio]) == 2)
    clic(0, 200, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("línea: borra un extremo", cuantos(lin.getFeature(L).geometry()) == 2)
    lin.selectByIds([K])
    pump(10)
    clic(300, 200, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    g = lin.getFeature(K).geometry()
    check("línea cerrada: el cierre no se borra", cuantos(g) == 4, g.asWkt(0))
    lin.selectByIds([L])
    pump(10)
    clic(100, 200, MAYUS)
    canvas.setFocus()
    pump(3)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    pump(10)
    check("línea: con dos vértices no se borra", cuantos(lin.getFeature(L).geometry()) == 2)
    lin.rollBack()
    rutap = os.path.join(carpeta, "pun.shp")
    pun = archivo(rutap, "Point", ["POINT(50 -50)"])
    QgsProject.instance().addMapLayer(pun)
    iface.setActiveLayer(pun)
    pump(10)
    canvas.setMapTool(cad)
    pun.startEditing()
    pun.selectAll()
    pump(10)
    check("punto: 1 agarre y sin medios", len(ag.lista) == 1)
    clic(50, -50)
    escribir("@10,0")
    p = next(pun.getFeatures()).geometry().asPoint()
    check("punto: se mueve", abs(p.x() - 60) < 1e-6, str(p))
    pun.rollBack()
    pump(10)
    check("punto: sin edición, sin agarres", not ag.lista)
    pun.removeSelection()
    iface.setActiveLayer(lay)
    pump(10)

    # ---- después de usar los agarres, la herramienta de QGIS sigue andando
    iface.setActiveLayer(lay)
    lay.removeSelection()
    lay.startEditing()
    iface.actionVertexTool().trigger()
    pump(10)
    lineas.append("    capas en edición: %s; topológica %s; referencia %s" % (
        [c.name() for c in QgsProject.instance().mapLayers().values() if c.isEditable()],
        proy.topologicalEditing(), proy.snappingConfig().enabled()))
    arrastrar_vertices(100, 100)
    mover(120, 130)
    clic(120, 130)
    pump(40)
    check("Vértices, después de los agarres: anda", cerca(A, 120, 130), geom(A).asWkt(0))
    lay.rollBack()
    pump(10)

    # ---- apagado, como venía
    from geocad import modulos
    modulos.guardar("qgis", {"agarres": False})
    dib.unload()
    pump(10)
    dib.initGui()
    pump(10)
    canvas.setMapTool(dib.mgr.tool)
    pump(5)
    iface.setActiveLayer(lay)
    lay.selectByIds([A])
    pump(10)
    check("apagado: sin agarres", dib.mgr.agarres is None and dib.agarres is None)
    clic(100, 100)
    check("apagado: clic en el vértice no arranca nada", dib.mgr.command is None and not lay.isEditable())
    check("apagado: AGARRE no es un comando", "AGARRE" not in dib.mgr.specs)
    check("nada se guardó en el archivo, al final", huella(ruta) == antes)


def Qgis_todas():
    return QgsSnappingConfig.SnappingMode.AllLayers


def tipo_vertice():
    from qgis.core import Qgis
    return Qgis.SnappingType.Vertex


try:
    correr()
except Exception:  # noqa: BLE001
    fallas.append("excepción")
    lineas.append(traceback.format_exc())
lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
os._exit(0)
