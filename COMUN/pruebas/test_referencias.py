"""Referencias a objetos con Shift + clic derecho en QGIS (3.55.0): el menú de
IngeCAD para un solo punto al digitalizar líneas, polilíneas o polígonos con
las herramientas de QGIS. Las cuentas se prueban sin QGIS; si el QGIS de
Flatpak está instalado, además se digitaliza de verdad (sin ventanas) con
el filtro sobre el lienzo y la herramienta de QGIS."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, subprocess, shutil, json, math
os.environ["HOME"] = HOME = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
from geocad import referencias as R, modulos

# el módulo se elige al instalar (sólo en QGIS), activo por defecto
assert "referencias" in [m.clave for m in modulos.catalogo("qgis")]
assert "referencias" not in [m.clave for m in modulos.catalogo("ingecad")]
assert modulos.activo("qgis", "referencias")
assert [m for m in modulos.catalogo("qgis") if m.clave == "referencias"][0].cambia_programa

# Dibujo de GeoCAD (3.55.1): Mayús ya no invierte el ORTO (sólo F8); Mayús + clic
# derecho es el menú de referencias
cmds = (RAIZ / "QGIS" / "codigo" / "geocad" / "dibujo" / "commands.py").read_text(encoding="utf-8")
assert "self.ortho != self.shift" not in cmds and "if base is not None and self.ortho and not" in cmds
assert "Mayús lo invierte" not in (RAIZ / "QGIS" / "codigo" / "geocad" / "dibujo" / "plugin.py").read_text(encoding="utf-8")

# ================================================================ el menú, igual a IngeCAD
textos = [i[1] if i else "-" for i in R.MENU]
assert textos == ["From", "Mid Between 2 Points", "-", "Endpoint", "Midpoint", "Intersection",
                  "Apparent Intersection", "Extension", "-", "Center", "Geometric Center",
                  "Quadrant", "Tangent", "-", "Perpendicular", "Parallel", "Node", "Insertion",
                  "Nearest", "Origin", "None", "-", "Object Snap Settings..."], textos
assert set(R.NO_DISPONIBLES) == {"APP"}          # en gris, como en IngeCAD

def cerca(p, q, tol=1e-6):
    return p is not None and abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol

# ================================================================ las cuentas
# una L (dos tramos de una misma polilínea) y una recta que la cruza
d = R.Datos(segs=[(0, 0, 10, 0, 1), (10, 0, 10, 10, 1), (5, -5, 5, 5, 2)])
assert cerca(R.buscar("END", (9.5, 0.3), 1, d), (10, 0))
assert R.buscar("END", (7, 0.3), 1, d) is None              # fuera de la apertura
assert cerca(R.buscar("MID", (5.4, 0.2), 1, d), (5, 0))
assert cerca(R.buscar("INT", (5.3, 0.4), 1, d), (5, 0))
# el vértice de la propia polilínea no es una intersección
assert R.buscar("INT", (9.8, 0.2), 1, d) is None
assert cerca(R.buscar("NEA", (3, 0.4), 1, d), (3, 0))
assert cerca(R.buscar("ORI", (0.3, -0.2), 1, d), (0, 0))
# PER: el cursor sobre el objeto, el pie donde caiga (lejos del cursor)
assert cerca(R.buscar("PER", (10.2, 9), 1, d, previo=(20, 3)), (10, 3))
assert R.buscar("PER", (10.2, 9), 1, d) is None             # sin punto anterior

# círculo linealizado (así llegan los de IngeCAD): centro, cuadrantes, tangente
anillo = [(50 + 5 * math.cos(i * math.tau / 36), 20 + 5 * math.sin(i * math.tau / 36)) for i in range(36)]
anillo.append(anillo[0])
c = R.circulo_de_anillo(anillo)
assert c and cerca(c, (50, 20, 5)[:2], 1e-6) and abs(c[2] - 5) < 1e-6
assert R.circulo_de_anillo([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]) is None
dc = R.Datos(arcos=[(50, 20, 5, 0.0, math.tau, True, 7)])
assert cerca(R.buscar("CEN", (50.5, 20.4), 1, dc), (50, 20))
assert cerca(R.buscar("QUA", (50.2, 25.3), 1, dc), (50, 25))
t = R.buscar("TAN", (53, 24), 1, dc, previo=(60, 20))
assert t is not None and abs(math.dist(t, (50, 20)) - 5) < 1e-9
# el radio por el punto de tangencia es perpendicular a la tangente
assert abs((t[0] - 50) * (t[0] - 60) + (t[1] - 20) * (t[1] - 20)) < 1e-9
assert cerca(R.buscar("NEA", (56, 20), 1.5, dc), (55, 20))
# recta que cruza el círculo
dc.segs.append((40, 20, 60, 20, 8))
assert cerca(R.buscar("INT", (54.8, 20.3), 1, dc), (55, 20))

# arco por tres puntos (CircularString): antihorario aunque venga al revés
a = R.arco_de_tres((10, 0), (0, 10), (-10, 0))
assert cerca(a[:3], (0, 0, 10)[:2]) and abs(a[2] - 10) < 1e-9 and abs(a[3]) < 1e-9 and abs(a[4] - math.pi) < 1e-9
b = R.arco_de_tres((-10, 0), (0, 10), (10, 0))
assert abs(b[3]) < 1e-9 and abs(b[4] - math.pi) < 1e-9
assert R.arco_de_tres((0, 0), (1, 1), (2, 2)) is None
da = R.Datos(arcos=[(0, 0, 10, a[3], a[4], False, 3)])
assert cerca(R.buscar("MID", (0.3, 9.6), 1, da), (0, 10))
assert cerca(R.buscar("END", (9.6, 0.3), 1, da), (10, 0))
assert R.buscar("QUA", (0.2, -9.8), 1, da) is None          # el arco no llega abajo

# Geometric Center: el del área, no el promedio de los vértices (lote en L)
L = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]
g = R.centroide(L)
assert cerca(g, (19 / 14, 19 / 14), 1e-9)
assert not cerca(g, (sum(x for x, _ in L) / 6, sum(y for _, y in L) / 6), 1e-3)
assert cerca(R.buscar("GCE", (1.5, 1.2), 1, R.Datos(centros=[g])), g)
assert cerca(R.buscar("NOD", (3.1, 2.9), 1, R.Datos(nodos=[(3, 3)])), (3, 3))
assert cerca(R.buscar("INS", (3.1, 2.9), 1, R.Datos(inserciones=[(3, 3)])), (3, 3))

# Extension: se adquiere la punta y se sigue la prolongación
de = R.Datos(segs=[(0, 0, 10, 0, 1)])
f = R.fuente_extension((10.2, 0.3), 1, de)
assert f == ((10, 0), (1.0, 0.0))
assert cerca(R.sobre_extension((17, 0.4), 1, [f]), (17, 0))
assert R.sobre_extension((5, 0.4), 1, [f]) is None          # para atrás no
# Parallel: la dirección de un tramo, por el punto anterior
dp = R.direccion_de_tramo((5, 0.2), 1, de)
assert dp == (1.0, 0.0)
assert cerca(R.sobre_paralela((8, 5.3), 1, (2, 5), [dp]), (8, 5))
assert R.sobre_paralela((8, 9), 1, (2, 5), [dp]) is None

# From y Mid Between 2 Points
assert cerca(R.medio((0, 0), (10, 4)), (5, 2))
assert cerca(R.desplazamiento("@3,4", (10, 10)), (13, 14))
assert cerca(R.desplazamiento("3,-4", (10, 10)), (13, 6))
assert cerca(R.desplazamiento("@2,5;-1,5", (0, 0)), (2.5, -1.5))
assert cerca(R.desplazamiento("@10<90", (1, 1)), (1, 11))
assert cerca(R.desplazamiento("@ 5 < 180", (0, 0)), (-5, 0))
for malo in ("", "@", "abc", "@1,2,3", "@1<"):
    assert R.desplazamiento(malo, (0, 0)) is None, malo


# ================================================================ en QGIS de verdad
def ramas_qgis():
    """Las ramas del QGIS de Flatpak instaladas (stable = 4.x, lts = 3.28)."""
    if not shutil.which("flatpak"):
        return []
    return [rama for rama in ("stable", "lts")
            if subprocess.run(["flatpak", "info", f"org.qgis.qgis//{rama}"],
                              capture_output=True, text=True).returncode == 0]

CARGA = r'''
import json, sys, math
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
                       QgsPointXY, QgsRectangle, Qgis)
from qgis.gui import (QgsMapCanvas, QgsMapToolDigitizeFeature, QgsAdvancedDigitizingDockWidget,
                      QgsMapToolCapture, QgsMapToolPan)
from qgis.PyQt.QtCore import Qt, QEvent, QPointF, QPoint
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QMainWindow
app = QgsApplication([], True); app.initQgis()
from geocad import referencias_qgis as RQ
out = {"version": Qgis.QGIS_VERSION}

def en(owner, scope, member):
    sc = getattr(owner, scope, None)
    return getattr(sc, member) if sc is not None and hasattr(sc, member) else getattr(owner, member)

win = QMainWindow()
canvas = QgsMapCanvas(win); win.setCentralWidget(canvas)
win.resize(800, 600); win.show()
base = QgsVectorLayer("LineString?crs=EPSG:22185", "base", "memory")
f = QgsFeature(); f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(100, 0)]))
base.dataProvider().addFeatures([f])
circ = QgsFeature(); circ.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(200, 50)).buffer(20, 16))
pol = QgsVectorLayer("Polygon?crs=EPSG:22185", "pol", "memory"); pol.dataProvider().addFeatures([circ])
nueva = QgsVectorLayer("LineString?crs=EPSG:22185", "nueva", "memory")
QgsProject.instance().addMapLayers([base, pol, nueva])
canvas.setDestinationCrs(base.crs())
canvas.setLayers([nueva, base, pol])
canvas.setExtent(QgsRectangle(-20, -100, 260, 100))
canvas.refresh(); app.processEvents()
nueva.startEditing()
canvas.setCurrentLayer(nueva)

class Iface:
    def mapCanvas(self): return canvas
    def mainWindow(self): return win

cad = QgsAdvancedDigitizingDockWidget(canvas)
tool = QgsMapToolDigitizeFeature(canvas, cad, en(QgsMapToolCapture, "CaptureMode", "CaptureLine"))
tool.setLayer(nueva)
canvas.setMapTool(tool)
ref = RQ.ReferenciasQgis(Iface())
menus = []
ref.menu = lambda gpos: menus.append(1)
vp = canvas.viewport()

def px(x, y):
    p = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
    return QPointF(p.x(), p.y())

def evento(tipo, pos, boton, mods):
    gl = vp.mapToGlobal(QPoint(int(pos.x()), int(pos.y())))
    botones = boton if tipo != en(QEvent, "Type", "MouseButtonRelease") else en(Qt, "MouseButton", "NoButton")
    return QMouseEvent(tipo, pos, QPointF(gl), boton, botones, mods)

PRESS, RELEASE, MOVE = (en(QEvent, "Type", n) for n in ("MouseButtonPress", "MouseButtonRelease", "MouseMove"))
IZQ, DER, NADA = (en(Qt, "MouseButton", n) for n in ("LeftButton", "RightButton", "NoButton"))
SHIFT, SIN = en(Qt, "KeyboardModifier", "ShiftModifier"), en(Qt, "KeyboardModifier", "NoModifier")

def clic(x, y, boton=IZQ, mods=SIN):
    p = px(x, y)
    app.sendEvent(vp, evento(MOVE, p, NADA, mods))
    app.sendEvent(vp, evento(PRESS, p, boton, mods))
    app.sendEvent(vp, evento(RELEASE, p, boton, mods))
    for _ in range(3):
        app.processEvents()

def puntos():
    return [(round(p.x(), 6), round(p.y(), 6)) for p in tool.points()]

# Shift + clic derecho con la herramienta de QGIS: el menú, y QGIS no termina la línea
clic(10, 30)
out["primero"] = puntos()
clic(40, 60, DER, SHIFT)
out["menu"] = len(menus)
out["sigue"] = tool.isCapturing() and len(puntos()) == 1
# Perpendicular desde el primer punto a la línea de base (el pie lejos del cursor)
ref.elegir("PER"); clic(60, 0.8)
out["per"] = puntos()[-1]
# Midpoint: el clic cerca del medio de la línea de base agrega el medio exacto
ref.elegir("MID")
clic(51.3, 1.2)
out["mid"] = puntos()[-1]
out["una_vez"] = ref.modo is None
# Center del círculo (polígono linealizado) y Quadrant
ref.elegir("CEN"); clic(201, 51)
out["cen"] = puntos()[-1]
ref.elegir("QUA"); clic(200.5, 69.0)
out["qua"] = puntos()[-1]
# sin nada cerca: no agrega y la referencia sigue esperando; Esc la cancela
n = len(puntos())
ref.elegir("END"); clic(150, -80)
out["nada"] = len(puntos()) == n and ref.modo == "END"
from qgis.PyQt.QtGui import QKeyEvent
app.sendEvent(canvas, QKeyEvent(en(QEvent, "Type", "KeyPress"), en(Qt, "Key", "Key_Escape"), SIN))
out["esc"] = ref.modo is None and len(puntos()) == n and tool.isCapturing()
# From: punto base (con el enganche de QGIS a vértices) + desplazamiento
from qgis.core import QgsSnappingConfig, QgsTolerance
cfg = QgsSnappingConfig(QgsProject.instance())
cfg.setEnabled(True)
cfg.setMode(en(QgsSnappingConfig, "SnappingMode", "AllLayers"))
cfg.setTypeFlag(en(Qgis, "SnappingType", "Vertex") if hasattr(Qgis, "SnappingType")
                else en(QgsSnappingConfig, "SnappingTypes", "VertexFlag"))
cfg.setTolerance(12)
cfg.setUnits(en(Qgis, "MapToolUnit", "Pixels") if hasattr(Qgis, "MapToolUnit") else QgsTolerance.Pixels)
QgsProject.instance().setSnappingConfig(cfg)
canvas.snappingUtils().setConfig(cfg)
import qgis.PyQt.QtWidgets as W
RQ.QInputDialog.getText = staticmethod(lambda *a, **k: ("@5,-3", True))
ref.elegir("FROM"); clic(100.4, 0.3)
out["from"] = puntos()[-1]
# Mid Between 2 Points
ref.elegir("M2P"); clic(0, 0); clic(100, 0)
out["m2p"] = puntos()[-1]
# un comando de Dibujo de GeoCAD que pide un punto (LINEA): el mismo menú
from qgis.gui import QgsMapTool
class Cmd:
    def base(self): return QgsPointXY(0, 50)
    def snap_points(self): return [QgsPointXY(0, 50)]
class Mgr:
    def __init__(self): self.command, self.lastpoint, self.puntos = Cmd(), QgsPointXY(0, 50), []
    def point_clicked(self, pt, snapped, shift): self.puntos.append([round(pt.x(), 6), round(pt.y(), 6), snapped])
class Herr(QgsMapTool):
    def __init__(self, c, mgr):
        super().__init__(c); self.mgr, self.derechos = mgr, 0
    def canvasReleaseEvent(self, ev):
        if ev.button() == DER: self.derechos += 1      # clic derecho = Enter en Dibujo
mgr = Mgr(); herr = Herr(canvas, mgr)
canvas.setMapTool(herr); menus.clear()
clic(40, 60, DER, SHIFT)
out["dib_menu"] = [len(menus), herr.derechos]
ref.elegir("PER"); clic(60, 0.8)
ref.elegir("MID"); clic(51, 1)
ref.elegir("NON"); clic(30, 30)
out["dib"] = mgr.puntos
mgr.command = None                                     # sin comando: Mayús + clic derecho = Enter
clic(40, 60, DER, SHIFT)
out["dib_sin"] = [len(menus), herr.derechos]
# fuera de la digitalización: Shift + clic derecho no se toca
canvas.setMapTool(QgsMapToolPan(canvas))
menus.clear()
clic(40, 60, DER, SHIFT)
out["otra"] = len(menus)
ref.unload()
json.dump(out, open(sys.argv[2], "w"))
'''

for rama in ramas_qgis():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "carga.py").write_text(CARGA, encoding="utf-8")
    env = {"HOME": HOME, "PATH": "/usr/bin:/bin"}
    for k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    r = subprocess.run(["flatpak", "run", f"--filesystem={RAIZ}:ro", f"--filesystem={tmp}",
                        "--command=python3", "--env=QT_QPA_PLATFORM=offscreen",
                        *(["--env=LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6"] if rama == "lts" else []),
                        f"--env=PYTHONPATH=/app/share/qgis/python:{RAIZ / 'QGIS' / 'codigo'}",
                        f"org.qgis.qgis//{rama}", str(tmp / "carga.py"), "-", str(tmp / "salida.json")],
                       capture_output=True, text=True, env=env, timeout=300)
    assert (tmp / "salida.json").exists(), r.stderr[-3000:]
    out = json.loads((tmp / "salida.json").read_text())
    shutil.rmtree(tmp, ignore_errors=True)
    assert out["menu"] == 1 and out["sigue"], out
    assert out["mid"] == [50, 0], out
    assert out["una_vez"], out
    assert math.dist(out["cen"], (200, 50)) < 1e-6, out
    assert math.dist(out["qua"], (200, 70)) < 1e-6, out
    assert out["per"] == [out["primero"][0][0], 0], out     # el pie, con la x del primero
    assert out["nada"] and out["esc"], out
    assert out["from"] == [105, -3], out
    assert out["m2p"] == [50, 0], out
    assert out["otra"] == 0, out
    assert out["dib_menu"] == [1, 0] and out["dib_sin"] == [1, 1], out
    assert out["dib"][0] == [0, 0, True] and out["dib"][1] == [50, 0, True], out
    assert out["dib"][2][2] is False, out                # None: sin enganche
    print("  QGIS %s: Shift + clic derecho, MID, CEN, QUA, PER, From y M2P en QGIS y en Dibujo"
          % out["version"])
if not ramas_qgis():
    print("  (QGIS de Flatpak no instalado: sólo las cuentas)")
print("TODO OK: referencias con Shift + clic derecho en QGIS")
