"""Tablas en QGIS (3.23.0): Pegar tabla en las composiciones. Dos puntos
(la esquina inferior derecha en el cursor) y una tabla manual nativa de
QGIS con el formato de la planilla. Las cuentas se prueban sin QGIS; si el
QGIS de Flatpak está instalado, además se arma la tabla en una composición
de verdad (sin ventanas) y se mide dibujada."""
import os, sys, tempfile, subprocess, shutil, json
os.environ["HOME"] = HOME = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
from geocad import pegartabla as QP, tablas as T, modulos

assert (RAIZ / "QGIS" / "codigo" / "geocad" / "tablas.py").read_bytes() == \
    (RAIZ / "COMUN" / "nucleo" / "tablas.py").read_bytes()
assert QP.ICONO.is_file()
# el módulo «Tablas» se elige también en QGIS (activo por defecto)
assert "tablas" in [m.clave for m in modulos.catalogo("qgis")]
assert modulos.activo("qgis", "tablas")

KEY = "1234567890123456789"
HTML = ('<google-sheets-html-origin><table data-copy-id="x"><colgroup><col width="100"><col width="60">'
        '<col width="80"></colgroup>'
        '<tr style="height:24px"><td colspan="2" style="font-family:Arial;font-size:11pt;font-weight:bold;'
        'color:#c00000;text-align:center;border:1px solid #000000">CUADRO</td>'
        '<td style="font-family:Arial;font-size:10pt;font-style:italic;border:1px solid #000000">Obs.</td></tr>'
        '<tr style="height:20px"><td style="font-family:Arial;font-size:10pt;background-color:#ddebf7;'
        'border:1px solid #000000">key</td><td style="font-family:Arial;font-size:10pt;'
        'border:1px solid #000000">name</td><td style="border:1px solid #000000"></td></tr>'
        '<tr style="height:20px"><td style="font-family:Arial;font-size:10pt;border:1px solid #000000">'
        + KEY + '</td><td style="font-family:Arial;font-size:10pt;text-align:right;'
        'border:1px solid #000000">452,37</td><td style="border:1px solid #000000">x</td></tr></table>')
TXT = "CUADRO\t\tObs.\nkey\tname\t\n" + KEY + "\t452,37\tx"
t = T.leer(HTML, TXT)
assert t is not None and t.con_formato and t.origen == "genoffice"

# ================================================================ los dos puntos
assert QP.ventana((10, 20), (110, 70), 50.0, 25.0) == ((10.0, 20.0), 2.0, 2.0)
# hacia arriba y a la izquierda: la esquina superior izquierda es la menor
assert QP.ventana((110, 70), (10, 20), 50.0, 25.0) == ((10.0, 20.0), 2.0, 2.0)
# sin alto: la escala del ancho; sin nada: tamaño natural
assert QP.ventana((10, 20), (60, 20), 50.0, 25.0) == ((10.0, 20.0), 1.0, 1.0)
assert QP.ventana((10, 20), (110, 20), 50.0, 25.0) == ((10.0, 20.0), 2.0, 2.0)
assert QP.ventana((10, 20), (10, 20), 50.0, 25.0) == ((10.0, 20.0), 1.0, 1.0)

