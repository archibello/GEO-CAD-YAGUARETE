# -*- coding: utf-8 -*-
"""Imagen base en las presentaciones (Fernando, 08/11/2026).

Corre la imagen (teselas XYZ como Google Earth, una captura o un recorte
guardado: cualquier ráster) por debajo de las capas vectoriales, sólo dentro de
la ventana de una composición. Tres botones:

    1. Desplazar imagen: se arrastra con el mouse sobre el mapa; Esc la devuelve
       a sus coordenadas originales.
    2. Bloquear imagen: la deja fija (el corrimiento queda en el proyecto).
    3. Guardar recorte: GeoTIFF de lo que se ve y un 25 % más de área alrededor,
       con la georreferencia lograda.

No está en el menú GeoCAD: sólo en la barra de la composición y en el banco
Edición de Administrar Herramientas.

Cómo funciona: una capa de teselas no se puede correr, pero un mapa sí. Al primer
arrastre el mapa se separa en dos, en la misma ventana y con el mismo tamaño:
abajo un mapa nuevo con la imagen («imagen base»), arriba el mapa original con
las capas vectoriales, sin fondo. Arrastrar corre la extensión del de abajo
(lo mismo que el «Mover contenido» de QGIS) y el corrimiento se guarda en él.
El mapa de abajo sigue al de arriba en escala, extensión, posición y giro.

El recorte se pide a la imagen en la extensión corrida y se escribe con la
extensión del mapa vectorial: esa es la georreferencia nueva. Como en ArcGIS
(Georreferenciar > Guardar como nuevo, antes Rectificar), nace un archivo nuevo
y la fuente no se toca.

Las cuentas no usan QGIS: las prueba test_imagen_base.py.
"""
from __future__ import annotations

import os
from pathlib import Path

ICONOS = Path(__file__).parent / "iconos"
TITULO_BARRA = "GeoCAD Imagen base"
#: la imagen guardada abarca un 25 % más de área que el recorte (Fernando, 08/11/2026)
EXCESO_AREA = 0.25
OBJETO_BARRA = "GeoCADYaguareteImagenBase"

# propiedades propias de los mapas: viajan con el proyecto y con Deshacer
P_BASE = "geocad_imagen_base/base"             # en el mapa vectorial: uuid de su imagen
P_FRENTE = "geocad_imagen_base/frente"         # en la imagen: uuid de su mapa vectorial
P_DX = "geocad_imagen_base/dx"
P_DY = "geocad_imagen_base/dy"
P_BLOQUEADA = "geocad_imagen_base/bloqueada"
ENGANCHADO = "geocad_imagen_base_enganchado"   # propiedad Qt: ya sigue al mapa

PRIMERO = ("Arrastre sobre el mapa para correr la imagen; botón derecho cancela el arrastre; "
           "Esc la vuelve a sus coordenadas originales.")
SIN_IMAGEN = "Ese mapa no muestra ninguna imagen (teselas XYZ o ráster)."
SIN_MAPA = "Haga clic sobre un mapa, o elíjalo antes."
BLOQUEADA = "La imagen está bloqueada: destrábela con el botón del candado para moverla."
SIN_PAR = "Todavía no hay imagen corrida en esta composición: desplácela primero."
SOLO_PRESENTACION = "Esta herramienta se usa desde una presentación: abra su ventana primero."


# ------------------------------------------------------------ cuentas, sin QGIS
def partir_capas(capas, es_tesela):
    """``capas`` (la de arriba primero) en (arriba, imagen y lo que tiene debajo),
    cortando en la primera imagen; None si no hay. Lo que estaba debajo de la
    imagen sigue debajo: el mapa se ve igual que antes de separarlo."""
    for i, capa in enumerate(capas):
        if es_tesela(capa):
            return list(capas[:i]), list(capas[i:])
    return None


def corrimiento(frente, base) -> tuple:
    """(dx, dy) de la imagen respecto del mapa vectorial, en unidades de mapa.
    Las dos extensiones como (xmin, ymin, xmax, ymax)."""
    return ((base[0] + base[2] - frente[0] - frente[2]) / 2.0,
            (base[1] + base[3] - frente[1] - frente[3]) / 2.0)


