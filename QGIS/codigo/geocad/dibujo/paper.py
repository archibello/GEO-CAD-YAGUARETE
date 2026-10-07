# -*- coding: utf-8 -*-
"""
Espacio papel al estilo AutoCAD sobre los diseños de impresión de QGIS.

  * Presentaciones (QgsPrintLayout) con hoja ISO, recuadro, cajetín con campos
    dinámicos, ventana gráfica a escala, norte y escala gráfica.
  * Trazado (PLOT) a PDF, imagen o impresora desde el modelo (Ventana / Extensión /
    Pantalla) o desde una presentación.
  * Tablas de estilo de trazado: variables de diseño @cad_ctb ('monochrome',
    'grayscale', '') y @cad_lw (0 = sin grosores), que interpreta la simbología de
    Layer Properties Manager.
"""

import os
import tempfile

from qgis.PyQt.QtCore import QSize, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices, QFont
from qgis.core import (QgsExpressionContextUtils, QgsFillSymbol, QgsLayoutExporter, QgsLayoutItemLabel,
                       QgsLayoutItemMap, QgsLayoutItemShape, QgsLayoutMeasurement, QgsLayoutPoint,
                       QgsLayoutSize, QgsPrintLayout, QgsProject, QgsRectangle)

from .compat import enum

PAPERS = {  # nombre -> (ancho, alto) en mm, vertical
    'ISO A4 (210 x 297 mm)': (210, 297), 'ISO A3 (297 x 420 mm)': (297, 420),
    'ISO A2 (420 x 594 mm)': (420, 594), 'ISO A1 (594 x 841 mm)': (594, 841),
    'ISO A0 (841 x 1189 mm)': (841, 1189), 'Carta (216 x 279 mm)': (216, 279),
    'Oficio (216 x 356 mm)': (216, 356),
}
PAPER_ORDER = list(PAPERS)
SCALES = ['Ajustar al papel', '1:1', '1:2', '1:5', '1:10', '1:20', '1:25', '1:50', '1:75', '1:100',
          '1:125', '1:200', '1:250', '1:500', '1:750', '1:1000', '1:1250', '1:2000', '1:2500',
          '1:5000', '1:10000', '1:20000', '1:25000', '1:50000']
CTB = [('', 'Ninguno (según pantalla)'), ('monochrome', 'monochrome.ctb (monocromo)'),
       ('grayscale', 'Grayscale.ctb (escala de grises)')]
CAD_FLAG = 'dibujo_cad/layout'


# ---------------------------------------------------------------- utilidades
def mm():
    try:
        from qgis.core import Qgis
        return Qgis.LayoutUnit.Millimeters
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return QgsUnitTypes.LayoutMillimeters


def P(x, y):
    return QgsLayoutPoint(x, y, mm())


def S(w, h):
    return QgsLayoutSize(w, h, mm())


def paper_size(name, landscape):
    w, h = PAPERS.get(name, (297, 420))
    return (max(w, h), min(w, h)) if landscape else (min(w, h), max(w, h))


def parse_scale(text):
    """'1:100' / '100' -> 100.0 ; 'Ajustar...' -> None."""
    t = (text or '').strip().lower()
    if not t or t.startswith('ajust') or t.startswith('fit'):
        return None
    if ':' in t:
        a, b = t.split(':', 1)
        a, b = float(a.replace(',', '.')), float(b.replace(',', '.'))
        return b / a if a else None
    return float(t.replace(',', '.'))


def layout_manager():
    return QgsProject.instance().layoutManager()


def layouts():
    return list(layout_manager().printLayouts()) if hasattr(layout_manager(), 'printLayouts') \
        else [l for l in layout_manager().layouts() if isinstance(l, QgsPrintLayout)]


def find_layout(name):
    for l in layouts():
        if l.name() == name:
            return l
    return None


def unique_layout_name(base='Presentación'):
    names = {l.name() for l in layouts()}
    i = 1
    while '%s%d' % (base, i) in names:
        i += 1
    return '%s%d' % (base, i)


def set_style_vars(layout, ctb, lineweights=True):
    QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_ctb', ctb or '')
    QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_lw', 1 if lineweights else 0)


