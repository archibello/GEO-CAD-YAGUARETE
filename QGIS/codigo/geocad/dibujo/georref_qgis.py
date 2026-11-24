# -*- coding: utf-8 -*-
"""GEORREF en QGIS: el de IngeCAD (3.93.0), barra «Yaguá Imagenes».

    Designe UNA imagen a ajustar (clic en la imagen):
    Punto en la imagen n [Cargar puntos/Deshacer] <Intro: tabla de puntos>:
    Punto de destino n [Deshacer]:

Fernando (23/11/2026): «que la misma este basada en la de IngeCAD y no en la
de QGIS, para que exista una verdadera razon para ocuparla en casos donde el
plano fué insertado a la pantalla desde otros procedimientos». La imagen se
ajusta DONDE ESTÁ en el mapa (pegada, arrastrada, insertada o ya
georreferenciada): se marcan pares de puntos con las referencias a objetos
(«Punto en la imagen» y «Punto de destino»), cada par es una flecha numerada,
U quita el último, C carga «<imagen>.points»; con los puntos suficientes se
ve, punteado, dónde va a quedar. Intro abre la TABLA DE PUNTOS (la de IngeCAD:
método con los nombres de QGIS, habilitar puntos, residuos, error medio,
remuestreo, fondo, dónde se guarda) y Transformar:
  * Lineal, Helmert y Polinómica 1 no rehacen la imagen: una copia
    «<imagen>_georref» con su archivo de mundo (o el archivo de mundo junto a
    la original), y la capa pasa a usarla;
  * Proyectiva, Polinómica 2-3 y Thin Plate Spline la deforman: se rehace en
    una copia (sin PIL: nucleo/georref_rehacer.py, igual que IngeCAD con PIL).
La original nunca se toca. Los puntos quedan en «<imagen>.points» (el archivo
del Georreferenciador de QGIS); la tabla tiene «Abrir en el Georreferenciador
de QGIS» con la imagen y esos puntos (decidido con Fernando). Las cuentas:
nucleo/georref_cuentas.py, las mismas de IngeCAD.
"""

import math
import os
import shutil

from qgis.core import QgsCoordinateTransform, QgsGeometry, QgsPointXY, QgsProject

from .. import georref_cuentas as G
from .. import georref_rehacer as GR
from . import aspecto_qgis as AQ
from . import imagen_geo as IG
from . import soltar_imagen as SI
from .imagen_geo_qgis import _ElegirImagen, abrir_georreferenciador, archivo_de_capa, leer as leer_gdal

#: en QGIS la imagen está en su archivo: no hay «sólo el dibujo»
SALIDAS = {k: v for k, v in G.SALIDAS.items() if k != "dibujo"}
PEDIDO_IMAGEN = 'Designe UNA imagen a ajustar (clic en la imagen)'


def coef_de_gt(gt):
    """Píxel de QGIS (columna, −fila) -> mapa, de una geotransformación de GDAL."""
    g = IG.gt_como_qgis(gt)
    return (g[0], g[1], -g[2], g[3], g[4], -g[5])


def gt_de_coef(coef):
    a, b, c, d, e, f = coef
    return (a, b, -c, d, e, -f)


def aux_xml(wkt, coef=None):
    """El .aux.xml de GDAL con el sistema y, con ``coef``, la geotransformación (manda
    sobre la de adentro de un GeoTIFF y sobre el archivo de mundo)."""
    from xml.sax.saxutils import escape
    txt = '<PAMDataset>\n'
    if wkt:
        txt += '  <SRS>%s</SRS>\n' % escape(wkt)
    if coef is not None:
        txt += '  <GeoTransform>%s</GeoTransform>\n' % ', '.join(repr(float(v)) for v in gt_de_coef(coef))
    return txt + '</PAMDataset>\n'


def georreferenciar_copia(ruta, coef, wkt=''):
    """El archivo de mundo y el .aux.xml de una copia hecha por GEORREF."""
    hechos = []
    m = SI.ruta_mundo(ruta)
    with open(m, 'w', encoding='ascii') as f:
        f.write(G.texto_mundo(coef))
    hechos.append(m)
    with open(str(ruta) + '.aux.xml', 'w', encoding='utf-8') as f:
        f.write(aux_xml(wkt, coef))
    hechos.append(str(ruta) + '.aux.xml')
    return hechos


