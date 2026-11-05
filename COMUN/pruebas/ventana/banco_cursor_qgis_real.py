# -*- coding: utf-8 -*-
"""El cursor de GeoCAD por defecto (módulo «Cursor de GeoCAD», 3.67), con QGIS real.

Mide con la aplicación de verdad: qué herramienta queda al abrir QGIS, al abrir o crear un
proyecto y cuando el mapa se queda sin herramienta; que la elegida a propósito se respeta;
Esc en el mapa, en el panel de capas y en la línea de comandos con cada herramienta; lo que
Esc no debe tocar; arrastrar en el mapa con el cursor; y el módulo apagado.

Sin pantalla, en un perfil aparte, con GeoCAD instalado en ese perfil para medir el arranque
de verdad (ver el encabezado de banco_enviar_copias_qgis_real.py). En <hogar> tiene que estar
ya guardada la elección de módulos (si no, abre el diálogo de la primera vez):

    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen
        --env=HOME=<hogar> --env=BANCO_SALIDA=<carpeta>/f.txt
        org.qgis.qgis --nologo --noversioncheck --profiles-path <perfil>
        --code banco_cursor_qgis_real.py
"""
import os, tempfile, time, traceback
from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.utils import iface, plugins
from qgis.PyQt.QtCore import QEvent, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QApplication, QDialog, QLineEdit
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


def capa(nombre):
    lay = QgsVectorLayer("LineString?crs=EPSG:32721&field=z:integer", nombre, "memory")
    feats = []
    for i in range(3):
        f = QgsFeature(lay.fields())
        f.setGeometry(QgsGeometry.fromWkt("LINESTRING(%d 0,%d 100)" % (i * 40, i * 40)))
        feats.append(f)
    lay.dataProvider().addFeatures(feats)
    lay.updateExtents()
    QgsProject.instance().addMapLayer(lay)
    return lay