def _label(layout, text, x, y, w, h, size=8, bold=False, align_left=True):
    lb = QgsLayoutItemLabel(layout)
    lb.setText(text)
    f = QFont('Arial')
    f.setBold(bold)
    try:
        from qgis.core import QgsTextFormat
        fmt = QgsTextFormat()
        fmt.setFont(f)
        fmt.setSize(size)
        fmt.setColor(QColor(0, 0, 0))
        lb.setTextFormat(fmt)
    except (ImportError, AttributeError):
        f.setPointSizeF(size)
        lb.setFont(f)
    try:
        from qgis.PyQt.QtCore import Qt
        lb.setVAlign(Qt.AlignmentFlag.AlignVCenter if hasattr(Qt, 'AlignmentFlag') else Qt.AlignVCenter)
    except Exception:  # noqa: BLE001
        pass
    layout.addLayoutItem(lb)
    lb.attemptMove(P(x, y))
    lb.attemptResize(S(w, h))
    return lb


def _rect(layout, x, y, w, h, width=0.35, fill=None):
    sh = QgsLayoutItemShape(layout)
    sh.setShapeType(enum(QgsLayoutItemShape, 'Shape', 'Rectangle'))
    sym = QgsFillSymbol.createSimple({'color': fill or '255,255,255,0', 'outline_color': '0,0,0',
                                      'outline_width': str(width), 'outline_width_unit': 'MM'})
    try:
        sh.setSymbol(sym)
    except AttributeError:
        pass
    layout.addLayoutItem(sh)
    sh.attemptMove(P(x, y))
    sh.attemptResize(S(w, h))
    return sh


def paper_map_background(item):
    """Las ventanas del espacio papel se ven sobre papel blanco, como en AutoCAD
    (QGIS les copia el fondo del mapa; si es oscuro, el color 7 trazado en negro no se ve).
    Devuelve True si cambió algo."""
    try:
        c = item.backgroundColor()
        if item.hasBackground() and c.alpha() > 0 and c.lightness() < 128:
            item.setBackgroundColor(QColor(255, 255, 255))
            item.refresh()
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def fix_layout_backgrounds(layout):
    n = 0
    try:
        for it in layout.items():
            if isinstance(it, QgsLayoutItemMap) and paper_map_background(it):
                n += 1
    except RuntimeError:
        pass
    return n


# ---------------------------------------------------------------- bloqueo de ventanas
def layout_maps(layout):
    try:
        return [it for it in layout.items() if isinstance(it, QgsLayoutItemMap)]
    except RuntimeError:
        return []


def is_layout_locked(layout):
    maps = layout_maps(layout)
    return bool(maps) and all(m.keepLayerSet() and m.isLocked() for m in maps)


def lock_layout(layout, on, canvas=None):
    """Bloquea (o desbloquea) las ventanas de una presentación, como VENTANAS > Bloquear de AutoCAD:
    capas visibles y estilos actuales fijos, y la ventana no se puede mover ni redimensionar.
    Devuelve la cantidad de ventanas cambiadas."""
    n = 0
    layers = None
    if on:
        try:
            layers = list(canvas.layers()) if canvas is not None else \
                list(QgsProject.instance().layerTreeRoot().checkedLayers())
        except Exception:  # noqa: BLE001
            layers = None
    for m in layout_maps(layout):
        try:
            if on:
                if layers:
                    m.setLayers(layers)
                m.setKeepLayerSet(True)
                try:
                    m.storeCurrentLayerStyles()
                except AttributeError:
                    pass
                m.setKeepLayerStyles(True)
                m.setLocked(True)
            else:
                m.setKeepLayerSet(False)
                m.setKeepLayerStyles(False)
                m.setLocked(False)
            m.refresh()
            n += 1
        except RuntimeError:
            pass
    return n


def _map(layout, canvas, x, y, w, h, extent, scale, item_id):
    m = QgsLayoutItemMap(layout)
    m.setId(item_id)
    m.setBackgroundColor(QColor(255, 255, 255))
    layout.addLayoutItem(m)
    m.attemptMove(P(x, y))
    m.attemptResize(S(w, h))
    try:
        m.setCrs(canvas.mapSettings().destinationCrs())
    except Exception:  # noqa: BLE001
        pass
    if extent is not None:
        m.zoomToExtent(extent)
    if scale:
        m.setScale(scale)        # QGIS conserva el centro de la ventana al cambiar la escala
    m.setFrameEnabled(True)
    try:
        m.setFrameStrokeWidth(QgsLayoutMeasurement(0.25, mm()))
    except Exception:  # noqa: BLE001
        pass
    return m