def extension(original, fondo):
    """Transparente -> .png (o la de la original si es TIFF o PNG); blanco o negro -> la de la original."""
    suf = os.path.splitext(str(original))[1]
    if fondo == 'transparente':
        return suf if suf.lower() in ('.tif', '.tiff', '.png') else '.png'
    return suf


def rutas(original, fondo, elegida=None):
    """[(ruta, fondo), ...] de las imágenes rehechas (la primera la usa la capa), como IngeCAD."""
    fondos = ('transparente', 'blanco') if fondo == 'ambos' else (fondo,)
    out = []
    base_o, _e = os.path.splitext(str(original))
    for f in fondos:
        ext = extension(original, f)
        if elegida:
            b = os.path.expanduser(str(elegida))
            r = os.path.splitext(b)[0] + ext
        else:
            r = IG.nombre_copia(base_o + ext)
        if any(r == o for o, _f in out):
            r = (os.path.splitext(r)[0] + '_blanco' + ext if elegida
                 else IG.nombre_copia(base_o + '_blanco' + ext))
        if os.path.realpath(r) == os.path.realpath(str(original)):
            raise GR.RehacerError('la copia no puede ser la imagen original')
        if not os.path.isdir(os.path.dirname(os.path.abspath(r))):
            raise GR.RehacerError('no existe la carpeta %s' % os.path.dirname(r))
        out.append((r, f))
    return out


def guardar_imagen(a, ruta, gris=False):
    """Un arreglo RGBA como imagen (el formato, por la extensión)."""
    import numpy as np
    from qgis.PyQt.QtGui import QImage
    ext = os.path.splitext(str(ruta))[1].lower()
    im = AQ.a_qimage(a)
    if a[..., 3].min() == 255 or ext in ('.jpg', '.jpeg', '.bmp'):
        if gris:
            g = np.ascontiguousarray(a[..., 0])
            im = QImage(g.tobytes(), g.shape[1], g.shape[0], g.shape[1], QImage.Format.Format_Grayscale8).copy()
        else:
            im = im.convertToFormat(QImage.Format.Format_RGB888)
    fmt = {'.jpg': 'JPG', '.jpeg': 'JPG', '.tif': 'TIFF', '.tiff': 'TIFF', '.bmp': 'BMP'}.get(ext, 'PNG')
    if not im.save(str(ruta), fmt, 95 if fmt == 'JPG' else -1):
        raise OSError('no se pudo escribir %s' % ruta)


# ------------------------------------------------------------------ los números de las flechas
def _numeros_item(canvas):
    from qgis.gui import QgsMapCanvasItem

    class Numeros(QgsMapCanvasItem):
        def __init__(self):
            super().__init__(canvas)
            self.textos = []
            self.setZValue(6)

        def poner(self, textos):
            from qgis.core import QgsRectangle
            self.textos = list(textos)
            if self.textos:
                xs = [p[0] for p, _t in self.textos]
                ys = [p[1] for p, _t in self.textos]
                r = QgsRectangle(min(xs), min(ys), max(xs), max(ys))
                r.grow(max(r.width(), r.height(), 1.0) * 0.1)
                self.setRect(r)
            self.update()

        def paint(self, painter, option=None, widget=None):  # noqa: ARG002
            from qgis.PyQt.QtGui import QColor, QFont, QPen
            o = self.pos()
            painter.save()
            f = QFont(); f.setBold(True); f.setPointSize(10)
            painter.setFont(f)
            for p, t in self.textos:
                q = self.toCanvasCoordinates(QgsPointXY(*p))
                x, y = q.x() - o.x() + 6, q.y() - o.y() - 6
                painter.setPen(QPen(QColor(255, 255, 255)))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(int(x + dx), int(y + dy), t)
                painter.setPen(QPen(QColor(220, 30, 30)))
                painter.drawText(int(x), int(y), t)
            painter.restore()

    return Numeros()


