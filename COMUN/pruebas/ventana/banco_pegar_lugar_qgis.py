"""Banco con el QGIS REAL (sin pantalla): PEGAR EN EL LUGAR (3.66.0, PEGARORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «copiar en una las entidades seleccionadas y pegarlas en
la otra»; «... y lo mismo en QGIS»; «ESO ES PEGAR EN EL LUGAR»; «CTRL+ALT+V»;
«si no está configurado el sistema de representación de coordenadas, esta
acción va a crear el mismo de forma automática».

Comprueba: «Pegar en el lugar» en Edición justo debajo de «Pegar objetos
espaciales», con Ctrl+Alt+V; el Ctrl+C de QGIS deja lo suyo y además el
mensaje para IngeCAD (capa CAD, color, tipo, grosor, sistema); pegar lo
copiado en IngeCAD en la capa activa: mismas coordenadas, LAYER_CODE y
CAD_COLOR / CAD_LTYPE / CAD_LW, capas CAD nuevas con su color en Yaguá Capas,
la capa entra en edición, lo de otro tipo se cuenta; el proyecto sin sistema
toma el del dibujo; capa en otro sistema: reproyectado; capa multi; módulo
apagado: sin el ítem.

Se corre como banco_botones_qgis.py; con una carpeta como argumento deja ahí
desde_qgis.json (para el banco de IngeCAD) y pega desde_ingecad.json si está.
Termina en «TODO OK».
"""
import os, sys, json, tempfile, faulthandler
faulthandler.dump_traceback_later(180, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
CARPETA = sys.argv[1] if len(sys.argv) > 1 else None
from pathlib import Path
from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                       QgsVectorLayer)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QMimeData
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QAction, QApplication, QMainWindow, QMenu

iface = get_iface()
win = QMainWindow()
canvas = QgsMapCanvas(win)
win.setCentralWidget(canvas)
win.show()
iface.mainWindow.return_value = win
iface.mapCanvas.return_value = canvas
editar = QMenu("Edición", win)
a_copiar = QAction("Copiar objetos espaciales", win)
a_pegar = QAction("Pegar objetos espaciales", win)
a_pegar.setShortcut(QKeySequence("Ctrl+V"))
for a in (QAction("Cortar objetos espaciales", win), a_copiar, a_pegar, QAction("Borrar", win)):
    editar.addAction(a)
iface.editMenu.return_value = editar
iface.actionCopyFeatures.return_value = a_copiar
iface.actionPasteFeatures.return_value = a_pegar
mensajes = []
iface.messageBar.return_value.pushMessage.side_effect = lambda *a, **k: mensajes.append(a[1])

fallas = []


def comprobar(cond, texto):
    print(("ok   " if cond else "MAL  ") + texto)
    if not cond:
        fallas.append(texto)


def eventos():
    for _ in range(5):
        QApplication.processEvents()


from geocad import modulos, pegar_lugar as PL
from geocad.pegar_lugar_qgis import PegarLugarQgis, PROP_KEY
modulos.guardar("qgis", {"pegar_lugar": True})
P = PegarLugarQgis(iface)

# ---- 1. Edición > Pegar en el lugar, debajo de Pegar objetos espaciales ----------------------
acc = editar.actions()
comprobar(acc.index(P.accion) == acc.index(a_pegar) + 1,
          "debajo de «Pegar objetos espaciales» (%s)" % [a.text() for a in acc])
comprobar(P.accion.text() == "Pegar en el lugar" and P.accion.shortcut() == QKeySequence("Ctrl+Alt+V"),
          "«Pegar en el lugar» con Ctrl+Alt+V")

# ---- 2. Ctrl+C de QGIS: lo suyo y el mensaje para IngeCAD ----------------------------------
QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:22197"))
obra = QgsVectorLayer("LineString?crs=EPSG:22197&field=id:integer&field=LAYER_CODE:string(50)"
                      "&field=CAD_COLOR:string(20)&field=CAD_LW:double", "Obra", "memory")
QgsProject.instance().addMapLayer(obra)
obra.setCustomProperty(PROP_KEY, json.dumps({"layers": [
    {"name": "Muros", "color": {"aci": 1, "rgb": None}, "linetype": "DASHED", "lineweight": 0.35},
    {"name": "Ejes", "color": {"aci": None, "rgb": "#a0b0c0"}, "linetype": "Continuous", "lineweight": -1}],
    "current": "0"}))
for i, (capa, color, lw) in enumerate((("Muros", None, None), ("Ejes", "#00ff00", 0.5), (None, None, None))):
    f = QgsFeature(obra.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5600000 + i, 7000000), QgsPointXY(5600010 + i, 7000005)]))
    f.setAttributes([i, capa, color, lw])
    obra.dataProvider().addFeatures([f])
