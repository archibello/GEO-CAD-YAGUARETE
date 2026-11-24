# SPDX-License-Identifier: GPL-3.0-or-later
"""ASPECTOIMAGEN: el aspecto de una imagen del dibujo (3.31.0).

Pedido de Fernando (20/10/2026) para llevar planos de mensura escaneados
encima de otros dibujos o de Google Earth. Se elige una imagen y en una
ventana (aspecto_ui.py) se decide:

  - fondo transparente: cada píxel es más transparente cuanto más claro
    (negro opaco, blanco invisible), así los bordes quedan suaves; «Blanco
    que se borra» dice desde qué tono claro ya no se ve nada (papel
    amarillento, escaneos grises);
  - las líneas como están, en negativo (lo negro pasa a blanco) o de un color;
  - la opacidad general;
  - el contraste de las líneas (3.83.0, Fernando): refuerza la «tinta» de
    cada píxel, sea negra o de color (100 % como están, hasta 400 %); el
    papel blanco sigue blanco y las líneas tenues se ven más fuertes;
  - la imagen final (3.83.0): «Entregar imagen final...» hace la copia con
    el aspecto sobre papel blanco, toda opaca, para entregar el trabajo
    terminado; reemplaza al fondo de la capa (ver abajo);
  - limpiar manchas (3.84.0, ver abajo).

El archivo original NUNCA se toca: se guarda una copia PNG en la carpeta de
imágenes del dibujo (la de PEGARIMAGEN), la imagen pasa a usarla y U lo
deshace. Los valores y el archivo original quedan en la imagen (XDATA
GEOCAD_ASPECTO): la ventana vuelve a abrir con ellos, se rehace siempre desde
el original, «Volver al original» la devuelve, y EXPORTARKML (3.32.0) los
usa. Las cuentas usan PIL y numpy (IngeCAD los trae) y no usan Qt.

Fondo blanco (3.82.0, Fernando, 16/11/2026): «para volver al fondo blanco
cuando lo necesitemos», con una capa que se prende o se apaga en vez de
rellenar los píxeles. Es un sombreado sólido blanco con el contorno de la
imagen (o su recorte), en la capa FONDO_IMAGENES, enviado al fondo: queda
debajo de la imagen y de todo lo demás. Apagar o inutilizar la capa lo saca
de la vista sin tocar la imagen. Lleva XDATA GEOCAD_FONDO con el handle de
su imagen: la ventana lo encuentra, lo rehace al contorno actual o lo quita.

Limpiar manchas (3.84.0, Fernando, 16/11/2026): la limpieza de planos que
se hace con Photoshop; borrar el polvo y los granos del escaneo «para que el
resto permanezca lo más blanco o transparente posible», con «un porcentaje
de admitidos a pequeñas distancias» y «dando prioridad a los textos». Cada
píxel con algo de tinta cuenta la tinta que hay a su alrededor, en un
cuadrado de lado 2·Distancia+1. Se borra si esa cuenta es menor que
Tolerancia % de una línea fina que cruzara el cuadrado (2·Distancia+1
píxeles). Así:
  * una línea nunca se borra (la tolerancia llega hasta 50 %: hasta la
    punta de una línea tiene la mitad);
  * una mancha se borra sólo si es chica Y está sola: un punto, una coma o
    una tilde a menos de Distancia de una letra cuentan la tinta de la letra
    y se quedan (la prioridad de los textos); lo más grande que puede borrar
    es Tolerancia % · (2·Distancia+1) píxeles, menos que cualquier letra;
  * cuenta si hay tinta, no cuán oscura es: una línea tenue no se trata
    como mancha por ser clara.
Lo borrado queda transparente (o blanco, sin fondo transparente). En la
vista previa puede verse en rojo antes de aceptar. Las cuentas son sumas en
ventana (acumuladas, por franjas): sólo numpy, en Windows igual.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.commands import Command, CompositeCommand
from tools.base import Tool

from . import georref as G
from . import pegarimagen

APPID = "GEOCAD_ASPECTO"
MARCA = "ASPECTO 1"
SUFIJO = "_aspecto"
# 3.91.0: las cuentas (sólo numpy) están en el núcleo, aspecto_cuentas.py, y las usa
# también ASPECTOIMAGEN de QGIS
from .aspecto_cuentas import (  # noqa: F401 -- nombres de siempre para el resto de GeoCAD
    BLANCO_MAX, CONTRASTE_MAX, DEFECTO, DISTANCIA_MAX, DISTANCIA_MIN, FILAS_FRANJA, LINEAS,
    OPACIDAD_MIN, ROJO, SUFIJO_FINAL, TOLERANCIA_MAX, TOLERANCIA_MIN, AspectoError, _color,
    _franja, _halo, _sobre_blanco, _suma_filas, _tinta, describir, manchas, normalizar,
    procesar_arreglo, rgb)

#: los últimos usados en la sesión, para una imagen que todavía no tiene aspecto
_ultimos = [dict(DEFECTO)]


#: el fondo blanco: su capa y sus XDATA
CAPA_FONDO = "FONDO_IMAGENES"
APPID_FONDO = "GEOCAD_FONDO"
MARCA_FONDO = "FONDO 1"
BLANCO_RGB = (255, 255, 255)          # color verdadero: el 7 sería negro en pantalla oscura


# ------------------------------------------------------------------ los píxeles
def _pil():
    try:
        from PIL import Image
        import numpy  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise AspectoError("faltan PIL (Pillow) o numpy para procesar la imagen") from exc
    Image.MAX_IMAGE_PIXELS = None              # los escaneos grandes son nuestros
    return Image


def abrir(ruta):
    Image = _pil()
    try:
        im = Image.open(str(ruta))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise AspectoError(f"no se puede leer {Path(ruta).name} ({exc})") from exc
    return im


def procesar(imagen, valores, hecho=None, escala: float = 1.0, marcar: bool = False):
    """La imagen (PIL) RGBA con el aspecto: aspecto_cuentas.procesar_arreglo (la
    misma cuenta que QGIS, 3.91.0)."""
    Image = _pil()
    import numpy as np
    im = imagen if imagen.mode == "RGBA" else imagen.convert("RGBA")
    return Image.fromarray(procesar_arreglo(np.asarray(im), valores, hecho, escala, marcar), "RGBA")


def reducida(imagen, lado: int = 420):
    """Una copia chica para la vista previa (la cuenta es la misma)."""
    im = imagen.copy()
    im.thumbnail((lado, lado))
    return im


# ------------------------------------------------------------------ guardado en la imagen
def leer(img):
    """(valores, archivo original como estaba escrito) o None si la imagen
    no tiene aspecto de GeoCAD."""
    try:
        tags = [t[1] for t in img.get_xdata(APPID)]
    except Exception:  # noqa: BLE001 -- sin XDATA
        return None
    if not tags or tags[0] != MARCA or len(tags) < 3:
        return None
    try:
        valores = normalizar(json.loads(tags[1]))
    except (TypeError, ValueError):
        return None
    return valores, "".join(str(t) for t in tags[2:])


def etiquetas(valores, original: str) -> list:
    """Las XDATA: marca, valores (JSON) y el archivo original en trozos de
    200 caracteres (el límite de un texto de XDATA es 255)."""
    original = str(original)
    trozos = [original[i:i + 200] for i in range(0, len(original), 200)] or [""]
    return ([(1000, MARCA), (1000, json.dumps(normalizar(valores), sort_keys=True))]
            + [(1000, t) for t in trozos])


def _xdata(img):
    try:
        return list(img.get_xdata(APPID))
    except Exception:  # noqa: BLE001
        return None


def _poner_xdata(img, tags) -> None:
    if tags:
        doc = img.doc
        if doc is not None and APPID not in doc.appids:
            doc.appids.add(APPID)
        img.set_xdata(APPID, tags)
    elif img.has_xdata(APPID):
        img.discard_xdata(APPID)


# ------------------------------------------------------------------ archivos
def nombre_copia(carpeta, original, sufijo: str = SUFIJO) -> Path:
    """<original>_aspecto.png en ``carpeta``, sin pisar otra (…_2, …_3): U
    vuelve a la copia anterior, que tiene que seguir siendo la misma."""
    base = Path(original).stem
    ruta = Path(carpeta) / f"{base}{sufijo}.png"
    n = 2
    while ruta.exists():
        ruta = Path(carpeta) / f"{base}{sufijo}_{n}.png"
        n += 1
    return ruta


def invisible(imagen) -> bool:
    """¿No queda ningún píxel visible?"""
    return imagen.getchannel("A").getextrema()[1] == 0


#: compresión del PNG: la 6 de siempre tardaba más que la cuenta en un plano
#: de 37 megapíxeles; la 3 es bastante más rápida y casi del mismo tamaño
COMPRESION_PNG = 3


def destino(original, ruta_dibujo, sufijo: str = SUFIJO) -> Path:
    """Dónde va la copia (crea la carpeta)."""
    carpeta = pegarimagen.carpeta_destino(ruta_dibujo)
    carpeta.mkdir(parents=True, exist_ok=True)
    return nombre_copia(carpeta, original, sufijo)


def guardar_png(hecha, ruta, opaca: bool = False) -> None:
    if opaca:                                  # la imagen final: sin canal alfa
        hecha = hecha.convert("RGB")
    hecha.save(str(ruta), "PNG", compress_level=COMPRESION_PNG)


def guardar_copia(original, valores, ruta_dibujo):
    """Procesa el original y lo guarda como PNG junto al dibujo:
    (ruta, quedó invisible)."""
    hecha = procesar(abrir(original), valores)
    ruta = destino(original, ruta_dibujo)
    guardar_png(hecha, ruta)
    return ruta, invisible(hecha)


#: segundos por megapíxel de cada etapa (se ajustan con lo medido en cada
#: uso, mientras IngeCAD esté abierto): para la cuenta regresiva de la barra
_ritmo = {"abrir": 0.03, "guardar": 0.08}


def estimar(etapa: str, megapixeles: float) -> float:
    return max(1.0, _ritmo[etapa] * megapixeles)


def medir(etapa: str, megapixeles: float, segundos: float) -> None:
    if megapixeles > 0.5 and segundos > 0:
        _ritmo[etapa] = segundos / megapixeles


# ------------------------------------------------------------------ el comando
class AspectoCommand(G.GeorrefCommand):
    """La imagen apunta a otro archivo (la copia o, al volver, el original)
    y lleva sus XDATA. Sin moverla (matriz identidad); un U deshace todo."""

    def __init__(self, img, archivo, tags) -> None:
        from ezdxf.math import Matrix44
        super().__init__(img, Matrix44(), copia=archivo)
        self.name = "ASPECTOIMAGEN"
        self.tags = tags
        self._tags_antes = None
        self._flags_antes = None

    def do(self, document) -> None:
        super().do(document)
        if not self.entities:
            return
        img = self.img
        self._tags_antes = _xdata(img)
        self._flags_antes = img.dxf.get("flags", 0)
        if self.tags:
            # sin «usar transparencia» el alfa del PNG no cuenta y el fondo se ve negro
            img.set_flag_state(img.USE_TRANSPARENCY, state=True)
        _poner_xdata(img, self.tags)
        G._recargar_pixeles(img.dxf.handle)

    def undo(self, document) -> None:
        if self.entities:
            img = self.img
            _poner_xdata(img, self._tags_antes)
            if self._flags_antes is not None:
                img.dxf.flags = self._flags_antes
        super().undo(document)
        if self.entities:
            G._recargar_pixeles(self.img.dxf.handle)


# ------------------------------------------------------------------ el fondo blanco
def _espacio(img):
    try:
        return img.get_layout()
    except Exception:  # noqa: BLE001
        return None


def fondo_de(img):
    """El sombreado de fondo blanco de esa imagen, o None."""
    espacio = _espacio(img)
    if espacio is None:
        return None
    handle = img.dxf.handle
    for h in espacio.query("HATCH"):
        try:
            tags = [t[1] for t in h.get_xdata(APPID_FONDO)]
        except Exception:  # noqa: BLE001 -- sin XDATA
            continue
        if len(tags) >= 2 and tags[0] == MARCA_FONDO and tags[1] == handle:
            return h
    return None


def contorno(img) -> list:
    """El contorno de la imagen en el dibujo (su recorte, si tiene)."""
    try:
        puntos = [(float(p[0]), float(p[1])) for p in img.boundary_path_wcs()]
    except Exception:  # noqa: BLE001
        puntos = []
    if len(puntos) > 1 and puntos[0] == puntos[-1]:
        puntos = puntos[:-1]
    return puntos if len(puntos) >= 3 else [tuple(p) for p in G.esquinas(img)]


def _natural(espacio) -> tuple:
    handles = [int(e.dxf.handle, 16) for e in espacio if e.dxf.handle]
    return (min(handles), max(handles)) if handles else (1, 1)


class FondoCommand(Command):
    """Pone (rehace al contorno actual) o quita el fondo blanco de una
    imagen. Un U deja la capa, el sombreado y el orden de dibujo como estaban."""

    needs_regen = True

    def __init__(self, img, poner: bool) -> None:
        self.name = "fondo blanco"
        self.img, self.poner = img, bool(poner)
        self.nuevo = self.quitado = None
        self._orden_antes = None
        self._capa_creada = False
        self.al_fondo_la_imagen = False      # la imagen estaba enviada al fondo

    def _crear(self, espacio, doc):
        h = espacio.add_hatch(dxfattribs={"layer": CAPA_FONDO})
        h.set_solid_fill(color=7, rgb=BLANCO_RGB)
        h.paths.add_polyline_path(contorno(self.img), is_closed=True)
        if APPID_FONDO not in doc.appids:
            doc.appids.add(APPID_FONDO)
        h.set_xdata(APPID_FONDO, [(1000, MARCA_FONDO), (1000, self.img.dxf.handle)])
        return h

    def do(self, document) -> None:
        espacio = _espacio(self.img)
        if espacio is None:
            return
        doc = document.doc
        self._orden_antes = list(espacio.get_redraw_order())
        orden = dict(self._orden_antes)
        viejo = fondo_de(self.img)
        if viejo is not None:
            self.quitado = viejo
            espacio.unlink_entity(viejo)
            orden.pop(viejo.dxf.handle, None)
        if self.poner:
            if CAPA_FONDO not in doc.layers:
                doc.layers.add(CAPA_FONDO, color=7)
                self._capa_creada = True
            if self.nuevo is not None and self.nuevo.is_alive:
                espacio.add_entity(self.nuevo)                   # rehacer: el mismo
            else:
                self.nuevo = self._crear(espacio, doc)
            lo, _hi = _natural(espacio)
            ih = self.img.dxf.handle
            try:
                if ih in orden and int(orden[ih], 16) < lo:
                    # IngeCAD pinta las imágenes de un grupo debajo de sus
                    # rellenos: la imagen vuelve al grupo normal para quedar
                    # encima de su fondo
                    del orden[ih]
                    self.al_fondo_la_imagen = True
            except (TypeError, ValueError):
                pass
            orden[self.nuevo.dxf.handle] = f"{max(1, lo - 1):X}"
        espacio.set_redraw_order(orden)
        document.dirty = True

    def undo(self, document) -> None:
        espacio = _espacio(self.img)
        if espacio is None or self._orden_antes is None:
            return
        handles = []
        if self.nuevo is not None and self.nuevo.is_alive and self.nuevo.dxf.get("owner") is not None:
            handles.append(self.nuevo.dxf.handle)
            espacio.unlink_entity(self.nuevo)
        if self.quitado is not None and self.quitado.is_alive:
            espacio.add_entity(self.quitado)
            self.quitado = None
        if self._capa_creada:
            try:
                document.doc.layers.remove(CAPA_FONDO)
            except Exception:  # noqa: BLE001
                pass
            self._capa_creada = False
        espacio.set_redraw_order(dict(self._orden_antes))
        self.removed_handles = handles
        document.dirty = True


# ------------------------------------------------------------------ la ventana
def ventana(parent, original, valores, con_aspecto: bool, fondo: bool = False):
    """{"accion": "aceptar" | "original", "valores", "fondo_blanco"} o None
    (Cancelar). Las pruebas la reemplazan; sin Qt no hay ventana."""
    from . import aspecto_ui
    return aspecto_ui.ventana(parent, original, valores, con_aspecto, fondo)


# ------------------------------------------------------------------ la orden
class AspectoImagenTool(Tool):
    """ASPECTOIMAGEN: clic en una imagen y la ventana del aspecto."""

    entity_picker = True
    PEDIDO = "Designe la imagen para cambiar su aspecto (clic en la imagen o en su borde):"

    def start(self) -> None:
        self.name = "ASPECTOIMAGEN"
        s = self.ctx.services
        previa = list(getattr(s, "selection", None) or ())
        if previa:
            aux = G.GeorrefTool(self.ctx)
            imgs = [e for h in previa if (e := aux._entidad(h)) is not None and e.dxftype() == "IMAGE"]
            if len(imgs) == 1:
                s.selection = set()
                self._aspecto(imgs[0])
                return
        self.prompt(self.PEDIDO)

    def _buscar(self, p):
        return G.GeorrefTool(self.ctx)._imagen_en(p)

    def on_point(self, point) -> None:
        img, otro = self._buscar((float(point[0]), float(point[1])))
        if img is None:
            if otro is not None:
                self.ctx.echo(f"GeoCAD Yaguareté: {otro.dxftype()} no es una imagen.")
            self.prompt(self.PEDIDO)
            return
        self._aspecto(img)

    def _documento(self):
        return getattr(getattr(self.ctx.services, "window", None), "document", None)

    def _real(self, escrito):
        """La ruta en el disco de un nombre como está escrito en el dibujo."""
        p = Path(str(escrito))
        if not p.is_absolute():
            base = getattr(self._documento(), "path", None)
            if base:
                p = Path(str(base)).parent / p
        return p

    def _fin(self, texto: str) -> None:
        self.ctx.echo(texto)
        self.ctx.finish()

    @staticmethod
    def _con_fondo(cmd, fondo_cmd):
        """El aspecto y el fondo en un solo paso: un U deshace los dos."""
        return cmd if fondo_cmd is None else CompositeCommand("ASPECTOIMAGEN", [cmd, fondo_cmd])

    def _echo_fondo(self, fondo_cmd, fondo: bool) -> None:
        if fondo:
            self.ctx.echo(f"Fondo blanco debajo de la imagen, en la capa {CAPA_FONDO}: "
                          "apague la capa para sacarlo de la vista.")
            if fondo_cmd.al_fondo_la_imagen:
                self.ctx.echo("La imagen estaba enviada al fondo: vuelve al orden normal "
                              "para quedar encima de su fondo blanco.")
        else:
            self.ctx.echo("Fondo blanco quitado.")

    def _solo_fondo(self, fondo_cmd, fondo: bool) -> None:
        self.ctx.execute(fondo_cmd)
        self._echo_fondo(fondo_cmd, fondo)
        self.ctx.echo("U lo deshace.")
        self.ctx.finish()

    def _aspecto(self, img) -> None:
        guardado = leer(img)
        if guardado is not None:
            valores, escrito = guardado
        else:
            valores, escrito = dict(_ultimos[0]), img.image_def.dxf.filename
        original = self._real(escrito)
        if not original.is_file():
            self._fin("GeoCAD Yaguareté: no se encuentra el archivo original de la imagen "
                      f"({original}).")
            return
        tenia_fondo = fondo_de(img) is not None
        r = ventana(getattr(self.ctx.services, "window", None), original, valores,
                    guardado is not None, tenia_fondo)
        if not r:
            self._fin("ASPECTOIMAGEN cancelado.")
            return
        from . import georref_progreso as GP

        pantalla = getattr(self.ctx.services, "window", None)
        fondo = bool(r.get("fondo_blanco", tenia_fondo))
        # el fondo se pone (o se rehace al contorno actual) o se quita
        fondo_cmd = FondoCommand(img, fondo) if (fondo or tenia_fondo) else None
        if r.get("accion") == "original":
            if guardado is None:
                if fondo != tenia_fondo:
                    self._solo_fondo(fondo_cmd, fondo)
                    return
                self._fin("La imagen ya usa su archivo original.")
                return
            with GP.Progreso(pantalla, "ASPECTOIMAGEN") as prog:
                self.ctx.execute(self._con_fondo(AspectoCommand(img, escrito, None), fondo_cmd))
                prog.regeneracion(pantalla, img.dxf.handle, 0, 100,
                                  etapa="Volviendo al original: actualizando la pantalla")
            self._fin(f"La imagen vuelve a su original: {original}. U lo deshace.")
            return
        valores = normalizar(r.get("valores"))
        final = r.get("accion") == "final"
        valores["final"] = final
        _ultimos[0] = dict(valores, final=False)
        if final:
            # la entrega: la imagen nueva ya trae el papel blanco; el fondo
            # de la capa ya no hace falta y se quita
            fondo = False
            fondo_cmd = FondoCommand(img, False) if tenia_fondo else None
        if guardado is not None and valores == guardado[0] and fondo != tenia_fondo:
            # el aspecto no cambió: sólo el fondo, sin rehacer la copia
            self._solo_fondo(fondo_cmd, fondo)
            return
        ruta_dibujo = getattr(self._documento(), "path", None)
        w, h = G.tamano(img)
        mp = w * h / 1e6
        # 3.31.2 (Fernando): con un plano grande el sistema decía «IngeCAD no
        # responde»; ahora una barra con el porcentaje de cada etapa
        with GP.Progreso(pantalla, "ASPECTOIMAGEN") as prog:
            try:
                t0 = time.monotonic()
                fuente = prog.trabajo("1/4  Abriendo la imagen", lambda: abrir(original),
                                      estimar("abrir", mp), 0, 15)
                medir("abrir", mp, time.monotonic() - t0)
                hecho = [0.0]
                hecha = prog.trabajo("2/4  Aplicando el aspecto",
                                     lambda: procesar(fuente, valores, hecho), 0, 15, 35, hecho=hecho)
                del fuente
                copia = destino(original, ruta_dibujo, SUFIJO_FINAL if final else SUFIJO)
                t0 = time.monotonic()
                prog.trabajo("3/4  Guardando la copia", lambda: guardar_png(hecha, copia, final),
                             estimar("guardar", mp), 50, 25)
                medir("guardar", mp, time.monotonic() - t0)
                vacia = invisible(hecha)
                del hecha
            except (AspectoError, OSError, MemoryError) as exc:
                prog.cerrar()
                self._fin(f"GeoCAD Yaguareté: no se pudo hacer la copia ({exc}).")
                return
            self.ctx.execute(self._con_fondo(
                AspectoCommand(img, str(copia), etiquetas(valores, escrito)), fondo_cmd))
            prog.regeneracion(pantalla, img.dxf.handle, 75, 25,
                              etapa="4/4  Actualizando la pantalla")
        if final:
            self.ctx.echo(f"Imagen final, con fondo blanco y opaca: {copia}. Es la que se "
                          "entrega; la imagen del dibujo pasa a usarla (el original no se "
                          "toca). U lo deshace.")
        else:
            self.ctx.echo(f"Aspecto de la imagen: {describir(valores)}. Copia: {copia} "
                          "(el original no se toca). U lo deshace.")
        if vacia:
            # 3.31.1: un negativo ya exportado (líneas blancas sobre transparente)
            # se borra entero: lo claro es lo que «Blanco que se borra» quita
            self.ctx.echo("Atención: la imagen quedó invisible (todo lo claro se borra). Si es un "
                          "negativo ya hecho, use la imagen original o quite «Fondo "
                          "transparente». U lo deshace.")
        if fondo_cmd is not None:
            self._echo_fondo(fondo_cmd, fondo)
        if not ruta_dibujo:
            self.ctx.echo("El dibujo no está guardado: la copia quedó fuera de su carpeta. "
                          "Si lleva el dibujo a otra computadora, lleve también esa imagen.")
        self.ctx.finish()

    # -- resaltado: la imagen bajo el cursor ------------------------------------
    def resaltado(self, cursor) -> dict:
        if cursor is None:
            return {}
        img, _o = self._buscar(tuple(cursor))
        return {"cursor": G.marco(G.esquinas(img))} if img is not None else {}
