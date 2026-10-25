"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
Administrar botones (3.38.0; 3.47.0: barras apagadas, mirar no cambia nada).

Comprueba con las barras de verdad (PySide6) lo que test_botones.py ve con
barras simuladas: de fábrica nada cambia; con categorías guardadas cada una
es una barra con sus botones (en su orden, sin los ocultos, y el botón
sigue llamando a su orden); la barra GeoCAD y Yaguareté Tools vacías se
esconden; al sacar GeoCAD (o volver a «Como de fábrica») todo queda como
estaba; la ventana Administrar botones (Nueva, Pasar, destildar, Una por
tema, Aceptar) guarda y arma las barras.

Uso (necesita PySide6, ezdxf, numpy, Pillow):
    python banco_botones_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, types, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar, QListWidget, QPushButton

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {m.clave: True for m in mods.CATALOGO["ingecad"]})
pkg = import_module("ingecad_plugin_geocad")
BT = import_module("ingecad_plugin_geocad.botones")
BU = import_module("ingecad_plugin_geocad.botones_ui")
C = import_module("ingecad_plugin_geocad.categorias")
from views.main_window import MainWindow

DEFECTO = BT.DEFECTO
BT.DEFECTO = {}                 # 1 a 5: sin categorías de fábrica (las barras de siempre)
fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def barras(win):
    """{objectName: barra} de las barras que hay en la ventana."""
    return {b.objectName(): b for b in win.findChildren(QToolBar)}


def ordenes(bar):
    return [a.property("geocad_orden") for a in bar.actions() if a.property("geocad_orden")]


def divisores(bar):
    return sum(1 for a in bar.actions()
               if (bar.widgetForAction(a) is not None and bar.widgetForAction(a).objectName() == "geocad_divisor"))


def poner_geocad(win):
    pkg.PLUGIN = pkg.construir_spec()
    win.add_toolbar(pkg.PLUGIN)
    app.processEvents()


def sacar_geocad(win):
    win.remove_toolbar("geocad")
    app.processEvents()


win = MainWindow()
win.new_document("m")
win.show(); app.processEvents()
llamadas = []
win._invoke_command = lambda n: llamadas.append(n)

# ---- 1. de fábrica: como siempre ---------------------------------------------------------
poner_geocad(win)
b = barras(win)
geo, yag = b.get("plugin_geocad_toolbar"), b.get("geocad_yaguarete_toolbar")
comprobar(geo is not None and yag is not None, "barra GeoCAD y Yaguareté Tools")
fab_geo, fab_yag = ordenes(geo), ordenes(yag)
div_geo, div_yag = divisores(geo), divisores(yag)
comprobar(len(fab_geo) == len(pkg.PLUGIN.toolbar) and "SHPTABLE" in fab_geo, f"GeoCAD con {len(fab_geo)} botones con su orden")
comprobar(fab_yag[:2] == ["RECTANG", "TEXT"] and div_geo > 3 and div_yag == 2, "Yaguareté y divisores de fábrica")
comprobar(not [n for n in b if n.startswith("GeoCADCategoria_")], "sin barras de categorías")
fabrica = C.fabrica(win)
comprobar([n for n, _f in fabrica] == [geo.windowTitle(), "Yaguareté Tools"], "fábrica = las dos barras")

# ---- 2. con categorías ---------------------------------------------------------------------
modelo = BT.distribuir(fabrica)
edicion = [("FILLET", True), ("CHAMFER", True), ("BREAKATPOINT", True), ("STRETCH", True)]
datos = [(o, True) for o in ("SHPQUERY", "SHPTABLE")]
resto = [(o, o != "SELECT") for n, f in modelo for o, _v in f
         if o not in {x for x, _ in edicion + datos}]
BT.guardar("ingecad", [("Edición", edicion), ("Datos SIG", datos), ("Lo demás", resto)], fabrica)
sacar_geocad(win); poner_geocad(win)                   # como al cambiar los módulos
b = barras(win)
ed, da, lo = (b.get(BT.objeto_barra(n)) for n in ("Edición", "Datos SIG", "Lo demás"))
comprobar(None not in (ed, da, lo), "una barra por categoría")
comprobar(ordenes(ed) == ["FILLET", "CHAMFER", "BREAKATPOINT", "STRETCH"], "Edición en su orden")
comprobar(ordenes(da) == ["SHPQUERY", "SHPTABLE"], "Datos SIG en su orden")
comprobar("SELECT" not in ordenes(lo) and "RECTANG" in ordenes(lo), "SELECT oculto, el resto en Lo demás")
geo, yag = b["plugin_geocad_toolbar"], b["geocad_yaguarete_toolbar"]
comprobar(geo.isHidden() and yag.isHidden() and not geo.toggleViewAction().isVisible(),
          "barra GeoCAD y Yaguareté escondidas")
