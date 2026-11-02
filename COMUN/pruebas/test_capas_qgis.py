"""Panel Capas de IngeCAD en QGIS (3.60.0), sin Qt: los filtros de grupo
(capas/filtros.py), que el panel y la barra son los de IngeCAD 0.7.0 (columnas,
textos, reglas) y que el panel viejo ya no está. Lo que se ve y se toca en
QGIS lo prueba ventana/banco_capas_qgis.py con el QGIS real.

Fernando, 01/11/2026: «reemplaces por completo el panel administrador de
capas de QGIS (Yaguá Capas) por el de IngeCAD y que adoptes todos sus
comportamientos»."""
import tmp_pruebas  # lo temporal de la prueba se borra al salir
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPAS = ROOT / "QGIS" / "codigo" / "geocad" / "capas"


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


F = cargar("filtros", CAPAS / "filtros.py")

# ---- 1. filtros de grupo --------------------------------------------------------------
fs = F.normalize([{"name": "A", "layers": ["c1", "c1", 3], "children": [{"name": "h"}]},
                  {"name": "H"}, "x", {"name": " "}, {"name": "B"}])
assert fs == [{"name": "A", "layers": ["c1"], "children": [{"name": "h", "layers": [], "children": []}]},
              {"name": "B", "layers": [], "children": []}], fs      # «H» repetido (sin mayúsculas) fuera
assert [(p, d) for p, d, _f in F.rows(fs)] == [(("A",), 0), (("A", "h"), 1), (("B",), 0)]
assert F.find(fs, ("A", "h"))["name"] == "h" and F.find(fs, ("A", "x")) is None
assert F.unique_name(fs) == "Filtro de grupo1"
p = F.new_group(fs)
assert p == ("Filtro de grupo1",) and F.unique_name(fs) == "Filtro de grupo2"
assert F.new_group(fs, ("A",), "Hijo", ["c2", "c2", "c3"]) == ("A", "Hijo")
assert F.find(fs, ("A", "Hijo"))["layers"] == ["c2", "c3"]
assert F.new_group(fs, (), "b") is None                     # «B» ya existe
assert F.new_group(fs, ("NoEsta",), "Z") is None
assert F.rename(fs, ("A", "Hijo"), "B") == "Ya existe un filtro llamado B."
assert F.rename(fs, ("A", "Hijo"), "Nuevo") is None and F.find(fs, ("A", "Nuevo"))
assert F.group_layers(fs, ("B",), ["c1", "c2"]) == 2
assert F.group_layers(fs, ("B",), ["c1"]) == 0               # ya estaba
assert F.group_layers(fs, ("B",), ["c1"], add=False) == 1 and F.find(fs, ("B",))["layers"] == ["c2"]
F.rename_layer(fs, "c2", "C2")
assert F.find(fs, ("B",))["layers"] == ["C2"] and F.find(fs, ("A", "Nuevo"))["layers"] == ["C2", "c3"]
F.drop_layers(fs, ["C2"])
assert F.find(fs, ("A", "Nuevo"))["layers"] == ["c3"] and F.find(fs, ("B",))["layers"] == []
assert F.delete(fs, ("A",)) and F.find(fs, ("A", "Nuevo")) is None
assert not F.delete(fs, ("A",)) and not F.delete(fs, ())
print("ok filtros de grupo")

# ---- 2. el panel es el de IngeCAD 0.7.0 ---------------------------------------------------
panel = (CAPAS / "panel.py").read_text(encoding="utf-8")
for texto in ("'Estado'", "'Nombre'", "'Encendida/Apagada'", "'Inut'", "'Bloq'", "'Color'",
              "'Tipo de línea'", "'Grosor de línea'", "'Imprimir'", "'Descripción'",
              "'Nueva capa'", "'Eliminar capa'", "'Establecer actual'", "'Nuevo filtro de grupo'",
              "'Buscar capa'", "'Optimizar todas las columnas'", "'Todas las capas utilizadas'",
              "'Añadir al grupo'", "'Nuevo grupo con estas capas'", "'Quitar del grupo'",
              "'Activar capas'", "'Inutilizar capas'", "'Bloquear capas'", "'Capa vacía'",
              "'No se puede eliminar la capa actual.'", "'La capa %s está en uso.'"):
    assert texto in panel, texto
assert "(C_STATUS, C_NAME, C_ON, C_FRZ, C_LCK, C_COLOR, C_LT, C_LW, C_PLOT, C_DESC) = range(10)" in panel
assert "DEFAULT_HIDDEN = str(C_DESC)" in panel            # Descripción oculta de entrada
assert "if col != C_NAME:\n            self.make_current" in panel   # doble clic = actual
# lo propio de GeoCAD que IngeCAD no tiene, fuera (acordado)
for fuera in ("Transparencia", "Invertir filtro", "borrador", "Capas no utilizadas"):
    assert fuera not in panel, fuera
