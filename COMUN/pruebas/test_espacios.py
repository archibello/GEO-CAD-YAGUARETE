"""Espacio de cada herramienta: lo elegido y su archivo, sin QGIS. Las ventanas de
verdad se miden en ventana/banco_espacios_qgis_real.py."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, tempfile
os.environ["HOME"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [HERE, os.path.join(HERE, "fake_qgis"), str(RAIZ / "QGIS" / "codigo")]
from geocad import espacios as E

N = E.IDS_NATIVAS
assert N == ("geocad:imgbase_mover", "geocad:imgbase_bloquear", "geocad:imgbase_guardar",
             "geocad:pegartabla", "geocad:copiartabla")
for _c, _t, icono in E.NATIVAS:
    assert (E.ICONOS / icono).is_file()
assert [n for _e, n in E.NOMBRES] == ["Espacio Presentaciones", "Espacio Modelo"]

# ---- de fábrica: las nativas en Presentaciones, todo lo demás en Modelo
e = E.leer()
assert e == {"espacios": {}, "ocultas": set()}
assert all(E.espacio(e, b) == E.PRESENTACION and E.visible_en_presentacion(e, b) for b in N)
assert E.espacio(e, "dibujo:line") == E.MODELO and not E.visible_en_presentacion(e, "dibujo:line")
assert E.de_espacio(e, E.PRESENTACION, ["dibujo:line"] + list(N)) == list(N)
assert E.de_espacio(e, E.MODELO, ["dibujo:line"] + list(N)) == ["dibujo:line"]

# ---- se guarda y se recupera, cualquier herramienta
e["espacios"].update({"geocad:pegartabla": E.MODELO, "dibujo:line": E.PRESENTACION})
e["ocultas"].add("geocad:imgbase_guardar")
E.guardar(e)
f = E.leer()
assert f == e
assert E.visible_en_presentacion(f, "dibujo:line") and not E.visible_en_presentacion(f, "geocad:pegartabla")
assert not E.visible_en_presentacion(f, "geocad:imgbase_guardar") and E.espacio(f, "geocad:imgbase_guardar") == E.PRESENTACION
assert E.de_espacio(f, E.PRESENTACION, ["x:y", "dibujo:line"] + list(N)) == [
    "geocad:imgbase_mover", "geocad:imgbase_bloquear", "geocad:imgbase_guardar", "geocad:copiartabla", "dibujo:line"]
assert not [n for n in os.listdir(E.archivo().parent) if n.startswith(".espacios-")]

# ---- la ventana principal pierde sólo lo elegido explícitamente para Presentaciones
assert E.fuera_de_modelo(f) == {"dibujo:line"}             # una nativa sin elección sigue en su categoría
assert E.fuera_de_modelo({"espacios": {N[0]: E.PRESENTACION, N[1]: E.MODELO}, "ocultas": set()}) == {N[0]}
dist = [("Yaguá Dibujo", ["dibujo:line", "dibujo:arc"]), ("Otra", ["a:b"])]
assert E.sin_presentacion(dist, [], set()) is dist
assert E.sin_presentacion(None, [], set()) is None
assert E.sin_presentacion(dist, [], {"dibujo:line"}) == [("Yaguá Dibujo", ["dibujo:arc"]), ("Otra", ["a:b"])]
# con las barras de fábrica (None) también se saca; los bancos no son barras
fab = [("Barra", ["dibujo:line", "c:d"]), ("banco:Dibujo", ["dibujo:line"])]
assert E.sin_presentacion(None, fab, {"dibujo:line"}) == [("Barra", ["c:d"])]

# ---- una barra por categoría en la presentación, y una para lo que no tiene categoría
cats = [("Yaguá Texto", ["t:a", "t:b"]), ("Yaguá Dibujo", ["d:a"]), ("Vacía", [])]
assert E.por_categoria(["d:a", "t:b", "t:a"], cats) == [("Yaguá Texto", ["t:a", "t:b"]), ("Yaguá Dibujo", ["d:a"])]
assert E.por_categoria(["d:a", "z:z"], cats) == [("Yaguá Dibujo", ["d:a"]), (E.TITULO_SIN_CATEGORIA, ["z:z"])]
assert E.por_categoria([], cats) == []

# ---- lo que guardó la 3.72.0 (claves cortas) se entiende
E.archivo().write_text('{"espacios": {"imgbase_mover": "modelo", "pegartabla": "presentacion"}, "ocultas": ["copiartabla"]}',
                       encoding="utf-8")
assert E.leer() == {"espacios": {"geocad:imgbase_mover": E.MODELO, "geocad:pegartabla": E.PRESENTACION},
                    "ocultas": {"geocad:copiartabla"}}

# ---- un archivo dañado o con basura no molesta
for malo in ("{no es json", "[1, 2]", '{"espacios": 3, "ocultas": "x"}'):
    E.archivo().write_text(malo, encoding="utf-8")
    assert E.leer() == {"espacios": {}, "ocultas": set()}, malo
E.archivo().write_text('{"espacios": {"dibujo:line": "marte", "otra": "modelo", "geocad:copiartabla": "modelo"}, '
                       '"ocultas": ["otra", 7, "geocad:pegartabla"]}', encoding="utf-8")
assert E.leer() == {"espacios": {"geocad:copiartabla": E.MODELO}, "ocultas": {"geocad:pegartabla"}}

print("TODO OK espacios")
