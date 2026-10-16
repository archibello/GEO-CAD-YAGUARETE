# SPDX-License-Identifier: GPL-3.0-or-later
"""Ventanas del módulo «Intercambio» (3.25.0): SISTEMAGEO, REPROYECTAR,
IMPORTARSHP y EXPORTARSHP. Las cuentas están en intercambio.py.

Antes de cambiar el sistema de un dibujo con objetos, y antes de escribir
archivos, siempre se pregunta y se confirma (decisiones de Fernando 10 y
11, 15/10/2026)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import intercambio as IX

TITULO = "GeoCAD Yaguareté"


# ------------------------------------------------------------------ piezas comunes
class ElegirSistema(QComboBox):
    """La lista corta argentina, editable: también se escribe cualquier
    código EPSG («5347», «EPSG:27700»)."""

    def __init__(self, actual: str = "", vacio: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(360)
        if vacio:
            self.addItem(vacio, "")
        for code, nombre_s in IX.lista_corta():
            self.addItem(f"{nombre_s} ({code})", code)
        if actual:
            self.poner(actual)

    def poner(self, code: str) -> None:
        i = self.findData(code)
        if i < 0:
            self.addItem(IX.nombre(code), code)
            i = self.count() - 1
        self.setCurrentIndex(i)

    def codigo(self) -> str:
        texto = self.currentText().strip()
        i = self.currentIndex()
        if i >= 0 and self.itemText(i) == texto:
            return self.itemData(i) or ""
        if not texto:
            return ""
        return IX.normalizar(texto.rsplit("(", 1)[-1].rstrip(")")) or IX.normalizar(texto)


def _botones(dlg, texto_ok: str = "Aceptar") -> QDialogButtonBox:
    caja = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    caja.button(QDialogButtonBox.Ok).setText(texto_ok)
    caja.button(QDialogButtonBox.Cancel).setText("Cancelar")
    caja.accepted.connect(dlg.accept)
    caja.rejected.connect(dlg.reject)
    return caja


def _host_path(ruta: str) -> str:
    try:
        from views import file_dialogs
        return file_dialogs.host_path(str(ruta))
    except Exception:  # noqa: BLE001 -- sin la vista de IngeCAD
        return str(ruta)


def _inicio() -> str:
    try:
        from views import file_dialogs
        return file_dialogs.start_dir()
    except Exception:  # noqa: BLE001
        return str(Path.home())


def _recordar(ruta) -> None:
    try:
        from views import file_dialogs
        file_dialogs.remember(ruta)
    except Exception:  # noqa: BLE001
        pass


def _seleccion(ctx) -> list:
    """Los objetos seleccionados en el dibujo (del modelo)."""
    tools = getattr(ctx.host, "tools", None)
    handles = list(getattr(tools, "selection", None) or ())
    db = ctx.document.doc.entitydb
    out = []
    for h in handles:
        e = db.get(h)
        if e is not None and e.is_alive and e.dxf.owner == ctx.document.doc.modelspace().layout_key:
            out.append(e)
    return out


def _refrescar(ctx) -> None:
    for nombre_f in ("regen_in_memory",):
        f = getattr(ctx.host, nombre_f, None)
        if callable(f):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass


def _zoom(ctx, entidades) -> None:
    """Zoom a lo importado."""
    try:
        from ezdxf import bbox
        caja = bbox.extents(entidades, fast=True)
        if not caja.has_data:
            return
        pad = max(caja.size.x, caja.size.y, 1.0) * 0.05
        vp = ctx.host.viewport
        vp.view.zoom_extents(caja.extmin.x - pad, caja.extmin.y - pad,
                             caja.extmax.x + pad, caja.extmax.y + pad)
        vp.update()
    except Exception:  # noqa: BLE001 -- sin zoom, igual quedó importado
        pass


def _confirmar(parent, texto: str, ok: str = "Sí, seguir") -> bool:
    caja = QMessageBox(QMessageBox.Question, TITULO, texto, parent=parent)
    si = caja.addButton(ok, QMessageBox.AcceptRole)
    caja.addButton("Cancelar", QMessageBox.RejectRole)
    caja.exec()
    return caja.clickedButton() is si


# ================================================================== SISTEMAGEO
class SistemaDialog(QDialog):
    def __init__(self, actual: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sistema de coordenadas del dibujo (SISTEMAGEO)")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Sistema actual: <b>{IX.nombre(actual)}</b>"))
        lay.addWidget(QLabel("Declara en qué sistema están las coordenadas. <b>No mueve "
                             "ningún objeto</b>: para convertirlas use REPROYECTAR."))
        form = QFormLayout()
        self.combo = ElegirSistema(actual)
        form.addRow("Sistema:", self.combo)
        fila = QHBoxLayout()
        prj = QPushButton("Tomar el de un .prj o .shp...")
        prj.clicked.connect(self._de_prj)
        fila.addWidget(prj)
        fila.addStretch(1)
        form.addRow("", fila)
        lay.addLayout(form)
        self.aviso = QLabel("")
        self.aviso.setStyleSheet("color: #b00020")
        lay.addWidget(self.aviso)
        lay.addWidget(_botones(self, "Definir"))

    def _de_prj(self) -> None:
        ruta, _f = QFileDialog.getOpenFileName(self, "Tomar el sistema de...", _inicio(),
                                               "Proyección (*.prj *.shp)")
        if not ruta:
            return
        code = IX.sistema_de_prj(_host_path(ruta))
        if code:
            self.combo.poner(code)
            self.aviso.setText("")
        else:
            self.aviso.setText(f"No se reconoce el sistema de {Path(ruta).name}.")

    def accept(self) -> None:
        motivo = IX.validar(self.combo.codigo())
        if motivo:
            self.aviso.setText(motivo)
            return
        super().accept()


def sistema(ctx) -> None:
    doc = ctx.document.doc
    actual = IX.sistema_del_dibujo(doc)
    dlg = SistemaDialog(actual, ctx.host)
    if not dlg.exec():
        return
    code = dlg.combo.codigo()
    if code == actual:
        ctx.echo(f"SISTEMAGEO: el dibujo ya está en {IX.nombre(code)}.")
        return
    n = IX.cantidad_de_objetos(doc)
    if actual and n:
        caja = QMessageBox(QMessageBox.Warning, TITULO,
                           f"El dibujo tiene {n} objeto(s) en {IX.nombre(actual)}.\n\n"
                           f"«Sólo declarar» deja las coordenadas como están y dice que son de "
                           f"{IX.nombre(code)}. Úselo si el sistema estaba mal declarado.\n\n"
                           f"«Reproyectar» convierte las coordenadas a {IX.nombre(code)}.",
                           parent=ctx.host)
        declarar = caja.addButton("Sólo declarar", QMessageBox.AcceptRole)
        convertir = caja.addButton("Reproyectar...", QMessageBox.ActionRole)
        caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.exec()
        if caja.clickedButton() is convertir:
            reproyectar(ctx, code)
            return
        if caja.clickedButton() is not declarar:
            return
    ctx.execute(IX.DefinirSistemaCommand(code))
    ctx.echo(f"SISTEMAGEO: el dibujo está en {IX.nombre(code)} (antes: {IX.nombre(actual)}). "
             "No se movió ningún objeto. U lo deshace.")


# ================================================================== REPROYECTAR
class ReproyectarDialog(QDialog):
    def __init__(self, actual: str, destino: str, n_sel: int, parent=None) -> None:
        super().__init__(parent)
        self.actual = actual
        self.setWindowTitle("Reproyectar dibujo (REPROYECTAR)")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"De: <b>{IX.nombre(actual)}</b>"))
        form = QFormLayout()
        self.combo = ElegirSistema(destino)
        self.combo.currentIndexChanged.connect(self._describir)
        self.combo.editTextChanged.connect(self._describir)
        form.addRow("A:", self.combo)
        lay.addLayout(form)
        self.todo = QRadioButton("Todo el dibujo (también las ventanas del papel)")
        self.sel = QRadioButton(f"Sólo lo seleccionado ({n_sel} objeto(s))")
        self.todo.setChecked(True)
        self.sel.setEnabled(n_sel > 0)
        grupo = QGroupBox("Qué")
        g = QVBoxLayout(grupo)
        g.addWidget(self.todo)
        g.addWidget(self.sel)
        lay.addWidget(grupo)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)
        lay.addWidget(QLabel("Los objetos de capas conectadas (CONECTARSHP) no se tocan."))
        lay.addWidget(_botones(self, "Reproyectar"))
        self._describir()

    def _describir(self, *_a) -> None:
        code = self.combo.codigo()
        motivo = IX.validar(code)
        if motivo:
            self.desc.setText(motivo)
            return
        if code == self.actual:
            self.desc.setText("Es el sistema actual del dibujo.")
            return
        try:
            self.desc.setText("Conversión: " + IX.Proyeccion(self.actual, code).descripcion())
        except Exception as exc:  # noqa: BLE001
            self.desc.setText(f"PROJ no puede convertir: {exc}")

    def accept(self) -> None:
        code = self.combo.codigo()
        if IX.validar(code) or code == self.actual:
            self._describir()
            return
        super().accept()


def reproyectar(ctx, destino: str = "") -> None:
    doc = ctx.document.doc
    actual = IX.sistema_del_dibujo(doc)
    if not actual:
        if _confirmar(ctx.host, "El dibujo no tiene sistema de coordenadas: para reproyectar "
                                "hay que saber en cuál está. ¿Definirlo ahora (SISTEMAGEO)?",
                      "Definir sistema..."):
            sistema(ctx)
        return
    elegidos = _seleccion(ctx)
    dlg = ReproyectarDialog(actual, destino, len(elegidos), ctx.host)
    if not dlg.exec():
        return
    code = dlg.combo.codigo()
    solo_sel = dlg.sel.isChecked()
    cmd, conectados = IX.preparar_reproyeccion(doc, code, elegidos if solo_sel else None)
    n = len(cmd.entidades)
    texto = (f"Se van a convertir {n} objeto(s) de {IX.nombre(actual)} a {IX.nombre(code)} "
             f"con {cmd.proy.descripcion()}, y el dibujo queda declarado en {IX.nombre(code)}.")
    if solo_sel:
        texto += ("\n\nAtención: sólo lo seleccionado. El resto queda en el sistema anterior "
                  "y el dibujo tendría objetos en dos sistemas distintos.")
    if conectados:
        texto += f"\n\n{conectados} objeto(s) de capas conectadas no se tocan."
    if not _confirmar(ctx.host, texto + "\n\nUn solo U lo deshace.", "Reproyectar"):
        return
    ctx.execute(cmd)
    _refrescar(ctx)
    ctx.echo("REPROYECTAR: " + IX.resumen_reproyeccion(cmd, conectados))


# ================================================================== IMPORTARSHP
def _grosores() -> list:
    try:
        from core.layers import LINEWEIGHTS
        return list(LINEWEIGHTS)
    except Exception:  # noqa: BLE001
        return [-3, 0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70,
                80, 90, 100, 106, 120, 140, 158, 200, 211]


def _texto_grosor(lw: int) -> str:
    return "Por defecto" if lw == -3 else f"{lw / 100:.2f} mm"



class ImportarDialog(QDialog):
    def __init__(self, vistas, doc, parent=None) -> None:
        super().__init__(parent)
        self.vistas = vistas
        self.setWindowTitle("Importar SHP (IMPORTARSHP)")
        self.setMinimumWidth(720)
        lay = QVBoxLayout(self)
        destino = IX.sistema_del_dibujo(doc)
        lay.addWidget(QLabel(f"Sistema del dibujo: <b>{IX.nombre(destino)}</b>. Lo que entra "
                             "se lleva a ese sistema."))
        tabla = QTableWidget(len(vistas), 5)
        tabla.setHorizontalHeaderLabels(("Archivo", "Tipo", "Registros", "Sistema", "Codificación"))
        self.sistemas = {}
        for i, v in enumerate(vistas):
            for j, texto in enumerate((v.ruta.name, v.tipo, str(v.cantidad))):
                tabla.setItem(i, j, QTableWidgetItem(texto))
            if v.sistema:
                tabla.setItem(i, 3, QTableWidgetItem(IX.nombre(v.sistema)))
            else:                    # sin .prj: que lo diga quien lo conoce
                c = ElegirSistema("", "sin .prj: como viene")
                tabla.setCellWidget(i, 3, c)
                self.sistemas[str(v.ruta)] = c
            tabla.setItem(i, 4, QTableWidgetItem(v.codificacion))
        tabla.resizeColumnsToContents()
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(tabla)
        self.adoptar = QCheckBox("El dibujo no tiene sistema: adoptar el del primer SHP que lo traiga")
        self.adoptar.setChecked(True)
        self.adoptar.setVisible(not destino)
        lay.addWidget(self.adoptar)
        lugar_base = lay.count()            # la base de datos va arriba, junto a los archivos
        campos = sorted({c for v in vistas for c in v.campos})
        # capa
        g = QGroupBox("Capa y presentación")
        f = QFormLayout(g)
        self.capa_archivo = QRadioButton("Una por archivo (el nombre del archivo)")
        self.capa_fija = QRadioButton("Una sola:")
        self.capa_campo = QRadioButton("Según el valor de un campo:")
        self.capa_archivo.setChecked(True)
        self.nombre_capa = QLineEdit(IX.nombre_de_capa(vistas[0].ruta.stem) if vistas else "SHP")
        self.campo_capa = QComboBox()
        self.campo_capa.addItems(campos)
        f.addRow(self.capa_archivo)
        f.addRow(self.capa_fija, self.nombre_capa)
        f.addRow(self.capa_campo, self.campo_capa)
        self.color = 7
        self.boton_color = QPushButton()
        self.boton_color.clicked.connect(self._elegir_color)
        self._mostrar_color()
        self.grosor = QComboBox()
        for lw in _grosores():
            self.grosor.addItem(_texto_grosor(lw), lw)
        fila = QHBoxLayout()
        fila.addWidget(self.boton_color)
        fila.addSpacing(16)
        fila.addWidget(QLabel("Espesor de línea:"))
        fila.addWidget(self.grosor, 1)
        f.addRow("Color:", fila)
        lay.addWidget(g)
        # puntos
        g = QGroupBox("Puntos")
        f = QFormLayout(g)
        self.pt_punto = QRadioButton("Como punto")
        self.pt_bloque = QRadioButton("Como bloque:")
        self.pt_texto = QRadioButton("Como texto del campo:")
        self.pt_punto.setChecked(True)
        self.bloque = QComboBox()
        self.bloque.addItems(sorted(b.name for b in doc.blocks
                                    if not b.name.startswith("*") and not b.is_any_layout))
        self.pt_bloque.setEnabled(self.bloque.count() > 0)
        self.campo_texto = QComboBox()
        self.campo_texto.addItems(campos)
        f.addRow(self.pt_punto)
        f.addRow(self.pt_bloque, self.bloque)
        f.addRow(self.pt_texto, self.campo_texto)
        self.altura = QDoubleSpinBox()
        self.altura.setRange(0.01, 10000)
        self.altura.setDecimals(2)
        self.altura.setValue(2.5)
        f.addRow("Altura del texto:", self.altura)
        lay.addWidget(g)
        # base de datos (lo principal, con el vectorial; los rótulos se hacen después)
        g = QGroupBox("Base de datos")
        v = QVBoxLayout(g)
        self.con_base = QRadioButton("Con base de datos: cada objeto lleva su registro, con el "
                                     "esquema del .dbf")
        self.sin_base = QRadioButton("Sólo la geometría (sin atributos)")
        self.con_base.setChecked(True)
        v.addWidget(self.con_base)
        nota = QLabel("Una tabla por archivo en la Tabla de atributos (TABLASIG).\n"
                      "Los rótulos, después, desde la tabla con ROTULOSIG.")
        nota.setContentsMargins(24, 0, 0, 4)
        v.addWidget(nota)
        v.addWidget(self.sin_base)
        lay.insertWidget(lugar_base, g)
        lay.addWidget(_botones(self, "Importar"))

    def _elegir_color(self) -> None:
        try:
            from views.color_dialog import SelectColorDialog
        except Exception:  # noqa: BLE001 -- un IngeCAD sin el selector
            return
        dlg = SelectColorDialog(self, self.color, include_bylayer=False)
        if dlg.exec():
            self.color = dlg.result_aci()
            self._mostrar_color()

    def _mostrar_color(self) -> None:
        try:
            from views.color_dialog import aci_label, swatch_icon
            self.boton_color.setIcon(swatch_icon(self.color, 16))
            self.boton_color.setText(" " + aci_label(self.color))
        except Exception:  # noqa: BLE001
            self.boton_color.setText(f"Color {self.color}")

    def opciones(self) -> IX.OpcionesImportar:
        op = IX.OpcionesImportar()
        op.capa = "fija" if self.capa_fija.isChecked() else "campo" if self.capa_campo.isChecked() else "archivo"
        op.capa_fija = self.nombre_capa.text().strip() or "SHP"
        op.campo_capa = self.campo_capa.currentText()
        op.puntos = "bloque" if self.pt_bloque.isChecked() else "texto" if self.pt_texto.isChecked() else "punto"
        op.bloque = self.bloque.currentText()
        op.campo_texto = self.campo_texto.currentText()
        op.atributos = self.con_base.isChecked()
        op.altura = self.altura.value()
        op.color = self.color
        op.grosor = self.grosor.currentData()
        op.sistema_shp = {ruta: c.codigo() for ruta, c in self.sistemas.items()}
        op.adoptar = self.adoptar.isChecked()
        return op


def importar(ctx) -> None:
    rutas, _f = QFileDialog.getOpenFileNames(ctx.host, "Importar SHP", _inicio(), "Shapefile (*.shp)")
    if not rutas:
        return
    rutas = [_host_path(r) for r in rutas]
    _recordar(rutas[0])
    vistas, malos = [], []
    for r in rutas:
        try:
            vistas.append(IX.ver_shp(r))
        except Exception as exc:  # noqa: BLE001 -- archivo dañado o incompleto
            malos.append(f"{Path(r).name}: {exc}")
    if malos:
        ctx.echo("IMPORTARSHP: no se pueden leer " + "; ".join(malos) + ".")
    if not vistas:
        return
    doc = ctx.document.doc
    dlg = ImportarDialog(vistas, doc, ctx.host)
    if not dlg.exec():
        return
    antes = {e.dxf.handle for e in doc.modelspace()}
    try:
        plan = IX.plan_importar(doc, [v.ruta for v in vistas], dlg.opciones())
    except Exception as exc:  # noqa: BLE001
        ctx.echo(f"IMPORTARSHP: no se pudo importar ({exc}). No se cambió nada.")
        return
    ctx.execute(plan.comando)
    _refrescar(ctx)
    _zoom(ctx, [e for e in doc.modelspace() if e.dxf.handle not in antes])
    ctx.echo("IMPORTARSHP: " + IX.resumen_importar(plan))
    if plan.tablas:
        try:
            from . import puente
            puente.table_refresh()
        except Exception:  # noqa: BLE001 -- sin el módulo de datos
            pass


# ================================================================== EXPORTARSHP
class ExportarDialog(QDialog):
    def __init__(self, doc, n_sel: int, carpeta: str, nombre_base: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar SHP (EXPORTARSHP)")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        # qué
        g = QGroupBox("Qué")
        v = QVBoxLayout(g)
        self.sel = QRadioButton(f"Lo seleccionado ({n_sel} objeto(s))")
        self.todo = QRadioButton("Todo el dibujo")
        self.capas = QRadioButton("Las capas elegidas:")
        (self.sel if n_sel else self.todo).setChecked(True)
        self.sel.setEnabled(n_sel > 0)
        self.lista = QListWidget()
        for capa in sorted(l.dxf.name for l in doc.layers):
            item = QListWidgetItem(capa)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lista.addItem(item)
        self.lista.setMaximumHeight(120)
        for w in (self.sel, self.todo, self.capas, self.lista):
            v.addWidget(w)
        lay.addWidget(g)
        # cómo (decisión 11: las dos valen; se elige y se confirma)
        g = QGroupBox("Archivos (un shapefile admite un solo tipo de geometría)")
        f = QFormLayout(g)
        self.por_capa = QRadioButton("Uno por capa y tipo (CAPA_puntos, CAPA_lineas, CAPA_poligonos)")
        self.por_tipo = QRadioButton("Uno por tipo con todas las capas y el campo LAYER:")
        self.por_capa.setChecked(True)
        self.base = QLineEdit(nombre_base)
        f.addRow(self.por_capa)
        f.addRow(self.por_tipo, self.base)
        self.poligonos = QCheckBox("Polilíneas cerradas y círculos como polígonos")
        self.poligonos.setChecked(True)
        f.addRow(self.poligonos)
        lay.addWidget(g)
        # sistema
        form = QFormLayout()
        actual = IX.sistema_del_dibujo(doc)
        self.sistema = ElegirSistema(actual)
        form.addRow(f"Sistema (el del dibujo: {IX.nombre(actual)}):", self.sistema)
        fila = QHBoxLayout()
        self.carpeta = QLineEdit(carpeta)
        elegir = QPushButton("Elegir...")
        elegir.clicked.connect(self._elegir)
        fila.addWidget(self.carpeta, 1)
        fila.addWidget(elegir)
        form.addRow("Carpeta:", fila)
        lay.addLayout(form)
        self.aviso = QLabel("")
        self.aviso.setStyleSheet("color: #b00020")
        lay.addWidget(self.aviso)
        lay.addWidget(_botones(self, "Exportar..."))

    def _elegir(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta para los SHP", self.carpeta.text())
        if ruta:
            self.carpeta.setText(_host_path(ruta))

    def capas_elegidas(self) -> set:
        return {self.lista.item(i).text() for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.Checked}

    def accept(self) -> None:
        motivo = IX.validar(self.sistema.codigo())
        if motivo:
            self.aviso.setText("Sistema: " + motivo)
            return
        if not self.carpeta.text().strip():
            self.aviso.setText("Elija la carpeta.")
            return
        if self.capas.isChecked() and not self.capas_elegidas():
            self.aviso.setText("Tilde al menos una capa.")
            return
        super().accept()


def exportar(ctx) -> None:
    doc = ctx.document.doc
    elegidos = _seleccion(ctx)
    archivo = getattr(ctx.document, "path", None)
    base = Path(str(archivo)).stem if archivo else "dibujo"
    carpeta = str(Path(str(archivo)).parent / f"{base}_shp") if archivo else str(Path(_inicio()) / "shp")
    dlg = ExportarDialog(doc, len(elegidos), carpeta, base, ctx.host)
    if not dlg.exec():
        return
    if dlg.sel.isChecked():
        entidades = elegidos
    elif dlg.capas.isChecked():
        capas = dlg.capas_elegidas()
        entidades = [e for e in doc.modelspace() if e.dxf.get("layer", "0") in capas]
    else:
        entidades = list(doc.modelspace())
    try:
        plan = IX.plan_exportar(entidades, doc, "tipo" if dlg.por_tipo.isChecked() else "capa",
                                IX.nombre_de_archivo(dlg.base.text() or base),
                                dlg.sistema.codigo(), dlg.poligonos.isChecked())
    except Exception as exc:  # noqa: BLE001
        ctx.echo(f"EXPORTARSHP: {exc}")
        return
    if not plan.grupos:
        ctx.echo("EXPORTARSHP: no hay nada que se pueda exportar en lo elegido.")
        return
    carpeta = Path(dlg.carpeta.text().strip())
    lista = "\n".join(f"  {g.archivo}.shp  ({len(g.elementos)} registro(s))" for g in plan.grupos)
    texto = f"Se van a escribir en {carpeta}, en {IX.nombre(plan.destino)}:\n\n{lista}"
    if plan.origen != plan.destino:
        texto += f"\n\nReproyectado desde {IX.nombre(plan.origen)}."
    if plan.salteados:
        texto += "\n\nNo se exportan: " + ", ".join(f"{k} {v}" for k, v in sorted(plan.salteados.items()))
    pisar = plan.existentes(carpeta)
    if pisar:
        texto += (f"\n\nATENCIÓN: ya existen {len(pisar)} archivo(s) con esos nombres "
                  f"({', '.join(p.name for p in pisar[:6])}{'...' if len(pisar) > 6 else ''}) "
                  "y se van a REEMPLAZAR.")
    if not _confirmar(ctx.host, texto, "Reemplazar y exportar" if pisar else "Exportar"):
        return
    try:
        hechos = IX.escribir(plan, carpeta)
    except Exception as exc:  # noqa: BLE001
        ctx.echo(f"EXPORTARSHP: no se pudo escribir en {carpeta} ({exc}).")
        return
    ctx.echo("EXPORTARSHP: " + IX.resumen_exportar(plan, hechos))
