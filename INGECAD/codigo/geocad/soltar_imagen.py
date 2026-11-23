# SPDX-License-Identifier: GPL-3.0-or-later
"""SOLTARIMAGEN (GEODROPIMAGE): una imagen arrastrada desde el explorador (3.88.0).

Pedido de Fernando (23/11/2026): «volcar desde el explorador un archivo de
imagen al área en pantalla, ofreciendo dos puntos de escalado previo y giro
al final antes de agregar definitivamente la imagen». Al soltar el archivo
sobre el dibujo:

  1. la esquina INFERIOR IZQUIERDA de la imagen;
  2. un segundo punto: la distancia del 1º al 2º es el ANCHO de la imagen (la
     escala; el alto sigue la proporción). La imagen se ve, derecha, estirándose
     con el cursor. También se puede escribir el ancho;
  3. el GIRO, alrededor del 1er punto: con el cursor (la imagen gira con él;
     ORTO lo deja en 0/90/180/270), escrito en grados (antihorario) o Enter = 0°.

Recién ahí queda la IMAGE (capa actual, apunta al archivo soltado tal cual,
U la quita). En Wayland (IngeCAD en Flatpak) Qt no siempre entrega la ruta en
urls(): deja un número del portal de archivos; la ruta se lee entonces del
texto soltado o se le pide al portal (3.88.1, Fernando: «en IngeCAD no funcionó»).
Esc en cualquier paso: no queda nada. Apagado el módulo
«georref», el lienzo vuelve a no aceptar lo arrastrado, como venía.

Las cuentas (``ubicar``, ``esquinas_giradas``) no usan Qt.
"""
from __future__ import annotations

import math
from pathlib import Path

from tools.base import Tool

from . import modulos
from .pegarimagen import EXTENSIONES, comando, esquinas

PROGRAMA = "ingecad"
NOMBRE = "GEODROPIMAGE"

#: el archivo soltado, para la orden que arranca enseguida
_pendiente: list = []


# ------------------------------------------------------------------ las cuentas
def ancho_de(p1, p2) -> float:
    """El ancho que da el 2º punto: la distancia del 1º al 2º."""
    return math.hypot(float(p2[0]) - float(p1[0]), float(p2[1]) - float(p1[1]))


def angulo_de(p1, p) -> float:
    """La dirección (grados, antihoraria desde el este) del 1er punto a ``p``."""
    return math.degrees(math.atan2(float(p[1]) - float(p1[1]), float(p[0]) - float(p1[0])))


def ubicar(p1, ancho: float, giro: float):
    """El punto final del borde de abajo: el que usa ``pegarimagen.comando``."""
    a = math.radians(giro)
    return (float(p1[0]) + ancho * math.cos(a), float(p1[1]) + ancho * math.sin(a))


def esquinas_giradas(p1, ancho: float, giro: float, px: int, py: int) -> list:
    """Las 4 esquinas (inf. izq., inf. der., sup. der., sup. izq.)."""
    if ancho <= 0:
        return []
    return esquinas(p1, ubicar(p1, ancho, giro), px, py)


def leer_giro(texto: str):
    """Grados escritos («30», «-12,5», «30°»), o None."""
    t = texto.strip().replace(",", ".").rstrip("°dD").strip()
    try:
        return float(t)
    except ValueError:
        return None


def es_imagen(ruta) -> bool:
    return Path(str(ruta)).suffix.lower() in EXTENSIONES


def rutas_de_texto(texto) -> list:
    """Las rutas de un texto soltado: una por renglón, absolutas o «file://»."""
    from urllib.parse import unquote, urlparse
    if isinstance(texto, (bytes, bytearray)):
        texto = bytes(texto).decode("utf-8", "replace")
    rutas = []
    for linea in str(texto or "").replace("\x00", "\n").splitlines():
        linea = linea.strip()
        if linea.startswith("file://"):
            linea = unquote(urlparse(linea).path)
        if linea.startswith("/") or (len(linea) > 2 and linea[1] == ":" and linea[2] in "\\/"):
            rutas.append(Path(linea))
    return rutas