def mover(extension, dx: float, dy: float) -> tuple:
    return (extension[0] + dx, extension[1] + dy, extension[2] + dx, extension[3] + dy)


def ampliar(rect, exceso_area: float = EXCESO_AREA) -> tuple:
    """``rect`` agrandado parejo desde su centro hasta sumar ``exceso_area`` de área."""
    k = (1.0 + exceso_area) ** 0.5
    cx, cy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
    mx, my = (rect[2] - rect[0]) * k / 2.0, (rect[3] - rect[1]) * k / 2.0
    return (cx - mx, cy - my, cx + mx, cy + my)


def plan_recorte(visible, extension, ancho_mm: float, dpi: float) -> dict:
    """El recorte a la resolución de la composición: tamaño en píxeles, píxel en
    unidades de mapa y ``destino``, ajustado a un número entero de píxeles para
    que la georreferencia sea exacta. ``visible`` es lo que abarca el mapa (si
    está girado, su rectángulo envolvente)."""
    pixeles_mapa = max(1, round(ancho_mm * dpi / 25.4))
    tam = (extension[2] - extension[0]) / pixeles_mapa
    if tam <= 0:
        raise ValueError("El mapa no tiene extensión.")
    ancho = max(1, round((visible[2] - visible[0]) / tam))
    alto = max(1, round((visible[3] - visible[1]) / tam))
    xmin, ymax = visible[0], visible[3]
    return {"ancho": ancho, "alto": alto, "tam": tam,
            "destino": (xmin, ymax - alto * tam, xmin + ancho * tam, ymax)}


def geotransform(destino, tam: float) -> tuple:
    """El geotransform de GDAL con origen en la esquina superior izquierda."""
    return (destino[0], tam, 0.0, destino[3], 0.0, -tam)


def nombre_archivo(mapa: str) -> str:
    limpio = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(mapa)).strip("_")
    return "imagen_base_%s.tif" % (limpio or "mapa")


def texto_corrimiento(dx: float, dy: float, unidad: str = "") -> str:
    fin = " " + unidad if unidad else ""
    return "Imagen corrida: X %+.3f%s, Y %+.3f%s respecto de las capas." % (dx, fin, dy, fin)


# ------------------------------------------------------------ los mapas de la composición
def _tupla(r) -> tuple:
    return (r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum())


def capa_es_imagen(capa) -> bool:
    """Teselas XYZ, WMS, capturas, GeoTIFF: todo lo que QGIS dibuja como ráster."""
    from qgis.core import QgsRasterLayer
    return isinstance(capa, QgsRasterLayer)


def capas_visibles(mapa) -> list:
    """Las capas que dibuja el mapa, la de arriba primero."""
    from qgis.core import QgsProject
    if mapa.keepLayerSet():
        return list(mapa.layers())
    temas = QgsProject.instance().mapThemeCollection()
    if mapa.followVisibilityPreset():
        return list(temas.mapThemeVisibleLayers(mapa.followVisibilityPresetName()))
    return list(temas.masterVisibleLayers())


def _item(layout, uuid):
    if not uuid:
        return None
    from qgis.core import QgsLayoutItemMap
    item = layout.itemByUuid(str(uuid))
    return item if isinstance(item, QgsLayoutItemMap) else None


def base_de(frente):
    """La imagen de ``frente``. Debe apuntarlo a él: un mapa copiado hereda la
    propiedad, pero la imagen sigue siendo del original."""
    base = _item(frente.layout(), frente.customProperty(P_BASE))
    return base if base is not None and str(base.customProperty(P_FRENTE)) == frente.uuid() else None


def frente_de(mapa):
    """El mapa vectorial de ``mapa`` (él mismo si no es una imagen base)."""
    return _item(mapa.layout(), mapa.customProperty(P_FRENTE)) or mapa


def mapas(layout) -> list:
    from qgis.core import QgsLayoutItemMap
    return [i for i in layout.items() if isinstance(i, QgsLayoutItemMap)]


