"""Rótulos estandarizados (3.26.0, reglas de Fernando del 16/10/2026).
Polígonos cerrados (3.48.1): en el epicentro y según el eje más largo,
achicando ahí los que no entran (sin opciones A-E); con círculo (3.48.0);
altura del más chico y conservar los anteriores (3.48.1). Líneas: según el eje, en la mitad, sobre / arriba /
abajo, nunca cabeza abajo. Puntos: centrado o desde el punto a media
altura. ROTULOSIG los dibuja así y recuerda lo último elegido."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
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
u = R.en_poligono("0228005000001020003", 0.5, q, [], med)
assert cerca(u.punto, cq, 1e-6) and u.altura == 0.5                   # en el centroide, entero
print("ok geometría: centro visual (también en L y con hueco), eje más largo, legible")

# ------------------------------------------------------------- 2. polígonos
# 3.48.1 (Fernando, 25/10/2026): en el epicentro y según el eje más largo, siempre;
# los que no entran se achican ahí mismo
grande = rect(100, 50, 40, 20, 5)
angosta = rect(0, 0, 40, 6, 80)
u = R.en_poligono("0016", 2.5, grande, [], med)
assert cerca(u.punto, (100, 50), 1e-6) and u.altura == 2.5 and abs(u.giro - 5) < 1e-6
assert u.alineacion == "MIDDLE_CENTER" and u.circulo is None
u = R.en_poligono("0016", 2.5, angosta, [], med)
assert cerca(u.punto, (0, 0), 1e-6) and abs(u.giro - 80) < 1e-6 and u.altura == 2.5
uC = R.en_poligono("1", 1.0, rect(0, 0, 40, 30, 20), [], med)               # aunque horizontal entraba
assert abs(uC.giro - 20) < 1e-6 and uC.altura == 1.0
# no entra: achicado EN EL EPICENTRO (antes se corría al centro visual), según el eje
tee = [(0, 0), (20, 0), (20, 6), (11, 6), (11, 40), (9, 40), (9, 6), (0, 6)]   # ┴: el centroide en el palo
ct = R.centroide(tee)
assert R._dentro(ct, tee) and 9 < ct[0] < 11 and ct[1] > 6
# 3.51.0: el centro visual (en la base) no sirve: según el eje (vertical) ahí entra más chico
# que en el palo; se queda en el epicentro
u = R.en_poligono("00001234", 2.0, tee, [], med)
assert cerca(u.punto, ct, 1e-6) and u.altura < 2.0 and abs(u.giro - R.eje_mas_largo(tee)) < 1e-6
# 3.51.0 (Fernando, la 001): parcela en L con el centroide en el rincón interior. Antes
# quedaba diminuta en el rincón; ahora, en el lugar más holgado y con la altura pedida
# (igual que sus vecinas); con círculo, igual
ele = [(0, 0), (60, 0), (60, 60), (35, 60), (35, 25), (0, 25)]               # brazos de 25
ce = R.centroide(ele)
assert R._dentro(ce, ele) and R._dist_borde(ce, [ele]) < 3, ce          # el centroide, pegado al rincón
for circ in (False, True):
    u = R.en_poligono("001", 5.0, ele, [], med, circ)
    assert u.altura == 5.0 and not cerca(u.punto, ce, 1.0), (circ, u)
    assert cerca(u.punto, R.centro_visual(ele)[:2], 1e-6), (circ, u.punto)
# una mejora chica (menos del 20 %) no lo mueve del epicentro
assert R.MEJORA_VISUAL == 1.20
# 3.26.3: el achicado ocupa el 80 % de lo que entraría justo
u = R.en_poligono("0016" * 6, 2.5, angosta, [], med)
justo = R._escala(u.punto, med("0016" * 6, 2.5) + 2 * R.MARGEN * 2.5, 2.5 * (1 + 2 * R.MARGEN), u.giro, angosta, [])
assert u.altura < 2.5 and abs(u.altura - 2.5 * justo * R.LLENADO) < 1e-9 and R.LLENADO == 0.8
assert R.entra(R._caja(u.punto, med("0016" * 6, u.altura) + 2 * R.MARGEN * u.altura,
                       u.altura * (1 + 2 * R.MARGEN), u.giro), angosta)
# centroide afuera (U): en el centro visual
U = [(0, 0), (30, 0), (30, 20), (24, 20), (24, 6), (6, 6), (6, 20), (0, 20)]
assert not R._dentro(R.centroide(U), U)
u = R.en_poligono("1", 1.0, U, [], med)
assert R._dentro(u.punto, U) and cerca(u.punto, R.centro_visual(U)[:2], 1e-6)
# centroide en un hueco: el centro visual, y el texto no pisa el hueco
u = R.en_poligono("0001", 2.0, c, [hueco], med)
assert not R._dentro(u.punto, hueco)
assert R.entra(R._caja(u.punto, med("0001", u.altura), u.altura, u.giro), c, [hueco])
# centroide justo en el borde de un hueco (ni achicado entra): el centro visual
cuad = rect(0, 0, 20, 30, 0)
hb = [(0, -3), (5, -3), (5, 3), (0, 3)]             # el borde x=0 pasa por el centroide
u = R.en_poligono("0001", 1.0, cuad, [hb], med)
assert u is not None and not cerca(u.punto, (0, 0), 0.5)
# ilegible en todos lados: se omite
assert R.en_poligono("0016", 2.5, rect(0, 0, 0.01, 0.01, 0), [], med) is None
print("ok polígonos: epicentro y eje más largo; achica ahí; U y huecos al centro visual")

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
op = R.OpcionesRotulo("abajo", "desde")
assert R.ubicar("x", 1, [([(0, 0), (4, 0), (4, 4), (0, 4)], True)], op, med).alineacion == "MIDDLE_CENTER"
assert cerca(R.ubicar("x", 1, [([(0, 0), (4, 0)], False)], op, med).punto, (2, -1))
assert R.ubicar("x", 1, [([(3, 3)], False)], op, med).alineacion == "MIDDLE_LEFT"
assert R.ubicar("x", 1, [], op, med) is None
# un anillo cerrado degenerado (área 0) no es polígono: se rotula como línea
assert R.ubicar("x", 1, [([(0, 0), (4, 0), (8, 0)], True)], op, med).alineacion == "MIDDLE_CENTER"
print("ok líneas (según el eje, nunca cabeza abajo, sobre/arriba/abajo) y puntos (centro/desde)")

# ------------------------------------------------------------- 4. lo último elegido
assert R.leer_opciones() == R.OpcionesRotulo()
R.guardar_opciones(R.OpcionesRotulo("arriba", "desde"))
assert R.leer_opciones() == R.OpcionesRotulo("arriba", "desde")
todo = R.OpcionesRotulo("arriba", "desde", circulo="si", anteriores="conservar")
R.guardar_opciones(todo)                                        # 3.48.0 y 3.48.1
assert R.leer_opciones() == todo and todo.altura == "achicados"
# 3.53.0: la altura es siempre como Enviar a IngeCAD; lo guardado antes («propia», «menor»)
# vuelve así, sin romper nada
for vieja in ("propia", "menor"):
    R.guardar_opciones(R.OpcionesRotulo("arriba", "desde", circulo="si", altura=vieja))
    assert R.leer_opciones().altura == "achicados", vieja
# lo guardado antes de la 3.48.1 (con «poligono» A-E): se ignora, sin romper nada
R._archivo().write_text('{"poligono": "D", "linea": "abajo", "punto": 3}', encoding="utf-8")
assert R.leer_opciones() == R.OpcionesRotulo("abajo", "centro")
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


cmd, n, _o = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, R.OpcionesRotulo())
hist.execute(cmd)
rot = rotulos("parcelas")
assert n == 5 and len(rot) == 5 and cmd.omitidos == 0
alturas = []
for i, t in enumerate(rot):     # parcelas de 20 x 25: en el epicentro, según el eje (vertical)
    assert t.dxf.halign == 1 and t.dxf.valign == 2 and t.dxf.rotation == 90
    epi = (5_430_000 + i * 30 + 10, 6_300_012.5)
    assert cerca(tuple(t.dxf.align_point)[:2], epi, 1e-6) == (i != 2), (i, t.dxf.align_point)
    alturas.append(t.dxf.height)
# la 2 tiene un hueco al lado del epicentro: en la 3.48.1 se achicaba ahí; desde la 3.51.0
# va al centro visual, con la misma altura que sus vecinas y sin pisar el hueco
assert all(h == 2.0 for h in alturas), alturas
t2 = rot[2]; hueco2 = [(5_430_065, 6_300_005), (5_430_070, 6_300_005), (5_430_070, 6_300_010), (5_430_065, 6_300_010)]
assert R.entra(R._caja(tuple(t2.dxf.align_point)[:2], med(t2.dxf.text, 2.0), 2.0, 90),
               rect(5_430_070, 6_300_012.5, 20, 25, 0), [hueco2])
# altura enorme: todos achicados en su epicentro, ninguno omitido
cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 30.0, R.OpcionesRotulo())
hist.execute(cmd)
assert n == 5 and old == 5 and cmd.omitidos == 0
assert all(t.dxf.height < 30 and t.dxf.rotation == 90 for t in rotulos("parcelas"))
hist.undo()
assert [t.dxf.height for t in rotulos("parcelas")] == alturas                # un deshacer
# 3.48.1: todos con la altura del más chico
cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, R.OpcionesRotulo(altura="menor"))
hist.execute(cmd)
assert n == 5 and {t.dxf.height for t in rotulos("parcelas")} == {min(alturas)}
hist.undo()
# 3.48.1: conservar los anteriores, sumando los nuevos
cmd, n, old = HD.label_commands(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(anteriores="conservar"))
hist.execute(cmd)
assert n == 5 and old == 0 and cmd.quedan == 5 and len(rotulos("parcelas")) == 10
assert "se suman a 5 anteriores" in HD.resumen_rotulos(cmd, n, old, "TITULAR", "parcelas")
hist.undo()
assert len(rotulos("parcelas")) == 5
# líneas: T1 (0,0)-(10,0)-(20,5): la mitad cae en el 2.º tramo, con su ángulo, por arriba
hist.execute(HD.label_commands(doc, "red", "TRAMO", 1.0, R.OpcionesRotulo(linea="arriba"))[0])
t1 = rotulos("red")[0]
g = math.degrees(math.atan2(5, 10))
assert t1.dxf.text == "T1" and abs(t1.dxf.rotation - g) < 1e-6
# puntos: empezando en el punto, a media altura
hist.execute(HD.label_commands(doc, "pozos", "NOMBRE", 1.0, R.OpcionesRotulo(punto="desde"))[0])
p1 = rotulos("pozos")[0]
assert p1.dxf.halign == 0 and p1.dxf.valign == 2 and cerca(tuple(p1.dxf.align_point)[:2], (100, 200))
print("ok ROTULOSIG: en el epicentro según el eje, achica ahí, altura del más chico, conservar; líneas y puntos")

# 3.26.1: sólo los objetos elegidos, sumando a lo que ya hay
elegidos = HD.objetos_por_capa(doc, [e for e in msp if e.dxf.layer == "parcelas"][:2] + rotulos("red"))
assert list(elegidos) == ["parcelas"] and len(elegidos["parcelas"]) == 2
cmd, n, old = HD.label_commands(doc, "parcelas", "TITULAR", 2.0, R.OpcionesRotulo(), elegidos["parcelas"])
hist.execute(cmd)
assert n == 2 and old == 2 and cmd.quedan == 3 and len(rotulos("parcelas")) == 5
assert "quedan 3 de otros objetos" in HD.resumen_rotulos(cmd, n, old, "TITULAR", "parcelas", elegidos["parcelas"])
hist.undo(); assert {t.dxf.text for t in rotulos("parcelas")} == {f"01-{i:04d}" for i in range(5)}
print("ok ROTULOSIG con selección: rotula sólo esos y suma a los demás")

# ------------------------------------------------------------- 6. con círculo (3.48.0)
# Fernando, 25/10/2026: el círculo = diagonal del texto + 10 %, dentro del polígono
# con el 90 % del lugar; los que no entran, achicados dentro de su círculo


def diag(t, h):
    return math.hypot(med(t, h), h)


def borde(p, anillo):
    return min(R._dist_seg(p, anillo[i], anillo[(i + 1) % len(anillo)]) for i in range(len(anillo)))


op_c = R.OpcionesRotulo(circulo="si")
grande = rect(0, 0, 40, 40, 0)
u = R.ubicar("0002", 2.0, [(grande, True)], op_c, med)
assert cerca(u.punto, (0, 0)) and u.altura == 2.0 and u.giro == R.eje_mas_largo(grande)
assert abs(u.circulo - diag("0002", 2.0) * 1.10 / 2) < 1e-9          # el texto + 10 %
assert R.ubicar("0002", 2.0, [(grande, True)], R.OpcionesRotulo(), med).circulo is None
# chico: el círculo usa el 90 % del lugar y el texto se achica adentro, con su 10 %
chico = rect(100, 0, 6, 6, 0)
u = R.ubicar("0002", 2.0, [(chico, True)], op_c, med)
assert u is not None and cerca(u.punto, (100, 0), 1e-6)                    # en el epicentro
assert abs(u.circulo - 0.9 * 3) < 1e-9 and u.circulo <= 0.9 * borde(u.punto, chico) + 1e-9
assert u.altura < 2.0 and abs(diag("0002", u.altura) * 1.10 / 2 - u.circulo) < 1e-9
# siempre según el eje, también los achicados (3.48.1)
largo = rect(0, 0, 60, 12, 30)
u = R.ubicar("0002", 2.0, [(largo, True)], op_c, med)
assert u.altura == 2.0 and abs(u.giro - 30) < 1e-6 and u.circulo <= 0.9 * borde(u.punto, largo)
u = R.ubicar("0002" * 4, 2.0, [(largo, True)], op_c, med)
assert u.altura < 2.0 and abs(u.giro - 30) < 1e-6
# con hueco en el centroide: va al centro visual, lejos del hueco
anillo = rect(0, 0, 40, 40, 0)
hueco = rect(0, 0, 10, 10, 0)
u = R.ubicar("0002", 2.0, [(anillo, True), (hueco, True)], op_c, med)
assert u.altura == 2.0 and u.circulo <= 0.9 * min(borde(u.punto, anillo), borde(u.punto, hueco)) + 1e-9
# demasiado chico para leerse: se omite; líneas y puntos, sin círculo
assert R.ubicar("0002", 2.0, [(rect(0, 0, 0.1, 0.1, 0), True)], op_c, med) is None
assert R.ubicar("T1", 1.0, [([(0, 0), (10, 0)], False)], op_c, med).circulo is None
assert R.ubicar("P1", 1.0, [([(5, 5)], False)], op_c, med).circulo is None
print("ok círculo: texto + 10 %, 90 % del lugar, achica en el epicentro, según el eje")


def circulos(capa):
    return [c for c in msp.query("CIRCLE") if c.dxf.layer == f"{capa}-ROTULOS"]


cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, op_c)
hist.execute(cmd)
rot, cir = rotulos("parcelas"), circulos("parcelas")
assert n == 5 and old == 5 and len(rot) == 5 and len(cir) == 5          # old: textos, sin círculos
for t in rot:
    c = min(cir, key=lambda c: math.dist(tuple(c.dxf.center)[:2], tuple(t.dxf.align_point)[:2]))
    assert cerca(tuple(c.dxf.center)[:2], tuple(t.dxf.align_point)[:2])
    assert t.dxf.height <= 2.0 and c.get_xdata(HD.APPID)[0][1] == HD.LABEL_TAG
    assert c.dxf.radius >= math.hypot(R.medidor(doc.doc)(t.dxf.text, t.dxf.height), t.dxf.height) * 1.1 / 2 - 1e-9
# volver a rotular reemplaza textos y círculos; con altura enorme, todos achicados adentro
cmd, n, old = HD.label_commands(doc, "parcelas", "PARTIDA", 30.0, op_c)
hist.execute(cmd)
assert n == 5 and old == 5 and len(circulos("parcelas")) == 5 and cmd.omitidos == 0
assert all(t.dxf.height < 30 for t in rotulos("parcelas"))
assert all(c.dxf.radius <= 0.9 * 10 + 0.05 for c in circulos("parcelas"))    # parcelas de 20 de ancho
hist.undo(); hist.undo()
assert not circulos("parcelas") and len(rotulos("parcelas")) == 5           # un deshacer cada vez
# sin círculo, los círculos anteriores también se van
hist.execute(HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, op_c)[0])
hist.execute(HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, R.OpcionesRotulo())[0])
assert not circulos("parcelas") and len(rotulos("parcelas")) == 5
# conservar: los círculos de antes también se quedan; altura del más chico, con círculos
hist.execute(HD.label_commands(doc, "parcelas", "PARTIDA", 2.0, op_c)[0])
op_cc = R.OpcionesRotulo(circulo="si", altura="menor", anteriores="conservar")
hist.execute(HD.label_commands(doc, "parcelas", "TITULAR", 2.0, op_cc)[0])
assert len(circulos("parcelas")) == 10 and len(rotulos("parcelas")) == 10
nuevos = [t for t in rotulos("parcelas") if not t.dxf.text.startswith("01-")]
assert len({t.dxf.height for t in nuevos}) == 1
print("ok ROTULOSIG con círculo: en la capa de rótulos, se reemplazan y deshacen con su texto")
print("TODO OK test_rotulos")