assert not (CAPAS / "manager.py").exists()
plugin = (CAPAS / "plugin.py").read_text(encoding="utf-8")
assert "LayerManagerDock" not in plugin and "LayersDock" in plugin
assert "self.dock.setFloating(True)" not in plugin        # acoplado, como la pestaña de IngeCAD
# la barra de IngeCAD: la lista de capa + Color, Tipo y Grosor; 3.60.2: y el botón del panel
assert plugin.count("self.toolbar.addAction") == 1 and "self.toolbar.addAction(self.a_props)" in plugin
assert "self.toolbar.addSeparator" not in plugin
# 3.60.2 (Fernando: «no está el panel de capas Yaguá»): a la vista desde el arranque
assert "if self.ctrl.setting('panel/visible', True, bool):" in plugin
assert "TITLE = 'Yaguá Capas'" in panel
# 3.60.3 (Fernando): con los colores del tema de QGIS, no los de IngeCAD
assert "background" not in panel.split("PANEL_STYLE")[1].split('"""')[1] and "#1e1e22" not in panel
for clave in ("'capa'", "'color'", "'linetype'", "'lineweight'"):
    assert clave in plugin, clave
barra = (CAPAS / "barra.py").read_text(encoding="utf-8")
for texto in ("'PorCapa'", "'Seleccionar color...'", "'Otro...'", "'Por defecto'", "'%s actual: %s'"):
    assert texto in barra, texto
assert "set_selection_prop" in barra and "set_current_prop" in barra   # selección o lo próximo
combo = (CAPAS / "layer_combo.py").read_text(encoding="utf-8")
assert "set_selection_prop('color', None)" in combo and "set_current_prop('color', None)" in combo
# 3.60.1 (Fernando): después de asignar desde la barra se quita la selección, para ver el resultado
assert "self.ctrl.clear_selection()" in combo and "self.ctrl.clear_selection()" in barra
ctrl = (CAPAS / "controller.py").read_text(encoding="utf-8")
assert "'filters': self.cfg.get('filters', [])" in ctrl     # CAPAP deshace también los grupos
assert "filtros.rename_layer" in ctrl and "filtros.drop_layers" in ctrl
dib = (ROOT / "QGIS/codigo/geocad/dibujo/commands.py").read_text(encoding="utf-8")
assert dib.count("self._current_attrs(layer)") == 2 and "new_feature_attrs" in dib
# 3.60.4 (Fernando: «minimizar y maximizar no responden»): el panel a la derecha, solo,
# con nombre nuevo (el viejo traía guardada la pestaña) y poca altura mínima
assert "RightDockWidgetArea" in plugin and "tabifyDockWidget" not in plugin
assert "self.setObjectName('YaguaCapasDock')" in panel and "self.table.setMinimumHeight(48)" in panel
# y el aviso de ventana más alta que la pantalla (lo medido en su perfil)
V = cargar("ventana_alta", ROOT / "QGIS/codigo/geocad/ventana_alta.py")
col = {1: [("Navegador", 153), ("Editor de vértices", 151), ("Capas", 153)], 2: [("Yaguá Capas", 111)]}
t = V.texto_aviso(1035, 1080, col)
assert t and "1035" in t and "994" in t and "izquierda" in t and "Editor de vértices" in t, t
assert V.texto_aviso(913, 1080, col) is None              # con dos en pestaña entra
assert V.texto_aviso(994, 1080, col) is None
assert "quitá alguna fila" in V.texto_aviso(1100, 1080, {1: [("Capas", 153)]})
gc = (ROOT / "QGIS/codigo/geocad/plugin.py").read_text(encoding="utf-8")
assert "ventana_alta.revisar(" in gc
# 3.60.5: un latido del reloj después de descargar no vuelve a armar las barras
assert "        if self.menu is None:\n            return          # ya descargado" in gc
# 3.60.5 (Fernando: «qué ítems están agrandando el ancho... las mismas configuraciones»):
# las medidas de IngeCAD aunque QGIS tenga letra y encabezados más grandes
assert "(C_LT, 'Tipo', 'Tipo de línea', None)" in panel and "(C_LW, 'Grosor', 'Grosor de línea', None)" in panel
assert "ICON_WIDTH = 28" in panel and "'Por defecto'" in panel and "Predeterminado'" not in panel
assert "chica.setPixelSize(11)" in panel and "setFixedHeight(24)" in panel
print("ok panel y barra de IngeCAD")
print("TODO OK")
