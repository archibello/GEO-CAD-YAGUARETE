# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanas del módulo «Impresión» (3.7.0): VISTAPREVIA, el editor de plumas
y los botones Editar... / Vista previa... de Page Setup. Las cuentas están
en impresion.py."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPicture, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QAbstractItemView)

from . import impresion as I

#: Puntos de la vista previa por mm de hoja (se graba en vectores: el zoom
#: no pierde definición).
_PX_MM = 10.0


def _mm(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _rgb_aci(aci: int) -> tuple[int, int, int]:
    from ezdxf import colors
    return colors.int2rgb(colors.DXF_DEFAULT_COLORS[aci])


def _muestra(rgb) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(QColor(*rgb))
    return QIcon(pix)


# ---------------------------------------------------------------- vista previa
class _Hoja:
    """Hace de impresora para pdf_out.plot: una hoja de ``ancho`` × ``alto``
    mm a _PX_MM puntos por mm; lo dibujado queda en un QPicture."""

    class Unit:
        DevicePixel = 0

    def __init__(self, ancho_mm: float, alto_mm: float) -> None:
        self.ancho, self.alto = ancho_mm, alto_mm

    def pageRect(self, _unidad=None) -> QRectF:
        return QRectF(0.0, 0.0, self.ancho * _PX_MM, self.alto * _PX_MM)

    def resolution(self) -> float:
        return _PX_MM * 25.4

    def setFullPage(self, _si: bool) -> None:
        pass


def grabar(document, layout_name: str, ctb: str):
    """(QPicture, ancho_mm, alto_mm): la presentación tal como la imprime
    IngeCAD (con GeoCAD: escala de la hoja, plumas de ``ctb``)."""
    from formats import pdf_out

    (ancho, alto), _hoja = pdf_out.layout_sheet(document, layout_name)
    hoja = _Hoja(ancho, alto)
    dibujo = QPicture()
    pintor = QPainter(dibujo)
    try:
        pdf_out.plot_layout(document, hoja, layout_name, ctb=ctb, painter=pintor)
    finally:
        pintor.end()
    return dibujo, ancho, alto


class Visor(QWidget):
    """La hoja blanca sobre fondo gris; rueda = zoom, arrastrar = mover."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(500, 350)
        self.dibujo = None
        self.ancho = self.alto = 1.0
        self.zoom = 1.0                       # píxeles de pantalla por mm
        self.origen = QPointF(0, 0)
        self._arrastre = None
        self._ajustada = True
        self.al_cambiar = None

    def mostrar(self, dibujo, ancho: float, alto: float) -> None:
        nueva_hoja = (abs(ancho - self.ancho) > 1e-6 or abs(alto - self.alto) > 1e-6)
        self.dibujo, self.ancho, self.alto = dibujo, ancho, alto
        if nueva_hoja or self._ajustada:
            self.ajustar()
        self.update()

    def ajustar(self) -> None:
        m = 24
        self.zoom = max(1e-3, min((self.width() - 2 * m) / self.ancho,
                                  (self.height() - 2 * m) / self.alto))
        self.origen = QPointF((self.width() - self.ancho * self.zoom) / 2,
                              (self.height() - self.alto * self.zoom) / 2)
        self._ajustada = True
        self._avisar()
        self.update()

    def tamano_real(self) -> None:
        centro = QPointF(self.width() / 2, self.height() / 2)
        self._zoom_en(centro, (self.logicalDpiX() / 25.4) / self.zoom)

    def porcentaje(self) -> float:
        return 100.0 * self.zoom / (self.logicalDpiX() / 25.4)

    def _avisar(self) -> None:
        if self.al_cambiar is not None:
            self.al_cambiar()

    def _zoom_en(self, punto: QPointF, factor: float) -> None:
        factor = max(0.02 / self.zoom, min(factor, 400.0 / self.zoom))
        self.origen = punto - (punto - self.origen) * factor
        self.zoom *= factor
        self._ajustada = False
        self._avisar()
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(110, 110, 110))
        hoja = QRectF(self.origen.x(), self.origen.y(),
                      self.ancho * self.zoom, self.alto * self.zoom)
        p.fillRect(hoja.translated(4, 4), QColor(60, 60, 60))
        p.fillRect(hoja, Qt.white)
        if self.dibujo is not None:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            p.setClipRect(hoja)
            p.translate(self.origen)
            p.scale(self.zoom / _PX_MM, self.zoom / _PX_MM)
            p.drawPicture(0, 0, self.dibujo)
        p.end()

    def wheelEvent(self, evento) -> None:
        pasos = evento.angleDelta().y() / 120.0
        if pasos:
            self._zoom_en(evento.position(), 1.25 ** pasos)

    def mousePressEvent(self, evento) -> None:
        if evento.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._arrastre = evento.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        if self._arrastre is not None:
            self.origen += evento.position() - self._arrastre
            self._arrastre = evento.position()
            self._ajustada = False
            self.update()

    def mouseReleaseEvent(self, _evento) -> None:
        self._arrastre = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, evento) -> None:
        if evento.button() == Qt.MiddleButton:
            self.ajustar()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        if self._ajustada:
            self.ajustar()


def _llenar_tablas(combo: QComboBox, actual: str) -> None:
    from core import plotstyles

    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Ninguna", "")
    for nombre in plotstyles.available():
        combo.addItem(nombre, nombre)
    if actual and combo.findData(actual) < 0:
        combo.addItem(actual, actual)
    combo.setCurrentIndex(max(0, combo.findData(actual or "")))
    combo.blockSignals(False)


class VistaPrevia(QDialog):
    """VISTAPREVIA: la presentación como sale impresa.

    ``provisoria(hacer)`` (desde Page Setup) dibuja con la página elegida
    todavía sin aplicar; ``imprimir`` (desde la orden) cierra y abre PLOT.
    """

    def __init__(self, parent, document, layout_name: str, ctb: str,
                 provisoria=None, imprimir=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Vista previa — {layout_name}")
        self.resize(1000, 720)
        self.document, self.layout_name = document, layout_name
        self.provisoria = provisoria
        self.ctb = ctb or ""
        self.imprimir_pedido = False

        self.visor = Visor(self)
        self.info = QLabel(self)
        self.tablas = QComboBox(self)
        _llenar_tablas(self.tablas, self.ctb)
        self.tablas.currentIndexChanged.connect(self._otra_tabla)
        editar = QPushButton("Editar plumas...", self)
        editar.clicked.connect(self._editar)
        ajustar = QPushButton("Ajustar hoja", self)
        ajustar.clicked.connect(self.visor.ajustar)
        real = QPushButton("Tamaño real", self)
        real.clicked.connect(self.visor.tamano_real)

        arriba = QHBoxLayout()
        arriba.addWidget(QLabel("Plumas:", self))
        arriba.addWidget(self.tablas)
        arriba.addWidget(editar)
        arriba.addStretch(1)
        arriba.addWidget(ajustar)
        arriba.addWidget(real)

        botones = QDialogButtonBox(self)
        if imprimir is not None:
            b = botones.addButton("Imprimir...", QDialogButtonBox.AcceptRole)
            b.clicked.connect(self._imprimir)
        cerrar = botones.addButton("Cerrar", QDialogButtonBox.RejectRole)
        cerrar.clicked.connect(self.reject)
        abajo = QHBoxLayout()
        abajo.addWidget(self.info, 1)
        abajo.addWidget(botones)

        caja = QVBoxLayout(self)
        caja.addLayout(arriba)
        caja.addWidget(self.visor, 1)
        caja.addLayout(abajo)
        self.visor.al_cambiar = self._info
        self._dibujar()

    def _dibujar(self) -> None:
        hacer = lambda: grabar(self.document, self.layout_name, self.ctb)  # noqa: E731
        try:
            dibujo, ancho, alto = (self.provisoria(hacer) if self.provisoria
                                   else hacer())
        except Exception as error:  # noqa: BLE001
            QMessageBox.warning(self, "Vista previa",
                                f"No se pudo dibujar la vista previa:\n{error}")
            return
        self.visor.mostrar(dibujo, ancho, alto)
        self._info()

    def _info(self) -> None:
        self.info.setText(
            f"Hoja {_mm(self.visor.ancho)} × {_mm(self.visor.alto)} mm · "
            f"Plumas: {self.ctb or 'ninguna'} · Zoom {self.visor.porcentaje():.0f} % "
            "· Rueda: zoom · Arrastrar: mover")

    def _otra_tabla(self) -> None:
        self.ctb = self.tablas.currentData() or ""
        self._dibujar()

    def _editar(self) -> None:
        editor = EditorPlumas(self, self.ctb)
        editor.exec()
        if editor.guardada:
            self.ctb = editor.guardada
            _llenar_tablas(self.tablas, self.ctb)
        self._dibujar()

    def _imprimir(self) -> None:
        self.imprimir_pedido = True
        self.accept()


# ---------------------------------------------------------------- editor de plumas
class EditorPlumas(QDialog):
    """PLUMAS: la tabla de plumas como el editor de AutoCAD. Una fila por
    color de AutoCAD (1 Rojo, 2 Amarillo, 3 Verde...); se eligen una o varias
    y se cambia el color de impresión, el grosor, el tramado y los grises."""

    COLUMNAS = ("Color del objeto", "Color de impresión", "Grosor", "Tramado",
                "Grises", "Descripción")

    def __init__(self, parent, nombre: str = "") -> None:
        super().__init__(parent)
        self.resize(940, 640)
        self.guardada = ""
        self.modificada = False
        self.ruta = None
        from core import plotstyles

        ruta = plotstyles.resolve(nombre) if nombre else None
        if ruta is not None and ruta.suffix.lower() == ".ctb":
            self.tabla = I.leer(ruta)
            self.ruta = ruta
        else:
            base = plotstyles.resolve("acad.ctb")
            self.tabla = I.leer(base) if base else I.nueva()
        self._titulo()

        self.lista = QTableWidget(255, len(self.COLUMNAS), self)
        self.lista.setHorizontalHeaderLabels(self.COLUMNAS)
        self.lista.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lista.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lista.verticalHeader().setVisible(False)
        for aci in range(1, 256):
            celda = QTableWidgetItem(_muestra(_rgb_aci(aci)), I.nombre_color(aci))
            self.lista.setItem(aci - 1, 0, celda)
            self._fila(aci)
        self.lista.resizeColumnsToContents()
        self.lista.setColumnWidth(2, 80)
        self.lista.horizontalHeader().setStretchLastSection(True)
        self.lista.itemSelectionChanged.connect(self._cargar)

        # -- propiedades de las plumas elegidas
        self.grupo = QGroupBox(self)
        form = QFormLayout(self.grupo)
        self.color = QComboBox(self)
        for texto in ("Usar color del objeto", "Negro", "Elegir color..."):
            self.color.addItem(texto)
        self.color.activated.connect(self._color)
        self.grosor = QComboBox(self)
        self.grosor.addItem("Usar grosor del objeto", 0.0)
        for mm in I.GROSORES[1:]:
            self.grosor.addItem(f"{_mm(mm)} mm", mm)
        self.grosor.activated.connect(
            lambda _i: self._cambiar(grosor=self.grosor.currentData()))
        self.tramado = QSpinBox(self)
        self.tramado.setRange(0, 100)
        self.tramado.setSuffix(" %")
        self.tramado.editingFinished.connect(
            lambda: self._cambiar(tramado=self.tramado.value()))
        self.grises = QCheckBox("Imprimir en escala de grises", self)
        self.grises.clicked.connect(lambda si: self._cambiar(grises=si))
        self.descripcion = QLineEdit(self)
        self.descripcion.editingFinished.connect(
            lambda: self._cambiar(descripcion=self.descripcion.text()))
        form.addRow("Color de impresión:", self.color)
        form.addRow("Grosor de línea:", self.grosor)
        form.addRow("Tramado (intensidad):", self.tramado)
        form.addRow("", self.grises)
        form.addRow("Descripción:", self.descripcion)
        todas = QPushButton("Elegir todas", self)
        todas.clicked.connect(self.lista.selectAll)
        form.addRow("", todas)
        form.addRow(QLabel("Ctrl o Mayús + clic elige varias plumas a la vez.\n"
                           "Tramado 100 % = color pleno; 50 % = más claro.", self))

        self.desc_tabla = QLineEdit(str(self.tabla.description or ""), self)
        self.desc_tabla.editingFinished.connect(self._desc_tabla)
        arriba = QFormLayout()
        arriba.addRow("Descripción de la tabla:", self.desc_tabla)

        medio = QHBoxLayout()
        medio.addWidget(self.lista, 3)
        medio.addWidget(self.grupo, 1)

        botones = QDialogButtonBox(self)
        guardar = botones.addButton("Guardar", QDialogButtonBox.ActionRole)
        guardar.clicked.connect(self._guardar)
        como = botones.addButton("Guardar como...", QDialogButtonBox.ActionRole)
        como.clicked.connect(self._guardar_como)
        botones.addButton("Cerrar", QDialogButtonBox.RejectRole).clicked.connect(self.reject)
        self.aviso = QLabel(f"Carpeta: {I.carpeta()}", self)

        caja = QVBoxLayout(self)
        caja.addLayout(arriba)
        caja.addLayout(medio, 1)
        caja.addWidget(self.aviso)
        caja.addWidget(botones)
        self.lista.selectRow(0)

    # -- lista
    def _titulo(self) -> None:
        nombre = self.ruta.name if self.ruta else "tabla nueva (basada en acad.ctb)"
        marca = " *" if self.modificada else ""
        self.setWindowTitle(f"Editor de plumas — {nombre}{marca}")

    def _elegidas(self) -> list[int]:
        return sorted({i.row() + 1 for i in self.lista.selectionModel().selectedRows()})

    def _fila(self, aci: int) -> None:
        d = I.pluma(self.tabla, aci)
        fila = aci - 1
        if d["color"] is None:
            color = QTableWidgetItem("Objeto")
        else:
            color = QTableWidgetItem(_muestra(d["color"]), "%d, %d, %d" % d["color"])
        textos = (color,
                  QTableWidgetItem("Objeto" if not d["grosor"] else f"{_mm(d['grosor'])} mm"),
                  QTableWidgetItem(f"{d['tramado']} %"),
                  QTableWidgetItem("Sí" if d["grises"] else ""),
                  QTableWidgetItem(d["descripcion"]))
        for col, item in enumerate(textos, start=1):
            self.lista.setItem(fila, col, item)

    def _cargar(self) -> None:
        acis = self._elegidas()
        self.grupo.setEnabled(bool(acis))
        if not acis:
            return
        self.grupo.setTitle(f"Pluma {I.nombre_color(acis[0])}" if len(acis) == 1
                            else f"{len(acis)} plumas elegidas")
        d = I.pluma(self.tabla, acis[0])
        self.color.setCurrentIndex(0 if d["color"] is None
                                   else 1 if d["color"] == (0, 0, 0) else 2)
        i = self.grosor.findData(d["grosor"])
        self.grosor.setCurrentIndex(i if i >= 0 else 0)
        self.tramado.setValue(d["tramado"])
        self.grises.setChecked(d["grises"])
        self.descripcion.setText(d["descripcion"])

    # -- cambios
    def _cambiar(self, **cambios) -> None:
        acis = self._elegidas()
        if not acis:
            return
        antes = [I.pluma(self.tabla, a) for a in acis]
        I.cambiar(self.tabla, acis, **cambios)
        if antes != [I.pluma(self.tabla, a) for a in acis]:
            self.modificada = True
            self._titulo()
        for aci in acis:
            self._fila(aci)

    def _color(self, indice: int) -> None:
        if indice == 0:
            self._cambiar(color=None)
        elif indice == 1:
            self._cambiar(color=(0, 0, 0))
        else:
            acis = self._elegidas()
            d = I.pluma(self.tabla, acis[0]) if acis else {"color": None}
            inicial = QColor(*(d["color"] or _rgb_aci(acis[0] if acis else 7)))
            elegido = QColorDialog.getColor(inicial, self, "Color de impresión")
            if elegido.isValid():
                self._cambiar(color=(elegido.red(), elegido.green(), elegido.blue()))
            self._cargar()

    def _desc_tabla(self) -> None:
        if self.desc_tabla.text() != str(self.tabla.description or ""):
            self.tabla.description = self.desc_tabla.text()
            self.modificada = True
            self._titulo()

    # -- guardar
    def _escribir(self, ruta) -> bool:
        try:
            respaldo = I.guardar(self.tabla, ruta)
        except Exception as error:  # noqa: BLE001
            QMessageBox.warning(self, "Editor de plumas", f"No se pudo guardar:\n{error}")
            return False
        self.ruta = ruta
        self.guardada = ruta.name
        self.modificada = False
        self._titulo()
        self.aviso.setText(f"Guardada: {ruta}" + (f"  (la anterior quedó en {respaldo.name})"
                                                   if respaldo else ""))
        return True

    def _guardar(self) -> bool:
        if self.ruta is None:
            return self._guardar_como()
        return self._escribir(self.ruta)

    def _guardar_como(self) -> bool:
        sugerido = self.ruta.stem + " copia" if self.ruta else "GeoCAD"
        nombre, ok = QInputDialog.getText(self, "Guardar tabla de plumas como",
                                          "Nombre de la tabla (.ctb):", text=sugerido)
        if not ok:
            return False
        try:
            nombre = I.nombre_archivo(nombre)
        except ValueError as error:
            QMessageBox.warning(self, "Editor de plumas", str(error))
            return False
        ruta = I.carpeta() / nombre
        if ruta.exists() and QMessageBox.question(
                self, "Editor de plumas",
                f"Ya existe {nombre}. ¿Reemplazarla? (queda un respaldo .bak)") \
                != QMessageBox.Yes:
            return False
        return self._escribir(ruta)

    def reject(self) -> None:
        if self.modificada:
            r = QMessageBox.question(
                self, "Editor de plumas", "La tabla tiene cambios sin guardar. ¿Guardarlos?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self._guardar()):
                return
        super().reject()


# ---------------------------------------------------------------- Page Setup
def agregar_a_page_setup(dialogo, window, layout) -> None:
    """Junto a «Plot style table»: Editar plumas... y Vista previa..."""
    combo = getattr(dialogo, "style_sheet", None)
    if combo is None:
        return
    grupo = combo.parentWidget()
    form = grupo.layout() if grupo is not None else None
    fila = QHBoxLayout()
    editar = QPushButton("Editar plumas...", dialogo)
    previa = QPushButton("Vista previa...", dialogo)
    fila.addWidget(editar)
    fila.addWidget(previa)
    if isinstance(form, QFormLayout):
        form.addRow(fila)
    else:
        caja = dialogo.findChild(QDialogButtonBox)
        if caja is None:
            return
        caja.addButton(editar, QDialogButtonBox.ActionRole)
        caja.addButton(previa, QDialogButtonBox.ActionRole)

    def tabla_elegida() -> str:
        dato = combo.currentData()
        return dato if dato is not None else combo.currentText()

    def elegir(nombre: str) -> None:
        if not nombre:
            return
        if combo.findData(nombre) < 0:
            combo.addItem(nombre, nombre)
        combo.setCurrentIndex(combo.findData(nombre))

    def al_editar() -> None:
        editor = EditorPlumas(dialogo, tabla_elegida())
        editor.exec()
        elegir(editor.guardada)

    def al_previa() -> None:
        from core import layouts

        valores = dialogo.values()
        ancho, alto = valores.pop("width"), valores.pop("height")
        comando = layouts.page_setup_command(layout, ancho, alto, valores.pop("margins"),
                                             valores.pop("size_name"), **valores)
        document = window.document
        vista = VistaPrevia(
            dialogo, document, layout.name, tabla_elegida(),
            provisoria=lambda hacer: I.con_pagina_provisoria(document, layout, comando, hacer))
        vista.exec()
        if vista.ctb != tabla_elegida():
            if vista.ctb:
                elegir(vista.ctb)
            else:
                combo.setCurrentIndex(0)

    editar.clicked.connect(al_editar)
    previa.clicked.connect(al_previa)


def _envolver_init(original):
    def __init__(self, window, layout, *args, **kwargs):
        original(self, window, layout, *args, **kwargs)
        if I.activo():
            try:
                agregar_a_page_setup(self, window, layout)
            except Exception:  # noqa: BLE001 - Page Setup sigue como venía
                pass
    __init__._puente_original = original
    __init__._puente_fabrica = _envolver_init
    return __init__


# ---------------------------------------------------------------- órdenes
def vista_previa(window, echo) -> None:
    document = getattr(window, "document", None)
    nombre = getattr(window, "_active_layout", "Model")
    if document is None or nombre == "Model" or nombre not in document.doc.layouts:
        echo("VISTAPREVIA trabaja en una presentación: pase a una pestaña de presentación.")
        return
    layout = document.doc.layouts.get(nombre)
    ctb = str(layout.dxf.get("current_style_sheet", "") or "")
    vista = VistaPrevia(window, document, nombre, ctb, imprimir=True)
    vista.exec()
    if vista.ctb != ctb:
        from core import layouts
        window.history.execute(
            layouts.PageSetupCommand(layout, {"current_style_sheet": vista.ctb}))
        echo(f"Tabla de plumas de «{nombre}»: {vista.ctb or 'ninguna'}.")
    if vista.imprimir_pedido:
        window._invoke_command("PLOT")


def plumas(window, echo) -> None:
    document = getattr(window, "document", None)
    nombre = getattr(window, "_active_layout", "Model")
    ctb = ""
    if document is not None and nombre != "Model" and nombre in document.doc.layouts:
        ctb = str(document.doc.layouts.get(nombre).dxf.get("current_style_sheet", "") or "")
    editor = EditorPlumas(window, ctb or "acad.ctb")
    editor.exec()
    if editor.guardada:
        echo(f"Tabla de plumas guardada: {editor.guardada}.")
