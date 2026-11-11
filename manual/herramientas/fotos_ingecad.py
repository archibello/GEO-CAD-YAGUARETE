"""Capturas del manual con la VENTANA REAL de IngeCAD, sin pantalla (Qt «offscreen»).

Como los bancos de COMUN/pruebas/ventana (necesita PySide6, ezdxf, numpy, Pillow, pyproj):
    python fotos_ingecad.py <carpeta de IngeCAD> <carpeta del plugin geocad> \\
        <carpeta con parcelas.shp> <carpeta de imágenes>
Corre las órdenes de verdad sobre la manzana de ejemplo; cada ventana que se abre
se fotografía y se contesta sola (Aceptar o Cancelar, según el guion).
"""
import os, sys, tempfile, time, traceback, faulthandler
faulthandler.dump_traceback_later(400, exit=True)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="fotos-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="fotos-home-")
INGECAD, PLUGIN, DATOS, SALIDA = sys.argv[1:5]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtCore import QCoreApplication, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox, QPushButton
import main as ingecad_main

QCoreApplication.setApplicationName("IngeCAD")
QCoreApplication.setOrganizationName("IngeCAD")
ingecad_main._configure_surface_format()
app = QApplication.instance() or QApplication([])
ingecad_main._apply_dark_theme(app)
from core import i18n
i18n.set_language("es")                     # Herramientas > Idioma > Español
from views import qt_translations
qt_translations.install("es")
for _n in ("warning", "question", "information", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
SHP = str(Path(DATOS) / "parcelas.shp")
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([SHP], ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (SHP, ""))

from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
mods.guardar("ingecad", {m.clave: True for m in mods.CATALOGO["ingecad"]})
pkg = import_module("ingecad_plugin_geocad")
pkg.PLUGIN = pkg.construir_spec()
lp.spec = pkg.PLUGIN
from views.main_window import MainWindow

log = []
guion = []          # [(nombre de la foto, "aceptar" | "cancelar", ajuste opcional)]


def eventos(n=20):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def esperar(win, s=15.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        if getattr(win, "_regen_worker", None) is None and not win.tools._merge_timer.isActive():
            break
        time.sleep(0.01)
    eventos()


def foto(widget, nombre):
    eventos(10)
    widget.grab().save(str(Path(SALIDA) / (nombre + ".png")))
    log.append("foto " + nombre)


def contestar():
    w = QApplication.activeModalWidget()
    if w is None or not isinstance(w, QDialog) or not guion or getattr(w, "_fotografiada", False):
        return
    w._fotografiada = True
    w.setWindowOpacity(0.0)
    nombre, que, ajuste = guion.pop(0)
    if ajuste:
        try:
            ajuste(w)
        except Exception as exc:          # noqa: BLE001
            log.append("ajuste %s: %s" % (nombre, exc))
    eventos(5)
    if nombre:
        foto(w, nombre)
    (w.accept if que == "aceptar" else w.reject)()


reloj = QTimer()
reloj.timeout.connect(contestar)
reloj.start(250)


def orden(win, nombre, *pasos, respuestas=()):
    guion.extend(pasos)
    win._invoke_command(nombre)
    esperar(win)
    for texto in respuestas:                 # lo que se escribe en la línea de comandos
        win.dispatcher.submit(texto)
        esperar(win)
    eventos(30)
    if guion:
        log.append("quedó sin usar en %s: %s" % (nombre, [p[0] for p in guion]))
        guion.clear()


def menu_geocad(win):
    for m in win.findChildren(QMenu):
        if "GeoCAD" in m.title():
            return m
    return None


def ruta_neutra(dlg):
    from PySide6.QtWidgets import QLineEdit
    for e in dlg.findChildren(QLineEdit):
        if "/" in e.text():
            e.setText("Manzana12.kmz")


def tildar_todas(dlg):
    for b in dlg.findChildren(QPushButton):
        if b.text().startswith("Tildar todas"):
            b.click()


def correr():
    win = MainWindow()
    win.plugins.loaded["geocad"] = lp
    win.plugins.activate("geocad")
    win.add_toolbar(pkg.PLUGIN)
    win.menus_changed()
    win.new_document("m")
    win.resize(1500, 920)
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        win.setWindowOpacity(0.0)           # en la pantalla real, pero invisible
    win.show()
    esperar(win)

    orden(win, "GEOIMPORTSHP", ("ingecad_importarshp", "aceptar", tildar_todas))
    esperar(win, 30)
    foto(win, "ingecad_ventana")

    m = menu_geocad(win)
    if m is not None:
        m.popup(win.mapToGlobal(QPoint(420, 25)))
        eventos(20)
        foto(m, "ingecad_menu_geocad")
        m.hide()
    else:
        log.append("sin menú GeoCAD: " + ", ".join(a.text() for a in win.menuBar().actions()))

    orden(win, "GEOCADMODULES", ("ingecad_modulos", "cancelar", None))
    orden(win, "GEOCRS", ("ingecad_sistemageo", "cancelar", None))
    def rotulo_lote(dlg):
        dlg.campo.setCurrentText("LOTE")
        dlg.altura.setValue(2.0)
        dlg.circulo.setChecked(True)

    guion.append(("ingecad_rotulosig", "aceptar", rotulo_lote))
    win._invoke_command("SHPLABEL")
    esperar(win)
    win.tools.tool.on_selection([])          # Enter sin elegir = toda la capa
    esperar(win, 30)
    eventos(30)
    import shapefile
    pts = [p for s in shapefile.Reader(SHP).shapeRecords() if s.record["MANZANA"] == "12"
           for p in s.shape.points]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    win.tools.zoom_to_window((min(xs) - 15, min(ys) - 15, max(xs) + 15, max(ys) + 15))
    esperar(win, 30)
    foto(win, "ingecad_rotulos")
    orden(win, "SHPTABLE")
    eventos(30)
    foto(win, "ingecad_tablasig")
    orden(win, "GEOEXPORTKML", ("ingecad_exportarkml", "cancelar", ruta_neutra))
    win.close()


try:
    correr()
    log.append("FIN")
except Exception:                            # noqa: BLE001
    log.append(traceback.format_exc())
(Path(SALIDA) / "fotos_ingecad.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
os._exit(0)
