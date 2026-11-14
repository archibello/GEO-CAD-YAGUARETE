"""Ventanita de avance (3.79.0) para SHPLABEL e IMPORTARSHP.

Sin Qt no se muestra nada, pero se cuenta igual: las etapas quedan en
``registro``, cada objeto es un ``paso()`` y ``cancelar()`` simula el botón.
Cancelar mientras se ubican los rótulos o se leen los registros deja el
dibujo como estaba; en las etapas que escriben, Cancelar no hace nada. Un
solo redibujo: si IngeCAD ya está redibujando, no se le pide otro."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.commands import History
from core.document import Document
from core.plugins import load_plugin

import fixtures

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
AV = import_module("ingecad_plugin_geocad.avance")
IX = import_module("ingecad_plugin_geocad.intercambio")
HD = import_module("ingecad_plugin_geocad.herramientas_datos")
R = import_module("ingecad_plugin_geocad.rotulos")

# ------------------------------------------------------------- 1. textos
assert AV.texto_etapa(1, 3, "Ubicando rótulos", 640, 1373) == "1/3  Ubicando rótulos... 640 de 1373 (46 %)"
assert AV.texto_etapa(2, 3, "Escribiendo", 0, 0) == "2/3  Escribiendo..."
assert AV.texto_etapa(1, 1, "Leyendo", 5, 4) == "Leyendo... 4 de 4 (100 %)"     # nunca más del total
print("ok textos de cada etapa")

# ------------------------------------------------------------- 2. sin Qt: cuenta y cancela
with AV.Avance(None, "PRUEBA", etapas=2) as av:
    assert av.qt is None and av.dlg is None
    av.etapa("Uno", total=3)
    av.paso(); av.paso()
    assert av.hechos == 2
    av.cancelar()
    try:
        av.paso()
        raise AssertionError("debía cancelar")
    except AV.Cancelado:
        pass
with AV.Avance(None, "PRUEBA", etapas=2) as av:
    av.etapa("Escribe", total=2, cancelable=False)
    av.cancelar()                                   # apagado: no hace nada
    av.paso(); av.paso()
    assert not av.cancelado and av.registro == [(1, "Escribe", 2)]
print("ok sin Qt: cuenta, Cancelar sólo donde no se escribió nada")

# ------------------------------------------------------------- 3. IMPORTARSHP
tmp = tempfile.mkdtemp()
parcelas, red, pozos = fixtures.make_parcelas(tmp), fixtures.make_red(tmp), fixtures.make_puntos(tmp)
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
capas_antes = {l.dxf.name for l in doc.doc.layers}

av = AV.Avance(None, "IMPORTARSHP", etapas=3)
plan = IX.plan_importar(doc.doc, [parcelas, red, pozos], IX.OpcionesImportar(adoptar=False), av)
registros = sum(r for _n, r, _o, _s, _c in plan.por_archivo)
assert av.registro[0][1] == "Leyendo los registros" and av.registro[0][2] == registros
assert av.hechos == registros, (av.hechos, registros)
av.etapa("Agregando al dibujo", total=plan.objetos, cancelable=False)
hist.execute(plan.comando)
assert av.hechos == plan.objetos == len(list(msp)), (av.hechos, plan.objetos)   # cada objeto agregado cuenta
hist.undo()
assert not list(msp)

# Cancelar mientras se leen: nada cambia (ni objetos, ni capas, ni sistema)
class CortaEn(AV.Avance):
    def __init__(self, n):
        super().__init__(None, "PRUEBA", etapas=3)
        self.n = n

    def paso(self, hechos=None):
        if self.numero == 1 and self.hechos + 1 >= self.n:
            self.cancelar()
        super().paso(hechos)


try:
    IX.plan_importar(doc.doc, [parcelas, red, pozos], IX.OpcionesImportar(), CortaEn(3))
    raise AssertionError("debía cancelar")
except AV.Cancelado:
    pass
assert not list(msp) and {l.dxf.name for l in doc.doc.layers} == capas_antes
assert IX.sistema_del_dibujo(doc.doc) == ""
# sin avance, como siempre
plan = IX.plan_importar(doc.doc, [parcelas, red, pozos], IX.OpcionesImportar(adoptar=False))
hist.execute(plan.comando)
assert len(list(msp)) == plan.objetos
print("ok IMPORTARSHP: cuenta registros y objetos; Cancelar al leer no cambia nada")

# ------------------------------------------------------------- 4. SHPLABEL
def rotulos(capa):
    return sorted(t.dxf.text for t in msp.query("TEXT") if t.dxf.layer == f"{capa}-ROTULOS")


hist.execute(HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, R.OpcionesRotulo())[0])
antes = rotulos("parcelas")
assert len(antes) == 5
av = AV.Avance(None, "SHPLABEL", etapas=3)
cmd, n, old = HD.label_commands(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(), None, av)
assert av.registro[0] == (1, "Ubicando rótulos", 5) and av.hechos == 5 and n == 5
try:
    HD.label_commands(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(), None, CortaEn(2))
    raise AssertionError("debía cancelar")
except AV.Cancelado:
    pass
assert rotulos("parcelas") == antes                 # los anteriores siguen, intactos


# la herramienta: Cancelar avisa y no ejecuta; sin cancelar, rotula y resume
class Ctx:
    def __init__(self):
        self.ecos, self.ejecutados = [], []
        self.services = types.SimpleNamespace(window=None)

    def echo(self, t):
        self.ecos.append(t)

    def execute(self, c):
        self.ejecutados.append(c)
        hist.execute(c)


herramienta = HD.LabelTool.__new__(HD.LabelTool)
herramienta.ctx = Ctx()
original = AV.Avance
AV.Avance = lambda *a, **k: CortaEn(2)
try:
    herramienta._rotular(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(), None)
finally:
    AV.Avance = original
assert herramienta.ctx.ejecutados == [] and herramienta.ctx.ecos == ["SHPLABEL cancelado: no se cambió nada."]
assert rotulos("parcelas") == antes
herramienta._rotular(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(), None)
assert len(herramienta.ctx.ejecutados) == 1 and "5 rótulo(s) de TITULAR" in herramienta.ctx.ecos[-1]
assert rotulos("parcelas") != antes and len(rotulos("parcelas")) == 5
print("ok SHPLABEL: cuenta cada objeto; Cancelar deja los rótulos como estaban")

# ------------------------------------------------------------- 5. un solo redibujo
class Ventana:
    def __init__(self, ocupada):
        self._regen_worker = object() if ocupada else None
        self.pedidos = []

    def regen_in_background(self):
        self.pedidos.append("fondo")

    def regen_in_memory(self):
        self.pedidos.append("memoria")


v = Ventana(ocupada=True)
AV.pedir_redibujo(v)
assert v.pedidos == []                              # IngeCAD ya redibuja: no se pide otro
v = Ventana(ocupada=False)
AV.pedir_redibujo(v)
assert v.pedidos == ["fondo"]                       # en segundo plano, si se puede
v = Ventana(ocupada=False)
with AV.Avance(None, "PRUEBA", etapas=2) as av:
    av.pantalla(v, pedir=False)                     # SHPLABEL: sólo espera el de IngeCAD
    assert v.pedidos == [] and av.registro[-1][1] == "Actualizando la pantalla"
    av.pantalla(v)
    assert v.pedidos == ["fondo"]
print("ok un solo redibujo")

# ============================================================= 3.80.0
import random, shapefile
D = import_module("ingecad_plugin_geocad.datos")
KML = import_module("ingecad_plugin_geocad.kml")
ES = import_module("ingecad_plugin_geocad.estilo")
from core.georef import Georef, write_georef

# ------------------------------------------------------------- 6. consulta por ubicación: igual que antes
random.seed(7)
ruta = os.path.join(tempfile.mkdtemp(), "azar")
w = shapefile.Writer(ruta, shapeType=shapefile.POLYGON, encoding="utf-8")
w.field("N", "N", 6)
for k in range(300):
    x, y = random.uniform(0, 1000), random.uniform(0, 1000)
    a_, b_ = random.uniform(2, 40), random.uniform(2, 40)
    w.poly([[(x, y), (x, y + b_), (x + a_, y + b_), (x + a_, y), (x, y)]])
    w.record(k)
w.close()
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
hist.execute(IX.plan_importar(doc.doc, [ruta + ".shp"], IX.OpcionesImportar(adoptar=False)).comando)
zonas = []
for k in range(60):
    x, y = random.uniform(-50, 1050), random.uniform(-50, 1050)
    tipo = k % 4
    if tipo == 0:
        a_ = random.uniform(5, 120)
        zonas.append(msp.add_lwpolyline([(x, y), (x + a_, y), (x + a_, y + a_), (x, y + a_)], close=True))
    elif tipo == 1:
        zonas.append(msp.add_lwpolyline([(x, y), (x + random.uniform(-200, 200), y + random.uniform(-200, 200))]))
    elif tipo == 2:
        zonas.append(msp.add_circle((x, y), random.uniform(1, 60)))
    else:
        zonas.append(msp.add_point((x, y)))
zonas.append(msp.add_lwpolyline([(-10, -10), (1100, -10), (1100, 1100), (-10, 1100)], close=True))  # enorme


def vieja(zs, mode, dist=0.0):
    """La cuenta de antes: cada objeto contra todas las zonas."""
    zone = [r for e in zs for r in D.entity_rings(e)]
    por = {}
    for fid, e in D.tagged(doc, "azar"):
        por.setdefault(fid, []).append(e)
    return {fid for fid, ents in por.items()
            if D.relation([r for e in ents for r in D.entity_rings(e)], zone, mode, dist)}


casos = 0
for zs in (zonas[:-1], zonas, zonas[2:3], zonas[3:4], [zonas[1], zonas[3]]):
    for mode, dist in (("dentro", 0), ("toca", 0), ("distancia", 0), ("distancia", 7.5), ("distancia", 60)):
        nueva = D.spatial_select(doc, "azar", zs, mode, dist)
        assert nueva == vieja(zs, mode, dist), (mode, dist, len(zs))
        casos += 1
assert D.spatial_select(doc, "azar", zonas[-1:], "dentro") == set(range(300))  # la enorme las cubre
av = AV.Avance(None, "SHPSPATIAL", etapas=2)
D.spatial_select(doc, "azar", zonas[:-1], "toca", 0, av)
assert av.registro[0] == (1, "Comparando con las zonas", 300) and av.hechos == 300
try:
    D.spatial_select(doc, "azar", zonas[:-1], "toca", 0, CortaEn(50))
    raise AssertionError("debía cancelar")
except AV.Cancelado:
    pass
print(f"ok consulta por ubicación: igual que la cuenta de antes en {casos} casos; cuenta y cancela")

# ------------------------------------------------------------- 7. REPROYECTAR cuenta cada objeto
write_georef(doc.doc, Georef(crs="EPSG:5347"))
cmd, _c = IX.preparar_reproyeccion(doc.doc, "EPSG:22195")
av = AV.Avance(None, "REPROYECTAR", etapas=2)
av.etapa("Convirtiendo los objetos", total=len(cmd.entidades), cancelable=False)
cmd.avance = av
hist.execute(cmd)
cmd.avance = None
assert av.hechos == len(cmd.entidades) > 300
hist.undo(); hist.redo()                                    # sin avance: como siempre
print("ok REPROYECTAR cuenta cada objeto")

# ------------------------------------------------------------- 8. EXPORTARKML
hist.undo()
ents_kml = [e for e in msp if e.dxf.layer == "azar"]
av = AV.Avance(None, "EXPORTARKML", etapas=3)
plan = KML.plan_kml(ents_kml, doc.doc, "Prueba", avance=av)
assert av.registro[0] == (1, "Preparando las marcas", 300) and av.hechos == 300
try:
    KML.plan_kml(ents_kml, doc.doc, "Prueba", avance=CortaEn(10))
    raise AssertionError("debía cancelar")
except AV.Cancelado:
    pass
carpeta = Path(tempfile.mkdtemp())
av.etapa("Escribiendo las marcas", total=len(plan.marcas))
KML.escribir(plan, carpeta / "a.kmz", av)
assert (carpeta / "a.kmz").exists() and av.registro[-1] == (3, "Guardando el archivo", 0)
assert av.registro[-2][1] == "Escribiendo las marcas" and av.hechos == 0
(carpeta / "b.kmz").write_text("lo de antes")
corta = CortaEn(0)
corta.numero = 0
corta.etapa("Escribiendo las marcas", total=len(plan.marcas))
corta.cancelar()
try:
    KML.escribir(plan, carpeta / "b.kmz", corta)
    raise AssertionError("debía cancelar")
except AV.Cancelado:
    pass
assert (carpeta / "b.kmz").read_text() == "lo de antes"             # el archivo que había queda
assert sorted(p.name for p in carpeta.iterdir()) == ["a.kmz", "b.kmz"]  # sin temporales
print("ok EXPORTARKML: cuenta marcas; Cancelar no toca el archivo")

# ------------------------------------------------------------- 9. rótulos de QGIS: sin Cancelar
av = AV.Avance(None, "QGIS", cancelar=False)
av.etapa("Ubicando rótulos", total=3)
av.cancelar()
av.paso(); av.paso(); av.paso()
assert not av.cancelado and not av.cancelable
print("ok rótulos que llegan de QGIS: la ventanita no se puede cancelar")

print("TODO OK")
