"""Banco con el QGIS REAL (sin pantalla): la PRIMERA instalación de GeoCAD en
QGIS no cambia la interfaz; lo único nuevo a la vista es la línea de comandos
(3.60.6).

Fernando, 01/11/2026: «la idea de trabajar con la herramienta capas de GeoCAD
debería ser algo opcional, por eso al instalar geocad por primera vez no
deberían modificar la interfaz de qgis ... lo único que debería estar presente
es la barra de línea de comandos». Comprueba, con nada guardado y la ventana
de Módulos aceptada como viene: Papel y Capas sin tildar, ningún panel nuevo
salvo la línea de comandos (ni Yaguá Capas, ni Propiedades), ninguna barra a la
vista (tampoco las pestañas Modelo / Presentaciones); y que prender Capas y
Papel después trae el panel y las pestañas.

Se corre como banco_botones_qgis.py. Termina en «TODO OK».
"""
import os, sys, tempfile, faulthandler
faulthandler.dump_traceback_later(180, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QCheckBox, QDockWidget, QMainWindow, QToolBar

iface = get_iface()
win = QMainWindow()
canvas = QgsMapCanvas(win)
win.setCentralWidget(canvas)
win.show()
iface.mainWindow.return_value = win
iface.mapCanvas.return_value = canvas
iface.cadDockWidget.return_value = QgsAdvancedDigitizingDockWidget(canvas)
iface.addToolBar.side_effect = lambda nombre: win.addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: win.addDockWidget(area, dock)
iface.removeDockWidget.side_effect = lambda dock: win.removeDockWidget(dock)
capas_qgis = QDockWidget("Capas", win)          # el panel Capas de QGIS
capas_qgis.setObjectName("Layers")
from qgis.PyQt.QtCore import Qt as _Qt
win.addDockWidget(_Qt.DockWidgetArea.LeftDockWidgetArea, capas_qgis)
QApplication.processEvents()

fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def eventos():
    for _ in range(5):
        QApplication.processEvents()


def a_la_vista():
    docks = sorted(d.objectName() or d.windowTitle() for d in win.findChildren(QDockWidget)
                   if d.isVisible())
    barras = sorted(b.objectName() or b.windowTitle() for b in win.findChildren(QToolBar)
                    if b.isVisible() and b.parent() is win)
    return docks, barras


antes = a_la_vista()

import qgis.utils
qgis.utils.available_plugins.append("geocad")
import geocad
from geocad import modulos
comprobar(not modulos.elegido("qgis"), "nada guardado: primera instalación")

# la ventana de Módulos de la primera vez: se mira qué viene tildado y se acepta
tildes = {}


def aceptar_modulos():
    dlg = QApplication.activeModalWidget()
    if dlg is None:
        QTimer.singleShot(20, aceptar_modulos)
        return
    for caja in dlg.findChildren(QCheckBox):
        tildes[caja.text()] = caja.isChecked()
    dlg.accept()


QTimer.singleShot(0, aceptar_modulos)
P = geocad.classFactory(iface)
P._bar = lambda *a, **k: None
P.initGui()                               # el primer inicio lo programa initGui, como en QGIS
import time
limite = time.monotonic() + 30
while not modulos.elegido("qgis") and time.monotonic() < limite:
    QApplication.processEvents()
    time.sleep(0.02)
eventos()

capas_txt = [t for t in tildes if t.startswith("Capas CAD")]
comprobar(capas_txt and not tildes[capas_txt[0]], "la ventana de Módulos trae Capas sin tildar")
comprobar(any(t.startswith("Espacio papel") and not v for t, v in tildes.items()),
          "y Espacio papel sin tildar")
comprobar(any(t.startswith("Dibujo CAD") and v for t, v in tildes.items()),
          "y Dibujo CAD tildado (la línea de comandos)")
comprobar(modulos.elegido("qgis") and not modulos.activo("qgis", "capas")
          and not modulos.activo("qgis", "papel"), "aceptada como viene: Papel y Capas apagados")
docks, barras = a_la_vista()
nuevos_docks = [d for d in docks if d not in antes[0]]
nuevas_barras = [b for b in barras if b not in antes[1]]
print("     paneles nuevos a la vista:", nuevos_docks, "· barras nuevas a la vista:", nuevas_barras)
comprobar(len(nuevos_docks) == 1 and isinstance(P.subs.activos["dibujo"][0].cmdline, QDockWidget)
          and P.subs.activos["dibujo"][0].cmdline.isVisible(),
          "un solo panel nuevo a la vista: la línea de comandos")
comprobar(not win.findChildren(QDockWidget, "YaguaCapasDock"), "sin panel Yaguá Capas")
comprobar(not nuevas_barras, "ninguna barra nueva a la vista")

# son opcionales: prenderlos en Módulos... los trae, con su panel y sus pestañas
modulos.guardar("qgis", {"capas": True, "papel": True})
P.aplicar_modulos()
eventos()
panel = win.findChildren(QDockWidget, "YaguaCapasDock")
comprobar(panel and panel[0].isVisible(), "prendido Capas en Módulos...: aparece el panel Yaguá Capas")
pestanas = win.findChildren(QToolBar, "PresentacionesCADToolbar")
comprobar(pestanas and pestanas[0].isVisible(),
          "prendido Papel: aparecen las pestañas Modelo / Presentaciones")

if getattr(P, "timer", None) is not None:
    P.timer.stop()
    P.timer = None
P.unload()
eventos()
if fallas:
    print("FALLAS:", *fallas, sep="\n  ")
    sys.exit(1)
print("TODO OK")
