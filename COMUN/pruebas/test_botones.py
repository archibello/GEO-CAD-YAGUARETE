"""Administrar botones (3.38.0): categorías propias para los botones de
GeoCAD, cada una una barra, en IngeCAD y en QGIS (pedido de Fernando,
24/10/2026). El modelo (núcleo), la ventana sin widgets, cómo se ponen las
barras (con barras simuladas) y que esté en el menú GeoCAD de los dos."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, json, tempfile, types, filecmp
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "COMUN"))
from nucleo import botones as BT, botones_barras as BB, botones_ui as BU

# ---- 1. el modelo (sin categorías de fábrica: las barras de siempre) --------------------
DEFECTO = BT.DEFECTO
BT.DEFECTO = {}
FAB = [("GeoCAD", ["SELECT", "SHPTABLE", "BLOCK"]), ("Yaguareté Tools", ["RECTANG", "FILLET"])]
assert BT.leer("ingecad") is None                                   # sin archivo: de fábrica
assert BT.distribuir(FAB) == [("GeoCAD", [("SELECT", True), ("SHPTABLE", True), ("BLOCK", True)]),
                              ("Yaguareté Tools", [("RECTANG", True), ("FILLET", True)])]
assert BT.barras("ingecad", FAB) is None
# lo igual a la fábrica no se guarda
BT.guardar("ingecad", BT.distribuir(FAB), FAB)
assert BT.leer("ingecad") is None
modelo = [("Edición", [("FILLET", True), ("RECTANG", False)]),
          ("Datos y selección", [("SHPTABLE", True), ("SELECT", True)])]
BT.guardar("ingecad", modelo, FAB)
assert BT.leer("ingecad") == {"categorias": [{"nombre": "Edición", "botones": ["FILLET", "RECTANG"]},
                                              {"nombre": "Datos y selección", "botones": ["SHPTABLE", "SELECT"]}],
                              "ocultos": ["RECTANG"], "apagadas": []}
# BLOCK no estaba en ninguna: vuelve a su barra de fábrica (creada al final)
assert BT.barras("ingecad", FAB) == [("Edición", ["FILLET"]), ("Datos y selección", ["SHPTABLE", "SELECT"]),
                                     ("GeoCAD", ["BLOCK"])]
# un botón nuevo (versión nueva) va a la categoría con el nombre de su barra
BT.guardar("ingecad", [("GeoCAD", [("SELECT", True)]), ("Mía", [("FILLET", True), ("RECTANG", True),
                                                               ("SHPTABLE", True), ("BLOCK", True)])], FAB)
fab2 = [("GeoCAD", ["SELECT", "SHPTABLE", "BLOCK", "NUEVO"]), FAB[1]]
assert BT.barras("ingecad", fab2)[0] == ("GeoCAD", ["SELECT", "NUEVO"])
# módulo apagado: sus botones no están, pero no se pierden al guardar
BT.guardar("ingecad", [("Edición", [("FILLET", True), ("RECTANG", True)]),
                       ("Datos", [("SHPTABLE", True), ("SELECT", False), ("BLOCK", True)])], FAB)
sin_bloques = [("GeoCAD", ["SELECT", "SHPTABLE"]), FAB[1]]
m = BT.distribuir(sin_bloques, BT.leer("ingecad"))
assert m == [("Edición", [("FILLET", True), ("RECTANG", True)]), ("Datos", [("SHPTABLE", True), ("SELECT", False)])]
BT.guardar("ingecad", [("Edición", [("RECTANG", True), ("FILLET", True)]), m[1]], sin_bloques)
assert BT.leer("ingecad")["categorias"][1]["botones"] == ["SHPTABLE", "SELECT", "BLOCK"]
assert BT.leer("ingecad")["ocultos"] == ["SELECT"]
assert BT.barras("ingecad", FAB)[1] == ("Datos", ["SHPTABLE", "BLOCK"])   # vuelve a su categoría
# cada programa lo suyo, en el mismo archivo
FQ = [("Dibujo CAD", ["dibujo:line", "dibujo:arc"]), ("Capas CAD", ["capas:layiso"])]
BT.guardar("qgis", [("Todo", [("capas:layiso", True), ("dibujo:arc", True), ("dibujo:line", True)])], FQ)
data = json.loads(BT.archivo().read_text(encoding="utf-8"))
assert set(data) == {"ingecad", "qgis", "_version"} and BT.archivo().name == "botones.json"
BT.restablecer("qgis")
assert BT.leer("qgis") is None and BT.leer("ingecad") is not None
# archivo dañado: de fábrica, sin romper nada
BT.archivo().write_text("{no es json", encoding="utf-8")
assert BT.leer("ingecad") is None and BT.barras("ingecad", FAB) is None
BT.archivo().write_text(json.dumps({"ingecad": {"categorias": [{"nombre": "A", "botones": ["FILLET", 3]},
                                                               {"nombre": "A"}, "x", {"nombre": ""}]}}))
assert BT.leer("ingecad") == {"categorias": [{"nombre": "A", "botones": ["FILLET"]}], "ocultos": [],
                              "apagadas": []}
BT.restablecer("ingecad")
# una por tema y el nombre de la barra
temas = {"SELECT": "seleccion", "SHPTABLE": "datos", "BLOCK": "bloques", "RECTANG": "dibujo", "FILLET": "edicion"}
pt = BT.por_temas(BT.distribuir(FAB), temas.get, {"seleccion": "Selección", "datos": "Datos"})
assert [n for n, _f in pt] == ["Selección", "Datos", "Bloques", "Dibujo", "Edicion"]
assert BT.objeto_barra("Edición y más") == "GeoCADCategoria_Edicion_y_mas"
assert BT.objeto_barra("¿?") == "GeoCADCategoria_sin_nombre"
print("ok modelo")

# ---- 1a. 3.60.0: Yaguá Capas = la barra de IngeCAD, también en lo ya guardado -----------
assert dict(DEFECTO["qgis"])["Yaguá Capas"] == ("capas:layprops", "capas:capa", "capas:color",
                                                "capas:linetype", "capas:lineweight",
                                                "capas:fill", "capas:filltr")      # 3.64.0
assert "capas:capa" not in dict(DEFECTO["qgis"])["Yaguá Dibujo"]
viejo = {"qgis": {"categorias": [{"nombre": "Yaguá Dibujo", "botones": ["dibujo:line", "capas:capa"]},
                                 {"nombre": "Yaguá Capas", "botones": ["capas:layprops", "capas:layiso"]}],
                  "ocultos": ["capas:capa", "dibujo:line"]}}
BT.archivo().write_text(json.dumps(viejo), encoding="utf-8")
m = BT.leer("qgis")
assert m["categorias"] == [{"nombre": "Yaguá Dibujo", "botones": ["dibujo:line"]},
                           {"nombre": "Yaguá Capas", "botones": ["capas:layprops", "capas:capa", "capas:color",
                                                                 "capas:linetype", "capas:lineweight",
                                                                 "capas:fill", "capas:filltr"]}], m
assert m["ocultos"] == ["dibujo:line"]
assert json.loads(BT.archivo().read_text(encoding="utf-8"))["qgis"]["migraciones"] == ["capas-ingecad",
                                                                                      "capas-panel", "capas-banco",
                                                                                      "capas-relleno"]
# 3.60.7: lo que ya pasó por la 3.60.2: LAYISO y los demás sólo en el banco Capas CAD
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "Mía", "botones": [
    "capas:layiso", "dibujo:line", "capas:lwdisplay"]}], "ocultos": ["capas:layoff", "dibujo:arc"],
    "migraciones": ["capas-ingecad", "capas-panel"]}}), encoding="utf-8")
m = BT.leer("qgis")
assert m["categorias"][0]["botones"] == ["dibujo:line"] and m["ocultos"] == ["dibujo:arc"], m
# 3.60.2: lo que ya pasó por la 3.60.0/1 (botón del panel al final): el botón va primero
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "Yaguá Capas", "botones": [
    "capas:capa", "capas:color", "capas:linetype", "capas:lineweight", "capas:layprops"]}],
    "ocultos": ["capas:layprops"], "migraciones": ["capas-ingecad"]}}), encoding="utf-8")
m = BT.leer("qgis")
assert m["categorias"][0]["botones"][:2] == ["capas:layprops", "capas:capa"] and m["ocultos"] == [], m
# una sola vez: si Fernando después saca la lista de color de Yaguá Capas, queda así
FQ4 = [("Capas CAD", ["capas:capa", "capas:color", "capas:linetype", "capas:lineweight"]),
       ("Dibujo CAD", ["dibujo:line"])]
mod = BT.distribuir(FQ4, BT.leer("qgis"))
mod = [(n, [(b, v) for b, v in f if b != "capas:color"]) for n, f in mod] + [("Otra", [("capas:color", True)])]
BT.guardar("qgis", mod, FQ4)
assert dict(BT.barras("qgis", FQ4))["Otra"] == ["capas:color"]
assert "capas:color" not in dict(BT.barras("qgis", FQ4))["Yaguá Capas"]
# sin categoría Yaguá Capas guardada: se crea al final
BT.archivo().write_text(json.dumps({"qgis": {"categorias": [{"nombre": "A", "botones": ["capas:capa"]}]}}),
                        encoding="utf-8")
assert [c["nombre"] for c in BT.leer("qgis")["categorias"]] == ["A", "Yaguá Capas"]
assert BT.leer("ingecad") is None                       # IngeCAD no se toca
BT.restablecer("qgis")
print("ok Yaguá Capas de IngeCAD")

# ---- 1b. las categorías de fábrica (3.39.0): las de Fernando ---------------------------
BT.DEFECTO = DEFECTO
assert [n for n, _b in DEFECTO["ingecad"]][:2] == ["Yaguá GEO", "Yaguá Dibujo"]
assert [n for n, _b in DEFECTO["qgis"]][0] == "Yaguá Dibujo" and len(DEFECTO["qgis"]) == 8
for p_ in ("ingecad", "qgis"):
    ids = [b for _n, bs in DEFECTO[p_] for b in bs]
    assert len(ids) == len(set(ids)), p_                    # ningún botón dos veces
BT.restablecer("ingecad")
FAB3 = [("GeoCAD", ["SELECT", "GEOFILTER", "SHPTABLE", "OTRO"]), ("Yaguareté Tools", ["RECTANG", "FILLET"])]
# sin nada guardado: las de fábrica, APAGADAS (3.47.0), también la de lo que no
# figura (su barra de siempre); a la vista sólo los botones de IngeCAD que GeoCAD
# reconfiguró, en sus categorías (Fernando, 25/10/2026)
FAB3 = [FAB3[0], ("Yaguareté Tools", ["RECTANG", "FILLET", "BREAKATPOINT"])]
assert BT.barras("ingecad", FAB3) == [("Yaguá Dibujo", ["RECTANG"]), ("Yaguá Edición", ["FILLET"])]
modelo_f = BT.distribuir(FAB3, None, "ingecad")
assert ("Yaguá Select", [("SELECT", True), ("GEOFILTER", True)]) in modelo_f
assert ("Yaguá Edición", [("BREAKATPOINT", False), ("FILLET", True)]) in modelo_f
assert modelo_f[-1] == ("GeoCAD", [("OTRO", True)])
todas = {n for n, _f in modelo_f}
assert BT.apagadas("ingecad", modelo_f) == todas - {"Yaguá Dibujo", "Yaguá Edición"}
BT.guardar("ingecad", modelo_f, FAB3, todas - {"Yaguá Dibujo", "Yaguá Edición"})
assert BT.leer("ingecad") is None              # igual a la fábrica: no se guarda
# PRENDIDOS = las herramientas de IngeCAD que Yaguareté Tools saca de su barra
import re as _re
yag = (RAIZ / "INGECAD/codigo/geocad/yaguarete.py").read_text(encoding="utf-8")
assert tuple(_re.findall(r'\("([A-Z]+)", "[a-z]*", "[a-z_]+"\)', yag)) == BT.PRENDIDOS["ingecad"]
assert "qgis" not in BT.PRENDIDOS              # en QGIS sólo la línea de comandos (un panel)
assert BT.leer("ingecad") is None
# prender una barra: se guarda, y sólo esa aparece
BT.guardar("ingecad", modelo_f, FAB3, todas - {"Yaguá Select", "Yaguá Edición"})
assert BT.leer("ingecad")["apagadas"] == [n for n, _f in modelo_f
                                          if n not in ("Yaguá Select", "Yaguá Edición")]
assert BT.barras("ingecad", FAB3) == [("Yaguá Select", ["SELECT", "GEOFILTER"]), ("Yaguá Edición", ["FILLET"])]
BT.guardar("ingecad", modelo_f, FAB3, todas)    # todas apagadas: ninguna barra
assert BT.barras("ingecad", FAB3) == []
# todas prendidas (como guardaban las versiones de antes, sin «apagadas»)
BT.guardar("ingecad", modelo_f, FAB3)
d = BT.barras("ingecad", FAB3)
assert ("Yaguá Select", ["SELECT", "GEOFILTER"]) in d and d[-1] == ("GeoCAD", ["OTRO"])
# botones ocultos de fábrica: el último estado de Fernando (25/10/2026)
assert "SHPTHEME" in BT.OCULTOS["ingecad"]
assert ("SHPTHEME", False) in dict(BT.distribuir([("GeoCAD", ["SHPTHEME"])], None, "ingecad"))["Yaguá Dibujo"]
assert dict(DEFECTO["qgis"])["Yaguá-IngeCAD"] == ("puente:send",)
BT.restablecer("ingecad")
BT.guardar("ingecad", [("Mía", [(b, True) for _n, f in modelo_f for b, _v in f])], FAB3)
assert BT.barras("ingecad", FAB3) == [("Mía", ["RECTANG", "SELECT", "GEOFILTER", "SHPTABLE", "BREAKATPOINT",
                                              "FILLET", "OTRO"])]
# lo elegido por cada uno se respeta; «Como de fábrica» vuelve a las de Fernando
assert BU.Ventana(BT.distribuir(FAB3, programa="ingecad")).resultado() == modelo_f
BT.restablecer("ingecad")
# la casilla de la categoría prende o apaga la barra entera (3.47.0)
V = BU.Ventana(modelo_f, BT.apagadas("ingecad", modelo_f))
i = V.nombres().index("Yaguá Select")
assert not V.prendida(i)
V.prender(i, True)
assert V.prendida(i) and V.renombrar(i, "Selección") is None and V.prendida(i)
assert V.prendida(V.nombres().index("Yaguá Edición"))
j = V.nombres().index("Yaguá Tablas")
assert not V.prendida(j) and V.renombrar(j, "Ed") is None and "Ed" in V.apagadas
assert V.borrar(j) is None and "Ed" not in V.apagadas
BT.guardar("ingecad", V.resultado(), FAB3, V.apagadas)
assert [n for n, _b in BT.barras("ingecad", FAB3)] == ["Yaguá Dibujo", "Selección", "Yaguá Edición"]
BT.restablecer("ingecad")
# los módulos: todos prendidos de fábrica (también un estándar desde 3.39.0), menos
# Papel y Capas en QGIS: opcionales, al instalar sólo la línea de comandos (3.60.6)
from nucleo import modulos as MO
assert [(prog, m.clave) for prog in MO.PROGRAMAS for m in MO.CATALOGO[prog]
        if not m.defecto] == [("qgis", "papel"), ("qgis", "capas")]
print("ok fábrica")
BT.DEFECTO = {}

# ---- 2. la ventana, sin widgets ------------------------------------------------------
V = BU.Ventana(BT.distribuir(FAB))
assert V.nueva("GeoCAD") and V.nueva("  ") and V.nueva("Edición") is None
assert V.nombres() == ["GeoCAD", "Yaguareté Tools", "Edición"]
V.pasar(1, 1, 2)                                  # FILLET a Edición
V.mover_boton(0, 2, -1)                           # BLOCK antes que SHPTABLE
V.mostrar(0, 0, False)                            # SELECT oculto
assert V.mover_categoria(2, -1) == 1 and V.mover_categoria(0, -1) == 0
assert V.renombrar(0, "Yaguareté Tools") and V.renombrar(0, "Datos") is None
assert V.resultado() == [("Datos", [("SELECT", False), ("BLOCK", True), ("SHPTABLE", True)]),
                         ("Edición", [("FILLET", True)]), ("Yaguareté Tools", [("RECTANG", True)])]
assert V.borrar(1) is None                        # FILLET pasa a la anterior
assert V.resultado()[0][1][-1] == ("FILLET", True) and len(V.modelo) == 2
assert V.borrar(0) is None and V.borrar(0) == "Tiene que quedar al menos una categoría."
print("ok ventana")


# ---- 3. las barras, con barras simuladas -----------------------------------------------
class Accion:
    def __init__(self, nombre, sep=False, widget=None):
        self.nombre, self.sep, self.widget, self.props = nombre, sep, widget, {}
    def isSeparator(self): return self.sep
    def property(self, k): return self.props.get(k)
    def setProperty(self, k, v): self.props[k] = v
    def __repr__(self): return self.nombre


class Widget:
    def __init__(self, nombre=""): self.nombre = nombre
    def objectName(self): return self.nombre


class Barra:
    def __init__(self, titulo, acciones=()):
        self.titulo, self._a, self.oculta = titulo, list(acciones), False
        self.vista = types.SimpleNamespace(v=True, setVisible=lambda b: setattr(self.vista, "v", b))
    def windowTitle(self): return self.titulo
    def actions(self): return list(self._a)
    def removeAction(self, a):
        if a in self._a: self._a.remove(a)
    def addAction(self, a): self.removeAction(a); self._a.append(a)
    def insertAction(self, antes, a): self.removeAction(a); self._a.insert(self._a.index(antes), a)
    def addSeparator(self): a = Accion("|", sep=True); self._a.append(a); return a
    def widgetForAction(self, a): return a.widget
    def isHidden(self): return self.oculta
    def setVisible(self, b): self.oculta = not b
    def toggleViewAction(self): return self.vista
    def setParent(self, p): pass
    def deleteLater(self): pass


class Ventana:
    def __init__(self): self.quitadas = []
    def removeToolBar(self, b): self.quitadas.append(b)


def boton(nombre):
    a = Accion(nombre); a.setProperty("geocad_id", nombre); return a


idb = lambda a: a.property("geocad_id")
line, arc, rect = boton("line"), boton("arc"), boton("rect")
ortho = boton("ortho")
dt, ed = boton("dtext"), boton("edittext")
fuente = Accion("[fuente]", widget=Widget("combo"))
div = Accion("[div]", widget=Widget(BB.DIVISOR))
dibujo = Barra("Dibujo CAD", [line, arc, rect, Accion("|", sep=True), ortho])
texto = Barra("Texto CAD", [dt, ed, fuente])
capas = Barra("Capas CAD", [boton("layiso"), div, boton("layoff")])
fabs = [("Dibujo CAD", dibujo), ("Texto CAD", texto), ("Capas CAD", capas)]
antes = {b.titulo: b.actions() for _n, b in fabs}
assert [(n, [x for x, _a in f]) for n, f in BB.elementos(fabs, idb)] == \
    [("Dibujo CAD", ["line", "arc", "rect", "ortho"]), ("Texto CAD", ["dtext", "edittext"]),
     ("Capas CAD", ["layiso", "layoff"])]
t = BB.temas(fabs, idb)
assert t["line"] == t["rect"] != t["ortho"] and t["layiso"] != t["layoff"]
win = Ventana()
nuevas = []
def nueva_barra(nombre):
    b = Barra(nombre); nuevas.append(b); return b
assert BB.aplicar(win, fabs, idb, None, nueva_barra) == [] and not nuevas    # de fábrica: nada
dist = [("Texto CAD", ["edittext", "line"]), ("Mía", ["arc", "rect", "ortho", "layoff"])]
puestas = BB.aplicar(win, fabs, idb, dist, nueva_barra)
assert [b.titulo for b in puestas] == ["Texto CAD", "Mía"] and len(nuevas) == 1
# en su barra de fábrica los botones van primero; la lista de fuentes se queda
assert [a.nombre for a in texto.actions()] == ["edittext", "|", "line", "|", "[fuente]"]
# entre tramos distintos de la fábrica, un divisor
assert [a.nombre for a in nuevas[0].actions()] == ["arc", "rect", "|", "ortho", "|", "layoff"]
# Dibujo y Capas quedaron vacías: escondidas (también en el menú de barras)
assert dibujo.actions() == [] or all(a.isSeparator() for a in dibujo.actions())
assert dibujo.oculta and capas.oculta and not dibujo.vista.v and not texto.oculta
# volver a aplicar no duplica; restaurar deja todo igual que antes
BB.aplicar(win, fabs, idb, dist, nueva_barra)
assert [a.nombre for a in texto.actions()] == ["edittext", "|", "line", "|", "[fuente]"]
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes, ({b.titulo: b.actions() for _n, b in fabs}, antes)
assert not dibujo.oculta and dibujo.vista.v and len(win.quitadas) == 2 and win.quitadas[-1] is nuevas[-1]
BB.restaurar(win)                                   # dos veces: nada
assert {b.titulo: b.actions() for _n, b in fabs} == antes
# 3.39.1: aplicar dos veces seguidas con la distribución calculada DESPUÉS de
# restaurar (en QGIS, la segunda vez contaba con las barras de fábrica vacías
# y los botones quedaban fuera de toda barra)
calc = lambda fab: [("Mía", [b for _n, f in fab for b in f])]
BB.aplicar(win, fabs, idb, calc, nueva_barra)
BB.aplicar(win, fabs, idb, calc, nueva_barra)
assert [a.nombre for a in nuevas[-1].actions() if idb(a)] == ["line", "arc", "rect", "ortho", "dtext",
                                                              "edittext", "layiso", "layoff"]
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes
# lo oculto no está en ninguna barra
BB.aplicar(win, fabs, idb, [("Dibujo CAD", ["line"])], nueva_barra)
assert [a.nombre for a in dibujo.actions()] == ["line"] and texto.actions() == [fuente]
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes
# 3.47.0: mirar no cambia nada (Fernando, 25/10/2026): con las categorías puestas,
# la ventana lee la fábrica de la foto sin tocar las barras
fab_antes = [(n, [x for x, _a in f]) for n, f in BB.elementos(fabs, idb)]
puestas = BB.aplicar(win, fabs, idb, dist, nueva_barra)
ahora = {id(b): b.actions() for b in puestas}
assert [(n, [x for x, _a in f]) for n, f in BB.elementos(fabs, idb, win)] == fab_antes
assert {id(b): b.actions() for b in puestas} == ahora
# la barra que el usuario escondió sigue escondida al rearmar; al aceptar, no
puestas[-1].setVisible(False)
assert BB.escondidas(win) == {"Mía"}
puestas = BB.aplicar(win, fabs, idb, dist, nueva_barra)
assert puestas[-1].isHidden() and BB.escondidas(win) == {"Mía"}
puestas = BB.aplicar(win, fabs, idb, dist, nueva_barra, mostrar=True)
assert not puestas[-1].isHidden() and BB.escondidas(win) == set()
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes
# 3.47.0: todas las categorías apagadas ([] no es None): ninguna barra de botones
n_antes = len(nuevas)
assert BB.aplicar(win, fabs, idb, [], nueva_barra) == [] and len(nuevas) == n_antes
assert not [a for _n, b in fabs for a in b.actions() if idb(a)]
assert dibujo.oculta and capas.oculta
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes and not dibujo.oculta
print("ok barras")

# ---- 4. IngeCAD: en el menú GeoCAD, con los temas de la barra -------------------------
from core.plugins import load_plugin, SEPARATOR
lp = load_plugin(RAIZ / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
pkg = import_module("ingecad_plugin_geocad")
C = import_module("ingecad_plugin_geocad.categorias")
Bar_ = import_module("ingecad_plugin_geocad.barra")
Y = import_module("ingecad_plugin_geocad.yaguarete")
spec = pkg.construir_spec()
assert spec.commands["GEOBUTTONS"] is C.cmd_administrar
items = [i for i in spec.menu if i is not SEPARATOR and hasattr(i, "command")]
textos = [i.label for i in items] if hasattr(items[0], "label") else [i.text for i in items]
cmds = [i.command for i in items]
assert cmds.index("GEOBUTTONS") == cmds.index("GEOCADMODULES") + 1          # junto a Módulos
ui = json.loads((RAIZ / "INGECAD/codigo/geocad/i18n/es/ui.json").read_text(encoding="utf-8"))
assert "Tool Settings..." in textos and "Manage buttons..." not in textos   # 3.70.7 (Fernando)
assert ui["Tool Settings..."] == "Administrar Herramientas..." and "Manage buttons..." not in ui
# 3.70.7: «Paste in Place» fuera del menú GeoCAD; de respaldo en los bancos (completo)
assert "GEOPASTEORIG" not in cmds
assert "GEOPASTEORIG" in [i.command for i in pkg.construir_spec(completo=True).menu if hasattr(i, "command")]
assert set(Bar_.TEMAS.values()) | set(Y.TEMAS.values()) <= set(C.NOMBRES_TEMA)
assert C.tema_de("FILLET") == "edicion" and C.tema_de("SHPTABLE") == "datos" and C.tema_de("X") is None
a = Accion("x"); a.setProperty("geocad_orden", "FILLET")
assert C.id_de(a) == "FILLET" and C.id_de(Accion("y")) is None
# sin ventana: aviso, sin romper
ecos = []
C.cmd_administrar(types.SimpleNamespace(host=None, echo=ecos.append))
assert ecos and "ventana" in ecos[0]
# el núcleo, igual en los dos lados
for n in ("botones.py", "botones_barras.py", "botones_ui.py"):
    for lado in ("INGECAD/codigo/geocad", "QGIS/codigo/geocad"):
        assert filecmp.cmp(RAIZ / "COMUN/nucleo" / n, RAIZ / lado / n, shallow=False), (n, lado)
# 3.60.7: los bancos de respaldo (Fernando, 02/11/2026): Dibujo CAD y Capas CAD
# enteros, sin barra; de ahí se traen botones a una categoría
layiso2, laymcur = capas.actions()[0], boton("capas:laymcur")
bancos = [(BT.BANCO + "Dibujo CAD", [line, arc, line]), (BT.BANCO + "Capas CAD", [layiso2, laymcur])]
el = [(n, [x for x, _a in f]) for n, f in BB.elementos(fabs, idb, bancos=bancos)]
assert el[-2:] == [("banco:Dibujo CAD", ["line", "arc"]), ("banco:Capas CAD", ["layiso", "capas:laymcur"])]
fabb = el
assert BT.distribuir(fabb) == BT.distribuir(el[:-2])                # un banco no es categoría
g = {"categorias": [{"nombre": "Mía", "botones": ["capas:laymcur", "line"]}], "ocultos": []}
m = BT.distribuir(fabb, g)
assert m[0] == ("Mía", [("capas:laymcur", True), ("line", True)])
assert all(not BT.es_banco(n) for n, _f in m) and "capas:laymcur" not in [b for _n, f in m[1:] for b, _v in f]
v = BU.Ventana(BT.distribuir(el[:-2]))
assert v.donde("line") == "Dibujo CAD" and v.donde("capas:laymcur") is None
v.traer("line", 1)
v.traer("capas:laymcur", 1)
assert v.donde("line") == "Texto CAD" and [b for b, _v in v.modelo[0][1]] == ["arc", "rect", "ortho"]
assert v.modelo[1][1][-2:] == [["line", True], ["capas:laymcur", True]]
# en la barra: el botón del banco que no estaba en ninguna barra se saca al restaurar
puestas = BB.aplicar(win, fabs, idb, [("Capas CAD", ["layiso", "capas:laymcur"])], nueva_barra,
                     bancos=bancos)
assert [a.nombre for a in capas.actions() if idb(a)] == ["layiso", "capas:laymcur"]
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes
calc = lambda fab: [("Nueva", ["capas:laymcur"])] if any(n == "banco:Capas CAD" for n, _f in fab) else []
BB.aplicar(win, fabs, idb, calc, nueva_barra, bancos=bancos)
assert [a.nombre for a in nuevas[-1].actions()] == ["capas:laymcur"]
BB.restaurar(win)
assert {b.titulo: b.actions() for _n, b in fabs} == antes
print("ok bancos de respaldo")

# 3.65.0: tres bancos por tema, iguales en IngeCAD y QGIS (Fernando, 04/11/2026: «meter
# todo en estos tres grupos, así no quedan tan extensos»); cada botón en uno solo
import re
assert BT.BANCOS == ("Configuración", "Edición", "Dibujo")
for prog, temas in BT.TEMA_BANCO.items():
    assert set(temas) == set(BT.BANCOS), prog
    todos = [b for t in BT.BANCOS for b in temas[t]]
    assert len(todos) == len(set(todos)), (prog, [b for b in todos if todos.count(b) > 1])
assert BT.banco_de("ingecad", "FILLET") == "Edición" and BT.banco_de("ingecad", "RECTANG") == "Dibujo"
assert BT.banco_de("ingecad", "ANGREL") == "Configuración" and BT.banco_de("qgis", "otro:x") == "Configuración"
r = BT.bancos("ingecad", [boton(x) for x in ("RECTANG", "FILLET", "NUEVO", "ANGREL", "SELECT", "FILLET")], idb)
assert [(n, [idb(a) for a in f]) for n, f in r] == [
    ("banco:Configuración", ["ANGREL", "NUEVO"]), ("banco:Edición", ["SELECT", "FILLET"]),
    ("banco:Dibujo", ["RECTANG"])], r
assert BT.bancos("ingecad", [Accion("sin")], idb) == []
# todo lo de GeoCAD tiene banco a propósito (nada cae en Configuración por descuido)
fuente_i = (RAIZ / "INGECAD/codigo/geocad/__init__.py").read_text(encoding="utf-8")
ordenes_i = set(re.findall(r'(?:MenuItem|ToolbarItem)\(\s*"[^"]*",\s*"(\w+)"', fuente_i))
ordenes_i |= {o for o, _m, _b in Y.HERRAMIENTAS}
assert len(ordenes_i) > 50, len(ordenes_i)
listados = {b for t in BT.BANCOS for b in BT.TEMA_BANCO["ingecad"][t]}
assert ordenes_i == listados, (ordenes_i - listados, listados - ordenes_i)
q = RAIZ / "QGIS/codigo/geocad"
ids_q = {"dibujo:" + x for x in re.findall(r"_action\(\s*'(\w+)'", (q / "dibujo/plugin.py").read_text(encoding="utf-8"))}
ids_q |= {"dibujo:" + x for x in re.findall(r"_lista\([^,]+,\s*'(\w+)'", (q / "dibujo/plugin.py").read_text(encoding="utf-8"))}
edit = (q / "dibujo/edit_commands.py").read_text(encoding="utf-8").split("EDIT_COMMANDS = [", 1)[1]
ids_q |= {"dibujo:" + x for x in re.findall(r"'(\w+)'\),\s*$", edit.split("\n]", 1)[0], re.M)}
ids_q |= {"dibujo:" + x for x in re.findall(r"\('(zoom\w*|pan|regen)', '", (q / "dibujo/plugin.py").read_text(encoding="utf-8"))}
ids_q |= {"capas:" + x for x in re.findall(r"_action\(\s*'(\w+)'", (q / "capas/plugin.py").read_text(encoding="utf-8"))}
ids_q |= {"capas:" + x for x in ("capa", "color", "linetype", "lineweight", "fill", "filltr")}
fuente_q = (q / "plugin.py").read_text(encoding="utf-8")
ids_q |= {"geocad:" + x for x in re.findall(r'add\("(\w+)"', fuente_q) if x != "send"}
ids_q |= {"geocad:" + x for x in re.findall(r'\("(ge_\w+)"', fuente_q)} | {"puente:send"}
listados_q = {b for t in BT.BANCOS for b in BT.TEMA_BANCO["qgis"][t]}
assert ids_q <= listados_q, ids_q - listados_q
assert '"puente:send" if key == "send" else "geocad:" + key' in fuente_q
# IngeCAD: los bancos con la ventana; lo que sólo está en el menú, con un botón propio
hechos = []
def _propia(window, item):
    hechos.append(item.command)
    a = Accion(item.command)
    a.setProperty("geocad_orden", item.command)
    return a
C._accion_menu, original = _propia, C._accion_menu
vent = types.SimpleNamespace(_plugin_toolbars={})
bi = C.bancos(vent)
assert [n for n, _f in bi] == ["banco:" + t for t in BT.BANCOS], bi
en_bancos = [C.id_de(a) for _n, f in bi for a in f]
assert "GEOCADMODULES" in en_bancos and "ANGREL" in en_bancos and len(en_bancos) == len(set(en_bancos))
assert C.bancos(vent) and len(hechos) == len(set(hechos))          # los propios se hacen una vez
C._accion_menu = lambda *a: (_ for _ in ()).throw(ImportError("sin Qt"))
assert C.bancos(types.SimpleNamespace(_plugin_toolbars={})) == []   # sin Qt: sólo el menú
C._accion_menu = original
print("ok bancos por tema (3.65.0)")
print("ok ingecad")

# ---- 5. QGIS: en el menú GeoCAD; los botones con nombre propio --------------------------
sys.path[:0] = [str(Path(__file__).resolve().parent / "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
import geocad as qpkg
from geocad import plugin as qp
assert qp.BARRAS_GEOCAD[:2] == ("DibujoCADToolbar", "EdicionCADToolbar") and "GeoCADToolbar" in qp.BARRAS_GEOCAD
mensajes = []
iface = types.SimpleNamespace(
    mainWindow=lambda: types.SimpleNamespace(menuBar=lambda: types.SimpleNamespace(insertMenu=lambda *a: None,
                                                                                 removeAction=lambda *a: None),
                                             removeToolBar=lambda *a: None),
    helpMenu=lambda: types.SimpleNamespace(menuAction=lambda: None),
    messageBar=lambda: types.SimpleNamespace(pushMessage=lambda *a, **k: mensajes.append(a)),
    addToolBar=lambda n: None)
P = qpkg.classFactory(iface)
P.initGui()
textos_q = [getattr(i, "text", "") for i in P.menu.items if not isinstance(i, str)]
assert "Administrar Herramientas..." in textos_q and "Administrar botones..." not in textos_q
assert textos_q.index("Administrar Herramientas...") == textos_q.index("Módulos...") + 1
assert not any(t.startswith("Pegar en el lugar") for t in textos_q)      # 3.70.7: fuera del menú
# 3.60.7: sin los submenús Dibujo CAD y Capas CAD; son bancos de Administrar botones
assert "Dibujo CAD" not in textos_q and "Capas CAD" not in textos_q
assert all(BT.es_banco(n) for n, _a in P._bancos())
assert "a.setProperty('geocad_id', 'capas:' + ico)" in (RAIZ / "QGIS/codigo/geocad/capas/plugin.py").read_text(encoding="utf-8")
# 3.65.0: el menú GeoCAD también en los bancos; sin dibujo, ícono de letras sólo en la barra
bq = P._bancos()
assert bq and all(n in ["banco:" + t for t in BT.BANCOS] for n, _f in bq), bq
ids_bq = [a.property("geocad_id") for _n, f in bq for a in f]
assert "geocad:modules" in ids_bq and "geocad:about" in ids_bq and len(ids_bq) == len(set(ids_bq)), ids_bq
assert P.actions["modules"].icono_en_menu is False and not P.actions["modules"].icon().isNull()
assert BT.letras("GEOREFADD") == "B+" and BT.letras("geocad:otra") == "OTR"
P._aplicar_botones()                     # ventana sin barras: nada, sin avisos
assert P._fabricas() == [] and not mensajes
fuente = (RAIZ / "QGIS/codigo/geocad/dibujo/plugin.py").read_text(encoding="utf-8")
assert "setProperty('geocad_id', 'dibujo:' + ico)" in fuente
# 3.60.0: la barra de Capas CAD es la de IngeCAD, cuatro listas con su geocad_id
assert "wa.setProperty('geocad_id', 'capas:' + clave)" in (RAIZ / "QGIS/codigo/geocad/capas/plugin.py").read_text(encoding="utf-8")
P.timer = None
P.unload()
print("ok qgis")
print("TODO OK")