def mapa_en(layout, punto):
    """El mapa bajo ``punto``, aunque arriba haya rótulos u otros elementos."""
    from qgis.core import QgsLayoutItemMap
    item = layout.layoutItemAt(punto, True)
    while item is not None and not isinstance(item, QgsLayoutItemMap):
        item = layout.layoutItemAt(punto, item, True)
    return item


def mapa_elegido(layout):
    """El mapa vectorial elegido; si no hay, el único que tenga imagen corrida."""
    from qgis.core import QgsLayoutItemMap
    for item in layout.selectedLayoutItems():
        if isinstance(item, QgsLayoutItemMap):
            return frente_de(item)
    pares = [m for m in mapas(layout) if base_de(m) is not None]
    return pares[0] if len(pares) == 1 else None


def huerfanas(layout) -> list:
    """Las imágenes base cuyo mapa ya no está en la composición. Se mira el modelo
    de elementos: al borrar, el mapa sale de él antes que de la escena."""
    modelo = layout.itemsModel()
    items = [modelo.itemFromIndex(modelo.index(f, 0)) for f in range(modelo.rowCount())]
    items = [i for i in items if i is not None]
    vivos = {i.uuid() for i in items}
    return [i for i in items if i.customProperty(P_FRENTE) and str(i.customProperty(P_FRENTE)) not in vivos]


def en_macro(layout) -> bool:
    """¿Hay un borrado del usuario en curso? QUndoStack, durante una macro, no deja
    deshacer ni rehacer; en un Deshacer, un Rehacer o al cerrar no se está en macro."""
    pila = layout.undoStack().stack()
    return pila.count() > 0 and not pila.canUndo() and not pila.canRedo()


def bloqueada(base) -> bool:
    return str(base.customProperty(P_BLOQUEADA, "0")) == "1"


def _debajo(base, frente) -> None:
    """La imagen inmediatamente debajo de su mapa vectorial, sin anotarlo en
    Deshacer: lowerItem suma un paso y, tras un Rehacer, borraría los siguientes."""
    layout = base.layout()
    if base.zValue() < frente.zValue():
        return
    pila = layout.undoStack()
    bloqueado = pila.isBlocked()
    pila.blockCommands(True)
    try:
        for _ in range(len(layout.items()) + 1):
            if base.zValue() < frente.zValue() or not layout.lowerItem(base):
                return
    finally:
        pila.blockCommands(bloqueado)


def sincronizar(frente) -> None:
    """La imagen sigue al mapa vectorial, conservando el corrimiento."""
    from qgis.core import QgsRectangle
    try:
        base = base_de(frente)
        if base is None:
            return
        dx = float(base.customProperty(P_DX, 0.0) or 0.0)
        dy = float(base.customProperty(P_DY, 0.0) or 0.0)
        base.setReferencePoint(frente.referencePoint())
        base.attemptResize(frente.sizeWithUnits())
        base.attemptMove(frente.positionWithUnits())
        base.setItemRotation(frente.itemRotation())
        base.setCrs(frente.presetCrs())
        base.setMapRotation(frente.mapRotation())
        base.zoomToExtent(QgsRectangle(*mover(_tupla(frente.extent()), dx, dy)))
    except RuntimeError:        # el elemento ya no existe
        pass