# ================================================================ el plan de la tabla de QGIS
opciones = {"respetar": True, "encabezado": True, "alto": 2.5, "quitar": []}
tt, a = QP.preparar(t, opciones)
assert len(a.xs) == 4 and len(a.ys) == 4 and a.xs[0] == 0.0 and a.ys[0] == 0.0
assert {(x.fila, x.col) for x in a.textos} >= {(0, 0), (0, 2), (2, 0)}
p = QP.plan(tt, a)
assert (p["n_filas"], p["n_cols"]) == (3, 3)
# QGIS: total = suma (ancho + 2 márgenes) + (n + 1) grillas -> llena justo el ancho del armado
tot_w = sum(w + 2 * p["margen"] for w in p["anchos"]) + (p["n_cols"] + 1) * p["grilla"]
tot_h = sum(h + 2 * p["margen"] for h in p["altos"]) + (p["n_filas"] + 1) * p["grilla"]
assert abs(tot_w - a.ancho_mm) < 1e-9 and abs(tot_h - a.alto_mm) < 1e-9, (tot_w, a.ancho_mm)
assert p["grilla"] > 0 and p["color_grilla"] == "#000000"
celda = {(d["fila"], d["col"]): d for d in p["celdas"]}
tit = celda[(0, 0)]
assert (tit["cols"], tit["negrita"], tit["color"], tit["alin_h"]) == (2, True, "#c00000", "centro")
assert abs(tit["pt"] - 11.0) < 1e-9                      # 11 pt de la planilla, sin escalar
assert celda[(0, 2)]["cursiva"] and celda[(1, 0)]["fondo"] == "#ddebf7"
assert celda[(2, 1)]["alin_h"] == "derecha" and celda[(2, 0)]["alin_h"] == "derecha"   # número
# llenando un rectángulo 2 x 1,5: anchos y altos se estiran, la letra toma la menor
p2 = QP.plan(tt, a, 2.0, 1.5)
tot_w2 = sum(w + 2 * p2["margen"] for w in p2["anchos"]) + (p2["n_cols"] + 1) * p2["grilla"]
tot_h2 = sum(h + 2 * p2["margen"] for h in p2["altos"]) + (p2["n_filas"] + 1) * p2["grilla"]
assert abs(tot_w2 - 2 * a.ancho_mm) < 1e-9 and abs(tot_h2 - 1.5 * a.alto_mm) < 1e-9
assert abs({(d["fila"], d["col"]): d for d in p2["celdas"]}[(0, 0)]["pt"] - 16.5) < 1e-9
assert (p2["ancho_mm"], p2["alto_mm"]) == (2 * a.ancho_mm, 1.5 * a.alto_mm)
# la vista previa: las líneas en la composición (y hacia abajo)
segs = QP.segmentos(a, (100.0, 50.0), 1.0, 1.0)
xs_ = [q[0] for s in segs for q in s]; ys_ = [q[1] for s in segs for q in s]
assert abs(min(xs_) - 100) < 1e-9 and abs(max(xs_) - (100 + a.ancho_mm)) < 1e-9
assert abs(min(ys_) - 50) < 1e-9 and abs(max(ys_) - (50 + a.alto_mm)) < 1e-9
# sin formato (estilo GeoCAD): sin fondos, grilla de 0,25 mm, encabezado en negrita
tg, ag = QP.preparar(t, {"respetar": False, "encabezado": True, "alto": 3.0})
pg = QP.plan(tg, ag, respetar_formato=False)
assert abs(pg["grilla"] - 0.25) < 1e-9 and not [d for d in pg["celdas"] if d["fondo"]]
# quitar columnas
tq, aq = QP.preparar(t, {"respetar": True, "quitar": [2]})
assert len(aq.xs) == 3

# ================================================================ en QGIS de verdad (Flatpak, sin ventanas)
def ramas_qgis():
    """Las ramas del QGIS de Flatpak instaladas (stable = 4.x, lts = 3.28)."""
    if not shutil.which("flatpak"):
        return []
    return [rama for rama in ("stable", "lts")
            if subprocess.run(["flatpak", "info", f"org.qgis.qgis//{rama}"],
                              capture_output=True, text=True).returncode == 0]

CARGA = r'''
import json, sys
from qgis.core import QgsApplication, QgsPrintLayout, QgsProject, QgsLayoutExporter, QgsLayoutFrame
from qgis.PyQt.QtGui import QColor
app = QgsApplication([], False); app.initQgis()
from geocad import pegartabla as QP, tablas as T
datos = json.load(open(sys.argv[1]))
from qgis.core import Qgis
out = {"version": Qgis.QGIS_VERSION}
t = T.leer(datos["html"], datos["txt"])
tt, a = QP.preparar(t, {"respetar": True, "encabezado": True}, QP.medidor())
med = QP.medidor()
out["entra"] = all(med(x.texto, x.alto_mm, x.negrita, x.cursiva, x.fuente) <= x.ancho_mm + 1e-6
                   for x in a.textos)
lay = QgsPrintLayout(QgsProject.instance()); lay.initializeDefaults()

def medir_dibujo():
    img = QgsLayoutExporter(lay).renderPageToImage(0, dpi=254)        # 10 px por mm
    w, h = img.width(), img.height()
    oscuro = lambda x, y: QColor(img.pixel(x, y)).value() < 90
    filas = [y for y in range(0, h, 1) if any(oscuro(x, y) for x in range(0, w, 3))]
    cols = [x for x in range(0, w, 1) if any(oscuro(x, y) for y in range(0, h, 3))]
    return (min(cols) / 10, min(filas) / 10, (max(cols) + 1) / 10, (max(filas) + 1) / 10)

n0 = len(lay.multiFrames())
tabla, marco = QP.crear_tabla(lay, QP.plan(tt, a), (20.0, 30.0), "Tabla de prueba", t.origen)
out["natural"] = [a.ancho_mm, a.alto_mm, list(medir_dibujo())]
c = tabla.tableContents()
out["span"] = [c[0][0].columnSpan(), c[0][0].rowSpan()] if hasattr(c[0][0], "columnSpan") else None
out["fondo"] = c[1][0].backgroundColor().name()
out["negrita"] = c[0][0].textFormat().font().bold()
out["prop"] = tabla.customProperty(QP.PROPIEDAD)
out["id"] = marco.id()
marcos = lambda: len([i for i in lay.items() if isinstance(i, QgsLayoutFrame)])
lay.undoStack().stack().undo()
d1 = marcos()
lay.undoStack().stack().redo()
d2 = marcos()
lay.undoStack().stack().undo()
out["deshacer"] = [d1, d2, marcos(), sum(len(m.frames()) for m in lay.multiFrames())]
# la herramienta de dos puntos sobre la vista de la composición
from qgis.gui import QgsLayoutView
vista = QgsLayoutView(); vista.setCurrentLayout(lay)
avisos = []
h = QP.herramienta(vista, tt, a, {"respetar": True}, avisar=avisos.append)
vista.setTool(h)
h._previa((40.0, 50.0))
out["previa"] = h.vista is not None and h.vista.scene() is lay
h.p1 = (40.0, 50.0)
h.pegar(*QP.ventana(h.p1, (40.0 + 2 * a.ancho_mm, 50.0 + 1.5 * a.alto_mm), a.ancho_mm, a.alto_mm))
out["previa_borrada"] = h.vista is None
# 3.23.1: después de pegar la herramienta se suelta (antes cada clic pegaba otra tabla)
out["suelta"] = [h.terminado, vista.tool() is not h, type(vista.tool()).__name__]
out["ventana"] = [2 * a.ancho_mm, 1.5 * a.alto_mm, list(medir_dibujo())]
out["avisos"] = avisos
json.dump(out, open(sys.argv[2], "w"))
app.exitQgis()
'''

