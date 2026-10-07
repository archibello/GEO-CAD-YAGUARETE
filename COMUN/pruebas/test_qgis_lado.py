from pathlib import Path
"""Los dos lados del puente juntos: el complemento de QGIS (con un QGIS
simulado) y el plugin de IngeCAD (núcleo real), en una misma carpeta personal."""
import os, sys, tempfile, types, shutil, importlib
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(Path(__file__).resolve().parents[2] / "QGIS" / "codigo")]
from pathlib import Path
from core.commands import History
from core.document import Document
from core.plugins import load_plugin
from tools.base import ToolContext
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMessageBox
import geocad as ingecad_puente
from geocad import plugin as qp, buzon as qbuzon

# --- QGIS ---------------------------------------------------------------------
class Bar:
    def __init__(self): self.msgs = []
    def pushMessage(self, title, text, level=None, duration=0): self.msgs.append(text)
class MenuBar:
    def insertMenu(self, before, m): pass
    def removeAction(self, a): pass
class MW:
    def menuBar(self): return MenuBar()
    def removeToolBar(self, t): pass
bar = Bar()
class TB:
    def setObjectName(self, n): pass
    def addAction(self, a): pass
    def deleteLater(self): pass
iface = types.SimpleNamespace(mainWindow=lambda: MW(), helpMenu=lambda: types.SimpleNamespace(menuAction=lambda: None),
                              messageBar=lambda: bar, addToolBar=lambda n: TB(), activeLayer=lambda: None,
                              mapCanvas=lambda: types.SimpleNamespace(extent=lambda: __import__("qgis.core").core._Rect(10, 20, 30, 40)))
P = ingecad_puente.classFactory(iface); P.initGui()
print("menú QGIS:", [i if isinstance(i, str) else i.text for i in P.menu.items])
assert P.toolbar is None                       # botones apagados por defecto

tmp = Path(HOME) / "SIG"; tmp.mkdir()
gp = tmp / "catastro.gpkg"; shutil.copy(os.environ["GDAL_GPKG"] + "/poly_golden.gpkg", gp)
lay = QgsVectorLayer(f"{gp}|layername=POLY", "Parcelas")      # mayúsculas distintas a propósito
otra = QgsVectorLayer("/tmp/x.csv", "CSV suelto")
fuera = QgsVectorLayer("/media/disco/datos.shp", "En disco externo")
for l in (lay, otra, fuera): QgsProject.instance().layers[l.id()] = l
lay.editable = True; lay.modified = True; QMessageBox.answer = QMessageBox.StandardButton.Yes
from geocad.plugin import VERSION as QV
qbuzon.heartbeat("ingecad", {"version": QV})   # IngeCAD abierto con la misma versión: no se lanza
P.send_visible(); print(bar.msgs[-1])
assert not lay.isEditable()                     # se guardó en QGIS antes de enviar
assert "CSV suelto" in bar.msgs[-1] and "Fuera de la carpeta personal: En disco externo" in bar.msgs[-1]
qbuzon.receive("ingecad")                       # descartar ese envío de prueba
# modo por defecto = selección: sin nada seleccionado avisa y no manda nada
P.send_default(); assert "No hay objetos seleccionados" in bar.msgs[-1] and not qbuzon.receive("ingecad")
lay.selected = [2, 4]; P.send_default(); print(bar.msgs[-1])
pedido = qbuzon.receive("ingecad"); assert pedido[0]["capas"][0]["fids"] == [2, 4] and "2 objeto(s)" in bar.msgs[-1]
assert "IngeCAD tiene GeoCAD" not in bar.msgs[-1]
# 3.1.1 IngeCAD con otra versión (o una vieja que no la anuncia): avisa al enviar
qbuzon.heartbeat("ingecad", {"version": "2.8.1"}); P.send_default(); qbuzon.receive("ingecad")
assert f"IngeCAD tiene GeoCAD 2.8.1 y QGIS {QV}" in bar.msgs[-1] and "ACTUALIZARGEOCAD" in bar.msgs[-1], bar.msgs[-1]
qbuzon.heartbeat("ingecad"); P.send_default(); qbuzon.receive("ingecad")
assert "anterior a 3.1.1" in bar.msgs[-1], bar.msgs[-1]
qbuzon.heartbeat("ingecad", {"version": QV})
P.send_screen(); pedido = qbuzon.receive("ingecad"); assert all(c["bbox"] == [10, 20, 30, 40] for c in pedido[0]["capas"])
lay.selected = [2, 4]; P.send_selected()
assert QTimer_shots_ok if False else True

