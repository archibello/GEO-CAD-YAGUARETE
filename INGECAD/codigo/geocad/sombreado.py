# SPDX-License-Identifier: GPL-3.0-or-later
"""Sombreado «Custom» para el HATCH de IngeCAD (3.99.0, módulo «sombreado»).

Pedido de Fernando (27/11/2026): una categoría nueva «Custom» en la ventana
Hatch, con
  - líneas: Ninguna (sólo el color de fondo), Simples o Dobles (dos familias
    perpendiculares entre sí), a una separación dada;
  - un punto de origen y una dirección dada por un segundo punto; las líneas
    van paralelas a esa dirección y las dobles, además, perpendiculares (3.99.1;
    la 3.99.0 las ponía a 45°: «Giro» lo permite, 0 por defecto);
  - color de las líneas, color de fondo aparte y grosor de las líneas;
  - varias áreas juntas en un sombreado o cada una por separado («Crear
    sombreados separados» de AutoCAD), respetando las islas;
  - los bordes con la mayor precisión: los arcos quedan arcos.

Es un HATCH común de DXF/DWG, como lo guarda AutoCAD:
  - líneas: patrón «Definido por el usuario» (_USER, tipo 0, «Doble» en el
    grupo 77), ángulo en el grupo 52 y separación en el 41, con las líneas del
    patrón pasando por el origen elegido;
  - fondo: el color de fondo del sombreado de AutoCAD (XDATA
    HATCHBACKGROUNDCOLOR), que IngeCAD no pinta: lo pinta GeoCAD;
  - sin líneas: un relleno sólido (SOLID) del color de fondo;
  - lo elegido en Custom viaja en el XDATA GEOCAD_TRAMA, para que HATCHEDIT
    vuelva a abrirlo en Custom (también uno sin líneas).

Sin Qt: la ventana está en sombreado_ui.py.
"""
from __future__ import annotations

import copy
import math

from . import modulos

PROGRAMA = "ingecad"
CLAVE = "sombreado"
CUSTOM = "CUSTOM"              # el nombre que lleva en la galería y en los ajustes
APPID = "GEOCAD_TRAMA"
LINEAS = ("ninguna", "simples", "dobles")
GIRO = 0.0                     # 3.99.1: paralelas a la dirección (la 3.99.0 las ponía a 45°)
GIRO_3990 = 45.0               # el de los sombreados hechos con la 3.99.0

DEFECTO = {
    "lineas": "dobles",
    "separacion": 1.0,
    "origen": (0.0, 0.0),
    "direccion": 0.0,          # grados, medidos desde la X del SCP, como Angle
    "giro": GIRO,              # las líneas respecto de la dirección (por defecto paralelas)
    "fondo": None,             # (r, g, b) o None
    "grosor": -1,              # centésimas de mm; -1 PorCapa, -2 PorBloque, -3 Por defecto
    "separados": False,
}


def activo() -> bool:
    return modulos.activo(PROGRAMA, CLAVE)


def es_custom(settings) -> bool:
    return bool(settings) and str(settings.get("pattern", "")).upper() == CUSTOM


def custom_de(settings) -> dict:
    """Los valores de Custom de unos ajustes, completos y en orden."""
    c = dict(DEFECTO)
    c.update({k: v for k, v in dict((settings or {}).get("custom") or {}).items()
              if k in DEFECTO})
    if c["lineas"] not in LINEAS:
        c["lineas"] = DEFECTO["lineas"]
    try:
        c["separacion"] = float(c["separacion"])
    except (TypeError, ValueError):
        c["separacion"] = DEFECTO["separacion"]
    if not c["separacion"] > 0:
        c["separacion"] = DEFECTO["separacion"]
    c["origen"] = (float(c["origen"][0]), float(c["origen"][1]))
    c["direccion"] = float(c["direccion"]) % 360.0
    c["giro"] = float(c["giro"]) % 360.0
    if c["fondo"] is not None:
        c["fondo"] = tuple(int(v) & 0xFF for v in c["fondo"])[:3]
    c["grosor"] = int(c["grosor"])
    c["separados"] = bool(c["separados"])
    return c


def angulo_lineas(direccion_mundo: float, giro: float = GIRO) -> float:
    """El ángulo de la primera familia de líneas (en el dibujo): paralela a la
    dirección, salvo un giro pedido; la segunda (Dobles), perpendicular."""
    return (float(direccion_mundo) + float(giro)) % 360.0


