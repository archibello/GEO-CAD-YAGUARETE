# SPDX-License-Identifier: GPL-3.0-or-later
"""Imágenes georreferenciadas de ida y vuelta (módulo «georref», 3.19.0).

INSERTARGEO   elegir una imagen georreferenciada (archivo de mundo .pgw /
              .jgw / .tfw / .wld, o un GeoTIFF con su georreferencia
              adentro) y que entre al dibujo EN SU LUGAR, con su tamaño,
              giro y sesgo, en la capa actual. IMAGEATTACH de IngeCAD no lee
              los archivos de mundo: la imagen caía donde se hacía clic.
EXPORTARGEO   clic en una imagen del dibujo y «Guardar como»: una copia con
              su archivo de mundo y el sistema de coordenadas (.aux.xml),
              en la carpeta que se elija. QGIS la abre en su lugar. El dibujo
              no cambia.

Junto con GEORREF (ajustar con puntos de control) son los tres botones de
imágenes en la barra «Yaguareté Tools». Las cuentas no usan Qt.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from core import actions
from tools.base import Tool

from . import georref as G

FILTRO_IMAGENES = ("Imágenes (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif);;"
                   "Todos los archivos (*)")


# ------------------------------------------------------------- leer la georreferencia
def _numeros(texto: str) -> list:
    return [float(v) for v in texto.replace(",", " ").split()]


def coef_de_mundo(valores) -> tuple:
    """Las 6 líneas del archivo de mundo (A, D, B, E, C, F; C y F en el
    CENTRO del píxel de arriba a la izquierda) -> coeficientes de GEORREF
    (píxel de QGIS: columna, −fila desde la esquina)."""
    A, D, B, E, C, F = valores
    b, e, c, f = A, D, -B, -E
    return (C - 0.5 * b + 0.5 * c, b, c, F - 0.5 * e + 0.5 * f, e, f)


def archivos_de_mundo(ruta) -> list:
    """Dónde puede estar el archivo de mundo: plano.pgw, plano.pngw, plano.wld."""
    ruta = Path(ruta)
    return [G.ruta_mundo(ruta), ruta.with_suffix(ruta.suffix + "w"), ruta.with_suffix(".wld")]


def leer_mundo(ruta):
    """(coeficientes, archivo) del archivo de mundo, o None."""
    for m in archivos_de_mundo(ruta):
        if not m.is_file():
            # también en mayúsculas (PLANO.PGW)
            alt = [x for x in m.parent.glob("*") if x.name.lower() == m.name.lower()] \
                if m.parent.is_dir() else []
            if not alt:
                continue
            m = alt[0]
        try:
            v = _numeros(m.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if len(v) >= 6:
            coef = coef_de_mundo(v[:6])
            if abs(coef[1] * coef[5] - coef[2] * coef[4]) > 0:
                return coef, m
    return None


def _clave_geotiff(tags, clave):
    """Un valor corto de la GeoKeyDirectory (34735) de un GeoTIFF, o None."""
    d = tags.get(34735)
    if not d:
        return None
    d = list(d)
    for i in range(4, len(d) - 3, 4):
        if d[i] == clave and d[i + 1] == 0:        # 0 = el valor está en la clave
            return d[i + 3]
    return None


def coef_de_geotiff(tags):
    """Coeficientes de las etiquetas GeoTIFF (ModelTransformation, o
    ModelPixelScale + ModelTiepoint), o None. Con PixelIsPoint (GeoKey 1025
    = 2) el punto de enlace es el centro del píxel."""
    medio = 0.5 if _clave_geotiff(tags, 1025) == 2 else 0.0
    t = tags.get(34264)
    if t and len(t) >= 16:
        m = [float(v) for v in t]
        b, c, e, f = m[0], -m[1], m[4], -m[5]
        a, d = m[3], m[7]
        return (a - medio * b + medio * c, b, c, d - medio * e + medio * f, e, f)
    escala, enlace = tags.get(33550), tags.get(33922)
    if escala and enlace and len(escala) >= 2 and len(enlace) >= 6:
        sx, sy = float(escala[0]), float(escala[1])
        i, j, x, y = float(enlace[0]), float(enlace[1]), float(enlace[3]), float(enlace[4])
        if sx and sy:
            return (x - (i + medio) * sx, sx, 0.0, y + (j + medio) * sy, 0.0, sy)
    return None


def _abrir_imagen(ruta):
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None              # sólo se leen el tamaño y las etiquetas
    return Image.open(ruta)


def tiene_alfa(im) -> bool:
    """¿La imagen (PIL) trae transparencia propia? (PNG RGBA o LA, paleta
    con color transparente). Sin la marca «usar transparencia» en la IMAGE,
    IngeCAD la ignora y se ven los píxeles invisibles con su color: un
    negativo de ASPECTOIMAGEN salía como un rectángulo blanco (3.31.1)."""
    return im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or "transparency" in im.info


def leer(ruta) -> dict:
    """Lo que hace falta para insertar ``ruta``: tamaño en píxeles,
    coeficientes, de dónde salieron y su sistema de coordenadas (si se
    sabe). Sin georreferencia, «coef» es None."""
    ruta = Path(ruta)
    with _abrir_imagen(ruta) as im:
        w, h = im.size
        tags = dict(getattr(im, "tag_v2", {}) or {})
        alfa = tiene_alfa(im)
    out = {"ancho": int(w), "alto": int(h), "coef": None, "fuente": "", "crs": "", "alfa": alfa}
    coef = coef_de_geotiff(tags) if tags else None
    if coef is not None:                       # como GDAL: lo de adentro primero
        out.update(coef=coef, fuente="georreferencia del GeoTIFF")
        epsg = _clave_geotiff(tags, 3072) or _clave_geotiff(tags, 2048)
        if epsg and epsg != 32767:
            out["crs"] = f"EPSG:{epsg}"
    else:
        m = leer_mundo(ruta)
        if m is not None:
            out.update(coef=m[0], fuente=f"archivo de mundo {m[1].name}")
    if not out["crs"]:
        out["crs"] = crs_al_lado(ruta)
    return out


def crs_al_lado(ruta) -> str:
    """El sistema de «<imagen>.aux.xml» o «<imagen>.prj», como EPSG:n si se
    puede; "" si no hay."""
    ruta = Path(ruta)
    texto = ""
    aux = ruta.with_name(ruta.name + ".aux.xml")
    try:
        if aux.is_file():
            m = re.search(r"<SRS[^>]*>(.*?)</SRS>", aux.read_text(encoding="utf-8", errors="replace"), re.S)
            if m:
                from xml.sax.saxutils import unescape

                texto = unescape(m.group(1)).strip()
        if not texto and ruta.with_suffix(".prj").is_file():
            texto = ruta.with_suffix(".prj").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not texto:
        return ""
    try:
        import pyproj

        epsg = pyproj.CRS.from_user_input(texto).to_epsg()
        return f"EPSG:{epsg}" if epsg else "(sistema sin código EPSG)"
    except Exception:  # noqa: BLE001
        return "(sistema sin código EPSG)"


def aviso_crs(crs_imagen: str, crs_proyecto: str) -> str:
    """Un aviso si la imagen y el proyecto están en sistemas distintos."""
    if not crs_imagen or not crs_proyecto:
        return ""
    if crs_imagen.upper() == crs_proyecto.upper():
        return ""
    return (f"Atención: la imagen está en {crs_imagen} y el proyecto en {crs_proyecto}; "
            "no se reproyecta (quedaría corrida).")


def insertar_command(ruta, ancho: int, alto: int, coef, transparente: bool = False):
    """La IMAGE en su lugar (capa actual, deshacer de IngeCAD): la esquina de
    abajo a la izquierda y los vectores por píxel salen de ``coef``. Con
    ``transparente`` (la imagen trae alfa) lleva «usar transparencia»."""
    from .modelo import AddToModelCommand
    cmd = AddToModelCommand("INSERTARGEO", fabrica(ruta, ancho, alto, coef, transparente))
    cmd.needs_regen = True                     # como IMAGEATTACH: los píxeles piden la regeneración
    return cmd


def fabrica(ruta, ancho: int, alto: int, coef, transparente: bool = False):
    """La función que crea la IMAGE (para AddToModelCommand; también la usa
    IMPORTARKML, 3.32.0)."""
    a, b, c, d, e, f = coef
    esquina = G.aplicar(coef, (0.0, -float(alto)))

    def factory(msp):
        image_def = msp.doc.add_image_def(filename=str(ruta), size_in_pixel=(ancho, alto))
        img = msp.add_image(image_def, insert=esquina, size_in_units=(ancho * abs(b) or 1, alto * abs(f) or 1))
        img.dxf.insert = (esquina[0], esquina[1], 0.0)
        img.dxf.u_pixel = (b, e, 0.0)
        img.dxf.v_pixel = (c, f, 0.0)
        if transparente:
            img.set_flag_state(img.USE_TRANSPARENCY, state=True)
        return img

    return factory


# ------------------------------------------------------------- ventanas de archivo
def ruta_real(ruta) -> str:
    """En el Flatpak la ventana de archivos puede devolver una ruta del
    «portal» (/run/user/…/doc/…) que al otro día no existe: la verdadera."""
    if not ruta:
        return ruta
    try:
        from views import file_dialogs

        return file_dialogs.host_path(str(ruta))
    except Exception:  # noqa: BLE001 -- sin la vista de IngeCAD (pruebas)
        return str(ruta)


def es_portal(ruta) -> bool:
    p = Path(str(ruta)).parts
    return (len(p) > 4 and p[:3] == ("/", "run", "user") and p[4] == "doc") \
        or (len(p) > 3 and p[:4] == ("/", "run", "flatpak", "doc"))


def pedir_abrir(ctx, titulo: str, filtro: str, inicio: str = "") -> str:
    """La ventana de abrir de IngeCAD; sin ventana, se escribe la ruta."""
    window = getattr(ctx.services, "window", None)
    try:
        from views import file_dialogs

        if window is not None:
            return file_dialogs.get_open_file(window, titulo, filtro, inicio or None) or ""
    except ImportError:
        pass
    return (ctx.ask_text(titulo + ":", inicio) or "").strip()


def pedir_abrir_en(parent, titulo: str, filtro: str, inicio: str = "") -> str:
    """La ventana de abrir de IngeCAD sobre otra ventana (la tabla de puntos)."""
    try:
        from views import file_dialogs

        return file_dialogs.get_open_file(parent, titulo, filtro, inicio or None) or ""
    except ImportError:
        return ""


def pedir_guardar(ctx, titulo: str, sugerido: str, filtro: str, parent=None) -> str:
    """La ventana de guardar de IngeCAD; sin ventana, se escribe la ruta."""
    window = parent or (getattr(ctx.services, "window", None) if ctx is not None else None)
    try:
        from views import file_dialogs

        if window is not None:
            ruta, _f = file_dialogs.get_save_file(window, titulo, sugerido, filtro,
                                                  str(Path(sugerido).parent) if sugerido else None)
            return ruta or ""
    except ImportError:
        pass
    if ctx is None:
        return ""
    return (ctx.ask_text(titulo + ":", sugerido) or "").strip()


# ------------------------------------------------------------- INSERTARGEO
class InsertarGeoTool(Tool):
    """INSERTARGEO: una imagen georreferenciada, en su lugar."""

    def start(self) -> None:
        self.name = "INSERTARGEO"
        ruta = pedir_abrir(self.ctx, "Insertar imagen georreferenciada", FILTRO_IMAGENES)
        if not ruta:
            self.ctx.finish()
            return
        self.insertar(ruta_real(ruta))
        self.ctx.finish()

    def insertar(self, ruta):
        ruta = Path(ruta)
        try:
            datos = leer(ruta)
        except Exception as exc:  # noqa: BLE001 -- archivo dañado o que no es imagen
            self.ctx.echo(f"GeoCAD Yaguareté: no se puede leer {ruta.name} como imagen ({exc}).")
            return None
        if datos["coef"] is None:
            self.ctx.echo(f"GeoCAD Yaguareté: {ruta.name} no tiene georreferencia (ni archivo de "
                          "mundo .pgw / .jgw / .tfw / .wld, ni GeoTIFF). Insértela con IMAGEATTACH "
                          "y ajústela con GEORREF.")
            return None
        cmd = insertar_command(ruta, datos["ancho"], datos["alto"], datos["coef"], datos["alfa"])
        self.ctx.execute(cmd)
        img = cmd.entity
        esq = G.esquinas(img)
        xs, ys = [p[0] for p in esq], [p[1] for p in esq]
        self.ctx.echo(f"Imagen {ruta.name} insertada en su lugar ({datos['fuente']}): "
                      f"X {G._fmt(min(xs), 2)} a {G._fmt(max(xs), 2)}, "
                      f"Y {G._fmt(min(ys), 2)} a {G._fmt(max(ys), 2)}; "
                      f"{G.describir(datos['coef'])}. U la quita.")
        aviso = aviso_crs(datos["crs"], G.crs_dibujo())
        if aviso:
            self.ctx.echo(aviso)
        window = getattr(self.ctx.services, "window", None)
        zoom = getattr(window, "zoom_to_entity", None)
        if zoom is not None:
            try:
                zoom(img)
            except Exception:  # noqa: BLE001 -- sin zoom, igual quedó insertada
                pass
        return img


# ------------------------------------------------------------- EXPORTARGEO
def exportar(img, destino, original, crs: str = "") -> list:
    """Copia la imagen a ``destino`` (nunca sobre la original) con su
    archivo de mundo y el .aux.xml: donde está HOY en el dibujo."""
    destino = G.destino_copia(destino, original)
    shutil.copy2(original, destino)
    real = Path(ruta_real(destino))
    return [real] + G.escribir_mundo(real, G.coef_imagen(img), crs)


class ExportarGeoTool(Tool):
    """EXPORTARGEO: clic en una imagen y «Guardar como»: copia georreferenciada."""

    entity_picker = True
    PEDIDO = "Designe la imagen a exportar con su georreferencia (clic en la imagen o en su borde):"

    def start(self) -> None:
        self.name = "EXPORTARGEO"
        s = self.ctx.services
        previa = list(getattr(s, "selection", None) or ())
        if previa:
            aux = G.GeorrefTool(self.ctx)
            imgs = [e for h in previa if (e := aux._entidad(h)) is not None and e.dxftype() == "IMAGE"]
            if len(imgs) == 1:
                s.selection = set()
                self._exportar(imgs[0])
                return
        self.prompt(self.PEDIDO)

    def _buscar(self, p):
        aux = G.GeorrefTool(self.ctx)
        return aux._imagen_en(p)

    def on_point(self, point) -> None:
        img, otro = self._buscar((float(point[0]), float(point[1])))
        if img is None:
            if otro is not None:
                self.ctx.echo(f"GeoCAD Yaguareté: {otro.dxftype()} no es una imagen.")
            self.prompt(self.PEDIDO)
            return
        self._exportar(img)

    def _exportar(self, img) -> None:
        doc = getattr(getattr(self.ctx.services, "window", None), "document", None)
        original = G.archivo_imagen(img, doc)
        if original is None or not original.is_file():
            self.ctx.echo("GeoCAD Yaguareté: no se encuentra el archivo de la imagen"
                          + (f" ({original})." if original else "."))
            self.ctx.finish()
            return
        try:
            sugerido = str(G.nombre_copia(original))
        except OSError:
            sugerido = str(original.with_name(original.stem + G.SUFIJO_COPIA + original.suffix))
        ruta = pedir_guardar(self.ctx, "Guardar copia geo como", sugerido,
                             f"Imagen (*{original.suffix});;Todos los archivos (*)")
        if not ruta:
            self.ctx.echo("EXPORTARGEO cancelado.")
            self.ctx.finish()
            return
        try:
            hechos = exportar(img, ruta, original, G.crs_dibujo())
        except OSError as exc:
            self.ctx.echo(f"GeoCAD Yaguareté: no se pudo exportar ({exc}).")
            self.ctx.finish()
            return
        if es_portal(hechos[0]):
            self.ctx.echo("Atención: IngeCAD no tiene acceso directo a esa carpeta; el archivo de "
                          "mundo puede no haber quedado al lado de la copia. Habilite el acceso "
                          "(flatpak override --user --filesystem=<carpeta> org.ingecad.IngeCAD).")
        self.ctx.echo(f"Copia geo: {hechos[0]} ({' y '.join(h.name for h in hechos[1:])}). "
                      "QGIS la abre en su lugar; el dibujo no cambia.")
        self.ctx.finish()

    # -- resaltado: la imagen bajo el cursor ------------------------------------
    def resaltado(self, cursor) -> dict:
        if cursor is None:
            return {}
        img, _o = self._buscar(tuple(cursor))
        return {"cursor": G.marco(G.esquinas(img))} if img is not None else {}
