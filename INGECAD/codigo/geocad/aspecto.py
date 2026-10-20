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
  - la opacidad general.

El archivo original NUNCA se toca: se guarda una copia PNG en la carpeta de
imágenes del dibujo (la de PEGARIMAGEN), la imagen pasa a usarla y U lo
deshace. Los valores y el archivo original quedan en la imagen (XDATA
GEOCAD_ASPECTO): la ventana vuelve a abrir con ellos, se rehace siempre desde
el original, «Volver al original» la devuelve, y EXPORTARKML (3.32.0) los
usa. Las cuentas usan PIL y numpy (IngeCAD los trae) y no usan Qt.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tools.base import Tool

from . import georref as G
from . import pegarimagen

APPID = "GEOCAD_ASPECTO"
MARCA = "ASPECTO 1"
SUFIJO = "_aspecto"
LINEAS = ("como", "negativo", "color")

#: los valores iniciales («Valores iniciales» en la ventana)
DEFECTO = {"transparente": True, "blanco": 25, "lineas": "como",
           "color": "#FF2020", "opacidad": 100}
BLANCO_MAX = 80
OPACIDAD_MIN = 10

#: los últimos usados en la sesión, para una imagen que todavía no tiene aspecto
_ultimos = [dict(DEFECTO)]


class AspectoError(Exception):
    """No se puede leer o procesar la imagen."""


# ------------------------------------------------------------------ los valores
def _color(texto) -> str:
    t = str(texto or "").strip().lstrip("#")
    if len(t) == 6:
        try:
            int(t, 16)
            return "#" + t.upper()
        except ValueError:
            pass
    return DEFECTO["color"]


def normalizar(valores) -> dict:
    """Los valores completos y dentro de sus márgenes."""
    v = dict(DEFECTO)
    v.update({k: x for k, x in dict(valores or {}).items() if k in DEFECTO})
    v["transparente"] = bool(v["transparente"])
    try:
        v["blanco"] = int(round(min(BLANCO_MAX, max(0, float(v["blanco"])))))
    except (TypeError, ValueError):
        v["blanco"] = DEFECTO["blanco"]
    try:
        v["opacidad"] = int(round(min(100, max(OPACIDAD_MIN, float(v["opacidad"])))))
    except (TypeError, ValueError):
        v["opacidad"] = DEFECTO["opacidad"]
    if v["lineas"] not in LINEAS:
        v["lineas"] = DEFECTO["lineas"]
    v["color"] = _color(v["color"])
    return v


def rgb(color) -> tuple:
    t = _color(color).lstrip("#")
    return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)


def describir(valores) -> str:
    """Una línea para la línea de comandos."""
    v = normalizar(valores)
    partes = [f"fondo transparente (blanco que se borra {v['blanco']} %)" if v["transparente"]
              else "fondo como está"]
    partes.append({"como": "líneas como están", "negativo": "líneas en negativo",
                   "color": f"líneas de color {v['color']}"}[v["lineas"]])
    partes.append(f"opacidad {v['opacidad']} %")
    return ", ".join(partes)


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


#: filas por franja: la cuenta va por franjas para decir cuánto lleva (la
#: barra de progreso, 3.31.2) y no tener toda la imagen en decimales a la vez
FILAS_FRANJA = 256


def _franja(a, v, color):
    """El aspecto de una franja de filas (uint8 RGBA -> uint8 RGBA)."""
    import numpy as np
    f = a.astype(np.float32)
    colores = f[..., :3]
    alfa = f[..., 3] / 255.0
    if v["transparente"]:
        lum = (0.299 * colores[..., 0] + 0.587 * colores[..., 1] + 0.114 * colores[..., 2]) / 255.0
        t = 1.0 - v["blanco"] / 100.0
        alfa = alfa * np.clip((t - lum) / t, 0.0, 1.0)
    alfa = alfa * (v["opacidad"] / 100.0)
    if v["lineas"] == "negativo":
        colores = 255.0 - colores
    elif v["lineas"] == "color":
        colores = np.broadcast_to(color, colores.shape)
    salida = np.empty(a.shape, dtype=np.uint8)
    salida[..., :3] = np.clip(np.rint(colores), 0, 255).astype(np.uint8)
    salida[..., 3] = np.clip(np.rint(alfa * 255.0), 0, 255).astype(np.uint8)
    return salida