#: lo que trae un archivo arrastrado a un Flatpak en Wayland: Qt no siempre
#: lo traduce y deja en urls() un número en vez de la ruta (3.88.1)
PORTAL = "application/vnd.portal.filetransfer"


def del_portal(clave) -> list:
    """Las rutas que el portal de archivos guarda con esa clave."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        if isinstance(clave, (bytes, bytearray)):
            clave = bytes(clave).decode("utf-8", "replace")
        clave = str(clave).strip("\x00").strip()
        if not clave:
            return []
        i = QDBusInterface("org.freedesktop.portal.Documents", "/org/freedesktop/portal/documents",
                           "org.freedesktop.portal.FileTransfer", QDBusConnection.sessionBus())
        r = i.call("RetrieveFiles", clave, {})
        rutas = []
        for arg in r.arguments() or ():
            for ruta in (arg if isinstance(arg, (list, tuple)) else [arg]):
                rutas.extend(rutas_de_texto(str(ruta)))
        return rutas
    except Exception:  # noqa: BLE001 -- sin portal ni QtDBus
        return []


def candidatas(data, portal: bool = False) -> list:
    """Las rutas de lo arrastrado: urls(), el texto (Wayland) y, al soltar, el portal."""
    if data is None:
        return []
    rutas = []
    if data.hasUrls():
        rutas += [Path(u.toLocalFile()) for u in data.urls() if u.isLocalFile()]
    for formato in ("text/uri-list", "text/plain"):
        if data.hasFormat(formato):
            rutas += rutas_de_texto(bytes(data.data(formato)))
    if portal and not any(es_imagen(r) and r.is_file() for r in rutas) and data.hasFormat(PORTAL):
        rutas += del_portal(bytes(data.data(PORTAL)))
    return rutas


def imagen_soltada(data, portal: bool = False):
    """El primer archivo de imagen local de lo arrastrado, o None."""
    for ruta in candidatas(data, portal):
        if es_imagen(ruta) and ruta.is_file():
            return ruta
    return None


def quiza_imagen(data) -> bool:
    """¿Aceptar el arrastre? Una imagen ya reconocible, o lo que sólo el portal dirá al soltar."""
    return imagen_soltada(data) is not None or (data is not None and data.hasFormat(PORTAL))


def medida(ruta):
    """(ancho, alto) en píxeles, o None si no se puede leer."""
    try:
        import PIL.Image

        with PIL.Image.open(str(ruta)) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:  # noqa: BLE001 -- sin PIL o archivo raro: probar con Qt
        pass
    try:
        from PySide6.QtGui import QImageReader

        t = QImageReader(str(ruta)).size()
        if t.width() > 0 and t.height() > 0:
            return t.width(), t.height()
    except Exception:  # noqa: BLE001
        pass
    return None


# ------------------------------------------------------------------ la orden
class SoltarImagenTool(Tool):
    """La imagen soltada: esquina, ancho y giro."""

    NOMBRE = NOMBRE
    PRIMERO = "Imagen soltada. Esquina inferior izquierda:"
    SEGUNDO = "Segundo punto (la distancia da el ancho y la escala) o escriba el ancho:"
    TERCERO = "Giro alrededor de la esquina (señale o escriba los grados; Enter = 0°):"
    SIN_IMAGEN = ("GeoCAD Yaguareté: arrastre un archivo de imagen (PNG, JPG, TIF, BMP, GIF) "
                  "desde el explorador y suéltelo sobre el dibujo.")

    def start(self) -> None:
        self.name = self.NOMBRE
        ruta = _pendiente.pop() if _pendiente else None
        _pendiente.clear()
        self.empezar(ruta, medida(ruta) if ruta is not None else None)

    def empezar(self, ruta, tam) -> None:
        """Con el archivo ya leído (las pruebas llaman acá directamente)."""
        self._ruta = Path(str(ruta)) if ruta is not None else None
        self._tam = tam
        self._p1 = None
        self._ancho = None
        self._muestra = None
        if self._ruta is None or not tam or tam[0] <= 0 or tam[1] <= 0:
            if self._ruta is not None:
                self.ctx.echo(f"GeoCAD Yaguareté: no se pudo leer la imagen {self._ruta.name}.")
            else:
                self.ctx.echo(self.SIN_IMAGEN)
            self.ctx.finish()
            return
        _enganchar_pintura(self)
        self.prompt(self.PRIMERO)

    # -- lo que se ve
    def esquinas_con(self, cursor) -> list:
        """Las esquinas de la imagen según el paso y el cursor."""
        if getattr(self, "_tam", None) is None or self._p1 is None or cursor is None:
            return []
        px, py = self._tam
        if self._ancho is None:
            return esquinas_giradas(self._p1, ancho_de(self._p1, cursor), 0.0, px, py)
        return esquinas_giradas(self._p1, self._ancho, self._giro_cursor(cursor), px, py)

    def _giro_cursor(self, cursor) -> float:
        if cursor is None or ancho_de(self._p1, cursor) <= 1e-12:
            return 0.0
        return angulo_de(self._p1, cursor)

    def preview_segments(self, cursor) -> list:
        e = self.esquinas_con(cursor)
        if not e:
            return []
        lineas = [(e[i], e[(i + 1) % 4]) for i in range(4)]
        return lineas + [(self._p1, (float(cursor[0]), float(cursor[1])))]

    # -- los pasos
    def on_point(self, point) -> None:
        if getattr(self, "_tam", None) is None:
            return
        p = (float(point[0]), float(point[1]))
        if self._p1 is None:
            self._p1 = p
            self.last_point = p
            self.prompt(self.SEGUNDO)
            return
        if self._ancho is None:
            ancho = ancho_de(self._p1, p)
            if ancho <= 1e-12:
                self.ctx.echo("El segundo punto tiene que ser distinto del primero.")
                return
            self._fijar_ancho(ancho)
            return
        if ancho_de(self._p1, p) <= 1e-12:
            self._agregar(0.0)
            return
        self._agregar(angulo_de(self._p1, p))

    def _fijar_ancho(self, ancho: float) -> None:
        self._ancho = ancho
        self.prompt(self.TERCERO)

    def on_option(self, text: str) -> bool:
        if getattr(self, "_tam", None) is None or self._p1 is None:
            return False
        if self._ancho is None:
            try:
                ancho = float(text.replace(",", "."))
            except ValueError:
                return False
            if ancho <= 0:
                self.ctx.echo("El ancho tiene que ser mayor que cero.")
                return True
            self._fijar_ancho(ancho)
            return True
        giro = leer_giro(text)
        if giro is None:
            return False
        self._agregar(giro)
        return True

    def on_enter(self) -> None:
        if getattr(self, "_tam", None) is not None and self._p1 is not None \
                and self._ancho is not None:
            self._agregar(0.0)
            return
        self.ctx.echo("Imagen sin agregar.")
        self.ctx.finish()

    def on_cancel(self) -> None:
        if getattr(self, "_tam", None) is not None:
            self.ctx.echo("Imagen sin agregar.")
        self.ctx.finish()

    def _agregar(self, giro: float) -> None:
        px, py = self._tam
        p2 = ubicar(self._p1, self._ancho, giro)
        self.ctx.execute(comando(self._ruta, px, py, self._p1, p2, nombre=self.NOMBRE))
        texto_giro = f", girada {giro:.4g}°" if abs(giro) > 1e-9 else ""
        self.ctx.echo(f"Imagen agregada: {self._ruta.name}, {px} × {py} píxeles, "
                      f"{self._ancho:.4g} × {self._ancho * py / px:.4g} unidades{texto_giro}. "
                      "U la quita.")
        self.ctx.finish()


# ------------------------------------------------------------------ la imagen en pantalla
def _muestra(tool):
    """La imagen achicada para la vista previa (una sola vez), o None."""
    if tool._muestra is None:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage

            im = QImage(str(tool._ruta))
            if im.isNull():
                tool._muestra = False
            else:
                if max(im.width(), im.height()) > 1600:
                    im = im.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                tool._muestra = im
        except Exception:  # noqa: BLE001
            tool._muestra = False
    return tool._muestra or None


def pintar(visor, p, tool) -> bool:
    """La imagen semitransparente en su lugar provisorio. True si la pintó."""
    controlador = getattr(visor, "tool_delegate", None)
    cursor = getattr(controlador, "_cursor", None)
    if cursor is None:
        return False
    try:
        punto = controlador.resolved_point(*cursor)
    except Exception:  # noqa: BLE001
        return False
    e = tool.esquinas_con(punto)
    im = _muestra(tool) if e else None
    if im is None:
        return False
    from PySide6.QtGui import QTransform

    # píxel (0,0) = esquina superior izquierda; x hacia la inf. der.; y hacia abajo
    sup_izq = visor._space_to_screen(*e[3])
    sup_der = visor._space_to_screen(*e[2])
    inf_izq = visor._space_to_screen(*e[0])
    w, h = im.width(), im.height()
    t = QTransform((sup_der[0] - sup_izq[0]) / w, (sup_der[1] - sup_izq[1]) / w,
                   (inf_izq[0] - sup_izq[0]) / h, (inf_izq[1] - sup_izq[1]) / h,
                   sup_izq[0], sup_izq[1])
    p.save()
    try:
        p.setOpacity(0.6)
        p.setRenderHint(p.RenderHint.SmoothPixmapTransform, True)
        p.setTransform(t, True)
        p.drawImage(0, 0, im)
    finally:
        p.restore()
    return True


def _enganchar_pintura(tool) -> None:
    """Mientras corre la orden, el lienzo pinta la imagen debajo del contorno."""
    window = getattr(getattr(tool.ctx, "services", None), "window", None)
    visor = getattr(window, "viewport", None)
    if visor is None or not hasattr(type(visor), "_draw_tool_preview"):
        return
    vars(visor).pop("_draw_tool_preview", None)

    def dibujar(p):
        controlador = getattr(visor, "tool_delegate", None)
        if getattr(controlador, "tool", None) is not tool:
            vars(visor).pop("_draw_tool_preview", None)   # la orden terminó
        else:
            try:
                pintar(visor, p, tool)
            except Exception:  # noqa: BLE001 -- la vista previa nunca corta la orden
                pass
        type(visor)._draw_tool_preview(visor, p)

    dibujar._geocad_soltar = True
    visor._draw_tool_preview = dibujar


# ------------------------------------------------------------------ el arrastre
def _filtro(window):
    from PySide6.QtCore import QEvent, QObject

    class Filtro(QObject):
        def eventFilter(self, _obj, evento):  # noqa: N802 -- Qt
            t = evento.type()
            if t == QEvent.DragEnter:
                # se mira una vez al entrar: en Wayland cada lectura pide los datos al explorador
                self.acepta = quiza_imagen(evento.mimeData())
            if t in (QEvent.DragEnter, QEvent.DragMove):
                if getattr(self, "acepta", False):
                    evento.acceptProposedAction()
                    return True
                return False
            if t == QEvent.Drop:
                ruta = imagen_soltada(evento.mimeData(), portal=True)
                if ruta is None:
                    return False
                evento.acceptProposedAction()
                soltar(window, ruta)
                return True
            return False

    return Filtro(window.viewport)


def soltar(window, ruta) -> None:
    """Arranca la orden con el archivo soltado."""
    _pendiente[:] = [Path(str(ruta))]
    try:
        window.activateWindow()
        window.viewport.setFocus()
    except Exception:  # noqa: BLE001
        pass
    window.tools.start_tool(NOMBRE)


def aplicar(window) -> None:
    """El lienzo acepta imágenes arrastradas si el módulo «georref» está activo."""
    if window is None or not hasattr(window, "viewport") or not hasattr(window, "tools"):
        return
    quitar(window)
    if not modulos.activo(PROGRAMA, "georref"):
        return
    visor = window.viewport
    if not hasattr(visor, "installEventFilter"):
        return
    filtro = _filtro(window)
    window._geocad_soltar = (filtro, visor.acceptDrops())
    visor.setAcceptDrops(True)
    visor.installEventFilter(filtro)


def quitar(window) -> None:
    guardado = vars(window).pop("_geocad_soltar", None)
    if guardado is None:
        return
    filtro, antes = guardado
    window.viewport.removeEventFilter(filtro)
    window.viewport.setAcceptDrops(antes)
    filtro.deleteLater()