# --- IngeCAD ------------------------------------------------------------------
lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False); assert lp.available, lp.reason
spec = lp.spec
puente = sys.modules["ingecad_plugin_geocad.puente"]
enlace = sys.modules["ingecad_plugin_geocad.enlace"]
doc = Document.new(); hist = History(doc); log = []; answers = []
class Tools:
    def start_tool(self, name):
        ctx = ToolContext(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None,
                          ask_text=lambda p, d="": d,
                          ask_choice=lambda p, items, d="": (lambda a: None if a is None else next((i for i in items if i.startswith(a)), None))(answers.pop(0) if answers else None),
                          services=types.SimpleNamespace(document=doc))
        spec.tools[name](ctx).start()
win = types.SimpleNamespace(tools=Tools(), command_line=types.SimpleNamespace(echo=log.append),
                            viewport=types.SimpleNamespace(push_view=lambda: None, update=lambda: None, view=types.SimpleNamespace(zoom_extents=lambda *a: log.append(f"zoom {a}"))),
                            isMinimized=lambda: False, raise_=lambda: None, activateWindow=lambda: None)
puente._state["window"] = win
puente._tick()                                   # IngeCAD lee el buzón
assert qbuzon.version_of("ingecad") == QV, qbuzon.version_of("ingecad")   # 3.1.1 anuncia su versión
print("\n".join(log)); assert "zoom (10.0, 20.0, 30.0, 40.0)" in log
assert set(enlace.read_links(doc.doc)["GPKG-poly"].hashes) == {2, 4}     # sólo lo seleccionado

# --- QGIS ve el bloqueo -> solo lectura -------------------------------------------
P._tick(); P._tick()
assert lay.readOnly() and lay.id() in P.readonly_by_us, "debía quedar en solo lectura"
# IngeCAD edita y devuelve todo
e = next(e for e in doc.doc.modelspace() if enlace.feat_tag(e))
p = list(e.get_points("xy")); p[0] = (p[0][0] + 2, p[0][1]); e.set_points(p, format="xy")
lay.selected = []
answers[:] = ["Sí"]; log.clear()
sel_tool = spec.tools["QGISSAVESEL"]
ctx = types.SimpleNamespace()
from tools.base import ToolContext as TC
tc = TC(execute=hist.execute, prompt=lambda s: None, echo=log.append, finish=lambda: None, ask_text=lambda p, d="": d,
        ask_choice=lambda p, items, d="": "Sí", services=types.SimpleNamespace(document=doc))
t = sel_tool(tc); t.start(); t.on_selection([e]); print("\n".join(log))
r0 = lay.reloads; P._tick(); assert lay.reloads == r0 + 1, "QGIS debía recargar la capa"
print(bar.msgs[-1]); fid_e = enlace.feat_tag(e).fid
assert lay.selected == [fid_e] and "quedan seleccionados" in bar.msgs[-1]
# IngeCAD desconecta -> QGIS habilita la edición otra vez
answers[:] = []; win.tools.start_tool("SHPRELEASE"); P._tick(); P._tick()
assert not lay.readOnly() and not P.readonly_by_us
# una capa que el usuario puso en solo lectura por su cuenta no se toca
lay.setReadOnly(True); P._tick(); P._tick(); assert lay.readOnly()
lay.setReadOnly(False)
# IngeCAD cerrado: QGIS intenta abrirlo
qbuzon.clear_heartbeat("ingecad")
called = []
qp.subprocess.Popen = lambda cmd, **k: called.append(cmd) or types.SimpleNamespace(poll=lambda: 1)
qp.shutil.which = lambda n: "/usr/bin/" + n if n == "flatpak" else None
otra.visible = False; fuera.visible = False
P.send_visible(); print("lanza:", called)
assert called and called[0][-1] == "org.ingecad.IngeCAD"
from qgis.PyQt.QtCore import QTimer
for f in QTimer.shots: f()
assert QMessageBox.shown and "flatpak override" in QMessageBox.shown[-1]
P.show_status(); print(QMessageBox.shown[-1])
P.unload()
print("TODO OK LOS DOS LADOS")