def separar(frente):
    """Divide el mapa en imagen base y capas vectoriales. Devuelve la imagen o
    None si el mapa no muestra teselas XYZ. Se deshace de una sola vez."""
    from qgis.core import QgsLayoutItemMap, QgsProject

    capas = capas_visibles(frente)
    partes = partir_capas(capas, capa_es_imagen)
    if partes is None:
        return None
    arriba, abajo = partes
    layout = frente.layout()
    tema = frente.followVisibilityPresetName() if frente.followVisibilityPreset() else ""
    pila = layout.undoStack()
    pila.beginMacro("Separar la imagen base")
    try:
        base = QgsLayoutItemMap(layout)
        base.setId("Imagen base de " + frente.displayName())
        base.setCustomProperty(P_FRENTE, frente.uuid())
        base.setCustomProperty(P_DX, 0.0)
        base.setCustomProperty(P_DY, 0.0)
        base.setKeepLayerSet(True)
        base.setLayers(abajo)
        base.setBackgroundEnabled(frente.hasBackground())
        base.setBackgroundColor(frente.backgroundColor())
        base.setFrameEnabled(False)
        base.setLocked(True)    # los clics van al mapa de arriba
        layout.addLayoutItem(base)

        pila.beginCommand(frente, "Separar la imagen base")
        if tema:
            frente.setLayerStyleOverrides(
                QgsProject.instance().mapThemeCollection().mapThemeStyleOverrides(tema))
            frente.setKeepLayerStyles(True)
            frente.setFollowVisibilityPreset(False)
        frente.setKeepLayerSet(True)
        frente.setLayers(arriba)
        frente.setBackgroundEnabled(False)
        frente.setCustomProperty(P_BASE, base.uuid())
        pila.endCommand()
    finally:
        pila.endMacro()
    sincronizar(frente)
    _debajo(base, frente)
    # sin esto el mapa de arriba sigue mostrando su dibujo guardado, con la imagen y
    # el fondo, y tapa a la de abajo hasta que algo lo regenere (Fernando, 08/11/2026)
    frente.invalidateCache()
    base.invalidateCache()
    return base


def guardar_corrimiento(frente, base) -> tuple:
    dx, dy = corrimiento(_tupla(frente.extent()), _tupla(base.extent()))
    base.setCustomProperty(P_DX, dx)
    base.setCustomProperty(P_DY, dy)
    return dx, dy


# ------------------------------------------------------------ el recorte
def _renderizar(capa, frente, plan, origen):
    """La capa en la extensión ``origen``, como QImage RGBA, y sus errores."""
    from qgis.core import (QgsMapRendererParallelJob, QgsMapSettings, QgsProject,
                           QgsRectangle)
    from qgis.PyQt.QtCore import QEventLoop, QSize
    from qgis.PyQt.QtGui import QColor, QImage

    ajustes = QgsMapSettings()
    ajustes.setLayers([capa])
    ajustes.setDestinationCrs(frente.crs())
    ajustes.setTransformContext(QgsProject.instance().transformContext())
    ajustes.setOutputSize(QSize(plan["ancho"], plan["alto"]))
    ajustes.setOutputDpi(frente.layout().renderContext().dpi())
    ajustes.setBackgroundColor(QColor(0, 0, 0, 0))
    ajustes.setExtent(QgsRectangle(*origen))
    trabajo = QgsMapRendererParallelJob(ajustes)
    espera = QEventLoop()
    trabajo.finished.connect(espera.quit)
    trabajo.start()
    if trabajo.isActive():
        espera.exec()
    errores = [e.message for e in trabajo.errors()]
    return trabajo.renderedImage().convertToFormat(QImage.Format.Format_RGBA8888), errores


def _escribir_geotiff(imagen, plan, crs, ruta) -> None:
    from osgeo import gdal

    ancho, alto, salto = imagen.width(), imagen.height(), imagen.bytesPerLine()
    puntero = imagen.constBits()
    puntero.setsize(imagen.sizeInBytes())
    datos = bytes(puntero)
    alfa = datos[3::4]
    if alfa.count(0) == len(alfa):
        raise ValueError("La imagen llegó vacía: revise la conexión y las teselas.")
    bandas = 3 if alfa.count(255) == len(alfa) else 4     # opaca: la lee también IngeCAD

    # primero un temporal: un archivo anterior no se pierde si algo falla
    temporal = str(ruta) + ".geocad-tmp.tif"
    try:
        opciones = ["COMPRESS=LZW", "TILED=YES"] + (["ALPHA=YES"] if bandas == 4 else [])
        ds = gdal.GetDriverByName("GTiff").Create(temporal, ancho, alto, bandas, gdal.GDT_Byte,
                                                  options=opciones)
        if ds is None:
            raise OSError("No se puede escribir en esa carpeta.")
        ds.SetGeoTransform(geotransform(plan["destino"], plan["tam"]))
        ds.SetProjection(crs.toWkt())
        for i in range(bandas):
            error = ds.GetRasterBand(i + 1).WriteRaster(
                0, 0, ancho, alto, datos[i:], buf_pixel_space=4, buf_line_space=salto)
            if error:
                raise OSError("GDAL no pudo escribir la imagen.")
        ds.FlushCache()
        ds = None
        os.replace(temporal, str(ruta))
    finally:
        ds = None
        if os.path.exists(temporal):
            os.remove(temporal)


