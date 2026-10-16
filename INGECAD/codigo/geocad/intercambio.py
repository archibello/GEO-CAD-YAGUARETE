# SPDX-License-Identifier: GPL-3.0-or-later
"""Módulo «Intercambio» (3.25.0): el sistema de coordenadas del dibujo,
Importar SHP y Exportar SHP. Propuesta: propuesta_importar/.

* SISTEMAGEO declara (o redeclara) en qué sistema están las coordenadas
  del dibujo. No mueve nada. Se guarda en el registro GEOREF de IngeCAD
  (core/georef.py), el mismo que usan Terreno y el Puente.
* REPROYECTAR convierte las coordenadas del dibujo a otro sistema (PROJ,
  con el pyproj que trae IngeCAD) y deja declarado el nuevo. Un solo
  deshacer, exacto: cada objeto vuelve a su copia de antes. Los objetos de
  capas CONECTADAS a un SHP o GPKG no se tocan: al guardarlas se
  escribirían en su archivo coordenadas de otro sistema.
* IMPORTARSHP copia uno o varios shapefiles al dibujo (sin vínculo; para el
  vínculo vivo sigue CONECTARSHP), llevados al sistema del dibujo, con su
  base de datos: cada objeto guarda su registro y la tabla se ve y edita
  en la Tabla de atributos (importados.py). Los rótulos, después, con
  ROTULOSIG.
* EXPORTARSHP escribe lo elegido como shapefiles nuevos, en el sistema del
  dibujo o en otro, con su .prj, su .cpg y los atributos que traían.

Todo lo que no necesita la ventana está acá y se prueba sin Qt; las
ventanas están en intercambio_ui.py.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.commands import Command, CompositeCommand
from core.georef import Georef, read_georef, write_georef
from core.layers import NewLayerCommand

from .modelo import AddToModelCommand
from . import crs as crs_mod
from . import shpio

#: XDATA propia para los atributos que trae un objeto importado (la de
#: IngeCAD, «INGECAD», la usa CONECTARSHP y se reemplaza entera): ver importados.py.
from .importados import APPID_ATRIB, LARGO_XDATA, MARCA_ATRIB, atributos, poner_atributos  # noqa: E402,F401

TOLERANCIA = 0.01      # arcos y curvas a tramos rectos: 1 cm con el dibujo en metros


class SinProj(RuntimeError):
    """pyproj no está (un IngeCAD armado sin él)."""


# ================================================================== sistemas de coordenadas

def lista_corta() -> list[tuple[str, str]]:
    """[(«EPSG:xxxx», nombre)] de la lista argentina: POSGAR 2007, 98 y 94 y
    Campo Inchauspe en sus 7 fajas, y WGS 84 / UTM. Sin geográficas: el
    dibujo está en metros."""
    out = []
    for _nombre, base, _geo in crs_mod.DATUMS:
        for faja in range(1, 8):
            code = base + faja - 1
            out.append((f"EPSG:{code}", crs_mod.KNOWN[code]))
    for zona in (18, 19, 20, 21, 22):
        out.append((f"EPSG:{32700 + zona}", crs_mod.KNOWN[32700 + zona]))
    return out


def normalizar(texto: str) -> str:
    """«5347», «epsg:5347», «EPSG 5347» -> «EPSG:5347»; "" si no es un código."""
    m = re.fullmatch(r"\s*(?:EPSG\s*[: ]\s*)?(\d{4,6})\s*", str(texto or ""), re.I)
    return f"EPSG:{m.group(1)}" if m else ""


def _epsg(code: str) -> Optional[int]:
    m = re.fullmatch(r"EPSG:(\d+)", code or "")
    return int(m.group(1)) if m else None


def nombre(code: str) -> str:
    """Cómo se muestra un sistema: «POSGAR 2007 / Argentina faja 5 (EPSG:5347)»."""
    if not code:
        return "sin definir"
    n = _epsg(code)
    if n in crs_mod.KNOWN:
        return f"{crs_mod.KNOWN[n]} ({code})"
    try:
        from pyproj import CRS
        return f"{CRS.from_user_input(code).name} ({code})"
    except Exception:  # noqa: BLE001 -- sin pyproj o código desconocido
        return code


# ------------------------------------------------------------------ favoritos y buscador (3.25.5)
#: los sistemas que se van eligiendo quedan primero, como los «usados
#: recientemente» de QGIS (Fernando, 16/10/2026); el último elegido, arriba.
MAX_FAVORITOS = 20


def _archivo_favoritos() -> Path:
    from . import config
    return config.config_path().parent / "sistemas_favoritos.json"


def favoritos() -> list[str]:
    """Los códigos «EPSG:xxxx» elegidos antes, el más reciente primero. Un
    archivo dañado o ausente es una lista vacía."""
    try:
        data = json.loads(_archivo_favoritos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        c = normalizar(c) if isinstance(c, str) else ""
        if c and c not in out:
            out.append(c)
    return out[:MAX_FAVORITOS]


def _guardar_favoritos(lista: list[str]) -> None:
    ruta = _archivo_favoritos()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".favoritos-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(lista[:MAX_FAVORITOS], fh, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def agregar_favorito(code: str) -> list[str]:
    """Pone ``code`` primero en los favoritos (sin repetirlo)."""
    code = normalizar(code)
    if not code:
        return favoritos()
    lista = [code] + [c for c in favoritos() if c != code]
    try:
        _guardar_favoritos(lista)
    except OSError:
        pass
    return lista[:MAX_FAVORITOS]


def quitar_favorito(code: str) -> list[str]:
    lista = [c for c in favoritos() if c != normalizar(code)]
    try:
        _guardar_favoritos(lista)
    except OSError:
        pass
    return lista


_CATALOGO: dict = {}


def catalogo(solo_metros: bool = False) -> list[tuple[str, str]]:
    """[(«EPSG:xxxx», nombre)] de todos los sistemas EPSG vigentes que conoce
    PROJ (proyectados y, si no es ``solo_metros``, también geográficos), como
    el buscador de QGIS. Sin pyproj, la lista corta."""
    if solo_metros in _CATALOGO:
        return _CATALOGO[solo_metros]
    try:
        from pyproj.database import query_crs_info
        from pyproj.enums import PJType
        tipos = [PJType.PROJECTED_CRS]
        if not solo_metros:
            tipos += [PJType.GEOGRAPHIC_2D_CRS]
        info = query_crs_info(auth_name="EPSG", pj_types=tipos)
        # los argentinos, con el nombre de la lista corta («... faja 5»)
        out = sorted(((f"EPSG:{i.code}", crs_mod.KNOWN.get(int(i.code), i.name))
                      for i in info if not i.deprecated and i.code.isdigit()),
                     key=lambda t: t[1].lower())
    except Exception:  # noqa: BLE001 -- sin pyproj
        out = lista_corta()
    _CATALOGO[solo_metros] = out
    return out


def buscar_sistemas(texto: str, solo_metros: bool = False, limite: int = 500) -> list[tuple[str, str]]:
    """Los del catálogo cuyo nombre o código tienen todas las palabras de
    ``texto`` («posgar 5», «5347», «utm 21s»)."""
    palabras = str(texto or "").lower().split()
    out = []
    for code, nombre_s in catalogo(solo_metros):
        donde = f"{nombre_s} {code}".lower()
        if all(p in donde for p in palabras):
            out.append((code, nombre_s))
            if len(out) >= limite:
                break
    return out


def validar(code: str) -> str:
    """El motivo por el que ``code`` no sirve para un dibujo, o ""."""
    if not _epsg(code):
        return "escriba un código EPSG (p. ej. 5347)"
    try:
        from pyproj import CRS
    except ImportError:
        return "" if _epsg(code) in crs_mod.KNOWN else "sin pyproj sólo se aceptan los de la lista"
    try:
        crs = CRS.from_user_input(code)
    except Exception:  # noqa: BLE001
        return f"PROJ no conoce {code}"
    if not crs.is_projected:
        return f"{code} es geográfico (grados): el dibujo necesita un sistema en metros"
    return ""


def sistema_de(georef: Optional[Georef]) -> str:
    """«EPSG:xxxx» de una georreferencia de IngeCAD, o ""."""
    if georef is None:
        return ""
    if georef.crs:
        return georef.crs
    if georef.datum == "WGS84":
        return f"EPSG:{(32600 if georef.northern else 32700) + georef.zone}"
    if georef.datum == "PSAD56":
        return f"EPSG:{(24800 if georef.northern else 24860) + georef.zone}"
    return ""


def sistema_del_dibujo(doc) -> str:
    """El sistema DECLARADO en el dibujo (registro GEOREF), o ""."""
    try:
        return sistema_de(read_georef(doc))
    except Exception:  # noqa: BLE001
        return ""


def sistema_de_prj(prj_path) -> str:
    """«EPSG:xxxx» del .prj, o "" si no hay .prj o no se reconoce."""
    p = Path(prj_path)
    if p.suffix.lower() != ".prj":
        p = p.with_suffix(".prj")
    if not p.exists():
        return ""
    texto = p.read_text(errors="replace")
    c = crs_mod.identify(texto)
    if c.epsg:
        return c.code
    try:                                    # un .prj de ESRI sin código: que PROJ lo reconozca
        from pyproj import CRS
        auth = CRS.from_wkt(texto).to_authority(min_confidence=70)
        if auth and auth[0] == "EPSG":
            return f"EPSG:{auth[1]}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def wkt_prj(code: str) -> str:
    """El texto del .prj (WKT1 de ESRI, el que leen QGIS y ArcGIS)."""
    from pyproj import CRS
    from pyproj.enums import WktVersion
    return CRS.from_user_input(code).to_wkt(WktVersion.WKT1_ESRI)


class DefinirSistemaCommand(Command):
    """SISTEMAGEO: declara el sistema del dibujo (no mueve nada)."""

    name = "definir sistema"

    def __init__(self, code: str) -> None:
        self.code = code
        self._antes = None

    def do(self, document) -> None:
        self._antes = read_georef(document.doc)
        write_georef(document.doc, Georef(crs=self.code) if self.code else None)
        document.dirty = True

    def undo(self, document) -> None:
        write_georef(document.doc, self._antes)
        document.dirty = True


def cantidad_de_objetos(doc) -> int:
    return len(doc.modelspace())


# ================================================================== reproyectar

class Proyeccion:
    """De un sistema a otro con PROJ. ``xy`` convierte un punto; ``giro``
    dice cuántos grados gira localmente el norte (la convergencia), para
    corregir el ángulo de textos, bloques y arcos."""

    def __init__(self, origen: str, destino: str) -> None:
        try:
            from pyproj import Transformer
        except ImportError as exc:
            raise SinProj("pyproj no está instalado") from exc
        self.origen, self.destino = origen, destino
        self.t = Transformer.from_crs(origen, destino, always_xy=True)

    def xy(self, x: float, y: float) -> tuple[float, float]:
        X, Y = self.t.transform(x, y)
        if not (math.isfinite(X) and math.isfinite(Y)):
            raise ValueError("punto fuera del área del sistema")
        return X, Y

    def giro(self, x: float, y: float) -> float:
        x0, y0 = self.xy(x, y)
        x1, y1 = self.xy(x + 1.0, y)
        return math.degrees(math.atan2(y1 - y0, x1 - x0))

    def descripcion(self) -> str:
        """Qué conversión usa PROJ y con qué precisión."""
        texto = getattr(self.t, "description", "") or "conversión de PROJ"
        acc = getattr(self.t, "accuracy", -1)
        if acc is not None and acc >= 0:
            texto += f" (precisión ≈ {acc:g} m)"
        elif _datum(self.origen) != _datum(self.destino):
            texto += " (precisión sin dato: cambia el datum)"
        return texto


def _datum(code: str) -> str:
    n = _epsg(code) or 0
    for nombre_d, base, geo in crs_mod.DATUMS:
        if base <= n < base + 7 or n == geo:
            return nombre_d
    return "WGS 84" if 32600 < n < 32800 or n == 4326 else code


class NoSeConvierte(Exception):
    """Un objeto que REPROYECTAR no sabe convertir (el motivo va en args[0])."""


def _p3(v):
    return (v[0], v[1], v[2] if len(v) > 2 else 0.0)


def _xyz(proy, v):
    x, y, z = _p3(v)
    X, Y = proy.xy(x, y)
    return (X, Y, z)


def _girar_vector(v, grados):
    a = math.radians(grados)
    x, y, z = _p3(v)
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), z)


def _plano(e) -> bool:
    ext = e.dxf.get("extrusion", (0.0, 0.0, 1.0))
    return abs(ext[0]) < 1e-9 and abs(ext[1]) < 1e-9 and ext[2] > 0


def _hatch_paths(e, proy, giro):
    from ezdxf.entities.boundary_paths import EdgePath, PolylinePath
    for path in e.paths:
        if isinstance(path, PolylinePath):
            path.vertices = [(*proy.xy(v[0], v[1]), *(v[2:] if len(v) > 2 else (0.0,)))
                             for v in path.vertices]
        elif isinstance(path, EdgePath):
            for edge in path.edges:
                t = type(edge).__name__
                if t == "LineEdge":
                    edge.start, edge.end = proy.xy(*edge.start[:2]), proy.xy(*edge.end[:2])
                elif t == "ArcEdge":
                    edge.center = proy.xy(*edge.center[:2])
                    edge.start_angle += giro
                    edge.end_angle += giro
                elif t == "EllipseEdge":
                    edge.center = proy.xy(*edge.center[:2])
                    edge.major_axis = _girar_vector(edge.major_axis, giro)[:2]
                    # sus ángulos se miden desde el eje mayor: giran con él
                elif t == "SplineEdge":
                    edge.control_points = [proy.xy(*p[:2]) for p in edge.control_points]
                    edge.fit_points = [proy.xy(*p[:2]) for p in edge.fit_points]
                else:
                    raise NoSeConvierte("HATCH")
    if e.seeds:
        e.seeds = [proy.xy(*s[:2]) for s in e.seeds]


def reproyectar_entidad(e, proy: Proyeccion, document=None) -> None:
    """Convierte ``e`` en su lugar. NoSeConvierte si no sabe."""
    t = e.dxftype()
    d = e.dxf
    if t in ("LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT", "INSERT", "HATCH",
             "SOLID", "TRACE", "ELLIPSE") and not _plano(e):
        raise NoSeConvierte(f"{t} fuera del plano XY")
    if t == "POINT":
        d.location = _xyz(proy, d.location)
    elif t == "LINE":
        d.start, d.end = _xyz(proy, d.start), _xyz(proy, d.end)
    elif t == "LWPOLYLINE":
        pts = [(*proy.xy(x, y), sw, ew, b) for x, y, sw, ew, b in e.get_points("xyseb")]
        e.set_points(pts, format="xyseb")
    elif t == "POLYLINE":
        if e.is_poly_face_mesh or e.is_polygon_mesh:
            raise NoSeConvierte("malla")
        for v in e.vertices:
            v.dxf.location = _xyz(proy, v.dxf.location)
    elif t == "CIRCLE":
        d.center = _xyz(proy, d.center)
    elif t == "ARC":
        g = proy.giro(d.center[0], d.center[1])
        d.center = _xyz(proy, d.center)
        d.start_angle = (d.start_angle + g) % 360.0
        d.end_angle = (d.end_angle + g) % 360.0
    elif t == "ELLIPSE":
        g = proy.giro(d.center[0], d.center[1])
        d.center = _xyz(proy, d.center)
        d.major_axis = _girar_vector(d.major_axis, g)
    elif t in ("TEXT", "ATTRIB", "ATTDEF"):
        g = proy.giro(d.insert[0], d.insert[1])
        d.insert = _xyz(proy, d.insert)
        if d.hasattr("align_point"):
            d.align_point = _xyz(proy, d.align_point)
        d.rotation = (d.get("rotation", 0.0) + g) % 360.0
    elif t == "MTEXT":
        g = proy.giro(d.insert[0], d.insert[1])
        d.insert = _xyz(proy, d.insert)
        if d.hasattr("text_direction"):
            d.text_direction = _girar_vector(d.text_direction, g)
        else:
            d.rotation = (d.get("rotation", 0.0) + g) % 360.0
    elif t == "INSERT":
        g = proy.giro(d.insert[0], d.insert[1])
        d.insert = _xyz(proy, d.insert)
        d.rotation = (d.get("rotation", 0.0) + g) % 360.0
        for a in e.attribs:
            reproyectar_entidad(a, proy, document)
    elif t == "SPLINE":
        if e.control_point_count():
            e.control_points = [_xyz(proy, p) for p in e.control_points]
        if e.fit_point_count():
            e.fit_points = [_xyz(proy, p) for p in e.fit_points]
    elif t == "HATCH":
        pts = [v for p in e.paths for v in getattr(p, "vertices", [])[:1]]
        x, y = (pts[0][0], pts[0][1]) if pts else (0.0, 0.0)
        _hatch_paths(e, proy, proy.giro(x, y))
    elif t in ("SOLID", "TRACE", "3DFACE"):
        for k in ("vtx0", "vtx1", "vtx2", "vtx3"):
            if d.hasattr(k):
                setattr(d, k, _xyz(proy, getattr(d, k)))
    elif t in ("IMAGE", "WIPEOUT"):
        g = proy.giro(d.insert[0], d.insert[1])
        d.insert = _xyz(proy, d.insert)
        d.u_pixel = _girar_vector(d.u_pixel, g)
        d.v_pixel = _girar_vector(d.v_pixel, g)
    elif t == "LEADER":
        e.vertices = [_xyz(proy, v) for v in e.vertices]
    elif t == "DIMENSION":
        from core import actions
        redibujar = getattr(actions, "redraw_transformed_dimension", None)
        if redibujar is None or getattr(actions, "snapshot_entity", None) is None:
            raise NoSeConvierte("cota (IngeCAD 0.6.7 o más nuevo)")
        for k in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint"):
            if d.hasattr(k):
                setattr(d, k, _xyz(proy, getattr(d, k)))
        if document is not None:
            redibujar(document, e)
    else:
        raise NoSeConvierte(t)


def _foto(e):
    """La copia del objeto y, si es un bloque, la de cada atributo (IngeCAD
    0.6.6 no devolvía los atributos al restaurar el bloque)."""
    from core import actions
    snap = getattr(actions, "snapshot_entity", None) or (lambda x: x.copy())
    attribs = [(a, snap(a)) for a in e.attribs] if e.dxftype() == "INSERT" else []
    return snap(e), attribs


def _restaurar(e, foto) -> None:
    from core import actions
    copia, attribs = foto
    actions._restore_entity(e, copia)
    for a, copia_a in attribs:
        actions._restore_entity(a, copia_a)


def conectada(e) -> bool:
    """El objeto es de una capa conectada (CONECTARSHP): no se reproyecta."""
    from . import enlace
    return enlace.feat_tag(e) is not None


class ReproyectarCommand(Command):
    """REPROYECTAR como UN paso de deshacer: convierte ``entidades`` y deja
    declarado ``destino``. Deshacer devuelve a cada objeto su copia exacta
    de antes y el sistema que estaba declarado."""

    name = "reproyectar"

    def __init__(self, entidades, proy: Proyeccion, ventanas=()) -> None:
        self.entidades = list(entidades)
        self.ventanas = list(ventanas)
        self.proy = proy
        self.hechos: list = []
        self.salteados: Counter = Counter()
        self._georef_antes = None

    def do(self, document) -> None:
        self.hechos, self.salteados = [], Counter()
        for e in self.entidades:
            foto = _foto(e)
            try:
                reproyectar_entidad(e, self.proy, document)
            except NoSeConvierte as exc:
                _restaurar(e, foto)
                self.salteados[str(exc.args[0]) if exc.args else e.dxftype()] += 1
                continue
            except Exception:  # noqa: BLE001 -- fuera del sistema u otro error: queda como estaba
                _restaurar(e, foto)
                self.salteados[f"{e.dxftype()} (no se pudo convertir)"] += 1
                continue
            self.hechos.append((e, foto))
        for vp in self.ventanas:             # las ventanas del papel siguen mirando lo mismo
            foto = _foto(vp)
            try:
                c = vp.dxf.view_center_point
                vp.dxf.view_center_point = self.proy.xy(c[0], c[1])
                self.hechos.append((vp, foto))
            except Exception:  # noqa: BLE001
                _restaurar(vp, foto)
        self._georef_antes = read_georef(document.doc)
        write_georef(document.doc, Georef(crs=self.proy.destino))
        document.dirty = True

    def undo(self, document) -> None:
        for e, foto in reversed(self.hechos):
            _restaurar(e, foto)
        self.hechos = []
        write_georef(document.doc, self._georef_antes)
        document.dirty = True


def ventanas_del_papel(doc) -> list:
    """Las ventanas de las presentaciones que miran el modelo sin giro."""
    out = []
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        for vp in layout.query("VIEWPORT"):
            if vp.dxf.get("id", 0) == 1:              # la de la hoja misma
                continue
            if abs(vp.dxf.get("view_twist_angle", 0.0)) > 1e-9:
                continue
            tgt = vp.dxf.get("view_target_point", (0, 0, 0))
            if any(abs(c) > 1e-9 for c in tgt):
                continue
            out.append(vp)
    return out


def preparar_reproyeccion(doc, destino: str, entidades=None):
    """(comando, cantidad de conectados que no se tocan). ``entidades`` None
    = todo el modelo (y entonces también las ventanas del papel)."""
    origen = sistema_del_dibujo(doc)
    if not origen:
        raise ValueError("el dibujo no tiene sistema de coordenadas: defínalo primero (SISTEMAGEO)")
    if origen == destino:
        raise ValueError("el dibujo ya está en ese sistema")
    todo = entidades is None
    entidades = list(doc.modelspace()) if todo else list(entidades)
    conectados = [e for e in entidades if conectada(e)]
    libres = [e for e in entidades if not conectada(e)]
    proy = Proyeccion(origen, destino)
    return ReproyectarCommand(libres, proy, ventanas_del_papel(doc) if todo else ()), len(conectados)


def resumen_reproyeccion(cmd: ReproyectarCommand, conectados: int) -> str:
    n = sum(1 for e, _f in cmd.hechos if e.dxftype() != "VIEWPORT")
    texto = (f"Reproyectado a {nombre(cmd.proy.destino)}: {n} objeto(s) convertidos con "
             f"{cmd.proy.descripcion()}.")
    if cmd.salteados:
        texto += " Quedaron como estaban: " + ", ".join(
            f"{k} {v}" for k, v in sorted(cmd.salteados.items())) + "."
    if conectados:
        texto += (f" {conectados} objeto(s) de capas conectadas (CONECTARSHP) no se tocaron: "
                  "su archivo manda; desconéctelas y vuelva a conectarlas, o reproyéctelas en QGIS.")
    return texto + " U lo deshace."


# ================================================================== atributos en los objetos

# (poner_atributos y atributos están en importados.py)


# ================================================================== IMPORTAR SHP

@dataclass
class OpcionesImportar:
    capa: str = "archivo"           # archivo | fija | campo
    capa_fija: str = "SHP"
    campo_capa: str = ""
    atributos: bool = True
    columnas: Optional[dict] = None  # {ruta .shp: [campos]} que se copian al dibujo; None = todos (3.25.5)
    puntos: str = "punto"           # punto | bloque | texto
    bloque: str = ""
    campo_texto: str = ""
    altura: float = 2.5             # puntos como texto, en unidades del dibujo
    color: int = 7                  # ACI de las capas que se crean
    grosor: int = -3                # espesor de línea de esas capas (centésimas de mm; -3 = por defecto)
    sistema_shp: dict = field(default_factory=dict)   # {ruta .shp: «EPSG:» o ""} si no hay .prj
    adoptar: bool = True            # dibujo sin sistema: adoptar el del primer SHP


@dataclass
class VistaShp:
    """Lo que la ventana muestra de un archivo antes de importarlo."""
    ruta: Path
    tipo: str
    cantidad: int
    campos: list
    sistema: str
    codificacion: str
    muestra: list = field(default_factory=list)    # primeros registros, como texto (vista previa)


def ver_shp(ruta, filas: int = 8) -> VistaShp:
    sf = shpio.Shapefile(ruta)
    campos = [f.name for f in sf.fields]
    muestra = []
    for i in range(len(sf)):
        if len(muestra) >= filas:
            break
        if sf.is_deleted(i):
            continue
        valores = sf.attributes(i)
        muestra.append([shpio.display_value(valores.get(c)) for c in campos])
    return VistaShp(Path(sf.shp_path), shpio.SHAPE_NAMES.get(sf.shape_type, str(sf.shape_type)),
                    sum(1 for i in range(len(sf)) if not sf.is_deleted(i)),
                    campos, sistema_de_prj(sf.shp_path), sf.encoding, muestra)


_CAPA_MALA = re.compile(r'[<>/\\":;?*|=`]')


def nombre_de_capa(texto: str, defecto: str = "SHP") -> str:
    limpio = _CAPA_MALA.sub("_", str(texto or "").strip())[:255]
    return limpio or defecto


@dataclass
class PlanImportar:
    comando: CompositeCommand
    objetos: int
    por_archivo: list               # [(nombre, registros, objetos, sistema, conversión)]
    avisos: list
    sistema_adoptado: str = ""
    tablas: list = field(default_factory=list)     # tablas de atributos creadas


def plan_importar(doc, rutas, op: OpcionesImportar) -> PlanImportar:
    """Lo que IMPORTARSHP agrega, como UN paso de deshacer."""
    destino = sistema_del_dibujo(doc)
    adoptado = ""
    capas_nuevas, fabricas, por_archivo, avisos = [], [], [], []
    capas_existentes = {l.dxf.name.lower() for l in doc.layers}
    from . import enlace, importados
    tablas_usadas = set(importados.tablas(doc)) | set(enlace.read_links(doc))
    tablas = []
    total = 0

    def capa_para(nombre_c: str) -> str:
        nombre_c = nombre_de_capa(nombre_c)
        if nombre_c.lower() not in capas_existentes:
            capas_existentes.add(nombre_c.lower())
            capas_nuevas.append(nombre_c)
        return nombre_c

    for ruta in rutas:
        sf = shpio.Shapefile(ruta)
        nombre_a = Path(sf.shp_path).stem
        sistema = sistema_de_prj(sf.shp_path) or op.sistema_shp.get(str(Path(ruta)), "")
        if not destino and sistema and op.adoptar and not adoptado:
            adoptado = destino = sistema
        proy, conversion = None, "como viene"
        if sistema and sistema == destino:
            conversion = f"ya en {nombre(destino)}"
        elif sistema and destino:
            proy = Proyeccion(sistema, destino)
            conversion = f"de {nombre(sistema)} a {nombre(destino)}"
        elif not sistema:
            conversion = "como viene (sin sistema)"
            if destino:
                avisos.append(f"{nombre_a}: no tiene .prj ni se eligió su sistema; entra como "
                              f"viene, sin convertir a {nombre(destino)}.")
        elif sistema and not destino:
            conversion = f"como viene ({nombre(sistema)}; el dibujo queda sin sistema)"
        st = sf.shape_type
        if st in shpio.POINT_TYPES or st in (shpio.MULTIPOINT, shpio.MULTIPOINTZ, shpio.MULTIPOINTM):
            tipo = "punto"
        elif st in shpio.POLYGON_TYPES:
            tipo = "poligono"
        elif st in shpio.LINE_TYPES:
            tipo = "linea"
        else:
            avisos.append(f"{nombre_a}: el tipo {shpio.SHAPE_NAMES.get(st, st)} no se importa.")
            continue
        bloque_ok = op.puntos == "bloque" and op.bloque and op.bloque in doc.blocks
        if op.puntos == "bloque" and tipo == "punto" and not bloque_ok:
            avisos.append(f"{nombre_a}: el bloque «{op.bloque}» no está en el dibujo; "
                          "los puntos entran como puntos.")
        # sólo las columnas elegidas: el .dbf de origen no se toca (3.25.5)
        elegidas = None if op.columnas is None else set(op.columnas.get(str(Path(ruta)), ()))
        campos_a = [f for f in sf.fields if elegidas is None or f.name in elegidas]
        con_base = op.atributos and bool(campos_a)
        tabla = nombre_a
        if con_base:
            tabla = importados.nombre_libre(nombre_a, tablas_usadas)
            tablas_usadas.add(tabla)
        registros = objetos = sin_geo = 0
        for i in range(len(sf)):
            if sf.is_deleted(i):
                continue
            geom = sf.geometry(i)
            if geom.is_null:
                sin_geo += 1
                continue
            registros += 1
            valores = sf.attributes(i)
            partes = geom.parts
            if proy is not None:
                try:
                    partes = [[proy.xy(x, y) for x, y in parte] for parte in partes]
                except Exception:  # noqa: BLE001
                    sin_geo += 1
                    continue
            if op.capa == "fija":
                capa = capa_para(op.capa_fija)
            elif op.capa == "campo" and op.campo_capa:
                capa = capa_para(shpio.display_value(valores.get(op.campo_capa)) or nombre_a)
            else:
                capa = capa_para(nombre_a)
            zs = geom.z
            for n_parte, parte in enumerate(partes):
                z = zs[n_parte][0] if (tipo == "punto" and zs) else 0.0
                fabricas.append((capa, _fabrica(tipo, parte, z, op, bloque_ok, valores,
                                                tabla, campos_a if con_base else None, i)))
                objetos += 1
        if sin_geo:
            avisos.append(f"{nombre_a}: {sin_geo} registro(s) sin geometría (o fuera del sistema) "
                          "no entraron.")
        por_archivo.append((nombre_a, registros, objetos, sistema, conversion))
        if con_base and registros:
            tablas.append(tabla)
        total += objetos
    comandos: list = []
    if adoptado:
        comandos.append(DefinirSistemaCommand(adoptado))
    comandos += [NewLayerCommand(c, color=op.color, lineweight=op.grosor) for c in capas_nuevas]
    usadas = {c for c, _f in fabricas}
    viejas = sorted(c for c in usadas if c not in capas_nuevas)
    if viejas:
        avisos.append("Las capas que ya estaban (" + ", ".join(viejas) + ") conservan su color "
                      "y espesor.")
    comandos += [AddToModelCommand("IMPORTARSHP", f, layer=c) for c, f in fabricas]
    return PlanImportar(CompositeCommand("importar SHP", comandos), total, por_archivo, avisos,
                        adoptado, tablas)


def _abrir(parte):
    if len(parte) > 1 and parte[0] == parte[-1]:
        return parte[:-1]
    return parte


def _fabrica(tipo, parte, z, op: OpcionesImportar, bloque_ok, valores, origen, campos, fid=None):
    def make(msp):
        if tipo == "punto":
            x, y = parte[0]
            if op.puntos == "bloque" and bloque_ok:
                e = msp.add_blockref(op.bloque, (x, y, z))
            elif op.puntos == "texto" and op.campo_texto:
                e = msp.add_text(shpio.display_value(valores.get(op.campo_texto)) or "?",
                                 dxfattribs={"height": op.altura, "insert": (x, y, z)})
            else:
                e = msp.add_point((x, y, z))
        elif tipo == "poligono":
            e = msp.add_lwpolyline(_abrir(parte), format="xy", close=True)
        else:
            e = msp.add_lwpolyline(parte, format="xy")
        if campos is not None:
            poner_atributos(e, origen, campos, valores, fid)
        return e
    return make


def resumen_importar(plan: PlanImportar) -> str:
    partes = [f"{n}: {r} registro(s), {o} objeto(s), {c}" for n, r, o, _s, c in plan.por_archivo]
    texto = f"Importado: {plan.objetos} objeto(s). " + "; ".join(partes) + "."
    if plan.sistema_adoptado:
        texto += f" El dibujo adoptó el sistema {nombre(plan.sistema_adoptado)}."
    if plan.tablas:
        texto += (" Base de datos: " + ", ".join(f"«{t}»" for t in plan.tablas)
                  + " en la Tabla de atributos (TABLASIG); rótulos con ROTULOSIG.")
    if plan.avisos:
        texto += " " + " ".join(plan.avisos)
    return texto + " U lo deshace."


# ================================================================== EXPORTAR SHP

TIPOS_SHP = {"puntos": shpio.POINT, "lineas": shpio.POLYLINE, "poligonos": shpio.POLYGON}

#: los campos que pone GeoCAD (además de los atributos que traen los objetos)
CAMPOS_FIJOS = [("LAYER", "C", 80, 0), ("COLOR", "C", 7, 0), ("TIPO_CAD", "C", 12, 0)]
CAMPOS_PUNTOS = [("TEXTO", "C", 254, 0), ("ALTURA", "N", 12, 3), ("GIRO", "N", 10, 4),
                 ("BLOQUE", "C", 64, 0), ("ESCALA", "N", 12, 4)]


def _anillo_cerrado(pts):
    pts = [tuple(p[:2]) for p in pts]
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _horario(anillo, horario: bool):
    """ESRI: el borde en sentido horario, los huecos antihorario."""
    a = shpio.signed_area(anillo[:-1] if anillo[0] == anillo[-1] else anillo)
    return anillo if (a < 0) == horario else list(reversed(anillo))


def geometria_de(e, doc, cerradas_como_poligono: bool = True, tolerancia: float = TOLERANCIA):
    """(tipo, partes, extra) de un objeto, o (None, motivo, None).
    tipo: puntos | lineas | poligonos."""
    from . import aqgis
    t = e.dxftype()
    extra = {}
    if t == "POINT":
        p = e.dxf.location
        return "puntos", [[(p[0], p[1])]], extra
    if t == "INSERT":
        p = e.dxf.insert
        extra = {"BLOQUE": e.dxf.name, "GIRO": f"{e.dxf.get('rotation', 0.0):.4f}",
                 "ESCALA": f"{e.dxf.get('xscale', 1.0):.4f}"}
        return "puntos", [[(p[0], p[1])]], extra
    if t in ("TEXT", "MTEXT"):
        p = e.dxf.insert
        if t == "TEXT":
            texto, altura = e.dxf.get("text", ""), e.dxf.get("height", 0.0)
            giro = e.dxf.get("rotation", 0.0)
            alin = e.get_align_enum() if hasattr(e, "get_align_enum") else None
            if alin is not None and getattr(alin, "name", "LEFT") != "LEFT" and e.dxf.hasattr("align_point"):
                p = e.dxf.align_point
        else:
            texto, altura = e.plain_text(), e.dxf.get("char_height", 0.0)
            giro = e.get_rotation() if hasattr(e, "get_rotation") else e.dxf.get("rotation", 0.0)
        extra = {"TEXTO": texto.replace("\n", " ")[:254], "ALTURA": f"{altura:.3f}",
                 "GIRO": f"{giro % 360.0:.4f}"}
        return "puntos", [[(p[0], p[1])]], extra
    if t == "HATCH":
        from ezdxf import path as ezpath
        anillos = [_anillo_cerrado([(v.x, v.y) for v in p.flattening(tolerancia, segments=8)])
                   for p in ezpath.from_hatch(e)]
        anillos = [a for a in anillos if len(a) >= 4]
        if not anillos:
            return None, "sombreado sin borde", None
        anillos.sort(key=lambda a: abs(shpio.signed_area(a[:-1])), reverse=True)
        return "poligonos", [_horario(anillos[0], True)] + [_horario(a, False) for a in anillos[1:]], extra
    if t in aqgis._TRAZOS:
        try:
            pts = aqgis._limpios(aqgis._vertices(e, tolerancia))
        except Exception:  # noqa: BLE001
            return None, t, None
        if aqgis._cerrado(e) and cerradas_como_poligono:
            anillo = _anillo_cerrado(pts)
            if len(anillo) >= 4:
                return "poligonos", [_horario(anillo, True)], extra
        if aqgis._cerrado(e) and pts and pts[0] != pts[-1]:
            pts = pts + [pts[0]]
        if len(pts) >= 2:
            return "lineas", [pts], extra
        return None, "objeto sin largo", None
    return None, t, None


def _nombre_campo(nombre_c: str, usados: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", nombre_c.upper())[:10] or "CAMPO"
    out, n = base, 1
    while out in usados:
        sufijo = str(n)
        out = base[:10 - len(sufijo)] + sufijo
        n += 1
    usados.add(out)
    return out


def nombre_de_archivo(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", str(texto).strip()) or "capa"


@dataclass
class Grupo:
    """Un shapefile a escribir."""
    archivo: str
    tipo: str
    elementos: list = field(default_factory=list)   # [(partes, {campo: texto}, atributos)]


@dataclass
class PlanExportar:
    grupos: list
    salteados: Counter
    origen: str
    destino: str

    def archivos(self, carpeta) -> list[Path]:
        carpeta = Path(carpeta)
        return [carpeta / f"{g.archivo}.shp" for g in self.grupos]

    def existentes(self, carpeta) -> list[Path]:
        """Los archivos que ya están (y se pisarían): hay que preguntar antes."""
        out = []
        for shp in self.archivos(carpeta):
            out += [shp.with_suffix(x) for x in (".shp", ".shx", ".dbf", ".prj", ".cpg")
                    if shp.with_suffix(x).exists()]
        return out


def plan_exportar(entidades, doc, modo: str = "capa", nombre_base: str = "dibujo",
                  destino: str = "", cerradas_como_poligono: bool = True) -> PlanExportar:
    """``modo``: «capa» = un archivo por capa y tipo (CAPA_lineas...); «tipo» =
    un archivo por tipo con todas las capas y el campo LAYER."""
    from . import aqgis
    origen = sistema_del_dibujo(doc)
    destino = destino or origen
    if not destino:
        raise ValueError("el dibujo no tiene sistema de coordenadas: elija en cuál exportar")
    if not origen and destino:
        origen = destino                # sin sistema declarado: se escriben como están
    proy = Proyeccion(origen, destino) if origen != destino else None
    grupos: dict = {}
    salteados = Counter()
    for e in entidades:
        try:
            tipo, partes, extra = geometria_de(e, doc, cerradas_como_poligono)
        except Exception:  # noqa: BLE001
            tipo, partes, extra = None, e.dxftype(), None
        if tipo is None:
            salteados[partes] += 1
            continue
        if proy is not None:
            try:
                partes = [[proy.xy(x, y) for x, y in parte] for parte in partes]
            except Exception:  # noqa: BLE001
                salteados[f"{e.dxftype()} fuera del sistema"] += 1
                continue
        capa = e.dxf.get("layer", "0")
        valores = {"LAYER": capa, "COLOR": aqgis.color_de(e, doc), "TIPO_CAD": e.dxftype()}
        valores.update(extra)
        _origen, attrs = atributos(e)
        archivo = (nombre_de_archivo(f"{capa}_{tipo}") if modo == "capa"
                   else nombre_de_archivo(f"{nombre_base}_{tipo}"))
        g = grupos.setdefault((archivo, tipo), Grupo(archivo, tipo))
        g.elementos.append((partes, valores, attrs))
    return PlanExportar(list(grupos.values()), salteados, origen, destino)


def _campos_de(grupo: Grupo):
    """[(nombre, tipo, ancho, dec)] y, por elemento, {nombre dbf: texto}."""
    usados: set = set()
    campos = []
    for n, t, s, d in CAMPOS_FIJOS + (CAMPOS_PUNTOS if grupo.tipo == "puntos" else []):
        campos.append((_nombre_campo(n, usados), t, s, d))
    propios: dict = {}                       # nombre original -> (tipo, ancho, dec)
    for _p, _v, attrs in grupo.elementos:
        for n, defi, _texto in attrs:
            if n not in propios:
                propios[n] = defi
            elif propios[n] != defi:
                propios[n] = ("C", 254, 0)    # dos esquemas distintos: texto
    renombre = {}
    for n, (t, s, d) in propios.items():
        if t not in "CNFDL":
            t, s, d = "C", 254, 0
        nuevo = _nombre_campo(n, usados)
        renombre[n] = nuevo
        campos.append((nuevo, t, s, d))
    filas = []
    for partes, valores, attrs in grupo.elementos:
        fila = dict(valores)
        for n, _defi, texto in attrs:
            fila[renombre[n]] = texto
        filas.append((partes, fila))
    return campos, filas


def escribir(plan: PlanExportar, carpeta) -> list[tuple[Path, int]]:
    """Escribe cada shapefile con su .prj. [(ruta, registros)].
    Un valor que no entra en su campo hace que el campo pase a texto."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    prj = wkt_prj(plan.destino)
    hechos = []
    for g in plan.grupos:
        campos, filas = _campos_de(g)
        shp = carpeta / f"{g.archivo}.shp"
        st = TIPOS_SHP[g.tipo]
        geoms = [(shpio.Geometry(st, partes), fila) for partes, fila in filas]
        try:
            n = shpio.escribir_nuevo(shp, st, campos, geoms)
        except shpio.ShapefileError:
            campos = [c if c[1] == "C" or c[0] in ("ALTURA", "GIRO", "ESCALA") else (c[0], "C", 254, 0)
                      for c in campos]
            n = shpio.escribir_nuevo(shp, st, campos, geoms)
        shp.with_suffix(".prj").write_text(prj)
        hechos.append((shp, n))
    return hechos


