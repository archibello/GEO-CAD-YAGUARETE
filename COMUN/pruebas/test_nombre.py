"""GEO-CAD-YAGUARETÉ (3.8.0): el nombre que se ve en los dos programas, los
créditos en metadata.txt de QGIS y la ventana «Acerca de...». Por dentro
sigue siendo «geocad» (carpeta, órdenes, archivos de Actualizar)."""
import importlib.util
import re
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("nombre", ROOT / "COMUN" / "nucleo" / "nombre.py")
N = importlib.util.module_from_spec(spec); spec.loader.exec_module(N)

assert N.NOMBRE == "GEO-CAD-YAGUARETÉ" and N.NOMBRE_CORTO == "GeoCAD Yaguareté"

# el núcleo está copiado igual a los dos lados
for lado in ("QGIS", "INGECAD"):
    assert (ROOT / lado / "codigo" / "geocad" / "nombre.py").read_bytes() == \
        (ROOT / "COMUN" / "nucleo" / "nombre.py").read_bytes(), lado

# texto (IngeCAD, línea de comandos) y html (ventana)
t = N.texto_acerca("ingecad", "3.8.0", "Puente, Datos")
for parte in ("GEO-CAD-YAGUARETÉ 3.8.0 para IngeCAD", "Puente, Datos", "Arq. Fernando Pablo Bellocchio",
              "Posadas, Misiones, Argentina", "GPL-3.0-or-later",
              "https://github.com/archibello/GEO-CAD-YAGUARETE", "/issues", "Claude"):
    assert parte in t, parte
h = N.html_acerca("qgis", "3.8.0")
assert 'href="https://github.com/archibello/GEO-CAD-YAGUARETE/issues"' in h and "Para QGIS" in h
print("ok textos")


# la ventana, con un QtWidgets de mentira
class W:
    hechos = []
    def __init__(self, *a): self.a = a; W.hechos.append(self)
    def __getattr__(self, n):
        return lambda *a, **k: W.hechos.append((n, a))
class Senal:
    def connect(self, f): pass
class Botones(W):
    StandardButton = types.SimpleNamespace(Close=1)
    accepted = rejected = Senal()
Qt = types.SimpleNamespace(QDialog=W, QVBoxLayout=W, QLabel=W, QDialogButtonBox=Botones)
N.mostrar_acerca(Qt, None, "qgis", "3.8.0", "Puente")
llamadas = [x for x in W.hechos if isinstance(x, tuple)]
assert ("setWindowTitle", ("Acerca de GEO-CAD-YAGUARETÉ",)) in llamadas
assert ("setOpenExternalLinks", (True,)) in llamadas and ("exec", ()) in llamadas
print("ok ventana")

# QGIS: metadata con créditos; sin el correo personal
meta = (ROOT / "QGIS" / "codigo" / "geocad" / "metadata.txt").read_text(encoding="utf-8")
assert "name=GEO-CAD-YAGUARETÉ\n" in meta and "gmail" not in meta
assert re.search(r"^author=Arq\. Fernando Pablo Bellocchio", meta, re.M)
assert "email=19672761+archibello@users.noreply.github.com" in meta
for k in ("homepage", "repository"):
    assert f"{k}=https://github.com/archibello/GEO-CAD-YAGUARETE\n" in meta, k
assert "tracker=https://github.com/archibello/GEO-CAD-YAGUARETE/issues" in meta

# menú corto; lo interno no cambia (estado de barras guardado, Actualizar)
plug = (ROOT / "QGIS" / "codigo" / "geocad" / "plugin.py").read_text(encoding="utf-8")
assert "MENU_TITLE = nombre.NOMBRE_CORTO" in plug and "nombre.mostrar_acerca(" in plug
assert 'setObjectName("GeoCADMenu")' in plug and 'setObjectName("GeoCADToolbar")' in plug
act = (ROOT / "COMUN" / "nucleo" / "actualizar.py").read_text(encoding="utf-8")
assert "GeoCAD_{_V}" in act and "geocad_qgis_" in act
ing = (ROOT / "INGECAD" / "codigo" / "geocad" / "__init__.py").read_text(encoding="utf-8")
assert 'PLUGIN_ID = "geocad"' in ing and 'name="GeoCAD Yaguareté"' in ing
print("ok metadata y nombres internos")
print("TODO OK test_nombre")
