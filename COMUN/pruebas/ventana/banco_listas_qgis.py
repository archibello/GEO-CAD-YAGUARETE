"""Banco con el QGIS REAL (sin pantalla): las listas de Texto CAD (fuente,
altura, color) y de Capas CAD (capa actual) en Administrar botones (3.46.0).

Fernando, 24/10/2026: «Puedes hacer que aparezcan en el administrador de
botones así las puedo editar y distribuir entre las YAGUÁ que ya tenemos?»
Comprueba que las cuatro listas van a «Yaguá Texto» y «Yaguá Capas» y se
ven ahí, que siguen andando, que Texto CAD y Capas CAD quedan vacías y
escondidas, que la ventana las muestra con su nombre, que se pueden pasar a
otra categoría y que al descargar todo vuelve a su barra.

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


from qgis.PyQt.QtCore import QCoreApplication, QEvent


def barras():
    """Las barras de la ventana, sin las que ya se están borrando (deleteLater):
    una barra vieja puede tener el mismo nombre que la nueva."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value
                                      if hasattr(QEvent.Type.DeferredDelete, "value") else QEvent.Type.DeferredDelete)
    gc.collect()
    return {x.objectName(): x for x in ventana().findChildren(QToolBar)}


P = geocad.classFactory(iface)
avisos = []
P._bar = lambda texto, *a, **k: avisos.append(texto)
ventana().resize(6000, 1000)              # que entren todas las barras (si no, Qt esconde lo que sobra)
P.initGui()
P._primer_inicio()
QApplication.processEvents()
# 3.47.0: de fábrica las barras arrancan apagadas; acá, todas prendidas (como Fernando)
from geocad import botones_barras
P._restaurar_botones()
_fab = [(n, [x for x, _a in f]) for n, f in botones_barras.elementos(P._fabricas(), P._id_boton)]
botones.guardar("qgis", botones.distribuir(_fab, None, "qgis"), _fab)
P._aplicar_botones()
QApplication.processEvents()
# 3.47.0: la capa CAD actual, en Yaguá Dibujo (el último estado de Fernando)
LISTAS = {"dibujo:font": "Yaguá Texto", "dibujo:size": "Yaguá Texto", "dibujo:textcolor": "Yaguá Texto",
          "capas:capa": "Yaguá Dibujo"}


def accion(bar, clave):
    return next((a for a in bar.actions() if P._id_boton(a) == clave), None)


def se_ve(bar, clave):
    """La lista misma (no un botón vacío en su lugar) está en la barra y a la vista."""
    QApplication.processEvents()
    a = accion(bar, clave)
    w = bar.widgetForAction(a) if a is not None else None
    return w is not None and w is a.defaultWidget() and w.isVisible()


b = barras()
for clave, cat in LISTAS.items():
    comprobar(se_ve(b[botones.objeto_barra(cat)], clave), "%s está y se ve en «%s»" % (clave, cat))
for fab in ("TextoCADToolbar", "CadLayersToolbar"):
    comprobar(not b[fab].actions() and not b[fab].isVisible(), "%s vacía y escondida" % fab)

# siguen andando desde su barra nueva
dib = qgis.utils.plugins["Dibujo_CAD"]
dib.size_combo.setEditText("4.25")
dib.size_combo.lineEdit().editingFinished.emit()
comprobar(abs(dib.mgr.text_style.height - 4.25) < 1e-9, "la altura del texto se cambia desde Yaguá Texto")
dib._set_text_color("#ff0000")
comprobar(dib.mgr.text_style.color == "#ff0000" and dib.text_color_btn.text() == "#ff0000" or
          dib.mgr.text_style.color == "#ff0000", "el color del texto, también")

# la ventana Administrar botones las muestra con su nombre
vistos = {}


def mirar(QtW, parent, prog, fabrica, etiquetas, *a, **k):
    vistos["fabrica"], vistos["etiquetas"] = fabrica, etiquetas
    return False


botones_ui.administrar = mirar
P.administrar_botones()
QApplication.processEvents()
todos = {x for _n, f in vistos["fabrica"] for x in f}
comprobar(set(LISTAS) <= todos, "la ventana muestra las cuatro listas")
comprobar(vistos["etiquetas"].get("dibujo:font") == "Fuente del texto" and
          vistos["etiquetas"].get("capas:capa") == "Capa CAD actual", "con su nombre")
b = barras()
comprobar(all(accion(b[botones.objeto_barra(c)], k) is not None for k, c in LISTAS.items()),
          "después de la ventana siguen en sus categorías")

# distribuirlas: la fuente y la capa pasan a «Yaguá Setting»
cats = [[n, list(x)] for n, x in botones.DEFECTO["qgis"]]
for c in cats:
    c[1] = [x for x in c[1] if x not in ("dibujo:font", "capas:capa")]
    if c[0] == "Yaguá Setting":
        c[1] += ["dibujo:font", "capas:capa"]
from geocad import botones_barras
P._restaurar_botones()                      # la fábrica, como hace la ventana antes de guardar
fabrica = [(n, [x for x, _a in fila]) for n, fila in botones_barras.elementos(P._fabricas(), P._id_boton)]
botones.guardar("qgis", [(n, [(x, True) for x in fila]) for n, fila in cats], fabrica)
P._aplicar_botones()
QApplication.processEvents()
b = barras()
s = b[botones.objeto_barra("Yaguá Setting")]
comprobar(all(se_ve(s, k) for k in ("dibujo:font", "capas:capa")), "pasadas a Yaguá Setting, se ven ahí")
comprobar(accion(b[botones.objeto_barra("Yaguá Texto")], "dibujo:font") is None, "y ya no en Yaguá Texto")
comprobar(not b["CadLayersToolbar"].isVisible(), "Capas CAD sigue escondida")

# descargar: cada lista vuelve a su barra, sin errores
errores = []
sys.excepthook = lambda t, v, tb: errores.append("%s: %s" % (t.__name__, v))
P._restaurar_botones()
b = barras()
comprobar(all(se_ve(b[fab], k) for fab, k in (("TextoCADToolbar", "dibujo:font"),
                                              ("TextoCADToolbar", "dibujo:size"),
                                              ("TextoCADToolbar", "dibujo:textcolor"),
                                              ("CadLayersToolbar", "capas:capa"))),
          "como de fábrica: cada lista en su barra de siempre, a la vista")
P.timer = None
P.unload()
QApplication.processEvents()
comprobar(not errores and not avisos, "sin errores al descargar %s %s" % (errores, avisos))
if fallas:
    print("FALLAS:", *fallas, sep="\n  ")
    sys.exit(1)
print("TODO OK")
