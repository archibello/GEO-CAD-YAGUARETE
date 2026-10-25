"""Banco con el QGIS REAL (sin pantalla): Administrar botones en QGIS (3.39.1).

Fernando, 24/10/2026: en QGIS la ventana mostraba las categorías vacías
(0/0) y los botones de Dibujo y Capas no estaban en ninguna barra. Causa:
al arrancar QGIS las categorías se aplican dos veces seguidas y la segunda
contaba los botones con las barras de fábrica ya vacías. Este banco arranca
GeoCAD entero (módulos, submódulos, barras) y comprueba que las categorías
«Yaguá» queden con sus botones después de aplicar varias veces, que la
ventana vea todos los botones y que al descargar vuelva todo.

Se corre con el Python de QGIS (Flatpak org.qgis.qgis), con el complemento
GeoCAD copiado a una carpeta de prueba (nunca la carpeta real de QGIS):
    flatpak run --filesystem=<carpeta> --command=sh org.qgis.qgis -c \\
      'PYTHONPATH=/app/share/qgis/python:<carpeta con geocad> QT_QPA_PLATFORM=offscreen \\
       python3 banco_botones_qgis.py'
Termina en «TODO OK».
"""
import os, sys, tempfile, faulthandler
faulthandler.dump_traceback_later(180, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.PyQt.QtWidgets import QApplication, QMainWindow, QToolBar

# La ventana principal es de C++, como QgisApp: cada iface.mainWindow() da un
# envoltorio de Python nuevo si nadie guarda el anterior (Fernando, 24/10/2026,
# 3.41.0: lo que GeoCAD colgaba de la ventana se perdía y Administrar botones
# decía «No hay barras de GeoCAD»). El banco no guarda la ventana.
import gc
from qgis.PyQt import sip
iface = get_iface()
_mw = QMainWindow()
canvas = QgsMapCanvas(_mw)
_mw.setCentralWidget(canvas)
_mw.show()
sip.transferto(_mw, None)
_PTR = sip.unwrapinstance(_mw)
del _mw
gc.collect()


def ventana():
    return sip.wrapinstance(_PTR, QMainWindow)


iface.mainWindow.side_effect = ventana
iface.mapCanvas.return_value = canvas
iface.cadDockWidget.return_value = QgsAdvancedDigitizingDockWidget(canvas)
iface.addToolBar.side_effect = lambda nombre: ventana().addToolBar(nombre)
iface.addDockWidget.side_effect = lambda area, dock: ventana().addDockWidget(area, dock)
QApplication.processEvents()

# como QGIS: su gancho de import anota los módulos de cada complemento, y
# reloadPlugin saca sólo ésos (los cargados con importlib no los ve)
import builtins
import qgis.utils
qgis.utils.available_plugins.append("geocad")
builtins.__import__ = qgis.utils._import
import geocad
from geocad import botones, botones_ui, config, modulos
modulos.guardar("qgis", {m.clave: True for m in modulos.CATALOGO["qgis"]})
config.save({"mostrar_botones": True}, "QGIS")
fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def ids(bar):
    return [P._id_boton(a) for a in bar.actions() if P._id_boton(a)]


def barras():
    gc.collect()                          # ningún envoltorio viejo de la ventana vivo
    return {b.objectName(): b for b in ventana().findChildren(QToolBar)}


P = geocad.classFactory(iface)
avisos = []
P._bar = lambda texto, *a, **k: avisos.append(texto)
P.initGui()
P._primer_inicio()                        # carga Dibujo y Capas: aplica las categorías
for _ in range(3):                        # y otra vez, como al cambiar módulos o el puente
    P._aplicar_botones()
QApplication.processEvents()
b = barras()
cats = {n: x for n, x in b.items() if n.startswith("GeoCADCategoria_")}
esperadas = [botones.objeto_barra(n) for n, _i in botones.DEFECTO["qgis"]]
comprobar(sorted(cats) == sorted(esperadas), f"las {len(esperadas)} categorías «Yaguá», sin repetir")
total = sum(len(ids(x)) for x in cats.values())
n_edicion = len(dict(botones.DEFECTO["qgis"])["Yaguá Edición"])     # 18 desde 3.42.0 (PERPENDICULAR)
comprobar(len(ids(cats[botones.objeto_barra("Yaguá Edición")])) == n_edicion,
          "Yaguá Edición con sus %d botones" % n_edicion)
comprobar(ids(cats[botones.objeto_barra("Yagureté-IngeCAD")]) == ["puente:send", "dibujo:cmdline"],
          "Yagureté-IngeCAD con Enviar y la línea de comandos")
comprobar(all(not ids(b[n]) for n in ("DibujoCADToolbar", "EdicionCADToolbar", "CadLayersToolbar")),
          "las barras de siempre sin botones (están en las categorías)")
comprobar(not avisos, "sin avisos de error " + str(avisos))

vistos = {}
def mirar(QtW, parent, prog, fabrica, etiquetas, *a, **k):
    vistos["fabrica"] = fabrica
    vistos["modelo"] = botones.distribuir(fabrica, botones.leer(prog), prog)
    return False
botones_ui.administrar = mirar
P.administrar_botones()
QApplication.processEvents()
fab_total = sum(len(f) for _n, f in vistos["fabrica"])
comprobar(fab_total == total and fab_total > 50, f"la ventana ve los {fab_total} botones")
llenas = [n for n, f in vistos["modelo"] if f]
comprobar(len(llenas) == len(esperadas), "en la ventana ninguna categoría vacía (0/0)")
b = barras()
comprobar(sum(len(ids(x)) for n, x in b.items() if n.startswith("GeoCADCategoria_")) == total,
          "después de la ventana, los botones siguen en sus barras")

# ---- cambiar los módulos: Dibujo y Capas se descargan y vuelven a cargar sin
# que QGIS vuelva a su bucle (sus barras viejas siguen ahí hasta deleteLater)
P.aplicar_modulos()
b = barras()
cats = {n: x for n, x in b.items() if n.startswith("GeoCADCategoria_")}
comprobar(sorted(cats) == sorted(esperadas) and sum(len(ids(x)) for x in cats.values()) == total,
          "al cambiar los módulos, las categorías con sus botones (sin procesar eventos)")
QApplication.processEvents()

# ---- actualizar en caliente (GeoCAD > Actualizar: qgis.utils.reloadPlugin):
# unload, módulos nuevos, classFactory e initGui en la misma vuelta (Fernando,
# 24/10/2026: con la 3.40.0 recién instalada, todas las categorías 0/0)
viejo_dibujo = sys.modules["geocad.dibujo.plugin"]
P.timer = None
P.unload()
qgis.utils._unloadPluginModules("geocad")          # lo que hace reloadPlugin
import geocad
from geocad import botones, botones_ui
P = geocad.classFactory(iface)
P._bar = lambda texto, *a, **k: avisos.append(texto)
P.initGui()
P._primer_inicio()
comprobar(sys.modules["geocad.dibujo.plugin"] is not viejo_dibujo,
          "tras actualizar en caliente, Dibujo con el código nuevo (no el de la memoria)")
b = barras()
cats = {n: x for n, x in b.items() if n.startswith("GeoCADCategoria_")}
comprobar(sorted(cats) == sorted(esperadas) and sum(len(ids(x)) for x in cats.values()) == total,
          "tras actualizar en caliente, las categorías con sus botones")
vistos.clear()
botones_ui.administrar = mirar
P.administrar_botones()
comprobar(sum(len(f) for _n, f in vistos.get("fabrica", [])) == total,
          "tras actualizar en caliente, la ventana ve todos los botones (no 0/0)")
QApplication.processEvents()
b = barras()
comprobar(sum(len(ids(x)) for n, x in b.items() if n.startswith("GeoCADCategoria_")) == total,
          "y siguen en sus barras después de procesar los eventos")

P.timer = None
P.unload()
QApplication.processEvents()
comprobar(not [n for n in barras() if n.startswith("GeoCADCategoria_")], "al descargar, sin barras de categorías")
if fallas:
    print("FALLAS:", *fallas, sep="\n  ")
    sys.exit(1)
print("TODO OK")