def exportar_recorte(frente, capa, ruta, dx: float = 0.0, dy: float = 0.0) -> dict:
    """Escribe en ``ruta`` el GeoTIFF de lo que abarca ``frente`` más el excedente
    (EXCESO_AREA), con la imagen corrida (dx, dy). Devuelve el plan, con
    ``errores`` si faltó alguna tesela."""
    borde = frente.visibleExtentPolygon().boundingRect()
    visible = ampliar((borde.left(), borde.top(), borde.right(), borde.bottom()))
    plan = plan_recorte(visible, _tupla(frente.extent()), frente.rect().width(),
                        frente.layout().renderContext().dpi())
    imagen, errores = _renderizar(capa, frente, plan, mover(plan["destino"], dx, dy))
    _escribir_geotiff(imagen, plan, frente.crs(), ruta)
    plan["errores"] = errores
    return plan


# ------------------------------------------------------------ la herramienta de arrastre
def herramienta(modulo, designer):
    """La herramienta de la vista: arrastra el contenido de la imagen base."""
    from qgis.gui import QgsLayoutViewTool
    from qgis.PyQt.QtCore import Qt

    class DesplazarImagenTool(QgsLayoutViewTool):
        def __init__(self):
            super().__init__(designer.view(), "Desplazar imagen base")
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.base = None
            self.frente = None
            self.inicio = None

        def _diferencia(self, ev):
            p = ev.layoutPoint()
            return p.x() - self.inicio.x(), p.y() - self.inicio.y()

        def cancelar(self):
            if self.base is not None:
                try:
                    self.base.setMoveContentPreviewOffset(0, 0)
                    self.base.update()
                except RuntimeError:
                    pass
            self.base = self.frente = self.inicio = None

        def layoutPressEvent(self, ev):
            if ev.button() != Qt.MouseButton.LeftButton:
                self.cancelar()
                return
            par = modulo.par_para_mover(designer, ev.layoutPoint())
            if par is not None:
                self.frente, self.base = par
                self.inicio = ev.layoutPoint()

        def layoutMoveEvent(self, ev):
            if self.base is not None:
                self.base.setMoveContentPreviewOffset(*self._diferencia(ev))
                self.base.update()

        def layoutReleaseEvent(self, ev):
            if self.base is None or ev.button() != Qt.MouseButton.LeftButton:
                return
            base, frente = self.base, self.frente
            dx, dy = self._diferencia(ev)
            self.cancelar()
            if dx or dy:
                modulo.aplicar_arrastre(designer, frente, base, dx, dy)

        def keyPressEvent(self, ev):
            if ev.key() != Qt.Key.Key_Escape:
                super().keyPressEvent(ev)
                return
            self.cancelar()
            modulo.volver_al_origen(designer)
            ev.accept()

        def deactivate(self):
            self.cancelar()
            super().deactivate()

    return DesplazarImagenTool()


