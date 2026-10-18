# SPDX-License-Identifier: GPL-3.0-or-later
"""EXPORTARKML (3.29.0, módulo «Intercambio»): lo elegido del dibujo a un
KMZ (o KML) para Google Earth, siempre en WGS 84. IMPORTARKML (3.30.0), al
final: un KML o KMZ al sistema del dibujo, una capa por carpeta, con sus
colores y sus datos extendidos como atributos.

* Las coordenadas salen del sistema del dibujo (SISTEMAGEO) con PROJ
  (intercambio.Proyeccion hacia EPSG:4326). Sin sistema no se exporta: la
  ventana lo pregunta y lo deja asignado.
* La geometría es la de EXPORTARSHP (intercambio.geometria_de): arcos y
  círculos a tramos de 1 cm, polilíneas cerradas y sombreados como
  polígonos (los sombreados con sus huecos y sus islas sueltas), textos y
  bloques como marcadores.
* Una carpeta por capa (se prenden y apagan en Google Earth) o todo junto.
  Cada objeto lleva el color de su capa u objeto y su grosor; los
  polígonos, un relleno con la opacidad elegida.
* Los atributos de IMPORTARSHP (y los de un bloque) van como ExtendedData:
  la tabla del globo de Google Earth.
* Todo pegado al suelo (clampToGround), como KMLOUT de Terreno: Google
  Earth nunca entierra un borde bajo su relieve.

Del KMLOUT de Terreno (IngeCAD 0.6.7) se toman los formatos ya probados con
Google Earth (color aabbggrr, tessellate, 9 decimales = 0,1 mm, el KMZ como
un zip con doc.kml); no se lo llama, porque es interno de otro complemento
y no escribe carpetas, grosores ni datos extendidos.
"""
from __future__ import annotations

import html
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import intercambio as IX

KML_NS = "http://www.opengis.net/kml/2.2"
WGS84 = "EPSG:4326"
RELLENO = 40            # % de opacidad del relleno de los polígonos, si no se elige otro
#: los grosores de CAD (mm) en píxeles de Google Earth: 0,25 mm (el normal) = 2 px
PX_POR_MM = 6.0
PX_MIN = 2.0
GROSOR_NORMAL = 25      # centésimas de mm: «Por defecto» de AutoCAD e IngeCAD