# ------------------------------------------------------------------ la orden
class GeorrefCommand(_ElegirImagen):
    title = 'GEORREF'
    PEDIDO = PEDIDO_IMAGEN
    SALIDAS = SALIDAS

    def __init__(self, mgr, layer, kind):
        super().__init__(mgr, layer, kind)
        self.capa = None
        self._pares = []                 # {sx, sy, X, Y, on}, X/Y en el sistema de la capa
        self._pendiente = None           # punto en la imagen sin su destino (sistema de la capa)
        self._metodo = G._ultimo_metodo[0]
        self._salida = G._ultima_salida[0] if G._ultima_salida[0] in SALIDAS else 'copia'
        self._remuestreo = G._ultimo_remuestreo[0]
        self._fondo = G._ultimo_fondo[0]
        self._copia_en = None
        self.numeros = None
        self.hecha = None

    # -- elegir la imagen
    def prompt(self):
        if self.capa is None:
            self.cl.set_prompt(PEDIDO_IMAGEN)
        elif self._pendiente is None:
            self.cl.set_prompt('Punto en la imagen %d [Cargar puntos/Deshacer] <Intro: tabla de puntos>'
                               % self._n())
        else:
            self.cl.set_prompt('Punto de destino %d [Deshacer]' % self._n())

    def base(self):
        return self._a_mapa(self._pendiente) if self._pendiente is not None else None

    def _n(self):
        return len(self._pares) + 1

    def con_capa(self, capa):
        original = archivo_de_capa(capa)
        datos = leer_gdal(original)
        if datos is None:
            self.cl.echo('GEORREF: no se puede leer %s.' % os.path.basename(original))
            self.end()
            return
        self.capa, self.original = capa, original
        if not capa.crs().isValid():               # sin sistema: el del mapa, como INSERTARGEO
            capa.setCrs(self.mgr.canvas.mapSettings().destinationCrs())
        self.coef = coef_de_gt(datos[0])
        self.tam = (float(datos[1]), float(datos[2]))
        self.cl.echo('Imagen: %s (%d x %d píxeles).' % (os.path.basename(original), datos[1], datos[2]))
        r = self.ruta_points()
        if os.path.isfile(r):
            try:
                n = len(G.leer_points(r))
            except OSError:
                n = 0
            if n:
                self.cl.echo('Hay %d puntos guardados en %s: C (Cargar puntos) los trae.'
                             % (n, os.path.basename(r)))
        try:
            self.numeros = _numeros_item(self.mgr.canvas)
        except Exception:  # noqa: BLE001 -- sin números: quedan las flechas
            self.numeros = None
        self.prompt()

    def ruta_points(self):
        return self.original + '.points'

    # -- mapa <-> sistema de la capa
    def _ct(self, ida=True):
        destino = self.mgr.canvas.mapSettings().destinationCrs()
        crs = self.capa.crs()
        if not (crs.isValid() and destino.isValid()) or crs == destino:
            return None
        return QgsCoordinateTransform(destino, crs, QgsProject.instance()) if ida else \
            QgsCoordinateTransform(crs, destino, QgsProject.instance())

    def _a_capa(self, p):
        ct = self._ct(True)
        q = ct.transform(p) if ct is not None else p
        return (q.x(), q.y())

    def _a_mapa(self, xy):
        p = QgsPointXY(*xy)
        ct = self._ct(False)
        return ct.transform(p) if ct is not None else p

    def mundo_a_pixel(self, xy):
        return G.aplicar(G.inversa(self.coef), xy)

    def pixel_a_mundo(self, s):
        return G.aplicar(self.coef, s)

    # -- entrada
    def on_point(self, p):
        if self.capa is None:
            super().on_point(p)
            return
        xy = self._a_capa(p)
        if self._pendiente is None:
            self._pendiente = xy
            self._set_last(p)
            self.prompt()
            return
        sx, sy = self.mundo_a_pixel(self._pendiente)
        self._pares.append({'sx': sx, 'sy': sy, 'X': xy[0], 'Y': xy[1], 'on': True})
        self._pendiente = None
        self._set_last(p)
        self.cl.echo(self._resumen())
        self.prompt()

    def _resumen(self):
        hab = [x for x in self._pares if x['on']]
        nombre, minimo, _d = G.METODOS[self._metodo]
        if len(hab) < minimo:
            return '%d par(es). %s necesita %d.' % (len(self._pares), nombre, minimo)
        t = G.filas_tabla(self._pares, self._metodo)
        if t['coef'] is None:
            return '%d par(es). %s' % (len(self._pares), t['motivo'])
        return ('%d par(es). %s: error medio %s. Intro abre la tabla de puntos.'
                % (len(self._pares), nombre, G._fmt(t['rms'])))

    def on_text(self, text):
        t = text.strip().upper().lstrip('_')
        if self.capa is not None:
            if t in ('U', 'D', 'DESHACER', 'UNDO'):
                if self._pendiente is not None:
                    self._pendiente = None
                    self.cl.echo('Se quitó el punto en la imagen sin destino.')
                elif self._pares:
                    self._pares.pop()
                    self.cl.echo('Se quitó el par %d.' % (len(self._pares) + 1))
                else:
                    self.cl.echo('No hay pares para quitar.')
                self.prompt()
                return
            if t in ('C', 'CARGAR', 'CARGARPUNTOS', 'LOAD') and self._pendiente is None:
                self.cargar()
                self.prompt()
                return
        self._resolve_and_apply(text)

    def cargar(self, ruta=None):
        ruta = ruta or self.ruta_points()
        if not os.path.isfile(ruta):
            self.cl.echo('No hay archivo de puntos junto a la imagen.')
            return False
        try:
            self._pares = G.leer_points(ruta)
        except OSError as e:
            self.cl.echo('No se pudo leer %s: %s' % (os.path.basename(ruta), e))
            return False
        self.cl.echo('Cargados %d pares de %s.' % (len(self._pares), os.path.basename(ruta)))
        return True

    def on_enter(self):
        if self.capa is None:
            self.end()
            return
        if self._pendiente is not None:
            self.cl.echo('Falta el punto de destino de ese par (U lo quita).')
            self.prompt()
            return
        if not self._pares:
            self.end()
            return
        self.abrir_tabla()

    def escape(self):
        if self.capa is not None and self.hecha is None:
            self.cl.echo('GEORREF cancelado: la imagen queda como estaba.')
        self.end()

    def cleanup(self):
        n, self.numeros = self.numeros, None
        if n is not None:
            try:
                n.hide()
                self.mgr.canvas.scene().removeItem(n)
            except Exception:  # noqa: BLE001
                pass

    # -- lo que se ve: el marco, las flechas numeradas y dónde quedaría
    def _flecha(self, a, b, punta):
        segs = [[a, b]]
        L = math.dist(a, b)
        if L <= G.EPS:
            return segs
        k = min(punta, 0.35 * L) / L
        dx, dy = (b[0] - a[0]) * k, (b[1] - a[1]) * k
        for s in (1, -1):
            c, si = math.cos(math.radians(25)), s * math.sin(math.radians(25))
            segs.append([b, (b[0] - (dx * c - dy * si), b[1] - (dx * si + dy * c))])
        return segs

    def _linea(self, pts):
        return QgsGeometry.fromPolylineXY([self._a_mapa(p) for p in pts])

    def preview(self, cur):
        if self.capa is None:
            return super().preview(cur)
        if self._pendiente is None or cur is None:
            return [], False, [], []
        a, b = self._pendiente, self._a_capa(cur)
        caja = [self.pixel_a_mundo(s) for s in G.borde_pixeles(*self.tam)]
        segs = self._flecha(a, b, 0.02 * math.dist(caja[0], caja[2]))
        pts = [self._a_mapa(segs[0][0]), self._a_mapa(segs[0][1])]
        for s in segs[1:]:
            pts += [self._a_mapa(s[1]), self._a_mapa(segs[0][1])]
        return pts, False, [], []

    def preview_geoms(self, cur):
        if self.capa is None:
            return None
        caja = [self.pixel_a_mundo(s) for s in G.borde_pixeles(*self.tam)]
        geoms = [self._linea(caja + caja[:1])]
        punta = 0.02 * math.dist(caja[0], caja[2])
        textos = []
        for i, p in enumerate(self._pares, 1):
            a = self.pixel_a_mundo((p['sx'], p['sy']))
            for s in self._flecha(a, (p['X'], p['Y']), punta):
                geoms.append(self._linea(s))
            q = self._a_mapa(a)
            textos.append(((q.x(), q.y()), str(i) if p['on'] else '(%d)' % i))
        pares = list(self._pares)
        if self._pendiente is not None:
            q = self._a_mapa(self._pendiente)
            textos.append(((q.x(), q.y()), str(self._n())))
            if cur is not None:
                c = self._a_capa(cur)
                sx, sy = self.mundo_a_pixel(self._pendiente)
                pares.append({'sx': sx, 'sy': sy, 'X': c[0], 'Y': c[1], 'on': True})
        if self.numeros is not None:
            try:
                self.numeros.poner(textos)
            except Exception:  # noqa: BLE001
                pass
        hab = [p for p in pares if p['on']]
        if len(hab) >= G.METODOS[self._metodo][1]:
            try:
                coef = G.ajustar(self._metodo, [(p['sx'], p['sy']) for p in hab],
                                 [(p['X'], p['Y']) for p in hab])
                vista = [G.aplicar(coef, s) for s in G.borde_pixeles(*self.tam, coef)]
                geoms.append(self._linea(vista + vista[:1]))
            except (G.AjusteError, ZeroDivisionError, ValueError):
                pass
        return geoms

    # -- la tabla
    def abrir_tabla(self):
        r = tabla(self.mgr.iface.mainWindow(), self)
        if r is None:
            self.escape()
            return
        self._metodo = G._ultimo_metodo[0] = r.get('metodo', self._metodo)
        self._salida = G._ultima_salida[0] = r.get('salida', self._salida)
        self._remuestreo = G._ultimo_remuestreo[0] = r.get('remuestreo', self._remuestreo)
        self._fondo = G._ultimo_fondo[0] = r.get('fondo', self._fondo)
        if r.get('copia_en'):
            self._copia_en = r['copia_en']
        if r.get('pares') is not None:
            self._pares = r['pares']
        for p, on in zip(self._pares, r.get('habilitados', ())):
            p['on'] = bool(on)
        accion = r.get('accion')
        if accion == 'transformar':
            self.transformar()
        elif accion == 'nativo':
            self.al_georreferenciador()
        else:
            self.prompt()

    def guardar(self, ruta=None):
        ruta = ruta or self.ruta_points()
        crs = self.capa.crs().authid() if self.capa.crs().isValid() else ''
        try:
            r = G.escribir_points(ruta, self._pares, crs, self._metodo)
        except OSError as e:
            self.cl.echo('No se pudieron guardar los puntos en %s: %s' % (ruta, e))
            return None
        self.cl.echo('Puntos guardados en %s (se abren en el Georreferenciador de QGIS).' % r)
        return str(r)

    def al_georreferenciador(self):
        """«Abrir en el Georreferenciador de QGIS»: los puntos en el .points y la imagen ahí."""
        self.guardar()
        falla = abrir_georreferenciador(self.mgr.iface, self.original)
        if falla:
            self.cl.echo('GEORREF: %s. Abra %s con «Abrir ráster» del Georreferenciador.' % (falla, self.original))
        else:
            self.cl.echo('GEORREF: %s abierta en el Georreferenciador de QGIS con sus %d puntos.'
                         % (os.path.basename(self.original), len(self._pares)))
        self.end()

    # -- transformar
    def _wkt(self):
        return self.capa.crs().toWkt() if self.capa.crs().isValid() else ''

    def transformar(self):
        t = G.filas_tabla(self._pares, self._metodo)
        if t['coef'] is None:
            self.cl.echo('No se puede transformar: ' + t['motivo'])
            self.abrir_tabla()
            return
        coef, capa, original = t['coef'], self.capa, self.original
        nombre = G.METODOS[self._metodo][0]
        n = sum(1 for p in self._pares if p['on'])
        if self._metodo in G.REHACEN:
            self.rehacer(coef, t['rms'])
            return
        try:
            if self._salida == 'mundo':
                mundo = SI.ruta_mundo(original)
                if os.path.exists(mundo):
                    shutil.copy2(mundo, mundo + '.bak')
                with open(mundo, 'w', encoding='ascii') as f:
                    f.write(G.texto_mundo(coef))
                AQ.usar_archivo(capa, original)             # vuelve a leerla, ya en su lugar
                donde = 'Archivo de mundo junto a la original: %s.' % os.path.basename(mundo)
            else:
                copia = (IG.destino_copia(self._copia_en, original) if self._copia_en
                         else IG.nombre_copia(original))
                shutil.copy2(original, copia)
                hechos = georreferenciar_copia(copia, coef, self._wkt())
                AQ.usar_archivo(capa, copia)
                donde = ('Copia ajustada: %s (%s); la capa usa la copia y %s queda como estaba.'
                         % (copia, ' y '.join(os.path.basename(h) for h in hechos), os.path.basename(original)))
        except OSError as e:
            self.cl.echo('GEORREF: no se pudo guardar (%s).' % e)
            self.end()
            return
        self.hecha = capa
        self.cl.echo('Imagen ajustada con %s: %d puntos, error medio %s (%s).'
                     % (nombre, n, G._fmt(t['rms']), G.describir(coef)))
        self.cl.echo(donde)
        self.guardar()
        self.end()

    def rehacer(self, modelo, rms):
        capa, original = self.capa, self.original
        nombre = G.METODOS[self._metodo][0]
        try:
            salidas = rutas(original, self._fondo, self._copia_en)
        except (OSError, G.AjusteError) as e:
            self.cl.echo('GEORREF: no se pudo rehacer la imagen (%s).' % e)
            self.abrir_tabla()
            return
        prog = AQ.Progreso(self.mgr.iface.mainWindow(), 'GEORREF', self.tam[0] * self.tam[1] / 1e6)
        rem, wkt = self._remuestreo, self._wkt()
        try:
            fuente = prog.trabajo('1/3  Abriendo la imagen', lambda: AQ.abrir(original), 0.0, 0.15, 'abrir')
            gris = bool((fuente[..., 0] == fuente[..., 1]).all() and (fuente[..., 1] == fuente[..., 2]).all())
            hecho = [0.0]
            nueva, coef, tam = prog.trabajo('2/3  Rehaciendo la imagen con %s' % nombre,
                                            lambda: GR.rehacer_arreglo(fuente, modelo, rem,
                                                                       lambda f: hecho.__setitem__(0, f)),
                                            0.15, 0.8, 'rehacer', hecho)
            del fuente

            def escribir():
                out = []
                for ruta, fondo in salidas:
                    guardar_imagen(GR.con_fondo(nueva, fondo), ruta, gris and fondo != 'transparente')
                    out.append((ruta, fondo, georreferenciar_copia(ruta, coef, wkt)))
                return out
            hechos = prog.trabajo('3/3  Guardando la copia', escribir, 0.8, 0.97, 'guardar')
            prog.etapa(0.98, 'Actualizando el mapa')
            AQ.usar_archivo(capa, salidas[0][0])
        except (OSError, G.AjusteError, ValueError, MemoryError) as e:
            prog.cerrar()
            self.cl.echo('GEORREF: no se pudo rehacer la imagen (%s).' % e)
            self.abrir_tabla()
            return
        prog.cerrar()
        self.hecha = capa
        n = sum(1 for p in self._pares if p['on'])
        self.cl.echo('Imagen rehecha con %s: %d puntos, error medio %s, %d x %d píxeles.'
                     % (nombre, n, G._fmt(rms), tam[0], tam[1]))
        for ruta, fondo, h in hechos:
            uso = 'la usa la capa' if ruta == salidas[0][0] else 'otra copia'
            self.cl.echo('  %s (fondo %s; %s) y %s.' % (ruta, fondo, uso, ' y '.join(os.path.basename(x) for x in h)))
        self.cl.echo('%s queda como estaba.' % os.path.basename(original))
        self.guardar()
        self.end()


def tabla(parent, tool):
    """La tabla de puntos (georref_ui_qgis.py); las pruebas la reemplazan."""
    from . import georref_ui_qgis
    return georref_ui_qgis.tabla(parent, tool)


def instalar(plugin):
    from .commands import CommandSpec
    plugin.mgr.register(CommandSpec('GEORREF', ('GEORREF', 'RUBBERSHEET', 'AJUSTEIMAGEN'), GeorrefCommand,
                                    'interactive', 'GEORREF', None, False, 'dibujo',
                                    'Ajustar una imagen con puntos de control, donde está en el mapa '
                                    '(el de IngeCAD; tabla de puntos, siete métodos)'))
