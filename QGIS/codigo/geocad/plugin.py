# SPDX-License-Identifier: GPL-3.0-or-later
"""GeoCAD en QGIS: menú «GeoCAD», con módulos que se eligen la primera vez
que se abre y se cambian en GeoCAD > Módulos... (ver modulos.py).

Módulo Puente (la otra punta del puente con IngeCAD):

* Enviar a IngeCAD lo que se está viendo (capas visibles) o la capa activa.
  Si IngeCAD está cerrado, intenta abrirlo; el pedido queda esperando.
* Mientras IngeCAD tiene tomada una capa (archivo .ingecad.lock), QGIS la
  pone en solo lectura; al soltarla, la vuelve a habilitar.
* Cuando IngeCAD guarda, QGIS recarga esa capa.
* Configuración común: la misma página que en IngeCAD, el mismo archivo.

Los mensajes viajan por archivos (ver buzon.py): sin red y sin puertos.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from qgis.core import (Qgis, QgsCoordinateTransform, QgsProject, QgsProviderRegistry,
                       QgsApplication, QgsVectorLayer)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import QMenu, QMessageBox

try:                                    # Qt6 (QGIS 4)
    from qgis.PyQt.QtGui import QAction
except ImportError:                     # Qt5 (QGIS 3)
    from qgis.PyQt.QtWidgets import QAction

from . import actualizar, bloqueo, buzon, config, modulos, nombre, submodulos

MENU_TITLE = nombre.NOMBRE_CORTO
PROGRAMA = "qgis"
VIEJOS = ("ingecad_puente",)          # Puente IngeCAD-QGIS 1.x
VERSION = "3.11.2"
INGECAD_FLATPAK = "org.ingecad.IngeCAD"
_MSG = {"info": Qgis.MessageLevel.Info, "ok": Qgis.MessageLevel.Success,
        "warn": Qgis.MessageLevel.Warning, "error": Qgis.MessageLevel.Critical}
_YES = QMessageBox.StandardButton.Yes
_NO = QMessageBox.StandardButton.No
_CANCEL = QMessageBox.StandardButton.Cancel


# -- qué archivo hay detrás de una capa ------------------------------------------------

def layer_source(layer):
    """("gpkg", ruta, tabla) / ("shp", ruta, "") o None si no es un archivo
    que el puente sepa editar."""
    if not isinstance(layer, QgsVectorLayer) or layer.providerType() != "ogr":
        return None
    parts = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
    path = parts.get("path") or ""
    if not path:
        return None
    ext = Path(path).suffix.lower()
    if ext == ".shp":
        return ("shp", str(Path(path).resolve()), "")
    if ext == ".gpkg":
        table = parts.get("layerName") or ""
        if not table:
            try:
                conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
                row = conn.execute("SELECT table_name FROM gpkg_contents "
                                   "WHERE data_type = 'features' LIMIT 1").fetchone()
                conn.close()
                table = row[0] if row else ""
            except sqlite3.Error:
                table = ""
        return ("gpkg", str(Path(path).resolve()), table) if table else None
    return None


def lock_target(fmt: str, path: str, table: str) -> str:
    return f"{path}.{table}" if fmt == "gpkg" else path


def locked(fmt: str, path: str, table: str):
    """El contenido del bloqueo de IngeCAD para esa capa, o None.
    (El nombre de la tabla se compara sin distinguir mayúsculas.)"""
    target = lock_target(fmt, path, table)
    found = bloqueo.read(target)
    if found is not None or fmt != "gpkg":
        return found
    folder = Path(path).parent
    want = (Path(path).name + "." + table + ".ingecad.lock").lower()
    try:
        for p in folder.iterdir():
            if p.name.lower() == want:
                return bloqueo.read(str(p)[:-len(".ingecad.lock")])
    except OSError:
        pass
    return None


def _same(ref: dict, src) -> bool:
    fmt, path, table = src
    return (ref.get("ruta") == path
            and (ref.get("tabla") or "").lower() == (table or "").lower())


# -- el complemento ---------------------------------------------------------------------

class GeoCAD:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.timer = None
        self.ticks = 0
        self.readonly_by_us: set[str] = set()
        self.warned_editing: set[str] = set()
        self._launch = None
        self.menu = None
        self.toolbar = None
        self.actions = {}
        self.subs = None
        self._cargando = False
        self._submenus = []

    # ciclo de vida
    def initGui(self) -> None:
        mw = self.iface.mainWindow()
        config.migrar()
        aqui = Path(__file__).resolve().parent
        self.subs = submodulos.Cargador(self.iface, __package__, aqui.parent,
                                        al_cambiar=self._subs_cambiaron)
        self.menu = QMenu(MENU_TITLE, mw)
        self.menu.setObjectName("GeoCADMenu")
        self._build_menu()
        menubar = mw.menuBar()
        try:
            menubar.insertMenu(self.iface.helpMenu().menuAction(), self.menu)
        except Exception:
            menubar.addMenu(self.menu)
        self._sync_toolbar()
        self._export_icon()
        if self._puente():
            try:
                buzon.heartbeat("qgis", {"version": VERSION})
            except OSError:
                pass
        self.timer = QTimer(mw)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        QTimer.singleShot(0, self._primer_inicio)

    def _puente(self) -> bool:
        return modulos.activo(PROGRAMA, "puente")

    def _build_menu(self) -> None:
        """El menú según los módulos activos (se rearma al cambiarlos)."""
        self.menu.clear()
        self.actions = {}
        add = self._add_action
        if self._puente():
            self.menu.addSection("Puente con IngeCAD")
            add("send", "Enviar a IngeCAD (modo de la configuración común)", self.send_default,
                self._ingecad_icon())
            self.menu.addSeparator()
            add("send_sel", "Enviar a IngeCAD los objetos seleccionados", self.send_selected)
            add("send_screen", "Enviar a IngeCAD lo que está en pantalla", self.send_screen)
            add("send_full", "Enviar a IngeCAD las capas visibles completas", self.send_visible)
            add("send_active", "Enviar a IngeCAD la capa activa completa", self.send_active)
            self.menu.addSeparator()
            add("reload", "Recargar las capas que editó IngeCAD", self.reload_all)
            add("status", "Estado del puente...", self.show_status)
        self._submenus = []
        if self.subs is not None:
            for titulo, acciones in self.subs.menus():
                if not acciones:
                    continue
                self.menu.addSeparator()
                sub = self.menu.addMenu(titulo)
                for a in acciones:
                    sub.addAction(a)
                self._submenus.append(sub)
        self.menu.addSeparator()
        add("modules", "Módulos...", self.choose_modules)
        add("config", "Configuración común...", self.open_config)
        add("update", "Actualizar GeoCAD Yaguareté (QGIS e IngeCAD)...", self.update_bridge)
        add("about", f"Acerca de {nombre.NOMBRE} (versión {VERSION})...", self.about)

    # primera vez: retirar el Puente 1.x y elegir los módulos
    def _retirar_viejos(self) -> list:
        aqui = Path(__file__).resolve().parent
        retirados = []
        for viejo in VIEJOS:
            carpeta = aqui.parent / viejo
            if not carpeta.is_dir():
                continue
            try:
                import qgis.utils
                qgis.utils.unloadPlugin(viejo)
            except Exception:
                pass
            guardado = aqui.parent / f".anterior-{viejo}"
            try:
                shutil.rmtree(guardado, ignore_errors=True)
                carpeta.rename(guardado)
                retirados.append(viejo)
            except OSError:
                pass
        return retirados

    def _subs_cambiaron(self) -> None:
        if not self._cargando and self.menu is not None:
            self._build_menu()

    def _cargar_subs(self) -> None:
        if self.subs is None:
            return
        self._cargando = True
        try:
            self.subs.cargar(modulos.estado(PROGRAMA))
        finally:
            self._cargando = False
        self._build_menu()
        for aviso in self.subs.tomar_avisos():
            self._bar(aviso, "ok" if aviso.startswith("Se retiró") else "warn", 10)

    def _primer_inicio(self) -> None:
        retirados = self._retirar_viejos()
        if retirados:
            self._bar("Se retiró el Puente IngeCAD-QGIS 1.x (queda una copia como "
                      ".anterior-ingecad_puente). Ahora todo está en el menú «GeoCAD Yaguareté».", "ok", 10)
        if not modulos.elegido(PROGRAMA):
            self.choose_modules(primera_vez=True)
        elif modulos.nuevos(PROGRAMA):
            # una versión nueva trajo módulos: se ofrecen (Cancelar = sus valores
            # por defecto, y no se vuelve a preguntar)
            self.choose_modules()
            if modulos.nuevos(PROGRAMA):
                modulos.aceptar_nuevos(PROGRAMA)
            self._cargar_subs()
        else:
            self._cargar_subs()

    def choose_modules(self, primera_vez=False) -> None:
        from qgis.PyQt import QtWidgets
        from . import modulos_ui

        nuevo = modulos_ui.elegir(QtWidgets, self.iface.mainWindow(), PROGRAMA,
                                  primera_vez is True)
        if nuevo is None:
            return
        self.aplicar_modulos()
        self._bar("Módulos de GeoCAD Yaguareté activos: " + modulos.resumen(PROGRAMA) + ".", "ok")

    def aplicar_modulos(self) -> None:
        if self.subs is not None:
            # Dibujo (con Bloques y Papel) y Capas se vuelven a arrancar con la
            # elección nueva; lo apagado se descarga sin dejar rastro
            self.subs.descargar()
            self._cargar_subs()
        self._build_menu()
        self._sync_toolbar()
        if not self._puente():
            self._liberar_capas()
            buzon.clear_heartbeat("qgis")

    def _liberar_capas(self) -> None:
        for layer_id in list(self.readonly_by_us):
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is not None:
                layer.setReadOnly(False)
        self.readonly_by_us.clear()

    def unload(self) -> None:
        if self.subs is not None:
            self.subs.descargar()
            self.subs = None
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        self._liberar_capas()
        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.menu is not None:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None
        buzon.clear_heartbeat("qgis")

    def _add_action(self, key, text, slot, icon=None):
        action = QAction(icon, text, self.iface.mainWindow()) if icon else \
            QAction(text, self.iface.mainWindow())
        action.triggered.connect(slot)
        self.menu.addAction(action)
        self.actions[key] = action
        return action

    def _sync_toolbar(self) -> None:
        """Botones sólo si la configuración común lo pide: el menú está siempre."""
        want = bool(config.get("mostrar_botones")) and self._puente() and "send" in self.actions
        if want and self.toolbar is None:
            self.toolbar = self.iface.addToolBar("GeoCAD Yaguareté")
            self.toolbar.setObjectName("GeoCADToolbar")
            self.toolbar.addAction(self.actions["send"])
        elif not want and self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None

    # íconos
    def _ingecad_icon(self) -> QIcon:
        path = buzon.icon_path("ingecad")
        if path.exists():
            return QIcon(str(path))
        pix = QPixmap(64, 64)               # genérico hasta que IngeCAD publique el suyo
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#2b5797"))
        p.setPen(QColor("#2b5797"))
        p.drawRoundedRect(4, 4, 56, 56, 10, 10)
        p.setPen(QColor("white"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(20)
        p.setFont(font)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "CAD")
        p.end()
        return QIcon(pix)

    def _export_icon(self) -> None:
        """El ícono de QGIS, para el menú "QGIS" de IngeCAD."""
        try:
            icon = QIcon(QgsApplication.appIconPath())
            if icon.isNull():
                return
            path = buzon.icon_path("qgis")
            path.parent.mkdir(parents=True, exist_ok=True)
            icon.pixmap(64, 64).save(str(path), "PNG")
        except Exception:
            pass

    def _bar(self, text: str, level: str = "info", seconds: int = 6) -> None:
        self.iface.messageBar().pushMessage("IngeCAD", text, level=_MSG[level], duration=seconds)

    # temporizador
    def _tick(self) -> None:
        self.ticks += 1
        try:
            if not self._puente():
                # sin el módulo Puente sólo se atiende el aviso de actualización
                for msg in buzon.receive("qgis"):
                    if msg.get("tipo") == "actualizar":
                        self._handle(msg)
                return
            if self.ticks % 4 == 0:
                buzon.heartbeat("qgis", {"version": VERSION})
                self._sync_toolbar()
                if buzon.icon_path("ingecad").exists() and self.ticks % 20 == 0 \
                        and "send" in self.actions:
                    self.actions["send"].setIcon(self._ingecad_icon())
            messages = buzon.receive("qgis")
            for msg in messages:
                self._handle(msg)
            if messages or self.ticks % 2 == 0:
                self._sync_locks()
        except Exception as exc:                    # el puente nunca tumba QGIS
            if self.ticks % 30 == 0:
                self._bar(f"{type(exc).__name__}: {exc}", "warn")

    def _project_layers(self):
        for layer in QgsProject.instance().mapLayers().values():
            src = layer_source(layer)
            if src is not None:
                yield layer, src

    def _sync_locks(self) -> None:
        block = bool(config.get("bloquear_en_qgis"))
        for layer, src in self._project_layers():
            lock = locked(*src) if block else None
            lid = layer.id()
            if lock is not None:
                if layer.readOnly() or lid in self.readonly_by_us:
                    continue
                if layer.isEditable():
                    if lid not in self.warned_editing:
                        self.warned_editing.add(lid)
                        self._bar(f"«{layer.name()}» está tomada por IngeCAD y usted la está "
                                  "editando en QGIS: guarde o descarte esos cambios.", "warn", 12)
                    continue
                layer.setReadOnly(True)
                self.readonly_by_us.add(lid)
            elif lid in self.readonly_by_us:
                layer.setReadOnly(False)
                self.readonly_by_us.discard(lid)
                self.warned_editing.discard(lid)

    def _handle(self, msg: dict) -> None:
        if msg.get("tipo") == "actualizar":
            # IngeCAD se actualizó: si en su carpeta hay algo nuevo para QGIS, se ofrece
            carpeta = msg.get("carpeta") or config.get("carpeta_actualizaciones")
            QTimer.singleShot(0, lambda: self.update_bridge(carpeta, avisar_ingecad=False,
                                                            silencioso=True))
            return
        if msg.get("tipo") != "guardado":
            return
        names, selected = [], 0
        for ref in msg.get("capas", []):
            for layer, src in self._project_layers():
                if _same(ref, src):
                    if self._reload(layer):
                        names.append(layer.name())
                        if ref.get("fids"):
                            layer.selectByIds([int(f) for f in ref["fids"]])
                            selected += len(ref["fids"])
        if names:
            self._bar("IngeCAD guardó: " + ", ".join(names)
                      + (f" ({selected} objeto(s) devueltos, quedan seleccionados)" if selected else ""),
                      "ok")

    def _reload(self, layer) -> bool:
        if not config.get("recargar_qgis"):
            return False
        if layer.isEditable():
            self._bar(f"«{layer.name()}» no se recargó porque está en edición en QGIS.", "warn")
            return False
        layer.dataProvider().reloadData()
        layer.reload()
        layer.triggerRepaint()
        return True

    def reload_all(self) -> None:
        n = 0
        for layer, _src in self._project_layers():
            if not layer.isEditable():
                layer.dataProvider().reloadData()
                layer.triggerRepaint()
                n += 1
        self._bar(f"{n} capa(s) recargadas.", "ok")

    # enviar
    def _visible_layers(self):
        layers = QgsProject.instance().layerTreeRoot().checkedLayers()
        return [lyr for lyr in layers if isinstance(lyr, QgsVectorLayer)]

    def send_default(self) -> None:
        mode = config.get("envio_predeterminado")
        self._send_mode(mode if mode in ("pantalla", "completa") else "seleccion")

    def send_selected(self) -> None:
        self._send_mode("seleccion")

    def send_screen(self) -> None:
        self._send_mode("pantalla")

    def send_visible(self) -> None:
        self._send_mode("completa")

    def send_active(self) -> None:
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            self._bar("Elija una capa vectorial (GeoPackage o shapefile).", "warn")
            return
        self._send_mode("completa", [layer])

    def _selected_layers(self):
        return [lyr for lyr in QgsProject.instance().mapLayers().values()
                if isinstance(lyr, QgsVectorLayer) and lyr.selectedFeatureCount() > 0]

    def _send_mode(self, mode: str, layers=None) -> None:
        """Pide las opciones del envío (ventana «Enviar a IngeCAD») y envía."""
        if mode == "seleccion" and layers is None and not self._selected_layers():
            self._bar("No hay objetos seleccionados. Seleccione en el mapa o use "
                      "«Enviar lo que está en pantalla».", "warn", 8)
            return
        opts = self._options(mode, show_mode=layers is None)
        if opts is None:
            return
        mode = opts["modo"]
        if layers is None:
            layers = self._selected_layers() if mode == "seleccion" else self._visible_layers()
        if mode == "seleccion" and not layers:
            self._bar("No hay objetos seleccionados.", "warn", 8)
            return
        self.send(layers, mode, opts)

    def _options(self, mode: str, show_mode: bool = True):
        try:
            from . import envio_ui

            if not config.get("preguntar_al_enviar"):
                return envio_ui.from_config(mode)
            scale = self.iface.mapCanvas().scale()
            return envio_ui.ask(self.iface.mainWindow(), mode, scale, show_mode)
        except Exception:                          # sin ventana: lo guardado
            return self._options_saved(mode)

    def _extent_in(self, layer):
        extent = self.iface.mapCanvas().extent()
        try:
            xform = QgsCoordinateTransform(QgsProject.instance().crs(), layer.crs(),
                                           QgsProject.instance())
            extent = xform.transformBoundingBox(extent)
        except Exception:
            pass
        return [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]

    def send(self, layers, mode: str = "completa", opts=None) -> None:
        """``mode``: "seleccion" (sólo los objetos seleccionados), "pantalla"
        (lo que toca el encuadre actual) o "completa". ``opts``: las opciones
        de la ventana «Enviar a IngeCAD» (None = las guardadas)."""
        mw = self.iface.mainWindow()
        opts = opts or self._options_saved(mode)
        extra = self._send_context(opts, layers, mode)
        refs, skipped, notes, first, count = [], [], [], None, 0
        home = Path.home().resolve()
        for layer in layers:
            if not layer.isSpatial():
                continue
            src = layer_source(layer)
            if src is None:
                skipped.append(f"{layer.name()} (no es GeoPackage ni shapefile)")
                continue
            if layer.isEditable():
                if layer.isModified():
                    answer = QMessageBox.question(
                        mw, "IngeCAD",
                        f"«{layer.name()}» tiene cambios sin guardar en QGIS.\n"
                        "¿Guardarlos antes de mandarla a IngeCAD?",
                        _YES | _NO | _CANCEL)
                    if answer == _CANCEL:
                        return
                    if answer == _NO:
                        skipped.append(f"{layer.name()} (cambios sin guardar en QGIS)")
                        continue
                if not layer.commitChanges():
                    skipped.append(f"{layer.name()} (QGIS no pudo guardarla)")
                    continue
            if any(_same(r, src) for r in refs):
                continue
            ref = buzon.layer_ref(*src)
            if mode == "seleccion":
                ids = sorted(int(i) for i in layer.selectedFeatureIds())
                if not ids:
                    continue
                ref["fids"] = ids
                count += len(ids)
            elif mode == "pantalla":
                ref["bbox"] = self._extent_in(layer)
            pres = self._presentacion(layer, ref, opts, extra)
            if pres:
                ref["estilo"] = pres
            if home not in Path(src[1]).parents:
                notes.append(layer.name())
            refs.append(ref)
            first = first or layer
        if not refs:
            self._bar("Nada para enviar. " + "; ".join(skipped), "warn", 10)
            return
        msg = {"tipo": "conectar", "capas": refs, "crs": first.crs().authid(),
               "extension": self._extent_in(first)}
        buzon.send("ingecad", msg, "qgis")
        what = {"seleccion": f"{count} objeto(s) seleccionados de {len(refs)} capa(s)",
                "pantalla": f"lo que está en pantalla de {len(refs)} capa(s)"}.get(
                    mode, f"{len(refs)} capa(s) completas")
        text = f"Enviado a IngeCAD: {what}."
        if skipped:
            text += " No se enviaron: " + "; ".join(skipped)
        if notes:
            text += (" Fuera de la carpeta personal: " + ", ".join(notes) + " (si IngeCAD no "
                     "la abre: flatpak override --user --filesystem=/media org.ingecad.IngeCAD).")
        other = buzon.version_of("ingecad") if buzon.is_alive("ingecad") else VERSION
        if other != VERSION:
            text += (f" IngeCAD tiene GeoCAD Yaguareté {other or 'anterior a 3.1.1'} y QGIS {VERSION}: "
                     "actualícelo (ACTUALIZARGEOCAD en IngeCAD) o pueden no llegar rótulos, "
                     "colores ni símbolos.")
        mismatch = other != VERSION
        self._bar(text, "warn" if (skipped or notes or mismatch) else "ok", 15 if mismatch else 12)
        if not buzon.is_alive("ingecad"):
            self.launch_ingecad()

    def _options_saved(self, mode: str) -> dict:
        try:
            from . import envio_ui

            return envio_ui.from_config(mode)
        except Exception:
            return {"modo": mode, "escala": 0, "capas_colores": False, "rotulos": "ninguno",
                    "simbolos": False, "ajustar": False, "preguntar": True}

    def _send_zone(self, layers, mode):
        """La zona que se manda, en coordenadas del mapa (xmin, ymin, xmax, ymax)."""
        canvas = self.iface.mapCanvas()
        if mode == "pantalla":
            e = canvas.extent()
            return [e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()]
        zone = None
        for layer in layers:
            box = layer.boundingBoxOfSelected() if mode == "seleccion" else layer.extent()
            if box is None or box.isNull():
                continue
            try:
                xform = QgsCoordinateTransform(layer.crs(), QgsProject.instance().crs(),
                                               QgsProject.instance())
                box = xform.transformBoundingBox(box)
            except Exception:
                pass
            b = [box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()]
            zone = b if zone is None else [min(zone[0], b[0]), min(zone[1], b[1]),
                                           max(zone[2], b[2]), max(zone[3], b[3])]
        return zone

    def _send_context(self, opts, layers=(), mode: str = "seleccion") -> dict:
        """Lo que se calcula una vez por envío: las etiquetas que QGIS muestra
        y las parcelas para achicar rótulos y símbolos."""
        extra = {"shown": None, "parcels": None, "screen": False}
        rot = opts.get("rotulos")
        try:
            from . import presentacion

            canvas = self.iface.mapCanvas()
            if rot == "visibles_zona":
                zone = self._send_zone(layers, mode)
                shown = None
                if zone is not None:
                    self._bar("Calculando las etiquetas que QGIS muestra en toda la zona...",
                              "info", 3)
                    QgsApplication.processEvents()
                    shown = presentacion.visible_labels_zone(
                        canvas.mapSettings(), zone, opts.get("escala") or 0)
                if shown is None:                 # zona enorme: lo de fuera va siempre
                    self._bar("La zona es demasiado grande para calcular sus etiquetas: "
                              "fuera de la pantalla van todas.", "warn", 10)
                    rot = "visibles_resto"
                else:
                    extra["shown"] = shown
            if rot in ("visibles", "visibles_resto"):
                extra["shown"] = presentacion.visible_labels(canvas, canvas.mapSettings()) or {}
                extra["screen"] = rot == "visibles_resto"
            if opts.get("ajustar"):
                extra["parcels"] = presentacion.Parcels(self._visible_layers())
        except Exception:
            pass
        return extra

    def _presentacion(self, layer, ref, opts=None, extra=None) -> dict:
        """Capas, colores, símbolos y rótulos de la capa para IngeCAD, según
        las opciones del envío (vacío si algo falla: el envío sigue igual)."""
        opts = opts or self._options_saved("completa")
        extra = extra or {}
        style, symbols = opts.get("capas_colores"), opts.get("simbolos")
        labels = opts.get("rotulos", "ninguno") != "ninguno"
        if not (style or labels or symbols):
            return {}
        try:
            from . import presentacion

            canvas = self.iface.mapCanvas()
            scale = opts.get("escala") or canvas.scale()
            shown = extra.get("shown")
            return presentacion.of_layer(
                layer, canvas.mapSettings(), scale, fids=ref.get("fids"), bbox=ref.get("bbox"),
                with_style=style, with_labels=labels, with_symbols=symbols,
                shown=None if shown is None else shown.get(layer.id(), set()),
                parcels=extra.get("parcels"),
                screen=self._extent_in(layer) if extra.get("screen") else None)
        except Exception as exc:                  # nunca frena el envío
            self._bar(f"«{layer.name()}» va sin capas, colores ni rótulos: {exc}", "warn", 8)
            return {}

    # abrir IngeCAD
    def launch_ingecad(self) -> None:
        candidates = []
        if os.path.exists("/.flatpak-info"):      # QGIS corre como Flatpak
            candidates.append(["flatpak-spawn", "--host", "flatpak", "run", INGECAD_FLATPAK])
        if shutil.which("flatpak"):
            candidates.append(["flatpak", "run", INGECAD_FLATPAK])
        if shutil.which("ingecad"):
            candidates.append(["ingecad"])
        for cmd in candidates:
            try:
                self._launch = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL,
                                                start_new_session=True)
            except OSError:
                continue
            self._bar("Abriendo IngeCAD... el pedido se carga solo al abrirse.")
            QTimer.singleShot(5000, self._check_launch)
            return
        self._launch_failed()

    def _check_launch(self) -> None:
        p = self._launch
        if p is not None and p.poll() not in (None, 0) and not buzon.is_alive("ingecad"):
            self._launch_failed()

    def _launch_failed(self) -> None:
        QMessageBox.information(
            self.iface.mainWindow(), "IngeCAD",
            "No pude abrir IngeCAD desde QGIS. Ábralo a mano: el pedido lo está "
            "esperando y se carga solo.\n\nPara que QGIS (Flatpak) pueda abrirlo, "
            "ejecute una vez en una terminal:\n\n"
            "flatpak override --user --talk-name=org.freedesktop.Flatpak org.qgis.qgis")

    # configuración y estado
    def open_config(self) -> None:
        from .opciones import open_dialog

        open_dialog(self.iface.mainWindow(), "QGIS")
        self._sync_toolbar()

    def show_status(self) -> None:
        lines = [f"GeoCAD Yaguareté {VERSION} para QGIS. Módulos: {modulos.resumen(PROGRAMA)}",
                 f"Carpeta común: {buzon.base_dir()}"]
        try:
            buzon.base_dir().mkdir(parents=True, exist_ok=True)
            probe = buzon.base_dir() / ".prueba"
            probe.write_text("ok")
            probe.unlink()
            lines.append("  se puede escribir: sí")
        except OSError as exc:
            lines.append(f"  se puede escribir: NO ({exc})")
        state = "abierto" if buzon.is_alive("ingecad") else "cerrado (o sin el plugin activo)"
        lines.append(f"IngeCAD: {state}")
        pend = list(buzon.inbox("ingecad").glob("*.json")) if buzon.inbox("ingecad").is_dir() else []
        if pend:
            lines.append(f"  {len(pend)} pedido(s) esperando a que IngeCAD los lea")
        taken = [layer.name() for layer, src in self._project_layers() if locked(*src)]
        lines.append("Capas tomadas por IngeCAD: " + (", ".join(taken) or "ninguna"))
        values = config.load()
        lines.append("")
        lines.append("Configuración común:")
        for s in config.SETTINGS:
            lines.append(f"  {s.label}: {config.display(s.key, values[s.key])}")
        QMessageBox.information(self.iface.mainWindow(), "Estado del puente", "\n".join(lines))

    # actualizar desde la carpeta del proyecto
    def _pedir_carpeta(self, actual: str):
        from qgis.PyQt.QtWidgets import QFileDialog

        carpeta = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(), "Carpeta de donde se actualiza GeoCAD Yaguareté (la del proyecto)",
            actual or str(Path.home()))
        return carpeta or None

    def _reinstalar(self) -> None:
        try:
            import qgis.utils
            qgis.utils.reloadPlugin(Path(__file__).resolve().parent.name)
        except Exception as exc:
            QMessageBox.information(self.iface.mainWindow(), "GeoCAD Yaguareté",
                                    f"La versión nueva quedó instalada, pero no se pudo recargar "
                                    f"({exc}). Reinicie QGIS.")

    def update_bridge(self, carpeta=None, avisar_ingecad: bool = True,
                      silencioso: bool = False) -> bool:
        """Busca la versión más nueva en la carpeta de actualizaciones, la
        instala y recarga el complemento; además le avisa a IngeCAD."""
        if carpeta is False:            # triggered(bool) del menú
            carpeta = None
        mw = self.iface.mainWindow()
        if not carpeta:
            carpeta = config.get("carpeta_actualizaciones")
        if not carpeta or not Path(carpeta).is_dir():
            if silencioso:
                return False
            elegida = self._pedir_carpeta(carpeta)
            if not elegida:
                self._bar("Actualizar GeoCAD Yaguareté: cancelado (falta la carpeta).", "warn")
                return False
            config.save({"carpeta_actualizaciones": elegida}, "QGIS")
            carpeta = elegida
        if avisar_ingecad:
            try:
                buzon.send("ingecad", {"tipo": "actualizar", "carpeta": carpeta}, "qgis")
            except OSError:
                pass
        cand = actualizar.mas_nueva(carpeta, "qgis", VERSION)
        if cand is None:
            if not silencioso:
                aviso = (" IngeCAD revisa la misma carpeta al recibir el aviso."
                         if avisar_ingecad else "")
                self._bar(f"GeoCAD Yaguareté para QGIS ya está en la última versión ({VERSION})."
                          + aviso, "info")
            return False
        texto = (f"Hay una versión nueva de GeoCAD Yaguareté para QGIS:\n\n"
                 f"    instalada: {VERSION}\n    nueva:     {cand.version}\n"
                 f"    archivo:   {cand.nombre}\n")
        detalle = actualizar.cambios(cand)
        if detalle:
            texto += "\n" + detalle + "\n"
        texto += "\n¿Instalarla ahora?"
        if QMessageBox.question(mw, "Actualizar GeoCAD Yaguareté", texto,
                                _YES | _NO) != _YES:
            return False
        aqui = Path(__file__).resolve().parent
        try:
            actualizar.instalar_zip(actualizar.extraer(cand), aqui.parent, aqui.name)
        except Exception as exc:
            QMessageBox.information(mw, "GeoCAD Yaguareté", f"No se instaló: {exc}")
            return False
        self._bar(f"GeoCAD Yaguareté {cand.version} instalado; recargando el complemento...", "ok")
        QTimer.singleShot(0, self._reinstalar)
        return True

    def about(self) -> None:
        from qgis.PyQt import QtWidgets

        nombre.mostrar_acerca(QtWidgets, self.iface.mainWindow(), PROGRAMA, VERSION,
                              modulos.resumen(PROGRAMA))
