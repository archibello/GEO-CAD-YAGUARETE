# -*- coding: utf-8 -*-
"""Espacio de cada herramienta (Fernando, 08/11/2026).

En Administrar Herramientas se elige una categoría y «Espacio de cada herramienta...»
lista sus botones; cada uno tiene su lugar definitivo:

    Espacio Presentaciones  su botón en una barra de la presentación, con el nombre de
                            su categoría, y una casilla en Ver > Herramientas GeoCAD
                            que lo muestra u oculta. Sale de la ventana principal.
    Espacio Modelo          su botón en la ventana principal; en la presentación no está.

Las cinco NATIVAS están hechas para la presentación y traen allí su propia barra: de
fábrica van en Presentaciones. Las demás, en Modelo. Las que dibujan sobre el mapa de
QGIS siguen trabajando en él: su botón, desde la presentación, lleva a la ventana
principal y la lanza. Las listas desplegables de las barras sólo pueden estar en Modelo.

Lo elegido se guarda en ~/.config/geocad/espacios.json. Las cuentas no usan QGIS: las
prueba test_espacios.py; las ventanas de verdad, ventana/banco_espacios_qgis_real.py.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import botones

PRESENTACION = "presentacion"
MODELO = "modelo"
NOMBRES = ((PRESENTACION, "Espacio Presentaciones"), (MODELO, "Espacio Modelo"))

#: (botón, etiqueta, ícono): con barra propia en la presentación
NATIVAS = (
    ("geocad:imgbase_mover", "Desplazar imagen base", "imagen_base_mover.png"),
    ("geocad:imgbase_bloquear", "Bloquear imagen base", "imagen_base_bloquear.png"),
    ("geocad:imgbase_guardar", "Guardar imagen base recortada", "imagen_base_guardar.png"),
    ("geocad:pegartabla", "Pegar tabla", "pegar_tabla.png"),
    ("geocad:copiartabla", "Copiar tabla", "copiar_tabla.png"),
)
IDS_NATIVAS = tuple(b for b, _t, _i in NATIVAS)
ICONOS = Path(__file__).parent / "iconos"
BARRAS_PRESENTACION = ("GeoCADYaguareteComposicion", "GeoCADYaguareteImagenBase")
PREFIJO_BARRA = "GeoCADYaguareteEspacio_"
OBJETO_BARRA_MODELO = "GeoCADYaguareteEspacioModelo"
TITULO_BARRA_MODELO = "GeoCAD Herramientas de presentación"
TITULO_SIN_CATEGORIA = "GeoCAD Herramientas"
TITULO_MENU = "Herramientas GeoCAD"
OBJETO_MENU_BARRAS = "mToolbarMenu"
SIN_BARRA = "geocad_sin_botones"               # propiedad Qt: la barra la escondió esto


def _exec(dialog):
    run = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return run()


# ------------------------------------------------------------ lo elegido, sin QGIS
def archivo() -> Path:
    return Path.home() / ".config" / "geocad" / "espacios.json"


def _boton(clave):
    """El id completo; la 3.72.0 guardaba «pegartabla» por «geocad:pegartabla»."""
    if not isinstance(clave, str) or not clave:
        return None
    if ":" in clave:
        return clave
    return "geocad:" + clave if "geocad:" + clave in IDS_NATIVAS else None


def leer() -> dict:
    """{"espacios": {botón: espacio}, "ocultas": set}; un archivo dañado no molesta."""
    validos = {e for e, _n in NOMBRES}
    try:
        crudo = json.loads(archivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        crudo = {}
    if not isinstance(crudo, dict):
        crudo = {}
    guardados = crudo.get("espacios")
    ocultas = crudo.get("ocultas")
    return {"espacios": {_boton(c): e for c, e in guardados.items() if _boton(c) and e in validos}
            if isinstance(guardados, dict) else {},
            "ocultas": {_boton(c) for c in ocultas if _boton(c)} if isinstance(ocultas, list) else set()}


def guardar(estado: dict) -> None:
    ruta = archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".espacios-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"espacios": estado["espacios"], "ocultas": sorted(estado["ocultas"])},
                  fh, ensure_ascii=False, indent=2)
    botones._reemplazar(tmp, ruta)


def espacio(estado: dict, boton: str) -> str:
    return estado["espacios"].get(boton, PRESENTACION if boton in IDS_NATIVAS else MODELO)


def visible_en_presentacion(estado: dict, boton: str) -> bool:
    return espacio(estado, boton) == PRESENTACION and boton not in estado["ocultas"]


def de_espacio(estado: dict, cual: str, disponibles) -> list:
    """Las disponibles de ese espacio: primero las nativas, en su orden."""
    disponibles = list(disponibles)
    orden = [b for b in IDS_NATIVAS if b in disponibles] + [b for b in disponibles if b not in IDS_NATIVAS]
    return [b for b in orden if espacio(estado, b) == cual]


def fuera_de_modelo(estado: dict) -> set:
    """Las elegidas para Presentaciones: no van en las barras de la ventana principal.
    Sin elección explícita una nativa puesta en una categoría sigue donde está."""
    return {b for b, e in estado["espacios"].items() if e == PRESENTACION}


def sin_presentacion(distribucion, fabrica, fuera):
    """La distribución de las barras principales sin las de ``fuera``; ``distribucion``
    None son las barras de fábrica: con algo que sacar, hay que armarlas igual."""
    if not fuera:
        return distribucion
    base = distribucion if distribucion is not None else [
        (n, list(f)) for n, f in fabrica if not botones.es_banco(n)]
    return [(n, [b for b in f if b not in fuera]) for n, f in base]


def por_categoria(ids, categorias) -> list:
    """[(categoría, [botones])], en el orden de las categorías; lo que no está en
    ninguna va al final, en TITULO_SIN_CATEGORIA."""
    quedan, salida = list(ids), []
    for nombre, fila in categorias:
        propios = [b for b in fila if b in quedan]
        if propios:
            salida.append((nombre, propios))
            quedan = [b for b in quedan if b not in propios]
    if quedan:
        salida.append((TITULO_SIN_CATEGORIA, quedan))
    return salida


# ------------------------------------------------------------ el formulario
def formulario(QtWidgets, parent, titulo: str, filas, estado: dict):
    """{botón: espacio} con lo elegido, o None si se canceló. ``filas``:
    [(botón, texto, QIcon o None, sólo_modelo)]. Aceptar va arriba."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Espacio de cada herramienta: " + titulo)
    lay = QtWidgets.QVBoxLayout(dlg)
    intro = QtWidgets.QLabel(f"Elija el lugar definitivo de cada herramienta de «{titulo}».", dlg)
    intro.setWordWrap(True)
    lay.addWidget(intro)
    caja = QtWidgets.QDialogButtonBox(dlg)
    std = getattr(QtWidgets.QDialogButtonBox, "StandardButton", QtWidgets.QDialogButtonBox)
    caja.setStandardButtons(std.Ok | std.Cancel)
    caja.accepted.connect(dlg.accept)
    caja.rejected.connect(dlg.reject)
    lay.addWidget(caja)

    fila_toda = QtWidgets.QHBoxLayout()
    fila_toda.addWidget(QtWidgets.QLabel("Toda la categoría:", dlg), 1)
    toda = QtWidgets.QComboBox(dlg)
    toda.setObjectName("toda")
    toda.addItem("(cada una por separado)", "")
    for valor, nombre in NOMBRES:
        toda.addItem(nombre, valor)
    fila_toda.addWidget(toda)
    lay.addLayout(fila_toda)

    from qgis.PyQt.QtCore import Qt
    area = QtWidgets.QScrollArea(dlg)
    area.setWidgetResizable(True)
    # sin barra horizontal: los nombres largos se parten y el selector queda a la vista
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    dentro = QtWidgets.QWidget(area)
    grilla = QtWidgets.QGridLayout(dentro)
    combos = {}
    for fila, (boton, texto, icono, solo_modelo) in enumerate(filas):
        dibujo = QtWidgets.QLabel(dentro)
        if icono is not None:
            dibujo.setPixmap(icono.pixmap(24, 24))
        combo = QtWidgets.QComboBox(dentro)
        combo.setObjectName(boton)
        for valor, nombre in NOMBRES:
            combo.addItem(nombre, valor)
        combo.setCurrentIndex(combo.findData(MODELO if solo_modelo else espacio(estado, boton)))
        if solo_modelo:
            combo.setEnabled(False)
            combo.setToolTip("Es una lista desplegable de las barras: sólo puede estar en Modelo.")
        grilla.addWidget(dibujo, fila, 0)
        etiqueta_fila = QtWidgets.QLabel(texto, dentro)
        etiqueta_fila.setWordWrap(True)
        grilla.addWidget(etiqueta_fila, fila, 1)
        grilla.addWidget(combo, fila, 2)
        combos[boton] = combo
    grilla.setColumnStretch(1, 1)
    grilla.setRowStretch(len(filas), 1)
    area.setWidget(dentro)
    lay.addWidget(area, 1)

    def toda_la_categoria(_i):
        valor = toda.currentData()
        if valor:
            for combo in combos.values():
                if combo.isEnabled():
                    combo.setCurrentIndex(combo.findData(valor))

    toda.currentIndexChanged.connect(toda_la_categoria)
    dlg.resize(640, min(640, 190 + 40 * len(filas)))
    if not _exec(dlg):
        return None
    return {b: c.currentData() for b, c in combos.items() if c.isEnabled()}