# ------------------------------------------------------------ barra de cada composición
class ImagenBaseComposicion:
    """La barra de tres botones en cada ventana de composición y las órdenes
    para el banco de Administrar Herramientas. Apagado el módulo, unload() la
    saca; los mapas ya separados quedan como están."""

    def __init__(self, iface):
        self.iface = iface
        self.barras = {}            # id(diseñador) -> dict de su barra
        self.enganches = []         # (mapa, función) para desconectar al apagar
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

    @staticmethod
    def icono(nombre):
        from qgis.PyQt.QtGui import QIcon
        return QIcon(str(ICONOS / nombre))

    def respaldo(self) -> list:
        """(clave, texto, función, archivo de ícono) para el banco de botones."""
        return [("imgbase_mover", "Desplazar imagen base (presentaciones)",
                 lambda _=False: self._desde_banco(self.desplazar), "imagen_base_mover.png"),
                ("imgbase_bloquear", "Bloquear imagen base (presentaciones)",
                 lambda _=False: self._desde_banco(self.bloquear), "imagen_base_bloquear.png"),
                ("imgbase_guardar", "Guardar imagen base recortada (presentaciones)",
                 lambda _=False: self._desde_banco(self.guardar), "imagen_base_guardar.png")]

    def _desde_banco(self, orden) -> None:
        try:
            abiertos = list(self.iface.openLayoutDesigners())
        except Exception:  # noqa: BLE001
            abiertos = []
        for d in abiertos:
            try:
                if d.window().isActiveWindow():
                    orden(d)
                    return
            except RuntimeError:
                pass
        if abiertos:
            orden(abiertos[-1])
        else:
            self.iface.messageBar().pushInfo("GeoCAD", SOLO_PRESENTACION)

    # -------------------------------------------------------- ventanas
    def _abierto(self, designer) -> None:
        from qgis.PyQt.QtCore import QTimer
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
        barra = QToolBar(TITULO_BARRA, win)
        barra.setObjectName(OBJETO_BARRA)
        desplazar = QAction(self.icono("imagen_base_mover.png"),
                            "Desplazar la imagen por debajo de las capas vectoriales", barra)
        desplazar.setCheckable(True)
        desplazar.triggered.connect(lambda _=False, d=designer: self.desplazar(d))
        trabar = QAction(self.icono("imagen_base_bloquear.png"),
                         "Bloquear la imagen en la posición lograda", barra)
        trabar.setCheckable(True)
        trabar.triggered.connect(lambda _=False, d=designer: self.bloquear(d))
        grabar = QAction(self.icono("imagen_base_guardar.png"),
                         "Guardar la imagen recortada con la nueva georreferencia", barra)
        grabar.triggered.connect(lambda _=False, d=designer: self.guardar(d))
        for accion, clave in ((desplazar, "imgbase_mover"), (trabar, "imgbase_bloquear"), (grabar, "imgbase_guardar")):
            accion.setProperty("geocad_id", "geocad:" + clave)      # Ver > Herramientas GeoCAD
        barra.addActions([desplazar, trabar, grabar])
        win.addToolBar(barra)
        tool = herramienta(self, designer)
        tool.setAction(desplazar)
        layout = designer.layout()
        actualizar = lambda *_a, d=designer: self._actualizar(d)  # noqa: E731
        quitado = lambda *_a, l=layout: self._quitado(l)  # noqa: E731
        agregado = lambda *_a: QTimer.singleShot(0, actualizar)  # noqa: E731
        try:
            layout.selectedItemChanged.connect(actualizar)
        except (AttributeError, TypeError):
            pass
        modelo = layout.itemsModel()
        modelo.rowsRemoved.connect(quitado)
        modelo.rowsInserted.connect(agregado)     # Deshacer un borrado rehace el mapa
        self.barras[id(designer)] = {"designer": designer, "barra": barra, "tool": tool,
                                     "trabar": trabar, "actualizar": actualizar,
                                     "quitado": quitado, "agregado": agregado}
        self._barrer_huerfanas(layout)
        self._actualizar(designer)

    def _cerrado(self, designer) -> None:
        datos = self.barras.pop(id(designer), None)
        if datos is not None:
            self._quitar_barra(datos)

    @staticmethod
    def _quitar_barra(datos) -> None:
        designer = datos["designer"]
        try:
            view = designer.view()
            if view.tool() is datos["tool"]:
                view.unsetTool(datos["tool"])
        except (RuntimeError, AttributeError):
            pass
        try:
            layout = designer.layout()
            layout.selectedItemChanged.disconnect(datos["actualizar"])
            layout.itemsModel().rowsRemoved.disconnect(datos["quitado"])
            layout.itemsModel().rowsInserted.disconnect(datos["agregado"])
        except (RuntimeError, TypeError, AttributeError):
            pass
        try:
            designer.window().removeToolBar(datos["barra"])
            datos["barra"].deleteLater()
        except RuntimeError:
            pass

    @staticmethod
    def _quitado(layout) -> None:
        """Borrado el mapa, se va su imagen, dentro de la misma macro: un solo Ctrl+Z
        recupera los dos. Deshacer o cerrar la composición también quitan elementos,
        pero eso no se toca."""
        try:
            if en_macro(layout):
                for base in huerfanas(layout):
                    layout.removeLayoutItem(base)
        except RuntimeError:
            pass

    @staticmethod
    def _barrer_huerfanas(layout) -> None:
        """Al abrir la composición: las que quedaron de antes (3.71.0), sin anotar en Deshacer."""
        pila = layout.undoStack()
        bloqueado = pila.isBlocked()
        pila.blockCommands(True)
        try:
            for base in huerfanas(layout):
                layout.removeLayoutItem(base)
        finally:
            pila.blockCommands(bloqueado)

    def _enganchar(self, layout) -> None:
        """Cada mapa con imagen la lleva consigo. Se revisa al abrir la ventana y
        al cambiar la selección: Deshacer o abrir un proyecto rehacen los elementos."""
        for frente in mapas(layout):
            base = base_de(frente)
            if base is None:
                continue
            _debajo(base, frente)
            if frente.property(ENGANCHADO):
                continue
            frente.setProperty(ENGANCHADO, True)
            seguir = lambda *_a, f=frente: sincronizar(f)  # noqa: E731
            for senal in self._senales(frente):
                senal.connect(seguir)
            self.enganches.append((frente, seguir))

    @staticmethod
    def _senales(frente) -> tuple:
        return (frente.extentChanged, frente.sizePositionChanged, frente.rotationChanged,
                frente.mapRotationChanged, frente.crsChanged)

    def _actualizar(self, designer) -> None:
        """El candado muestra el estado del mapa en uso."""
        datos = self.barras.get(id(designer))
        if datos is None:
            return
        try:
            layout = designer.layout()
            self._enganchar(layout)
            frente = mapa_elegido(layout)
            base = base_de(frente) if frente is not None else None
            datos["trabar"].setChecked(base is not None and bloqueada(base))
        except RuntimeError:
            pass

    # -------------------------------------------------------- las tres órdenes
    def desplazar(self, designer) -> None:
        datos = self.barras.get(id(designer))
        if datos is None:
            return
        designer.view().setTool(datos["tool"])
        designer.messageBar().pushInfo("GeoCAD", PRIMERO)

    def par_para_mover(self, designer, punto):
        """(mapa vectorial, imagen) bajo el punto, separándolos si hace falta."""
        layout = designer.layout()
        mapa = mapa_en(layout, punto)
        if mapa is None:
            designer.messageBar().pushInfo("GeoCAD", SIN_MAPA)
            return None
        frente = frente_de(mapa)
        base = base_de(frente)
        if base is None:
            base = separar(frente)
            if base is None:
                designer.messageBar().pushWarning("GeoCAD", SIN_IMAGEN)
                return None
            self._enganchar(layout)
        if bloqueada(base):
            designer.messageBar().pushWarning("GeoCAD", BLOQUEADA)
            return None
        return frente, base

    def aplicar_arrastre(self, designer, frente, base, dx, dy) -> None:
        pila = designer.layout().undoStack()
        pila.beginCommand(base, "Desplazar la imagen base")
        base.moveContent(-dx, -dy)
        mx, my = guardar_corrimiento(frente, base)
        pila.endCommand()
        datos = self.barras.get(id(designer))
        if datos is not None:
            datos["ultimo"] = frente.uuid()
        designer.messageBar().pushInfo("GeoCAD", texto_corrimiento(mx, my))

    def volver_al_origen(self, designer) -> None:
        """Esc: la imagen del último mapa arrastrado (o del elegido) sin corrimiento."""
        layout = designer.layout()
        datos = self.barras.get(id(designer)) or {}
        frente = _item(layout, datos.get("ultimo")) or mapa_elegido(layout)
        base = base_de(frente) if frente is not None else None
        if base is None:
            designer.messageBar().pushInfo("GeoCAD", SIN_PAR)
            return
        if bloqueada(base):
            designer.messageBar().pushWarning("GeoCAD", BLOQUEADA)
            return
        pila = layout.undoStack()
        pila.beginCommand(base, "Volver la imagen base a sus coordenadas originales")
        base.setCustomProperty(P_DX, 0.0)
        base.setCustomProperty(P_DY, 0.0)
        sincronizar(frente)
        pila.endCommand()
        designer.messageBar().pushInfo("GeoCAD", "Imagen en sus coordenadas originales.")

    def bloquear(self, designer) -> None:
        layout = designer.layout()
        frente = mapa_elegido(layout)
        base = base_de(frente) if frente is not None else None
        if base is None:
            designer.messageBar().pushInfo("GeoCAD", SIN_PAR)
            self._actualizar(designer)
            return
        nuevo = not bloqueada(base)
        pila = layout.undoStack()
        pila.beginCommand(base, "Bloquear la imagen base" if nuevo else "Destrabar la imagen base")
        base.setCustomProperty(P_BLOQUEADA, "1" if nuevo else "0")
        pila.endCommand()
        self._actualizar(designer)
        if nuevo:
            datos = self.barras.get(id(designer))
            if datos is not None and designer.view().tool() is datos["tool"]:
                from .pegartabla import volver_a_seleccionar
                volver_a_seleccionar(designer.view(), designer.window())
            designer.messageBar().pushSuccess("GeoCAD", "Imagen bloqueada en esta posición.")
        else:
            designer.messageBar().pushInfo("GeoCAD", "Imagen destrabada: ya se puede mover.")

    def guardar(self, designer) -> None:
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QApplication, QFileDialog

        frente = mapa_elegido(designer.layout())
        if frente is None:
            designer.messageBar().pushInfo("GeoCAD", SIN_MAPA)
            return
        base = base_de(frente)
        capas = capas_visibles(base if base is not None else frente)
        capa = next((c for c in capas if capa_es_imagen(c)), None)
        if capa is None:
            designer.messageBar().pushWarning("GeoCAD", SIN_IMAGEN)
            return
        dx, dy = (0.0, 0.0)
        if base is not None:
            dx, dy = corrimiento(_tupla(frente.extent()), _tupla(base.extent()))
        ruta, _f = QFileDialog.getSaveFileName(designer.window(), "Guardar imagen recortada",
                                               nombre_archivo(frente.displayName()),
                                               "GeoTIFF (*.tif *.tiff)")
        if not ruta:
            return
        if not ruta.lower().endswith((".tif", ".tiff")):
            ruta += ".tif"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            plan = exportar_recorte(frente, capa, ruta, dx, dy)
        except Exception as exc:  # noqa: BLE001 - se avisa y no queda archivo a medias
            designer.messageBar().pushCritical("GeoCAD", "No se guardó la imagen: %s" % exc)
            return
        finally:
            QApplication.restoreOverrideCursor()
        if plan["errores"]:
            designer.messageBar().pushWarning(
                "GeoCAD", "Imagen guardada, pero faltaron teselas: %s" % plan["errores"][0])
        else:
            designer.messageBar().pushSuccess(
                "GeoCAD", "Imagen guardada (%d × %d píxeles): %s" % (plan["ancho"], plan["alto"], ruta))

    # -------------------------------------------------------- descarga
    def unload(self) -> None:
        try:
            self.iface.layoutDesignerOpened.disconnect(self._abierto)
        except (TypeError, RuntimeError):
            pass
        try:
            self.iface.layoutDesignerWillBeClosed.disconnect(self._cerrado)
        except (TypeError, RuntimeError, AttributeError):
            pass
        for frente, seguir in self.enganches:
            try:
                for senal in self._senales(frente):
                    senal.disconnect(seguir)
                frente.setProperty(ENGANCHADO, False)
            except (TypeError, RuntimeError):
                pass
        self.enganches = []
        for datos in list(self.barras.values()):
            self._quitar_barra(datos)
        self.barras.clear()
