"""Shapefiles de prueba generados con pyshp (lector/escritor independiente)."""
import shapefile, os

def make_parcelas(folder, name="parcelas"):
    path = os.path.join(folder, name)
    w = shapefile.Writer(path, shapeType=shapefile.POLYGON, encoding="utf-8")
    w.field("PARTIDA", "C", size=12)
    w.field("TITULAR", "C", size=20)
    w.field("SUP_M2", "N", size=12, decimal=2)
    w.field("MANZANA", "N", size=4, decimal=0)
    w.field("FECHA", "D")
    w.field("EDIFICADO", "L")
    base_x, base_y = 5_430_000.0, 6_300_000.0   # POSGAR 2007 faja 5 aprox.
    for i in range(5):
        x0 = base_x + i * 30.0
        ring = [(x0, base_y), (x0, base_y + 25), (x0 + 20, base_y + 25), (x0 + 20, base_y), (x0, base_y)]
        if i == 2:  # con hueco
            hole = [(x0 + 5, base_y + 5), (x0 + 10, base_y + 5), (x0 + 10, base_y + 10), (x0 + 5, base_y + 10), (x0 + 5, base_y + 5)]
            w.poly([ring, hole])
        else:
            w.poly([ring])
        w.record(f"01-{i:04d}", ["Pérez", "Gómez", "Núñez", "Ibáñez", "Ruiz"][i], 500.0 + i, 12, "20240115", i % 2 == 0)
    w.close()
    with open(path + ".cpg", "w") as fh: fh.write("UTF-8")
    with open(path + ".prj", "w") as fh: fh.write('PROJCS["POSGAR_2007_Argentina_5",GEOGCS["GCS_POSGAR_2007"]]')
    return path + ".shp"

def make_red(folder, name="red"):
    path = os.path.join(folder, name)
    w = shapefile.Writer(path, shapeType=shapefile.POLYLINEZ)
    w.field("TRAMO", "C", size=8); w.field("DIAM", "N", size=5, decimal=0)
    w.linez([[(0, 0, 10.0), (10, 0, 10.5), (20, 5, 11.0)]]); w.record("T1", 110)
    w.linez([[(20, 5, 11.0), (30, 5, 11.2)]]); w.record("T2", 160)
    w.close()
    return path + ".shp"

def make_puntos(folder, name="pozos"):
    path = os.path.join(folder, name)
    w = shapefile.Writer(path, shapeType=shapefile.POINT)
    w.field("ID", "N", size=6, decimal=0); w.field("NOMBRE", "C", size=10)
    for i in range(3):
        w.point(100.0 + i, 200.0 + i * 2); w.record(i + 1, f"P{i+1}")
    w.close()
    return path + ".shp"
