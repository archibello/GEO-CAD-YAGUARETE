"""Rótulos estandarizados (3.26.0, reglas de Fernando del 16/10/2026).
Polígonos cerrados: dentro, centrados en el centro visual; los que no
entran: A achicar horizontal, B rotar al eje más largo y achicar, C todos
según el eje, D omitir. Líneas: según el eje, en la mitad, sobre / arriba /
abajo, nunca cabeza abajo. Puntos: centrado o desde el punto a media
altura. ROTULOSIG los dibuja así y recuerda lo último elegido."""
import math, os, tempfile, types
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
R = import_module("ingecad_plugin_geocad.rotulos")
IX = import_module("ingecad_plugin_geocad.intercambio")
HD = import_module("ingecad_plugin_geocad.herramientas_datos")

med = lambda t, h: 0.7 * h * len(t)          # medida fija: resultados exactos


def rect(cx, cy, largo, ancho, g):
    c, s = math.cos(math.radians(g)), math.sin(math.radians(g))
    return [(cx + u * c - v * s, cy + u * s + v * c)
            for u, v in ((-largo / 2, -ancho / 2), (largo / 2, -ancho / 2),
                         (largo / 2, ancho / 2), (-largo / 2, ancho / 2))]


def cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ------------------------------------------------------------- 1. geometría
assert R.legible(0) == 0 and R.legible(135) == -45 and R.legible(-100) == 80 and R.legible(270) == 90
assert R.legible(180) == 0 and R.legible(-90) == 90
assert R.legible(-87) == 93 and R.legible(93) == 93 and R.legible(-80) == -80   # de abajo hacia arriba
assert abs(R.eje_mas_largo(rect(0, 0, 40, 6, 80)) - 80) < 1e-6
assert abs(R.eje_mas_largo(rect(0, 0, 40, 6, 170)) - (-10)) < 1e-6
assert abs(R.eje_mas_largo(rect(0, 0, 6, 40, 0)) - 90) < 1e-6          # el largo es el vertical
x, y, r = R.centro_visual(rect(100, 50, 40, 20, 5))
assert cerca((x, y), (100, 50), 0.05) and abs(r - 10) < 0.05           # rectángulo: el centro
L = [(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)]                # forma en L
x, y, r = R.centro_visual(L)
assert R._dentro((x, y), L) and r > 0.9
c = rect(0, 0, 30, 20, 0)
hueco = rect(0, 0, 10, 10, 0)                                           # hueco en el centro
x, y, r = R.centro_visual(c, [hueco])
assert not R._dentro((x, y), hueco) and r > 2
# 3.26.2: con coordenadas de Gauss-Krüger (Misiones) el centroide no se corre
q = [(7431484.3, 7011496.3), (7431464.3, 7011489.8), (7431461.0, 7011499.4), (7431481.1, 7011505.9)]
cq = R.centroide(q)
assert R._dentro(cq, q) and cerca(cq, (sum(p[0] for p in q) / 4, sum(p[1] for p in q) / 4), 0.5), cq
assert abs(abs(R._area(q)) - abs(R._area([(x - 7431000, y - 7011000) for x, y in q]))) < 1e-6
u = R.en_poligono("0228005000001020003", 0.5, q, [], "A", med)
assert cerca(u.punto, cq, 1e-6) and u.altura == 0.5                   # en el centroide, entero
print("ok geometría: centro visual (también en L y con hueco), eje más largo, legible")

# ------------------------------------------------------------- 2. polígonos
grande = rect(100, 50, 40, 20, 5)
angosta = rect(0, 0, 40, 6, 80)                  # 6 de ancho: «0016» a 2,5 no entra horizontal
# centroide primero; si ahí no entra entero pero en el centro visual sí, ahí (la
# altura sugerida es la prioridad); si hay que achicar, en el centroide
tee = [(0, 0), (20, 0), (20, 6), (11, 6), (11, 40), (9, 40), (9, 6), (0, 6)]   # ┴: el centroide en el palo
ct = R.centroide(tee)
assert R._dentro(ct, tee) and 9 < ct[0] < 11 and ct[1] > 6
u = R.en_poligono("00001234", 2.0, tee, [], "A", med)
assert u.altura == 2.0 and u.punto[1] < 6                             # se corre a la base, entero
u = R.en_poligono("0" * 16, 2.0, tee, [], "A", med)
assert u.altura < 2.0 and cerca(u.punto, ct, 1e-6)                    # achicado: en el centroide
for modo in "ABCD":
    u = R.en_poligono("0016", 2.5, grande, [], modo, med)
    assert cerca(u.punto, (100, 50), 0.05) and u.altura == 2.5 and u.alineacion == "MIDDLE_CENTER"
    assert u.giro == (5.0 if modo == "C" else 0.0), (modo, u.giro)