for rama in ramas_qgis():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "carga.py").write_text(CARGA, encoding="utf-8")
    (tmp / "datos.json").write_text(json.dumps({"html": HTML, "txt": TXT}), encoding="utf-8")
    env = {"HOME": HOME, "PATH": "/usr/bin:/bin"}
    for k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    r = subprocess.run(["flatpak", "run", f"--filesystem={RAIZ}:ro", f"--filesystem={tmp}",
                        "--command=python3", "--env=QT_QPA_PLATFORM=offscreen",
                        # la 3.28 LTS no carga su Python afuera de QGIS sin esto (static TLS)
                        *(["--env=LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6"] if rama == "lts" else []),
                        f"--env=PYTHONPATH=/app/share/qgis/python:{RAIZ / 'QGIS' / 'codigo'}",
                        f"org.qgis.qgis//{rama}", str(tmp / "carga.py"), str(tmp / "datos.json"),
                        str(tmp / "salida.json")], capture_output=True, text=True, env=env, timeout=300)
    assert (tmp / "salida.json").exists(), r.stderr[-2000:]
    out = json.loads((tmp / "salida.json").read_text())
    assert out["entra"], "cada texto entra en su celda con la fuente de QGIS"
    W, H, (x0, y0, x1, y1) = out["natural"]
    # dibujada: la esquina en el punto y el tamaño del armado (+- la mitad de la grilla)
    assert abs(x0 - 20.0) < 0.3 and abs(y0 - 30.0) < 0.3, out["natural"]
    assert abs((x1 - x0) - W) < 0.3 and abs((y1 - y0) - H) < 0.3, out["natural"]
    W2, H2, (x0, y0, x1, y1) = out["ventana"]
    assert abs(x0 - 40.0) < 0.3 and abs(y0 - 50.0) < 0.3, out["ventana"]
    assert abs((x1 - x0) - W2) < 0.3 and abs((y1 - y0) - H2) < 0.3, out["ventana"]
    assert out["span"] in ([2, 1], None) and out["fondo"] == "#ddebf7" and out["negrita"]
    assert out["prop"] == "genoffice" and out["id"] == "Tabla de prueba"
    # Ctrl+Z la quita entera (no queda ningún marco a la vista) y Ctrl+Mayús+Z la vuelve
    assert out["deshacer"] == [0, 1, 0, 0], out["deshacer"]
    assert out["previa"] and out["previa_borrada"]
    assert out["suelta"] == [True, True, "QgsLayoutViewToolSelect"], out["suelta"]
    assert out["avisos"] and "pegada" in out["avisos"][-1]
    print("  QGIS %s: tabla de %.1f × %.1f mm dibujada en su lugar; llenando la ventana, %.1f × %.1f mm%s"
          % (out["version"], W, H, W2, H2, "" if out["span"] else " (sin combinar celdas)"))
if not ramas_qgis():
    print("  (QGIS de Flatpak no instalado: sólo las cuentas)")
print("TODO OK: tablas en las composiciones de QGIS")
