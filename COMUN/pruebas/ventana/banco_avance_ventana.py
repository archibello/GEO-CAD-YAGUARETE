"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
la ventanita de avance de SHPLABEL e IMPORTARSHP (3.79.0), y de SHPSPATIAL,
EXPORTARKML, REPROYECTAR y los rótulos que llegan de QGIS (3.80.0).

Con 1500 parcelas con base de datos (generadas acá, en Campo Inchauspe, a
un dibujo en POSGAR 2007: se reproyectan):
* IMPORTARSHP (la orden de verdad, con la ventana de opciones aceptada):
  aparece la ventanita, pasa por «Leyendo los registros», «Agregando al
  dibujo», «Actualizando la tabla de datos» y «Actualizando la pantalla»,
  con cuentas «N de 1500»; IngeCAD redibuja UNA vez.
* SHPLABEL: «Ubicando rótulos... N de 1500 (P %)» sube; Cancelar con el
  botón de verdad corta y no deja ningún rótulo; sin cancelar, 1500 rótulos.
* Cancelar en IMPORTARSHP mientras lee: el dibujo queda como estaba.

Uso (PySide6, ezdxf, numpy, pyshp, pyproj):
    python banco_avance_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, types, faulthandler
faulthandler.dump_traceback_later(400, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
import shapefile
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QPushButton

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
from core.georef import Georef, write_georef
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
AV = import_module("ingecad_plugin_geocad.avance")
HD = import_module("ingecad_plugin_geocad.herramientas_datos")
R = import_module("ingecad_plugin_geocad.rotulos")
UI = import_module("ingecad_plugin_geocad.intercambio_ui")
from views.main_window import MainWindow
fallas = []
N = 1500
PRJ = ('PROJCS["Argentina_Zone_6",GEOGCS["GCS_Campo_Inchauspe",DATUM["D_Campo_Inchauspe",'
       'SPHEROID["International_1924",6378388.0,297.0]],PRIMEM["Greenwich",0.0],'
       'UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
       'PARAMETER["False_Easting",6500000.0],PARAMETER["False_Northing",0.0],'
       'PARAMETER["Central_Meridian",-54.0],PARAMETER["Scale_Factor",1.0],'
       'PARAMETER["Latitude_Of_Origin",-90.0],UNIT["Meter",1.0]]')


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def hacer_shp(carpeta):
    ruta = os.path.join(carpeta, "lotes")
    w = shapefile.Writer(ruta, shapeType=shapefile.POLYGON, encoding="utf-8")
    w.field("PARC", "C", 10)
    for i in range(8):
        w.field(f"DATO{i}", "C", 30)
    for k in range(N):
        x0, y0 = 6_500_000 + (k % 50) * 40, 6_950_000 + (k // 50) * 40
        w.poly([[(x0, y0), (x0, y0 + 30), (x0 + 25, y0 + 32), (x0 + 30, y0 + 2), (x0, y0)]])
        w.record(f"{k:04d}", *[f"valor {k} {i}" for i in range(8)])
    w.close()
    Path(ruta + ".prj").write_text(PRJ)
    return ruta + ".shp"


class Espia:
    """Anota lo que muestra la ventanita (textos y valores) cada vez que se repinta."""

    def __init__(self):
        self.textos, self.valores, self.dialogos, self.botones = [], [], set(), []
        self.cancelar_en = None          # texto: al verlo, aprieta el botón Cancelar de verdad
        original = AV.Avance._refrescar
        espia = self
        orig_init = AV.Avance.__init__

        def init(av, parent, titulo, etapas=1, demora=0.4, **kw):
            # en el banco aparece enseguida (lo de 1500 dura menos que la demora)
            orig_init(av, parent, titulo, etapas, 0.0, **kw)
        AV.Avance.__init__ = init

        def refrescar(av, forzar=False):
            original(av, forzar)
            if av.dlg is not None:
                espia.dialogos.add(id(av.dlg))
                espia.textos.append(av.dlg.labelText())
                espia.valores.append(av.dlg.value())
                espia.botones.append(av._boton.isEnabled())
                if espia.cancelar_en and espia.cancelar_en in av.dlg.labelText() and av.hechos > 100:
                    espia.cancelar_en = None
                    boton = av.dlg.findChild(QPushButton)
                    boton.click()
        AV.Avance._refrescar = refrescar
        orig_pantalla = AV.Avance.pantalla

        def pantalla(av, ventana, texto="Actualizando la pantalla", pedir=True):
            orig_pantalla(av, ventana, texto, pedir)
            if av.dlg is not None:
                espia.textos.append(av.dlg.labelText())
        AV.Avance.pantalla = pantalla

    def limpiar(self):
        self.textos, self.valores, self.dialogos, self.botones = [], [], set(), []


espia = Espia()
AV.REFRESCO = 0.0          # repinta en cada paso: el clic en Cancelar no depende del reloj
regens = []

win = MainWindow()
win.new_document("m")
write_georef(win.document.doc, Georef(crs="EPSG:5348"))
win.show(); app.processEvents()
orig_bg = win.regen_in_background
win.regen_in_background = lambda: (regens.append(time.monotonic()), orig_bg())[1]
orig_mem = win.regen_in_memory
win.regen_in_memory = lambda *a, **k: (regens.append(time.monotonic()), orig_mem(*a, **k))[1]
shp = hacer_shp(tempfile.mkdtemp(prefix="banco-shp-"))


class Ctx:
    host = win
    document = property(lambda self: win.document)

    def echo(self, t):
        self.ecos.append(t)

    def execute(self, c):
        self.ultimo = c
        win.tools._execute(c)


ctx = Ctx(); ctx.ecos = []
UI.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([shp], ""))
def aceptar_con_base(self):
    """Tilda todas las columnas (con base de datos) y acepta."""
    from PySide6.QtCore import Qt
    for t, campos in self.previas.values():
        for j in range(len(campos)):
            t.item(0, j).setCheckState(Qt.Checked)
    return True


UI.ImportarDialog.exec = aceptar_con_base

# ------------------------------------------------------------- IMPORTARSHP, cancelar al leer
espia.cancelar_en = "Leyendo los registros"
n0 = len(list(win.document.modelspace()))
UI.importar(ctx)
ver("IMPORTARSHP: Cancelar con el botón corta", ctx.ecos[-1] == "IMPORTARSHP cancelado: no se cambió nada.",
    ctx.ecos[-1:])
ver("IMPORTARSHP cancelado: el dibujo como estaba", len(list(win.document.modelspace())) == n0
    and "lotes" not in win.document.doc.layers)

# ------------------------------------------------------------- IMPORTARSHP completo
espia.limpiar(); regens.clear()
t0 = time.monotonic()
UI.importar(ctx)
dt = time.monotonic() - t0
ver("IMPORTARSHP: importó", ctx.ecos[-1].startswith("IMPORTARSHP: Importado: 1500"), ctx.ecos[-1][:60])
ver("IMPORTARSHP: aparece la ventanita", len(espia.dialogos) == 1)
for etapa in ("1/4  Leyendo los registros...", "2/4  Agregando al dibujo...",
              "3/4  Actualizando la tabla de datos...", "4/4  Actualizando la pantalla..."):
    ver(f"IMPORTARSHP: «{etapa}»", any(t.startswith(etapa) for t in espia.textos))
ver("IMPORTARSHP: cuenta «de 1500»", any("de 1500 (" in t and "Leyendo" in t for t in espia.textos)
    and any("de 1500 (" in t and "Agregando" in t for t in espia.textos))
ver("IMPORTARSHP: un solo redibujo", len(regens) <= 1, f"({len(regens)} pedidos por GeoCAD, {dt:.1f} s)")
ver("IMPORTARSHP: la ventanita se cierra", not any(isinstance(w, QProgressDialog) and w.isVisible()
                                                   for w in app.topLevelWidgets()))

# ------------------------------------------------------------- SHPLABEL
herramienta = HD.LabelTool.__new__(HD.LabelTool)
herramienta.ctx = types.SimpleNamespace(services=types.SimpleNamespace(window=win), ecos=[],
                                        echo=lambda t: herramienta.ctx.ecos.append(t),
                                        execute=lambda c: win.tools._execute(c))
doc = win.document
espia.limpiar()
espia.cancelar_en = "Ubicando rótulos"
herramienta._rotular(doc, "lotes", "PARC", 5.0, R.OpcionesRotulo(), None)
ver("SHPLABEL: Cancelar con el botón corta", herramienta.ctx.ecos[-1:] == ["SHPLABEL cancelado: no se cambió nada."],
    herramienta.ctx.ecos[-1:])
ver("SHPLABEL cancelado: ningún rótulo", not [t for t in doc.modelspace().query("TEXT")])
espia.limpiar()
t0 = time.monotonic()
herramienta._rotular(doc, "lotes", "PARC", 5.0, R.OpcionesRotulo(), None)
dt = time.monotonic() - t0
ver("SHPLABEL: rotuló", "1500 rótulo(s) de PARC" in herramienta.ctx.ecos[-1], herramienta.ctx.ecos[-1][:50])
ver("SHPLABEL: 1500 rótulos", len(list(doc.modelspace().query("TEXT"))) == N)
ubic = [t for t in espia.textos if t.startswith("1/3  Ubicando rótulos...")]
ver("SHPLABEL: «1/3  Ubicando rótulos... N de 1500 (P %)» sube", len(ubic) >= 3 and "de 1500 (" in ubic[0],
    f"({len(ubic)} repintadas en {dt:.1f} s; {ubic[0] if ubic else ''} → {ubic[-1] if ubic else ''})")
ver("SHPLABEL: la barra avanza", espia.valores == sorted(espia.valores[:len(ubic)]) + espia.valores[len(ubic):]
    and max(espia.valores) >= 90)
ver("SHPLABEL: «2/3 Escribiendo» y «3/3 Actualizando la pantalla»",
    any(t.startswith("2/3  Escribiendo los rótulos") for t in espia.textos)
    and any(t.startswith("3/3  Actualizando la pantalla") for t in espia.textos))

# ------------------------------------------------------------- 3.80.0: SHPSPATIAL
D = import_module("ingecad_plugin_geocad.datos")
ES = import_module("ingecad_plugin_geocad.estilo")
ms = doc.modelspace()
lotes = [e for e in ms if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "lotes"]
x0, y0 = min(p[0] for p in lotes[0].get_points("xy")), min(p[1] for p in lotes[0].get_points("xy"))
zonas = [ms.add_lwpolyline([(x0 + 200 * i - 5, y0 - 5), (x0 + 200 * i + 75, y0 - 5),
                            (x0 + 200 * i + 75, y0 + 75), (x0 + 200 * i - 5, y0 + 75)], close=True)
         for i in range(10)]
consulta = HD.SpatialQueryTool.__new__(HD.SpatialQueryTool)
consulta.ctx = types.SimpleNamespace(services=win.tools, ecos=[], finish=lambda: None,
                                     echo=lambda t: consulta.ctx.ecos.append(t),
                                     ask_choice=lambda q, ops, defecto=None: ops[0] if "Condición" in q else defecto,
                                     ask_text=lambda q, d="": d)
HD.choose_link = lambda ctx, document, *a, **k: "lotes"
espia.limpiar()
espia.cancelar_en = "Comparando con las zonas"
consulta.on_selection(zonas)
ver("SHPSPATIAL: Cancelar con el botón corta", consulta.ctx.ecos[-1:] == ["SHPSPATIAL cancelado: no se cambió la selección."],
    consulta.ctx.ecos[-1:])
espia.limpiar()
t0 = time.monotonic()
consulta.on_selection(zonas)
dt = time.monotonic() - t0
esperado = D.spatial_select(doc, "lotes", zonas, "dentro")
ver("SHPSPATIAL: selecciona lo de adentro", len(esperado) > 0
    and {e.dxf.handle for e in HD.entities_of(doc, "lotes", esperado)} == set(win.tools.selection)
    and consulta.ctx.ecos[-1].startswith(f"{len(esperado)} objeto(s) de lotes"), f"{consulta.ctx.ecos[-1]} ({dt:.1f} s)")
ver("SHPSPATIAL: «1/2  Comparando con las zonas... N de 1500»",
    any(t.startswith("1/2  Comparando con las zonas...") and "de 1500 (" in t for t in espia.textos))

# ------------------------------------------------------------- 3.80.0: EXPORTARKML
carpeta = Path(tempfile.mkdtemp(prefix="banco-kml-"))
UI.ExportarKmlDialog.exec = lambda self: (self.todo.setChecked(True), True)[1]
UI.ExportarKmlDialog.archivo = lambda self: carpeta / "lotes.kmz"
win.tools.selection = set()
espia.limpiar(); ctx.ecos = []
espia.cancelar_en = "Preparando las marcas"
UI.exportar_kml(ctx)
ver("EXPORTARKML: Cancelar al preparar", ctx.ecos[-1:] == ["EXPORTARKML cancelado: no se escribió nada."]
    and not list(carpeta.iterdir()), ctx.ecos[-1:])
espia.limpiar()
espia.cancelar_en = "Escribiendo las marcas"
UI.exportar_kml(ctx)
ver("EXPORTARKML: Cancelar al escribir", ctx.ecos[-1:] == ["EXPORTARKML cancelado: no se escribió nada."]
    and not list(carpeta.iterdir()), ctx.ecos[-1:])
espia.limpiar()
UI.exportar_kml(ctx)
ver("EXPORTARKML: escribió", (carpeta / "lotes.kmz").exists() and ctx.ecos[-1].startswith("EXPORTARKML:"),
    ctx.ecos[-1][:60])
for etapa in ("1/3  Preparando las marcas...", "2/3  Escribiendo las marcas...", "3/3  Guardando el archivo..."):
    ver(f"EXPORTARKML: «{etapa}»", any(t.startswith(etapa) for t in espia.textos))

# ------------------------------------------------------------- 3.80.0: rótulos que llegan de QGIS
feats = []
for e in lotes:
    fid = D.fid_of(doc, e, "lotes")
    feats.append((fid, None, [[list(p) + [0.0] for p in e.get_points("xy")]], None))
link = types.SimpleNamespace(key="lotes", kind="polygon")
espia.limpiar()
cmds, info = ES.sig_label_commands(doc, link, {str(f[0]): [f"Q{f[0]}", 4.0] for f in feats}, "PARC",
                                   feats, {f[0] for f in feats})
ver("Rótulos de QGIS: los ubica", info["n"] == N, info)
ver("Rótulos de QGIS: «Ubicando rótulos... N de 1500»",
    any(t.startswith("Ubicando rótulos...") and "de 1500 (" in t for t in espia.textos))
ver("Rótulos de QGIS: sin Cancelar", all(not d for d in espia.botones))

# ------------------------------------------------------------- 3.80.0: REPROYECTAR
UI.ReproyectarDialog.exec = lambda self: True
UI._confirmar = lambda *a, **k: True
espia.limpiar(); regens.clear(); ctx.ecos = []
antes_xy = lotes[0].get_points("xy")[0]
UI.reproyectar(ctx, "EPSG:22196")
ver("REPROYECTAR: convirtió", ctx.ecos[-1:] and ctx.ecos[-1].startswith("REPROYECTAR:")
    and abs(lotes[0].get_points("xy")[0][0] - antes_xy[0]) > 1, ctx.ecos[-1:])
ver("REPROYECTAR: «1/2  Convirtiendo los objetos... N de M» y «2/2  Actualizando la pantalla»",
    any(t.startswith("1/2  Convirtiendo los objetos...") and " de " in t for t in espia.textos)
    and any(t.startswith("2/2  Actualizando la pantalla") for t in espia.textos))
ver("REPROYECTAR: sin Cancelar (ya se confirmó)", all(not d for d in espia.botones))
ver("REPROYECTAR: rehacer sin la ventanita", getattr(ctx.ultimo, "avance", 1) is None)

win.document.dirty = False
if fallas:
    print("FALLAS:", fallas)
    os._exit(1)
print("TODO OK")
sys.stdout.flush()
os._exit(0)
