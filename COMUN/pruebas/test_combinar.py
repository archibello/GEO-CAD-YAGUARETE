"""UNIR (J) con polígonos, la cuenta del núcleo (3.96.0), la misma en IngeCAD y
QGIS: como «Combinar objetos espaciales» de QGIS, con los datos del polígono
de MAYOR superficie; se rellenan los huecos encerrados entre los polígonos
(ranuras de la digitalización), se respetan los que cada uno ya tenía y los
grupos aislados quedan aparte, cada uno con su mayor. Python puro."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile, time, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("combinar", ROOT / "COMUN" / "nucleo" / "combinar.py")
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)


def sup(isla):
    return isla["superficie"]


def cuadro(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


# ---- 1. el caso de las capturas de Fernando (26/11/2026) -------------------------------------
# cuatro parcelas que se tocan en los vértices; entre vértices los bordes se
# separan unos centímetros: ranuras encerradas que hay que rellenar
E, N = 14522900.0, 9977200.0
A = [(E, N), (E + 10, N), (E + 10, N + 6), (E + 4.7, N + 6), (E, N + 6)]
B = [(E, N + 6), (E + 4.7, N + 6), (E + 4.7, N + 12), (E, N + 12)]
Cc = [(E + 4.7, N + 6), (E + 4.72, N + 9), (E + 4.7, N + 12), (E + 10, N + 12), (E + 10, N + 6)]
D = [(E + 10, N), (E + 14, N), (E + 14, N + 12), (E + 10, N + 12), (E + 10.01, N + 6)]
islas = C.combinar({1: [A], 2: [B], 3: [Cc], 4: [D]})
assert len(islas) == 1, islas
i = islas[0]
assert i["jefe"] == 1 and sorted(i["miembros"]) == [1, 2, 3, 4] and i["miembros"][0] == 1
assert i["rellenos"] == 2 and len(i["anillos"]) == 1
assert abs(sup(i) - 14 * 12) < 1e-6, sup(i)
assert len(i["anillos"][0]) == 8, i["anillos"][0]   # como QGIS: quedan los vértices de los linderos
assert C.area_con_signo(i["anillos"][0]) > 0              # borde antihorario
print("ok parcelas con ranuras: una sola, ranuras rellenas, datos de la mayor")

# ---- 2. manda la MAYOR superficie, no el orden ni la cantidad de vértices -----------------
chico = [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (2, 1), (1, 1), (0, 1)]   # 3 m², 8 vértices
grande = cuadro(3, 0, 5, 5)                                                 # 25 m²
islas = C.combinar({"a": [chico], "b": [grande]})
assert len(islas) == 1 and islas[0]["jefe"] == "b" and islas[0]["miembros"] == ["b", "a"]
assert abs(sup(islas[0]) - 28) < 1e-9 and islas[0]["rellenos"] == 0
print("ok datos del de mayor superficie")

# ---- 3. huecos: el propio se respeta, el encerrado entre polígonos se rellena ------------
dona = [cuadro(0, 0, 10, 10), cuadro(4, 4, 2, 2)]
islas = C.combinar({1: dona, 2: [cuadro(10, 0, 10, 10)]})
assert len(islas) == 1 and islas[0]["jefe"] == 2 and len(islas[0]["anillos"]) == 2
assert islas[0]["rellenos"] == 0 and abs(sup(islas[0]) - 196) < 1e-9
assert C.area_con_signo(islas[0]["anillos"][1]) < 0      # hueco horario
# anillo de cuatro piezas alrededor de un patio vacío: el patio se rellena
marco = {1: [cuadro(0, 0, 10, 2)], 2: [cuadro(0, 8, 10, 2)], 3: [cuadro(0, 2, 2, 6)], 4: [cuadro(8, 2, 2, 6)]}
islas = C.combinar(marco)
assert len(islas) == 1 and islas[0]["rellenos"] == 1 and len(islas[0]["anillos"]) == 1
assert abs(sup(islas[0]) - 100) < 1e-9
# parte del hueco propio tapado por otro: lo que queda del hueco se respeta
islas = C.combinar({1: dona, 2: [cuadro(5, 4, 1, 2)]})
assert len(islas) == 1 and len(islas[0]["anillos"]) == 2 and abs(sup(islas[0]) - 98) < 1e-9
print("ok huecos propios se respetan; los encerrados se rellenan")

# ---- 4. islas: aislados aparte, cada uno con su mayor; un punto no une ------------------
islas = C.combinar({1: [cuadro(0, 0, 4, 4)], 2: [cuadro(4, 0, 2, 2)],      # se tocan: 1 manda
                    3: [cuadro(50, 0, 1, 1)], 4: [cuadro(51, 0, 3, 1)],     # otro grupo: 4 manda
                    5: [cuadro(100, 0, 1, 1)]})                             # solo
por_jefe = {i["jefe"]: i for i in islas}
assert sorted(por_jefe) == [1, 4, 5], por_jefe.keys()
assert por_jefe[1]["miembros"] == [1, 2] and por_jefe[4]["miembros"] == [4, 3]
assert por_jefe[5]["sin_cambio"] and not por_jefe[1]["sin_cambio"]
islas = C.combinar({1: [cuadro(0, 0, 2, 2)], 2: [cuadro(2, 2, 3, 3)]})     # sólo una esquina
assert len(islas) == 2 and all(i["sin_cambio"] for i in islas)
# isla dentro del hueco de otro, sin tocarlo: aparte, y el hueco queda
islas = C.combinar({1: [cuadro(0, 0, 10, 10), cuadro(2, 2, 6, 6)], 2: [cuadro(4, 4, 1, 1)]})
assert len(islas) == 2 and all(i["sin_cambio"] for i in islas)
print("ok islas aparte; tocarse en un punto no une")

# ---- 5. superpuestos, contactos en T y en UTM ------------------------------------------
islas = C.combinar({1: [cuadro(0, 0, 4, 4)], 2: [cuadro(2, 2, 4, 4)]})      # se pisan
assert len(islas) == 1 and abs(sup(islas[0]) - 28) < 1e-9 and len(islas[0]["anillos"][0]) == 8
x, y = 5500000.0, 6950000.0
islas = C.combinar({1: [cuadro(x, y, 10, 10)],                               # T: el vértice de 2
                    2: [[(x + 10, y + 3), (x + 15, y + 3), (x + 15, y + 7), (x + 10, y + 7)]],
                    3: [[(x + 15 + 4e-4, y + 3), (x + 20, y + 3), (x + 20, y + 7), (x + 15, y + 7)]]})
assert len(islas) == 1 and abs(sup(islas[0]) - 140) < 1e-3, islas         # 0,4 mm: se pegan
islas = C.combinar({1: [cuadro(x, y, 10, 10)], 2: [cuadro(x + 10.01, y, 5, 5)]})
assert len(islas) == 2                                                      # a 1 cm: no
print("ok superpuestos, contactos en T y tolerancia en UTM")

# ---- 6. qué hacer en la capa original (lo usan IngeCAD y QGIS) --------------------------
islas = C.combinar({1: [cuadro(0, 0, 4, 4)], 2: [cuadro(4, 0, 2, 2)], 5: [cuadro(100, 0, 1, 1)],
                    # un objeto de dos partes: una se une con 7 (mayor), la otra queda sola
                    6: [cuadro(20, 0, 1, 1), cuadro(30, 0, 1, 1)], 7: [cuadro(21, 0, 3, 3)]})
cambiar, crear, borrar = C.plan_original(islas)
assert sorted(f for f, _i in cambiar) == [1, 6, 7], cambiar     # 6 pierde la parte unida a 7
assert crear == [] and sorted(borrar) == [2]
# el objeto de dos partes manda en las dos islas: la segunda pasa a ser un objeto
# nuevo con sus mismos datos (islas aparte, no unidas)
islas = C.combinar({6: [cuadro(20, 0, 3, 3), cuadro(30, 0, 1, 1)], 7: [cuadro(23, 0, 1, 1)]})
cambiar, crear, borrar = C.plan_original(islas)
assert [f for f, _i in cambiar] == [6] and borrar == [7] and [f for f, _i in crear] == [6]
assert len(cambiar[0][1]["miembros"]) == 2 and crear[0][1]["sin_cambio"]
print("ok plan para la capa original")

# ---- 7. nombre y lugar de la capa nueva ---------------------------------------------------
assert C.nombre_combinados(" Parcelas ") == "combinados de Parcelas"
d = tempfile.mkdtemp()
assert C.archivo_libre(d, "combinados de P") == os.path.join(d, "combinados de P.gpkg")
open(os.path.join(d, "combinados de P.gpkg"), "w").close()
assert C.archivo_libre(d, "combinados de P") == os.path.join(d, "combinados de P (2).gpkg")
prj = os.path.join(d, "obra.qgz"); open(prj, "w").close()
shp = os.path.join(tempfile.mkdtemp(), "lotes.shp"); open(shp, "w").close()
assert C.carpeta_para(prj, shp) == d
assert C.carpeta_para("", shp + "|layerid=0") == os.path.dirname(shp)
casa = tempfile.mkdtemp(); os.mkdir(os.path.join(casa, "Documentos"))
assert C.carpeta_para("", "", casa) == os.path.join(casa, "Documentos", "GeoCAD")
assert C.carpeta_para("", "", tempfile.mkdtemp()).endswith("GeoCAD")
print("ok nombre «combinados de» y carpeta")

# ---- 8. tiempo: una manzana de 20 x 20 parcelas -------------------------------------------
objs = {}
for i in range(20):
    for j in range(20):
        objs[i * 20 + j] = [cuadro(x + i * 10, y + j * 15, 10, 15)]
t = time.time()
islas = C.combinar(objs)
dt = time.time() - t
assert len(islas) == 1 and abs(sup(islas[0]) - 200 * 300) < 1e-3 and len(islas[0]["anillos"][0]) == 80
assert dt < 20, dt
print("ok 400 parcelas en %.1f s" % dt)
print("TODO OK")