def definicion(c: dict, ucs_grados: float = 0.0) -> list:
    """Las familias del patrón, ya giradas y con su separación: cada una
    [ángulo, punto base, desplazamiento, []] (líneas continuas). El punto base
    es el origen elegido: por ahí pasa una línea de cada familia."""
    s = float(c["separacion"])
    a0 = angulo_lineas(float(c["direccion"]) + ucs_grados, c["giro"])
    angulos = [a0] + ([(a0 + 90.0) % 360.0] if c["lineas"] == "dobles" else [])
    familias = []
    for a in angulos:
        rad = math.radians(a)
        familias.append([a, tuple(c["origen"]), (-s * math.sin(rad), s * math.cos(rad)), []])
    return familias


# -- el HATCH ----------------------------------------------------------------------------
def _appid(hatch) -> None:
    doc = getattr(hatch, "doc", None)
    if doc is not None and APPID not in doc.appids:
        doc.appids.add(APPID)


def guardar_custom(hatch, c: dict) -> None:
    _appid(hatch)
    hatch.discard_xdata(APPID)
    fondo = c["fondo"]
    hatch.set_xdata(APPID, [
        (1000, c["lineas"]),
        (1040, float(c["separacion"])),
        (1040, float(c["direccion"])),
        (1010, (float(c["origen"][0]), float(c["origen"][1]), 0.0)),
        (1071, -1 if fondo is None else (fondo[0] << 16) | (fondo[1] << 8) | fondo[2]),
        (1070, int(c["grosor"])),
        (1070, 1 if c["separados"] else 0),
        (1040, float(c["giro"])),
    ])


def leer_custom(hatch):
    """Lo de Custom guardado en un HATCH, o None si no es uno de Custom."""
    try:
        if not hatch.has_xdata(APPID):
            return None
        tags = [(t.code, t.value) for t in hatch.get_xdata(APPID)]
    except Exception:  # noqa: BLE001 -- XDATA ajeno o roto: no es de Custom
        return None
    valores = [v for k, v in tags if k != 1001]
    try:
        lineas, sep, dire, org, fondo, grosor, separados = valores[:7]
        fondo = int(fondo)
        giro = float(valores[7]) if len(valores) > 7 else GIRO_3990   # sin giro: de la 3.99.0
        return custom_de({"custom": {"giro": giro,
            "lineas": str(lineas), "separacion": float(sep), "direccion": float(dire),
            "origen": (float(org[0]), float(org[1])),
            "fondo": None if fondo < 0 else ((fondo >> 16) & 0xFF, (fondo >> 8) & 0xFF, fondo & 0xFF),
            "grosor": int(grosor), "separados": bool(int(separados))}})
    except (TypeError, ValueError, IndexError):
        return None


def aplicar(hatch, settings: dict, ucs_grados: float = 0.0) -> None:
    """Deja el HATCH como pide Custom: el relleno, el fondo, el grosor, el
    color y el XDATA. Los bordes no se tocan (sirve para crear y para
    HATCHEDIT). ``settings`` lleva color (ACI, 256 = PorCapa) y custom."""
    c = custom_de(settings)
    color = int(settings.get("color", 256))
    aci = 7 if color in (256, 0) else color
    estilo = int(hatch.dxf.get("hatch_style", 0))
    if c["lineas"] == "ninguna":
        fondo = c["fondo"] if c["fondo"] is not None else (255, 255, 255)
        hatch.set_solid_fill(color=aci, rgb=fondo)
        try:
            del hatch.bgcolor
        except Exception:  # noqa: BLE001
            pass
    else:
        hatch.set_pattern_fill("_USER", color=aci, angle=0.0, scale=1.0,
                               double=1 if c["lineas"] == "dobles" else 0,
                               pattern_type=0, definition=definicion(c, ucs_grados))
        # lo que AutoCAD lee de un «Definido por el usuario»: ángulo y
        # separación (los cambios de escala o giro de IngeCAD parten de acá)
        hatch.dxf.pattern_angle = angulo_lineas(c["direccion"] + ucs_grados, c["giro"])
        hatch.dxf.pattern_scale = float(c["separacion"])
        hatch.dxf.pattern_type = 0
        hatch.dxf.pattern_double = 1 if c["lineas"] == "dobles" else 0
        if c["fondo"] is not None:
            hatch.bgcolor = c["fondo"]
        else:
            try:
                del hatch.bgcolor
            except Exception:  # noqa: BLE001
                pass
        hatch.dxf.color = color
        try:
            hatch.dxf.discard("true_color")
        except Exception:  # noqa: BLE001
            pass
    hatch.dxf.hatch_style = estilo
    hatch.dxf.lineweight = int(c["grosor"])
    guardar_custom(hatch, c)