comprobar(not ed.isHidden() and ed.windowTitle() == "Edición", "la barra Edición a la vista")
comprobar(divisores(ed) == 0 and divisores(lo) >= 3, "divisores sólo entre tramos distintos de la fábrica")
ed.actions()[0].trigger(); app.processEvents()
comprobar(llamadas[-1:] == ["FILLET"], "el botón llama a su orden")
visibles = sum(len(ordenes(x)) for x in (ed, da, lo))
comprobar(visibles == len(fab_geo) + len(fab_yag) - 1, f"{visibles} botones a la vista (uno oculto)")

# ---- 3. sacar GeoCAD: nada queda --------------------------------------------------------
sacar_geocad(win)
b = barras(win)
comprobar(not [n for n in b if n.startswith("GeoCADCategoria_") or "geocad" in n.lower()],
          "sin GeoCAD no queda ninguna barra suya")

# ---- 4. como de fábrica: igual que al principio ----------------------------------------
BT.restablecer("ingecad")
poner_geocad(win)
b = barras(win)
geo, yag = b["plugin_geocad_toolbar"], b["geocad_yaguarete_toolbar"]
comprobar(ordenes(geo) == fab_geo and ordenes(yag) == fab_yag, "de fábrica: los mismos botones y orden")
comprobar(divisores(geo) == div_geo and divisores(yag) == div_yag and not geo.isHidden(), "y los mismos divisores")
# aplicar y restaurar sin rearmar (lo que hace la ventana): vuelve exacto
BT.guardar("ingecad", [("Todo", [(o, True) for o in fab_yag + fab_geo])], fabrica)
C.aplicar(win); app.processEvents()
todo = barras(win).get(BT.objeto_barra("Todo"))
comprobar(todo is not None and ordenes(todo) == fab_yag + fab_geo, "una sola barra «Todo»")
C.restaurar(win); app.processEvents()
comprobar(ordenes(geo) == fab_geo and divisores(geo) == div_geo and divisores(yag) == div_yag
          and not geo.isHidden() and not yag.isHidden(), "restaurar sin rearmar: exacto")
comprobar(BT.objeto_barra("Todo") not in barras(win), "la barra «Todo» fuera")
BT.restablecer("ingecad")

# ---- 5. la ventana Administrar botones ------------------------------------------------
QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("Mía", True))


def boton_dlg(dlg, texto):
    return next(x for x in dlg.findChildren(QPushButton) if x.text() == texto)


def usar(dlg):
    cats, bots = dlg.findChildren(QListWidget)
    boton_dlg(dlg, "Nueva...").click()
    comprobar(cats.count() == 3 and cats.item(2).text().startswith("Mía"), "Nueva... agrega «Mía»")
    cats.setCurrentRow(1)                                  # Yaguareté Tools
    bots.setCurrentRow(0)                                  # RECTANG
    combo = dlg.findChildren(QtWidgets.QComboBox)[0]
    combo.setCurrentIndex(2)
    boton_dlg(dlg, "Pasar").click()
    cats.setCurrentRow(1)
    bots.item(0).setCheckState(Qt.Unchecked)               # TEXT oculto
    comprobar(cats.item(1).text().endswith(f"({len(fab_yag) - 2}/{len(fab_yag) - 1})"), "el contador ve el oculto")
    return 1


BU._exec = usar
ecos = []
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
g = BT.leer("ingecad")
comprobar(g is not None and g["categorias"][2] == {"nombre": "Mía", "botones": ["RECTANG"]}, "guardado «Mía» con RECTANG")
comprobar(g["ocultos"] == ["TEXT"], "TEXT oculto guardado")
b = barras(win)
mia = b.get(BT.objeto_barra("Mía"))
comprobar(mia is not None and ordenes(mia) == ["RECTANG"], "la barra «Mía» armada al aceptar")
yag = b["geocad_yaguarete_toolbar"]
comprobar(not yag.isHidden() and "RECTANG" not in ordenes(yag) and "TEXT" not in ordenes(yag)
          and ordenes(yag)[0] == "STRETCH", "Yaguareté sin RECTANG ni TEXT, en su lugar")
comprobar(any("guardadas" in e for e in ecos), "aviso en la línea de comandos")


def por_tema(dlg):
    boton_dlg(dlg, "Una por tema").click()
    cats = dlg.findChildren(QListWidget)[0]
    nombres = [cats.item(i).text().split("  (")[0] for i in range(cats.count())]
    comprobar("Edición" in nombres and "Datos" in nombres and "Imágenes" in nombres, "Una por tema: " + ", ".join(nombres))
    return 1


BU._exec = por_tema
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
b = barras(win)
comprobar(BT.objeto_barra("Datos") in b and BT.objeto_barra("Imagenes") in b, "barras por tema armadas")


# 3.47.0: mirar no prende nada (Fernando, 25/10/2026); Cancelar no toca las barras
def foto_barras():
    app.processEvents()
    return {n: (ordenes(x), x.isHidden()) for n, x in barras(win).items()}


b[BT.objeto_barra("Datos")].setVisible(False)              # escondida a mano
antes_v, durante = foto_barras(), {}