obra.selectAll()
iface.activeLayer.return_value = obra


def copia_de_ingecad(mensaje):          # lo que dejan IngeCAD y GeoCAD al copiar allá
    m = QMimeData()
    m.setData("application/x-ingecad-clip-id", b"banco:1")
    QApplication.clipboard().setMimeData(m)
    assert PL.dejar_copia(mensaje, m, "application/x-ingecad-clip-id")


def copia_de_qgis():                    # lo que hace QGIS con su Ctrl+C (va primero)
    m = QMimeData()
    m.setText("wkt_geom\tid\nLineString (...)\t0")
    QApplication.clipboard().setMimeData(m)


a_copiar.triggered.disconnect()
a_copiar.triggered.connect(copia_de_qgis)
a_copiar.triggered.connect(P._al_copiar)
a_copiar.trigger()
eventos()
data = QApplication.clipboard().mimeData()
comprobar(data.hasText() and data.text().startswith("wkt_geom"), "la copia de QGIS sigue igual")
msg = PL.leer_copia(data)
comprobar(msg is not None, "y además el mensaje para IngeCAD, sin tocar el portapapeles")
comprobar(data.formats() == ["text/plain"], "el portapapeles, sólo lo de QGIS (%s)" % data.formats())
comprobar(msg["origen"] == "qgis" and msg["crs"] == "EPSG:22197" and len(msg["objetos"]) == 3,
          "3 objetos en EPSG:22197 (%s)" % msg["crs"])
o = {x["capa"]: x for x in msg["objetos"]}         # el orden de la selección no es fijo
comprobar(o["Muros"]["color"] is None and o["Muros"]["wkt"].startswith("LineString (5600000 7000000"),
          "Muros PorCapa, en sus coordenadas (%s)" % o["Muros"]["wkt"][:40])
comprobar(o["Ejes"]["color"] == "#00ff00" and o["Ejes"]["aci"] == 3 and o["Ejes"]["grosor"] == 0.5,
          "Ejes verde propio (ACI 3), 0.5 mm")
comprobar("Obra" in o and o["Obra"]["wkt"].startswith("LineString (5600002 7000000"),
          "sin LAYER_CODE: la capa CAD es la capa de QGIS")
comprobar(msg["capas"]["Muros"] == {"color": "#ff0000", "aci": 1, "tipo_linea": "DASHED", "grosor": 0.35},
          "capa Muros con el aspecto de Yaguá Capas (%s)" % msg["capas"]["Muros"])
if CARPETA:
    Path(CARPETA, "desde_qgis.json").write_text(json.dumps(msg), encoding="utf-8")

# ---- 3. pegar lo de IngeCAD: proyecto sin sistema, capa sin campos ---------------------------
entrada = Path(CARPETA, "desde_ingecad.json") if CARPETA else None
de_ingecad = entrada.read_bytes() if entrada is not None and entrada.exists() else None
crs_ingecad = "EPSG:22197"
fabricado = PL.empaquetar("ingecad", crs_ingecad, [
    {"wkt": "LINESTRING (5500000 6900000,5500010 6900000,5500010 6900010)", "capa": "Muros",
     "color": None, "aci": None, "tipo_linea": None, "grosor": None},
    {"wkt": "LINESTRING (5500001 6900001,5500002 6900002)", "capa": "Ejes", "color": "#0000ff",
     "aci": 5, "tipo_linea": "CENTER", "grosor": 0.25},
    {"wkt": "POLYGON ((5500020 6900020,5500023 6900020,5500023 6900023,5500020 6900020))",
     "capa": "Muros", "color": None, "aci": None, "tipo_linea": None, "grosor": None}],
    {"Muros": {"color": "#ff0000", "aci": 1, "tipo_linea": "DASHED", "grosor": 0.35},
     "Ejes": {"color": "#ffffff", "aci": 7, "tipo_linea": "Continuous", "grosor": -1.0}},
    {"texto(s)": 1})
QgsProject.instance().setCrs(QgsCoordinateReferenceSystem())
destino = QgsVectorLayer("LineString?crs=EPSG:22197", "Destino", "memory")
QgsProject.instance().addMapLayer(destino)
iface.activeLayer.return_value = destino
copia_de_ingecad(fabricado)
mensajes.clear()
texto = P.pegar()
comprobar(texto.startswith("Pegado en el lugar"), texto)
comprobar(QgsProject.instance().crs().authid() == crs_ingecad,
          "el proyecto sin sistema toma el del dibujo (%s)" % QgsProject.instance().crs().authid())