uA = R.en_poligono("0016", 2.5, angosta, [], "A", med)
assert uA.giro == 0 and 0.5 < uA.altura < 2.5
# 3.26.3: el achicado ocupa el 80 % de lo que entraría justo
justo = R._escala(uA.punto, med("0016", 2.5) + 2 * R.MARGEN * 2.5, 2.5 * (1 + 2 * R.MARGEN), 0, angosta, [])
assert abs(uA.altura - 2.5 * justo * R.LLENADO) < 1e-9 and R.LLENADO == 0.8
assert R.entra(R._caja(uA.punto, med("0016", uA.altura) + 2 * R.MARGEN * uA.altura,
                       uA.altura * (1 + 2 * R.MARGEN), 0), angosta)
uB = R.en_poligono("0016", 2.5, angosta, [], "B", med)
assert abs(uB.giro - 80) < 1e-6 and uB.altura == 2.5                    # rotado, entra entero
uC = R.en_poligono("0016", 2.5, angosta, [], "C", med)
assert abs(uC.giro - 80) < 1e-6 and uC.altura == 2.5
assert R.en_poligono("0016", 2.5, angosta, [], "D", med) is None        # se omite
# B: rotado tampoco entra entero -> se achica con la nueva orientación
uB2 = R.en_poligono("0016" * 6, 2.5, angosta, [], "B", med)
assert abs(uB2.giro - 80) < 1e-6 and uB2.altura < 2.5
# C: todos con el eje, aunque horizontal entraran
uC2 = R.en_poligono("1", 1.0, rect(0, 0, 40, 30, 20), [], "C", med)
assert abs(uC2.giro - 20) < 1e-6 and uC2.altura == 1.0
# con un hueco en el medio, el texto no lo pisa
u = R.en_poligono("0001", 2.0, c, [hueco], "A", med)
caja = R._caja(u.punto, med("0001", u.altura), u.altura, 0)
assert R.entra(caja, c, [hueco])
print("ok polígonos: A achica horizontal, B rota y achica, C según el eje, D omite; huecos")

# ------------------------------------------------------------- 3. líneas y puntos
u = R.en_linea(2.0, [(0, 0), (10, 0), (20, 0)], "sobre")
assert cerca(u.punto, (10, 0)) and u.giro == 0 and u.alineacion == "MIDDLE_CENTER"
u = R.en_linea(2.0, [(0, 0), (20, 0)], "arriba")
assert cerca(u.punto, (10, 2.0))
u = R.en_linea(2.0, [(0, 0), (20, 0)], "abajo")
assert cerca(u.punto, (10, -2.0))
u = R.en_linea(2.0, [(20, 0), (0, 0)], "arriba")                       # dibujada al revés
assert u.giro == 0 and cerca(u.punto, (10, 2.0))                        # igual se lee y va arriba
u = R.en_linea(2.0, [(0, 0), (0, 10), (10, 10)], "sobre")               # la mitad cae en el codo
assert cerca(u.punto, (0, 10)) and u.giro == 90
u = R.en_linea(2.0, [(0, 0), (0, 4), (16, 4)], "sobre")                 # mitad en el 2.º tramo
assert cerca(u.punto, (6, 4)) and u.giro == 0
u = R.en_punto(2.0, (5, 5), "centro")
assert u.punto == (5, 5) and u.alineacion == "MIDDLE_CENTER" and u.giro == 0
assert R.en_punto(2.0, (5, 5), "desde").alineacion == "MIDDLE_LEFT"
op = R.OpcionesRotulo("B", "abajo", "desde")
assert R.ubicar("x", 1, [([(0, 0), (4, 0), (4, 4), (0, 4)], True)], op, med).alineacion == "MIDDLE_CENTER"
assert cerca(R.ubicar("x", 1, [([(0, 0), (4, 0)], False)], op, med).punto, (2, -1))
assert R.ubicar("x", 1, [([(3, 3)], False)], op, med).alineacion == "MIDDLE_LEFT"
assert R.ubicar("x", 1, [], op, med) is None
# un anillo cerrado degenerado (área 0) no es polígono: se rotula como línea
assert R.ubicar("x", 1, [([(0, 0), (4, 0), (8, 0)], True)], op, med).alineacion == "MIDDLE_CENTER"
print("ok líneas (según el eje, nunca cabeza abajo, sobre/arriba/abajo) y puntos (centro/desde)")