def procesar(imagen, valores, hecho=None):
    """La imagen RGBA con el aspecto. La transparencia sale de la oscuridad
    de cada píxel: alfa = (T - L) / T, con L la luminancia (0 negro, 1
    blanco) y T = 1 - blanco/100: lo más claro que T queda invisible. Se
    multiplica por el alfa propio de la imagen y por la opacidad. Con
    ``hecho`` (una lista [0..1]) va diciendo cuánto lleva."""
    Image = _pil()
    import numpy as np
    v = normalizar(valores)
    im = imagen if imagen.mode == "RGBA" else imagen.convert("RGBA")
    a = np.asarray(im)
    color = np.array(rgb(v["color"]), dtype=np.float32)
    salida = np.empty(a.shape, dtype=np.uint8)
    alto = a.shape[0]
    for y in range(0, alto, FILAS_FRANJA):
        salida[y:y + FILAS_FRANJA] = _franja(a[y:y + FILAS_FRANJA], v, color)
        if hecho is not None:
            hecho[0] = min(alto, y + FILAS_FRANJA) / alto
    return Image.fromarray(salida, "RGBA")


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
def nombre_copia(carpeta, original) -> Path:
    """<original>_aspecto.png en ``carpeta``, sin pisar otra (…_2, …_3): U
    vuelve a la copia anterior, que tiene que seguir siendo la misma."""
    base = Path(original).stem
    ruta = Path(carpeta) / f"{base}{SUFIJO}.png"
    n = 2
    while ruta.exists():
        ruta = Path(carpeta) / f"{base}{SUFIJO}_{n}.png"
        n += 1
    return ruta


def invisible(imagen) -> bool:
    """¿No queda ningún píxel visible?"""
    return imagen.getchannel("A").getextrema()[1] == 0


#: compresión del PNG: la 6 de siempre tardaba más que la cuenta en un plano
#: de 37 megapíxeles; la 3 es bastante más rápida y casi del mismo tamaño
COMPRESION_PNG = 3


def destino(original, ruta_dibujo) -> Path:
    """Dónde va la copia (crea la carpeta)."""
    carpeta = pegarimagen.carpeta_destino(ruta_dibujo)
    carpeta.mkdir(parents=True, exist_ok=True)
    return nombre_copia(carpeta, original)


def guardar_png(hecha, ruta) -> None:
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


# ------------------------------------------------------------------ la ventana
def ventana(parent, original, valores, con_aspecto: bool):
    """{"accion": "aceptar" | "original", "valores"} o None (Cancelar).
    Las pruebas la reemplazan; sin Qt no hay ventana."""
    from . import aspecto_ui
    return aspecto_ui.ventana(parent, original, valores, con_aspecto)


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
        r = ventana(getattr(self.ctx.services, "window", None), original, valores,
                    guardado is not None)
        if not r:
            self._fin("ASPECTOIMAGEN cancelado.")
            return
        from . import georref_progreso as GP

        pantalla = getattr(self.ctx.services, "window", None)
        if r.get("accion") == "original":
            if guardado is None:
                self._fin("La imagen ya usa su archivo original.")
                return
            with GP.Progreso(pantalla, "ASPECTOIMAGEN") as prog:
                self.ctx.execute(AspectoCommand(img, escrito, None))
                prog.regeneracion(pantalla, img.dxf.handle, 0, 100,
                                  etapa="Volviendo al original: actualizando la pantalla")
            self._fin(f"La imagen vuelve a su original: {original}. U lo deshace.")
            return
        valores = normalizar(r.get("valores"))
        _ultimos[0] = dict(valores)
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
                copia = destino(original, ruta_dibujo)
                t0 = time.monotonic()
                prog.trabajo("3/4  Guardando la copia", lambda: guardar_png(hecha, copia),
                             estimar("guardar", mp), 50, 25)
                medir("guardar", mp, time.monotonic() - t0)
                vacia = invisible(hecha)
                del hecha
            except (AspectoError, OSError, MemoryError) as exc:
                prog.cerrar()
                self._fin(f"GeoCAD Yaguareté: no se pudo hacer la copia ({exc}).")
                return
            self.ctx.execute(AspectoCommand(img, str(copia), etiquetas(valores, escrito)))
            prog.regeneracion(pantalla, img.dxf.handle, 75, 25,
                              etapa="4/4  Actualizando la pantalla")
        self.ctx.echo(f"Aspecto de la imagen: {describir(valores)}. Copia: {copia} "
                      "(el original no se toca). U lo deshace.")
        if vacia:
            # 3.31.1: un negativo ya exportado (líneas blancas sobre transparente)
            # se borra entero: lo claro es lo que «Blanco que se borra» quita
            self.ctx.echo("Atención: la imagen quedó invisible (todo lo claro se borra). Si es un "
                          "negativo ya hecho, use la imagen original o quite «Fondo "
                          "transparente». U lo deshace.")
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