comprobar(destino.isEditable(), "la capa entró en edición")
feats = list(destino.getFeatures())
comprobar(len(feats) == 3, "2 líneas y el contorno del polígono (%d)" % len(feats))
comprobar("1 cerrado(s), como contorno" in texto and "1 texto(s)" in texto, "el contorno y los textos se cuentan")
comprobar(sum(f.geometry().asPolyline()[0] == f.geometry().asPolyline()[-1] for f in feats) == 1,
          "el contorno queda cerrado")
f0 = next(f for f in feats if f["LAYER_CODE"] == "Muros")
comprobar([(p.x(), p.y()) for p in f0.geometry().asPolyline()] ==
          [(5500000, 6900000), (5500010, 6900000), (5500010, 6900010)], "en sus mismas coordenadas")
f1 = next(f for f in feats if f["LAYER_CODE"] == "Ejes")
comprobar(f1["CAD_COLOR"] == "#0000ff" and f1["CAD_LTYPE"] == "CENTER" and abs(f1["CAD_LW"] - 0.25) < 1e-9,
          "Ejes con su color, tipo y grosor propios")
cfg = json.loads(destino.customProperty(PROP_KEY) or "{}")
capas = {c["name"]: c for c in cfg.get("layers", [])}
comprobar(capas.get("Muros", {}).get("color") == {"aci": 1, "rgb": None} and capas["Muros"]["linetype"] == "DASHED"
          and capas["Muros"]["lineweight"] == 0.35, "Yaguá Capas: Muros rojo, DASHED, 0.35 (%s)" % capas.get("Muros"))
comprobar("Ejes" in capas, "Yaguá Capas: Ejes")
destino.rollBack()

# ---- 4. capa en otro sistema: reproyectado; capa multi ---------------------------------------
geo = QgsVectorLayer("MultiLineString?crs=EPSG:4326", "Geo", "memory")
QgsProject.instance().addMapLayer(geo)
iface.activeLayer.return_value = geo
texto = P.pegar()
fs = list(geo.getFeatures())
comprobar(len(fs) == 3 and all(f.geometry().isMultipart() for f in fs), "capa multi: entra como multi (%s)" % texto)
pt = fs[0].geometry().asMultiPolyline()[0][0] if fs else None
comprobar(pt is not None and -80 < pt.x() < -50 and -45 < pt.y() < -20,
          "llevado a grados (EPSG:4326): %r" % ((pt and (round(pt.x(), 4), round(pt.y(), 4))),))
geo.rollBack()

# ---- 5. lo copiado de verdad en el banco de IngeCAD -----------------------------------------
if de_ingecad is not None:
    dm = PL.desempaquetar(de_ingecad)
    print("     (pega lo que copió el banco de IngeCAD: %s)" % PL.resumen(dm))
    copia_de_ingecad(de_ingecad)
    real = QgsVectorLayer("LineString?crs=EPSG:22197", "DeIngeCAD", "memory")
    QgsProject.instance().addMapLayer(real)
    iface.activeLayer.return_value = real
    texto = P.pegar()
    fs = list(real.getFeatures())
    # las líneas y el contorno de lo cerrado (3.66.3); el punto no va en una capa de líneas
    lineas = [x for x in dm["objetos"] if x["wkt"].upper().startswith(("LINESTRING", "POLYGON"))]
    comprobar(len(fs) == len(lineas) and len(fs) > 0, "lo de IngeCAD (%d): %s" % (len(fs), texto))
    if fs:
        linea = next(x for x in lineas if x["wkt"].upper().startswith("LINESTRING"))
        x0 = PL.partes_wkt(linea["wkt"])[1][0][0]
        con_x0 = [f for f in fs if (round(f.geometry().asPolyline()[0].x(), 6),
                                    round(f.geometry().asPolyline()[0].y(), 6)) == x0]
        comprobar(bool(con_x0), "en sus coordenadas de IngeCAD %s" % (x0,))
        comprobar(bool(con_x0) and con_x0[0]["LAYER_CODE"] == linea["capa"], "con su capa CAD %s" % linea["capa"])
    real.rollBack()

# ---- 6. sin nada de GeoCAD en el portapapeles; módulo apagado ---------------------------------
QApplication.clipboard().setText("hola")
texto = P.pegar()
comprobar("no tiene objetos copiados con GeoCAD" in texto, "portapapeles sin lo nuestro: lo dice")
P.unload()
eventos()
comprobar(P.accion not in editar.actions(), "apagado: sin el ítem en Edición")
print("TODO OK" if not fallas else "FALLAS: %s" % fallas)
sys.exit(1 if fallas else 0)