def _q(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


# ------------------------------------------------------------------ estilo
def color_kml(hex_rgb: str, alfa: int = 255) -> str:
    """«#rrggbb» -> el «aabbggrr» de KML."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"{max(0, min(255, int(alfa))):02x}{b}{g}{r}".lower()


def _capa(e, doc):
    try:
        return doc.layers.get(e.dxf.get("layer", "0"))
    except Exception:  # noqa: BLE001
        return None


def color_de(e, doc) -> str:
    """El color con que se ve el objeto (el propio o el de su capa). El
    blanco/negro de CAD (ACI 7) sale blanco: sobre la imagen satelital de
    Google Earth se ve, como sobre el fondo oscuro de IngeCAD."""
    from . import aqgis
    if not e.dxf.hasattr("true_color"):
        aci = e.dxf.get("color", 256)
        if aci in (0, 256):
            capa = _capa(e, doc)
            if capa is not None and not capa.dxf.hasattr("true_color"):
                aci = abs(int(capa.dxf.get("color", 7) or 7))
        if aci == 7:
            return "#ffffff"
    return aqgis.color_de(e, doc)


def grosor_de(e, doc) -> int:
    """El grosor del objeto en centésimas de mm (PorCapa = el de su capa)."""
    lw = e.dxf.get("lineweight", -1)
    if lw == -1:
        capa = _capa(e, doc)
        lw = capa.dxf.get("lineweight", -3) if capa is not None else -3
    if lw is None or lw < 0:
        lw = GROSOR_NORMAL
    return int(lw)


def grosor_px(lw: int) -> float:
    return round(max(PX_MIN, lw / 100.0 * PX_POR_MM), 1)


# ------------------------------------------------------------------ geometría
def _dentro(p, anillo) -> bool:
    """Punto en polígono (par-impar)."""
    x, y = p
    adentro = False
    n = len(anillo)
    for i in range(n):
        x1, y1 = anillo[i]
        x2, y2 = anillo[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            adentro = not adentro
    return adentro


def poligonos(anillos) -> list:
    """Los anillos de un sombreado como [(borde, [huecos])]: un anillo dentro
    de un número par de otros es un borde; dentro de uno impar, un hueco del
    borde más chico que lo contiene (islas sueltas = polígonos aparte)."""
    anillos = [a for a in anillos if len(a) >= 4]
    anillos.sort(key=lambda a: abs(IX.shpio.signed_area(a[:-1])), reverse=True)
    contiene = []
    for i, a in enumerate(anillos):
        contiene.append([j for j in range(i) if _dentro(a[0], anillos[j])])
    out, borde_de = [], {}
    for i, a in enumerate(anillos):
        if len(contiene[i]) % 2 == 0:
            borde_de[i] = len(out)
            out.append((a, []))
        else:
            padre = max((j for j in contiene[i] if j in borde_de), default=None)
            if padre is None:
                borde_de[i] = len(out)
                out.append((a, []))
            else:
                out[borde_de[padre]][1].append(a)
    return out


def _largo(pts) -> float:
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def _num(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


# ------------------------------------------------------------------ el plan
@dataclass
class Marca:
    """Un Placemark."""
    tipo: str                       # punto | texto | bloque | linea | poligono
    geometria: list                 # punto: [(lon, lat)]; linea: [pts]; poligono: [(borde, [huecos])]
    nombre: str
    capa: str
    color: str                      # #rrggbb
    grosor: int                     # centésimas de mm
    descripcion: str = ""
    datos: list = field(default_factory=list)      # [(nombre, texto)]
    sombreado: bool = False


@dataclass
class PlanKml:
    marcas: list
    salteados: Counter
    origen: str
    titulo: str
    por_capa: bool = True
    relleno: int = RELLENO

    def carpetas(self) -> list[tuple[str, list]]:
        if not self.por_capa:
            return [("", self.marcas)]
        grupos: dict = {}
        for m in self.marcas:
            grupos.setdefault(m.capa, []).append(m)
        return sorted(grupos.items(), key=lambda kv: kv[0].lower())


def campos_de(entidades) -> list[str]:
    """Los nombres de los atributos de IMPORTARSHP que traen los objetos
    (para elegir de cuál sale el nombre de cada uno)."""
    vistos: dict = {}
    for e in entidades:
        for n, _d, _t in IX.atributos(e)[1]:
            vistos.setdefault(n, None)
    return list(vistos)


def nombre_automatico(nombre: str) -> bool:
    """Bloques con nombre puesto por el programa, que no le dicen nada a
    nadie: los anónimos (*U12, *D3) y los de copiar y pegar de AutoCAD
    (A$C1F2E3D4B)."""
    return nombre.startswith("*") or re.fullmatch(r"A\$C[0-9A-Fa-f]{8}", nombre) is not None


def _datos_bloque(e) -> list:
    try:
        return [(a.dxf.tag, a.dxf.text) for a in e.attribs]
    except Exception:  # noqa: BLE001
        return []


def _con_datos(e) -> bool:
    """Un bloque que lleva datos (atributos o los de IMPORTARSHP): va como
    marcador con su tabla."""
    return bool(IX.atributos(e)[1] or _datos_bloque(e))


def desarmar(entidades, doc, nivel: int = 0):
    """Los bloques sin datos se exportan como su dibujo (3.29.2: sin marcador
    ni rótulo, como se ven en IngeCAD): lo de la capa 0 toma la capa del
    bloque y lo «por bloque», su color y grosor. Los anidados, también."""
    for e in entidades:
        if e.dxftype() != "INSERT" or _con_datos(e) or nivel > 8:
            yield e
            continue
        try:
            partes = list(e.virtual_entities())
        except Exception:  # noqa: BLE001 -- no se desarma: va como marcador
            yield e
            continue
        capa = e.dxf.get("layer", "0")
        color = e.dxf.get("color", 256)
        if color == 256 and capa in doc.layers:
            color = abs(doc.layers.get(capa).color)
        for v in partes:
            if v.dxf.get("layer", "0") == "0":
                v.dxf.layer = capa
            if v.dxf.get("color", 256) == 0:
                v.dxf.color = color
            if v.dxf.get("lineweight", -1) == -2:
                v.dxf.lineweight = e.dxf.get("lineweight", -1)
        yield from desarmar(partes, doc, nivel + 1)


def plan_kml(entidades, doc, titulo: str = "GeoCAD", por_capa: bool = True,
             relleno: int = RELLENO, cerradas_como_poligono: bool = True,
             campo_nombre: str = "") -> PlanKml:
    """Lo elegido como marcas en WGS 84. ``campo_nombre``: el atributo del
    que sale el nombre de líneas y polígonos (si no, «capa número»)."""
    origen = IX.sistema_del_dibujo(doc)
    if not origen:
        raise ValueError("el dibujo no tiene sistema de coordenadas (SISTEMAGEO)")
    proy = IX.Proyeccion(origen, WGS84)

    def ll(pts):
        return [proy.xy(x, y) for x, y in pts]

    marcas, salteados, cuenta = [], Counter(), Counter()
    for e in desarmar(entidades, doc):
        t = e.dxftype()
        try:
            tipo, partes, extra = IX.geometria_de(e, doc, cerradas_como_poligono)
        except Exception:  # noqa: BLE001
            tipo, partes, extra = None, t, None
        if tipo is None:
            salteados[partes] += 1
            continue
        capa = e.dxf.get("layer", "0")
        _origen, attrs = IX.atributos(e)
        datos = [(n, texto) for n, _d, texto in attrs]
        valor = dict(datos).get(campo_nombre, "") if campo_nombre else ""
        try:
            if tipo == "puntos":
                geom = ll(partes[0])
                if t in ("TEXT", "MTEXT"):
                    k, nombre = "texto", extra.get("TEXTO", "")
                elif t == "INSERT":
                    k, nombre = "bloque", valor or ("" if nombre_automatico(e.dxf.name)
                                                    else e.dxf.name)
                    datos = datos or _datos_bloque(e)
                else:
                    k, nombre = "punto", valor
                desc = f"Capa {capa}"
            elif tipo == "lineas":
                k, geom = "linea", ll(partes[0])
                cuenta[capa] += 1
                nombre = valor or f"{capa} {cuenta[capa]}"
                desc = f"Capa {capa}. Largo {_num(_largo(partes[0]))} m"
            else:
                k = "poligono"
                anillos = partes if t == "HATCH" else partes[:1]
                grupos = poligonos(anillos) if t == "HATCH" else [(partes[0], [])]
                area = sum(abs(IX.shpio.signed_area(b[:-1])) - sum(abs(IX.shpio.signed_area(h[:-1]))
                                                                    for h in hs)
                           for b, hs in grupos)
                geom = [(ll(b), [ll(h) for h in hs]) for b, hs in grupos]
                cuenta[capa] += 1
                nombre = valor or f"{capa} {cuenta[capa]}"
                desc = (f"Capa {capa}. Área {_num(area)} m², perímetro "
                        f"{_num(sum(_largo(a) for a in anillos))} m")
        except Exception:  # noqa: BLE001
            salteados[f"{t} fuera del sistema"] += 1
            continue
        marcas.append(Marca(k, geom, str(nombre), capa, color_de(e, doc), grosor_de(e, doc),
                            desc, datos, t == "HATCH"))
    return PlanKml(marcas, salteados, origen, titulo, por_capa, relleno)


# ------------------------------------------------------------------ escribir
def _fmt(pt) -> str:
    return f"{pt[0]:.9f},{pt[1]:.9f},0"          # 1e-9 grados = 0,1 mm


def _coords(pts) -> str:
    return " ".join(_fmt(p) for p in pts)


def _estilo_id(m: Marca) -> str:
    clase = "s" if m.sombreado else m.tipo[0]
    return f"{clase}{m.color.lstrip('#')}_{m.grosor}"


def _estilo(doc_el, m: Marca, relleno: int) -> None:
    st = ET.SubElement(doc_el, _q("Style"), id=_estilo_id(m))
    if m.tipo == "texto":
        ic = ET.SubElement(st, _q("IconStyle"))
        ET.SubElement(ic, _q("scale")).text = "0"          # sólo el rótulo, sin chinche
        lab = ET.SubElement(st, _q("LabelStyle"))
        ET.SubElement(lab, _q("color")).text = color_kml(m.color)
        return
    if m.tipo in ("punto", "bloque"):
        ic = ET.SubElement(st, _q("IconStyle"))
        ET.SubElement(ic, _q("color")).text = color_kml(m.color)
        ET.SubElement(ic, _q("scale")).text = "0.8" if m.tipo == "bloque" else "0.6"
        ET.SubElement(ET.SubElement(ic, _q("Icon")), _q("href")).text = (
            "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png")
        lab = ET.SubElement(st, _q("LabelStyle"))
        ET.SubElement(lab, _q("scale")).text = "0.8"
        return
    ln = ET.SubElement(st, _q("LineStyle"))
    ET.SubElement(ln, _q("color")).text = color_kml(m.color)
    ET.SubElement(ln, _q("width")).text = f"{grosor_px(m.grosor):g}"
    if m.tipo == "poligono":
        ps = ET.SubElement(st, _q("PolyStyle"))
        ET.SubElement(ps, _q("color")).text = color_kml(m.color, round(relleno * 2.55))
        ET.SubElement(ps, _q("fill")).text = "1" if relleno > 0 else "0"
        # un sombreado no tiene borde en CAD; sin relleno, el borde es lo único que se ve
        ET.SubElement(ps, _q("outline")).text = "0" if (m.sombreado and relleno > 0) else "1"


def _geometria(pm, m: Marca) -> None:
    def suelo(el):
        ET.SubElement(el, _q("altitudeMode")).text = "clampToGround"

    if m.tipo in ("punto", "texto", "bloque"):
        g = ET.SubElement(pm, _q("Point"))
        suelo(g)
        ET.SubElement(g, _q("coordinates")).text = _fmt(m.geometria[0])
        return
    if m.tipo == "linea":
        g = ET.SubElement(pm, _q("LineString"))
        ET.SubElement(g, _q("tessellate")).text = "1"
        suelo(g)
        ET.SubElement(g, _q("coordinates")).text = _coords(m.geometria)
        return
    padre = ET.SubElement(pm, _q("MultiGeometry")) if len(m.geometria) > 1 else pm
    for borde, huecos in m.geometria:
        g = ET.SubElement(padre, _q("Polygon"))
        ET.SubElement(g, _q("tessellate")).text = "1"
        suelo(g)
        for tag, anillo in [("outerBoundaryIs", borde)] + [("innerBoundaryIs", h) for h in huecos]:
            ring = ET.SubElement(ET.SubElement(g, _q(tag)), _q("LinearRing"))
            ET.SubElement(ring, _q("coordinates")).text = _coords(anillo)


def globo(m: Marca) -> str:
    """Lo que muestra el globo de Google Earth al hacer clic (3.30.1). Si hay
    descripción, Google Earth no muestra los ExtendedData: la tabla de
    atributos va en la descripción (HTML) y debajo la capa y las medidas. Los
    ExtendedData siguen igual, para QGIS e IMPORTARKML."""
    filas = "".join(
        f'<tr><td style="padding:2px 8px 2px 0"><b>{html.escape(str(n))}</b></td>'
        f'<td style="padding:2px 0">{html.escape("" if v is None else str(v))}</td></tr>'
        for n, v in m.datos)
    tabla = f"<table>{filas}</table>" if filas else ""
    pie = f"<p>{html.escape(m.descripcion)}</p>" if m.descripcion else ""
    return tabla + pie


def texto_kml(plan: PlanKml) -> str:
    ET.register_namespace("", KML_NS)
    raiz = ET.Element(_q("kml"))
    d = ET.SubElement(raiz, _q("Document"))
    ET.SubElement(d, _q("name")).text = plan.titulo
    ET.SubElement(d, _q("description")).text = (
        f"Exportado con GeoCAD Yaguareté desde {IX.nombre(plan.origen)} a WGS 84.")
    vistos = set()
    for m in plan.marcas:
        if _estilo_id(m) not in vistos:
            vistos.add(_estilo_id(m))
            _estilo(d, m, plan.relleno)
    for nombre_c, marcas in plan.carpetas():
        destino = d
        if nombre_c or plan.por_capa:
            destino = ET.SubElement(d, _q("Folder"))
            ET.SubElement(destino, _q("name")).text = nombre_c or "0"
        for m in marcas:
            pm = ET.SubElement(destino, _q("Placemark"))
            if m.nombre:
                ET.SubElement(pm, _q("name")).text = m.nombre
            if m.descripcion or m.datos:
                ET.SubElement(pm, _q("description")).text = globo(m)
            ET.SubElement(pm, _q("styleUrl")).text = "#" + _estilo_id(m)
            if m.datos:
                ext = ET.SubElement(pm, _q("ExtendedData"))
                for n, v in m.datos:
                    dato = ET.SubElement(ext, _q("Data"), name=str(n))
                    ET.SubElement(dato, _q("value")).text = "" if v is None else str(v)
            _geometria(pm, m)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(raiz, encoding="unicode")


def escribir(plan: PlanKml, ruta) -> Path:
    """``.kmz`` (un zip con doc.kml, lo que abre Google Earth con doble
    clic) o ``.kml`` (texto). Se escribe a un temporal y se reemplaza al
    final: si algo falla, el archivo que había queda como estaba."""
    ruta = Path(ruta)
    texto = texto_kml(plan)
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        if ruta.suffix.lower() == ".kml":
            tmp.write_text(texto, encoding="utf-8")
        else:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("doc.kml", texto)
        tmp.replace(ruta)
    finally:
        if tmp.exists():
            tmp.unlink()
    return ruta


def resumen(plan: PlanKml, ruta) -> str:
    tipos = Counter(m.tipo for m in plan.marcas)
    nombres = {"poligono": "polígono(s)", "linea": "línea(s)", "texto": "texto(s)",
               "bloque": "bloque(s)", "punto": "punto(s)"}
    partes = ", ".join(f"{tipos[k]} {v}" for k, v in nombres.items() if tipos[k])
    carpetas = len(plan.carpetas()) if plan.por_capa else 0
    texto = (f"{len(plan.marcas)} objeto(s) a {Path(ruta).name} ({partes}), de "
             f"{IX.nombre(plan.origen)} a WGS 84")
    texto += f", en {carpetas} carpeta(s) (una por capa)." if carpetas else ", todo junto."
    if plan.salteados:
        texto += " No se exportaron: " + ", ".join(
            f"{k} {v}" for k, v in sorted(plan.salteados.items())) + "."
    return texto + " Ábralo en Google Earth."


# ================================================================== IMPORTARKML (3.30.0)
# Lo que trae un KML o KMZ, al sistema del dibujo. Del KMLIN de Terreno
# (IngeCAD 0.6.7) se toman las reglas de lectura (sin espacio de nombres
# fijo, StyleMap -> su estilo «normal», MultiGeometry, gx:Track, el doc.kml
# del KMZ); no se lo llama: pone todo en una sola capa y no lee los datos
# extendidos.

@dataclass
class Lugar:
    """Una geometría de un Placemark, en WGS 84."""
    tipo: str                       # punto | linea | poligono
    geometria: list                 # punto y linea: [(lon, lat)]; poligono: [borde, hueco, ...] sin repetir el cierre
    nombre: str = ""
    carpeta: str = ""               # la carpeta (Folder) más cercana
    color: str = ""                 # #rrggbb ("" = sin color)
    datos: list = field(default_factory=list)      # ExtendedData: [(nombre, texto)]
    n: int = 0                      # número de Placemark (las partes de un MultiGeometry comparten datos)
    solo_rotulo: bool = False       # marcador sin ícono: un texto (así exporta los textos EXPORTARKML)


def _local(tag) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _hijo(el, nombre_t: str):
    for c in el:
        if _local(c.tag) == nombre_t:
            return c
    return None


def _texto(el, nombre_t: str) -> str:
    c = _hijo(el, nombre_t) if el is not None else None
    return (c.text or "").strip() if c is not None else ""


def color_rgb(texto: str) -> str:
    """«aabbggrr» de KML -> «#rrggbb» ("" si no se entiende)."""
    t = (texto or "").strip().lstrip("#")
    if len(t) == 6:
        t = "ff" + t
    if len(t) != 8 or not re.fullmatch(r"[0-9A-Fa-f]{8}", t):
        return ""
    return f"#{t[6:8]}{t[4:6]}{t[2:4]}".lower()


def _puntos(texto: str) -> list:
    """«lon,lat[,alt] lon,lat...» -> [(lon, lat)]."""
    out = []
    for tok in re.sub(r"\s*,\s*", ",", texto or "").split():
        partes = tok.split(",")
        try:
            out.append((float(partes[0]), float(partes[1])))
        except (ValueError, IndexError):
            continue
    return out


def _anillo(el) -> list:
    for nodo in el.iter():
        if _local(nodo.tag) == "coordinates":
            pts = _puntos(nodo.text)
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            return pts
    return []


def _colores(estilo) -> dict:
    """Qué color da un Style a puntos, líneas y polígonos; «sin_icono» si
    el ícono tiene escala 0 (un rótulo solo)."""
    out = {}
    for clave, tag in (("punto", "IconStyle"), ("linea", "LineStyle"), ("relleno", "PolyStyle")):
        nodo = _hijo(estilo, tag)
        if nodo is None:
            continue
        c = color_rgb(_texto(nodo, "color"))
        if c:
            out[clave] = c
        if tag == "IconStyle":
            try:
                out["sin_icono"] = float(_texto(nodo, "scale") or 1) == 0
            except ValueError:
                pass
    lab = _hijo(estilo, "LabelStyle")
    if lab is not None and "punto" not in out and color_rgb(_texto(lab, "color")):
        out["rotulo"] = color_rgb(_texto(lab, "color"))
    return out


def _estilos(raiz) -> dict:
    estilos, mapas = {}, {}
    for nodo in raiz.iter():
        tag, sid = _local(nodo.tag), nodo.get("id")
        if tag == "Style" and sid:
            estilos[sid] = _colores(nodo)
        elif tag == "StyleMap" and sid:
            for par in nodo:
                if _local(par.tag) == "Pair" and _texto(par, "key") in ("normal", ""):
                    interno = _hijo(par, "Style")
                    if interno is not None:
                        estilos[sid] = _colores(interno)
                    else:
                        mapas[sid] = _texto(par, "styleUrl").split("#")[-1]
                    break
    for sid, destino in mapas.items():
        estilos.setdefault(sid, estilos.get(destino, {}))
    return estilos


def _datos(pm) -> list:
    """ExtendedData: <Data name><value> y <SchemaData><SimpleData name>."""
    ext = _hijo(pm, "ExtendedData")
    if ext is None:
        return []
    out = []
    for nodo in ext.iter():
        tag = _local(nodo.tag)
        if tag == "Data" and nodo.get("name"):
            out.append((nodo.get("name"), _texto(nodo, "value")))
        elif tag == "SimpleData" and nodo.get("name"):
            out.append((nodo.get("name"), (nodo.text or "").strip()))
    return out


def _geometrias(el, base: Lugar, colores: dict, out: list, salteados: Counter) -> None:
    tag = _local(el.tag)

    def lugar(tipo, geom, color):
        out.append(Lugar(tipo, geom, base.nombre, base.carpeta, color or "", base.datos, base.n,
                         tipo == "punto" and bool(colores.get("sin_icono"))))

    if tag == "Point":
        pts = _anillo(el)
        if pts:
            lugar("punto", pts[:1], colores.get("punto") or colores.get("rotulo"))
    elif tag == "LineString":
        pts = _puntos(_texto(el, "coordinates"))
        if len(pts) >= 2:
            lugar("linea", pts, colores.get("linea"))
    elif tag == "LinearRing":
        pts = _anillo(el)
        if len(pts) >= 3:
            lugar("poligono", [pts], colores.get("linea") or colores.get("relleno"))
    elif tag == "Polygon":
        borde = _hijo(el, "outerBoundaryIs")
        pts = _anillo(borde) if borde is not None else []
        huecos = [_anillo(h) for h in el if _local(h.tag) == "innerBoundaryIs"]
        if len(pts) >= 3:
            lugar("poligono", [pts] + [h for h in huecos if len(h) >= 3],
                  colores.get("linea") or colores.get("relleno"))
    elif tag == "MultiGeometry":
        for hijo in el:
            _geometrias(hijo, base, colores, out, salteados)
    elif tag in ("Track", "MultiTrack"):
        pts = []
        for nodo in el.iter():
            if _local(nodo.tag) == "coord" and nodo.text:
                p = nodo.text.split()
                try:
                    pts.append((float(p[0]), float(p[1])))
                except (ValueError, IndexError):
                    continue
        if len(pts) >= 2:
            lugar("linea", pts, colores.get("linea"))
    elif tag == "Model":
        salteados["modelos 3D"] += 1


def leer_texto(texto) -> tuple[list, Counter]:
    """Los Placemark de un KML como [Lugar] y lo que no se lee."""
    raiz = ET.fromstring(texto)
    estilos = _estilos(raiz)
    out, salteados = [], Counter()
    n = 0

    def recorrer(el, carpeta):
        nonlocal n
        tag = _local(el.tag)
        if tag == "Folder":
            carpeta = _texto(el, "name") or carpeta
        if tag == "Placemark":
            n += 1
            colores = dict(estilos.get(_texto(el, "styleUrl").split("#")[-1], {}))
            propio = _hijo(el, "Style")
            if propio is not None:
                colores.update(_colores(propio))
            base = Lugar("", [], _texto(el, "name"), carpeta, "", _datos(el), n)
            antes, saltados = len(out), sum(salteados.values())
            for hijo in el:
                _geometrias(hijo, base, colores, out, salteados)
            if len(out) == antes and sum(salteados.values()) == saltados:
                salteados["marcadores sin geometría"] += 1
            return
        if tag in ("GroundOverlay", "ScreenOverlay", "PhotoOverlay"):
            salteados["imágenes superpuestas"] += 1
            return
        if tag == "NetworkLink":
            salteados["vínculos de red"] += 1
            return
        for hijo in el:
            recorrer(hijo, carpeta)

    recorrer(raiz, "")
    return out, salteados


def leer(ruta) -> tuple[list, Counter]:
    """Un ``.kml``, o el ``doc.kml`` (o el primer ``.kml``) de un ``.kmz``."""
    ruta = Path(ruta)
    if zipfile.is_zipfile(ruta):
        with zipfile.ZipFile(ruta) as z:
            nombres = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not nombres:
                raise ValueError("el KMZ no trae ningún .kml adentro")
            return leer_texto(z.read("doc.kml" if "doc.kml" in nombres else nombres[0]))
    return leer_texto(ruta.read_bytes())


@dataclass
class OpcionesKml:
    capa: str = "carpeta"           # carpeta (una capa por carpeta) | fija
    capa_fija: str = "KML"
    rotulos: bool = False           # el nombre de cada marcador como texto
    altura: float = 2.5             # de los rótulos, en unidades del dibujo
    colores: bool = True            # el color de cada marcador en su objeto
    atributos: bool = True          # ExtendedData -> atributos (como IMPORTARSHP)
    textos: bool = True             # los rótulos sin datos del KML (3.30.4: no, si rotula ROTULOSIG)
    color: int = 7                  # ACI de las capas que se crean
    sistema: str = ""               # dibujo sin sistema: el que se le asigna


def _tipo_campo(valores) -> tuple[str, int, int]:
    """El tipo de .dbf de una columna de texto: N si todos son números."""
    vals = [v for v in valores if v != ""]
    if vals and all(re.fullmatch(r"-?\d{1,17}", v) for v in vals):
        return "N", 18, 0
    if vals and all(re.fullmatch(r"-?\d{1,12}(\.\d{1,8})?", v) for v in vals):
        return "N", 19, max(len(v.partition(".")[2]) for v in vals)
    return "C", 254, 0


def _centro(anillo) -> tuple[float, float]:
    """Centroide de un anillo (corrido al primer punto: coordenadas grandes)."""
    x0, y0 = anillo[0]
    a = cx = cy = 0.0
    for i in range(len(anillo)):
        x1, y1 = anillo[i][0] - x0, anillo[i][1] - y0
        x2, y2 = anillo[(i + 1) % len(anillo)][0] - x0, anillo[(i + 1) % len(anillo)][1] - y0
        c = x1 * y2 - x2 * y1
        a += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    if abs(a) < 1e-12:
        return anillo[0]
    return x0 + cx / (3 * a), y0 + cy / (3 * a)


def _medio(pts) -> tuple[float, float]:
    """El punto que está a la mitad del largo de una línea."""
    falta = _largo(pts) / 2
    for i in range(len(pts) - 1):
        d = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if d >= falta and d > 0:
            t = falta / d
            return (pts[i][0] + t * (pts[i + 1][0] - pts[i][0]),
                    pts[i][1] + t * (pts[i + 1][1] - pts[i][1]))
        falta -= d
    return pts[-1]


def _pintar(e, color: str) -> None:
    if not color:
        return
    if color == "#ffffff":              # el blanco de Google Earth: blanco/negro de CAD
        e.dxf.color = 7
    else:
        e.rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _fab_objeto(tipo, pts, cerrada, color, valores, tabla, campos, fid):
    def make(msp):
        if tipo == "punto":
            e = msp.add_point((pts[0][0], pts[0][1], 0.0))
        else:
            e = msp.add_lwpolyline(pts, format="xy", close=cerrada)
        _pintar(e, color)
        if campos is not None:
            IX.poner_atributos(e, tabla, campos, valores, fid)
        return e
    return make


def _fab_texto(texto, punto, altura, alinear, color, valores=None, tabla="", campos=None, fid=None):
    def make(msp):
        e = msp.add_text(texto, height=altura, dxfattribs={"insert": (punto[0], punto[1], 0.0)})
        if alinear:
            from ezdxf.enums import TextEntityAlignment
            e.set_placement(punto, align=getattr(TextEntityAlignment, alinear))
        _pintar(e, color)
        if campos is not None:
            IX.poner_atributos(e, tabla, campos, valores, fid)
        return e
    return make


def nombre_generado(nombre: str, carpeta: str) -> bool:
    """El nombre que EXPORTARKML pone cuando no se elige un atributo: «capa
    número» (PC_2_DE_MAYO 5, dentro de la carpeta PC_2_DE_MAYO). No le dice
    nada a nadie: no se rotula (3.30.3)."""
    return bool(carpeta) and re.fullmatch(re.escape(carpeta) + r" \d+", nombre) is not None


def plan_importar(doc, ruta, lugares, op: OpcionesKml, salteados=None) -> "IX.PlanImportar":
    """Lo que IMPORTARKML agrega, como UN paso de deshacer: de WGS 84 al
    sistema del dibujo (o al de ``op.sistema``, que queda asignado)."""
    from . import importados
    destino = IX.sistema_del_dibujo(doc)
    adoptado = ""
    if not destino:
        if not op.sistema:
            raise ValueError("el dibujo no tiene sistema de coordenadas (SISTEMAGEO)")
        adoptado = destino = op.sistema
    proy = IX.Proyeccion(WGS84, destino)
    nombre_a = Path(ruta).stem
    capas_existentes = {l.dxf.name.lower() for l in doc.layers}
    capas_nuevas, fabricas, avisos = [], [], []

    def capa_para(texto: str) -> str:
        c = IX.nombre_de_capa(texto, IX.nombre_de_capa(nombre_a, "KML"))
        if c.lower() not in capas_existentes:
            capas_existentes.add(c.lower())
            capas_nuevas.append(c)
        return c

    # la tabla: todas las columnas que aparecen, en el orden en que aparecen
    columnas: dict = {}
    for lg in lugares:
        for n_c, v in lg.datos:
            columnas.setdefault(n_c, []).append(v)
    campos = None
    tabla = nombre_a
    if op.atributos and columnas:
        campos = [IX.shpio.DbfField(n_c, *_tipo_campo(vs), 0) for n_c, vs in columnas.items()]
        tabla = importados.nombre_libre(nombre_a, set(importados.tablas(doc)))
    fuera = textos_fuera = 0
    marcadores = set()
    for lg in lugares:
        try:
            geom = ([proy.xy(*p) for p in lg.geometria] if lg.tipo != "poligono"
                    else [[proy.xy(*p) for p in a] for a in lg.geometria])
        except Exception:  # noqa: BLE001
            fuera += 1
            continue
        capa = capa_para(op.capa_fija if op.capa == "fija" else lg.carpeta)
        color = lg.color if op.colores else ""
        valores = dict(lg.datos)
        marcadores.add(lg.n)
        cs = campos
        if lg.tipo == "punto" and lg.solo_rotulo and not lg.datos and not op.textos:
            textos_fuera += 1           # 3.30.4: los rótulos los hace ROTULOSIG
            continue
        if lg.tipo == "punto" and lg.solo_rotulo and lg.nombre:
            # 3.30.1: un rótulo (marcador sin chinche) es anotación, no un objeto: a la
            # tabla sólo si trae datos. Los de EXPORTARKML no traen y, mezclados con
            # las parcelas, TABLASIG medía «Longitud» en vez de «Área».
            cs = campos if lg.datos else None
            fabricas.append((capa, _fab_texto(lg.nombre, geom[0], op.altura, "", color, valores,
                                              tabla, cs, lg.n)))
            continue
        if lg.tipo == "poligono":
            for anillo in geom:
                fabricas.append((capa, _fab_objeto("poligono", anillo, True, color, valores,
                                                   tabla, cs, lg.n)))
        else:
            fabricas.append((capa, _fab_objeto(lg.tipo, geom, False, color, valores,
                                               tabla, cs, lg.n)))
        if op.rotulos and lg.nombre and not nombre_generado(lg.nombre, lg.carpeta):
            if lg.tipo == "punto":
                p = (geom[0][0] + op.altura * 0.6, geom[0][1])
                fabricas.append((capa, _fab_texto(lg.nombre, p, op.altura, "MIDDLE_LEFT", color)))
            else:
                p = _centro(geom[0]) if lg.tipo == "poligono" else _medio(geom)
                fabricas.append((capa, _fab_texto(lg.nombre, p, op.altura, "MIDDLE_CENTER", color)))
    if fuera:
        avisos.append(f"{fuera} geometría(s) fuera del área del sistema no entraron.")
    if textos_fuera:
        avisos.append(f"{textos_fuera} texto(s) del archivo no se traen: los rótulos los hace "
                      "ROTULOSIG.")
    if salteados:
        avisos.append("No se importan: " + ", ".join(
            f"{k} {v}" for k, v in sorted(salteados.items())) + ".")
    comandos: list = []
    if adoptado:
        comandos.append(IX.DefinirSistemaCommand(adoptado))
    comandos += [IX.NewLayerCommand(c, color=op.color) for c in capas_nuevas]
    viejas = sorted({c for c, _f in fabricas} - set(capas_nuevas))
    if viejas:
        avisos.append("Las capas que ya estaban (" + ", ".join(viejas) + ") conservan su color "
                      "y espesor.")
    comandos += [IX.AddToModelCommand("IMPORTARKML", f, layer=c) for c, f in fabricas]
    conversion = f"de WGS 84 a {IX.nombre(destino)}"
    return IX.PlanImportar(IX.CompositeCommand("importar KML", comandos), len(fabricas),
                           [(Path(ruta).name, len(marcadores), len(fabricas), WGS84, conversion)],
                           avisos, adoptado, [tabla] if campos is not None and fabricas else [])


def resumen_importar(plan) -> str:
    nombre_a, marcadores, objetos, _s, conversion = plan.por_archivo[0]
    texto = f"{nombre_a}: {marcadores} marcador(es), {objetos} objeto(s), {conversion}."
    if plan.sistema_adoptado:
        texto += f" El dibujo quedó en {IX.nombre(plan.sistema_adoptado)}."
    if plan.tablas:
        texto += (" Datos extendidos: tabla «" + plan.tablas[0] + "» en la Tabla de atributos "
                  "(TABLASIG).")
    if plan.avisos:
        texto += " " + " ".join(plan.avisos)
    return texto + " U lo deshace."
