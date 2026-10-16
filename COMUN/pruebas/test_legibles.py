"""Textos visibles según SU tamaño (3.26.4). IngeCAD esconde los textos de
menos de 2 píxeles, pero por el PROMEDIO de cada balde (capa, color,
espesor): en una capa de rótulos con muchos chicos y algunos grandes, al
alejarse desaparecían también los grandes. Con el retoque cada escalón de
tamaño (media octava) decide por sí mismo. Se prueba con la pantalla real
de IngeCAD (render.backend, sin Qt)."""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["INGECAD_SERIAL_REGEN"] = "1"
from pathlib import Path
from importlib import import_module
import ezdxf
from core.document import Document
from core.plugins import load_plugin

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
L = import_module("ingecad_plugin_geocad.legibles")
try:
    import core.window_colors  # noqa: F401  (lee los colores con Qt)
except ImportError:                      # sin Qt: los colores de siempre
    sys.modules["core.window_colors"] = types.SimpleNamespace(
        background=lambda espacio: "#212830", rgba=lambda espacio: (0.13, 0.16, 0.19, 1.0))
from render import backend as B

# escalones: media octava
assert L.escalon(1.0) == "h+00" and L.escalon(1.5) == "h+01" and L.escalon(2.0) == "h+02"
assert L.escalon(0.3) == "h-04" and L.escalon(20) == "h+08"
assert L.escalon(0) == "" and L.escalon(None) == "" and L.escalon("x") == ""
assert L.escalon(1.0) != L.escalon(1.42) and L.escalon(1.0) == L.escalon(1.41)


def dibujo():
    doc = Document(ezdxf.new("R2018"))
    msp = doc.modelspace()
    doc.doc.layers.add("ROTULOS")
    for i in range(60):                                       # parcelas urbanas: 0,3
        msp.add_text(f"{i:04d}", height=0.3, dxfattribs={"layer": "ROTULOS",
                                                         "insert": (i * 3.0, 0)})
    for i in range(2):                                        # chacras: 20
        msp.add_text(f"CH{i}", height=20.0, dxfattribs={"layer": "ROTULOS",
                                                        "insert": (i * 200.0, 100)})
    return doc


def texto_visible(scene, px_por_unidad):
    """(vértices de texto visibles, total) con la regla de IngeCAD (2 px)."""
    b = scene.triangles
    vista = (-1e12, -1e12, 1e12, 1e12)
    runs = b.visible_runs(vista, px_por_unidad, 2.0)
    vis = sum(c for _f, c in runs)
    return vis, b.vertex_count


def alturas(scene):
    b = scene.triangles
    return sorted({round(float(h), 3) for h, t in zip(b.text_height, b.is_text) if t})


# 3.26.5: GeoCAD ya lo pone al cargarse (antes de abrir un dibujo); se saca
# para ver primero el error de IngeCAD
from ingecad_plugin_geocad.dibujo import desenvolver
for n in ("enter_entity", "exit_entity", "_bucket"):
    desenvolver(B.VertexBackend, n)
assert not hasattr(B.VertexBackend._bucket, "_puente_original")
# sin el retoque: un solo balde de texto, promedio chico
antes = B.build_scene(dibujo())
assert len(alturas(antes)) == 1, alturas(antes)
vis, total = texto_visible(antes, 0.2)        # a esta escala 20 m = 4 px; 0,3 m = 0,06 px
assert vis == 0, "IngeCAD ya agrupa por tamaño: revisar si el retoque sigue haciendo falta"

assert L.instalar() is True
assert hasattr(B.VertexBackend._bucket, "_puente_original")
assert L.instalar() is False                   # una sola vez
assert not hasattr(B.VertexBackend._bucket._puente_original, "_puente_original")
despues = B.build_scene(dibujo())
assert len(alturas(despues)) == 2, alturas(despues)              # chicos y grandes, aparte
vis, total = texto_visible(despues, 0.2)
assert vis > 0                                                   # los grandes se ven
vis_cerca, _ = texto_visible(despues, 100.0)                     # de cerca: todos
vis_lejos, _ = texto_visible(despues, 0.01)                      # muy lejos: ninguno
assert vis < vis_cerca and vis_lejos == 0
# lo que no es texto (líneas) no cambia de balde
d = dibujo(); d.doc.modelspace().add_line((0, 0), (10, 10), dxfattribs={"layer": "ROTULOS"})
assert B.build_scene(d).lines.vertex_count > 0
print("ok cada escalón de tamaño se esconde por su propia altura; de cerca todos, de lejos ninguno")

# 3.27.0: tamaño mínimo configurable (MIN_TEXT_PX de views/viewport.py, que
# IngeCAD lee en cada dibujado). Sin Qt, una pantalla de mentira.
C = import_module("ingecad_plugin_geocad.config")
assert C.BY_KEY["texto_minimo_px"].default == 6.0 and C.load()["texto_minimo_px"] == 6.0
assert C.validate("texto_minimo_px", "5,5") == 5.5 and C.validate("texto_minimo_px", 0) == 0
for malo in (-1, 51, "x"):
    try:
        C.validate("texto_minimo_px", malo)
        raise AssertionError(malo)
    except ValueError:
        pass
assert L.aplicar_minimo() is False                     # sin la pantalla: no hace nada
vp = types.SimpleNamespace(MIN_TEXT_PX=2.0)
sys.modules["views.viewport"] = vp
assert L.aplicar_minimo() is True and vp.MIN_TEXT_PX == 6.0       # el valor por defecto
assert L.aplicar_minimo() is False                     # igual: no repinta
L.escuchar_config(); L.escuchar_config()
assert C.AL_GUARDAR.count(L.aplicar_minimo) == 1       # una sola vez
C.save({"texto_minimo_px": 3}, "prueba")
assert vp.MIN_TEXT_PX == 3.0                           # al guardar, en el momento
C.save({"texto_minimo_px": 0}, "prueba")
assert vp.MIN_TEXT_PX == 0.0                           # 0 = no esconder ninguno
assert L.minimo_px({"texto_minimo_px": "x"}) == 2.0    # ilegible: el de IngeCAD
# con la regla real: a 6 px los de 20 m a 0,2 px/u (4 px) ya no se ven; a 2 px sí
assert sum(c for _f, c in despues.triangles.visible_runs((-1e12, -1e12, 1e12, 1e12), 0.2, 6.0)) == 0
assert sum(c for _f, c in despues.triangles.visible_runs((-1e12, -1e12, 1e12, 1e12), 0.2, 2.0)) > 0
# un oyente que falla no rompe el guardado
C.AL_GUARDAR.insert(0, lambda v: 1 / 0)
assert C.save({"texto_minimo_px": 6}, "prueba")["texto_minimo_px"] == 6.0 and vp.MIN_TEXT_PX == 6.0
del sys.modules["views.viewport"]
print("ok tamaño mínimo configurable (6 px), aplicado al guardar sin reiniciar")
print("TODO OK test_legibles")
