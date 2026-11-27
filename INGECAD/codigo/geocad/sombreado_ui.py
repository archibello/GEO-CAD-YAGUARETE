# SPDX-License-Identifier: GPL-3.0-or-later
"""La categoría «Custom» en la ventana Hatch de IngeCAD (3.99.0).

GeoCAD agrega «Custom» a la lista Category. Elegida, la galería muestra una
sola muestra (CUSTOM) y, en lugar de Angle y Scale, el grupo Custom:
  Líneas (Ninguna / Simples / Dobles), Separación, Origen X e Y, Dirección
  (las líneas paralelas a ella; Giro, 0 por defecto), «Elegir en el dibujo <», Color de fondo,
  Grosor y «Crear sombreados separados». Color sigue siendo el de las líneas.
Con el módulo apagado la ventana queda como la trae IngeCAD.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QLocale, QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QWidget)

from . import sombreado as S

CLAVE_CAT = "GEOCUSTOM"
NOMBRES_LINEAS = {"ninguna": "Ninguna (sólo fondo)", "simples": "Simples", "dobles": "Dobles"}


def muestra(c=None, tam: int = 44) -> QPixmap:
    """La muestra de Custom: fondo y líneas."""
    c = S.custom_de({"custom": c or {"fondo": (200, 225, 255)}})
    pm = QPixmap(tam, tam)
    pm.fill(QColor(*c["fondo"]) if c["fondo"] is not None else QColor(240, 240, 240))
    if c["lineas"] != "ninguna":
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(40, 40, 40), 1.2))
        paso = tam / 5.0
        a0 = c["giro"]
        angulos = [a0] + ([a0 + 90.0] if c["lineas"] == "dobles" else [])
        for a in angulos:
            rad = math.radians(a)
            ux, uy = math.cos(rad), -math.sin(rad)
            nx, ny = -uy, ux
            for k in range(-8, 9):
                cx, cy = tam / 2 + nx * k * paso, tam / 2 + ny * k * paso
                p.drawLine(QPointF(cx - ux * tam * 2, cy - uy * tam * 2),
                           QPointF(cx + ux * tam * 2, cy + uy * tam * 2))
        p.end()
    return pm


def _rgb_de_aci(aci: int):
    from ezdxf.colors import aci2rgb
    r, g, b = aci2rgb(int(aci))
    return (int(r), int(g), int(b))


class PanelCustom(QGroupBox):
    """Los valores de Custom dentro de la ventana Hatch."""

    def __init__(self, dialog, settings: dict, puede_pedir: bool) -> None:
        super().__init__("Custom", dialog)
        self._dialog = dialog
        self.pedir = False
        c = S.custom_de(settings if S.es_custom(settings) else
                        {"custom": getattr(_tool(), "_custom", S.DEFECTO)})
        form = QFormLayout(self)

        self.lineas = QComboBox(self)
        for k in S.LINEAS:
            self.lineas.addItem(NOMBRES_LINEAS[k], k)
        self.lineas.setCurrentIndex(self.lineas.findData(c["lineas"]))
        form.addRow("Líneas", self.lineas)

        self.separacion = QDoubleSpinBox(self)
        self.separacion.setRange(0.0001, 1e9)
        self.separacion.setDecimals(4)
        self.separacion.setValue(c["separacion"])
        form.addRow("Separación", self.separacion)

        self.ox, self.oy = QDoubleSpinBox(self), QDoubleSpinBox(self)
        for w, v in ((self.ox, c["origen"][0]), (self.oy, c["origen"][1])):
            w.setRange(-1e12, 1e12)
            w.setDecimals(4)
            w.setValue(v)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("X", self))
        fila.addWidget(self.ox, 1)
        fila.addWidget(QLabel("Y", self))
        fila.addWidget(self.oy, 1)
        form.addRow("Origen", fila)

        self.direccion = QDoubleSpinBox(self)
        self.direccion.setRange(-360, 360)
        self.direccion.setDecimals(4)
        self.direccion.setValue(c["direccion"])
        # 3.99.2 (Fernando): «el ángulo ingresado ... siempre es relativo a la dirección
        # elegida, nunca al centro de coordenadas del espacio modelo»: la dirección sólo
        # se da con dos puntos (Elegir en el dibujo <); acá se ve, no se escribe
        self.direccion.setReadOnly(True)
        self.direccion.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.direccion.setToolTip("La dirección elegida con «Elegir en el dibujo <» (origen y "
                                  "segundo punto). Las líneas van paralelas a ella "
                                  "(las dobles, una paralela y otra perpendicular).")
        form.addRow("Dirección", self.direccion)

        self.giro = QDoubleSpinBox(self)
        self.giro.setRange(-360, 360)
        self.giro.setDecimals(4)
        self.giro.setValue(c["giro"])
        self.giro.setToolTip("Ángulo de las líneas respecto de la dirección elegida "
                             "(nunca respecto de la X del dibujo); 0 = paralelas.")
        form.addRow("Ángulo", self.giro)

        # 3.99.1 (Fernando): «las separaciones ... expresadas en decimales 0.15 con
        # punto, de la unidad del dibujo»: punto decimal, sin separador de miles
        for w in (self.separacion, self.ox, self.oy, self.direccion, self.giro):
            w.setLocale(QLocale.c())
            w.setGroupSeparatorShown(False)

        self.elegir = QPushButton("Elegir en el dibujo <", self)
        self.elegir.setToolTip("Cierra la ventana, pide el punto de origen y el segundo "
                               "punto de la dirección, y vuelve.")
        self.elegir.clicked.connect(self._pedir)
        self.elegir.setVisible(bool(puede_pedir))
        form.addRow("", self.elegir)

        self.fondo = QComboBox(self)
        self._llenar_fondo(c["fondo"])
        self.fondo.activated.connect(self._fondo_elegido)
        form.addRow("Color de fondo", self.fondo)

        self.grosor = QComboBox(self)
        self._llenar_grosor(c["grosor"])
        form.addRow("Grosor", self.grosor)

        self.separados = QCheckBox("Crear sombreados separados", self)
        self.separados.setToolTip("Una sola área por sombreado, cada una con sus islas. "
                                  "Sin tildar, todas las áreas elegidas van en uno.")
        self.separados.setChecked(c["separados"])
        form.addRow("", self.separados)

        # 3.99.2: el estilo (sin origen ni dirección) queda en la galería, para usarlo otra vez
        self.guardar = QPushButton("Guardar estilo...", self)
        self.guardar.setToolTip("Guarda líneas, separación, giro, colores y grosor con un nombre: "
                                "queda en la galería de Custom. Botón derecho sobre un estilo: "
                                "Renombrar o Borrar.")
        self.guardar.clicked.connect(lambda: guardar_estilo(self._dialog))
        form.addRow("", self.guardar)

        for w in (self.lineas, self.fondo):
            w.currentIndexChanged.connect(self._repintar)
        self.lineas.currentIndexChanged.connect(self._habilitar)
        self._habilitar()

    # -- colores y grosores --------------------------------------------------------
    def _llenar_fondo(self, rgb) -> None:
        self.fondo.addItem("Ninguno", None)
        try:
            from views.layers_panel import fill_color_combo
            tmp = QComboBox()
            fill_color_combo(tmp, include_bylayer=False)
            for i in range(tmp.count()):
                aci = tmp.itemData(i)
                if isinstance(aci, int) and 1 <= aci <= 255:
                    self.fondo.addItem(tmp.itemIcon(i), tmp.itemText(i), _rgb_de_aci(aci))
        except Exception:  # noqa: BLE001
            pass
        self._con_rgb(rgb)
        self.fondo.addItem("Elegir color...", "elegir")

    def _con_rgb(self, rgb) -> None:
        if rgb is None:
            self.fondo.setCurrentIndex(0)
            return
        rgb = tuple(rgb)
        for i in range(self.fondo.count()):
            if self.fondo.itemData(i) == rgb:
                self.fondo.setCurrentIndex(i)
                return
        pm = QPixmap(14, 14)
        pm.fill(QColor(*rgb))
        donde = max(1, self.fondo.count() - (1 if self.fondo.itemData(self.fondo.count() - 1) == "elegir" else 0))
        self.fondo.insertItem(donde, QIcon(pm), "%d,%d,%d" % rgb, rgb)
        self.fondo.setCurrentIndex(donde)

    def _fondo_elegido(self, i: int) -> None:
        if self.fondo.itemData(i) != "elegir":
            return
        color = QColorDialog.getColor(QColor(255, 255, 255), self, "Color de fondo")
        if color.isValid():
            self._con_rgb((color.red(), color.green(), color.blue()))
        else:
            self.fondo.setCurrentIndex(0)

    def _llenar_grosor(self, valor: int) -> None:
        try:
            from views.layers_panel import lineweight_icon
        except Exception:  # noqa: BLE001
            lineweight_icon = None
        for texto, v in (("PorCapa", -1), ("PorBloque", -2), ("Por defecto", -3)):
            self.grosor.addItem(texto, v)
        try:
            from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS
            pesos = VALID_DXF_LINEWEIGHTS
        except Exception:  # noqa: BLE001
            pesos = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90,
                     100, 106, 120, 140, 158, 200, 211)
        for v in pesos:
            texto = "%.2f mm" % (v / 100.0)
            if lineweight_icon is not None:
                try:
                    self.grosor.addItem(QIcon(lineweight_icon(v)), texto, v)
                    continue
                except Exception:  # noqa: BLE001
                    pass
            self.grosor.addItem(texto, v)
        i = self.grosor.findData(int(valor))
        self.grosor.setCurrentIndex(i if i >= 0 else 0)

    # -- estado --------------------------------------------------------------------
    def _habilitar(self) -> None:
        con_lineas = self.lineas.currentData() != "ninguna"
        for w in (self.separacion, self.ox, self.oy, self.giro, self.grosor):
            w.setEnabled(con_lineas)
        self.elegir.setEnabled(con_lineas)
        if not con_lineas and self.fondo.currentData() is None:
            self._con_rgb((255, 255, 255))     # sin líneas, el fondo es todo

    def poner_estilo(self, estilo: dict) -> None:
        """Un estilo guardado en los campos (origen y dirección quedan)."""
        c = S.aplicar_estilo(self.valores(), estilo)
        self.lineas.setCurrentIndex(self.lineas.findData(c["lineas"]))
        self.separacion.setValue(c["separacion"])
        self.giro.setValue(c["giro"])
        self._con_rgb(c["fondo"])
        i = self.grosor.findData(int(c["grosor"]))
        self.grosor.setCurrentIndex(i if i >= 0 else 0)
        color = getattr(self._dialog, "color", None)
        if color is not None and "color" in estilo:
            j = color.findData(int(estilo["color"]))
            if j >= 0:
                color.setCurrentIndex(j)
        self._habilitar()

    def _repintar(self, *_a) -> None:
        _refrescar_muestra(self._dialog)

    def _pedir(self) -> None:
        self.pedir = True
        self._dialog.accept()

    def valores(self) -> dict:
        fondo = self.fondo.currentData()
        if fondo == "elegir":
            fondo = None
        c = {
            "lineas": self.lineas.currentData(),
            "separacion": self.separacion.value(),
            "origen": (self.ox.value(), self.oy.value()),
            "direccion": self.direccion.value(),
            "giro": self.giro.value(),
            "fondo": fondo,
            "grosor": self.grosor.currentData(),
            "separados": self.separados.isChecked(),
        }
        c = S.custom_de({"custom": c})
        if self.pedir:
            c["_pedir"] = True
        return c


def _tool():
    try:
        from .sombreado_herramienta import GeoHatchTool
        return GeoHatchTool
    except Exception:  # noqa: BLE001
        return None


def _es_cat_custom(dialog) -> bool:
    cat = getattr(dialog, "category", None)
    return cat is not None and cat.currentData() == CLAVE_CAT


def _refrescar_muestra(dialog) -> None:
    panel = getattr(dialog, "_geo_custom", None)
    if panel is None or not _es_cat_custom(dialog):
        return
    item = dialog.gallery.item(0) if dialog.gallery.count() else None
    if item is not None:
        item.setIcon(QIcon(muestra(panel.valores())))


def _estilo_del_item(item):
    nombre = item.data(Qt.UserRole) if item is not None else None
    if isinstance(nombre, str) and nombre.startswith(S.PREFIJO):
        return nombre[len(S.PREFIJO):]
    return None


def _elegido(dialog, item) -> None:
    """Clic en un estilo guardado de la galería: sus valores al grupo Custom."""
    nombre = _estilo_del_item(item)
    if nombre is None or not _es_cat_custom(dialog):
        return
    estilo = S.estilos().get(nombre)
    if estilo is not None:
        dialog._geo_custom.poner_estilo(estilo)


def _rellenar(dialog, elegir=None) -> None:
    if elegir is not None:
        dialog._current_pattern = elegir
    dialog._fill_gallery()


def guardar_estilo(dialog) -> None:
    panel = dialog._geo_custom
    actual = _estilo_del_item(dialog.gallery.currentItem()) or ""
    nombre, ok = QInputDialog.getText(dialog, "Guardar estilo", "Nombre del estilo:", text=actual)
    nombre = str(nombre).strip()
    if not ok or not nombre:
        return
    if nombre in S.estilos() and QMessageBox.question(
            dialog, "Guardar estilo", f"Ya hay un estilo «{nombre}». ¿Reemplazarlo?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
        return
    color = getattr(dialog, "color", None)
    S.guardar_estilo(nombre, panel.valores(),
                     int(color.currentData()) if color is not None and color.currentData() is not None else 256)
    _rellenar(dialog, S.PREFIJO + nombre)


def _menu(dialog, pos) -> None:
    item = dialog.gallery.itemAt(pos)
    nombre = _estilo_del_item(item)
    if nombre is None or not _es_cat_custom(dialog):
        return
    menu = QMenu(dialog.gallery)
    renombrar = menu.addAction("Renombrar...")
    borrar = menu.addAction("Borrar")
    accion = menu.exec(dialog.gallery.viewport().mapToGlobal(pos))
    if accion is renombrar:
        nuevo, ok = QInputDialog.getText(dialog, "Renombrar estilo", "Nombre nuevo:", text=nombre)
        nuevo = str(nuevo).strip()
        if ok and nuevo and nuevo != nombre:
            if S.renombrar_estilo(nombre, nuevo):
                _rellenar(dialog, S.PREFIJO + nuevo)
            else:
                QMessageBox.information(dialog, "Renombrar estilo", f"Ya hay un estilo «{nuevo}».")
    elif accion is borrar:
        if QMessageBox.question(dialog, "Borrar estilo", f"¿Borrar el estilo «{nombre}»?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            S.borrar_estilo(nombre)
            _rellenar(dialog, S.CUSTOM)


def _mostrar(dialog) -> None:
    """Custom elegida: su grupo a la vista, Angle y Scale escondidos."""
    panel = getattr(dialog, "_geo_custom", None)
    if panel is None:
        return
    es = _es_cat_custom(dialog)
    panel.setVisible(es)
    form = getattr(dialog, "_geo_form", None)
    for w in (getattr(dialog, "angle", None), getattr(dialog, "scale", None)):
        if w is None:
            continue
        w.setVisible(not es)
        if form is not None:
            etiqueta = form.labelForField(w)
            if etiqueta is not None:
                etiqueta.setVisible(not es)
    if es:
        dialog._current_pattern = S.CUSTOM
        _refrescar_muestra(dialog)
    dialog.adjustSize()


def agregar(dialog, settings: dict) -> None:
    """Custom en una ventana Hatch ya armada por IngeCAD."""
    dialog.category.addItem("Custom", CLAVE_CAT)
    panel = PanelCustom(dialog, settings, bool(settings.get("_puede_pedir")))
    dialog._geo_custom = panel
    layout = dialog.layout()
    # top, galería, formulario (Angle, Scale, Color), botones: Custom antes de los botones
    dialog._geo_form = None
    for i in range(layout.count()):
        sub = layout.itemAt(i).layout()
        if isinstance(sub, QFormLayout):
            dialog._geo_form = sub
    layout.insertWidget(max(0, layout.count() - 1), panel)
    if dialog._geo_form is not None:
        lbl = dialog._geo_form.labelForField(dialog.color)
        if lbl is not None:
            lbl.setText("Color")
            lbl.setToolTip("En Custom: el color de las líneas.")
    dialog.category.currentIndexChanged.connect(lambda *_a: _mostrar(dialog))
    dialog.gallery.currentItemChanged.connect(lambda item, _prev: _elegido(dialog, item))
    dialog.gallery.setContextMenuPolicy(Qt.CustomContextMenu)
    dialog.gallery.customContextMenuRequested.connect(lambda pos: _menu(dialog, pos))
    if S.es_custom(settings):
        dialog.category.setCurrentIndex(dialog.category.findData(CLAVE_CAT))
    _mostrar(dialog)


# -- envoltorios -------------------------------------------------------------------------
def _envolver_init(original):
    def __init__(self, parent, settings, *args, **kwargs):
        original(self, parent, settings, *args, **kwargs)
        if S.activo():
            try:
                agregar(self, dict(settings or {}))
            except Exception:  # noqa: BLE001 -- la ventana sigue como la trae IngeCAD
                pass
    __init__._puente_original = original
    __init__._puente_fabrica = _envolver_init
    return __init__


def _envolver_nombres(original):
    def _names_for(self, key, *args, **kwargs):
        if key == CLAVE_CAT:
            return [S.CUSTOM] + [S.PREFIJO + n for n in S.estilos()]
        return original(self, key, *args, **kwargs)
    _names_for._puente_original = original
    _names_for._puente_fabrica = _envolver_nombres
    return _names_for


def _envolver_muestra(original):
    def _pattern_pixmap(name, *args, **kwargs):
        if str(name).upper() == S.CUSTOM:
            return muestra()
        if str(name).startswith(S.PREFIJO):
            return muestra(S.estilos().get(str(name)[len(S.PREFIJO):]))
        return original(name, *args, **kwargs)
    _pattern_pixmap._puente_original = original
    _pattern_pixmap._puente_fabrica = _envolver_muestra
    return _pattern_pixmap


def _envolver_galeria(original):
    def _fill_gallery(self, *_args, **_kwargs):
        # la señal de Category trae el número de la fila: IngeCAD no lo recibe
        resultado = original(self)
        if getattr(self, "_geo_custom", None) is not None and _es_cat_custom(self):
            for i in range(self.gallery.count()):          # el nombre del estilo, sin «CUSTOM:»
                item = self.gallery.item(i)
                nombre = _estilo_del_item(item)
                if nombre is not None:
                    item.setText(nombre)
                    item.setToolTip(nombre)
        return resultado
    _fill_gallery._puente_original = original
    _fill_gallery._puente_fabrica = _envolver_galeria
    return _fill_gallery


def _envolver_settings(original):
    def settings(self, *args, **kwargs):
        resultado = original(self, *args, **kwargs)
        panel = getattr(self, "_geo_custom", None)
        if panel is not None and _es_cat_custom(self):
            c = panel.valores()
            resultado = dict(resultado)
            resultado["pattern"] = S.CUSTOM
            resultado["custom"] = c
            resultado["scale"] = c["separacion"]
            resultado["angle"] = c["direccion"]
        return resultado
    settings._puente_original = original
    settings._puente_fabrica = _envolver_settings
    return settings


def instalar() -> None:
    from views import hatch_dialog
    from views.hatch_dialog import HatchDialog
    from .dibujo import envolver
    envolver(HatchDialog, "__init__", _envolver_init, reemplazar=True)
    envolver(HatchDialog, "_names_for", _envolver_nombres, reemplazar=True)
    envolver(HatchDialog, "settings", _envolver_settings, reemplazar=True)
    envolver(HatchDialog, "_fill_gallery", _envolver_galeria, reemplazar=True)
    envolver(hatch_dialog, "_pattern_pixmap", _envolver_muestra, reemplazar=True)