# ------------------------------------------------------------ las ventanas de QGIS
class EspaciosQgis:
    """Aplica lo elegido. ``acciones()``: {botón: QAction} de todo GeoCAD;
    ``categorias()``: [(categoría, [botones])] de las barras; ``reaplicar()``
    vuelve a armar las barras de la ventana principal."""

    def __init__(self, iface, acciones, categorias, reaplicar):
        self.iface = iface
        self.acciones = acciones
        self.categorias = categorias
        self.reaplicar = reaplicar
        self.menus = {}             # id(diseñador) -> (diseñador, menú Ver, submenú)
        self.barra_modelo = None
        iface.layoutDesignerOpened.connect(self._abierto)
        try:
            iface.layoutDesignerWillBeClosed.connect(self._cerrado)
        except AttributeError:
            pass
        try:
            for d in iface.openLayoutDesigners():
                self._abierto(d)
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------- cada presentación
    @staticmethod
    def _barras_propias(win) -> list:
        from qgis.PyQt.QtWidgets import QToolBar
        return [b for b in win.findChildren(QToolBar) if b.objectName().startswith(PREFIJO_BARRA)]

    def _barras(self, win) -> list:
        from qgis.PyQt.QtWidgets import QToolBar
        halladas = (win.findChild(QToolBar, objeto) for objeto in BARRAS_PRESENTACION)
        return [b for b in halladas if b is not None] + self._barras_propias(win)

    def _botones(self, win) -> dict:
        salida = {}
        for barra in self._barras(win):
            for accion in barra.actions():
                boton = accion.property("geocad_id")
                if boton:
                    salida[str(boton)] = accion
        return salida

    @staticmethod
    def _menu_barras(win):
        """(menú Ver, acción que sigue a Barras de herramientas)."""
        for arriba in win.menuBar().actions():
            menu = arriba.menu()
            if menu is None:
                continue
            lista = menu.actions()
            for i, accion in enumerate(lista):
                sub = accion.menu()
                if sub is not None and sub.objectName() == OBJETO_MENU_BARRAS:
                    return menu, lista[i + 1] if i + 1 < len(lista) else None
        return None, None

    def _abierto(self, designer) -> None:
        from qgis.PyQt.QtCore import QTimer
        from qgis.PyQt.QtWidgets import QMenu
        if id(designer) in self.menus:
            return
        try:
            win = designer.window()
        except Exception:  # noqa: BLE001
            return
        ver, siguiente = self._menu_barras(win)
        if ver is None:
            return
        sub = QMenu(TITULO_MENU, win)
        sub.setObjectName("GeoCADHerramientasMenu")
        if siguiente is not None:
            ver.insertMenu(siguiente, sub)
        else:
            ver.addMenu(sub)
        sub.aboutToShow.connect(lambda d=designer: self._pintar(d))
        self.menus[id(designer)] = (designer, ver, sub)
        QTimer.singleShot(0, self.aplicar)      # las barras se crean al abrirse la ventana

    def _cerrado(self, designer) -> None:
        self.menus.pop(id(designer), None)

    def _quitar_propias(self, win) -> None:
        for barra in self._barras_propias(win):
            win.removeToolBar(barra)
            barra.setObjectName("")
            barra.deleteLater()

    def _lanzar(self, original) -> None:
        """Las de dibujo trabajan sobre el mapa: se va a la ventana principal."""
        ventana = self.iface.mainWindow()
        ventana.raise_()
        ventana.activateWindow()
        original.trigger()

    def _armar_propias(self, designer, estado, acciones) -> None:
        """Una barra por categoría con las elegidas que no traen barra propia."""
        try:
            from qgis.PyQt.QtGui import QAction                # QGIS 4 (Qt 6)
        except ImportError:
            from qgis.PyQt.QtWidgets import QAction            # QGIS 3
        from qgis.PyQt.QtWidgets import QToolBar, QWidgetAction
        win = designer.window()
        self._quitar_propias(win)
        ids = [b for b in de_espacio(estado, PRESENTACION, acciones)
               if b not in IDS_NATIVAS and not isinstance(acciones[b], QWidgetAction)]
        for nombre, fila in por_categoria(ids, self.categorias()):
            barra = QToolBar(nombre, win)
            barra.setObjectName(PREFIJO_BARRA + nombre)
            for boton in fila:
                original = acciones[boton]
                copia = QAction(original.icon(), original.text(), barra)
                copia.setProperty("geocad_id", boton)
                copia.triggered.connect(lambda _=False, o=original: self._lanzar(o))
                barra.addAction(copia)
            win.addToolBar(barra)

    def _pintar(self, designer) -> None:
        """El submenú: una casilla por herramienta del espacio Presentaciones."""
        try:
            from qgis.PyQt.QtGui import QAction                # QGIS 4 (Qt 6)
        except ImportError:
            from qgis.PyQt.QtWidgets import QAction            # QGIS 3
        datos = self.menus.get(id(designer))
        if datos is None:
            return
        sub = datos[2]
        estado = leer()
        presentes = self._botones(designer.window())
        sub.clear()
        ids = de_espacio(estado, PRESENTACION, presentes)
        for boton in ids:
            original = presentes[boton]
            accion = QAction(original.icon(), original.text().split(" — ")[0].replace("&", ""), sub)
            accion.setCheckable(True)
            accion.setChecked(boton not in estado["ocultas"])
            accion.toggled.connect(lambda si, b=boton: self.mostrar(b, si))
            sub.addAction(accion)
        if not ids:
            vacia = sub.addAction("(ninguna: se eligen en Administrar Herramientas)")
            vacia.setEnabled(False)

    def _aplicar_a(self, designer) -> None:
        win = designer.window()
        estado = leer()
        for boton, accion in self._botones(win).items():
            accion.setVisible(visible_en_presentacion(estado, boton))
        for barra in self._barras(win):
            con_botones = any(a.isVisible() for a in barra.actions())
            if not con_botones and barra.isVisible():
                barra.setProperty(SIN_BARRA, True)
                barra.setVisible(False)
            elif con_botones and barra.property(SIN_BARRA):
                barra.setProperty(SIN_BARRA, False)
                barra.setVisible(True)

    # -------------------------------------------------------- la ventana principal
    def _aplicar_modelo(self, estado, acciones) -> None:
        """Una nativa en Modelo que no esté en ninguna categoría necesita una barra."""
        en_categorias = {b for _n, fila in self.categorias() for b in fila}
        lista = [acciones[b] for b in de_espacio(estado, MODELO, [b for b in IDS_NATIVAS if b in acciones])
                 if b not in en_categorias]
        if self.barra_modelo is None:
            if not lista:
                return
            self.barra_modelo = self.iface.addToolBar(TITULO_BARRA_MODELO)
            self.barra_modelo.setObjectName(OBJETO_BARRA_MODELO)
        self.barra_modelo.clear()
        self.barra_modelo.addActions(lista)
        self.barra_modelo.setVisible(bool(lista))

    # -------------------------------------------------------- órdenes
    def aplicar(self) -> None:
        estado = leer()
        acciones = self.acciones()
        for designer, _ver, _sub in list(self.menus.values()):
            try:
                self._armar_propias(designer, estado, acciones)
                self._aplicar_a(designer)
                self._pintar(designer)
            except RuntimeError:
                pass
        self._aplicar_modelo(estado, acciones)

    def mostrar(self, boton: str, visible: bool) -> None:
        """La casilla de Ver > Herramientas GeoCAD."""
        estado = leer()
        (estado["ocultas"].discard if visible else estado["ocultas"].add)(boton)
        guardar(estado)
        for designer, _ver, _sub in list(self.menus.values()):
            try:
                self._aplicar_a(designer)
            except RuntimeError:
                pass

    def elegir(self, titulo: str, ids, etiquetas=None, iconos=None) -> None:
        """El formulario para los botones de una categoría de Administrar Herramientas."""
        from qgis.PyQt import QtWidgets
        etiquetas, iconos = etiquetas or {}, iconos or {}
        acciones = self.acciones()
        filas = [(b, etiquetas.get(b, b), iconos.get(b),
                  isinstance(acciones[b], QtWidgets.QWidgetAction)) for b in ids if b in acciones]
        if not filas:
            QtWidgets.QMessageBox.information(
                self.iface.mainWindow(), "GeoCAD Yaguareté", f"«{titulo}» no tiene herramientas.")
            return
        padre = QtWidgets.QApplication.activeModalWidget() or self.iface.mainWindow()
        estado = leer()
        elegido = formulario(QtWidgets, padre, titulo, filas, estado)
        if elegido is None:
            return
        estado["espacios"].update(elegido)
        guardar(estado)
        self.reaplicar()
        self.aplicar()

    def unload(self) -> None:
        for nombre, funcion in (("layoutDesignerOpened", self._abierto),
                                ("layoutDesignerWillBeClosed", self._cerrado)):
            try:
                getattr(self.iface, nombre).disconnect(funcion)
            except (TypeError, RuntimeError, AttributeError):
                pass
        for designer, ver, sub in self.menus.values():
            try:
                ver.removeAction(sub.menuAction())
                sub.deleteLater()
                win = designer.window()
                self._quitar_propias(win)
                for accion in self._botones(win).values():
                    accion.setVisible(True)
                for barra in self._barras(win):
                    if barra.property(SIN_BARRA):
                        barra.setProperty(SIN_BARRA, False)
                        barra.setVisible(True)
            except RuntimeError:
                pass
        self.menus.clear()
        if self.barra_modelo is not None:
            try:
                self.iface.mainWindow().removeToolBar(self.barra_modelo)
                self.barra_modelo.deleteLater()
            except RuntimeError:
                pass
            self.barra_modelo = None
