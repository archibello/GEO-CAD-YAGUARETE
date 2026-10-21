"""Tablas de QGIS a IngeCAD (3.24.0). Copiar tabla en las composiciones de
QGIS: la tabla elegida (manual o de atributos) va al portapapeles con su
formato (HTML + texto) y PEGARTABLA la reconoce como «QGIS (composición)».
La escritura del HTML se prueba sin QGIS; si el QGIS de Flatpak está
instalado, además se copia una tabla manual y una de atributos de una
composición de verdad (sin ventanas) y se lee lo que quedó en el portapapeles."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, subprocess, shutil, json
os.environ["HOME"] = HOME = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
from geocad import pegartabla as QP, tablas as T

assert QP.ICONO_COPIAR.is_file()
for lado in ("QGIS", "INGECAD"):
    assert (RAIZ / lado / "codigo" / "geocad" / "tablas.py").read_bytes() == \
        (RAIZ / "COMUN" / "nucleo" / "tablas.py").read_bytes()

# ================================================================ HTML con formato, ida y vuelta
B = {lado: T.Borde(0.3, "#000000") for lado in T.LADOS}
celdas = [T.Celda(0, 0, "CUADRO & <x>", cols=2, negrita=True, tam_pt=11, fuente="Arial",
                  color="#c00000", alin_h="centro", bordes=dict(B), margen_mm=1.0),
          T.Celda(0, 2, "Obs.", cursiva=True, bordes=dict(B), margen_mm=1.0),
          T.Celda(1, 0, "1234567890123456789", fondo="#ddebf7", bordes=dict(B), margen_mm=1.0),
          T.Celda(1, 1, "452,37", alin_h="derecha", bordes=dict(B), margen_mm=1.0),
          T.Celda(1, 2, "dos\nrenglones", alin_v="arriba", bordes=dict(B), margen_mm=1.0)]
t = T.Tabla(celdas, 2, 3, [30.0, 20.0, 15.0], [6.0, 0.0], "qgis_composicion", "Arial", 10, True)
html, texto = T.a_html(t), T.a_texto(t)
assert T.GENERADOR in html and T.detectar(html, texto) == "qgis_composicion"
assert texto == "CUADRO & <x>\t\tObs.\n1234567890123456789\t452,37\tdos renglones", texto
u = T.leer(html, texto)
assert u.origen == "qgis_composicion" and u.con_formato
assert T.ORIGENES[u.origen] == "QGIS (composición)"
assert [round(w, 2) for w in u.anchos_mm] == [30.0, 20.0, 15.0]
assert [round(h, 2) for h in u.altos_mm] == [6.0, 0.0]
assert (u.fuente, u.tam_pt) == ("Arial", 10.0)
v = {(c.fila, c.col): c for c in u.celdas}
assert (v[0, 0].texto, v[0, 0].cols, v[0, 0].negrita, v[0, 0].color, v[0, 0].alin_h,
        v[0, 0].tam_pt) == ("CUADRO & <x>", 2, True, "#c00000", "centro", 11.0)
assert v[0, 2].cursiva and v[1, 0].fondo == "#ddebf7" and v[1, 1].alin_h == "derecha"
assert v[1, 2].texto == "dos\nrenglones" and v[1, 2].alin_v == "arriba"
assert all(abs(c.margen_mm - 1.0) < 1e-9 for c in u.celdas)
assert all(abs(c.bordes["arriba"].grosor_mm - 0.3) < 1e-9 for c in u.celdas)
# se arma como cualquier planilla (los anchos de la composición se respetan)
a = T.armar(u, True)
assert abs(a.xs[1] - a.xs[0] - 30.0) < 1e-6 or a.xs[1] - a.xs[0] > 30.0
# el texto solo (sin HTML) sigue siendo una tabla
assert T.leer("", texto).n_cols == 3
print("ok HTML con formato (ida y vuelta)")

# ================================================================ QGIS de verdad
def ramas_qgis():
    if not shutil.which("flatpak"):
        return []
    return [rama for rama in ("stable", "lts")
            if subprocess.run(["flatpak", "info", f"org.qgis.qgis//{rama}"],
                              capture_output=True, text=True).returncode == 0]

CARGA = r'''
import json, sys
from qgis.core import (QgsApplication, QgsPrintLayout, QgsProject, QgsVectorLayer, QgsFeature,
                       QgsLayoutItemAttributeTable, QgsLayoutFrame, Qgis)
from qgis.PyQt.QtCore import QRectF
app = QgsApplication([], False); app.initQgis()
from geocad import pegartabla as QP, tablas as T
datos = json.load(open(sys.argv[1]))
out = {"version": Qgis.QGIS_VERSION}
lay = QgsPrintLayout(QgsProject.instance()); lay.initializeDefaults()

# -- una tabla manual pegada de GenOffice, copiada de vuelta
t = T.leer(datos["html"], datos["txt"])
tt, a = QP.preparar(t, {"respetar": True, "encabezado": True}, QP.medidor())
p = QP.plan(tt, a)
manual, marco = QP.crear_tabla(lay, p, (20.0, 30.0))
lay.setSelectedItem(marco)
elegidas = QP.tablas_elegidas(lay)
out["elegidas"] = len(elegidas)
m = QP.tabla_de_elemento(elegidas[0])
QP.al_portapapeles(m)
html, txt, url = QP.leer_portapapeles()
r = T.leer(html, txt, url)
celda = {(c.fila, c.col): c for c in r.celdas}
out["manual"] = {"origen": r.origen, "dim": [r.n_filas, r.n_cols], "txt": txt,
                 "anchos": r.anchos_mm, "anchos_armado": [a.xs[i + 1] - a.xs[i] for i in range(len(a.xs) - 1)],
                 "negrita": celda[0, 0].negrita, "color": celda[0, 0].color,
                 "cols": celda[0, 0].cols, "fondo": celda[1, 0].fondo,
                 "alin": celda[2, 1].alin_h, "borde": celda[1, 1].bordes["arriba"].grosor_mm,
                 "grilla": p["grilla"]}

# -- una tabla de atributos de una capa
capa = QgsVectorLayer("Point?crs=EPSG:22185&field=lote:string&field=sup:double", "lotes", "memory")
fs = []
for lote, sup in (("A-1", 452.37), ("A-2", 1200.5), ("B-1", 98.0)):
    f = QgsFeature(capa.fields()); f.setAttributes([lote, sup]); fs.append(f)
capa.dataProvider().addFeatures(fs)
QgsProject.instance().addMapLayer(capa)
at = QgsLayoutItemAttributeTable.create(lay)
at.setVectorLayer(capa)
lay.addMultiFrame(at)
fr = QgsLayoutFrame(lay, at); fr.attemptSetSceneRect(QRectF(20, 120, 120, 60)); at.addFrame(fr)
at.refreshAttributes()
lay.deselectAll(); lay.setSelectedItem(fr)
x = QP.tabla_de_elemento(QP.tablas_elegidas(lay)[0])
QP.al_portapapeles(x)
html, txt, url = QP.leer_portapapeles()
r = T.leer(html, txt, url)
out["atributos"] = {"origen": r.origen, "grilla": r.grilla(), "con_formato": r.con_formato,
                    "negrita_enc": [c.negrita for c in r.celdas if c.fila == 0]}
# -- sin nada elegido
lay.deselectAll()
out["nada"] = len(QP.tablas_elegidas(lay))
json.dump(out, open(sys.argv[2], "w"))
app.exitQgis()
'''

HTML = ('<google-sheets-html-origin><table data-copy-id="x"><colgroup><col width="100"><col width="60">'
        '<col width="80"></colgroup>'
        '<tr style="height:24px"><td colspan="2" style="font-family:Arial;font-size:11pt;font-weight:bold;'
        'color:#c00000;text-align:center;border:1px solid #000000">CUADRO</td>'
        '<td style="font-family:Arial;font-size:10pt;font-style:italic;border:1px solid #000000">Obs.</td></tr>'
        '<tr style="height:20px"><td style="font-family:Arial;font-size:10pt;background-color:#ddebf7;'
        'border:1px solid #000000">key</td><td style="font-family:Arial;font-size:10pt;'
        'border:1px solid #000000">name</td><td style="border:1px solid #000000"></td></tr>'
        '<tr style="height:20px"><td style="font-family:Arial;font-size:10pt;border:1px solid #000000">'
        'K1</td><td style="font-family:Arial;font-size:10pt;text-align:right;'
        'border:1px solid #000000">452,37</td><td style="border:1px solid #000000">x</td></tr></table>')
TXT = "CUADRO\t\tObs.\nkey\tname\t\nK1\t452,37\tx"

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
                        *(["--env=LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6"] if rama == "lts" else []),
                        f"--env=PYTHONPATH=/app/share/qgis/python:{RAIZ / 'QGIS' / 'codigo'}",
                        f"org.qgis.qgis//{rama}", str(tmp / "carga.py"), str(tmp / "datos.json"),
                        str(tmp / "salida.json")], capture_output=True, text=True, env=env, timeout=300)
    assert (tmp / "salida.json").exists(), r.stderr[-2000:]
    out = json.loads((tmp / "salida.json").read_text())
    assert out["elegidas"] == 1 and out["nada"] == 0
    m = out["manual"]
    assert m["origen"] == "qgis_composicion" and m["dim"] == [3, 3], m
    assert m["txt"].split("\n")[0].split("\t")[0] == "CUADRO" and "452,37" in m["txt"], m["txt"]
    # el ancho de cada columna vuelve como estaba armado (márgenes y grilla incluidos)
    assert all(abs(x - y) < 0.01 for x, y in zip(m["anchos"], m["anchos_armado"])), m
    assert m["negrita"] and m["color"] == "#c00000" and m["fondo"] == "#ddebf7"
    assert m["alin"] == "derecha" and abs(m["borde"] - m["grilla"]) < 1e-3, m
    assert m["cols"] in (1, 2), m                      # combinadas: QGIS 3.40 o más nuevo
    x = out["atributos"]
    assert x["origen"] == "qgis_composicion" and x["con_formato"], x
    assert x["grilla"][0] == ["lote", "sup"], x["grilla"]
    assert [f[0] for f in x["grilla"][1:]] == ["A-1", "A-2", "B-1"], x["grilla"]
    assert x["grilla"][1][1].startswith("452.37"), x["grilla"]
    print("  QGIS %s: tabla manual y tabla de atributos copiadas con su formato%s"
          % (out["version"], "" if m["cols"] == 2 else " (sin combinar celdas)"))
if not ramas_qgis():
    print("  (QGIS de Flatpak no instalado: sólo el HTML)")
print("TODO OK: copiar tabla de las composiciones de QGIS")
