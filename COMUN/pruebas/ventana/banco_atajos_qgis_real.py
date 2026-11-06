"""Banco con la APLICACIÓN QGIS real (sin pantalla): Ctrl+C, Ctrl+V y Ctrl+Alt+V APRETANDO LAS TECLAS.

3.70.5. Fernando: «si nos manejamos por menú funcionan perfectamente». Los bancos anteriores usaban
trigger(), que es el camino del menú: el Ctrl+C y el Ctrl+V de QGIS son QShortcut del mapa y del panel
de capas y Ctrl+Alt+V lo comparte «Pegar como capa temporal». Acá todo pasa por QTest.keyClick, que
consulta los atajos como una tecla de verdad. No ve Wayland ni el portapapeles del sistema.

Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Hace falta DISPLAY definido, aunque no se use. Deja el resultado en BANCO_SALIDA; termina en «TODO OK».
"""
import os, sys, tempfile, time, traceback
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QMimeData, Qt, QTimer
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QAbstractItemView, QApplication, QDockWidget, QLineEdit
from qgis.utils import iface

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

sys.path.insert(0, os.environ["BANCO_CODIGO"])
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")   # no pisar la copia de Fernando
fallas, lineas = [], []
Key = getattr(Qt, "Key", Qt)
Mod = getattr(Qt, "KeyboardModifier", Qt)
CTRL, ALT = Mod.ControlModifier, Mod.AltModifier
MW = iface.mainWindow()


def check(nombre, ok, detalle=""):
    lineas.append("%s %s %s" % ("ok   " if ok else "FALLA", nombre, detalle if not ok else ""))
    if not ok:
        fallas.append(nombre)


def eventos():
    for _ in range(40):
        QCoreApplication.processEvents()


def cerrar_modales():
    m = QApplication.activeModalWidget()
    if m is not None:
        m.close()


def tecla(w, k, mods):
    w.setFocus()
    eventos()
    QTest.keyClick(QApplication.focusWidget() or w, k, mods)
    eventos()


def capa(nombre):
    lay = QgsVectorLayer("LineString?crs=EPSG:22185&field=nombre:string(20)", nombre, "memory")
    QgsProject.instance().addMapLayer(lay)
    return lay


def de_ingecad():
    """Lo que deja el Ctrl+C de IngeCAD: su DXF (sin texto) y el mensaje aparte."""
    from geocad import pegar_lugar
    objetos = [{"wkt": "LINESTRING (5500000 6100000, 5500100 6100100)", "capa": "Muros", "color": None,
                "aci": None, "tipo_linea": None, "grosor": None}]
    datos = QMimeData()
    datos.setData("application/x-ingecad-clip-id", b"banco:1")
    QApplication.clipboard().setMimeData(datos)
    eventos()
    pegar_lugar.dejar_copia(pegar_lugar.empaquetar("ingecad", "EPSG:22185", objetos, {}),
                            datos, "application/x-ingecad-clip-id")
    eventos()


def suma(lay, fn):
    n = lay.featureCount()
    fn()
    eventos()
    return lay.featureCount() - n


def correr():
    try:
        probar()
    except Exception:  # noqa: BLE001
        fallas.append("excepción")
        lineas.append(traceback.format_exc())
    lineas.append("TODO OK" if not fallas else "FALLAS: %s" % fallas)
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    os._exit(0)


