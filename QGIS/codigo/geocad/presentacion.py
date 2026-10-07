# -*- coding: utf-8 -*-
"""GIS to CAD: la «presentación» de una capa que viaja a IngeCAD (3.0.0).

Con cada capa que se manda, va lo que QGIS muestra de ella:

* capa CAD de cada objeto (LAYER_CODE) y la tabla de capas del módulo Capas
  (color ACI, tipo de línea, grosor);
* color de cada objeto: CAD_COLOR si lo tiene (vacío = PorCapa); en capas
  sin Capas, el color con que la dibuja la simbología de QGIS;
* rótulos: el texto, la altura y el giro de las etiquetas tal como están
  configuradas en QGIS (Propiedades de la capa > Etiquetas). La altura en
  mm o puntos se pasa a unidades del mapa con la escala elegida en
  GeoCAD > Configuración común (0 = la escala del mapa al enviar), para que el
  texto guarde con el dibujo la misma relación de tamaño que en QGIS.

* símbolos (3.1.0): cada punto con la forma, el tamaño y el giro de su
  símbolo de QGIS; llega a IngeCAD como un bloque que ES el punto.
* fondo de las etiquetas (3.1.1): círculo, elipse, cuadrado o rectángulo
  del «Fondo» del formato de texto, con su tamaño, giro y color de borde.
* opciones elegidas al enviar (envio_ui.py): todos los rótulos o sólo los que
  QGIS muestra; tamaño real aunque supere la parcela o achicado hasta entrar.

Formato: ver INGECAD/codigo/geocad/estilo.py. Lo que no depende de QGIS
(unidades, ángulos, la tabla de Capas) está en funciones sueltas probadas.
"""
from __future__ import annotations

import json
import math

LAYER_FIELD = "LAYER_CODE"
COLOR_FIELD = "CAD_COLOR"
CAPAS_KEY = "cad_layer_manager/config"
TEXT_FLAG = "dibujo_cad/text_layer"

#: mm por unidad de tamaño de texto de QGIS
_MM = {"millimeters": 1.0, "points": 25.4 / 72, "pixels": 25.4 / 96, "inches": 25.4}


# -- funciones sueltas ----------------------------------------------------------------------

def unit_name(unit) -> str:
    """'millimeters', 'points', 'mapunits'... para el enum de QGIS 3 o 4."""
    name = getattr(unit, "name", None) or str(unit).rsplit(".", 1)[-1]
    name = name.lower()
    return name[len("render"):] if name.startswith("render") else name


def height_in_map(size: float, unit: str, scale: float) -> float:
    """Altura del texto en unidades del mapa (metros): en el papel a la escala
    ``scale`` mide lo mismo que en QGIS."""
    if unit in ("mapunits", "metersinmapunits"):
        return float(size)
    return float(size) * _MM.get(unit, 1.0) * float(scale) / 1000.0


def readable(angle_ccw: float) -> float:
    """Ángulo antihorario en (-90, 90]: el texto nunca queda cabeza abajo."""
    a = (angle_ccw + 180.0) % 360.0 - 180.0
    if a > 90.0:
        a -= 180.0
    elif a <= -90.0:
        a += 180.0
    return round(a, 6)


def azimuth_to_ccw(radians_from_north: float) -> float:
    """interpolateAngle de QGIS (radianes, horario desde el norte) -> grados
    antihorarios desde el este, como en CAD."""
    return 90.0 - math.degrees(radians_from_north)


