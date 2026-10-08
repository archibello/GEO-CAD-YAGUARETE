# SPDX-License-Identifier: GPL-3.0-or-later
"""Cotas para el papel (3.9.0).

IngeCAD ya trae las órdenes de acotar (DIMLINEAR, DIMALIGNED, DIMANGULAR...)
y el administrador de estilos. Lo que falta es lo de todos los días: elegir
la escala del papel y la altura del texto en milímetros de hoja, y que cada
cota caiga sola en su capa.

1. CREAR COTA (GEODIMSETUP): escala del papel, letra, altura en mm de hoja,
   decimales y cabecera. Arma el estilo «Acot-100-6mm» (el DXF no admite
   «:» en los nombres) y lo deja activo; si ya existe, lo actualiza.
2. MEDIR: los botones lanzan las órdenes de IngeCAD tal cual.
3. Ángulos en grados, minutos y segundos por defecto (o grados decimales).
4. DIMANGULAR muestra la cota entera (arco, cabeceras y texto) mientras se
   elige dónde va el arco, como ya hacen la lineal y la alineada.
5. DIMANGULAR (3.9.2): los lados se resaltan con colores temporales (azul
   el primero, verde el segundo), el centro queda marcado con una X desde
   que se conoce hasta el final, el cursor dice «Interior 45°0'0"» o
   «Exterior 315°0'0"», y con dos líneas se mide el interior o el exterior
   según el lado del cursor (IngeCAD sólo medía hasta 180°). Acepta tramos
   rectos de polilíneas (los lotes de QGIS) y suma referencias (FIN, INT,
   CEN, MED) al pedir el vértice y los puntos.
6. Precisión de los ángulos en g/m/s como AutoCAD (3.9.3): la lista 0°,
   0°00', 0°00'00", 0°00'00.0"... en CREAR COTA y en la ventana de estilos
   de IngeCAD (allí era un número suelto), y el texto con esa precisión
   (ezdxf no ponía los decimales de los segundos o los rellenaba con ceros).
7. Toda cota hecha con un estilo «Acot-<escala>-<altura>mm» cae en la capa
   «COTAS Acot-<escala>-<altura>mm» (gris 8, línea fina), que se crea si
   falta. La capa actual no cambia. La opción Capa de DIM manda sobre esto.

Cuentas: el dibujo está en metros (o en lo que diga $INSUNITS). Las medidas
del estilo se escriben en mm de hoja × unidades por mm, y DIMSCALE = escala:
6 mm a 1:100 en metros = 0,006 × 100 = 0,60 m de alto en el modelo.

Python puro: las ventanas están en cotas_ui.py.
"""
from __future__ import annotations

import math
import re

from . import modulos

PROGRAMA = "ingecad"

#: Cabeceras del boceto -> bloque de flecha de AutoCAD ("" = flecha llena).
CABECERAS = (("oblicuo", "Trazo oblicuo", "ARCHTICK"),
             ("punto", "Punto", "DOT"),
             ("flecha", "Flecha", ""))

#: Letras que se ofrecen (nombre visible, archivo como lo guarda AutoCAD).
FUENTES = (("Arial Black", "ariblk.ttf"),
           ("Arial", "arial.ttf"),
           ("Arial negrita", "arialbd.ttf"),
           ("Liberation Sans", "LiberationSans.ttf"),
           ("ISOCP (de AutoCAD)", "isocp.shx"),
           ("Simplex (de AutoCAD)", "simplex.shx"))

#: Formato de los ángulos -> DIMAUNIT (0 grados decimales, 1 g/m/s).
ANGULOS = (("gms", "Grados, minutos y segundos", 1),
           ("decimal", "Grados decimales", 0))

