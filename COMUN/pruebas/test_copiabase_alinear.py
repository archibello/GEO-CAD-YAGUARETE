"""COPIABASE / PEGARENPUNTO y ALINEAR con Copia (3.44.0), sin Qt: órdenes y
alias registrados, botones en «Yaguá Edición», íconos y retiro de CAD
Copiar/Mover y Alinear y Duplicar. Lo que hacen en la capa lo prueba
ventana/banco_copiabase_qgis.py con el QGIS real."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import os, sys, re, tempfile
from pathlib import Path
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(__file__).resolve().parents[2]
GEOCAD = ROOT / "QGIS" / "codigo" / "geocad"

src = (GEOCAD / "dibujo" / "edit_commands.py").read_text(encoding="utf-8")
for linea in ("('ALIGNCOPY', ('ALINEARCOPIA', 'ALINEARYDUPLICAR', 'ALC'), AlignCopyCommand",
              "('COPYBASE', ('COPIABASE', 'COPIARCONBASE', 'CB'), CopyBaseCommand",
              "('PASTECLIP', ('PEGARENPUNTO', 'PEGARBASE', 'PB'), PasteBaseCommand"):
    assert linea in src, linea
# los alias nuevos no chocan con otros de Dibujo
alias = re.findall(r"\('([A-Z]+)', \(([^)]*)\)", src)
todos = [a for _n, al in alias for a in re.findall(r"'([^']+)'", al)]
for a in ("ALC", "CB", "PB", "ALINEARCOPIA", "COPIABASE", "PEGARENPUNTO"):
    assert todos.count(a) == 1, a
plug = (GEOCAD / "dibujo" / "plugin.py").read_text(encoding="utf-8")
assert "('COPYBASE', 'PASTECLIP')," in plug and "'ALIGN', 'ALIGNCOPY'" in plug
for ico in ("aligncopy", "copybase", "pastebase"):
    assert (GEOCAD / "dibujo" / "icons" / (ico + ".svg")).is_file(), ico
print("ok órdenes, alias sin choques, barra e íconos")

sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(GEOCAD.parent)]
from geocad import botones, submodulos
ed = list(dict(botones.DEFECTO["qgis"])["Yaguá Edición"])
# 3.47.0: la fábrica es el último estado de Fernando (las tres al final de Yaguá Edición)
assert ed[-3:] == ["dibujo:copybase", "dibujo:pastebase", "dibujo:aligncopy"]
assert "dibujo:align" in ed and "dibujo:aligncopy" in ed
assert len(ed) == len(set(ed))
assert {"cad_copy_move", "align_duplicate_plugin"} <= set(submodulos.VIEJOS["dibujo"])
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
for n in ("cad_copy_move", "align_duplicate_plugin", "Ajeno"):
    (plugins / n).mkdir()
assert submodulos.retirar_viejos("dibujo", plugins) == ["cad_copy_move", "align_duplicate_plugin"]
assert (plugins / "Ajeno").is_dir()             # lo que no es de GeoCAD se queda
print("ok botones en Yaguá Edición y retiro de los sueltos")
print("TODO OK")
