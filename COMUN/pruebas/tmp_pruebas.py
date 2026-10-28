"""Carpetas temporales de las pruebas: todo lo que la prueba crea con tempfile
(HOME falso, obras, salidas) queda dentro de UNA carpeta, que se borra al
terminar, pase o falle la prueba. /tmp es tmpfs: lo que queda ocupa RAM.
Se importa antes del primer uso de tempfile:  import tmp_pruebas"""
import atexit, os, shutil, signal, sys, tempfile

RAIZ = tempfile.mkdtemp(prefix="geocad-prueba-")
tempfile.tempdir = RAIZ
atexit.register(shutil.rmtree, RAIZ, ignore_errors=True)
# timeout manda SIGTERM: salir con sys.exit para que corra atexit
signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))

# Windows: las pruebas simulan la carpeta personal con HOME, pero Windows usa
# USERPROFILE, y IngeCAD y QGIS guardan en %APPDATA% / %LOCALAPPDATA%. Sin esto
# instalaban GeoCAD y escribían ~/.config/geocad en las carpetas REALES del
# usuario (28/10/2026). Todo va a una casa falsa dentro de RAIZ, y «~» sigue a
# HOME como en Linux (también cuando la prueba cambia HOME después).
if os.name == "nt":
    import ntpath

    _casa = os.path.join(RAIZ, "casa")
    for _var, _sub in (("USERPROFILE", ""), ("HOME", ""),
                       ("APPDATA", r"AppData\Roaming"), ("LOCALAPPDATA", r"AppData\Local")):
        os.environ[_var] = os.path.join(_casa, _sub) if _sub else _casa
        os.makedirs(os.environ[_var], exist_ok=True)
    _expanduser = ntpath.expanduser

    def _expanduser_home(path):
        p = os.fspath(path)
        sep = b"\\/" if isinstance(p, bytes) else "\\/"
        tilde = b"~" if isinstance(p, bytes) else "~"
        if p[:1] == tilde and (len(p) == 1 or p[1:2] in (sep[:1], sep[1:])) and os.environ.get("HOME"):
            home = os.environ["HOME"]
            return (os.fsencode(home) if isinstance(p, bytes) else home) + p[1:]
        return _expanduser(path)

    ntpath.expanduser = _expanduser_home
