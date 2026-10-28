"""GeoCAD en Windows: el instalador único (rutas de %APPDATA% y Registro), el .bat,
abrir IngeCAD desde QGIS, sqlite3 propio para el IngeCAD empaquetado, el aviso
de GeoPackage a QGIS y los reintentos al reemplazar archivos. Corre igual en
Linux y en Windows: el sistema se simula y el Registro no se toca."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import importlib.util, os, sys, tempfile, time, types
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
ING = ROOT / "INGECAD" / "codigo" / "geocad"
QG = ROOT / "QGIS" / "codigo" / "geocad"
sys.path.insert(0, str(ROOT / "COMUN"))


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = cargar("build_win", ROOT / "COMUN" / "build.py")

# ---- 1. build.py: UTF-8 y \n tal cual (en Windows write_text los cambiaría) -------------
p = Path(tempfile.mkdtemp()) / "x.py"
B._escribir(p, 'VERSION = "1.0.0"\n# Yaguareté\n')
assert p.read_bytes() == 'VERSION = "1.0.0"\n# Yaguareté\n'.encode("utf-8")
assert B._leer(p).endswith("Yaguareté\n")

# ---- 2. el .bat de Windows ----------------------------------------------------------------
bat = B.bat_windows("9.9.9")
assert bat.endswith("\r\n") and "\n" not in bat.replace("\r\n", "")
assert "%PY% instalar_geocad_9.9.9.py" in bat
assert '"%ProgramFiles%\\QGIS*"' in bat and "apps\\Python3*" in bat
assert "where py" in bat and "pause" in bat
assert bat.isascii()                          # cmd.exe: sin acentos en el .bat

# ---- 3. el instalador único, simulando Windows ---------------------------------------------
fuente = B.instalador(ING, "9.9.9")
fuente = fuente.rsplit("\ntry:\n    _main()", 1)[0]       # sin correrlo al cargar


def instalador(nombre_os, environ, hay_registro=False):
    registro = {}
    falso_os = types.SimpleNamespace(name=nombre_os, environ=environ, replace=os.replace)
    ns = {"__name__": "instalador_prueba"}
    exec(compile(fuente, "instalar_geocad_9.9.9.py", "exec"), ns)
    ns["os"] = falso_os
    ns["print"] = lambda *a: None
    ns["_registro_poner"] = lambda sub, k, v: registro.__setitem__(sub + "\\" + k, v)
    ns["_registro_hay_ingecad"] = lambda: hay_registro
    return ns, registro


appdata = Path(tempfile.mkdtemp())
(appdata / "IngeCAD").mkdir()
perfil = appdata / "QGIS" / "QGIS4" / "profiles" / "default"
(perfil / "QGIS").mkdir(parents=True)
(perfil / "QGIS" / "QGIS4.ini").write_text("[PythonPlugins]\nEasyFillet=true\n", encoding="utf-8")
ns, reg = instalador("nt", {"APPDATA": str(appdata), "HOME": str(appdata / "no")})
hechos = ns["_ingecad_desde_afuera"]()
destino = appdata / "IngeCAD" / "plugins" / "geocad"
assert hechos == [destino], hechos
for rel in ("sqlite_win.py", "diagnostico.py", "win/py312/_sqlite3.pyd", "win/py312/sqlite3.dll",
            "win/py312/sqlite3/__init__.py"):
    assert (destino / rel).is_file(), rel
assert reg == {"plugins\\geocad\\enabled": "true", "plugins\\geocad\\toolbar": "true",
               "plugins\\puente_qgis\\enabled": "false", "plugins\\conexion_shp\\enabled": "false"}, reg
assert not (appdata / "IngeCAD" / "IngeCAD.conf").exists()       # en Windows va al Registro
q_hechos, fallas = ns["_qgis"]()
assert q_hechos == ["QGIS4/default"] and not fallas, (q_hechos, fallas)
assert (perfil / "python" / "plugins" / "geocad" / "abrir_ingecad.py").is_file()
ini = (perfil / "QGIS" / "QGIS4.ini").read_text(encoding="utf-8")
assert "geocad=true" in ini and "EasyFillet=true" in ini
# reinstalar: la anterior queda como .anterior-geocad
ns["_ingecad_desde_afuera"]()
assert (appdata / "IngeCAD" / "plugins" / ".anterior-geocad" / "sqlite_win.py").is_file()

# sin IngeCAD (ni carpeta ni Registro): no instala nada; con el Registro sí
vacio = Path(tempfile.mkdtemp())
ns, reg = instalador("nt", {"APPDATA": str(vacio)})
assert ns["_ingecad_desde_afuera"]() == [] and reg == {}
assert list(ns["_perfiles_qgis"]()) == []
ns, reg = instalador("nt", {"APPDATA": str(vacio)}, hay_registro=True)
assert ns["_ingecad_desde_afuera"]() == [vacio / "IngeCAD" / "plugins" / "geocad"]

# Linux sigue igual: no mira %APPDATA% ni el Registro
casa = Path(tempfile.mkdtemp())
(casa / ".config" / "IngeCAD").mkdir(parents=True)
ns, reg = instalador("posix", {"HOME": str(casa), "APPDATA": str(appdata)})
assert ns["_ingecad_desde_afuera"]() == [casa / ".config" / "IngeCAD" / "plugins" / "geocad"]
assert reg == {}
assert "geocad\\enabled=true" in (casa / ".config" / "IngeCAD" / "IngeCAD.conf").read_text()
assert list(ns["_perfiles_qgis"]()) == []

# ---- 4. abrir IngeCAD desde QGIS -------------------------------------------------------------
A = cargar("abrir_ingecad", QG / "abrir_ingecad.py")
hay = {r"C:\Program Files\IngeCAD\ingecad.exe", r"D:\Apps\IngeCAD\ingecad.exe",
       r"C:\Users\u\AppData\Local\Programs\IngeCAD\ingecad.exe"}
existe = lambda p: str(p).replace("/", "\\") in hay
env = {"ProgramW6432": r"C:\Program Files", "ProgramFiles": r"C:\Program Files",
       "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
cmds = A.comandos(es_windows=True, env=env, registro=[], existe=existe, which=lambda n: None)
assert [PureWindowsPath(c[0]).name for c in cmds] == ["ingecad.exe", "ingecad.exe"], cmds
assert "Program Files" in cmds[0][0] and "Programs" in cmds[1][0]
cmds = A.comandos(es_windows=True, ruta_elegida=r"D:\Apps\IngeCAD\ingecad.exe", env=env,
                  registro=[Path(r"C:\Program Files\IngeCAD")], existe=existe, which=lambda n: None)
assert cmds[0] == [r"D:\Apps\IngeCAD\ingecad.exe"] and len(cmds) == 3, cmds   # sin repetir
assert A.comandos(es_windows=True, env={}, registro=[], existe=lambda p: False,
                  which=lambda n: None) == []
cmds = A.comandos(es_windows=False, flatpak_info=True, which=lambda n: "/usr/bin/" + n)
assert cmds[0][:2] == ["flatpak-spawn", "--host"] and ["ingecad"] in cmds
kw = A.popen_kwargs(es_windows=True)
assert kw["creationflags"] & 0x8 and "start_new_session" not in kw
assert A.popen_kwargs(es_windows=False)["start_new_session"] is True
assert "Configuración" in A.ayuda_si_falla(True) and "flatpak" not in A.ayuda_si_falla(True)
assert "flatpak override" in A.ayuda_si_falla(False)
plugin = (QG / "plugin.py").read_text(encoding="utf-8")
assert "abrir_ingecad as A" in plugin and "INGECAD_FLATPAK" not in plugin

# ---- 5. sqlite3 propio del IngeCAD empaquetado ---------------------------------------------
S = cargar("sqlite_win", ING / "sqlite_win.py")
assert S.carpeta_propia().name == f"py{sys.version_info[0]}{sys.version_info[1]}"
assert (ING / "win" / "py312" / "_sqlite3.pyd").is_file()
# con un Python completo usa el suyo; en Windows sin sqlite3 (como el IngeCAD empaquetado)
# carga de verdad la copia de GeoCAD
assert S.asegurar() is True, S.estado()
origen = S.estado()["origen"]
assert origen == "IngeCAD" or (os.name == "nt" and origen.startswith("GeoCAD (")), origen
import sqlite3
assert sqlite3.connect(":memory:").execute("select sqlite_version()").fetchone()[0]
S2 = cargar("sqlite_win2", ING / "sqlite_win.py")                       # Linux sin sqlite3
guardado = sys.modules.get("sqlite3")
sys.modules["sqlite3"] = None                                           # import -> ImportError
try:
    assert S2.asegurar(es_windows=False) is False
    assert S2.estado()["ok"] is False and "dll" not in S2.estado()
finally:
    if guardado is not None:
        sys.modules["sqlite3"] = guardado
    else:
        sys.modules.pop("sqlite3", None)
local = Path(tempfile.mkdtemp())
copia = S._copia_fuera(ING / "win" / "py312", env={"LOCALAPPDATA": str(local)})
assert copia.parent == local / "GeoCAD" / "sqlite" and copia.name.startswith("py312-")
assert (copia / "_sqlite3.pyd").is_file() and (copia / "sqlite3" / "dbapi2.py").is_file()
assert S._copia_fuera(ING / "win" / "py312", env={"LOCALAPPDATA": str(local)}) == copia
init = (ING / "__init__.py").read_text(encoding="utf-8")
assert init.index("sqlite_win.asegurar()") < init.index("from core.plugins")
assert '"GEOCADDIAG": cmd_diagnostico' in init
assert "DIAGNOSTICOGEOCAD" in (ING / "i18n" / "es" / "commands.json").read_text(encoding="utf-8")
assert '"gpkg": sqlite_win.disponible()' in (ING / "puente.py").read_text(encoding="utf-8")

# ---- 6. núcleo: lo que anuncia IngeCAD y los reintentos de Windows --------------------------
from nucleo import buzon as BZ, config as CF
os.environ["HOME"] = str(Path(tempfile.mkdtemp()))
os.environ["USERPROFILE"] = os.environ["HOME"]
BZ.base_dir = lambda: Path(os.environ["HOME"]) / ".config" / "geocad"
assert BZ.puede("ingecad", "gpkg") is True                    # no anunció nada: se supone que sí
BZ.heartbeat("ingecad", {"version": "9.9.9", "gpkg": False})
assert BZ.puede("ingecad", "gpkg") is False and BZ.version_of("ingecad") == "9.9.9"
assert "ingecad_windows" in CF.BY_KEY and CF.BY_KEY["ingecad_windows"].default == ""

d = Path(tempfile.mkdtemp())
(d / "a.json").write_text("nuevo")
(d / "b.json").write_text("viejo")
real, intentos = os.replace, []


def ocupado(src, dst):
    intentos.append(1)
    if len(intentos) < 3:
        raise PermissionError("en uso")
    real(src, dst)


BZ.os = types.SimpleNamespace(name="nt", replace=ocupado, unlink=os.unlink)
BZ.time = types.SimpleNamespace(sleep=lambda s: None, time=time.time)
BZ._reemplazar(d / "a.json", d / "b.json")
assert len(intentos) == 3 and (d / "b.json").read_text() == "nuevo"
(d / "c.json").write_text("x")


def siempre_ocupado(src, dst):
    raise PermissionError("en uso")


BZ.os = types.SimpleNamespace(name="posix", replace=siempre_ocupado, unlink=os.unlink)
try:
    BZ._reemplazar(d / "c.json", d / "b.json")
    raise AssertionError("en Linux no reintenta")
except PermissionError:
    assert not (d / "c.json").exists()                        # el temporal no queda
BZ.os = os
for n in ("config.py", "modulos.py", "botones.py"):
    texto = (ROOT / "COMUN" / "nucleo" / n).read_text(encoding="utf-8")
    assert "from .buzon import _reemplazar" in texto and "os.replace(" not in texto, n

print("TODO OK WINDOWS")