# ------------------------------------------------------------- 4. lo último elegido
assert R.leer_opciones() == R.OpcionesRotulo()
R.guardar_opciones(R.OpcionesRotulo("C", "arriba", "desde"))
assert R.leer_opciones() == R.OpcionesRotulo("C", "arriba", "desde")
R._archivo().write_text('{"poligono": "Z", "linea": 3}', encoding="utf-8")
assert R.leer_opciones() == R.OpcionesRotulo("A", "sobre", "centro")
R._archivo().write_text("dañado", encoding="utf-8")
assert R.leer_opciones() == R.OpcionesRotulo()
assert R.medidor(None)("0001", 2.0) > 0
print("ok opciones recordadas (archivo dañado = las de siempre); medida del texto")

# ------------------------------------------------------------- 5. ROTULOSIG en un dibujo
tmp = tempfile.mkdtemp()
parcelas, red, pozos = fixtures.make_parcelas(tmp), fixtures.make_red(tmp), fixtures.make_puntos(tmp)
doc = Document(ezdxf.new("R2018")); hist = History(doc); msp = doc.modelspace()
hist.execute(IX.plan_importar(doc.doc, [parcelas, red, pozos], IX.OpcionesImportar(adoptar=False)).comando)


def rotulos(capa):
    return sorted((t for t in msp.query("TEXT") if t.dxf.layer == f"{capa}-ROTULOS"),
                  key=lambda t: t.dxf.text)


cmd, n, _o = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, R.OpcionesRotulo("A"))
hist.execute(cmd)
rot = rotulos("parcelas")
assert n == 5 and len(rot) == 5 and cmd.omitidos == 0
for i, t in enumerate(rot):                     # parcelas de 20 x 25: el centro, sin achicar
    assert t.dxf.halign == 1 and t.dxf.valign == 2 and t.dxf.rotation == 0
    if i != 2:                                  # la 2 tiene un hueco: se corre lejos de él
        assert cerca(tuple(t.dxf.align_point)[:2], (5_430_000 + i * 30 + 10, 6_300_012.5), 0.05)
    assert t.dxf.height == 2.0
# altura enorme: A achica, D omite (y lo dice)
hist.execute(HD.label_commands(doc, "parcelas", "PARTIDA", 30.0, R.OpcionesRotulo("A"))[0])
assert all(t.dxf.height < 30 and t.dxf.rotation == 0 for t in rotulos("parcelas"))
cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 30.0, R.OpcionesRotulo("D"))
hist.execute(cmd)
assert n == 0 and cmd.omitidos == 5 and old == 5 and not rotulos("parcelas")
hist.undo()
assert len(rotulos("parcelas")) == 5                                   # un deshacer
# líneas: T1 (0,0)-(10,0)-(20,5): la mitad cae en el 2.º tramo, con su ángulo, por arriba
hist.execute(HD.label_commands(doc, "red", "TRAMO", 1.0, R.OpcionesRotulo(linea="arriba"))[0])
t1 = rotulos("red")[0]
g = math.degrees(math.atan2(5, 10))
assert t1.dxf.text == "T1" and abs(t1.dxf.rotation - g) < 1e-6
# puntos: empezando en el punto, a media altura
hist.execute(HD.label_commands(doc, "pozos", "NOMBRE", 1.0, R.OpcionesRotulo(punto="desde"))[0])
p1 = rotulos("pozos")[0]
assert p1.dxf.halign == 0 and p1.dxf.valign == 2 and cerca(tuple(p1.dxf.align_point)[:2], (100, 200))
print("ok ROTULOSIG: centrados en las parcelas, A achica, D omite y avisa, líneas y puntos")

# 3.26.1: sólo los objetos elegidos, sumando a lo que ya hay
elegidos = HD.objetos_por_capa(doc, [e for e in msp if e.dxf.layer == "parcelas"][:2] + rotulos("red"))
assert list(elegidos) == ["parcelas"] and len(elegidos["parcelas"]) == 2
cmd, n, old = HD.label_commands(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo("A"), elegidos["parcelas"])
hist.execute(cmd)
assert n == 2 and old == 2 and cmd.quedan == 3 and len(rotulos("parcelas")) == 5
assert "quedan 3 de otros objetos" in HD.resumen_rotulos(cmd, n, old, "TITULAR", "parcelas", elegidos["parcelas"])
hist.undo(); assert {t.dxf.text for t in rotulos("parcelas")} == {f"01-{i:04d}" for i in range(5)}
print("ok ROTULOSIG con selección: rotula sólo esos y suma a los demás")
print("TODO OK test_rotulos")