#: Precisión de g/m/s como la lista de AutoCAD -> DIMADEC (la regla de
#: angtos: 0-1 grados, 2-3 minutos, 4 segundos, 5-8 decimales de segundo).
PRECISION_GMS = (("0°", 0), ("0°00'", 2), ("0°00'00\"", 4), ("0°00'00.0\"", 5),
                 ("0°00'00.00\"", 6), ("0°00'00.000\"", 7), ("0°00'00.0000\"", 8))
PRECISION_GMS_DEFECTO = 4

COLOR_CAPA = 8            # gris oscuro
GROSOR_CAPA = 15          # 0,15 mm (centésimas de mm, como el DXF)
#: Milímetros por unidad, según $INSUNITS (4 mm, 5 cm, 6 m, 7 km).
MM_POR_UNIDAD = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 7: 1e6}
#: Sin unidad declarada se toma metros: así dibuja Fernando y así llega de QGIS.
MM_POR_DEFECTO = 1000.0

_PATRON = re.compile(r"^Acot-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)mm(?:-(\d+)d)?$")


def activo() -> bool:
    return modulos.activo(PROGRAMA, "cotas")


# ---------------------------------------------------------------- nombres
def _num(valor: float) -> str:
    """100 -> «100», 2.5 -> «2.5» (sin ceros de más)."""
    texto = f"{float(valor):.4f}".rstrip("0").rstrip(".")
    return texto or "0"


def nombre_estilo(escala: float, altura_mm: float, decimales: int = 0) -> str:
    """«Acot-100-6mm»; con decimales, «Acot-100-6mm-2d»."""
    nombre = f"Acot-{_num(escala)}-{_num(altura_mm)}mm"
    return nombre + (f"-{int(decimales)}d" if decimales else "")


def nombre_capa(estilo: str) -> str:
    return f"COTAS {estilo}"


def es_nuestro(estilo: str) -> bool:
    """Un estilo armado por CREAR COTA (los «Acot-100» de IngeCAD no)."""
    return bool(_PATRON.match(estilo or ""))


def leer_nombre(estilo: str):
    """«Acot-100-6mm-2d» -> (100.0, 6.0, 2); None si no es nuestro."""
    m = _PATRON.match(estilo or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), int(m.group(3) or 0)