# ---------------------------------------------------------------- presentación
def create_layout(iface, name, paper, landscape, extent, scale, title_block=True, north=True,
                  ctb='', lineweights=True):
    """Crea una presentación al estilo AutoCAD y la agrega al proyecto."""
    prj = QgsProject.instance()
    canvas = iface.mapCanvas()
    lay = QgsPrintLayout(prj)
    lay.initializeDefaults()
    lay.setName(name)
    W, H = paper_size(paper, landscape)
    page = lay.pageCollection().page(0)
    page.setPageSize(S(W, H))
    # márgenes ISO 5457: 20 mm a la izquierda (encuadernación), 10 mm el resto
    L, R, T, Bm = 20.0, 10.0, 10.0, 10.0
    _rect(lay, L, T, W - L - R, H - T - Bm, width=0.5)
    tb_h = 0.0
    if title_block:
        tb_w = min(180.0, W - L - R)
        tb_h = 32.0
        x0, y0 = W - R - tb_w, H - Bm - tb_h
        _rect(lay, x0, y0, tb_w, tb_h, width=0.5)
        c1, c2 = tb_w * 0.55, tb_w * 0.25
        rows = [(x0, y0, c1, 12, 'PROYECTO', "[% coalesce(nullif(@project_title, ''), @project_basename) %]"),
                (x0, y0 + 12, c1, 10, 'PLANO', '[% @layout_name %]'),
                (x0, y0 + 22, c1, 10, 'DIBUJÓ', '[% @user_full_name %]'),
                (x0 + c1, y0, c2, 12, 'ESCALA',
                 "[% '1:' || format_number(map_get(item_variables('VP1'), 'map_scale'), 0) %]"),
                (x0 + c1, y0 + 12, c2, 10, 'FECHA', "[% format_date(now(), 'dd/MM/yyyy') %]"),
                (x0 + c1, y0 + 22, c2, 10, 'HOJA', '1 / 1'),
                (x0 + c1 + c2, y0, tb_w - c1 - c2, tb_h, 'Nº', '[% @layout_name %]')]
        for x, y, w, h, title, value in rows:
            _rect(lay, x, y, w, h, width=0.25)
            _label(lay, title, x + 1.5, y + 0.6, w - 3, 3.6, size=5.5)
            _label(lay, value, x + 1.5, y + 3.6, w - 3, h - 4.2, size=9 if h > 10 else 8, bold=True)
    # ventana gráfica: área libre sobre el cajetín
    vx, vy = L + 5, T + 5
    vw, vh = W - L - R - 10, H - T - Bm - 10 - (tb_h + 5 if title_block else 0)
    m = _map(lay, canvas, vx, vy, vw, vh, extent, scale, 'VP1')
    if north:
        try:
            from qgis.core import QgsLayoutItemPicture, QgsLayoutItemScaleBar
            pic = QgsLayoutItemPicture(lay)
            pic.setPicturePath(':/images/north_arrows/layout_default_north_arrow.svg')
            pic.setLinkedMap(m)
            lay.addLayoutItem(pic)
            pic.attemptMove(P(vx + vw - 16, vy + 4))
            pic.attemptResize(S(12, 14))
            sb = QgsLayoutItemScaleBar(lay)
            sb.setLinkedMap(m)
            sb.setStyle('Single Box')
            sb.applyDefaultSize()
            lay.addLayoutItem(sb)
            sb.attemptMove(P(vx + 4, vy + vh - 14))
        except Exception:  # noqa: BLE001
            pass
    set_style_vars(lay, ctb, lineweights)
    lay.setCustomProperty(CAD_FLAG, '1')
    layout_manager().addLayout(lay)
    return lay


