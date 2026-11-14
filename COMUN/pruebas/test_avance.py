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

print("TODO OK")
