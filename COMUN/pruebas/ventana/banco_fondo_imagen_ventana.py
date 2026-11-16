"""Banco con la VENTANA REAL de IngeCAD (sin pantalla, Qt «offscreen»):
el fondo blanco de ASPECTOIMAGEN (3.82.0).

Fernando (16/11/2026): «superponer un fondo blanco opaco que aparezca por
detrás, y que dé como resultado una imagen con fondo blanco», en una capa
que se prende o se apaga, sin rellenar los píxeles. Comprueba, con la orden
y la ventana de verdad (casilla «Fondo blanco» tildada con el clic):
* la ventana trae la casilla, destildada; al tildarla la vista previa pasa
  a fondo Blanco;
* en la escena de IngeCAD el relleno blanco queda en el grupo de dibujo del
  fondo (-1) y la imagen en el normal (0): se pinta antes, queda detrás;
* la capa FONDO_IMAGENES apagada: el relleno no se pinta, la imagen sí;
* la ventana vuelve a abrir con la casilla tildada; destildarla lo quita; U.
3.83.0: el deslizador Contraste; la vista previa grande con zoom (rueda,
1:1, Ver todo; acercada, lo que se ve sale de los píxeles del original) y
«Entregar imagen final...»: una imagen nueva opaca con fondo blanco, la
imagen del dibujo pasa a usarla y su fondo de la capa se quita.

Uso (PySide6, ezdxf, numpy, Pillow):
    python banco_fondo_imagen_ventana.py <carpeta de IngeCAD> <carpeta del plugin geocad>
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
from PIL import Image as PILImage
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
for _n in ("warning", "question", "information", "critical"):   # «¿guardar cambios?»: no
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Discard))
from core.plugins import load_plugin
lp = load_plugin(Path(PLUGIN), bundled=False)
assert lp.available, getattr(lp, "reason", "")
A = import_module("ingecad_plugin_geocad.aspecto")
import_module("ingecad_plugin_geocad.modulos").guardar("ingecad", {"georref": True})
from views.main_window import MainWindow
import views.tool_controller as TC
TC.ALL_TOOL_CLASSES["ASPECTOIMAGEN"] = A.AspectoImagenTool      # como lo registra el plugin

tmp = Path(tempfile.mkdtemp(prefix="banco-"))
png = tmp / "recorte.png"                         # líneas negras sobre transparente
im = PILImage.new("RGBA", (3000, 1500), (0, 0, 0, 0))   # más grande que la vista entera (LADO_BASE)
im.paste((0, 0, 0, 255), (300, 745, 2700, 755))
im.save(png)
fallas = []


def verificar(nombre, ok):
    print(f"  [{nombre}] {'OK' if ok else 'FALLA'}")
    if not ok:
        fallas.append(nombre)


def esperar(win, s=15.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
        app.processEvents()
        if getattr(win, "_regen_worker", None) is None and not win.tools._merge_timer.isActive():
            break
        time.sleep(0.01)
    for _ in range(20):
        app.processEvents()


def grupos_relleno(win):
    return set(win.viewport._scene.triangles.group_set())


def grupo_imagen(win, h):
    """El grupo de la imagen en la escena (sin pantalla no hay OpenGL ni
    texturas: se mira lo que IngeCAD le manda a la placa)."""
    for i in getattr(win.viewport._scene, "images", []):
        if i.handle == h:
            return int(i.group)
    return None


def con_ventana(win, img, tildar, hacer=None):
    """ASPECTOIMAGEN con la ventana de verdad: (estado de la casilla al
    abrir, fondo de la vista previa después)."""
    visto = {}

    def mirar():
        dlg = app.activeModalWidget()
        if dlg is None or not hasattr(dlg, "fondo_blanco"):
            QTimer.singleShot(50, mirar)
            return
        visto["al_abrir"] = dlg.fondo_blanco.isChecked()
        if dlg.fondo_blanco.isChecked() != tildar:
            dlg.fondo_blanco.click()
        app.processEvents()
        visto["previa"] = dlg.fondo.currentData()
        visto["texto"] = dlg.fondo_blanco.text()
        if hacer:
            hacer(dlg, visto)
        else:
            dlg.accept()

    QTimer.singleShot(50, mirar)
    win.tools.selection = {img.dxf.handle}
    win.tools.start_tool("ASPECTOIMAGEN")
    esperar(win)
    win.regen_in_memory(); esperar(win)
    return visto


win = MainWindow()
win.new_document("m")
d = win.document.doc.add_image_def(filename=str(png), size_in_pixel=(3000, 1500))
img = win.document.modelspace().add_image(image_def=d, insert=(0, 0), size_in_units=(20, 10))
win.document.dirty = True
win.show(); app.processEvents()
win.regen_in_memory(); esperar(win)

print("1. tildar «Fondo blanco»")
v = con_ventana(win, img, True)
verificar("la casilla está y abre destildada", v.get("texto") == "Fondo blanco" and v.get("al_abrir") is False)
verificar("la vista previa pasa a fondo Blanco", v.get("previa") == "b")
f = A.fondo_de(img)
verificar("hay fondo en la capa FONDO_IMAGENES", f is not None and f.dxf.layer == A.CAPA_FONDO)
verificar("el relleno se pinta en el grupo del fondo (-1)", -1 in grupos_relleno(win))
verificar("la imagen en el grupo normal (0): encima del fondo", grupo_imagen(win, img.dxf.handle) == 0)

print("2. capa apagada")
capa = win.document.doc.layers.get(A.CAPA_FONDO)
capa.off(); win.regen_in_memory(); esperar(win)
verificar("apagada: el relleno no se pinta", -1 not in grupos_relleno(win))
verificar("apagada: la imagen sigue", grupo_imagen(win, img.dxf.handle) == 0)
capa.on(); win.regen_in_memory(); esperar(win)
verificar("prendida otra vez: se pinta", -1 in grupos_relleno(win))

print("3. destildar y U")
v = con_ventana(win, img, False)
verificar("vuelve a abrir tildada", v.get("al_abrir") is True)
verificar("destildada: el fondo se quita", A.fondo_de(img) is None and -1 not in grupos_relleno(win))
win.history.undo()
win.regen_in_memory(); esperar(win)
verificar("U lo devuelve", A.fondo_de(img) is not None and -1 in grupos_relleno(win))

print("4. contraste, zoom y entregar imagen final (3.83.0)")
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent


def probar(dlg, visto):
    pv = dlg.previa
    visto["contraste"] = (dlg.contraste.minimum(), dlg.contraste.maximum(), dlg.contraste_txt.text())
    dlg.contraste.setValue(300); app.processEvents()
    visto["contraste_txt"] = dlg.contraste_txt.text()
    visto["valor"] = dlg.valores()["contraste"]
    visto["tam_previa"] = (pv.width(), pv.height())
    pv.ver_todo(); app.processEvents()
    visto["todo"] = pv.zoom()
    centro = pv.viewport().rect().center()
    ev = QWheelEvent(QPointF(centro), QPointF(pv.mapToGlobal(centro)), QPoint(0, 0), QPoint(0, 480),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(pv.viewport(), ev); app.processEvents()
    visto["rueda"] = pv.zoom()
    print("    zoom: ver todo", round(visto["todo"], 3), "después de la rueda", round(visto["rueda"], 3))
    pv._calcular_detalle(); app.processEvents()
    visto["detalle"] = pv.detalle.isVisible()
    visto["zoom_txt"] = dlg.zoom_txt.text()
    pv.ver_todo(); pv._calcular_detalle()
    visto["detalle_todo"] = pv.detalle.isVisible()
    visto["boton"] = dlg.b_final.text()
    dlg.b_final.click()


antes = img.image_def.dxf.filename
v = con_ventana(win, img, True, probar)
verificar("Contraste de 100 a 400 %", v.get("contraste", (0, 0, ""))[:2] == (100, A.CONTRASTE_MAX))
verificar("el deslizador cambia el valor", v.get("contraste_txt") == "300 %" and v.get("valor") == 300)
verificar("vista previa grande", v.get("tam_previa", (0, 0))[0] >= 600 and v.get("tam_previa", (0, 0))[1] >= 360)
verificar("la rueda acerca", v.get("rueda", 0) > v.get("todo", 1) * 2)
verificar("acercada: detalle con los píxeles del original", v.get("detalle") is True)
verificar("dice el zoom", str(v.get("zoom_txt", "")).startswith("Zoom "))
verificar("ver todo: sin detalle", v.get("detalle_todo") is False)
verificar("botón «Entregar imagen final...»", v.get("boton") == "Entregar imagen final...")
nueva = Path(img.image_def.dxf.filename)
verificar("la imagen pasa a la final", nueva.name.startswith("recorte_final") and str(nueva) != antes)
fin = PILImage.open(nueva) if nueva.is_file() else None
verificar("la final es opaca con fondo blanco", fin is not None and fin.mode == "RGB"
          and fin.getpixel((5, 5)) == (255, 255, 255) and fin.getpixel((1500, 750))[0] < 60)
verificar("el fondo de la capa se quitó", A.fondo_de(img) is None and -1 not in grupos_relleno(win))
verificar("contraste guardado con la imagen", A.leer(img)[0]["contraste"] == 300 and A.leer(img)[0]["final"])
win.history.undo(); win.regen_in_memory(); esperar(win)
verificar("U: vuelve la de antes con su fondo", img.image_def.dxf.filename == antes and A.fondo_de(img) is not None)

print("TODO OK" if not fallas else f"FALLAS: {fallas}")
sys.stdout.flush()
os._exit(0 if not fallas else 1)
