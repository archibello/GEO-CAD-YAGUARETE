"""Aviso de versiones nuevas publicadas en GitHub (3.95.0): la consulta, la
descarga de GeoCAD_<v>.zip y el aviso con sus tres botones en IngeCAD y QGIS.
GitHub se reemplaza por un servidor de mentira: la prueba no usa la red."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import io, json, os, sys, tempfile, types, shutil, zipfile, re, importlib.util
CFG = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = CFG
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
ING = ROOT / "INGECAD" / "codigo" / "geocad"
QG = ROOT / "QGIS" / "codigo" / "geocad"

spec_b = importlib.util.spec_from_file_location("build_aviso", ROOT / "COMUN" / "build.py")
build = importlib.util.module_from_spec(spec_b); spec_b.loader.exec_module(build)
build.sincronizar()


def con_version(src: Path, version: str) -> Path:
    dst = Path(tempfile.mkdtemp()) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    t = (dst / "__init__.py").read_text()
    if 'version="' in t:
        (dst / "__init__.py").write_text(re.sub(r'version="[^"]+"', f'version="{version}"', t, count=1))
    if (dst / "metadata.txt").exists():
        t = (dst / "metadata.txt").read_text()
        (dst / "metadata.txt").write_text(re.sub(r"^version=.*$", f"version={version}", t, flags=re.M))
        t = (dst / "plugin.py").read_text()
        (dst / "plugin.py").write_text(re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', t, flags=re.M))
    return dst


def entrega(version: str) -> bytes:
    """GeoCAD_<v>.zip como la arma build.py."""
    buf = io.BytesIO()
    top = f"GeoCAD_{version}"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{top}/instalar_geocad_{version}.py", build.instalador(con_version(ING, version), version))
        zf.writestr(f"{top}/opcional_QGIS_geocad_qgis_{version}.zip",
                    build.zip_folder(con_version(QG, version), "geocad"))
        zf.writestr(f"{top}/CAMBIOS_{version}.txt", f"GeoCAD {version}: trae cosas nuevas.")
    return buf.getvalue()


ZIP_999 = entrega("9.9.9")
pedidos = []


class Respuesta(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


def release(version, con_entrega=True, **extra):
    assets = [{"name": "INSTALAR_GeoCAD.sh", "size": 200,
               "browser_download_url": f"https://github.com/x/releases/download/v{version}/INSTALAR_GeoCAD.sh"}]
    if con_entrega:
        assets.append({"name": f"GeoCAD_{version}.zip", "size": len(ZIP_999),
                       "browser_download_url": f"https://github.com/x/releases/download/v{version}/GeoCAD_{version}.zip"})
    d = {"tag_name": f"v{version}", "html_url": f"https://github.com/x/releases/tag/v{version}",
         "draft": False, "prerelease": False, "assets": assets}
    d.update(extra)
    return d


class GitHub:
    """El servidor de mentira: la API y las descargas."""
    def __init__(self, datos, archivo=ZIP_999, caido=False):
        self.datos, self.archivo, self.caido = datos, archivo, caido
    def __call__(self, url, timeout):
        pedidos.append(url)
        if self.caido:
            raise OSError("sin internet")
        if url.startswith("https://api.github.com/"):
            return Respuesta(json.dumps(self.datos).encode())
        return Respuesta(self.archivo)


# ---- el núcleo ---------------------------------------------------------------
sys.path.insert(0, str(ING.parent))
import geocad.aviso_versiones as AV
import geocad.config as C
assert AV.API == "https://api.github.com/repos/archibello/GEO-CAD-YAGUARETE/releases/latest"
assert C.get("avisar_versiones") is True                              # prendido de fábrica
assert "avisar_versiones" in [s.key for s in C.SETTINGS]              # en Configuración común
assert "aviso_saltear" not in [s.key for s in C.SETTINGS]             # lo interno no se muestra

# la prueba entera corre con el aviso apagado; acá se prende a mano
assert os.environ.get("GEOCAD_SIN_AVISO") == "1" and AV.toca_consultar("ingecad") is False
del os.environ["GEOCAD_SIN_AVISO"]
os.environ.pop("QT_QPA_PLATFORM", None)
assert AV.toca_consultar("ingecad") and AV.toca_consultar("qgis")
os.environ["QT_QPA_PLATFORM"] = "offscreen"                           # bancos sin pantalla: no
assert AV.toca_consultar("ingecad") is False
del os.environ["QT_QPA_PLATFORM"]

# leer la respuesta de GitHub
p = AV.leer_publicada(release("9.9.9"))
assert p.version == "9.9.9" and p.entrega.endswith("/GeoCAD_9.9.9.zip") and p.pagina.endswith("/v9.9.9")
assert AV.leer_publicada(release("9.9.9", draft=True)) is None
assert AV.leer_publicada(release("9.9.9", prerelease=True)) is None
assert AV.leer_publicada({"tag_name": "prueba"}) is None and AV.leer_publicada([]) is None
assert AV.leer_publicada(release("9.9.9", con_entrega=False)).entrega == ""
otra = release("9.9.9"); otra["assets"][1]["name"] = "GeoCAD_9.9.8.zip"          # la de otra versión no
assert AV.leer_publicada(otra).entrega == ""
assert AV.consultar(GitHub(release("9.9.9"))).version == "9.9.9"
assert AV.consultar(GitHub(None, caido=True)) is None
assert AV.consultar(lambda u, t: Respuesta(b"<html>no es json")) is None

# a quién se avisa
assert AV.para_avisar(p, "3.95.0") and not AV.para_avisar(p, "9.9.9") and not AV.para_avisar(p, "10.0.0")
assert not AV.para_avisar(AV.leer_publicada(release("9.9.9", con_entrega=False)), "1.0.0")
assert not AV.para_avisar(None, "1.0.0")
AV.saltear("9.9.9"); assert not AV.para_avisar(p, "3.95.0")
C.save({"aviso_saltear": ""}, "IngeCAD"); assert AV.para_avisar(p, "3.95.0")

# descargar: sana, se reutiliza, las viejas se borran, una rota no queda
desc = AV.carpeta_descargas()
assert desc == Path(HOME) / ".config" / "geocad" / "descargas"
desc.mkdir(parents=True); (desc / "GeoCAD_9.9.1.zip").write_bytes(b"vieja")
pedidos.clear()
assert AV.descargar(p, abrir=GitHub(None)) == desc
assert (desc / "GeoCAD_9.9.9.zip").read_bytes() == ZIP_999 and len(pedidos) == 1
assert not (desc / "GeoCAD_9.9.1.zip").exists() and not list(desc.glob(".*parcial"))
assert AV.descargar(p, abrir=GitHub(None, caido=True)) == desc               # ya estaba: no baja
rota = Path(tempfile.mkdtemp())
assert AV.descargar(p, rota, abrir=GitHub(None, archivo=b"no es un zip")) is None
assert list(rota.iterdir()) == []
sin_instalador = io.BytesIO()
with zipfile.ZipFile(sin_instalador, "w") as zf: zf.writestr("GeoCAD_9.9.9/LEEME.txt", "x")
assert AV.descargar(p, rota, abrir=GitHub(None, archivo=sin_instalador.getvalue())) is None
assert AV.descargar(AV.Publicada("9.9.9", "", "https://x", AV.LIMITE + 1), rota, abrir=GitHub(None)) is None
assert AV.descargar(p, rota, abrir=GitHub(None, caido=True)) is None and list(rota.iterdir()) == []

# revisar: todo junto, una vez por día y por programa
shutil.rmtree(desc)
pedidos.clear()
assert AV.revisar("ingecad", "3.95.0", abrir=GitHub(None, caido=True), hoy="2026-11-24") is None
assert C.get("aviso_consultado_ingecad") == ""                         # sin red no cuenta
r = AV.revisar("ingecad", "3.95.0", abrir=GitHub(release("9.9.9")), hoy="2026-11-24")
assert r and r[0].version == "9.9.9" and r[1] == desc and (desc / "GeoCAD_9.9.9.zip").is_file()
assert C.get("aviso_consultado_ingecad") == "2026-11-24" and C.get("aviso_consultado_qgis") == ""
pedidos.clear()
assert AV.revisar("ingecad", "3.95.0", abrir=GitHub(release("9.9.9")), hoy="2026-11-24") is None
assert pedidos == []                                                   # hoy ya se preguntó
assert AV.revisar("qgis", "3.95.0", abrir=GitHub(release("9.9.9")), hoy="2026-11-24")
assert AV.revisar("ingecad", "9.9.9", abrir=GitHub(release("9.9.9")), hoy="2026-11-25") is None
C.save({"avisar_versiones": False}, "IngeCAD")
assert AV.revisar("ingecad", "3.95.0", abrir=GitHub(release("9.9.9")), hoy="2026-11-26") is None
C.save({"avisar_versiones": True}, "IngeCAD")

# el texto del aviso y la entrega encontrada por Actualizar (también el zip de QGIS de adentro)
import geocad.actualizar as A
c_ing = A.mas_nueva(desc, "ingecad", "3.95.0"); c_qg = A.mas_nueva(desc, "qgis", "3.95.0")
assert c_ing.nombre == "instalar_geocad_9.9.9.py" and c_qg.nombre == "opcional_QGIS_geocad_qgis_9.9.9.zip"
t = AV.texto_aviso("IngeCAD", "3.95.0", p, A.cambios(c_ing))
assert "instalada en IngeCAD: 3.95.0" in t and "nueva:                 9.9.9" in t and "trae cosas nuevas" in t
sys.path.remove(str(ING.parent))
for n in [m for m in sys.modules if m == "geocad" or m.startswith("geocad.")]:
    del sys.modules[n]
print("ok núcleo")

# ---- IngeCAD: el aviso y sus tres botones --------------------------------------
from core.plugins import PluginManager, user_plugins_dir
from core import scripting
root = user_plugins_dir()
class Host:
    document = None
    def __init__(self): self.calls = []; self.command_line = types.SimpleNamespace(echo=lambda t: print("IngeCAD>", t))
    def __getattr__(self, n): return lambda *a, **k: self.calls.append(n) or True
from core.commands import History
host = Host(); host.history = History()
host.plugins = PluginManager(host=host, bundled_dir=Path(CFG) / "nada", user_dir=root); host.plugins.discover()
inst = Path(tempfile.mkdtemp()) / "instalar_actual.py"
inst.write_text(build.instalador(con_version(ING, "3.95.0"), "3.95.0"), encoding="utf-8")
_c, err = scripting.run_python(inst, host); assert err is None, err
assert host.plugins.loaded["geocad"].spec.version == "3.95.0"

mod = sys.modules["ingecad_plugin_geocad.actualizacion"]
qb = sys.modules["ingecad_plugin_geocad.buzon"]
iav = sys.modules["ingecad_plugin_geocad.aviso_versiones"]
icfg = sys.modules["ingecad_plugin_geocad.config"]
pub = iav.leer_publicada(release("9.9.9"))
log, textos = [], []
def contesta(eleccion):
    return lambda w, texto, pagina: textos.append((texto, pagina)) or eleccion
# sin Qt (como en estas pruebas) iniciar_aviso no hace nada ni sale a la red
pedidos.clear(); mod.iniciar_aviso(host, log.append); assert pedidos == [] and log == []
# Más tarde: no instala ni guarda nada
mod._preguntar_aviso = contesta(iav.MAS_TARDE)
assert mod.mostrar_aviso(host, log.append, pub, desc) == iav.MAS_TARDE
assert "nueva:                 9.9.9" in textos[-1][0] and "trae cosas nuevas" in textos[-1][0]
assert textos[-1][1].endswith("/v9.9.9") and "mañana" in log[-1]
assert host.plugins.loaded["geocad"].spec.version == "3.95.0" and icfg.get("aviso_saltear") == ""
# No avisar de esta versión: se guarda y no instala
mod._preguntar_aviso = contesta(iav.NO_AVISAR)
assert mod.mostrar_aviso(host, log.append, pub, desc) == iav.NO_AVISAR
assert icfg.get("aviso_saltear") == "9.9.9" and "ACTUALIZARGEOCAD" in log[-1]
assert host.plugins.loaded["geocad"].spec.version == "3.95.0" and not iav.para_avisar(pub, "3.95.0")
icfg.save({"aviso_saltear": ""}, "IngeCAD")
# con otra ventana de Actualizar abierta, no se abre otra
mod._hay_aviso_abierto = lambda: True; n = len(textos)
assert mod.mostrar_aviso(host, log.append, pub, desc) == "" and len(textos) == n
mod._hay_aviso_abierto = lambda: False
# Actualizar ahora: instala la bajada y le avisa a QGIS con la misma carpeta
qb.receive("qgis")
mod._preguntar_aviso = contesta(iav.ACTUALIZAR)
assert mod.mostrar_aviso(host, log.append, pub, desc) == iav.ACTUALIZAR
assert host.plugins.loaded["geocad"].spec.version == "9.9.9" and host.plugins.is_active("geocad")
msgs = qb.receive("qgis")
assert [m["tipo"] for m in msgs] == ["actualizar"] and msgs[0]["carpeta"] == str(desc)
# ya instalada: no vuelve a avisar
mod = sys.modules["ingecad_plugin_geocad.actualizacion"]
mod._preguntar_aviso = contesta(iav.ACTUALIZAR); n = len(textos)
assert mod.mostrar_aviso(host, log.append, pub, desc) == "" and len(textos) == n
print("ok IngeCAD")

# ---- QGIS: el mismo aviso ------------------------------------------------------
plugins = Path(tempfile.mkdtemp()) / "plugins"; plugins.mkdir()
shutil.copytree(con_version(QG, "3.95.0"), plugins / "geocad")
sys.path[:0] = [os.path.join(HERE, "fake_qgis"), str(plugins)]
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QTimer
os.environ["GEOCAD_SIN_AVISO"] = "1"
import geocad as geocad_qgis
from geocad import plugin as qp, buzon as qgb, aviso_versiones as qav
class Bar:
    def __init__(self): self.msgs = []
    def pushMessage(self, title, text, level=None, duration=0): self.msgs.append(text)
bar = Bar()
class MB:
    def insertMenu(self, b, m): pass
    def removeAction(self, a): pass
iface = types.SimpleNamespace(mainWindow=lambda: types.SimpleNamespace(menuBar=lambda: MB(), removeToolBar=lambda t: None),
                              helpMenu=lambda: types.SimpleNamespace(menuAction=lambda: None),
                              messageBar=lambda: bar, addToolBar=lambda n: None)
qp.modulos.guardar("qgis", {"puente": True})
P = geocad_qgis.classFactory(iface); P.initGui()
pedidos.clear()
for _ in range(3):                                    # _primer_inicio y el aviso que programa
    tiros, QTimer.shots[:] = list(QTimer.shots), []
    for f in tiros: f()
assert pedidos == [] and not getattr(P, "_aviso_iniciado", False)     # apagado en pruebas: sin red
qpub = qav.leer_publicada(release("9.9.9"))
P._preguntar_aviso = lambda texto, pagina: textos.append((texto, pagina)) or qav.MAS_TARDE
assert P.mostrar_aviso(qpub, desc) == qav.MAS_TARDE
assert "instalada en QGIS: 3.95.0" in textos[-1][0] and "mañana" in bar.msgs[-1]
P._preguntar_aviso = lambda texto, pagina: qav.NO_AVISAR
assert P.mostrar_aviso(qpub, desc) == qav.NO_AVISAR and qp.config.get("aviso_saltear") == "9.9.9"
assert "version=3.95.0" in (plugins / "geocad" / "metadata.txt").read_text()
qgb.receive("ingecad")
P._preguntar_aviso = lambda texto, pagina: qav.ACTUALIZAR
assert P.mostrar_aviso(qpub, desc) == qav.ACTUALIZAR
assert "version=9.9.9" in (plugins / "geocad" / "metadata.txt").read_text()
assert (plugins / ".anterior-geocad").exists() and not (plugins / ".instalando-geocad").exists()
msgs = qgb.receive("ingecad")
assert [m["tipo"] for m in msgs] == ["actualizar"] and msgs[0]["carpeta"] == str(desc)
assert "9.9.9 instalado" in bar.msgs[-1]
print("ok QGIS")
print("TODO OK AVISO VERSIONES")