def parse_escala(texto: str):
    """«1:100», «1/100» o «100» -> 100.0; None si no se entiende."""
    t = (texto or "").strip().replace(",", ".").replace(" ", "")
    m = re.fullmatch(r"(?:1[:/])?(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    valor = float(m.group(1))
    return valor if valor > 0 else None


# ---------------------------------------------------------------- cuentas
def unidades_por_mm(document) -> float:
    """Unidades del dibujo en un milímetro: 0,001 con el dibujo en metros."""
    try:
        insunits = int(document.doc.header.get("$INSUNITS", 0))
    except Exception:  # noqa: BLE001
        insunits = 0
    return 1.0 / MM_POR_UNIDAD.get(insunits, MM_POR_DEFECTO)


def nombre_texto(fuente: str) -> str:
    """Estilo de texto de la letra: «Acot-ariblk»."""
    return "Acot-" + fuente.rsplit(".", 1)[0]


def atributos(document, escala: float, altura_mm: float, decimales: int,
              cabecera: str, fuente: str, angulos: str = "gms",
              precision_gms: int = PRECISION_GMS_DEFECTO) -> dict:
    """Las variables del estilo de cota, sobre el ISO-25 de IngeCAD."""
    from core import styles

    upm = unidades_por_mm(document)
    attribs = styles.iso25_for(upm)
    bloque = dict((c, b) for c, _, b in CABECERAS).get(cabecera, "ARCHTICK")
    attribs.update({
        "dimscale": float(escala),
        "dimtxt": float(altura_mm) * upm,
        "dimgap": float(altura_mm) / 4.0 * upm,
        "dimdec": int(decimales),
        # g/m/s: DIMADEC 4 = 45°30'15" (0 = sólo grados, 2 = grados y minutos)
        "dimaunit": 1 if angulos == "gms" else 0,
        "dimadec": int(precision_gms) if angulos == "gms" else int(decimales),
        "dimazin": 2,                 # sin ceros de relleno en los segundos
        "dimdsep": ord(","),
        "dimsah": 1,
        "dimblk": bloque, "dimblk1": bloque, "dimblk2": bloque,
        "dimtxsty": nombre_texto(fuente),
    })
    return attribs


# ---------------------------------------------------------------- CREAR COTA
def comando_crear(document, escala: float, altura_mm: float, decimales: int,
                  cabecera: str, fuente: str, angulos: str = "gms",
                  precision_gms: int = PRECISION_GMS_DEFECTO):
    """La orden (se deshace con U) que arma o actualiza el estilo, su letra y
    su capa, y lo deja activo. Devuelve (orden, nombre del estilo)."""
    from core import layers, styles
    from core.commands import CompositeCommand

    doc = document.doc
    nombre = nombre_estilo(escala, altura_mm, decimales)
    texto = nombre_texto(fuente)
    pasos = []
    if texto not in doc.styles:
        pasos.append(styles.NewTextStyleCommand(texto, {"font": fuente, "height": 0.0}))
    attribs = atributos(document, escala, altura_mm, decimales, cabecera, fuente,
                        angulos, precision_gms)
    if nombre in doc.dimstyles:
        pasos.append(styles.SetDimStylePropsCommand(nombre, attribs))
    else:
        pasos.append(styles.NewDimStyleCommand(nombre, attribs))
    capa = nombre_capa(nombre)
    if capa not in doc.layers:
        pasos.append(layers.NewLayerCommand(capa, color=COLOR_CAPA,
                                            lineweight=GROSOR_CAPA))
    pasos.append(styles.SetCurrentDimStyleCommand(nombre))
    return CompositeCommand("GEODIMSETUP", pasos), nombre


def ultimos(document) -> dict:
    """Lo que la ventana propone: el estilo activo si es nuestro."""
    valores = {"escala": 100.0, "altura": 2.5, "decimales": 0,
               "cabecera": "oblicuo", "fuente": "arial.ttf", "angulos": "gms",
               "precision_gms": PRECISION_GMS_DEFECTO}
    try:
        actual = document.doc.header.get("$DIMSTYLE", "")
        leido = leer_nombre(actual)
        if leido is None:
            return valores
        valores["escala"], valores["altura"], valores["decimales"] = leido
        estilo = document.doc.dimstyles.get(actual)
        bloque = estilo.dxf.get("dimblk1", estilo.dxf.get("dimblk", ""))
        for clave, _, b in CABECERAS:
            if b.upper() == str(bloque).lstrip("_").upper():
                valores["cabecera"] = clave
        if int(estilo.dxf.get("dimaunit", 0)) == 0:
            valores["angulos"] = "decimal"
        else:
            valores["precision_gms"] = codigo_gms(int(estilo.dxf.get("dimadec", 4)))
        texto = estilo.dxf.get("dimtxsty", "")
        if texto in document.doc.styles:
            valores["fuente"] = document.doc.styles.get(texto).dxf.get("font", valores["fuente"])
    except Exception:  # noqa: BLE001
        pass
    return valores


def cmd_crear(ctx, *args) -> None:
    """CREAR COTA (GEODIMSETUP): la ventana; sin Qt, avisa."""
    try:
        from . import cotas_ui
    except Exception:  # noqa: BLE001
        ctx.echo("CREAR COTA necesita la ventana de IngeCAD.")
        return
    cotas_ui.crear_cota(ctx)


# ---------------------------------------------------------------- capa automática
def capa_para(document, estilo: str):
    """La capa de un estilo nuestro, creada si falta; None si no es nuestro."""
    if not es_nuestro(estilo):
        return None
    capa = nombre_capa(estilo)
    capas = document.doc.layers
    if capa not in capas:
        capas.add(capa, color=COLOR_CAPA, lineweight=GROSOR_CAPA)
    return capa


def _envolver_cota_do(original):
    def do(self, document):
        if activo() and getattr(self, "layer", None) is None:
            try:
                estilo = document.doc.header.get("$DIMSTYLE", "")
                self.layer = capa_para(document, estilo)
            except Exception:  # noqa: BLE001
                pass
        return original(self, document)
    do._puente_original = original
    do._puente_fabrica = _envolver_cota_do
    return do


# ---------------------------------------------------------------- DIMANGULAR en vivo
def comando_angular(tool, point):
    """La misma orden que dejaría el clic de DIMANGULAR en ``point`` (copia
    de su on_point al ubicar el arco), sin ejecutarla; None si todavía no
    se está ubicando el arco."""
    if getattr(tool, "_mode", None) != "locate" or getattr(tool, "_pending", None) is not None:
        return None
    from core import actions

    texto = dict(text=getattr(tool, "_text", None) or "<>",
                 text_rotation=getattr(tool, "_text_rotation", None))
    cuadrante = getattr(tool, "_quadrant", None)
    region = cuadrante if cuadrante is not None else point
    if getattr(tool, "_line2", None) is not None:
        res = actions.angular_from_lines(tool._line1, tool._line2, region)
        if res is None:
            return None
        vertice, p1, p2 = res
        return actions.dim_angular(vertice, p1, p2, point, **texto)
    if getattr(tool, "_vertex", None) is None or tool._p1 is None or tool._p2 is None:
        return None
    return actions.dim_angular(tool._vertex, tool._p1, tool._p2, point,
                               region=region if tool._region_free else None, **texto)


def _vista_angular(self, cursor):
    """preview_command de DIMANGULAR: IngeCAD dibuja la cota que va a quedar.
    Con el módulo apagado no hay vista previa, como venía."""
    if not activo():
        return None
    try:
        return comando_angular(self, cursor)
    except Exception:  # noqa: BLE001
        return None
_vista_angular._puente_fabrica = "cotas"


def _envolver_segmentos(original):
    def preview_segments(self, cursor):
        if activo() and getattr(self, "_mode", None) == "locate":
            return []                 # la cota misma ya se ve: sin la línea suelta
        return original(self, cursor)
    preview_segments._puente_original = original
    preview_segments._puente_fabrica = _envolver_segmentos
    return preview_segments


# ---------------------------------------------------------------- DIMANGULAR: lados, centro, interior/exterior
#: Referencias que se suman al pedir el vértice y los puntos (respetan F3).
REFERENCIAS_ANGULO = frozenset({"END", "INT", "CEN", "MID"})
_MODOS_PUNTO = ("vertex", "vp1", "vp2", "circle2", "locate")


def tramo(entity, pick):
    """La línea o el tramo recto de polilínea bajo ``pick``: ((x, y), (x, y)),
    o None (arco, tramo curvo u otro objeto)."""
    if entity is None:
        return None
    tipo = entity.dxftype()
    if tipo == "LINE":
        a, b = entity.dxf.start, entity.dxf.end
        return ((a.x, a.y), (b.x, b.y))
    if tipo in ("LWPOLYLINE", "POLYLINE"):
        from .empalme import trazo
        try:
            segs = trazo(entity, pick)
        except Exception:  # noqa: BLE001
            return None
        if len(segs) == 1:
            (ax, ay), (bx, by) = segs[0]
            return ((ax, ay), (bx, by))
    return None


def lados(l1, l2):
    """(vértice, p1, p2) de dos líneas: el cruce y, en cada una, su punta más
    lejana del cruce (el lado del ángulo). None si son paralelas."""
    from core import actions

    v = actions.line_intersection(l1, l2)
    if v is None:
        return None

    def lejos(linea):
        return max(linea, key=lambda q: (q[0] - v[0]) ** 2 + (q[1] - v[1]) ** 2)
    return (v[0], v[1]), tuple(lejos(l1)), tuple(lejos(l2))


def formato_angulo(document, grados: float) -> str:
    """Como lo escribe el estilo activo: 45°30'15" (g/m/s) o 45,50°."""
    gms, dec = True, PRECISION_GMS_DEFECTO
    try:
        estilo = document.doc.dimstyles.get(document.doc.header.get("$DIMSTYLE", ""))
        gms = int(estilo.dxf.get("dimaunit", 0)) == 1
        dec = int(estilo.dxf.get("dimadec", dec))
    except Exception:  # noqa: BLE001
        pass
    if not gms:
        return f"{grados:.{max(0, dec)}f}°".replace(".", ",")
    return texto_gms(grados, dec, ",", sin_ceros=True)


def codigo_gms(dimadec: int) -> int:
    """El renglón de la lista de AutoCAD que corresponde a un DIMADEC."""
    codigos = [c for _, c in PRECISION_GMS]
    return max(c for c in codigos if c <= max(0, min(8, int(dimadec))))


def texto_gms(grados: float, dimadec: int, separador: str = ",",
              sin_ceros: bool = False) -> str:
    """45.5042 -> 45°30'15" con la precisión de DIMADEC (regla de AutoCAD).
    Se redondea una sola vez, en la última unidad: 59,99" no queda 60".
    Un ángulo entero (ya redondeado) va sólo en grados: 90°, no 90°00'00"."""
    signo = "-" if grados < 0 else ""
    g = abs(grados)
    if dimadec < 2:
        return f"{signo}{int(round(g))}°"
    if dimadec < 4:
        d, m = divmod(int(round(g * 60.0)), 60)
        return f"{signo}{d}°" if m == 0 else f"{signo}{d}°{m:02d}'"
    lugares = min(4, max(0, dimadec - 4))
    escala = 10 ** lugares
    d, resto = divmod(int(round(g * 3600.0 * escala)), 3600 * escala)
    m, seg = divmod(resto, 60 * escala)
    if m == 0 and seg == 0:
        return f"{signo}{d}°"
    entero, frac = divmod(seg, escala)
    texto = f"{entero:02d}"
    if lugares:
        decimales = f"{frac:0{lugares}d}"
        if sin_ceros:
            decimales = decimales.rstrip("0")
        if decimales:
            texto += separador + decimales
    return f"{signo}{d}°{m:02d}'{texto}\""


def _envolver_formato(original):
    """ezdxf escribe los g/m/s de las cotas: con el módulo prendido, con la
    precisión de AutoCAD y sin ceros de relleno (DIMAZIN)."""
    def format_angular_text(value, angle_units, dimrnd, dimdec, dimzin, dimdsep):
        if activo() and angle_units == 1:
            try:
                return texto_gms(math.degrees(value), int(dimdec), dimdsep or ",",
                                 sin_ceros=bool(int(dimzin) & 8))
            except Exception:  # noqa: BLE001
                pass
        return original(value, angle_units, dimrnd, dimdec, dimzin, dimdsep)
    format_angular_text._puente_original = original
    format_angular_text._puente_fabrica = _envolver_formato
    return format_angular_text


def _envolver_editor_estilo(original):
    """La ventana de estilos de IngeCAD: con g/m/s, Precision es la lista de
    AutoCAD (0°, 0°00', 0°00'00"...) en vez de un número suelto."""
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not activo():
            return
        try:
            _lista_precision(self)
        except Exception:  # noqa: BLE001 -- la ventana sigue como venía
            pass
    __init__._puente_original = original
    __init__._puente_fabrica = _envolver_editor_estilo
    return __init__


def _lista_precision(dlg) -> None:
    """Junto al número de IngeCAD (que sigue guardando el valor), la lista
    de AutoCAD; con g/m/s se ve la lista, con otro formato el número."""
    from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

    spin, unidades = dlg.dimadec, dlg.dimaunit
    layout = spin.parentWidget().layout()
    fila, _rol = layout.getWidgetPosition(spin)
    lista = QComboBox()
    for texto, codigo in PRECISION_GMS:
        lista.addItem(texto.replace(".", ","), codigo)
    caja = QWidget()
    h = QHBoxLayout(caja)
    h.setContentsMargins(0, 0, 0, 0)
    layout.removeWidget(spin)
    h.addWidget(spin)
    h.addWidget(lista)
    layout.setWidget(fila, layout.ItemRole.FieldRole, caja)
    lista.currentIndexChanged.connect(lambda _i: spin.setValue(lista.currentData()))

    def mostrar(*_):
        gms = unidades.currentData() == 1
        if gms:
            lista.setCurrentIndex(lista.findData(codigo_gms(spin.value())))
        lista.setVisible(gms)
        spin.setVisible(not gms)
    unidades.currentIndexChanged.connect(mostrar)
    mostrar()
    dlg._geocad_precision = lista


def _a_vertice(tool) -> None:
    """Dos líneas elegidas -> vértice y dos puntos: así el lado del cursor
    elige interior o exterior, como en el modo vértice de IngeCAD."""
    r = lados(tool._line1, tool._line2)
    if r is None:
        return
    tool._geo_lineas = (tool._line1, tool._line2)
    tool._vertex, tool._p1, tool._p2 = r
    tool._region_free = True
    tool._line1 = tool._line2 = None


def _envolver_on_point(original):
    def on_point(self, point):
        modo = getattr(self, "_mode", None)
        if (not activo() or getattr(self, "_pending", None) is not None
                or modo not in ("select", "line2")):
            return original(self, point)
        if modo == "select":
            self._geo_lineas = None
        s = getattr(self.ctx, "services", None)
        e = s.pick_entity(point) if s is not None else None
        if e is not None and e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
            t = tramo(e, point)
            if t is None:
                self.ctx.echo("Elija un tramo recto de la polilínea.")
                return None
            if modo == "select":
                self._line1 = t
                self._mode = "line2"
                self.prompt("Select second line:")
                return None
            if lados(self._line1, t) is None:
                self.ctx.echo("Las líneas son paralelas.")
                return None
            self._line2 = t
            self._to_locate()
        else:
            original(self, point)
        if getattr(self, "_mode", None) == "locate" and getattr(self, "_line2", None) is not None:
            _a_vertice(self)
        return None
    on_point._puente_original = original
    on_point._puente_fabrica = _envolver_on_point
    return on_point


def _referencias_angulo(self) -> frozenset:
    if activo() and getattr(self, "_mode", None) in _MODOS_PUNTO:
        return REFERENCIAS_ANGULO
    return frozenset()
_referencias_angulo._puente_fabrica = "cotas"


def resaltado_angular(self, cursor) -> dict:
    """Lo que DIMANGULAR pinta con colores temporales (lo dibuja dibujo.py):
    el lado bajo el cursor, el primer lado en azul y el segundo en verde, el
    centro con una X y, al ubicar el arco, «Interior …» o «Exterior …»."""
    out = {"cursor": [], "pieza_a": [], "pieza_b": [], "puntos": [], "textos": []}
    if not activo() or cursor is None:
        return out
    from core import actions

    modo = getattr(self, "_mode", None)
    ctx = getattr(self, "ctx", None)
    s = getattr(ctx, "services", None)

    def bajo_cursor():
        try:
            return tramo(s.pick_entity(cursor), cursor) if s is not None else None
        except Exception:  # noqa: BLE001
            return None

    v = getattr(self, "_vertex", None)
    if modo == "select":
        t = bajo_cursor()
        if t is not None:
            out["cursor"] = [t]
    elif modo == "line2":
        out["pieza_a"] = [self._line1]
        t = bajo_cursor()
        if t is not None:
            out["cursor"] = [t]
            r = lados(self._line1, t)
            if r is not None:
                out["puntos"] = [r[0]]             # el centro, antes del clic
    elif modo in ("vp1", "vp2", "circle2") and v is not None:
        out["puntos"] = [v]
        if modo != "vp1" and getattr(self, "_p1", None) is not None:
            out["pieza_a"] = [(v, self._p1)]
        out["pieza_b"] = [(v, cursor)] if modo != "vp1" else []
        if modo == "vp1":
            out["pieza_a"] = [(v, cursor)]
    elif modo == "locate" and v is not None:
        p1, p2 = self._p1, self._p2
        lineas = getattr(self, "_geo_lineas", None)
        out["pieza_a"] = ([lineas[0]] if lineas else []) + [(v, p1)]
        out["pieza_b"] = ([lineas[1]] if lineas else []) + [(v, p2)]
        out["puntos"] = [v]
        cuadrante = getattr(self, "_quadrant", None)
        region = cuadrante if cuadrante is not None else cursor
        a, b = (actions.angular_points(v, p1, p2, region)
                if getattr(self, "_region_free", True) else (p1, p2))
        try:
            grados = actions.angular_measurement(v, a, b)
            doc = getattr(ctx, "document", None)
            tipo = "Interior" if grados <= 180.0 + 1e-9 else "Exterior"
            out["textos"] = [(cursor, f"{tipo} {formato_angulo(doc, grados)}")]
        except Exception:  # noqa: BLE001
            pass
    return out
resaltado_angular._puente_fabrica = "cotas"


def instalar() -> None:
    """Se llama al cargar el plugin. Los envoltorios miran ``activo()`` en
    cada llamada: prender o apagar el módulo no necesita reinstalarlos."""
    from .dibujo import envolver
    try:
        from core.actions import AddDimensionCommand
    except Exception:  # noqa: BLE001
        return
    if getattr(AddDimensionCommand.do, "_puente_fabrica", None) is not _envolver_cota_do:
        envolver(AddDimensionCommand, "do", _envolver_cota_do, reemplazar=True)
    try:
        from tools.dimension import DimAngularTool
    except Exception:  # noqa: BLE001
        return
    actual = getattr(DimAngularTool, "preview_command", None)
    if actual is None or getattr(actual, "_puente_fabrica", None) == "cotas":
        DimAngularTool.preview_command = _vista_angular
    if getattr(DimAngularTool.preview_segments, "_puente_fabrica", None) is not _envolver_segmentos:
        envolver(DimAngularTool, "preview_segments", _envolver_segmentos, reemplazar=True)
    if getattr(DimAngularTool.on_point, "_puente_fabrica", None) is not _envolver_on_point:
        envolver(DimAngularTool, "on_point", _envolver_on_point, reemplazar=True)
    for nombre, funcion in (("resaltado", resaltado_angular),
                            ("referencias_extra", _referencias_angulo)):
        actual = getattr(DimAngularTool, nombre, None)
        if actual is None or getattr(actual, "_puente_fabrica", None) == "cotas":
            setattr(DimAngularTool, nombre, funcion)
    try:
        from ezdxf.render import dim_curved
    except Exception:  # noqa: BLE001
        dim_curved = None
    if dim_curved is not None and getattr(dim_curved.format_angular_text, "_puente_fabrica",
                                          None) is not _envolver_formato:
        envolver(dim_curved, "format_angular_text", _envolver_formato, reemplazar=True)
    try:
        from views.dimstyle_dialog import DimStyleEditorDialog   # usa Qt
    except Exception:  # noqa: BLE001
        return
    if getattr(DimStyleEditorDialog.__init__, "_puente_fabrica", None) is not _envolver_editor_estilo:
        envolver(DimStyleEditorDialog, "__init__", _envolver_editor_estilo, reemplazar=True)
