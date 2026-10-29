# SPDX-License-Identifier: GPL-3.0-or-later
"""Shift + clic derecho al digitalizar en QGIS: el menú de referencias de IngeCAD.

Mientras se digitalizan líneas, polilíneas o polígonos, Shift + clic
derecho despliega el menú y la opción elegida vale para el punto siguiente,
como en AutoCAD. Vale en las dos clases de herramienta:
- las de QGIS (Agregar entidad de línea / de polígono): el vértice se
  agrega exacto con addVertex, sin pasar por el píxel del cursor;
- los comandos de Dibujo de GeoCAD que piden un punto (LINEA, PLINEA...):
  el punto va al comando como un punto enganchado (3.55.1).
Esc cancela la referencia sin cancelar el dibujo.

No toca la herramienta: un filtro de eventos sobre el lienzo, que se saca
entero al apagar el módulo. Las cuentas están en referencias.py.
"""
from __future__ import annotations

import math

from qgis.core import (QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsPointXY,
                       QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsMapToolCapture, QgsVertexMarker
from qgis.PyQt.QtCore import QEvent, QObject, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QInputDialog, QMenu, QToolTip

from . import referencias as R

APERTURA_PX = 12        # radio de búsqueda alrededor del cursor, en píxeles
MAX_ENTIDADES = 500     # por capa y por movimiento del cursor

_ICONO = {"END": "ICON_BOX", "MID": "ICON_TRIANGLE", "INT": "ICON_X", "EXT": "ICON_CROSS",
          "CEN": "ICON_CIRCLE", "GCE": "ICON_CIRCLE", "QUA": "ICON_RHOMBUS",
          "TAN": "ICON_CIRCLE", "PER": "ICON_BOX", "PAR": "ICON_CROSS", "NOD": "ICON_CIRCLE",
          "INS": "ICON_BOX", "NEA": "ICON_DOUBLE_TRIANGLE", "ORI": "ICON_CROSS",
          "FROM": "ICON_BOX", "M2P": "ICON_BOX"}


def _enum(owner, scope, member):
    """owner.scope.member (Qt6 / QGIS 4) u owner.member (Qt5 / QGIS 3)."""
    sc = getattr(owner, scope, None)
    if sc is not None and hasattr(sc, member):
        return getattr(sc, member)
    return getattr(owner, member)


def _exec(obj, *args):
    fn = getattr(obj, "exec", None) or getattr(obj, "exec_")
    return fn(*args)


def _pos(ev):
    p = ev.position() if hasattr(ev, "position") else ev.pos()
    return p.x(), p.y()


class ReferenciasQgis(QObject):
    """El menú de referencias para un punto, en las herramientas de QGIS."""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.modo = None            # la referencia elegida, hasta el próximo punto
        self.etapa = 0              # FROM: 0 = punto base; M2P: 0 = primero, 1 = segundo
        self.base = None
        self.fuentes = []           # EXT: puntas adquiridas
        self.direcciones = []       # PAR: direcciones adquiridas
        self.candidato = None
        self._abriendo = False
        self._tragar_suelta = False
        self.marca = QgsVertexMarker(self.canvas)
        self.marca.setColor(QColor(255, 140, 0))
        self.marca.setIconSize(14)
        self.marca.setPenWidth(2)
        self.marca.hide()
        self.guia = QgsVertexMarker(self.canvas)      # lo adquirido para EXT / PAR
        self.guia.setColor(QColor(0, 160, 0))
        self.guia.setIconType(_enum(QgsVertexMarker, "IconType", "ICON_CROSS"))
        self.guia.setIconSize(10)
        self.guia.hide()
        self.canvas.viewport().installEventFilter(self)
        self.canvas.installEventFilter(self)
        self.canvas.mapToolSet.connect(self._cambio_herramienta)

    def unload(self):
        self.cancelar()
        try:
            self.canvas.mapToolSet.disconnect(self._cambio_herramienta)
        except Exception:  # noqa: BLE001
            pass
        for obj in (self.canvas.viewport(), self.canvas):
            try:
                obj.removeEventFilter(self)
            except Exception:  # noqa: BLE001
                pass
        scene = self.canvas.scene()
        for item in (self.marca, self.guia):
            try:
                scene.removeItem(item)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ herramienta activa
    def herramienta(self):
        """La herramienta que está digitalizando (envuelta en _Captura o
        _Dibujo), o None si no hay ninguna."""
        tool = self.canvas.mapTool()
        if isinstance(tool, QgsMapToolCapture):
            modos = (_enum(QgsMapToolCapture, "CaptureMode", "CaptureLine"),
                     _enum(QgsMapToolCapture, "CaptureMode", "CapturePolygon"))
            try:
                return _Captura(tool, self.canvas) if tool.mode() in modos else None
            except Exception:  # noqa: BLE001
                return None
        mgr = getattr(tool, "mgr", None)
        if mgr is not None and hasattr(mgr, "point_clicked") and getattr(mgr, "command", None) is not None:
            return _Dibujo(mgr)
        return None

    def _vertices(self, tool):
        return tool.vertices()

    def _agregar(self, tool, x, y, engancha=True):
        tool.agregar(x, y, engancha)

    def _cambio_herramienta(self, *args):
        self.cancelar()

    # ------------------------------------------------------------ eventos
    def eventFilter(self, obj, ev):
        try:
            return self._filtrar(obj, ev)
        except Exception as exc:  # noqa: BLE001  un error acá no puede trabar el lienzo
            self.cancelar()
            self._aviso(f"GeoCAD: {type(exc).__name__}: {exc}")
            return False

    def _filtrar(self, obj, ev):
        t = ev.type()
        if t == _enum(QEvent, "Type", "KeyPress"):
            if self.modo is not None and ev.key() == _enum(Qt, "Key", "Key_Escape"):
                self.cancelar()
                self._aviso("*Cancel* (object snap)")
                return True
            return False
        if obj is not self.canvas.viewport():
            return False
        derecho = _enum(Qt, "MouseButton", "RightButton")
        izquierdo = _enum(Qt, "MouseButton", "LeftButton")
        shift = _enum(Qt, "KeyboardModifier", "ShiftModifier")
        press = _enum(QEvent, "Type", "MouseButtonPress")
        release = _enum(QEvent, "Type", "MouseButtonRelease")
        move = _enum(QEvent, "Type", "MouseMove")
        if t == press and ev.button() == derecho and (ev.modifiers() & shift):
            if self.herramienta() is None:
                return False
            self._abriendo = True          # la herramienta no ve el clic: no termina el objeto
            return True
        if t == release and ev.button() == derecho and self._abriendo:
            self._abriendo = False
            gpos = QCursor.pos()
            QTimer.singleShot(0, lambda: self.menu(gpos))
            return True
        if self.modo is None:
            return False
        tool = self.herramienta()
        if tool is None:
            self.cancelar()
            return False
        if t == move:
            self._mover(tool, *_pos(ev))
            return False                   # la línea elástica sigue al cursor
        if t == press and ev.button() == izquierdo:
            self._tragar_suelta = True
            return True
        if t == release and ev.button() == izquierdo and self._tragar_suelta:
            self._tragar_suelta = False
            x, y = _pos(ev)
            QTimer.singleShot(0, lambda: self._clic(tool, x, y))
            return True
        if t == press and ev.button() == derecho:
            self.cancelar()                # clic derecho solo: QGIS termina el objeto
        return False

    # ------------------------------------------------------------ menú
    def menu(self, gpos):
        tool = self.herramienta()
        if tool is None:
            return
        m = QMenu(self.canvas)
        m.setToolTipsVisible(True)
        elegidas = {}
        for item in R.MENU:
            if item is None:
                m.addSeparator()
                continue
            clave, texto = item
            act = m.addAction(texto)
            if clave in R.NO_DISPONIBLES:
                act.setEnabled(False)
                act.setToolTip(R.NO_DISPONIBLES[clave])
            elegidas[act] = clave
        act = _exec(m, gpos)
        if act is None or act not in elegidas:
            return
        self.elegir(elegidas[act], tool)

    def elegir(self, clave, tool=None):
        tool = self.herramienta()
        if clave == "SETTINGS":
            self._opciones_enganche()
            return
        self.cancelar()
        if tool is None:
            return
        previo = tool.previo()
        if clave == "PER" and previo is None:
            self._aviso("Perpendicular needs a previous point.")
            return
        if clave == "PAR" and previo is None:
            self._aviso("Parallel needs a previous point.")
            return
        self.modo = clave
        mensajes = {"FROM": "From  Base point:", "M2P": "First point of mid:",
                    "EXT": "Extension: pause over the end of a line, then follow its path.",
                    "PAR": "Parallel: pause over a line, then move parallel to it.",
                    "NON": "None: the next point is not snapped."}
        self._aviso(mensajes.get(clave, f"{R.ETIQUETA[clave]}: pick the point (Esc cancels)."))

    def _opciones_enganche(self):
        from qgis.PyQt.QtWidgets import QAction, QToolBar
        win = self.iface.mainWindow()
        act = win.findChild(QAction, "mActionSnappingOptions")
        if act is not None:
            act.trigger()
            return
        barra = win.findChild(QToolBar, "mSnappingToolBar")
        if barra is not None:
            barra.setVisible(True)

    def cancelar(self):
        self.modo, self.etapa, self.base, self.candidato = None, 0, None, None
        self.fuentes, self.direcciones = [], []
        self._tragar_suelta = False
        self.marca.hide()
        self.guia.hide()

    # ------------------------------------------------------------ búsqueda
    def _mapa(self, x, y):
        p = self.canvas.getCoordinateTransform().toMapCoordinates(int(round(x)), int(round(y)))
        return (p.x(), p.y())

    def _umbral(self):
        return self.canvas.mapUnitsPerPixel() * APERTURA_PX

    def _enganche_qgis(self, p):
        """Para el punto base de From y los de Mid Between 2 Points: el
        enganche de QGIS que esté configurado."""
        try:
            match = self.canvas.snappingUtils().snapToMap(QgsPointXY(*p))
            if match.isValid():
                q = match.point()
                return (q.x(), q.y())
        except Exception:  # noqa: BLE001
            pass
        return p

    def _calcular(self, tool, p):
        u = self._umbral()
        vertices = self._vertices(tool)
        previo = tool.previo()
        if self.modo in ("FROM", "M2P"):
            return self._enganche_qgis(p)
        if self.modo == "NON":
            return p
        datos = self.datos(p, u, vertices)
        if self.modo == "EXT":
            fuente = R.fuente_extension(p, u, datos)
            if fuente is not None and fuente not in self.fuentes:
                self.fuentes = (self.fuentes + [fuente])[-2:]
            return R.sobre_extension(p, u, self.fuentes)
        if self.modo == "PAR":
            d = R.direccion_de_tramo(p, u, datos)
            if d is not None and d not in self.direcciones:
                self.direcciones = [d]
            return R.sobre_paralela(p, u, previo, self.direcciones)
        return R.buscar(self.modo, p, u, datos, previo)

    def _mover(self, tool, x, y):
        p = self._mapa(x, y)
        self.candidato = self._calcular(tool, p)
        if self.candidato is None or self.modo == "NON":
            self.marca.hide()
        else:
            self.marca.setIconType(_enum(QgsVertexMarker, "IconType", _ICONO.get(self.modo, "ICON_BOX")))
            self.marca.setCenter(QgsPointXY(*self.candidato))
            self.marca.show()
            QToolTip.showText(QCursor.pos(), R.ETIQUETA[self.modo], self.canvas)
        guia = (self.fuentes[-1][0] if self.modo == "EXT" and self.fuentes else None)
        if guia is not None:
            self.guia.setCenter(QgsPointXY(*guia))
            self.guia.show()
        else:
            self.guia.hide()

    def _clic(self, tool, x, y):
        if self.modo is None:
            return
        p = self._mapa(x, y)
        punto = self._calcular(tool, p)
        if self.modo == "FROM":
            if self.etapa == 0:
                self.base, self.etapa = punto, 1
                texto, ok = QInputDialog.getText(self.canvas, "From", "<Offset> (@dx,dy or @distance<angle):",
                                                 text="@")
                destino = R.desplazamiento(texto, self.base) if ok else None
                if not ok:
                    self.cancelar()
                    return
                if destino is None:
                    self._aviso("Invalid offset. From  Base point:")
                    self.etapa, self.base = 0, None
                    return
                self.cancelar()
                self._agregar(tool, *destino)
            return
        if self.modo == "NON":
            self.cancelar()
            self._agregar(tool, *punto, engancha=False)
            return
        if self.modo == "M2P":
            if self.etapa == 0:
                self.base, self.etapa = punto, 1
                self._aviso("Second point of mid:")
                return
            destino = R.medio(self.base, punto)
            self.cancelar()
            self._agregar(tool, *destino)
            return
        if punto is None:
            self._aviso(f"No {R.ETIQUETA[self.modo].lower()} found for specified point.")
            return
        self.cancelar()
        self._agregar(tool, *punto)

    def datos(self, p, umbral, vertices=()):
        """La geometría de las capas visibles cerca de p (coordenadas del mapa)."""
        d = R.Datos()
        oid = [0]
        rect = QgsRectangle(p[0] - umbral, p[1] - umbral, p[0] + umbral, p[1] + umbral)
        destino = self.canvas.mapSettings().destinationCrs()
        for lyr in self.canvas.layers():
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isSpatial():
                continue
            try:
                ida = QgsCoordinateTransform(destino, lyr.crs(), QgsProject.instance())
                vuelta = QgsCoordinateTransform(lyr.crs(), destino, QgsProject.instance())
                req = QgsFeatureRequest().setFilterRect(ida.transformBoundingBox(rect))
                req.setNoAttributes()
                req.setLimit(MAX_ENTIDADES)
                for f in lyr.getFeatures(req):
                    g = QgsGeometry(f.geometry())
                    if g.isNull() or g.isEmpty():
                        continue
                    if lyr.crs() != destino:
                        g.transform(vuelta)
                    oid[0] += 1
                    _descomponer(g.constGet(), oid[0], d)
            except Exception:  # noqa: BLE001  una capa rara no corta la búsqueda
                continue
        # lo que se está dibujando (todavía no está en la capa)
        for a, b in zip(vertices, list(vertices)[1:]):
            d.segs.append((a[0], a[1], b[0], b[1], -1))
        return d

    def _aviso(self, texto):
        try:
            self.iface.mainWindow().statusBar().showMessage(texto, 6000)
        except Exception:  # noqa: BLE001
            pass


class _Captura:
    """Una herramienta propia de QGIS que digitaliza (QgsMapToolCapture)."""

    def __init__(self, tool, canvas):
        self.tool, self.canvas = tool, canvas

    def __eq__(self, otra):
        return isinstance(otra, _Captura) and otra.tool is self.tool

    def _capa(self):
        try:
            lyr = self.tool.layer()
        except Exception:  # noqa: BLE001
            lyr = None
        return lyr if lyr is not None else self.canvas.currentLayer()

    def vertices(self):
        """Los vértices ya digitalizados, en coordenadas del mapa."""
        lyr = self._capa()
        ms = self.canvas.mapSettings()
        out = []
        try:
            for p in self.tool.points():
                q = QgsPointXY(p.x(), p.y())
                out.append(ms.layerToMapCoordinates(lyr, q) if lyr is not None else q)
        except Exception:  # noqa: BLE001
            return []
        return [(q.x(), q.y()) for q in out]

    def previo(self):
        v = self.vertices()
        return v[-1] if v else None

    def agregar(self, x, y, engancha=True):
        self.tool.addVertex(QgsPointXY(x, y))
        if hasattr(self.tool, "isCapturing") and not self.tool.isCapturing():
            self.tool.startCapturing()


class _Dibujo:
    """Un comando de Dibujo de GeoCAD que pide un punto (LINEA, PLINEA...)."""

    def __init__(self, mgr):
        self.mgr = mgr

    def __eq__(self, otra):
        return isinstance(otra, _Dibujo) and otra.mgr is self.mgr

    def vertices(self):
        try:
            return [(p.x(), p.y()) for p in (self.mgr.command.snap_points() or [])]
        except Exception:  # noqa: BLE001
            return []

    def previo(self):
        try:
            b = self.mgr.command.base()
        except Exception:  # noqa: BLE001
            b = None
        if b is None:
            b = getattr(self.mgr, "lastpoint", None)
        return (b.x(), b.y()) if b is not None else None

    def agregar(self, x, y, engancha=True):
        # enganchado: el comando lo toma tal cual (sin Orto ni redondeo)
        self.mgr.point_clicked(QgsPointXY(x, y), engancha, False)


def _xy(pt):
    return (pt.x(), pt.y())


def _descomponer(geom, oid, d, anillo=False):
    """Reparte una geometría de QGIS en tramos, arcos, nodos y centros."""
    nombre = type(geom).__name__
    if nombre in ("QgsPoint",):
        d.nodos.append(_xy(geom))
        d.inserciones.append(_xy(geom))
        return
    if nombre in ("QgsLineString",):
        pts = [_xy(geom.pointN(i)) for i in range(geom.numPoints())]
        _cadena(pts, oid, d, anillo)
        return
    if nombre == "QgsCircularString":
        pts = [_xy(geom.pointN(i)) for i in range(geom.numPoints())]
        cerrado = len(pts) >= 3 and R._igual(pts[0], pts[-1])
        if cerrado and len(pts) in (3, 5):
            c = R.arco_de_tres(pts[0], pts[1], pts[2]) if len(pts) == 5 else None
            if len(pts) == 3:                   # círculo dado por dos puntos opuestos
                cx, cy = R.medio(pts[0], pts[1])
                d.arcos.append((cx, cy, math.dist(pts[0], pts[1]) / 2, 0.0, 2 * math.pi, True, oid))
                return
            if c is not None:
                d.arcos.append((c[0], c[1], c[2], 0.0, 2 * math.pi, True, oid))
                return
        for i in range(0, len(pts) - 2, 2):
            c = R.arco_de_tres(pts[i], pts[i + 1], pts[i + 2])
            if c is None:
                d.segs.append((*pts[i], *pts[i + 2], oid))
            else:
                d.arcos.append((*c, False, oid))
        return
    if nombre == "QgsCompoundCurve":
        for i in range(geom.nCurves()):
            _descomponer(geom.curveAt(i), oid, d)
        return
    if hasattr(geom, "exteriorRing"):           # polígonos (también curvos)
        ext = geom.exteriorRing()
        if ext is not None:
            _descomponer(ext, oid, d, anillo=True)
            try:
                lineal = ext.curveToLine() if hasattr(ext, "curveToLine") else ext
                pts = [_xy(lineal.pointN(i)) for i in range(lineal.numPoints())]
                c = R.centroide(pts)
                if c is not None and c not in d.centros:
                    d.centros.append(c)
            except Exception:  # noqa: BLE001
                pass
        for i in range(geom.numInteriorRings()):
            _descomponer(geom.interiorRing(i), oid, d, anillo=True)
        return
    if hasattr(geom, "numGeometries"):           # multi y colecciones
        for i in range(geom.numGeometries()):
            _descomponer(geom.geometryN(i), oid, d)


def _cadena(pts, oid, d, anillo):
    cerrada = len(pts) >= 3 and R._igual(pts[0], pts[-1])
    if cerrada:
        circ = R.circulo_de_anillo(pts)
        if circ is not None:                    # círculo linealizado: centro y cuadrantes
            d.arcos.append((circ[0], circ[1], circ[2], 0.0, 2 * math.pi, True, oid))
            for a, b in zip(pts, pts[1:]):
                d.cuerdas.append((a[0], a[1], b[0], b[1], oid))
            return
        if not anillo:                          # polilínea cerrada: también Geometric Center
            c = R.centroide(pts)
            if c is not None:
                d.centros.append(c)
    for a, b in zip(pts, pts[1:]):
        if not R._igual(a, b):
            d.segs.append((a[0], a[1], b[0], b[1], oid))
