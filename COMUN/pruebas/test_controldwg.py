"""Control de los DWG al guardar (módulo «dwg», 3.28.1 y 3.28.2): IngeCAD avisaba
«the DWG writer reported internal errors while packing the file» por un
error de LibreDWG (el código 21 = 0 de los bordes de sombreado le resulta
«desconocido»). Se descarta sólo si el DXF tiene esos ceros; lo demás se
avisa en español y con el texto del error."""
import os, shutil, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from formats import dwg_bridge as B

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
C = import_module("ingecad_plugin_geocad.controldwg")
mods = import_module("ingecad_plugin_geocad.modulos")
plugin = import_module("ingecad_plugin_geocad")

carpeta = Path(tempfile.mkdtemp())
FALSA = "ERROR: Unknown DXF code 21 for HATCH"

# ------------------------------------------------------------- 1. el dibujo
doc = ezdxf.new("R2000")
msp = doc.modelspace()
h = msp.add_hatch(color=1)                 # cuadrado desde el origen: 2 rectas con Y final = 0
ed = h.paths.add_edge_path()
ed.add_line((0, 0), (1, 0))
ed.add_line((1, 0), (1, 1))
ed.add_line((1, 1), (0, 1))
ed.add_line((0, 1), (0, 0))
blk = doc.blocks.new("PIEZA")              # y una elipse en un bloque: eje mayor (1, 0)
h2 = blk.add_hatch()
ed2 = h2.paths.add_edge_path()
ed2.add_ellipse((0, 0), major_axis=(1, 0), ratio=0.5, start_angle=0, end_angle=360)
dxf = carpeta / "plano.dxf"
doc.saveas(dxf)
ceros = C.ceros_21(dxf)
assert ceros == 3, ceros                   # (1,0), (0,0) y el eje (1,0)
print("ok ceros", ceros)

# ------------------------------------------------------------- 2. filtrar
limpio, n = C.filtrar("\n".join([FALSA] * 3 + ["Writing DWG file x as r2000"]), dxf)
assert n == 3 and FALSA not in limpio and "Writing" in limpio
assert B._converter_errors(limpio) == []
limpio, n = C.filtrar("\n".join([FALSA] * 4), dxf)       # más quejas que ceros: quedan todas
assert n == 0 and limpio.count(FALSA) == 4
otro = "ERROR: Invalid table entry"
limpio, n = C.filtrar(f"{FALSA}\n{otro}\n{otro}", dxf)     # el error real se queda
assert n == 1 and B._converter_errors(limpio) == [otro, otro]
assert C.filtrar("", dxf) == ("", 0)
assert C.filtrar(FALSA, carpeta / "no_existe.dxf") == (FALSA, 0)
ESTILO = 'ERROR: DETAILVIEWSTYLE: Unexpected DXF code 340, expected 90 for "\\"flags\\""'
CORTE = 'ERROR: SECTIONVIEWSTYLE: Unexpected DXF code 62, expected 40 for "\\"identifier_height\\""'
limpio, n = C.filtrar(f"{ESTILO}\n{CORTE}\n{FALSA}\n{otro}", dxf)     # 3.28.2: estilos de vista
assert n == 3 and B._converter_errors(limpio) == [otro], limpio
assert C.filtrar("ERROR: DIMSTYLE: Unexpected DXF code 340", dxf)[1] == 0  # otro objeto: se queda
print("ok filtrar")

# ------------------------------------------------------------- 3. avisos en español
assert C.detalle([otro, otro, "ERROR: a", "ERROR: b", "ERROR: c"]) == \
    "«ERROR: Invalid table entry» (2 veces); «ERROR: a»; «ERROR: b»; y 1 más"
assert C.traducir(C.AVISO_ERRORES, [otro]) == \
    "LibreDWG informó errores al armar el DWG: «ERROR: Invalid table entry»"
assert C.traducir(C.AVISO_REABRIR, []).startswith("no se pudo volver a abrir")
assert C.traducir("some drawing objects did not survive the save (10 → 8)", []).startswith(
    "se perdieron objetos del dibujo al guardar (10 → 8)")
assert C.traducir("otra cosa", []) == "otra cosa"
print("ok traducir")

# ------------------------------------------------------------- 4. verify_dwg envuelto
assert getattr(B.verify_dwg, "_puente_fabrica", None) is C._envolver_verify_dwg
copia = carpeta / "vuelta.dxf"


def convertir(_dwg):                       # la vuelta DWG -> DXF, sin LibreDWG: el mismo DXF
    shutil.copy(dxf, copia)
    return copia


B._convert_dwg = convertir
B._discard_temp_dxf = lambda p: None
dwg = carpeta / "plano.dwg"
mods.poner("ingecad", "dwg", True)
assert C.activo()
assert B.verify_dwg(dxf, dwg, "\n".join([FALSA] * 3)) == []                  # falsa alarma: limpio
av = B.verify_dwg(dxf, dwg, f"{FALSA}\n{otro}")
assert av == ["LibreDWG informó errores al armar el DWG: «ERROR: Invalid table entry»"], av
mods.poner("ingecad", "dwg", False)                                          # apagado: como viene
assert B.verify_dwg(dxf, dwg, "\n".join([FALSA] * 3)) == [C.AVISO_ERRORES]
mods.poner("ingecad", "dwg", True)
print("ok verify_dwg")

# ------------------------------------------------------------- 5. el módulo y la instalación
m = next(m for m in mods.CATALOGO["ingecad"] if m.clave == "dwg")
assert m.defecto and m.disponible
antes = B.verify_dwg
C.instalar()                               # instalar de nuevo no envuelve dos veces
assert B.verify_dwg is antes
assert not hasattr(B.verify_dwg._puente_original, "_puente_original")   # el de IngeCAD
print("ok instalar")
print("TODO OK CONTROL DWG")
