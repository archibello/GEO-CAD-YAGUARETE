"""Color propio del menú GeoCAD (prueba de 12/11/2026, opción B de Fernando):
bordó profundo en IngeCAD, verde bosque en QGIS, sólo en NUESTRO menú."""
import tmp_pruebas  # noqa: F401 - lo temporal de la prueba se borra al salir
import importlib.util
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# --- IngeCAD: el módulo no necesita Qt para cargarse
spec = importlib.util.spec_from_file_location("color_menu", RAIZ / "INGECAD/codigo/geocad/color_menu.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)


class Menu:
    def __init__(self, titulo):
        self._t, self.estilo = titulo, ""
    def title(self): return self._t
    def styleSheet(self): return self.estilo
    def setStyleSheet(self, e): self.estilo = e


class Accion:
    def __init__(self, menu): self._m = menu
    def menu(self): return self._m


class Barra:
    def __init__(self, menus): self._a = [Accion(m) for m in menus]
    def actions(self): return self._a


class Ventana:
    def __init__(self, menus): self._menu_bar = Barra(menus)


editar, geocad, ayuda = Menu("&Edit"), Menu("GeoCAD Yaguaret&é"), Menu("&Help")
v = Ventana([editar, geocad, ayuda])
v._menu_bar._a.insert(1, Accion(None))           # una acción sin menú no molesta
assert cm.aplicar(v) is True
assert geocad.estilo == cm.ESTILO and "#430E18" in cm.ESTILO and "#7D1C2C" in cm.ESTILO
assert editar.estilo == "" and ayuda.estilo == "", "los menús de IngeCAD quedan como vienen"
assert cm.aplicar(Ventana([editar])) is False      # sin nuestro menú: nada
assert cm.aplicar(object()) is False               # nunca tira abajo a IngeCAD

# se vuelve a aplicar cuando IngeCAD rearma los menús (envoltorio de _build_menus)
fuente = (RAIZ / "INGECAD/codigo/geocad/pegar_lugar_ingecad.py").read_text(encoding="utf-8")
assert "color_menu.aplicar(self)" in fuente

# --- QGIS: verde bosque y título de sección propio (addSection no se ve con estilo)
qg = (RAIZ / "QGIS/codigo/geocad/plugin.py").read_text(encoding="utf-8")
estilo = re.search(r'ESTILO_MENU = """(.*?)"""', qg, re.S).group(1)
assert "#1F4A26" in estilo and "#3F7F3A" in estilo
assert "self.menu.setStyleSheet(ESTILO_MENU)" in qg
assert 'self._titulo_seccion("Puente con IngeCAD")' in qg and "addSection(" not in qg

# --- 3.78.1: el título en la barra de menús, del mismo color (color_barra, núcleo)
nucleo = (RAIZ / "COMUN/nucleo/color_barra.py").read_text(encoding="utf-8")
for lado in ("INGECAD", "QGIS"):
    assert (RAIZ / lado / "codigo/geocad/color_barra.py").read_text(encoding="utf-8") == nucleo, lado
assert "obj.event(" not in nucleo, "PyQt no deja llamar funciones protegidas de la barra de QGIS (C++)"
assert 'color_barra.instalar(menubar, lambda t: t == MENU_TITLE, "#3F7F3A", "#1F4A26"' in qg   # 3.78.3: claro
assert "color_barra.quitar(self.iface.mainWindow().menuBar())" in qg     # apagado no deja rastro
ing = (RAIZ / "INGECAD/codigo/geocad/color_menu.py").read_text(encoding="utf-8")
assert "color_barra.instalar(barra_de(window), _es_nuestro, BARRA, BARRA_ACTIVA, LETRA)" in ing.replace("\n", " ")
assert (cm.BARRA, cm.BARRA_ACTIVA) == ("#7D1C2C", "#430E18")      # 3.78.3: claro; abierto, el del menú
assert cm.FONDO == "#430E18" and cm.FONDO in cm.ESTILO and cm.RESALTADO in cm.ESTILO

spec = importlib.util.spec_from_file_location("color_barra", RAIZ / "COMUN/nucleo/color_barra.py")
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)
assert cb._limpio("GeoCAD Yaguaret&é") == "GeoCAD Yaguareté" and cb._limpio("A && B") == "A & B"
assert cb.instalar(None, None, "#000", "#000", "#fff") is False
assert cb.instalar(object(), None, "#000", "#000", "#fff") is False   # sin Qt: no tira abajo nada
cb.quitar(object())
# 3.78.2: nada colgado de la barra (en QGIS su envoltorio de Python se pierde)
assert "setattr(barra" not in nucleo and "_VIVOS.append(filtro)" in nucleo
assert "_retirar_otros(barra)" in nucleo          # actualizar sin reiniciar: un solo rótulo

print("TODO OK: color del menú GeoCAD (IngeCAD bordó, QGIS verde) y su título en la barra")
