from pathlib import Path
import sys, os, tempfile
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo"), os.path.dirname(__file__)]
from fixtures import make_parcelas, make_red, make_puntos
from geocad import shpio

def roundtrip(shp):
    sf = shpio.Shapefile(shp)
    rows = list(zip(sf.contents, sf.dbf_records))
    s, x, d = shpio.build_files(sf, rows)
    p = sf.paths
    assert s == p["shp"].read_bytes(), "shp distinto"
    assert x == p["shx"].read_bytes(), "shx distinto"
    orig = p["dbf"].read_bytes()
    assert d[:1] == orig[:1] and d[4:] == orig[4:], "dbf distinto"
    # re-encode de cada geometría también idéntico
    for c in sf.contents:
        g = shpio.parse_geometry(c)
        assert shpio.encode_geometry(g, sf.has_m) == c, (sf.shape_type, g)
    return sf

with tempfile.TemporaryDirectory() as t:
    sf = roundtrip(make_parcelas(t)); print(sf.encoding, sf.fields[1], sf.attributes(2), sf.geometry(2).parts[1][:2])
    sf = roundtrip(make_red(t)); print("has_m", sf.has_m, sf.geometry(0).z)
    sf = roundtrip(make_puntos(t)); print(sf.attributes(1))
    sf = shpio.Shapefile(os.path.join(t, "parcelas.shp"))
    f = sf.field("SUP_M2")
    print(shpio.encode_value(f, "1234,5", sf.encoding))
    for bad in [("SUP_M2", "abc"), ("MANZANA", "12.5"), ("MANZANA", "123456"), ("TITULAR", "x" * 21), ("FECHA", "31/02/2024")]:
        try: shpio.encode_value(sf.field(bad[0]), bad[1], sf.encoding); print("NO FALLÓ", bad)
        except shpio.ShapefileError as e: print("ok rechazo:", e)
print("OK")