def resumen_exportar(plan: PlanExportar, hechos) -> str:
    archivos = ", ".join(f"{p.name} ({n})" for p, n in hechos)
    texto = f"Exportado en {nombre(plan.destino)}: {archivos}."
    if plan.origen != plan.destino:
        texto += f" Reproyectado desde {nombre(plan.origen)}."
    if plan.salteados:
        texto += " No se exportaron: " + ", ".join(
            f"{k} {v}" for k, v in sorted(plan.salteados.items())) + "."
    return texto


# ================================================================== las órdenes

def _orden(nombre_ui: str, funcion: str):
    def cmd(ctx, *args) -> None:
        if ctx.document is None:
            ctx.echo(f"{nombre_ui}: no hay un dibujo abierto.")
            return
        try:
            from . import intercambio_ui
        except Exception:  # noqa: BLE001 -- sin Qt
            ctx.echo(f"{nombre_ui} necesita la ventana de IngeCAD.")
            return
        try:
            getattr(intercambio_ui, funcion)(ctx)
        except SinProj:
            ctx.echo(f"{nombre_ui}: este IngeCAD no trae pyproj (PROJ); no se puede convertir "
                     "entre sistemas. Sí se puede declarar el sistema con SISTEMAGEO.")
    cmd.__name__ = f"cmd_{funcion}"
    return cmd


COMMANDS = {
    "GEOCRS": _orden("SISTEMAGEO", "sistema"),
    "GEOREPROJECT": _orden("REPROYECTAR", "reproyectar"),
    "GEOIMPORTSHP": _orden("IMPORTARSHP", "importar"),
    "GEOEXPORTSHP": _orden("EXPORTARSHP", "exportar"),
}
