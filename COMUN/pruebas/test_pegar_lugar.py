"""PEGAR EN EL LUGAR entre IngeCAD y QGIS (3.66.0, PEGARORIG / PASTEORIG, Ctrl+Alt+V).

Fernando, 04/11/2026: «copiar en una las entidades seleccionadas y pegarlas en
la otra»; «crear en IngeCAD la herramienta PEGAR EN COORDENADAS ORIGINALES en
el menú EDIT debajo de PASTE y lo mismo en QGIS»; «ESO ES PEGAR EN EL LUGAR»;
«CTRL+ALT+V»; «si no está configurado el sistema de representación de
coordenadas, esta acción va a crear el mismo de forma automática».

Sin Qt: el mensaje del portapapeles (nucleo/pegar_lugar.py), la regla del
sistema de coordenadas, los grosores, el WKT, y el viaje IngeCAD -> mensaje ->
dibujo con capas, colores, tipos y grosores (pegar_lugar_ingecad.py). Lo que
se ve en las ventanas lo prueban ventana/banco_pegar_lugar_ventana.py
(IngeCAD real) y ventana/banco_pegar_lugar_qgis.py (QGIS real)."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import json, os, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin

ROOT = Path(__file__).resolve().parents[2]
lp = load_plugin(ROOT / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
PL = import_module("ingecad_plugin_geocad.pegar_lugar")
PI = import_module("ingecad_plugin_geocad.pegar_lugar_ingecad")
mods = import_module("ingecad_plugin_geocad.modulos")

# ---- 1. el mensaje ------------------------------------------------------------------------
assert PL.ATAJO == "Ctrl+Alt+V"
datos = PL.empaquetar("qgis", "EPSG:22197", [{"wkt": "POINT (1 2)", "capa": "Muros"}],
                      {"Muros": {"color": "#ff0000", "aci": 1}}, {"texto(s)": 2})
msg = PL.desempaquetar(datos)
assert msg["origen"] == "qgis" and msg["crs"] == "EPSG:22197" and len(msg["objetos"]) == 1
assert PL.resumen(msg) == "1 objeto(s) de QGIS (no viajan: 2 texto(s))", PL.resumen(msg)
assert PL.desempaquetar(b"hola") is None and PL.desempaquetar(b'{"a": 1}') is None
assert PL.desempaquetar(None) is None
print("ok el mensaje")

# ---- 2. el sistema de coordenadas: el destino sin sistema toma el del origen ---------------
assert PL.sistema("", "EPSG:22197") == ("EPSG:22197", False)        # «lo crea automáticamente»
assert PL.sistema("EPSG:22197", "epsg:22197") == ("", False)
assert PL.sistema("EPSG:22197", "EPSG:32721") == ("", True)          # distinto: se reproyecta
assert PL.sistema("EPSG:22197", "") == ("", False) and PL.sistema("", "") == ("", False)
print("ok sistema de coordenadas")

# ---- 3. grosores y WKT ----------------------------------------------------------------------
assert PL.grosor_dxf(None) == -1 and PL.grosor_dxf(-1) == -3 and PL.grosor_dxf(0.25) == 25
assert PL.grosor_dxf(0.26) == 25 and PL.grosor_dxf(2.11) == 211
assert PL.mm_de_dxf(-1) is None and PL.mm_de_dxf(-3) == -1.0 and PL.mm_de_dxf(35) == 0.35
assert PL.partes_wkt("POINT (1 2)") == ("punto", [(1.0, 2.0)])
assert PL.partes_wkt("MultiPoint ((1 2),(3 4))") == ("punto", [(1.0, 2.0), (3.0, 4.0)])
assert PL.partes_wkt("LineStringZ (0 0 5, 10 0 5)") == ("linea", [[(0.0, 0.0), (10.0, 0.0)]])
assert PL.partes_wkt("MULTILINESTRING ((0 0, 1 1), (2 2, 3 3))")[1] == [[(0, 0), (1, 1)], [(2, 2), (3, 3)]]
t, pol = PL.partes_wkt("POLYGON ((0 0, 10 0, 10 10, 0 0), (1 1, 2 1, 2 2, 1 1))")
assert t == "poligono" and len(pol) == 1 and len(pol[0]) == 2 and pol[0][1][0] == (1.0, 1.0)
t, pol = PL.partes_wkt("MultiPolygon (((0 0, 1 0, 1 1, 0 0)),((5 5, 6 5, 6 6, 5 5)))")
assert len(pol) == 2 and pol[1][0][0] == (5.0, 5.0), pol
assert PL.partes_wkt("POINT EMPTY") == ("punto", []) and PL.partes_wkt("hola") == ("", [])
assert PL.partes_wkt("POINT (-1.5e3 2.25)") == ("punto", [(-1500.0, 2.25)])
print("ok grosores y WKT")

# ---- 4. IngeCAD -> mensaje (lo que viaja a QGIS) ----------------------------------------------
doc = ezdxf.new("R2010", setup=True)
doc.layers.add("Muros", color=1, linetype="DASHED", lineweight=35)
doc.layers.add("Ejes", color=5)
msp = doc.modelspace()
pl = msp.add_lwpolyline([(1000, 2000), (1010, 2000), (1010, 2010)], dxfattribs={"layer": "Muros"})
cerrada = msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)], close=True,
                             dxfattribs={"layer": "Ejes", "color": 3, "lineweight": 50})
punto = msp.add_point((7, 8), dxfattribs={"layer": "Ejes"})
rgb = msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "Muros", "linetype": "CENTER"})
rgb.rgb = (10, 20, 30)
texto = msp.add_text("hola", dxfattribs={"layer": "Muros"})
m = PL.desempaquetar(PI.mensaje_de([pl, cerrada, punto, rgb, texto], doc, "EPSG:22197"))
assert m["origen"] == "ingecad" and m["crs"] == "EPSG:22197"
assert len(m["objetos"]) == 4 and m["salteados"] == {"texto(s)": 1}, m["salteados"]
o = {x["wkt"].split(" ")[0]: x for x in m["objetos"]}
assert m["objetos"][0]["capa"] == "Muros" and m["objetos"][0]["color"] is None      # PorCapa
assert m["objetos"][0]["wkt"].startswith("LINESTRING (1000 2000")
assert o["POLYGON"]["aci"] == 3 and o["POLYGON"]["color"] == "#00ff00" and o["POLYGON"]["grosor"] == 0.5
assert o["POINT"]["wkt"].startswith("POINT (7 8")
lineas = [x for x in m["objetos"] if x["wkt"].startswith("LINESTRING")]
propio = next(x for x in lineas if x["color"])
assert propio["color"] == "#0a141e" and propio["aci"] is None and propio["tipo_linea"] == "CENTER"
assert m["capas"]["Muros"] == {"color": "#ff0000", "aci": 1, "tipo_linea": "DASHED", "grosor": 0.35}
assert m["capas"]["Ejes"]["aci"] == 5 and m["capas"]["Ejes"]["grosor"] == -1.0
print("ok IngeCAD -> mensaje")

# ---- 5. mensaje -> IngeCAD (lo que llega de QGIS), en sus coordenadas ----------------------
qmsg = PL.desempaquetar(PL.empaquetar("qgis", "EPSG:22197", [
    {"wkt": "LineString (5500000 6900000, 5500100 6900050)", "capa": "Calles", "color": None,
     "aci": None, "tipo_linea": None, "grosor": None},
    {"wkt": "MultiPolygon (((10 10, 20 10, 20 20, 10 10)),((30 30, 40 30, 40 40, 30 30)))",
     "capa": "Lotes", "color": "#123456", "aci": None, "tipo_linea": "DASHED", "grosor": 0.5},
    {"wkt": "Point (1 2)", "capa": "Mojones", "color": "#ff0000", "aci": 1, "tipo_linea": None,
     "grosor": -1},
], {"Calles": {"color": "#0000ff", "aci": 5, "tipo_linea": "CENTER", "grosor": 0.35},
    "Lotes": {"color": "#a0b0c0", "aci": None, "tipo_linea": None, "grosor": None}}))
d = PI.documento_de(qmsg)
ents = list(d.modelspace())
assert [e.dxftype() for e in ents] == ["LWPOLYLINE", "LWPOLYLINE", "LWPOLYLINE", "POINT"]
calle = ents[0]
assert calle.dxf.layer == "Calles" and list(calle.get_points("xy")) == [(5500000, 6900000), (5500100, 6900050)]
assert calle.dxf.color == 256 and calle.dxf.lineweight == -1                    # PorCapa
assert d.layers.get("Calles").dxf.color == 5 and d.layers.get("Calles").dxf.linetype == "CENTER"
assert d.layers.get("Calles").dxf.lineweight == 35
assert d.layers.get("Lotes").rgb == (0xa0, 0xb0, 0xc0)
lote = ents[1]
assert lote.closed and lote.rgb == (0x12, 0x34, 0x56) and lote.dxf.linetype == "DASHED"
assert lote.dxf.lineweight == 50 and len(lote) == 3                     # sin repetir el primero
assert ents[3].dxf.color == 1 and ents[3].dxf.lineweight == -3 and ents[3].dxf.layer == "Mojones"
assert "Mojones" in d.layers                                            # capa sin datos: se crea
# reproyectado: cada punto por la función
d2 = PI.documento_de(qmsg, lambda x, y: (x + 1, y + 2))
assert tuple(list(d2.modelspace())[3].dxf.location)[:2] == (2, 4)
# ida y vuelta: IngeCAD -> mensaje -> IngeCAD deja las mismas coordenadas
vuelta = PI.documento_de(m)
assert list(list(vuelta.modelspace())[0].get_points("xy")) == [(1000, 2000), (1010, 2000), (1010, 2010)]
print("ok mensaje -> IngeCAD")

# ---- 6. el módulo, el menú y los botones (IngeCAD) ------------------------------------------
mod = next(x for x in mods.catalogo("ingecad") if x.clave == "pegar_lugar")
assert mod.defecto and mod.cambia_programa and "Ctrl+Alt+V" in mod.nombre
assert lp.spec.tools.get("GEOPASTEORIG") is PI.PegarLugarTool
init = (ROOT / "INGECAD/codigo/geocad/__init__.py").read_text(encoding="utf-8")
assert '"PASTEORIG": "GEOPASTEORIG"' in init and init.count("pegar_lugar_ingecad.aplicar(") == 2
cmds = json.loads((ROOT / "INGECAD/codigo/geocad/i18n/es/commands.json").read_text(encoding="utf-8"))
ui = json.loads((ROOT / "INGECAD/codigo/geocad/i18n/es/ui.json").read_text(encoding="utf-8"))
assert cmds["GEOPASTEORIG"]["name"] == "PEGARORIG" and ui["Paste in Place"] == "Pegar en el lugar"
assert ui["Paste in Place (PASTEORIG)"] == "Pegar en el lugar (PEGARORIG)"
fuente = (ROOT / "INGECAD/codigo/geocad/pegar_lugar_ingecad.py").read_text(encoding="utf-8")
assert "menu.insertAction(_siguiente(menu, pegar), accion)" in fuente     # debajo de Paste
assert "PasteCommand(sources, 0.0, 0.0" in fuente                        # el Paste de IngeCAD, sin mover
assert "intercambio.DefinirSistemaCommand(definir)" in fuente
B = import_module("ingecad_plugin_geocad.botones")
assert B.banco_de("ingecad", "GEOPASTEORIG") == "Edición"            # banco Edición
assert B.banco_de("qgis", "geocad:pegarorig") == "Edición"
print("ok IngeCAD: módulo, Edit, comando y botón")

# ---- 7. QGIS (el código; lo demás, en el banco con QGIS real) --------------------------------
qmod = next(x for x in mods.catalogo("qgis") if x.clave == "pegar_lugar")
assert qmod.defecto and qmod.cambia_programa and not qmod.requiere
q = (ROOT / "QGIS/codigo/geocad/pegar_lugar_qgis.py").read_text(encoding="utf-8")
assert "iface.actionPasteFeatures()" in q and "self.menu.insertAction(siguiente, self.accion)" in q
assert "iface.actionCopyFeatures()" in q and "proyecto.setCrs(nuevo)" in q
assert "QKeySequence(pegar_lugar.ATAJO)" in q
qp = (ROOT / "QGIS/codigo/geocad/plugin.py").read_text(encoding="utf-8")
assert "self._sync_pegar_lugar()" in qp and "self._quitar_pegar_lugar()" in qp
assert 'add("pegarorig", "Pegar en el lugar (PEGARORIG, Ctrl+Alt+V)"' in qp
dq = (ROOT / "QGIS/codigo/geocad/dibujo/plugin.py").read_text(encoding="utf-8")
assert "('PEGARORIG', 'PEGARENLUGAR', 'PASTEORIG')" in dq
assert '"geocad:pegarorig"' in (ROOT / "COMUN/nucleo/botones.py").read_text(encoding="utf-8")
for f in ("pegar_lugar.py", "modulos.py", "botones.py"):            # el núcleo, igual en los dos
    n = (ROOT / "COMUN/nucleo" / f).read_bytes()
    assert n == (ROOT / "INGECAD/codigo/geocad" / f).read_bytes() == (ROOT / "QGIS/codigo/geocad" / f).read_bytes(), f
print("ok QGIS: módulo, Edición, Ctrl+C y comando")

# ---- 8. la copia guardada: sólo vale con lo que hay ahora en el portapapeles ------------------
class Mime:                                     # lo que usa de QMimeData
    def __init__(self, texto=None, **formatos):
        self.texto, self.formatos = texto, formatos
    def hasText(self): return self.texto is not None
    def text(self): return self.texto
    def hasFormat(self, f): return f in self.formatos
    def data(self, f): return self.formatos[f]

men = PL.empaquetar("qgis", "EPSG:22185", [{"wkt": "POINT (1 2)", "capa": "Ñandú"}])
assert PL.leer_copia(Mime("a")) is None and PL.leer_copia(None) is None          # sin archivo
assert not PL.dejar_copia(men, Mime(), PL.FORMATO_TEXTO)                         # sin texto, nada
assert PL.dejar_copia(men, Mime("wkt_geom\tñ\n"), PL.FORMATO_TEXTO)
assert PL.leer_copia(Mime("wkt_geom\tñ\n"))["objetos"][0]["capa"] == "Ñandú"
assert PL.leer_copia(Mime("wkt_geom\tñ\r\n"))["origen"] == "qgis"
assert PL.leer_copia(Mime("otra cosa")) is None and PL.leer_copia(Mime()) is None # copia vieja
assert PL.dejar_copia(men, Mime(id=b"p-1:1"), "id")
assert PL.leer_copia(Mime(id=b"p-1:1")) is not None and PL.leer_copia(Mime(id=b"p-1:2")) is None
assert not list(PL.archivo_copia().parent.glob(".pegar_lugar-*"))                # sin restos
PL.archivo_copia().write_text("{roto", encoding="utf-8")
assert PL.leer_copia(Mime(id=b"p-1:1")) is None
PL.borrar_copia(); PL.borrar_copia()
assert not PL.archivo_copia().exists()
# ni QGIS ni IngeCAD vuelven a escribir el portapapeles: en Wayland lo deja vacío y sin
# pantalla los bancos no lo ven
for f in ("QGIS/codigo/geocad/pegar_lugar_qgis.py", "INGECAD/codigo/geocad/pegar_lugar_ingecad.py"):
    assert "setMimeData" not in (ROOT / f).read_text(encoding="utf-8"), f
print("ok la copia guardada y su huella")
print("TODO OK test_pegar_lugar")
