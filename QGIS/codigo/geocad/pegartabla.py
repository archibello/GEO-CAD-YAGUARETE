# SPDX-License-Identifier: GPL-3.0-or-later
"""PEGAR TABLA en las composiciones de QGIS (3.23.0, módulo «Tablas»).

La misma propuesta que PEGARTABLA de IngeCAD (3.22.x), en la ventana de
composición (el equivalente del espacio papel): un botón «Pegar tabla» en la
barra GeoCAD Yaguareté de cada composición y en el menú GeoCAD. Mira el
portapapeles y reconoce de dónde viene lo copiado (GenOffice, QGIS, Calc,
Excel, texto; tablas.detectar). Se ubica con DOS PUNTOS: el primero es la
esquina superior izquierda y el segundo la esquina inferior derecha, que
acompaña al cursor hasta el clic: la tabla llena ese rectángulo (columnas y
filas se estiran; las letras toman la escala menor, sin deformarse). Enter
o el botón derecho en el segundo punto deja el tamaño natural (los mm de la
planilla en mm de hoja). Mientras se eligen los puntos se ven las líneas de
la tabla. Esc cancela.

El resultado es una TABLA MANUAL NATIVA de QGIS (QgsLayoutItemManualTable):
se edita con el editor de tablas de QGIS, se mueve y se exporta con todo lo
demás, sin nada que instalar para quien abra el proyecto. Lleva el formato
de la planilla: anchos de columna, altos de fila, combinadas, fuente,
tamaño, negrita, cursiva, subrayado, color de texto y de fondo, alineación.
Los bordes: QGIS dibuja una sola grilla para toda la tabla; va con el
grosor y el color más usados en la planilla (sin bordes en la planilla, sin
grilla). Se deshace de una vez (Ctrl+Z).

Sin Qt quedan las cuentas (plan, ventana, ancho_qgis): las pruebas las usan
sin abrir QGIS.
"""
from __future__ import annotations

from pathlib import Path

from . import tablas

HOLGURA = 0.05                      # mm de más en el marco (no se ve: la tabla no tiene fondo)
PROPIEDAD = "geocad_tabla"          # en la tabla: de dónde vino (para el vínculo, 3.24.0)
ICONO = Path(__file__).resolve().parent / "iconos" / "pegar_tabla.png"
PRIMERO = "Pegar tabla: clic en la esquina superior izquierda (Esc cancela)."
SEGUNDO = ("Pegar tabla: clic en la esquina inferior derecha (la tabla llena el rectángulo) "
           "o Enter / botón derecho para el tamaño natural.")


