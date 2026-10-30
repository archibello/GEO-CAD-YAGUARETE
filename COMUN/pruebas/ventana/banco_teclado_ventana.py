"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
el teclado siempre a la línea de comandos (módulo «Teclado», 3.59).

Con el foco en el panel de capas (sin hacer clic en la línea de comandos):
lo escrito llega a la línea; Intro con algo escrito arranca la orden y Esc
la cancela; Intro con la línea vacía no repite nada. Un campo de texto de la
ventana y un diálogo se quedan con lo suyo; Ctrl + tecla no se toma. Sobre
el dibujo sigue mandando IngeCAD. Módulo apagado: como viene IngeCAD.

Uso (necesita PySide6, ezdxf, numpy):
    python banco_teclado_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
Termina en «TODO OK». El cierre de Qt puede dar «violación de segmento»
DESPUÉS de «TODO OK»: no cuenta.
"""
import os, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(240, exit=True)        # colgado: dice dónde
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="banco-cfg-")
os.environ["HOME"] = tempfile.mkdtemp(prefix="banco-home-")
INGECAD, PLUGIN = sys.argv[1], sys.argv[2]
sys.path.insert(0, INGECAD)
from pathlib import Path
from importlib import import_module
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QMessageBox, QDockWidget, QLineEdit, QDialog,
                               QPushButton, QVBoxLayout)
from PySide6.QtTest import QTest

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
mods = import_module("ingecad_plugin_geocad.modulos")
TI = import_module("ingecad_plugin_geocad.teclado_ingecad")
from views.main_window import MainWindow
fallas = []


def ver(nombre, ok, extra=""):
    print(f"  [{nombre}] {'bien' if ok else 'MAL   <-- FALLA'} {extra}")
    if not ok:
        fallas.append(nombre)


def esperar(s=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        time.sleep(0.01)


def enfocar(w):
    w.setFocus(Qt.OtherFocusReason)
    esperar(0.05)
    return app.focusWidget() is w


def teclear(texto):
    """Como el teclado de verdad: cada tecla al widget que tiene el foco."""
    for ch in texto:
        QTest.keyClicks(app.focusWidget() or win, ch)
        app.processEvents()


mods.guardar("ingecad", {"teclado": True})
win = MainWindow()
# GeoCAD activo en el gestor de plugins de la ventana, como en IngeCAD instalado:
# al abrir el dibujo, on_document_open instala el filtro
win.plugins.loaded[lp.spec.id if hasattr(lp, "spec") else "geocad"] = lp
ver("GeoCAD activo en la ventana", bool(win.plugins.activate("geocad")) or win.plugins.is_active("geocad"))
win.new_document("m")
win.show(); win.activateWindow(); esperar(0.3)
ver("filtro instalado al abrir el dibujo", TI.activo())
entrada = win.command_line.input
tabla = win._layers_panel.table
if not tabla.isVisible():
    win.toggle_layers_panel(); esperar(0.2)
ver("panel de capas visible", tabla.isVisible())

# 1) letras desde el panel de capas
entrada.clear()
ver("foco en el panel de capas", enfocar(tabla))
teclear("line")
esperar()
ver("lo escrito en el panel de capas llega a la línea", entrada.text().lower() == "line",
    repr(entrada.text()))
ver("el foco pasa a la línea de comandos", app.focusWidget() is entrada)

# 2) Intro con algo escrito arranca la orden; Esc la cancela (con el foco afuera)
enfocar(tabla)
QTest.keyClick(tabla, Qt.Key_Return)
esperar(0.2)
en_marcha = TI._comando_en_marcha(win)
ver("Intro desde el panel arranca LINE", en_marcha and entrada.text() == "")
enfocar(tabla)
QTest.keyClick(tabla, Qt.Key_Escape)
esperar(0.2)
ver("Esc desde el panel cancela la orden", not TI._comando_en_marcha(win))

# 3) Intro con la línea vacía: no repite la última orden
enfocar(tabla)
QTest.keyClick(tabla, Qt.Key_Return)
esperar(0.2)
ver("Intro con la línea vacía no va a la línea", not TI._comando_en_marcha(win))
win.tools.cancel() if hasattr(win.tools, "cancel") else None
esperar(0.1)

# 4) un campo de texto de la ventana se queda con lo suyo
dock = QDockWidget("campo", win)
campo = QLineEdit(dock)
dock.setWidget(campo)
win.addDockWidget(Qt.RightDockWidgetArea, dock)
esperar(0.1)
entrada.clear()
enfocar(campo)
QTest.keyClicks(campo, "12,5")
esperar()
ver("campo de texto: escribe en el campo", campo.text() == "12,5" and entrada.text() == "",
    repr((campo.text(), entrada.text())))

# 5) un diálogo (no modal) se queda con lo suyo
dlg = QDialog(win)
boton = QPushButton("b", dlg)
QVBoxLayout(dlg).addWidget(boton)
dlg.show(); dlg.activateWindow(); esperar(0.1)
enfocar(boton)
QTest.keyClicks(boton, "abc")
esperar()
ver("diálogo: no va a la línea", entrada.text() == "", repr(entrada.text()))
dlg.close(); win.activateWindow(); esperar(0.1)

# 6) Ctrl + tecla no se toma
enfocar(tabla)
QTest.keyClick(tabla, Qt.Key_L, Qt.ControlModifier)
esperar()
ver("Ctrl+L no va a la línea", entrada.text() == "", repr(entrada.text()))

# 7) sobre el dibujo sigue IngeCAD (type_ahead propio)
entrada.clear()
enfocar(win.viewport)
QTest.keyClicks(win.viewport, "ci")
esperar()
ver("sobre el dibujo: IngeCAD lo pasa a la línea", entrada.text().lower().startswith("ci"),
    repr(entrada.text()))
entrada.clear()

# 7b) botón derecho = Enter / última orden con el foco en el panel de capas
def derecho():
    QTest.mouseClick(win.viewport, Qt.RightButton, Qt.NoModifier, win.viewport.rect().center())
    esperar(0.2)


enfocar(tabla)
derecho()
ver("clic derecho sin orden: repite la última (LINE)", TI._comando_en_marcha(win))
enfocar(tabla)
derecho()
ver("clic derecho durante la orden: Enter (termina)", not TI._comando_en_marcha(win))
entrada.setText("line")
enfocar(tabla)
derecho()
ver("clic derecho con algo escrito: lo acepta", TI._comando_en_marcha(win) and entrada.text() == "")
enfocar(tabla)
QTest.keyClick(tabla, Qt.Key_Escape)
esperar(0.2)
entrada.clear()

# 8) módulo apagado: como viene IngeCAD
mods.guardar("ingecad", {"teclado": False})
TI.aplicar(win)
ver("módulo apagado: sin filtro", not TI.activo())
enfocar(tabla)
QTest.keyClicks(tabla, "line")
esperar()
ver("módulo apagado: el panel no manda a la línea", entrada.text() == "", repr(entrada.text()))
mods.guardar("ingecad", {"teclado": True})
TI.aplicar(win)
ver("prendido de nuevo", TI.activo())

win.close(); app.processEvents()
if fallas:
    print("FALLAS:", fallas)
    sys.exit(1)
print("TODO OK")