def quitar_custom(hatch) -> None:
    """Un HATCH que deja de ser Custom (HATCHEDIT a otro patrón): sin el
    XDATA de GeoCAD y sin el fondo, como uno de IngeCAD."""
    try:
        hatch.discard_xdata(APPID)
    except Exception:  # noqa: BLE001
        pass
    try:
        del hatch.bgcolor
    except Exception:  # noqa: BLE001
        pass


def ajustes_de(hatch, base: dict) -> dict:
    """Los ajustes que HATCHEDIT muestra de un HATCH de Custom."""
    c = leer_custom(hatch)
    if c is None:
        return base
    s = dict(base)
    s["pattern"] = CUSTOM
    s["custom"] = c
    s["scale"] = c["separacion"]
    s["angle"] = c["direccion"]
    return s


# -- los bordes ---------------------------------------------------------------------------
def sin_tildes(texto: str) -> str:
    """«Parámetros» -> «Parametros» (para leer las opciones como se escriban)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def area(poli) -> float:
    n = len(poli)
    return abs(sum(poli[i][0] * poli[(i + 1) % n][1] - poli[(i + 1) % n][0] * poli[i][1]
                   for i in range(n))) / 2.0


def adentro(p, poli) -> bool:
    x, y = p[0], p[1]
    dentro = False
    n = len(poli)
    for i in range(n):
        x0, y0 = poli[i][0], poli[i][1]
        x1, y1 = poli[(i + 1) % n][0], poli[(i + 1) % n][1]
        if (y0 > y) != (y1 > y):
            cx = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < cx:
                dentro = not dentro
    return dentro


def _punto_interior(poli):
    """Un punto que cae dentro del polígono (no un vértice: en contornos que
    se tocan un vértice puede estar sobre el borde del otro)."""
    n = len(poli)
    for i in range(n):
        a, b, c = poli[i - 1], poli[i], poli[(i + 1) % n]
        m = ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)
        if adentro(m, poli):
            return m
    return (poli[0][0], poli[0][1])


def agrupar(poligonos: list) -> list:
    """Cada contorno con sus islas, para «sombreados separados».

    ``poligonos``: listas de puntos. Devuelve [(i_exterior, [i_islas])]: un
    contorno a profundidad par (0, 2...) es exterior; los de profundidad
    impar que tiene justo adentro son sus islas (como el estilo Normal)."""
    n = len(poligonos)
    areas = [area(p) for p in poligonos]
    muestra = [_punto_interior(p) for p in poligonos]
    padre = [None] * n
    hondo = [0] * n
    for i in range(n):
        contiene = [j for j in range(n) if j != i and areas[j] > areas[i]
                    and adentro(muestra[i], poligonos[j])]
        hondo[i] = len(contiene)
        if contiene:
            padre[i] = min(contiene, key=lambda j: areas[j])
    grupos = []
    for i in range(n):
        if hondo[i] % 2 == 0:
            grupos.append((i, [j for j in range(n) if padre[j] == i and hondo[j] % 2 == 1]))
    return grupos


def con_arcos(loop, entidades):
    """El contorno encontrado por un clic con sus arcos como arcos
    ((x, y, bulge)), como lo hace BOUNDARY de IngeCAD; si no se puede, tal cual."""
    try:
        from core.hatch_boundary import loop_with_bulges
        return [(float(x), float(y), float(b))
                for x, y, b in loop_with_bulges(list(loop), list(entidades))]
    except Exception:  # noqa: BLE001 -- un IngeCAD sin la función: los tramos
        return [(float(p[0]), float(p[1]), 0.0) for p in loop]


def agregar_borde(hatch, item, flags: int) -> None:
    """Un borde del HATCH: lista de (x, y[, bulge]) o una entidad cerrada."""
    if isinstance(item, (list, tuple)) and item and isinstance(item[0], (list, tuple)):
        pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in item]
        hatch.paths.add_polyline_path(pts, is_closed=True, flags=flags)
        return
    from core import actions
    actions._add_boundary(hatch, item, flags)


def poligono_de(item):
    """Los puntos de un borde (lista o entidad), para agrupar."""
    if isinstance(item, (list, tuple)):
        return [(p[0], p[1]) for p in item]
    if item.dxftype() == "LWPOLYLINE":          # también abierta (3.99.1: se cierra)
        return [(p[0], p[1]) for p in item.get_points("xy")]
    try:
        from core.hatch_boundary import boundary_polygon
        return [(p[0], p[1]) for p in (boundary_polygon(item) or [])]
    except Exception:  # noqa: BLE001
        return []


def orden_crear(grupos: list, settings: dict, ucs_grados: float = 0.0):
    """El comando que crea los sombreados: ``grupos`` = [(exteriores, islas)],
    uno por sombreado. Un solo U para todos."""
    from ezdxf.lldxf.const import BOUNDARY_PATH_EXTERNAL, BOUNDARY_PATH_OUTERMOST
    from core import actions

    def fabrica_de(exteriores, islas):
        def factory(msp):
            h = msp.add_hatch(color=7)
            for b in exteriores:
                agregar_borde(h, b, BOUNDARY_PATH_EXTERNAL)
            for b in islas:
                agregar_borde(h, b, BOUNDARY_PATH_OUTERMOST)
            h.dxf.hatch_style = 0           # Normal: las islas quedan huecas
            aplicar(h, settings, ucs_grados)
            return h
        return factory

    ordenes = [actions.AddEntityCommand("HATCH", fabrica_de(e, i)) for e, i in grupos]
    if len(ordenes) == 1:
        return ordenes[0]
    from core.commands import CompositeCommand
    return CompositeCommand("HATCH", ordenes)


def muy_denso(bordes, settings) -> bool:
    """Como el HPMAXLINES de IngeCAD 0.8.0 (más viejas: no se mira)."""
    c = custom_de(settings)
    if c["lineas"] == "ninguna":
        return False
    try:
        from core import actions
        f = actions.hatch_too_dense
    except Exception:  # noqa: BLE001
        return False
    planos = [poligono_de(b) if isinstance(b, (list, tuple)) else b for b in bordes]
    try:
        return bool(f(planos, "U", 1.0, 0.0,
                      (angulo_lineas(c["direccion"], c["giro"]), c["separacion"], c["lineas"] == "dobles")))
    except Exception:  # noqa: BLE001
        return False


def cmd_custom(ctx, *args) -> None:
    """SOMBREADOCUSTOM (GEOHATCHCUSTOM): HATCH con la ventana ya en Custom."""
    host = getattr(ctx, "host", None)
    invocar = getattr(host, "_invoke_command", None)
    if not callable(invocar):
        ctx.echo("El sombreado Custom necesita la ventana de IngeCAD.")
        return
    from .sombreado_herramienta import GeoHatchTool
    GeoHatchTool._abrir_custom = True
    invocar("HATCH")


# -- el fondo en pantalla y en el PDF -----------------------------------------------------
def _envolver_dibujo(original):
    def draw_hatch_entity(self, entity, properties, *args, **kwargs):
        if activo() and not kwargs.get("loops") and not args:
            try:
                rgb = None
                if entity.dxftype() == "HATCH" and not int(entity.dxf.get("solid_fill", 0) or 0):
                    rgb = entity.bgcolor
                if rgb is not None:
                    from ezdxf.addons.drawing.properties import Filling
                    fondo = copy.copy(properties)
                    fondo.filling = Filling()
                    alfa = str(properties.color)[7:9]
                    fondo.color = "#%02x%02x%02x%s" % (rgb[0], rgb[1], rgb[2], alfa)
                    original(self, entity, fondo)
            except Exception:  # noqa: BLE001 -- sin fondo, como lo pinta IngeCAD
                pass
        return original(self, entity, properties, *args, **kwargs)
    draw_hatch_entity._puente_original = original
    draw_hatch_entity._puente_fabrica = _envolver_dibujo
    return draw_hatch_entity


def instalar() -> None:
    """El fondo de los sombreados (pantalla, regen en paralelo e impresión)
    y HATCHEDIT con Custom. Los envoltorios miran ``activo()`` en cada
    llamada: apagado, IngeCAD queda como venía."""
    from .dibujo import envolver
    try:
        from ezdxf.addons.drawing.frontend import Frontend
        envolver(Frontend, "draw_hatch_entity", _envolver_dibujo, reemplazar=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        from core import actions
    except Exception:  # noqa: BLE001
        return
    envolver(actions, "hatch_settings", _envolver_leer, reemplazar=True)
    envolver(actions, "apply_hatch_settings", _envolver_aplicar, reemplazar=True)
    if hasattr(actions, "hatch_too_dense"):
        envolver(actions, "hatch_too_dense", _envolver_denso, reemplazar=True)
    try:
        from . import sombreado_ui
        sombreado_ui.instalar()
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas): sólo lo de arriba
        pass


def _envolver_leer(original):
    def hatch_settings(hatch):
        base = original(hatch)
        return ajustes_de(hatch, base) if activo() else base
    hatch_settings._puente_original = original
    hatch_settings._puente_fabrica = _envolver_leer
    return hatch_settings


def _envolver_aplicar(original):
    def apply_hatch_settings(hatch, settings):
        if activo() and es_custom(settings):
            aplicar(hatch, settings)
            return None
        resultado = original(hatch, settings)
        if leer_custom(hatch) is not None:
            quitar_custom(hatch)
        return resultado
    apply_hatch_settings._puente_original = original
    apply_hatch_settings._puente_fabrica = _envolver_aplicar
    return apply_hatch_settings


def _envolver_denso(original):
    def hatch_too_dense(boundaries, pattern="SOLID", scale=1.0, angle=0.0, user_def=None):
        if str(pattern).upper() == CUSTOM:
            # HATCHEDIT sólo pasa el nombre y la escala (= la separación)
            try:
                return original(boundaries, "U", 1.0, angle, (0.0, float(scale), True))
            except Exception:  # noqa: BLE001
                return False
        return original(boundaries, pattern, scale, angle, user_def)
    hatch_too_dense._puente_original = original
    hatch_too_dense._puente_fabrica = _envolver_denso
    return hatch_too_dense


# -- agarres: un agarre en el medio de cada lado (3.99.1) ------------------------------------
# Fernando, 27/11/2026: «todos los lados de las geometrías generadas por hatch deberán
# tener un punto de agarre central, desde donde poder agregar nuevos vértices». Van
# después de los de IngeCAD (el central y los vértices), con el rol «mid» de las
# polilíneas: arrastrarlo mueve el lado; Ctrl + clic agrega un vértice (agarres_ingecad).
# Los vértices también los mueve GeoCAD: en IngeCAD 0.7.0 y anteriores la cuenta del
# primer vértice usa la lista de agarres, que ahora es más larga.
def _paso(a, b) -> float:
    return 1e-9 * max(1.0, abs(a), abs(b))


def lados(hatch) -> list:
    """Los lados rectos del borde: (camino, k, inicio, fin) en un orden fijo."""
    from ezdxf.entities.boundary_paths import LineEdge
    out = []
    for pi, path in enumerate(getattr(hatch, "paths", ()) or ()):
        vertices = getattr(path, "vertices", None)
        if vertices is not None:
            n = len(vertices)
            for k in range(n if n >= 3 or getattr(path, "is_closed", True) else n - 1):
                v0, v1 = vertices[k], vertices[(k + 1) % n]
                if len(v0) > 2 and abs(float(v0[2])) > 1e-12:
                    continue                      # un arco: no tiene medio recto
                out.append((pi, k, (float(v0[0]), float(v0[1])), (float(v1[0]), float(v1[1]))))
            continue
        for k, edge in enumerate(getattr(path, "edges", ()) or ()):
            if isinstance(edge, LineEdge):
                out.append((pi, k, (float(edge.start[0]), float(edge.start[1])),
                            (float(edge.end[0]), float(edge.end[1]))))
    return out


def _vertices(hatch) -> list:
    from core.select import _hatch_vertices
    return list(_hatch_vertices(hatch))


def _originales(hatch) -> list:
    from core import select
    f = getattr(select, "core_entity_grips", None)
    if f is None:
        f = select.entity_grips
        while hasattr(f, "_puente_original"):
            f = f._puente_original
    return list(f(hatch))


def _base(hatch) -> list:
    """Los agarres de IngeCAD sin el del centro (3.100.1, Fernando: «no debe quedar
    un control por fuera de la geometría»): como un polígono, sólo vértices; se
    mueve con MOVE. Si no tiene vértices (asociativo), queda el de IngeCAD."""
    base = [tuple(g) for g in _originales(hatch)]
    if any(len(g) > 2 and g[2] == "vertex" for g in base):
        base = [g for g in base if not (len(g) > 2 and g[2] == "center")]
    return base


def agarres(hatch) -> list:
    """Los vértices y uno en el medio de cada lado recto."""
    base = _base(hatch)
    return base + [((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, "mid") for _pi, _k, a, b in lados(hatch)]


def mover_agarre(hatch, indice: int, rol: str, punto):
    """True/False si el agarre es de GeoCAD (lo movió o no); None: el de IngeCAD."""
    from core.select import _hatch_move_vertex
    base = _base(hatch)
    walk = _vertices(hatch)
    extra = len(base) - len(walk)               # el central (si se pudo calcular)
    if rol == "vertex":
        i = indice - extra
        if not 0 <= i < len(walk):
            return False
        pi, x, y = walk[i]
        return _hatch_move_vertex(hatch, pi, (x, y), (float(punto[0]), float(punto[1])))
    if rol == "mid":
        todos = lados(hatch)
        j = indice - len(base)
        if not 0 <= j < len(todos):
            return False
        pi, _k, a, b = todos[j]
        dx = float(punto[0]) - (a[0] + b[0]) / 2.0
        dy = float(punto[1]) - (a[1] + b[1]) / 2.0
        ok1 = _hatch_move_vertex(hatch, pi, a, (a[0] + dx, a[1] + dy))
        ok2 = _hatch_move_vertex(hatch, pi, b, (b[0] + dx, b[1] + dy))
        return bool(ok1 or ok2)
    return None


def agregar_vertice(hatch, indice: int, punto) -> int:
    """Un vértice nuevo en el lado del agarre del medio ``indice``; devuelve el
    índice de su agarre (rol «vertex»), o -1."""
    from ezdxf.entities.boundary_paths import LineEdge
    base = _base(hatch)
    extra = len(base) - len(_vertices(hatch))
    todos = lados(hatch)
    j = indice - len(base)
    if not 0 <= j < len(todos):
        return -1
    pi, k, _a, b = todos[j]
    path = hatch.paths[pi]
    p = (float(punto[0]), float(punto[1]))
    vertices = getattr(path, "vertices", None)
    if vertices is not None:
        vertices.insert(k + 1, (p[0], p[1], 0.0))
        local = k + 1
    else:
        edge = path.edges[k]
        nuevo = LineEdge()
        nuevo.start, nuevo.end = p, (b[0], b[1])
        edge.end = p
        path.edges.insert(k + 1, nuevo)
        local = sum(1 for e in path.edges[:k + 1] if isinstance(e, LineEdge))
    antes = sum(1 for w in _vertices(hatch) if w[0] < pi)
    return extra + antes + local


def lado_recto(hatch, indice: int) -> bool:
    """¿El agarre ``indice`` es el medio de un lado recto de este sombreado?"""
    try:
        return 0 <= indice - len(_base(hatch)) < len(lados(hatch))
    except Exception:  # noqa: BLE001
        return False


# -- contornos abiertos o mal cerrados (3.99.1) ------------------------------------------------
# Fernando, 27/11/2026: «cuando un hatch se encuentra con una geometría abierta, o mal
# cerrada, va a interpretar que está cerrada» y «cuando elijamos un objeto y no un espacio
# interior, nos va a dar como opción principal seleccionar el objeto».
#: la abertura más grande que se salva, respecto de la diagonal de lo que se ve
#: (como HPGAPTOL de AutoCAD, que se da en unidades; acá sigue al zoom)
HUECO = 0.01


def contorno_posible(e) -> bool:
    """¿Este objeto, tomado con un clic, sirve de contorno (abierto se cierra)?"""
    try:
        t = e.dxftype()
        if t == "LWPOLYLINE":
            return len(e) >= 3 or (len(e) >= 2 and any(abs(b) > 1e-12 for *_x, b in e.get_points("xyb")))
        if t in ("CIRCLE", "ELLIPSE"):
            return True
        if t == "SPLINE":
            return bool(e.closed)
        if t == "POLYLINE":
            return e.is_2d_polyline and len(e) >= 3
    except Exception:  # noqa: BLE001
        pass
    return False


def _extremos(e):
    """Las dos puntas de una curva abierta, o None si está cerrada o no es curva."""
    try:
        t = e.dxftype()
        if t == "LINE":
            return ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
        if t == "ARC":
            a, b = e.start_point, e.end_point
            return ((a.x, a.y), (b.x, b.y))
        if t == "LWPOLYLINE" and not e.closed and len(e) >= 2:
            pts = e.get_points("xy")
            return (tuple(pts[0][:2]), tuple(pts[-1][:2]))
        if t == "SPLINE" and not e.closed:
            pts = list(e.control_points) or list(e.fit_points)
            if len(pts) >= 2:
                return ((pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1]))
    except Exception:  # noqa: BLE001
        pass
    return None


def _linea(a, b):
    from ezdxf.entities import Line
    return Line.new(dxfattribs={"start": (a[0], a[1], 0.0), "end": (b[0], b[1], 0.0)})


def _tramos_rectos(e):
    """Los tramos rectos de una línea o polilínea (para saber si una punta toca)."""
    try:
        t = e.dxftype()
        if t == "LINE":
            return [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]
        if t == "LWPOLYLINE":
            pts = e.get_points("xyb")
            n = len(pts)
            idx = range(n if e.closed else n - 1)
            return [((pts[k][0], pts[k][1]), (pts[(k + 1) % n][0], pts[(k + 1) % n][1]))
                    for k in idx if abs(pts[k][2]) <= 1e-12]
    except Exception:  # noqa: BLE001
        pass
    return []


def _dist_tramo(p, a, b) -> float:
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def cierres(entidades, tolerancia: float) -> list:
    """Líneas de más (no van al dibujo) que cierran lo abierto, como la
    tolerancia de huecos de AutoCAD:
      1) cada punta suelta se une con la punta suelta más cercana a menos de
         ``tolerancia`` (de a pares, primero los más cercanos);
      2) una polilínea abierta de 3 o más vértices cuyas DOS puntas siguen
         sueltas se cierra de la última a la primera.
    Una punta no está suelta si toca otra punta o el tramo de otro objeto.
    (3.99.2: la 3.99.1 cerraba cada polilínea abierta sobre sí misma, también
    las que eran un pedazo de un contorno más grande: dejaba triángulos sin
    sombrear, Fernando 27/11/2026.)"""
    ents = list(entidades)
    puntas = []                                  # (objeto, 0/1, punto)
    for i, e in enumerate(ents):
        ext = _extremos(e)
        if ext is not None:
            puntas.extend([(i, 0, ext[0]), (i, 1, ext[1])])
    if len(puntas) > 4000:
        puntas = puntas[:4000]
    eps = 1e-9 * max([1.0] + [abs(c) for _i, _k, p in puntas for c in p])
    tramos = {i: _tramos_rectos(e) for i, e in enumerate(ents)}

    def toca(n):
        i, k, p = puntas[n]
        for m, (j, kk, q) in enumerate(puntas):
            if m != n and (j != i or kk != k) and math.dist(p, q) <= eps:
                return True
        return any(j != i and any(_dist_tramo(p, a, b) <= eps for a, b in segs)
                   for j, segs in tramos.items())

    sueltas = [n for n in range(len(puntas)) if not toca(n)]
    pares = sorted((math.dist(puntas[a][2], puntas[b][2]), a, b)
                   for x, a in enumerate(sueltas) for b in sueltas[x + 1:]
                   if math.dist(puntas[a][2], puntas[b][2]) <= tolerancia)
    usadas, extras = set(), []
    for _d, a, b in pares:
        if a in usadas or b in usadas:
            continue
        usadas.update((a, b))
        extras.append(_linea(puntas[a][2], puntas[b][2]))
    libres = {}
    for n in sueltas:
        if n not in usadas:
            libres.setdefault(puntas[n][0], []).append(n)
    for i, ns in libres.items():
        e = ents[i]
        if len(ns) == 2 and e.dxftype() == "LWPOLYLINE" and len(e) >= 3:
            extras.append(_linea(puntas[ns[1]][2], puntas[ns[0]][2]))
    return extras


def _entidades_del_espacio(servicios) -> list:
    win = getattr(servicios, "window", None)
    doc = getattr(win, "document", None)
    if doc is None:
        return []
    try:
        from core import xrefs
        out = []
        for e in doc.current_space():
            out.extend(xrefs.plain_entities(e, doc))
        return out
    except Exception:  # noqa: BLE001 -- IngeCAD 0.6.x: el modelo
        return list(doc.modelspace())


def region_abierta(servicios, punto, entidades=None, ventana=None):
    """La región del clic, tomando como cerradas las polilíneas abiertas y
    salvando las aberturas chicas. None si tampoco así se encuentra."""
    from core.hatch_boundary import region_at_point
    if entidades is None:
        entidades = _entidades_del_espacio(servicios)
    if ventana is None:
        f = getattr(servicios, "_visible_space_rect", None)
        try:
            ventana = f() if callable(f) else None
        except Exception:  # noqa: BLE001
            ventana = None
    if ventana is not None:
        diag = math.hypot(ventana[2] - ventana[0], ventana[3] - ventana[1])
    else:
        xs = [c[0] for e in entidades if (x := _extremos(e)) for c in x] or [0.0, 1.0]
        ys = [c[1] for e in entidades if (x := _extremos(e)) for c in x] or [0.0, 1.0]
        diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    extras = cierres(entidades, HUECO * diag)
    if not extras:
        return None
    try:
        r = region_at_point(list(entidades) + extras, punto, window=ventana)
    except Exception:  # noqa: BLE001
        return None
    if r is None:
        return None
    # los saltos chicos dejan dos vértices casi juntos: queda uno (agarres sin repetir)
    junta = max([0.0] + [math.dist((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
                         for e in extras if math.dist((e.dxf.start.x, e.dxf.start.y),
                                                      (e.dxf.end.x, e.dxf.end.y)) <= HUECO * diag])
    return (_sin_repetidos(r[0], junta), [_sin_repetidos(i, junta) for i in r[1]])


def _sin_repetidos(loop, tol: float):
    out = []
    for p in loop:
        if out and math.dist(out[-1], p) <= tol * 1.000001:
            continue
        out.append(p)
    while len(out) > 3 and math.dist(out[0], out[-1]) <= tol * 1.000001:
        out.pop()
    return out


# -- estilos guardados de Custom (3.99.2) -------------------------------------------------------
# Fernando, 27/11/2026: el espacio de la galería en Custom, para «guardar estilos para que
# podamos usarlos nuevamente». Guardan lo que no depende del lugar: líneas, separación,
# giro, color de las líneas, color de fondo y grosor (no el origen ni la dirección).
GUARDADOS = ("lineas", "separacion", "giro", "fondo", "grosor")
PREFIJO = CUSTOM + ":"          # el nombre de un estilo en la galería


def archivo_estilos():
    from pathlib import Path
    return Path.home() / ".config" / "geocad" / "sombreados.json"


def estilos() -> dict:
    """{nombre: {lineas, separacion, giro, fondo, grosor, color}}, en el orden guardado."""
    import json
    try:
        data = json.loads(archivo_estilos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    crudo = data.get("estilos") if isinstance(data, dict) else None
    if not isinstance(crudo, dict):
        return {}
    out = {}
    for nombre, v in crudo.items():
        if not isinstance(v, dict):
            continue
        c = custom_de({"custom": {k: v[k] for k in GUARDADOS if k in v}})
        estilo = {k: c[k] for k in GUARDADOS}
        try:
            estilo["color"] = int(v.get("color", 256))
        except (TypeError, ValueError):
            estilo["color"] = 256
        out[str(nombre)] = estilo
    return out


def _escribir_estilos(todos: dict) -> None:
    import json
    ruta = archivo_estilos()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {n: dict(e, fondo=list(e["fondo"]) if e.get("fondo") is not None else None)
             for n, e in todos.items()}
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "estilos": datos}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(ruta)


def guardar_estilo(nombre: str, custom: dict, color: int = 256) -> str:
    """Guarda (o reemplaza) un estilo; devuelve el nombre limpio."""
    nombre = str(nombre).strip()
    if not nombre:
        raise ValueError("falta el nombre del estilo")
    c = custom_de({"custom": custom})
    todos = estilos()
    todos[nombre] = dict({k: c[k] for k in GUARDADOS}, color=int(color))
    _escribir_estilos(todos)
    return nombre


def borrar_estilo(nombre: str) -> bool:
    todos = estilos()
    if nombre not in todos:
        return False
    del todos[nombre]
    _escribir_estilos(todos)
    return True


def renombrar_estilo(viejo: str, nuevo: str) -> bool:
    nuevo = str(nuevo).strip()
    todos = estilos()
    if viejo not in todos or not nuevo or (nuevo != viejo and nuevo in todos):
        return False
    _escribir_estilos({(nuevo if n == viejo else n): e for n, e in todos.items()})
    return True


def aplicar_estilo(custom: dict, estilo: dict) -> dict:
    """Los valores de Custom con un estilo puesto: origen y dirección quedan."""
    c = custom_de({"custom": custom})
    c.update({k: estilo[k] for k in GUARDADOS if k in estilo})
    return custom_de({"custom": c})
