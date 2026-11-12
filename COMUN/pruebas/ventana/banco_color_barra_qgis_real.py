"""Banco 3.78.1: el título «GeoCAD Yaguareté» pintado en la barra de menús del
QGIS REAL (la barra la crea C++: PyQt no deja llamar a sus funciones
protegidas, por eso se mide acá y no sólo con un Qt de Python).

Corre dentro de QGIS con --code (el código de geocad, en una carpeta sin espacios):
    flatpak run --branch=stable --filesystem=<carpeta> --env=QT_QPA_PLATFORM=offscreen \\
      --env=BANCO_SALIDA=<carpeta>/real.txt --env=BANCO_CODIGO=<carpeta con geocad> \\
      org.qgis.qgis --nologo --noversioncheck --noplugins --profiles-path <carpeta>/perfil \\
      --code <este archivo>
Deja el resultado en BANCO_SALIDA (y la barra en BANCO_SALIDA.png); termina en «TODO OK».
"""
import gc, os, sys, traceback
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QApplication, QMenu
from qgis.utils import iface

salida = []


def color_en(barra, accion):
    r = barra.actionGeometry(accion)
    img = barra.grab().toImage()
    return QColor(img.pixel(r.left() + 3, r.center().y())).name().upper()


def correr():
    try:
        sys.path.insert(0, os.path.join(os.environ["BANCO_CODIGO"], "geocad"))
        import color_barra as cb
        barra = iface.mainWindow().menuBar()
        menu = QMenu("GeoCAD Yaguareté", iface.mainWindow())
        menu.addAction("Módulos...")
        barra.insertMenu(iface.helpMenu().menuAction(), menu)
        es = lambda t: t == "GeoCAD Yaguareté"
        assert cb.instalar(barra, es, "#3F7F3A", "#1F4A26", "#F2F7EE")
        for _ in range(20):
            QApplication.processEvents()
        accion = cb.accion_nuestra(barra, es)
        assert accion is not None, "no encuentra el ítem"
        c = color_en(barra, accion)
        salida.append(f"color con el rótulo: {c}")
        assert c == "#3F7F3A", c
        otro = iface.helpMenu().menuAction()
        c2 = color_en(barra, otro)
        salida.append(f"Ayuda queda como viene: {c2}")
        assert c2 != "#3F7F3A"
        barra.grab().save(os.environ["BANCO_SALIDA"] + ".png")
        # 3.78.2: en la QGIS de Fernando salía blanco y angosto. La barra la crea C++:
        # al soltar Python su envoltorio se perdía el rótulo (sin pintar, con la medida vieja)
        del barra, accion, otro
        gc.collect()
        barra = iface.mainWindow().menuBar()
        letra = QFont(barra.font()); letra.setPointSize(letra.pointSize() + 4); barra.setFont(letra)
        for _ in range(30):
            QApplication.processEvents()
        accion = cb.accion_nuestra(barra, es)
        rot = [w for w in barra.children() if w.objectName() == "geocad_color_barra" and hasattr(w, "isVisible")]
        salida.append(f"tras gc y letra grande: {[type(w).__name__ for w in rot]} {color_en(barra, accion)}")
        assert [type(w).__name__ for w in rot] == ["Rotulo"], rot
        assert rot[0].geometry() == barra.actionGeometry(accion), "el rótulo no siguió la medida"
        assert color_en(barra, accion) == "#3F7F3A"
        assert cb.instalar(barra, es, "#3F7F3A", "#1F4A26", "#F2F7EE")     # otra vez: no duplica
        assert len([w for w in barra.children() if type(w).__name__ == "Rotulo"]) == 1
        assert cb._filtro_de(barra) is not None
        cb.quitar(barra)
        for _ in range(20):
            QApplication.processEvents()
        c3 = color_en(barra, accion)
        salida.append(f"después de quitar: {c3}")
        assert c3 != "#3F7F3A"
        salida.append("TODO OK color de la barra en QGIS real")
    except Exception:  # noqa: BLE001
        salida.append(traceback.format_exc())
    with open(os.environ["BANCO_SALIDA"], "w", encoding="utf-8") as fh:
        fh.write("\n".join(salida) + "\n")
    os._exit(0)


QTimer.singleShot(1500, correr)
