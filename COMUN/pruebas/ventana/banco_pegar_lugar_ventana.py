"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
PEGAR EN EL LUGAR (3.66.0, PEGARORIG / PASTEORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «crear en IngeCAD la herramienta PEGAR EN COORDENADAS
ORIGINALES en el menú EDIT debajo de PASTE y lo mismo en QGIS»; «ESO ES PEGAR
EN EL LUGAR»; «CTRL+ALT+V»; «si no está configurado el sistema de
representación de coordenadas, esta acción va a crear el mismo de forma
automática».

Comprueba: «Pegar en el lugar» en Edit justo debajo de Paste, con Ctrl+Alt+V
y sin otro atajo igual; Ctrl+C deja además el mensaje para QGIS; PEGARORIG y
Ctrl+Alt+V pegan en las mismas coordenadas; lo copiado en QGIS se pega con sus
capas, colores, tipos y grosores, el dibujo sin sistema toma el de QGIS y U lo
deshace todo; módulo apagado: sin el ítem ni el mensaje.

Uso (necesita PySide6, ezdxf, numpy, pyproj):
    python banco_pegar_lugar_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad> [carpeta]
Con [carpeta]: deja ahí desde_ingecad.json (lo copiado, para el banco de QGIS)
y, si está, pega desde_qgis.json (lo que copió el banco de QGIS).
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import json, os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
CARPETA = sys.argv[3] if len(sys.argv) > 3 else None
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
PL = import_module("ingecad_plugin_geocad.pegar_lugar")
PI = import_module("ingecad_plugin_geocad.pegar_lugar_ingecad")
IC = import_module("ingecad_plugin_geocad.intercambio")
from views import clipboard
from views.main_window import MainWindow
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def esperar(s=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


def esperar_que(cond, s=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def tiene(formato):
    data = QApplication.clipboard().mimeData()
    return data is not None and data.hasFormat(formato)


def objetos():
    return list(win.document.modelspace())


def puntos(e):
    return [tuple(round(c, 6) for c in p) for p in e.get_points("xy")]


mods.guardar("ingecad", {"pegar_lugar": True})
win = MainWindow()
ecos = []
_echo = win.command_line.echo
win.command_line.echo = lambda t, *a, **k: (ecos.append(str(t)), _echo(t, *a, **k))[1]
win.plugins.loaded[lp.spec.id if hasattr(lp, "spec") else "geocad"] = lp
ver("GeoCAD activo en la ventana", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
win.new_document("m")
win.show(); win.activateWindow(); esperar(0.3)

# ---- 1. Edit > Pegar en el lugar, debajo de Paste, Ctrl+Alt+V ------------------------------
menu, pegar = PI._menu_editar(win)
acciones = menu.actions() if menu is not None else []
accion = getattr(win, PI._ACCION, None)
ver("hay menú Edit con Paste", menu is not None and pegar is not None)
ver("«Pegar en el lugar» justo debajo de Paste", accion in acciones
    and acciones.index(accion) == acciones.index(pegar) + 1,
    str([a.text() for a in acciones[:6]]))
atajo = QKeySequence(PL.ATAJO)
ver("con Ctrl+Alt+V", accion is not None and accion.shortcut() == atajo)
otras = [a.text() for a in win.findChildren(QAction) if a is not accion and a.shortcut() == atajo]
ver("ningún otro Ctrl+Alt+V en IngeCAD", not otras, str(otras))
ver("GeoCAD > Pegar en el lugar y el comando", "GEOPASTEORIG" in lp.spec.tools)

# ---- 2. Ctrl+C: la copia de IngeCAD y el mensaje para QGIS ------------------------------------
doc = win.document.doc
doc.layers.add("Muros", color=1, linetype="DASHED", lineweight=35)
msp = win.document.modelspace()
pl = msp.add_lwpolyline([(5500000, 6900000), (5500010, 6900000), (5500010, 6900010)],
                        dxfattribs={"layer": "Muros"})
circ = msp.add_circle((5500020, 6900020), 3, dxfattribs={"layer": "Muros", "color": 3})
pto = msp.add_point((5500030, 6900030), dxfattribs={"layer": "0"})
win.document.dirty = True
win.regen_in_memory(); esperar(0.2)
win.tools.selection = {pl.dxf.handle, circ.dxf.handle, pto.dxf.handle}
win._cmd_copy()
ok = esperar_que(lambda: PI.mensaje_en_portapapeles() is not None, 8)
ver("Ctrl+C deja la copia de IngeCAD", tiene(clipboard.MIME))
ver("y el mensaje para QGIS", ok)
msg = PI.mensaje_en_portapapeles()
ver("con los 3 objetos", msg is not None and len(msg["objetos"]) == 3,
    str(msg and [o["wkt"][:30] for o in msg["objetos"]]))
if msg is not None:
    ver("polilínea en sus coordenadas y su capa",
        any(o["wkt"].startswith("LINESTRING (5500000 6900000") and o["capa"] == "Muros"
            for o in msg["objetos"]))
    ver("capa Muros: rojo, DASHED, 0.35", msg["capas"].get("Muros") ==
        {"color": "#ff0000", "aci": 1, "tipo_linea": "DASHED", "grosor": 0.35}, str(msg["capas"].get("Muros")))
    ver("círculo como polígono, verde propio", any(o["wkt"].startswith("POLYGON") and o["aci"] == 3
                                                    for o in msg["objetos"]))
    if CARPETA:
        Path(CARPETA, "desde_ingecad.json").write_text(json.dumps(msg), encoding="utf-8")

# ---- 3. PEGARORIG y Ctrl+Alt+V: en las mismas coordenadas -----------------------------------
antes = len(objetos())
win._invoke_command("GEOPASTEORIG")
esperar(0.3)
nuevos = objetos()[antes:]
ver("PEGARORIG pega los 3", len(nuevos) == 3, str(len(nuevos)))
lw = [e for e in nuevos if e.dxftype() == "LWPOLYLINE"]
ver("en el lugar (mismas coordenadas)", lw and puntos(lw[0]) == puntos(pl), str(lw and puntos(lw[0])))
ver("en su capa", lw and lw[0].dxf.layer == "Muros")
antes = len(objetos())
win.viewport.setFocus(); esperar(0.1)
QTest.keyClick(win.viewport, Qt.Key_V, Qt.ControlModifier | Qt.AltModifier)
esperar(0.3)
ver("Ctrl+Alt+V también", len(objetos()) == antes + 3, str(len(objetos()) - antes))
win._cmd_undo(); esperar(0.2)
ver("U lo quita", len(objetos()) == antes)

# ---- 4. lo copiado en QGIS: capas, aspecto y sistema de coordenadas -------------------------
desde_qgis = Path(CARPETA, "desde_qgis.json") if CARPETA else None
if desde_qgis is not None and desde_qgis.exists():
    datos = desde_qgis.read_bytes()
    print("  (pega lo que copió el banco de QGIS: %s)" % desde_qgis)
else:
    datos = PL.empaquetar("qgis", "EPSG:22197", [
        {"wkt": "LineString (5600000 7000000, 5600100 7000050)", "capa": "Calles", "color": None,
         "aci": None, "tipo_linea": None, "grosor": None},
        {"wkt": "Polygon ((5600000 7000000, 5600010 7000000, 5600010 7000010, 5600000 7000000))",
         "capa": "Lotes", "color": "#123456", "aci": None, "tipo_linea": None, "grosor": 0.5}],
        {"Calles": {"color": "#0000ff", "aci": 5, "tipo_linea": "CENTER", "grosor": 0.35},
         "Lotes": {"color": "#a0b0c0", "aci": None, "tipo_linea": None, "grosor": None}})
esperado = PL.desempaquetar(datos)
mime = QMimeData()
mime.setText("wkt_geom\tid\n...")                      # lo que deja QGIS, y aparte lo nuestro
QApplication.clipboard().setMimeData(mime)
PL.dejar_copia(datos, mime, PL.FORMATO_TEXTO)
esperar(0.2)
ver("el dibujo todavía sin sistema", IC.sistema_del_dibujo(win.document.doc) == "")
antes = len(objetos())
win._invoke_command("GEOPASTEORIG")
esperar(0.3)
nuevos = objetos()[antes:]
ver("pega lo de QGIS", len(nuevos) >= len(esperado["objetos"]), "%d de %d" % (len(nuevos), len(esperado["objetos"])))
ver("el dibujo toma el sistema de QGIS", IC.sistema_del_dibujo(win.document.doc) == esperado["crs"],
    IC.sistema_del_dibujo(win.document.doc))
primero = esperado["objetos"][0]
tipo, partes = PL.partes_wkt(primero["wkt"])
pegado = next((e for e in nuevos if e.dxf.layer == primero["capa"]), None)
ver("en sus coordenadas", pegado is not None and tipo == "linea"
    and puntos(pegado)[:2] == [tuple(round(c, 6) for c in p) for p in partes[0][:2]],
    str(pegado is not None and puntos(pegado)[:2]))
for nombre, props in esperado["capas"].items():
    lay = win.document.doc.layers.get(nombre) if nombre in win.document.doc.layers else None
    color_ok = lay is not None and (lay.dxf.color == props["aci"] if props.get("aci") else
                                    props.get("color") is None or
                                    "#%02x%02x%02x" % lay.rgb == props["color"])
    ver("capa %s con su color" % nombre, color_ok, str(lay and (lay.dxf.color, lay.rgb)))
win._cmd_undo(); esperar(0.2)
ver("U quita lo pegado y el sistema", len(objetos()) == antes and IC.sistema_del_dibujo(win.document.doc) == "")

# ---- 5. con sistema ya puesto y distinto: se reproyecta --------------------------------------
if esperado["crs"]:
    win.tools._execute(IC.DefinirSistemaCommand("EPSG:22196" if esperado["crs"] != "EPSG:22196" else "EPSG:22197"))
    print("  (sistema del dibujo ahora: %s)" % IC.sistema_del_dibujo(win.document.doc))
    antes = len(objetos())
    win._invoke_command("GEOPASTEORIG")
    esperar(0.3)
    print("  (eco: %s)" % ecos[-2:])
    nuevos = objetos()[antes:]
    pegado = next((e for e in nuevos if e.dxf.layer == primero["capa"]), None)
    movido = pegado is not None and puntos(pegado)[0] != tuple(round(c, 6) for c in partes[0][0])
    ver("con otro sistema: reproyectado", movido, str(pegado is not None and puntos(pegado)[0]))
    win._cmd_undo(); win._cmd_undo(); esperar(0.2)

# ---- 6. módulo apagado: como venía IngeCAD -------------------------------------------------
mods.poner("ingecad", "pegar_lugar", False)
PI.aplicar(win)
ver("apagado: sin el ítem", getattr(win, PI._ACCION, None) is None
    and not [a for a in menu.actions() if a.objectName() == "geocad_pegar_lugar"])
win.tools.selection = {pl.dxf.handle}
win._cmd_copy()
esperar_que(lambda: clipboard.current_id() is not None
            and clipboard.current_id() != "x", 3)
esperar(0.5)
ver("apagado: Ctrl+C sin el mensaje", tiene(clipboard.MIME) and PI.mensaje_en_portapapeles() is None)
mods.poner("ingecad", "pegar_lugar", True)
PI.aplicar(win)
menu, pegar = PI._menu_editar(win)
ver("prendido otra vez: vuelve el ítem", getattr(win, PI._ACCION, None) in menu.actions())
# IngeCAD rearma los menús al prender o apagar un plugin: el ítem vuelve a Edit
win.menus_changed() if hasattr(win, "menus_changed") else win._build_menus()
menu, pegar = PI._menu_editar(win)
acciones = menu.actions()
ver("después de rearmar los menús, sigue debajo de Paste",
    getattr(win, PI._ACCION, None) in acciones
    and acciones.index(getattr(win, PI._ACCION)) == acciones.index(pegar) + 1)

# ---- 7. actualizar sin reiniciar: la conexión de la versión anterior no queda (3.66.3) --------
board = QApplication.clipboard()
board.dataChanged.disconnect(getattr(win, PI._ACCION + "_copia"))
llamadas = []
def vieja():
    llamadas.append(1)
board.dataChanged.connect(vieja)
setattr(win, PI._ACCION + "_copia", vieja)
PI.aplicar(win)
m = QMimeData(); m.setText("otra cosa"); board.setMimeData(m)
esperar(0.2)
ver("la conexión vieja se reemplaza", not llamadas and getattr(win, PI._ACCION + "_copia") is not vieja)

print("TODO OK" if not fallas else "FALLAS: %s" % fallas)
sys.stdout.flush()
os._exit(1 if fallas else 0)