def correr():
    mw.show()
    pump(40)
    plug = plugins["geocad"]
    dib = plug.subs.activos["dibujo"][0]
    mgr, cl, cad = dib.mgr, dib.cmdline, dib.mgr.tool
    tree = iface.layerTreeView()

    def es_cad():
        return canvas.mapTool() is cad

    def nombre():
        return type(canvas.mapTool()).__name__

    check("al abrir QGIS queda el cursor", es_cad(), nombre())

    # ---- proyecto
    iface.newProject(False)
    pump(40)
    check("proyecto nuevo: el cursor", es_cad(), nombre())
    iface.actionIdentify().trigger()
    pump()
    iface.newProject(False)
    pump(40)
    check("proyecto nuevo desde Identificar: el cursor", es_cad(), nombre())
    capa("A")
    ruta = os.path.join(tempfile.mkdtemp(prefix="banco-cursor-"), "p.qgz")
    QgsProject.instance().write(ruta)
    iface.actionIdentify().trigger()
    pump()
    iface.addProject(ruta)
    pump(40)
    check("abrir proyecto desde Identificar: el cursor", es_cad(), nombre())

    a, b = capa("A2"), capa("B2")      # las de memoria vuelven vacías de abrir el proyecto
    iface.setActiveLayer(a)
    canvas.setExtent(QgsRectangle(-100, -100, 200, 200))
    canvas.refresh()
    pump()

    def apretar(destino, mods=Qt.KeyboardModifier.NoModifier):
        mw.activateWindow()
        destino.setFocus()
        pump(5)
        foco = QApplication.focusWidget()
        QTest.keyClick(foco or destino, Qt.Key.Key_Escape, mods)
        pump(5)
        return foco

    def seleccionar():
        a.selectAll()
        b.selectAll()
        assert a.selectedFeatureCount() == 3 and b.selectedFeatureCount() == 3

    def limpias():
        return a.selectedFeatureCount() == 0 and b.selectedFeatureCount() == 0

    # ---- la elegida a propósito se respeta hasta Esc
    acciones = (("Desplazar", iface.actionPan()), ("Acercar", iface.actionZoomIn()),
                ("Identificar", iface.actionIdentify()), ("Seleccionar", iface.actionSelect()),
                ("Seleccionar por polígono", iface.actionSelectPolygon()))
    for titulo, accion in acciones:
        for lugar, destino in (("mapa", canvas), ("panel de capas", tree), ("línea de comandos", cl.input)):
            accion.trigger()
            pump(5)
            elegida = canvas.mapTool()
            iface.setActiveLayer(b)
            iface.setActiveLayer(a)
            pump(5)
            check("%s se respeta" % titulo, canvas.mapTool() is elegida and elegida is not cad)
            seleccionar()
            foco = apretar(destino)
            check("%s, Esc en %s: limpia todas y vuelve" % (titulo, lugar), limpias() and es_cad(),
                  "%s foco=%s A=%d B=%d" % (nombre(), type(foco).__name__,
                                           a.selectedFeatureCount(), b.selectedFeatureCount()))

    # ---- con el cursor
    for lugar, destino in (("mapa", canvas), ("panel de capas", tree), ("línea de comandos", cl.input)):
        canvas.setFocus()
        seleccionar()
        apretar(destino)
        check("cursor, Esc en %s: limpia todas" % lugar, limpias() and es_cad(),
              "A=%d B=%d" % (a.selectedFeatureCount(), b.selectedFeatureCount()))
    seleccionar()
    apretar(tree, Qt.KeyboardModifier.ControlModifier)
    check("Ctrl+Esc en el panel no es de GeoCAD", a.selectedFeatureCount() == 3 and b.selectedFeatureCount() == 3)
    a.removeSelection()
    b.removeSelection()

    # ---- con un comando en marcha, Esc cancela el comando y no la selección
    mgr.run("LINEA")
    pump()
    seleccionar()
    apretar(tree)
    check("LINEA, Esc en el panel: cancela el comando y conserva la selección",
          mgr.command is None and a.selectedFeatureCount() == 3 and b.selectedFeatureCount() == 3,
          str(mgr.command))
    a.rollBack()

    # ---- lo que Esc no toca
    seleccionar()
    campo = QLineEdit(mw)
    campo.show()
    apretar(campo)
    check("Esc en un campo de texto no deselecciona", a.selectedFeatureCount() == 3)
    campo.deleteLater()
    dialogo = QDialog(mw)
    dialogo.show()
    pump()
    dialogo.activateWindow()
    dialogo.setFocus()
    pump(5)
    if QApplication.focusWidget() is not None:
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Escape)
    pump(5)
    check("Esc en un diálogo no deselecciona", a.selectedFeatureCount() == 3)
    dialogo.close()
    dialogo.deleteLater()
    pump()
    iface.setActiveLayer(a)
    a.startEditing()
    iface.actionAddFeature().trigger()
    pump()
    agregar = canvas.mapTool()
    check("Agregar entidad se puede elegir", agregar is not cad, nombre())
    apretar(canvas)
    check("Agregar entidad, Esc en el mapa: conserva herramienta y selección",
          canvas.mapTool() is agregar and a.selectedFeatureCount() == 3)
    apretar(tree)
    check("Agregar entidad, Esc en el panel: deselecciona y conserva la herramienta",
          canvas.mapTool() is agregar and limpias())
    a.rollBack()
    pump()
    check("al salir de edición con Agregar entidad: el cursor", es_cad(), nombre())

    # ---- sin herramienta
    iface.actionPan().trigger()
    pump()
    canvas.unsetMapTool(canvas.mapTool())
    pump(10)
    check("el mapa sin herramienta: el cursor", es_cad(), nombre())

    # ---- arrastrar con el cursor
    def centro():
        c = canvas.center()
        return c.x(), c.y()

    def arrastrar(boton):
        vp = canvas.viewport()
        desde, hasta = QPointF(100, 100), QPointF(180, 150)
        nada = Qt.KeyboardModifier.NoModifier
        for tipo, donde, cual, apretados in (
                (QEvent.Type.MouseButtonPress, desde, boton, boton),
                (QEvent.Type.MouseMove, hasta, Qt.MouseButton.NoButton, boton),
                (QEvent.Type.MouseButtonRelease, hasta, boton, Qt.MouseButton.NoButton)):
            QApplication.sendEvent(vp, QMouseEvent(tipo, donde, QPointF(vp.mapToGlobal(donde.toPoint())),
                                                   cual, apretados, nada))
            pump(5)
        pump(20)

    canvas.setFocus()
    antes = centro()
    arrastrar(Qt.MouseButton.MiddleButton)           # primero: un segundo arrastre seguido no cuenta sin pantalla
    check("cursor, el botón del medio mueve el mapa", centro() != antes, "%s %s" % (antes, centro()))
    antes = centro()
    arrastrar(Qt.MouseButton.LeftButton)
    check("cursor, arrastrar con el izquierdo no mueve el mapa", centro() == antes, "%s %s" % (antes, centro()))
    mgr.idle_win = None

    # ---- apagado, como venía
    from geocad import modulos
    modulos.guardar("qgis", {"cursor_geocad": False})
    dib.unload()
    pump(10)
    check("al apagar queda Desplazar", type(canvas.mapTool()).__name__ == "QgsMapToolPan", nombre())
    dib.initGui()
    pump(10)
    mgr, cl = dib.mgr, dib.cmdline
    check("apagado: no se activa solo", type(canvas.mapTool()).__name__ == "QgsMapToolPan", nombre())
    iface.setActiveLayer(a)
    seleccionar()
    apretar(canvas)
    check("apagado, Esc con Desplazar en el mapa no deselecciona", a.selectedFeatureCount() == 3)
    apretar(tree)
    check("apagado, Esc en el panel no deselecciona", a.selectedFeatureCount() == 3)
    apretar(cl.input)
    check("apagado, Esc en la línea: sólo la capa activa, como antes",
          a.selectedFeatureCount() == 0 and b.selectedFeatureCount() == 3)
    iface.newProject(False)
    pump(40)
    check("apagado, proyecto nuevo: Desplazar", type(canvas.mapTool()).__name__ == "QgsMapToolPan", nombre())


try:
    correr()
except Exception:  # noqa: BLE001
    fallas.append("excepción")
    lineas.append(traceback.format_exc())
lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
    fh.write("\n".join(lineas) + "\n")
os._exit(0)