def probar():
    MW.show()
    MW.activateWindow()
    eventos()
    nativa = MW.findChild(QAction, "mActionPasteAsNewMemoryVector")
    check("de fábrica, Ctrl+Alt+V es de QGIS", nativa.shortcut() == QKeySequence("Ctrl+Alt+V"))
    import geocad
    from geocad.pegar_lugar_qgis import PegarLugarQgis, mensaje_en_portapapeles
    guardia = QTimer()
    guardia.timeout.connect(cerrar_modales)     # la ventana de Módulos del primer inicio
    guardia.start(300)
    plugin = geocad.classFactory(iface)         # GeoCAD entero: línea de comandos, cursor, Yaguá Capas
    plugin.initGui()
    espera = time.time() + 3
    while time.time() < espera:
        eventos()
        time.sleep(0.05)
    mod = plugin.pegar_lugar
    check("módulo prendido", mod is not None)
    MW.activateWindow()
    MW.raise_()
    eventos()
    canvas, arbol = iface.mapCanvas(), iface.layerTreeView()
    check("mientras dura el módulo, sin choque", nativa.shortcut().isEmpty())

    a, b = capa("origen"), capa("destino")
    a.startEditing()
    f = QgsFeature(a.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5500000, 6100000), QgsPointXY(5500100, 6100100)]))
    f.setAttributes(["uno"])
    a.addFeature(f)
    a.commitChanges()
    a.selectAll()
    b.startEditing()

    def copiar_con(w):
        QApplication.clipboard().clear()
        eventos()
        iface.setActiveLayer(a)
        tecla(w, Key.Key_C, CTRL)
        iface.setActiveLayer(b)
        return mensaje_en_portapapeles()

    # Ctrl+C por teclado deja la copia para IngeCAD
    for nombre, w in (("mapa", canvas), ("panel de capas", arbol)):
        msg = copiar_con(w)
        check("Ctrl+C en %s: copia para IngeCAD" % nombre, msg is not None and msg.get("origen") == "qgis")
        check("Ctrl+C en %s: sigue el texto de QGIS" % nombre, bool(QApplication.clipboard().text()))
    # Ctrl+V y Ctrl+Alt+V con lo copiado en QGIS (acá la acción de QGIS está habilitada: era el choque)
    copiar_con(canvas)
    check("QGIS: Ctrl+V pega una vez", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL)) == 1)
    copiar_con(canvas)
    check("QGIS: Ctrl+Alt+V pega una vez", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL | ALT)) == 1)
    # lo copiado en IngeCAD
    for nombre, w in (("mapa", canvas), ("panel de capas", arbol)):
        de_ingecad()
        check("IngeCAD: Ctrl+V en %s pega una vez" % nombre, suma(b, lambda: tecla(w, Key.Key_V, CTRL)) == 1)
        de_ingecad()
        check("IngeCAD: Ctrl+Alt+V en %s pega una vez" % nombre,
              suma(b, lambda: tecla(w, Key.Key_V, CTRL | ALT)) == 1)
    # copia vieja de QGIS y después copia de IngeCAD: va la última, una sola vez
    copiar_con(canvas)
    de_ingecad()
    check("copia de QGIS y luego de IngeCAD: una vez", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL)) == 1)
    # sin copia: nada
    QApplication.clipboard().clear()
    eventos()
    check("sin copia: Ctrl+V no pega", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL)) == 0)

    # la línea de comandos (el módulo Teclado le pasa el foco)
    linea = MW.findChild(QLineEdit, "CadCmdInput")
    check("hay línea de comandos", linea is not None)
    if linea is not None:
        dock = MW.findChild(QDockWidget, "DibujoCADCommandLine")
        dock.show()
        eventos()
        msg = copiar_con(linea)
        check("línea vacía: Ctrl+C copia objetos", msg is not None and msg.get("origen") == "qgis")
        check("línea vacía: Ctrl+V pega objetos", suma(b, lambda: tecla(linea, Key.Key_V, CTRL)) == 1)
        check("línea vacía: Ctrl+V no escribe", linea.text() == "", linea.text()[:40])
        de_ingecad()
        check("línea vacía: Ctrl+V de IngeCAD pega", suma(b, lambda: tecla(linea, Key.Key_V, CTRL)) == 1)
        de_ingecad()
        check("línea vacía: Ctrl+Alt+V pega", suma(b, lambda: tecla(linea, Key.Key_V, CTRL | ALT)) == 1)
        QApplication.clipboard().setText("100,200")
        eventos()
        check("texto común: no pega objetos", suma(b, lambda: tecla(linea, Key.Key_V, CTRL)) == 0)
        check("texto común: se escribe en la línea", linea.text() == "100,200", linea.text())
        linea.clear()
        linea.setText("escrito")
        msg = copiar_con(linea)
        check("con algo escrito: Ctrl+C no copia objetos", msg is None)
        linea.clear()

    # Yaguá Capas
    from geocad.capas.plugin import LayerPropertiesPlugin
    capas = LayerPropertiesPlugin(iface)
    capas.initGui()
    eventos()
    capas.toggle_manager(True)
    eventos()
    panel = MW.findChild(QDockWidget, "YaguaCapasDock")
    check("hay Yaguá Capas", panel is not None)
    eventos()
    vistas = panel.findChildren(QAbstractItemView)
    w = vistas[0] if vistas else panel
    msg = copiar_con(w)
    check("Yaguá Capas: Ctrl+C copia objetos", msg is not None and msg.get("origen") == "qgis")
    check("Yaguá Capas: Ctrl+V pega", suma(b, lambda: tecla(w, Key.Key_V, CTRL)) == 1)
    de_ingecad()
    check("Yaguá Capas: Ctrl+V de IngeCAD pega", suma(b, lambda: tecla(w, Key.Key_V, CTRL)) == 1)
    panel.hide()

    # apagado no deja rastro
    mod.unload()
    eventos()
    check("apagado: Ctrl+Alt+V vuelve a QGIS", nativa.shortcut() == QKeySequence("Ctrl+Alt+V"))
    msg = copiar_con(canvas)
    check("apagado: Ctrl+C sin copia para IngeCAD", msg is None)
    de_ingecad()
    check("apagado: Ctrl+V no pega lo de IngeCAD", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL)) == 0)
    # prender de nuevo: no se duplican las conexiones
    mod = PegarLugarQgis(iface)
    de_ingecad()
    check("prendido de nuevo: una vez", suma(b, lambda: tecla(canvas, Key.Key_V, CTRL)) == 1)
    mod.unload()
    guardia.stop()
    b.rollBack()


QTimer.singleShot(3000, correr)