# ------------------------------------------------------------------ las cuentas (sin Qt)
def ventana(p1, p2, ancho_mm: float, alto_mm: float) -> tuple:
    """(esquina superior izquierda, k a lo ancho, k a lo alto) de la tabla
    que llena el rectángulo entre ``p1`` y ``p2`` (coordenadas de la
    composición, en mm, con y hacia abajo): la esquina opuesta queda EN
    ``p2``, como en IngeCAD. Un rectángulo sin ancho o sin alto toma la
    escala del otro lado; sin ninguno, el tamaño natural."""
    (x0, y0), (x1, y1) = (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    kx = dx / ancho_mm if ancho_mm > 0 and dx > 1e-9 else None
    ky = dy / alto_mm if alto_mm > 0 and dy > 1e-9 else None
    if kx is None and ky is None:
        return (x0, y0), 1.0, 1.0
    kx = kx if kx is not None else ky
    ky = ky if ky is not None else kx
    origen = (min(x0, x1) if dx > 1e-9 else x0, min(y0, y1) if dy > 1e-9 else y0)
    return origen, kx, ky


def segmentos(armado: tablas.Armado, origen, kx: float, ky: float) -> list:
    """Las líneas de la tabla en la composición (y hacia abajo); sin bordes,
    el contorno."""
    ox, oy = float(origen[0]), float(origen[1])
    segs = [((ox + l.x0 * kx, oy - l.y0 * ky), (ox + l.x1 * kx, oy - l.y1 * ky))
            for l in armado.lineas]
    if not segs:
        x1, y1 = ox + armado.ancho_mm * kx, oy + armado.alto_mm * ky
        segs = [((ox, oy), (x1, oy)), ((x1, oy), (x1, y1)), ((x1, y1), (ox, y1)), ((ox, y1), (ox, oy))]
    return segs


def _grilla(armado: tablas.Armado):
    """(grosor mm, color) más usados en los bordes, por largo; None sin bordes."""
    peso: dict = {}
    for l in armado.lineas:
        largo = abs(l.x1 - l.x0) + abs(l.y1 - l.y0)
        clave = (round(l.grosor_mm, 3), (l.color or "#000000").lower())
        peso[clave] = peso.get(clave, 0.0) + largo
    if not peso:
        return None
    return max(peso.items(), key=lambda kv: kv[1])[0]


def ancho_qgis(total_mm: float, n: int, margen: float, grilla: float) -> float:
    """El ancho (o alto) que se le da a QGIS para una columna (fila) que debe
    ocupar ``total_mm``: QGIS suma dos márgenes por celda y el grosor de la
    grilla entre celdas y en los dos extremos (n + 1 líneas para n celdas)."""
    return max(0.1, total_mm - 2 * margen - grilla * (n + 1) / max(n, 1))


def plan(tabla: tablas.Tabla, armado: tablas.Armado, kx: float = 1.0, ky: float = 1.0,
         respetar_formato: bool = True) -> dict:
    """La tabla manual de QGIS, sin Qt: anchos y altos para QGIS, margen,
    grilla y cada celda con su formato (tamaño en puntos, escalado)."""
    kt = min(kx, ky)
    formato = respetar_formato and tabla.con_formato
    xs, ys = armado.xs, armado.ys
    n_c, n_f = len(xs) - 1, len(ys) - 1
    # un solo margen para toda la tabla (QGIS no tiene uno por celda): el más
    # chico de los textos, que ya entraba en su celda
    combinadas = {(c.fila, c.col) for c in tabla.celdas if c.cols > 1}
    margenes = []
    for tx in armado.textos:
        if tx.col < 0 or (tx.fila, tx.col) in combinadas:
            continue
        x0, x1 = xs[tx.col], xs[min(n_c, tx.col + 1)]
        if tx.alin_h == "izquierda":
            margenes.append(tx.x - x0)
        elif tx.alin_h == "derecha":
            margenes.append(x1 - tx.x)
    margen = (min(margenes) if margenes else 1.0) * kt
    grilla = _grilla(armado)
    g = grilla[0] * kt if grilla else 0.0
    anchos = [ancho_qgis((xs[i + 1] - xs[i]) * kx, n_c, margen, g) for i in range(n_c)]
    altos = [ancho_qgis((ys[i] - ys[i + 1]) * ky, n_f, margen, g) for i in range(n_f)]
    por_celda = {(tx.fila, tx.col): tx for tx in armado.textos}
    fondos = {}
    if formato:
        for c in tabla.celdas:
            if c.fondo:
                fondos[(c.fila, c.col)] = c.fondo
    celdas = []
    for c in tabla.celdas:
        tx = por_celda.get((c.fila, c.col))
        d = {"fila": c.fila, "col": c.col, "filas": c.filas, "cols": c.cols,
             "texto": c.texto, "fondo": fondos.get((c.fila, c.col), "")}
        if tx is not None:
            d.update(pt=tx.alto_mm * kt / (tablas.PT_MM * tablas.MAYUSCULA),
                     fuente=tx.fuente or "Arial", negrita=tx.negrita, cursiva=tx.cursiva,
                     subrayado=tx.subrayado, color=tx.color or "#000000",
                     alin_h=tx.alin_h, alin_v=tx.alin_v)
        celdas.append(d)
    return {"n_filas": n_f, "n_cols": n_c, "anchos": anchos, "altos": altos, "margen": margen,
            "grilla": g, "color_grilla": grilla[1] if grilla else "#000000",
            "celdas": celdas, "ancho_mm": armado.ancho_mm * kx, "alto_mm": armado.alto_mm * ky}


# ------------------------------------------------------------------ QGIS
def leer_portapapeles() -> tuple:
    """(html, texto, url) de lo que hay en el portapapeles del sistema."""
    try:
        from qgis.PyQt.QtWidgets import QApplication
    except Exception:  # noqa: BLE001
        return "", "", ""
    board = QApplication.clipboard()
    data = board.mimeData() if board is not None else None
    if data is None:
        return "", "", ""
    html = data.html() if data.hasHtml() else ""
    texto = data.text() if data.hasText() else ""
    url = ""
    if data.hasFormat("chromium/x-source-url"):
        try:
            url = bytes(data.data("chromium/x-source-url")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            url = ""
    return html, texto, url


def tabla_del_portapapeles():
    return tablas.leer(*leer_portapapeles())


def medidor():
    """medir(texto, alto, negrita, cursiva, fuente) -> mm para tablas.armar,
    con la fuente con que QGIS la va a dibujar (la que Qt encuentra para esa
    familia). El alto es el de las mayúsculas, como en el núcleo."""
    from qgis.PyQt.QtGui import QFont, QFontMetricsF

    cache = {}

    def medir(texto: str, alto: float, negrita: bool = False, cursiva: bool = False,
              fuente: str = ""):
        clave = (fuente or "Arial", negrita, cursiva)
        fm = cache.get(clave)
        if fm is None:
            f = QFont(clave[0])
            f.setPixelSize(1000)
            f.setBold(negrita)
            f.setItalic(cursiva)
            fm = cache[clave] = QFontMetricsF(f)
        return fm.horizontalAdvance(texto) / 1000.0 * alto / tablas.MAYUSCULA

    return medir


def _alineacion(alin_h: str, alin_v: str):
    from qgis.PyQt.QtCore import Qt
    A = Qt.AlignmentFlag
    h = {"centro": A.AlignHCenter, "derecha": A.AlignRight}.get(alin_h, A.AlignLeft)
    v = {"arriba": A.AlignTop, "abajo": A.AlignBottom}.get(alin_v, A.AlignVCenter)
    return h, v


def _formato_texto(d: dict):
    from qgis.core import Qgis, QgsTextFormat
    from qgis.PyQt.QtGui import QColor, QFont

    f = QFont(d.get("fuente") or "Arial")
    f.setBold(bool(d.get("negrita")))
    f.setItalic(bool(d.get("cursiva")))
    f.setUnderline(bool(d.get("subrayado")))
    fmt = QgsTextFormat()
    fmt.setFont(f)
    fmt.setSize(max(0.5, float(d.get("pt", 10.0))))
    try:
        fmt.setSizeUnit(Qgis.RenderUnit.Points)
    except AttributeError:                      # QGIS 3.28
        from qgis.core import QgsUnitTypes
        fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor(d.get("color") or "#000000"))
    return fmt


def crear_tabla(layout, p: dict, origen, nombre: str = "", origen_tabla: str = ""):
    """La tabla manual en la composición, con la esquina superior izquierda
    en ``origen`` (mm de la composición). Un solo paso de deshacer.
    Devuelve (tabla, marco)."""
    from qgis.core import QgsLayoutFrame, QgsLayoutItemManualTable, QgsTableCell
    from qgis.PyQt.QtCore import QRectF
    from qgis.PyQt.QtGui import QColor

    filas = [[QgsTableCell("") for _c in range(p["n_cols"])] for _f in range(p["n_filas"])]
    for d in p["celdas"]:
        celda = QgsTableCell(d["texto"])
        if "pt" in d:
            celda.setTextFormat(_formato_texto(d))
            h, v = _alineacion(d["alin_h"], d["alin_v"])
            celda.setHorizontalAlignment(h)
            celda.setVerticalAlignment(v)
        if d.get("fondo"):
            celda.setBackgroundColor(QColor(d["fondo"]))
        if (d["filas"] > 1 or d["cols"] > 1) and hasattr(celda, "setSpan"):
            celda.setSpan(d["filas"], d["cols"])      # QGIS 3.40 o más nuevo
        filas[d["fila"]][d["col"]] = celda
    pila = layout.undoStack()
    pila.beginMacro("Pegar tabla")
    try:
        t = QgsLayoutItemManualTable.create(layout)
        t.setIncludeTableHeader(False)
        t.setTableContents(filas)
        t.setCellMargin(p["margen"])
        t.setShowGrid(p["grilla"] > 0)
        if p["grilla"] > 0:
            t.setGridStrokeWidth(p["grilla"])
            t.setGridColor(QColor(p["color_grilla"]))
        t.setColumnWidths(p["anchos"])
        t.setRowHeights(p["altos"])
        try:
            t.setBackgroundColor(QColor(0, 0, 0, 0))
        except Exception:  # noqa: BLE001
            pass
        if origen_tabla:
            t.setCustomProperty(PROPIEDAD, origen_tabla)
        layout.addMultiFrame(t)
        marco = QgsLayoutFrame(layout, t)
        # una holgura mínima: con el alto justo, QGIS deja la última fila
        # afuera por redondeo (la manda a un marco siguiente que no hay)
        marco.attemptSetSceneRect(QRectF(float(origen[0]), float(origen[1]),
                                         p["ancho_mm"] + HOLGURA, p["alto_mm"] + HOLGURA))
        if nombre:
            marco.setId(nombre)
        t.addFrame(marco)
        t.recalculateFrameSizes()
    finally:
        pila.endMacro()
    return t, marco


def pedir_opciones(parent, tabla):
    """La ventana de Pegar tabla en la composición. None = cancelado."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                                     QDoubleSpinBox, QFormLayout, QLabel, QListWidget,
                                     QListWidgetItem, QVBoxLayout)

    dlg = QDialog(parent)
    dlg.setWindowTitle("Pegar tabla - GeoCAD Yaguareté")
    caja = QVBoxLayout(dlg)
    nombre = tablas.ORIGENES.get(tabla.origen, tabla.origen)
    encabezados = [h or f"Columna {i + 1}" for i, h in enumerate(tabla.encabezados())]
    col_geo = tabla.columna("wkt_geom")
    detalle = f"{tabla.n_filas} fila(s) × {tabla.n_cols} columna(s)"
    if tabla.con_formato:
        detalle += ", con formato"
    caja.addWidget(QLabel(f"<b>Copiado de {nombre}</b>: {detalle}.<br>"
                          "Va como tabla de la composición (se edita con el editor de tablas de QGIS)."))
    caja.addWidget(QLabel("Columnas (las marcadas van a la tabla):"))
    lista = QListWidget()
    lista.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    for i, h in enumerate(encabezados):
        it = QListWidgetItem(h)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Unchecked if i == col_geo else Qt.CheckState.Checked)
        lista.addItem(it)
    lista.setMaximumHeight(150)
    caja.addWidget(lista)
    form = QFormLayout()
    respetar = QCheckBox("Respetar el formato de la planilla (anchos, letras, colores, bordes)")
    respetar.setChecked(tabla.con_formato)
    respetar.setEnabled(tabla.con_formato)
    encabezado = QCheckBox("Primera fila como encabezado (en negrita)")
    encabezado.setChecked(True)
    alto = QDoubleSpinBox()
    alto.setRange(0.5, 50.0)
    alto.setDecimals(2)
    alto.setValue(2.5)
    alto.setSuffix(" mm")
    form.addRow(respetar)
    form.addRow(encabezado)
    form.addRow("Altura de texto (sin el formato):", alto)
    caja.addLayout(form)

    def actualizar():
        alto.setEnabled(not respetar.isChecked())
        encabezado.setEnabled(not respetar.isChecked())

    respetar.toggled.connect(actualizar)
    actualizar()
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    caja.addWidget(botones)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    marcadas = [i for i in range(lista.count())
                if lista.item(i).checkState() == Qt.CheckState.Checked]
    return {"quitar": [i for i in range(tabla.n_cols) if i not in marcadas],
            "respetar": respetar.isChecked(), "encabezado": encabezado.isChecked(),
            "alto": alto.value()}


def preparar(tabla, opciones: dict, medir=None) -> tuple:
    """(tabla sin las columnas quitadas, armado) según las opciones."""
    quitar = opciones.get("quitar", ())
    t = tablas.sin_columnas(tabla, quitar) if quitar else tabla
    a = tablas.armar(t, opciones.get("respetar", True), opciones.get("alto", 2.5),
                     opciones.get("encabezado", True), medir=medir)
    return t, a


_SELECCION = {}                     # id(vista) -> herramienta Seleccionar propia (sin diseñador)


def volver_a_seleccionar(view, ventana=None) -> None:
    """Deja la composición con la herramienta Seleccionar/Mover elemento: la
    del diseñador (su botón) o, sin diseñador, una propia."""
    try:
        from qgis.PyQt.QtGui import QAction           # QGIS 4 (Qt 6)
    except ImportError:
        from qgis.PyQt.QtWidgets import QAction       # QGIS 3
    if ventana is not None:
        try:
            accion = ventana.findChild(QAction, "mActionSelectMoveItem")
        except RuntimeError:
            accion = None
        if accion is not None:
            accion.trigger()
            return
    from qgis.gui import QgsLayoutViewToolSelect
    sel = _SELECCION.get(id(view))
    if sel is None:
        sel = _SELECCION[id(view)] = QgsLayoutViewToolSelect(view)
    try:
        sel.setLayout(view.currentLayout())     # sin esto se cae al primer clic
    except AttributeError:
        pass
    view.setTool(sel)


def herramienta(view, tabla, armado, opciones: dict, avisar=None, al_terminar=None,
                ventana_diseñador=None):
    """La herramienta de dos puntos sobre la vista de la composición
    (QgsLayoutViewTool). ``avisar(texto)`` muestra los pedidos."""
    from qgis.gui import QgsLayoutViewTool
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor, QPainterPath, QPen
    from qgis.PyQt.QtWidgets import QGraphicsPathItem

    class PegarTablaTool(QgsLayoutViewTool):
        def __init__(self):
            super().__init__(view, "Pegar tabla")
            bandera = getattr(getattr(QgsLayoutViewTool, "Flag", QgsLayoutViewTool), "FlagSnaps", None)
            if bandera is not None:
                self.setFlags(bandera)      # el punto sigue a la referencia (snapping) de la composición
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.p1 = None
            self.vista = None
            self.resultado = None
            self.terminado = False
            self._respetar = opciones.get("respetar", True)

        # -- vista previa: las líneas de la tabla
        def _previa(self, cursor):
            if self.p1 is None:
                origen, kx, ky = (cursor[0], cursor[1]), 1.0, 1.0
            else:
                origen, kx, ky = ventana(self.p1, cursor, armado.ancho_mm, armado.alto_mm)
            camino = QPainterPath()
            for (x0, y0), (x1, y1) in segmentos(armado, origen, kx, ky):
                camino.moveTo(x0, y0)
                camino.lineTo(x1, y1)
            escena = self.layout()
            if self.vista is None and escena is not None:
                self.vista = QGraphicsPathItem()
                pluma = QPen(QColor(0, 120, 215))
                pluma.setCosmetic(True)
                pluma.setWidth(1)
                pluma.setStyle(Qt.PenStyle.DashLine)
                self.vista.setPen(pluma)
                self.vista.setZValue(1e9)
                escena.addItem(self.vista)
            if self.vista is not None:
                self.vista.setPath(camino)

        def _borrar_previa(self):
            if self.vista is not None:
                try:
                    escena = self.vista.scene()
                    if escena is not None:
                        escena.removeItem(self.vista)
                except RuntimeError:
                    pass
                self.vista = None

        def _punto(self, ev):
            try:
                p = ev.snappedPoint()
            except AttributeError:
                p = ev.layoutPoint()
            return (p.x(), p.y())

        def layoutMoveEvent(self, ev):
            if not self.terminado:
                self._previa(self._punto(ev))

        def layoutPressEvent(self, ev):
            if self.terminado:              # ya pegó: un clic más no vuelve a pegar
                return
            if ev.button() == Qt.MouseButton.RightButton:
                if self.p1 is not None:
                    self.pegar(self.p1, 1.0, 1.0)
                else:
                    self.cancelar()
                return
            if ev.button() != Qt.MouseButton.LeftButton:
                return
            p = self._punto(ev)
            if self.p1 is None:
                self.p1 = p
                if avisar:
                    avisar(SEGUNDO)
                return
            self.pegar(*ventana(self.p1, p, armado.ancho_mm, armado.alto_mm))

        def keyPressEvent(self, ev):
            if self.terminado:
                ev.ignore()
                return
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.p1 is not None:
                self.pegar(self.p1, 1.0, 1.0)
            elif ev.key() == Qt.Key.Key_Escape:
                self.cancelar()
            else:
                ev.ignore()

        def pegar(self, origen, kx, ky):
            self._borrar_previa()
            nombre = "Tabla de " + tablas.ORIGENES.get(tabla.origen, tabla.origen)
            p = plan(tabla, armado, kx, ky, self._respetar)
            self.resultado = crear_tabla(self.layout(), p, origen, nombre, tabla.origen)
            self._salir(f"{nombre} pegada: {p['ancho_mm']:.1f} × {p['alto_mm']:.1f} mm. "
                        "Ctrl+Z la quita.")

        def cancelar(self):
            self._borrar_previa()
            self._salir("Pegar tabla: cancelado.")

        def _salir(self, texto):
            self.terminado = True
            if avisar:
                avisar(texto)
            # unsetTool de QGIS sólo desactiva: la herramienta seguía puesta y
            # cada clic pegaba otra tabla (3.23.1). Se vuelve a Seleccionar.
            volver_a_seleccionar(self.view(), ventana_diseñador)
            if al_terminar:
                al_terminar(self)

        def deactivate(self):
            self._borrar_previa()
            super().deactivate()

    return PegarTablaTool()


class TablasComposicion:
    """El botón «Pegar tabla» en cada ventana de composición (una barra
    GeoCAD Yaguareté) y la orden para el menú GeoCAD. Apagado el módulo,
    unload() lo saca todo."""

    TITULO_BARRA = "GeoCAD Yaguareté"

    def __init__(self, iface):
        self.iface = iface
        self.barras = {}            # id(diseñador) -> (diseñador, barra)
        self.tool = None
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

    def icono(self):
        from qgis.PyQt.QtGui import QIcon
        return QIcon(str(ICONO))

    def _abierto(self, designer):
        from qgis.PyQt.QtWidgets import QToolBar
        try:
            from qgis.PyQt.QtGui import QAction        # QGIS 4 (Qt 6)
        except ImportError:
            from qgis.PyQt.QtWidgets import QAction    # QGIS 3
        if id(designer) in self.barras:
            return
        try:
            win = designer.window()
        except Exception:  # noqa: BLE001
            return
        barra = QToolBar(self.TITULO_BARRA, win)
        barra.setObjectName("GeoCADYaguareteComposicion")
        accion = QAction(self.icono(), "Pegar tabla (GenOffice, Calc, Excel o QGIS) — dos puntos", barra)
        accion.triggered.connect(lambda _=False, d=designer: self.pegar(d))
        barra.addAction(accion)
        win.addToolBar(barra)
        self.barras[id(designer)] = (designer, barra)

    def _cerrado(self, designer):
        par = self.barras.pop(id(designer), None)
        if par is not None:
            self._quitar_barra(par)

    def _quitar_barra(self, par):
        designer, barra = par
        try:
            designer.window().removeToolBar(barra)
            barra.deleteLater()
        except RuntimeError:
            pass

    def diseñador_activo(self):
        try:
            abiertos = list(self.iface.openLayoutDesigners())
        except Exception:  # noqa: BLE001
            abiertos = []
        for d in abiertos:
            try:
                if d.window().isActiveWindow():
                    return d
            except RuntimeError:
                pass
        return abiertos[-1] if abiertos else None

    def pegar_menu(self):
        d = self.diseñador_activo()
        if d is None:
            self._aviso_principal("Abra una composición (Proyecto > Administrador de composiciones) y "
                                  "use «Pegar tabla» en su barra GeoCAD Yaguareté.")
            return
        try:
            d.window().raise_()
            d.window().activateWindow()
        except RuntimeError:
            pass
        self.pegar(d)

    def _aviso_principal(self, texto, nivel="warn"):
        from qgis.core import Qgis
        lv = {"warn": Qgis.MessageLevel.Warning, "ok": Qgis.MessageLevel.Success}.get(nivel, Qgis.MessageLevel.Info)
        self.iface.messageBar().pushMessage("GeoCAD Yaguareté", texto, lv, 8)

    def _aviso(self, designer, texto, nivel="info"):
        from qgis.core import Qgis
        lv = {"warn": Qgis.MessageLevel.Warning, "ok": Qgis.MessageLevel.Success}.get(nivel, Qgis.MessageLevel.Info)
        try:
            barra = designer.messageBar()
            barra.clearWidgets()
            barra.pushMessage("Pegar tabla", texto, lv, 0 if nivel == "info" else 6)
        except Exception:  # noqa: BLE001
            self._aviso_principal(texto, nivel)

    def pegar(self, designer):
        tabla = tabla_del_portapapeles()
        if tabla is None:
            self._aviso(designer, "El portapapeles no tiene una tabla. Copie celdas en GenOffice, Calc "
                                  "o Excel, o filas de la tabla de atributos de QGIS (Ctrl+C).", "warn")
            return
        opciones = pedir_opciones(designer.window(), tabla)
        if not opciones:
            return
        try:
            medir = medidor()
        except Exception:  # noqa: BLE001
            medir = None
        t, armado = preparar(tabla, opciones, medir)
        if not armado.xs or len(armado.xs) < 2:
            self._aviso(designer, "La tabla quedó sin columnas.", "warn")
            return
        view = designer.view()

        def terminar(tool):
            self.tool = None

        self.tool = herramienta(view, t, armado, opciones, ventana_diseñador=designer.window(),
                                avisar=lambda texto: self._aviso(
                                    designer, texto, "ok" if "pegada" in texto else "info"),
                                al_terminar=terminar)
        view.setTool(self.tool)
        self._aviso(designer, PRIMERO)

    def unload(self):
        try:
            self.iface.layoutDesignerOpened.disconnect(self._abierto)
        except (TypeError, RuntimeError):
            pass
        try:
            self.iface.layoutDesignerWillBeClosed.disconnect(self._cerrado)
        except (TypeError, RuntimeError, AttributeError):
            pass
        if self.tool is not None:
            try:
                self.tool.cancelar()
            except Exception:  # noqa: BLE001
                pass
            self.tool = None
        for par in list(self.barras.values()):
            self._quitar_barra(par)
        self.barras.clear()