def mirar(dlg):
    durante.update(foto_barras())
    cats = dlg.findChildren(QListWidget)[0]
    nombres = [cats.item(i).text().split("  (")[0] for i in range(cats.count())]
    i = nombres.index("Datos")
    comprobar(cats.item(i).checkState() == Qt.Unchecked, "la barra escondida a mano aparece apagada")
    return 0


BU._exec = mirar
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
comprobar(durante == antes_v, "con la ventana abierta las barras no cambian")
comprobar(foto_barras() == antes_v, "Cancelar: las barras quedan como estaban")
C.aplicar(win); app.processEvents()                          # rearmar (módulos, arranque)
comprobar(barras(win)[BT.objeto_barra("Datos")].isHidden(), "al rearmar, la escondida sigue escondida")


def apagar(dlg):
    cats = dlg.findChildren(QListWidget)[0]
    nombres = [cats.item(i).text().split("  (")[0] for i in range(cats.count())]
    cats.item(nombres.index("Datos")).setCheckState(Qt.Checked)         # la vuelve a prender
    cats.item(nombres.index("Edición")).setCheckState(Qt.Unchecked)     # la barra entera
    return 1


BU._exec = apagar
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
app.processEvents()                       # Qt muestra las barras nuevas en la vuelta siguiente
b = barras(win)
comprobar(BT.objeto_barra("Edición") not in b or not ordenes(b[BT.objeto_barra("Edición")]),
          "la casilla de la categoría apaga la barra entera")
comprobar("Edición" in BT.leer("ingecad")["apagadas"], "la barra apagada queda guardada")
comprobar(not b[BT.objeto_barra("Datos")].isHidden(), "tildada en la ventana, la barra vuelve a la vista")
comprobar(b["plugin_geocad_toolbar"].isHidden() and b["geocad_yaguarete_toolbar"].isHidden(), "las de fábrica escondidas")
comprobar("TEXT" not in sum((ordenes(x) for n, x in b.items() if n.startswith("GeoCADCategoria_")), []),
          "lo oculto sigue oculto")


def fabrica_dlg(dlg):
    boton_dlg(dlg, "Como de fábrica").click()
    return 1


BU._exec = fabrica_dlg
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
b = barras(win)
comprobar(BT.leer("ingecad") is None and not [n for n in b if n.startswith("GeoCADCategoria_")],
          "Como de fábrica: nada guardado y sin barras de categorías")
comprobar(ordenes(b["plugin_geocad_toolbar"]) == fab_geo and ordenes(b["geocad_yaguarete_toolbar"]) == fab_yag,
          "las barras de siempre")
BU._exec = lambda dlg: 0                                    # Cancelar: nada cambia
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
comprobar(BT.leer("ingecad") is None and not barras(win)["plugin_geocad_toolbar"].isHidden(), "Cancelar no cambia nada")

# ---- 6. las categorías de fábrica (3.39.0): las «Yaguá ...» de Fernando ------------------
BT.DEFECTO = DEFECTO
BT.restablecer("ingecad")
sacar_geocad(win); poner_geocad(win)
b = barras(win)
existen = set(fab_geo) | set(fab_yag)


def a_la_vista(b):
    """{categoría: botones} de las barras de categorías a la vista."""
    app.processEvents()
    return {x.windowTitle(): ordenes(x) for n, x in b.items()
            if n.startswith("GeoCADCategoria_") and ordenes(x) and not x.isHidden()}


# 3.47.0, primera instalación: sólo los botones de IngeCAD que GeoCAD reconfiguró,
# en sus categorías; el resto apagado (Fernando, 25/10/2026)
esperado = {}
for nombre, ids in DEFECTO["ingecad"]:
    fila = [o for o in ids if o in existen and o in BT.PRENDIDOS["ingecad"]]
    if fila:
        esperado[nombre] = fila
vista = a_la_vista(b)
comprobar(vista == esperado and set(sum(vista.values(), [])) == set(BT.PRENDIDOS["ingecad"]) & existen,
          "sin nada guardado: a la vista sólo " + str(vista))
geo, yag = b["plugin_geocad_toolbar"], b["geocad_yaguarete_toolbar"]
comprobar(not ordenes(geo) and not ordenes(yag) and geo.isHidden() and yag.isHidden(),
          "la barra GeoCAD y Yaguareté Tools vacías y escondidas")
BT.guardar("ingecad", [("Todo", [(o, True) for o in fab_yag + fab_geo])], C.fabrica(win))
C.aplicar(win); app.processEvents()
BU._exec = fabrica_dlg
C.cmd_administrar(types.SimpleNamespace(host=win, echo=ecos.append))
b = barras(win)
comprobar(BT.leer("ingecad") is None and BT.objeto_barra("Todo") not in b
          and a_la_vista(b) == esperado, "Como de fábrica: vuelve la primera instalación")
sacar_geocad(win)
comprobar(not [n for n in barras(win) if n.startswith("GeoCADCategoria_") or "geocad" in n.lower()],
          "sin GeoCAD no queda ninguna barra suya")

win.close()
if fallas:
    print("FALLAS:", *fallas, sep="\n  ")
    sys.exit(1)
print("TODO OK")
