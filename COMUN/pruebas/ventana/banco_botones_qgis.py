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
# el menú Edición y sus acciones, de verdad: «Pegar en el lugar» (3.66.0) se cuelga de ellos
from qgis.PyQt.QtWidgets import QAction, QMenu
_editar = QMenu("Edición", ventana())
_copiar, _pegar = QAction("Copiar objetos espaciales", ventana()), QAction("Pegar objetos espaciales", ventana())
_editar.addAction(_copiar)
_editar.addAction(_pegar)
iface.editMenu.return_value = _editar
iface.actionCopyFeatures.return_value = _copiar
iface.actionPasteFeatures.return_value = _pegar
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
# 3.47.0, primera instalación (nada guardado): todas las barras apagadas; sólo
# la línea de comandos a la vista (Fernando, 25/10/2026)
from qgis.PyQt.QtWidgets import QDockWidget
from geocad import botones_barras
b = barras()
comprobar(not any(ids(x) for n, x in b.items() if n.startswith("GeoCADCategoria_")),
          "primera instalación: ninguna barra de categorías con botones")
comprobar(all(b[n].isHidden() for n in ("DibujoCADToolbar", "EdicionCADToolbar", "CadLayersToolbar")),
          "primera instalación: las barras de siempre escondidas")
docks = {d.objectName(): d for d in ventana().findChildren(QDockWidget)}
comprobar("DibujoCADCommandLine" in docks and not docks["DibujoCADCommandLine"].isHidden(),
          "primera instalación: la línea de comandos a la vista")
# el resto del banco, con todas las barras prendidas (como las tiene Fernando)
P._restaurar_botones()
fab = [(n, [x for x, _a in f]) for n, f in botones_barras.elementos(P._fabricas(), P._id_boton)]
botones.guardar("qgis", botones.distribuir(fab, None, "qgis"), fab)
for _ in range(2):
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
comprobar(ids(cats[botones.objeto_barra("Yaguá-IngeCAD")]) == ["puente:send"],
          "Yaguá-IngeCAD con Enviar")
comprobar(ids(cats[botones.objeto_barra("Yaguá Setting")])[-1] == "dibujo:cmdline",
          "la línea de comandos en Yaguá Setting")
comprobar(all(not ids(b[n]) for n in ("DibujoCADToolbar", "EdicionCADToolbar", "CadLayersToolbar")),
          "las barras de siempre sin botones (están en las categorías)")
comprobar(not avisos, "sin avisos de error " + str(avisos))

vistos = {}
real_administrar = botones_ui.administrar
def mirar(QtW, parent, prog, fabrica, etiquetas, *a, **k):
    vistos["fabrica"] = fabrica
    vistos["modelo"] = botones.distribuir(fabrica, botones.leer(prog), prog)
    return False
botones_ui.administrar = mirar
P.administrar_botones()
QApplication.processEvents()
fab_total = sum(len(f) for n, f in vistos["fabrica"] if not botones.es_banco(n))
comprobar(fab_total == total and fab_total > 50, f"la ventana ve los {fab_total} botones")
# 3.65.0: tres bancos por tema (antes, 3.60.7, Dibujo CAD y Capas CAD), con todo lo de GeoCAD
bancos = {n: f for n, f in vistos["fabrica"] if botones.es_banco(n)}
comprobar([n for n, _f in vistos["fabrica"] if botones.es_banco(n)] == ["banco:" + t for t in botones.BANCOS],
          "los tres bancos: " + str(list(bancos)))
en_bancos = [b for f in bancos.values() for b in f]
comprobar(len(en_bancos) == len(set(en_bancos)), "cada botón en un solo banco")
comprobar("capas:layiso" in bancos.get("banco:Configuración", ()) and "dibujo:line" in bancos.get("banco:Dibujo", ())
          and "dibujo:fillet" in bancos.get("banco:Edición", ()) and "geocad:pegarorig" in bancos.get("banco:Edición", ()) and "geocad:modules" in bancos.get("banco:Configuración", ()),
          "LAYISO y Módulos en Configuración, EMPALME en Edición, LÍNEA en Dibujo")
comprobar(all(b in en_bancos for n, f in vistos["fabrica"] if not botones.es_banco(n) for b in f),
          "todos los botones de las barras están en algún banco")
# 3.61.0: ZOOM, ENCUADRE, REGEN e IGUALARPROP sólo en un banco, sin categoría
nuevos = ["dibujo:" + i for i in ("zoom", "zoomwin", "zoomext", "zoomprev", "zoomobj", "pan", "regen", "matchprop")]
comprobar(all(x in en_bancos for x in nuevos)
          and not any(x in f for n, f in vistos["modelo"] for x in nuevos),
          "ZOOM, ENCUADRE, REGEN e IGUALARPROP en los bancos, en ninguna categoría")
comprobar(not [a for a in P.menu.actions() if a.menu() is not None and a.text() in ("Dibujo CAD", "Capas CAD")],
          "el menú GeoCAD sin los submenús Dibujo CAD y Capas CAD")
# la ventana real: el banco elegido muestra sus botones y «Pasar» trae uno
from qgis.PyQt.QtWidgets import QListWidget, QComboBox, QPushButton
vista = {}
def mirar_dialogo(dlg):
    listas = dlg.findChildren(QListWidget)
    lb = [l for l in listas if l.count() == 3 and l.item(0).text() == "Configuración"]
    vista["bancos"] = bool(lb) and [lb[0].item(i).text() for i in range(3)] == list(botones.BANCOS) \
        and lb[0].isVisibleTo(dlg)
    if lb:
        lb[0].setCurrentRow(0)
        der = [l for l in listas if l is not lb[0]][1]
        textos = [der.item(i).text() for i in range(der.count())]
        vista["sin_barra"] = any("LAYISO" in t and "(sin barra)" in t for t in textos)
        k = next(i for i, t in enumerate(textos) if "LAYISO" in t)
        der.setCurrentRow(k)
        dlg.findChild(QComboBox).setCurrentIndex(0)
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Pasar").click()
        textos = [der.item(i).text() for i in range(der.count())]
        vista["traido"] = any("LAYISO" in t and "(en Yaguá Dibujo)" in t for t in textos)
    return False
botones_ui._exec = mirar_dialogo
botones_ui.administrar = real_administrar
P.administrar_botones()
comprobar(vista.get("bancos"), "la ventana muestra los tres bancos debajo de las categorías")
comprobar(vista.get("sin_barra") and vista.get("traido"),
          "LAYISO del banco: «sin barra» y con «Pasar» queda en Yaguá Dibujo " + str(vista))
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
P.timer.stop()                         # el reloj se para (sin esto seguía latiendo, 3.60.5)
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
comprobar(sum(len(f) for n, f in vistos.get("fabrica", []) if not botones.es_banco(n)) == total,
          "tras actualizar en caliente, la ventana ve todos los botones (no 0/0)")
QApplication.processEvents()
b = barras()
comprobar(sum(len(ids(x)) for n, x in b.items() if n.startswith("GeoCADCategoria_")) == total,
          "y siguen en sus barras después de procesar los eventos")

P.timer.stop()                         # el reloj se para (sin esto seguía latiendo, 3.60.5)
P.timer = None
P.unload()
QApplication.processEvents()
comprobar(not [n for n in barras() if n.startswith("GeoCADCategoria_")], "al descargar, sin barras de categorías")
if fallas:
    print("FALLAS:", *fallas, sep="\n  ")
    sys.exit(1)
print("TODO OK")
