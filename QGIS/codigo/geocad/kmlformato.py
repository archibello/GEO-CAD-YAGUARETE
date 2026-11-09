# SPDX-License-Identifier: GPL-3.0-or-later
"""Escribir KML y KMZ para Google Earth (3.74.0): lo común a IngeCAD
(EXPORTARKML, kml.py) y QGIS (kml_qgis.py). Cada programa arma un PlanKml con sus
objetos ya en WGS 84; acá no se sabe nada de dibujos ni de capas.

Formatos probados con Google Earth: color aabbggrr, tessellate, 9 decimales
= 0,1 mm, el KMZ como un zip con doc.kml. El archivo se escribe a un temporal y
reemplaza al anterior sólo al final.
"""
from __future__ import annotations

import html
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
RELLENO = 40            # % de opacidad del relleno de los polígonos, si no se elige otro
#: los grosores de CAD (mm) en píxeles de Google Earth: 0,25 mm (el normal) = 2 px
PX_POR_MM = 6.0
PX_MIN = 2.0
GROSOR_NORMAL = 25      # centésimas de mm: «Por defecto» de AutoCAD e IngeCAD

def _q(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _gx(tag: str) -> str:
    return f"{{{GX_NS}}}{tag}"

# ------------------------------------------------------------------ estilo
def color_kml(hex_rgb: str, alfa: int = 255) -> str:
    """«#rrggbb» -> el «aabbggrr» de KML."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"{max(0, min(255, int(alfa))):02x}{b}{g}{r}".lower()


def grosor_px(lw: int) -> float:
    return round(max(PX_MIN, lw / 100.0 * PX_POR_MM), 1)


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
    color_relleno: str = ""         # polígonos: #rrggbb del relleno (""= el de ``color``)
    relleno: int | None = None      # polígonos: % de opacidad propio (None = el del plan)


@dataclass
class Superposicion:
    """Una imagen del dibujo como GroundOverlay (3.32.0)."""
    nombre: str
    capa: str
    archivo: Path                   # el que usa la imagen en el dibujo
    esquinas: list                  # [(lon, lat)]: abajo izq., abajo der., arriba der., arriba izq.
    href: str = ""                  # dentro del KMZ o junto al .kml (lo pone escribir)


@dataclass
class PlanKml:
    marcas: list
    salteados: Counter
    origen: str
    titulo: str
    por_capa: bool = True
    relleno: int = RELLENO
    superposiciones: list = field(default_factory=list)
    nombre_origen: str = ""         # cómo se muestra el sistema de partida

    def carpetas(self) -> list[tuple[str, list]]:
        """[(capa, [Superposicion... Marca...])]: las imágenes primero, abajo de todo."""
        todo = self.superposiciones + self.marcas
        if not self.por_capa:
            return [("", todo)]
        grupos: dict = {}
        for m in todo:
            grupos.setdefault(m.capa, []).append(m)
        return sorted(grupos.items(), key=lambda kv: kv[0].lower())


# ------------------------------------------------------------------ escribir
def _fmt(pt) -> str:
    return f"{pt[0]:.9f},{pt[1]:.9f},0"          # 1e-9 grados = 0,1 mm


def _coords(pts) -> str:
    return " ".join(_fmt(p) for p in pts)


def _estilo_id(m: Marca) -> str:
    clase = "s" if m.sombreado else m.tipo[0]
    base = f"{clase}{m.color.lstrip('#')}_{m.grosor}"
    if m.color_relleno or m.relleno is not None:
        base += f"_{m.color_relleno.lstrip('#')}_{m.relleno}"
    return base


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
        if m.relleno is not None:
            relleno = m.relleno
        ET.SubElement(ps, _q("color")).text = color_kml(m.color_relleno or m.color, round(relleno * 2.55))
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


def _superposicion(destino, s: Superposicion, orden: int) -> None:
    go = ET.SubElement(destino, _q("GroundOverlay"))
    ET.SubElement(go, _q("name")).text = s.nombre
    ET.SubElement(go, _q("description")).text = f"Capa {s.capa}. Imagen {s.archivo.name}"
    ET.SubElement(go, _q("drawOrder")).text = str(orden)
    ET.SubElement(ET.SubElement(go, _q("Icon")), _q("href")).text = s.href
    ET.SubElement(go, _q("altitudeMode")).text = "clampToGround"
    quad = ET.SubElement(go, _gx("LatLonQuad"))
    ET.SubElement(quad, _q("coordinates")).text = _coords(s.esquinas)


def texto_kml(plan: PlanKml) -> str:
    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    raiz = ET.Element(_q("kml"))
    d = ET.SubElement(raiz, _q("Document"))
    ET.SubElement(d, _q("name")).text = plan.titulo
    ET.SubElement(d, _q("description")).text = (
        f"Exportado con GeoCAD Yaguareté desde {plan.nombre_origen or plan.origen} a WGS 84.")
    orden = {id(s): k for k, s in enumerate(plan.superposiciones, 1)}
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
            if isinstance(m, Superposicion):
                _superposicion(destino, m, orden[id(m)])
                continue
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


def nombres_png(superposiciones) -> list[str]:
    """Un nombre de PNG por imagen, sin repetir (dos imágenes del mismo
    archivo comparten el suyo)."""
    usados, por_archivo, out = set(), {}, []
    for s in superposiciones:
        clave = str(s.archivo)
        if clave not in por_archivo:
            base = re.sub(r"[^\w.-]+", "_", s.archivo.stem) or "imagen"
            nombre, k = f"{base}.png", 2
            while nombre.lower() in usados:
                nombre, k = f"{base}_{k}.png", k + 1
            usados.add(nombre.lower())
            por_archivo[clave] = nombre
        out.append(por_archivo[clave])
    return out


def guardar_imagen(datos: bytes, carpeta, nombre: str) -> Path:
    """La imagen del KMZ en ``carpeta``, sin pisar ninguna; si ya está la
    misma (importar dos veces el mismo KMZ), se usa esa."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    p = Path(nombre)
    base = re.sub(r"[^\w.-]+", "_", p.stem) or "imagen"
    ext = p.suffix.lower() if re.fullmatch(r"\.\w{1,5}", p.suffix) else ".png"
    for k in range(1, 1000):
        destino = carpeta / f"{base}{'' if k == 1 else f'_{k}'}{ext}"
        if not destino.exists():
            destino.write_bytes(datos)
            return destino
        if destino.stat().st_size == len(datos) and destino.read_bytes() == datos:
            return destino
    raise OSError("demasiadas imágenes con el mismo nombre")


def escribir(plan: PlanKml, ruta, a_png=None) -> Path:
    """``.kmz`` (un zip con doc.kml, lo que abre Google Earth con doble
    clic) o ``.kml`` (texto). Se escribe a un temporal y se reemplaza al
    final: si algo falla, el archivo que había queda como estaba. Las
    imágenes, en PNG: en «imagenes/» del KMZ, o en «<nombre>_imagenes»
    junto al .kml. Esa carpeta puede ser la de las imágenes del dibujo
    (PEGARIMAGEN, ASPECTOIMAGEN): ahí no se pisa nada; un PNG que ya está
    se nombra tal cual. ``a_png(archivo)``: los bytes en PNG, o None si ya lo
    es (sin ella, los archivos se copian tal cual: sólo sirve para PNG)."""
    png = a_png or (lambda _archivo: None)
    ruta = Path(ruta)
    es_kml = ruta.suffix.lower() == ".kml"
    carpeta = f"{ruta.stem}_imagenes" if es_kml else "imagenes"
    nombres = nombres_png(plan.superposiciones)
    archivos = list(dict.fromkeys(zip(nombres, (s.archivo for s in plan.superposiciones))))
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        if es_kml:
            final = {}
            for n, archivo in archivos:
                datos = png(archivo)
                if datos is None and archivo.resolve().parent == (ruta.parent / carpeta).resolve():
                    final[n] = archivo.name
                    continue
                if datos is None:
                    datos = archivo.read_bytes()
                final[n] = guardar_imagen(datos, ruta.parent / carpeta, n).name
            for s, n in zip(plan.superposiciones, nombres):
                s.href = f"{carpeta}/{final[n]}"
            tmp.write_text(texto_kml(plan), encoding="utf-8")
        else:
            for s, n in zip(plan.superposiciones, nombres):
                s.href = f"{carpeta}/{n}"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("doc.kml", texto_kml(plan))
                for n, archivo in archivos:      # el PNG ya viene comprimido
                    datos = png(archivo)
                    if datos is None:
                        z.write(archivo, f"{carpeta}/{n}", zipfile.ZIP_STORED)
                    else:
                        z.writestr(f"{carpeta}/{n}", datos, zipfile.ZIP_STORED)
        tmp.replace(ruta)
    finally:
        if tmp.exists():
            tmp.unlink()
    return ruta