def capas_table(raw) -> dict:
    """{código: {"color", "rgb", "tipo", "grosor"}} de la configuración que
    el módulo Capas guarda en la capa de QGIS."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    layers = data.get("layers", []) if isinstance(data, dict) else data
    out = {}
    for lay in layers if isinstance(layers, list) else []:
        if not isinstance(lay, dict) or not lay.get("name"):
            continue
        color = lay.get("color") if isinstance(lay.get("color"), dict) else {}
        name = str(lay["name"])
        out["" if name == "0" else name] = {
            "color": color.get("aci"), "rgb": color.get("rgb"),
            "tipo": lay.get("linetype") or "Continuous",
            "grosor": lay.get("lineweight", -1) if lay.get("lineweight") is not None else -1}
    return out


def _hex(qcolor) -> str:
    try:
        return qcolor.name().lower() if qcolor.isValid() else ""
    except Exception:
        return ""


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if value.isNull():                     # QVariant nulo
            return ""
    except AttributeError:
        pass
    return "" if str(value) == "NULL" else str(value)


# -- con QGIS --------------------------------------------------------------------------------

def _request(fids=None, bbox=None):
    from qgis.core import QgsFeatureRequest, QgsRectangle

    req = QgsFeatureRequest()
    if fids is not None:
        req.setFilterFids([int(f) for f in fids])
    elif bbox is not None:
        req.setFilterRect(QgsRectangle(*bbox))
    return req


def _label_settings(layer):
    """Las opciones de etiqueta de la capa (sólo etiquetas simples)."""
    try:
        if not layer.labelsEnabled():
            return None
        labeling = layer.labeling()
        if labeling is None:
            return None
        if hasattr(labeling, "settings"):
            return labeling.settings()
        root = labeling.rootRule()                # por reglas: la primera que rotula
        for rule in root.descendants():
            if rule.settings() is not None and rule.active():
                return rule.settings()
    except Exception:
        return None
    return None


def _prop(name):
    from qgis.core import QgsPalLayerSettings

    holder = getattr(QgsPalLayerSettings, "Property", QgsPalLayerSettings)
    return getattr(holder, name)


class _Labels:
    """Evalúa texto, altura y giro de las etiquetas de QGIS por objeto."""

    def __init__(self, layer, settings, scale, kind) -> None:
        from qgis.core import QgsExpression

        self.s = settings
        self.kind = kind
        self.props = settings.dataDefinedProperties()
        fmt = settings.format()
        self.unit = unit_name(fmt.sizeUnit())
        self.size = fmt.size()
        self.scale = scale
        self.color = _hex(fmt.color())
        expr = settings.fieldName or ""
        self.expr = QgsExpression(expr if settings.isExpression else QgsExpression.quotedColumnRef(expr))
        placement = unit_name(getattr(settings, "placement", ""))
        self.parallel = kind == "line" and placement in ("line", "curved", "perimetercurved")
        offset = 0.0
        for getter in (lambda: settings.angleOffset, lambda: settings.pointSettings().rotation()):
            try:
                offset = float(getter())
                break
            except Exception:
                continue
        self.offset = offset
        try:
            self.font = fmt.font()
        except Exception:
            self.font = None
        self.bg = _background(fmt, scale)

    def _dd(self, name, ctx, default):
        try:
            key = _prop(name)
            if not self.props.isActive(key):
                return default
            value, ok = self.props.valueAsDouble(key, ctx, 0.0)
            return float(value) if ok else default
        except Exception:
            return default

    def of(self, feature, ctx):
        """[texto, x, y, altura, giro, alineación, color] o None."""
        ctx.setFeature(feature)
        text = _text(self.expr.evaluate(ctx))
        geom = feature.geometry()
        if not text.strip() or geom is None or geom.isEmpty():
            return None
        size = self._dd("Size", ctx, self.size)
        height = height_in_map(size, self.unit, self.scale)
        rotation = self._dd("LabelRotation", ctx, None)
        align = "c"
        if self.kind == "point":
            p = geom.vertexAt(0)
            x, y = p.x() + height * 0.5, p.y()
            align = "i"
            angle = 0.0
        elif self.kind == "line":
            length = geom.length()
            p = geom.interpolate(length / 2.0).asPoint()
            x, y = p.x(), p.y()
            angle = readable(azimuth_to_ccw(geom.interpolateAngle(length / 2.0))) \
                if self.parallel else 0.0
        else:
            p = geom.pointOnSurface().asPoint()
            x, y = p.x(), p.y()
            angle = 0.0
        if rotation is not None:
            angle = -rotation                     # QGIS gira en sentido horario
        elif self.offset:
            angle = -self.offset
        out = [text, round(x, 6), round(y, 6), round(height, 6), round(angle, 6), align,
               self.color]
        if self.bg is not None:
            shape, size_type, sx, sy, rot_type, rot, color = self.bg
            w = text_width(text, height, self.font)
            W, H = background_size(shape, size_type, w, text_height(height, self.font), sx, sy)
            cx = x + w / 2.0 if align == "i" else x
            a = angle if rot_type == "sync" else angle - rot if rot_type == "offset" else -rot
            if W > 0 and H > 0:
                out.append([shape, round(cx, 6), round(y, 6), round(W, 6), round(H, 6),
                            round(a, 6), color])
        return out


def _enum(value, prefix, names) -> str:
    """'circle', 'buffer', 'sync'... del enum de QGIS 4 (con .name) o de
    QGIS 3 (un número: se compara con QgsTextBackgroundSettings.<Prefijo><Nombre>)."""
    from qgis.core import QgsTextBackgroundSettings as B

    for name in names:
        member = getattr(B, prefix + name.capitalize(), None)
        if member is None:
            member = getattr(B, prefix + name.upper(), None)
        if member is not None and (member is value or member == value):
            return name
    name = unit_name(value)
    return name[len(prefix.lower()):] if name.startswith(prefix.lower()) else name


def _background(fmt, scale):
    """(forma, tipo de tamaño, tamaño x, tamaño y en el mapa, tipo de giro,
    giro horario, color del borde) del fondo de la etiqueta, o None."""
    try:
        bg = fmt.background()
        if not bg.enabled():
            return None
        shape = _enum(bg.type(), "Shape", BG_SHAPES)
        if shape not in BG_SHAPES:
            return None
        size_type = _enum(bg.sizeType(), "Size", ("buffer", "fixed", "percent"))
        size = bg.size()
        if size_type == "percent":
            sx, sy = size.width(), size.height()
        else:
            unit = unit_name(bg.sizeUnit())
            sx, sy = height_in_map(size.width(), unit, scale), height_in_map(size.height(), unit, scale)
        rot_type = _enum(bg.rotationType(), "Rotation", ("sync", "offset", "fixed"))
        stroke = bg.strokeColor()
        if bg.strokeWidth() > 0 and stroke.isValid() and stroke.alpha() > 0:
            color = _hex(stroke)
        else:
            fill = bg.fillColor()
            if not (fill.isValid() and fill.alpha() > 0):
                return None                   # ni borde ni relleno: no se ve
            color = _hex(fill)
        return shape, size_type, float(sx), float(sy), rot_type, float(bg.rotation()), color
    except Exception:
        return None


def _kind(layer) -> str:
    try:
        from qgis.core import QgsWkbTypes

        g = QgsWkbTypes.geometryType(layer.wkbType())
        name = unit_name(g)
    except Exception:
        return "other"
    return {"pointgeometry": "point", "point": "point", "linegeometry": "line",
            "line": "line", "polygongeometry": "polygon", "polygon": "polygon"}.get(name, "other")


def _marker(symbol, ectx, scale):
    """[forma, tamaño en el mapa, giro antihorario] de un símbolo de punto."""
    try:
        from qgis.core import QgsMarkerSymbol

        if not isinstance(symbol, QgsMarkerSymbol):
            return None
    except ImportError:
        return None
    shape = "circle"
    for sl in symbol.symbolLayers():
        if hasattr(sl, "shape"):
            try:
                shape = unit_name(sl.shape())
                break
            except Exception:
                continue
    size, angle = symbol.size(), symbol.angle()
    for getter, default, attr in ((symbol.dataDefinedSize, size, "size"),
                                  (symbol.dataDefinedAngle, angle, "angle")):
        try:
            prop = getter()
            if prop.isActive():
                value, ok = prop.valueAsDouble(ectx, 0.0)
                if ok:
                    if attr == "size":
                        size = value
                    else:
                        angle = value
        except Exception:
            pass
    return [shape, round(height_in_map(size, unit_name(symbol.sizeUnit()), scale), 6),
            round(-angle, 6)]


def text_width(text: str, height: float, font=None) -> float:
    """Ancho aproximado de un texto de altura ``height`` (con la fuente de
    la etiqueta si se puede medir; si no, 0,6 de la altura por letra)."""
    if font is not None:
        try:
            from qgis.PyQt.QtGui import QFont, QFontMetricsF

            f = QFont(font)
            f.setPixelSize(100)
            return QFontMetricsF(f).horizontalAdvance(text) / 100.0 * height
        except Exception:
            pass
    return 0.6 * height * len(text)


def text_height(height: float, font=None) -> float:
    """Alto de la caja del texto (ascendentes y descendentes) para una
    letra de altura ``height``; sin fuente, la altura misma."""
    if font is not None:
        try:
            from qgis.PyQt.QtGui import QFont, QFontMetricsF

            f = QFont(font)
            f.setPixelSize(100)
            return QFontMetricsF(f).height() / 100.0 * height
        except Exception:
            pass
    return float(height)


#: formas de fondo de etiqueta que se dibujan en IngeCAD
BG_SHAPES = ("rectangle", "square", "ellipse", "circle")


def background_size(shape: str, size_type: str, w: float, h: float,
                    sx: float = 0.0, sy: float = 0.0):
    """(ancho, alto) del fondo de una etiqueta de QGIS alrededor de un texto
    de ``w`` x ``h``, como lo calcula QGIS: «buffer» suma ``sx``/``sy`` a cada
    lado; «fixed» usa ``sx`` x ``sy``; «percent» agranda el texto en %."""
    if size_type == "fixed" and (sx > 0 or sy > 0):
        W, H = (sx or sy), (sy or sx)
        if shape in ("square", "circle"):
            W = H = max(W, H)
        return W, H
    if shape == "square":
        w = h = max(w, h)
    elif shape == "circle":
        w = h = math.hypot(w, h)              # el círculo que encierra el texto
    elif shape == "ellipse":
        w, h = w * math.sqrt(2.0), h * math.sqrt(2.0)
    if size_type == "percent":
        return w * (1.0 + sx / 100.0), h * (1.0 + (sy or sx) / 100.0)
    if size_type == "fixed":
        return w, h
    return w + 2.0 * sx, h + 2.0 * sy


def box(cx, cy, w, h, angle_ccw, align="c"):
    """Los 4 vértices del rectángulo de un texto o símbolo."""
    x0 = 0.0 if align == "i" else -w / 2.0
    a = math.radians(angle_ccw)
    ca, sa = math.cos(a), math.sin(a)
    corners = [(x0, -h / 2.0), (x0 + w, -h / 2.0), (x0 + w, h / 2.0), (x0, h / 2.0)]
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in corners]


def fit_factor(inside, cx, cy, w, h, angle_ccw, align="c", minimum=0.1) -> float:
    """Cuánto achicar (1 = nada) para que el rectángulo entre en la parcela.
    ``inside(puntos)`` dice si un polígono de 4 vértices queda adentro."""
    f = 1.0
    while f >= minimum:
        if inside(box(cx, cy, w * f, h * f, angle_ccw, align)):
            return round(f, 6)
        f *= 0.85
    return minimum


class Parcels:
    """Las parcelas (polígonos de las capas visibles) donde cae un punto."""

    def __init__(self, layers) -> None:
        self.layers = [lyr for lyr in layers if _kind(lyr) == "polygon"]

    def containing(self, layer, x, y):
        from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle

        pt = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        for lyr in self.layers:
            try:
                if lyr.crs().authid() != layer.crs().authid():
                    continue
            except Exception:
                pass
            req = QgsFeatureRequest().setFilterRect(QgsRectangle(x, y, x, y))
            for f in lyr.getFeatures(req):
                g = f.geometry()
                if g is not None and not g.isEmpty() and g.contains(pt):
                    return g
        return None


def _inside(geom):
    from qgis.core import QgsGeometry, QgsPointXY

    def test(points):
        ring = [QgsPointXY(x, y) for x, y in points] + [QgsPointXY(*points[0])]
        return geom.contains(QgsGeometry.fromPolygonXY([ring]))
    return test


def _inside_rect(rect, x, y) -> bool:
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def visible_labels(canvas=None, map_settings=None):
    """{id de capa: {fids}} de las etiquetas que QGIS dibuja en la vista
    (las que no entran o chocan con otras no están). None si no se sabe."""
    results = None
    if canvas is not None:
        try:
            results = canvas.labelingResults()
        except Exception:
            results = None
    if results is None and map_settings is not None:
        from qgis.core import QgsMapRendererSequentialJob

        job = QgsMapRendererSequentialJob(map_settings)
        job.start()
        job.waitForFinished()
        results = job.takeLabelingResults()
    if results is None:
        return None
    out: dict = {}
    for pos in results.allLabels():
        if getattr(pos, "isUnplaced", False):
            continue
        out.setdefault(pos.layerID, set()).add(int(pos.featureId))
    return out


def tiles(extent, tile_w: float, tile_h: float, overlap: float = 0.2, limit: int = 400):
    """Tramos (xmin, ymin, xmax, ymax) del tamaño de la pantalla que cubren
    ``extent``, superpuestos ``overlap`` para que ningún rótulo quede partido
    entre dos. None si harían falta más de ``limit``."""
    x0, y0, x1, y1 = extent
    if tile_w <= 0 or tile_h <= 0:
        return None
    step_x, step_y = tile_w * (1.0 - overlap), tile_h * (1.0 - overlap)
    nx = max(1, math.ceil(max(x1 - x0 - tile_w, 0.0) / step_x) + 1)
    ny = max(1, math.ceil(max(y1 - y0 - tile_h, 0.0) / step_y) + 1)
    if nx * ny > limit:
        return None
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    ox = cx - ((nx - 1) * step_x + tile_w) / 2.0      # centrados sobre la zona
    oy = cy - ((ny - 1) * step_y + tile_h) / 2.0
    return [(ox + i * step_x, oy + j * step_y, ox + i * step_x + tile_w, oy + j * step_y + tile_h)
            for j in range(ny) for i in range(nx)]


def visible_labels_zone(map_settings, extent, scale: float = 0.0, limit: int = 400):
    """Como visible_labels, pero en toda ``extent`` (coordenadas del mapa) y a
    ``scale`` (0 = la de ``map_settings``): QGIS dibuja las etiquetas por
    tramos del tamaño de la pantalla y se juntan las que ubica en alguno.
    None si la zona es demasiado grande para ``limit`` tramos."""
    from qgis.core import QgsMapSettings, QgsRectangle, QgsVectorLayer

    view = map_settings.visibleExtent()
    base = QgsMapSettings(map_settings)           # sin fondos: sólo lo que rotula o tapa
    base.setLayers([lyr for lyr in map_settings.layers() if isinstance(lyr, QgsVectorLayer)])
    k = (scale / map_settings.scale()) if scale and map_settings.scale() else 1.0
    parts = tiles(extent, view.width() * k, view.height() * k, limit=limit)
    if parts is None:
        return None
    out: dict = {}
    for part in parts:
        ms = QgsMapSettings(base)
        ms.setExtent(QgsRectangle(*part))
        got = visible_labels(None, ms) or {}
        for layer_id, fids in got.items():
            out.setdefault(layer_id, set()).update(fids)
    return out


def of_layer(layer, map_settings=None, scale: float = 0.0, fids=None, bbox=None,
             with_style: bool = True, with_labels: bool = True, with_symbols: bool = False,
             shown=None, parcels=None, screen=None) -> dict:
    """La presentación de ``layer`` para los objetos que se mandan.

    ``with_symbols``: los puntos van con su símbolo (forma, tamaño, giro).
    ``shown``: sólo los rótulos de esos fids (los que QGIS muestra); None = todos.
    ``screen``: (xmin, ymin, xmax, ymax) en coordenadas de la capa; con ``shown``,
    los rótulos que caen fuera de ese rectángulo van siempre (3.4.0).
    ``parcels``: un Parcels para achicar rótulos y símbolos hasta que entren
    en su parcela; None = tamaño real aunque la superen."""
    from qgis.core import QgsExpressionContext, QgsExpressionContextUtils, QgsRenderContext

    out: dict = {}
    scale = scale or 1000.0
    fields = layer.fields()
    has = lambda n: fields.indexOf(n) != -1            # noqa: E731
    managed = bool(layer.customProperty(CAPAS_KEY)) and has(LAYER_FIELD)
    kind = _kind(layer)
    if layer.customProperty(TEXT_FLAG) == "1":
        with_style = with_labels = with_symbols = False  # capa de textos de Dibujo CAD
    with_symbols = with_symbols and kind == "point"
    if with_style:
        out["campo_capa"] = LAYER_FIELD if has(LAYER_FIELD) else ""
        out["campo_color"] = COLOR_FIELD if has(COLOR_FIELD) else ""
        if managed:
            out["capas"] = capas_table(layer.customProperty(CAPAS_KEY))
        out["objetos"] = {}
    settings = _label_settings(layer) if with_labels else None
    if not with_style and settings is None and not with_symbols:
        return {}
    ctx = QgsRenderContext.fromMapSettings(map_settings) if map_settings is not None \
        else QgsRenderContext()
    ectx = QgsExpressionContext()
    ectx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    ctx.setExpressionContext(ectx)
    color_from_renderer = with_style and not managed and not has(COLOR_FIELD)
    renderer = None
    if (color_from_renderer or with_symbols) and layer.renderer() is not None:
        renderer = layer.renderer().clone()
        renderer.startRender(ctx, fields)
    labels = None
    if settings is not None:
        try:
            labels = _Labels(layer, settings, scale, kind)
            out["rotulos"] = {}
        except Exception:
            labels = None
    if with_symbols:
        out["simbolos"] = {}
    font = None
    if labels is not None:
        try:
            font = settings.format().font()
        except Exception:
            font = None
    try:
        for f in layer.getFeatures(_request(fids, bbox)):
            fid = str(f.id())
            ctx.expressionContext().setFeature(f)
            symbols = []
            if renderer is not None:
                try:
                    symbols = renderer.symbolsForFeature(f, ctx)
                except Exception:
                    symbols = []
            if with_style:
                code = _text(f[LAYER_FIELD]) if has(LAYER_FIELD) else ""
                color = _text(f[COLOR_FIELD]) if has(COLOR_FIELD) else ""
                if color_from_renderer:
                    color = _hex(symbols[0].color()) if symbols else ""
                out["objetos"][fid] = ["" if code == "0" else code, color]
            sym = _marker(symbols[0], ctx.expressionContext(), scale) \
                if (with_symbols and symbols) else None
            own = None
            if parcels is not None:
                p = f.geometry().vertexAt(0) if kind == "point" else None
                own = f.geometry() if kind == "polygon" else \
                    (parcels.containing(layer, p.x(), p.y()) if p is not None else None)
            if sym is not None:
                if own is not None and sym[1] > 0:
                    p = f.geometry().vertexAt(0)
                    k = fit_factor(_inside(own), p.x(), p.y(), sym[1], sym[1], sym[2])
                    sym[1] = round(sym[1] * k, 6)
                out["simbolos"][fid] = sym
            if labels is not None:
                got = labels.of(f, ctx.expressionContext())
                if got is not None and shown is not None and f.id() not in shown and \
                        (screen is None or _inside_rect(screen, got[1], got[2])):
                    got = None                            # QGIS no lo muestra en pantalla
                if got is not None:
                    bg = got[7] if len(got) > 7 else None
                    if sym is not None and got[5] == "i":      # al costado del símbolo
                        got[1] = round(got[1] + sym[1] / 2.0, 6)
                        if bg is not None:
                            bg[1] = round(bg[1] + sym[1] / 2.0, 6)
                    if parcels is not None:
                        own_l = own if kind != "line" else \
                            parcels.containing(layer, got[1], got[2])
                        if own_l is not None:
                            if bg is not None:              # el fondo encierra al texto
                                k = fit_factor(_inside(own_l), bg[1], bg[2], bg[3], bg[4],
                                               bg[5], "c")
                            else:
                                w = text_width(got[0], got[3], font)
                                k = fit_factor(_inside(own_l), got[1], got[2], w, got[3],
                                               got[4], got[5])
                            got[3] = round(got[3] * k, 6)
                            if bg is not None:
                                bg[1] = round(got[1] + (bg[1] - got[1]) * k, 6)
                                bg[3], bg[4] = round(bg[3] * k, 6), round(bg[4] * k, 6)
                    out["rotulos"][fid] = got
    finally:
        if renderer is not None:
            renderer.stopRender(ctx)
    return out