def add_viewport(iface, layout, extent, scale):
    """VENTANAS (MVIEW): agrega una ventana gráfica a escala en la presentación."""
    page = layout.pageCollection().page(0)
    ps = page.pageSize()
    W, H = ps.width(), ps.height()
    n = 1 + sum(1 for it in layout.items() if isinstance(it, QgsLayoutItemMap))
    if scale and extent is not None:
        w = min(extent.width() * 1000.0 / scale, W - 40)
        h = min(extent.height() * 1000.0 / scale, H - 40)
    else:
        w, h = W * 0.4, H * 0.4
    x = max(20.0, (W - w) / 2.0)
    y = max(10.0, (H - h) / 2.0)
    return _map(layout, iface.mapCanvas(), x, y, w, h, extent, scale, 'VP%d' % n)


# ---------------------------------------------------------------- trazado
def _ok(res):
    try:
        return res == QgsLayoutExporter.ExportResult.Success
    except AttributeError:
        return res == QgsLayoutExporter.Success


def model_layout(iface, paper, landscape, extent, scale, ctb, lineweights, margin=5.0):
    """Presentación temporal para trazar el modelo (no se agrega al proyecto)."""
    lay = QgsPrintLayout(QgsProject.instance())
    lay.initializeDefaults()
    lay.setName('Modelo')
    W, H = paper_size(paper, landscape)
    lay.pageCollection().page(0).setPageSize(S(W, H))
    m = _map(lay, iface.mapCanvas(), margin, margin, W - 2 * margin, H - 2 * margin, extent, scale, 'VP1')
    m.setFrameEnabled(False)
    set_style_vars(lay, ctb, lineweights)
    return lay


def export(layout, device, path=None, dpi=300, ctb=None, lineweights=None):
    """Traza la presentación. device: 'PDF', 'PNG' o el nombre de una impresora."""
    prev = None
    if ctb is not None or lineweights is not None:
        scope = QgsExpressionContextUtils.layoutScope(layout)
        prev = (scope.variable('cad_ctb'), scope.variable('cad_lw'))
        set_style_vars(layout, ctb if ctb is not None else (prev[0] or ''),
                       lineweights if lineweights is not None else prev[1] != 0)
    try:
        exp = QgsLayoutExporter(layout)
        if device == 'PDF':
            s = QgsLayoutExporter.PdfExportSettings()
            s.dpi = dpi
            try:
                s.forceVectorOutput = True
            except AttributeError:
                pass
            return _ok(exp.exportToPdf(path, s)), path
        if device == 'PNG':
            s = QgsLayoutExporter.ImageExportSettings()
            s.dpi = dpi
            return _ok(exp.exportToImage(path, s)), path
        from qgis.PyQt.QtPrintSupport import QPrinter
        printer = QPrinter()
        printer.setPrinterName(device)
        s = QgsLayoutExporter.PrintExportSettings()
        s.dpi = dpi
        return _ok(exp.print(printer, s)), device
    finally:
        if prev is not None:
            QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_ctb', prev[0] or '')
            QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_lw', 1 if prev[1] is None else prev[1])


def render_preview(layout, ctb=None, lineweights=None, dpi=96):
    """Imagen de la primera hoja tal como se trazará (con el estilo de trazado elegido)."""
    scope = QgsExpressionContextUtils.layoutScope(layout)
    prev = (scope.variable('cad_ctb'), scope.variable('cad_lw'))
    set_style_vars(layout, ctb if ctb is not None else (prev[0] or ''),
                   lineweights if lineweights is not None else prev[1] != 0)
    try:
        exp = QgsLayoutExporter(layout)
        return exp.renderPageToImage(0, QSize(), dpi)
    finally:
        QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_ctb', prev[0] or '')
        QgsExpressionContextUtils.setLayoutVariable(layout, 'cad_lw', 1 if prev[1] is None else prev[1])


def preview(layout, ctb=None, lineweights=None):
    path = os.path.join(tempfile.gettempdir(), 'trazar_vista_previa.pdf')
    ok, _ = export(layout, 'PDF', path, 150, ctb, lineweights)
    if ok:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return ok


def printers():
    try:
        from qgis.PyQt.QtPrintSupport import QPrinterInfo
        return list(QPrinterInfo.availablePrinterNames())
    except Exception:  # noqa: BLE001
        return []
