# SPDX-License-Identifier: GPL-3.0-or-later
"""PEGARIMAGEN (GEOPASTEIMAGE): pegar la imagen del portapapeles (3.28.0).

Una captura de pantalla (o una imagen copiada en el navegador, en GIMP, o un
archivo de imagen copiado en el explorador) entra al dibujo en dos clics,
como pidió Fernando (17/10/2026): se captura, Ctrl+V y

  1. la esquina INFERIOR IZQUIERDA de la imagen;
  2. la esquina INFERIOR DERECHA: la imagen sigue al cursor (su contorno) y
     el clic le da la escala. La dirección del 1º al 2º punto es el borde de
     abajo: con ORTO (F8) queda derecha; sin ORTO, girada como se marque.
     También se puede escribir el ancho (en unidades del dibujo).

La IMAGE de IngeCAD siempre apunta a un archivo: la captura se guarda como
PNG en «<nombre del dibujo>_imagenes», junto al dibujo (o en
Imágenes/GeoCAD si el dibujo todavía no se guardó). Un archivo copiado se usa
tal cual. Va en la capa actual; U la quita. Las cuentas no usan Qt.

Ctrl+V: con una imagen en el portapapeles arranca PEGARIMAGEN; con objetos
copiados en IngeCAD (Ctrl+C) pega los objetos, como siempre. Apagado el
módulo «georref», Ctrl+V queda como venía.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from tools.base import Tool

from . import modulos

PROGRAMA = "ingecad"

EXTENSIONES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif")


# ------------------------------------------------------------------ las cuentas
def colocar(p1, p2, ancho: int, alto: int):
    """(esquina inferior izquierda, vector u por píxel, vector v por píxel)
    de la imagen de ``ancho`` × ``alto`` píxeles cuyo borde de abajo va de
    ``p1`` a ``p2``. None si los dos puntos coinciden."""
    x0, y0 = float(p1[0]), float(p1[1])
    dx, dy = float(p2[0]) - x0, float(p2[1]) - y0
    if math.hypot(dx, dy) <= 1e-12 or ancho <= 0 or alto <= 0:
        return None
    u = (dx / ancho, dy / ancho)
    v = (-u[1], u[0])                          # el píxel cuadrado, hacia arriba
    return (x0, y0), u, v


def esquinas(p1, p2, ancho: int, alto: int) -> list:
    """Las 4 esquinas (inf. izq., inf. der., sup. der., sup. izq.)."""
    c = colocar(p1, p2, ancho, alto)
    if c is None:
        return []
    (x0, y0), u, v = c
    bx, by = u[0] * ancho, u[1] * ancho
    hx, hy = v[0] * alto, v[1] * alto
    return [(x0, y0), (x0 + bx, y0 + by), (x0 + bx + hx, y0 + by + hy), (x0 + hx, y0 + hy)]


def comando(ruta, ancho: int, alto: int, p1, p2):
    """La IMAGE en el espacio actual (capa actual, deshacer de IngeCAD)."""
    (x0, y0), u, v = colocar(p1, p2, ancho, alto)
    lado = math.hypot(*u)

    def factory(space):
        image_def = space.doc.add_image_def(filename=str(ruta), size_in_pixel=(ancho, alto))
        img = space.add_image(image_def, insert=(x0, y0), size_in_units=(ancho * lado, alto * lado))
        img.dxf.insert = (x0, y0, 0.0)
        img.dxf.u_pixel = (u[0], u[1], 0.0)
        img.dxf.v_pixel = (v[0], v[1], 0.0)
        return img

    from core.actions import AddEntityCommand
    cmd = AddEntityCommand("GEOPASTEIMAGE", factory)
    cmd.needs_regen = True                     # como IMAGEATTACH: los píxeles piden la regeneración
    return cmd


# ------------------------------------------------------------------ dónde se guarda
def carpeta_destino(ruta_dibujo) -> Path:
    """Junto al dibujo, en «<nombre>_imagenes»; sin dibujo guardado, en
    Imágenes/GeoCAD (o Pictures/GeoCAD, o ~/GeoCAD)."""
    if ruta_dibujo:
        r = Path(str(ruta_dibujo))
        return r.parent / f"{r.stem}_imagenes"
    casa = Path.home()
    for nombre in ("Imágenes", "Pictures"):
        if (casa / nombre).is_dir():
            return casa / nombre / "GeoCAD"
    return casa / "GeoCAD"


def nombre_libre(carpeta, ahora=None) -> Path:
    """captura_AAAAMMDD_HHMMSS.png, sin pisar otra (…_2, …_3)."""
    base = "captura_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(ahora))
    ruta = Path(carpeta) / f"{base}.png"
    n = 2
    while ruta.exists():
        ruta = Path(carpeta) / f"{base}_{n}.png"
        n += 1
    return ruta


# ------------------------------------------------------------------ el portapapeles
class Copiada:
    """Lo que hay en el portapapeles: un archivo de imagen o una imagen
    suelta (``guardar(ruta)`` la escribe como PNG)."""

    def __init__(self, ancho: int, alto: int, archivo=None, guardar=None):
        self.ancho, self.alto = int(ancho), int(alto)
        self.archivo = Path(archivo) if archivo else None
        self._guardar = guardar

    def ruta_final(self, ruta_dibujo):
        """El archivo al que apunta la IMAGE (lo crea si hace falta)."""
        if self.archivo is not None:
            return self.archivo
        carpeta = carpeta_destino(ruta_dibujo)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = nombre_libre(carpeta)
        if not self._guardar(ruta):
            raise OSError(f"no se pudo escribir {ruta}")
        return ruta


def _archivo_copiado(data):
    """Un archivo de imagen copiado en el explorador de archivos."""
    if data is None or not data.hasUrls():
        return None
    for url in data.urls():
        ruta = Path(url.toLocalFile()) if url.isLocalFile() else None
        if ruta is not None and ruta.suffix.lower() in EXTENSIONES and ruta.is_file():
            return ruta
    return None


def _hay_imagen(data) -> bool:
    return data is not None and (data.hasImage() or _archivo_copiado(data) is not None)


def ctrl_v_es_imagen(hay_imagen: bool, hay_copia_ingecad: bool, copia_propia_en_curso: bool) -> bool:
    """¿Ctrl+V pega la imagen? Sólo si el portapapeles tiene una imagen y no
    una copia de objetos de IngeCAD (ni una de esta ventana que todavía se
    está escribiendo: el portapapeles aún muestra lo anterior)."""
    return hay_imagen and not hay_copia_ingecad and not copia_propia_en_curso


def del_portapapeles():
    """La imagen del portapapeles del sistema, o None."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001 -- sin Qt (pruebas)
        return None
    board = QApplication.clipboard()
    if board is None:
        return None
    archivo = _archivo_copiado(board.mimeData())
    if archivo is not None:
        try:
            import PIL.Image

            with PIL.Image.open(archivo) as im:
                return Copiada(im.size[0], im.size[1], archivo=archivo)
        except Exception:  # noqa: BLE001 -- no es una imagen legible: probar la imagen suelta
            pass
    imagen = board.image()
    if imagen is None or imagen.isNull():
        return None
    imagen = imagen.copy()                     # que no cambie si se copia otra cosa
    return Copiada(imagen.width(), imagen.height(),
                   guardar=lambda ruta: bool(imagen.save(str(ruta), "PNG")))


# ------------------------------------------------------------------ PEGARIMAGEN
class PegarImagenTool(Tool):
    """PEGARIMAGEN: la imagen del portapapeles, con dos clics."""

    NOMBRE = "GEOPASTEIMAGE"
    PRIMERO = "Esquina inferior izquierda de la imagen:"
    SEGUNDO = "Esquina inferior derecha (da la escala) o escriba el ancho:"
    SIN_IMAGEN = ("GeoCAD Yaguareté: el portapapeles no tiene una imagen. Haga una captura "
                  "de pantalla (Impr Pant, o Mayús+Impr Pant para una zona) o copie una "
                  "imagen, y vuelva a PEGARIMAGEN.")

    def start(self) -> None:
        self.name = self.NOMBRE
        self.empezar(del_portapapeles())

    def empezar(self, copiada) -> None:
        """Con la imagen ya leída (las pruebas llaman acá directamente)."""
        self._p1 = None
        self._copiada = copiada
        if copiada is None or copiada.ancho <= 0 or copiada.alto <= 0:
            self.ctx.echo(self.SIN_IMAGEN)
            self.ctx.finish()
            return
        self.prompt(self.PRIMERO)

    def preview_segments(self, cursor) -> list:
        """El contorno de la imagen, del primer punto al cursor, con sus
        diagonales; antes del primer punto, nada."""
        c = getattr(self, "_copiada", None)
        if c is None or self._p1 is None or cursor is None:
            return []
        e = esquinas(self._p1, cursor, c.ancho, c.alto)
        if not e:
            return []
        return [(e[i], e[(i + 1) % 4]) for i in range(4)] + [(e[0], e[2]), (e[1], e[3])]

    def on_point(self, point) -> None:
        if getattr(self, "_copiada", None) is None:
            return
        if self._p1 is None:
            self._p1 = (float(point[0]), float(point[1]))
            self.last_point = self._p1
            self.prompt(self.SEGUNDO)
            return
        if colocar(self._p1, point, self._copiada.ancho, self._copiada.alto) is None:
            self.ctx.echo("El segundo punto tiene que ser distinto del primero.")
            return
        self._pegar((float(point[0]), float(point[1])))

    def on_option(self, text: str) -> bool:
        if getattr(self, "_copiada", None) is None or self._p1 is None:
            return False
        try:
            ancho = float(text.replace(",", "."))
        except ValueError:
            return False
        if ancho <= 0:
            self.ctx.echo("El ancho tiene que ser mayor que cero.")
            return True
        self._pegar((self._p1[0] + ancho, self._p1[1]))
        return True

    def _pegar(self, p2) -> None:
        c = self._copiada
        window = getattr(self.ctx.services, "window", None)
        documento = getattr(window, "document", None)
        ruta_dibujo = getattr(documento, "path", None)
        try:
            ruta = c.ruta_final(ruta_dibujo)
        except Exception as exc:  # noqa: BLE001 -- carpeta sin permiso, disco lleno
            self.ctx.echo(f"GeoCAD Yaguareté: no se pudo guardar la imagen ({exc}).")
            self.ctx.finish()
            return
        self.ctx.execute(comando(ruta, c.ancho, c.alto, self._p1, p2))
        dx, dy = p2[0] - self._p1[0], p2[1] - self._p1[1]
        ancho = math.hypot(dx, dy)
        giro = math.degrees(math.atan2(dy, dx))
        texto_giro = f", girada {giro:.4g}°" if abs(giro) > 1e-9 else ""
        origen = "archivo copiado" if c.archivo is not None else "guardada en"
        self.ctx.echo(f"Imagen pegada: {c.ancho} × {c.alto} píxeles, {ancho:.4g} × "
                      f"{ancho * c.alto / c.ancho:.4g} unidades{texto_giro} ({origen} {ruta}). "
                      "U la quita.")
        if c.archivo is None and not ruta_dibujo:
            self.ctx.echo("El dibujo no está guardado: la imagen quedó fuera de su carpeta. "
                          "Si lleva el dibujo a otra computadora, lleve también esa imagen.")
        self.ctx.finish()


# ------------------------------------------------------------------ Ctrl+V
def _envolver_paste(original):
    def paste(self):
        try:
            if modulos.activo(PROGRAMA, "georref"):
                from PySide6.QtWidgets import QApplication
                from views import clipboard

                board = QApplication.clipboard()
                data = board.mimeData() if board is not None else None
                propia = bool(getattr(self, "_clip_writers", None)) \
                    or getattr(self, "_clip_pending", None) is not None
                if ctrl_v_es_imagen(_hay_imagen(data),
                                    data is not None and data.hasFormat(clipboard.MIME), propia):
                    self.start_tool("GEOPASTEIMAGE")
                    return None
        except Exception:  # noqa: BLE001 -- ante cualquier duda, Ctrl+V como venía
            pass
        return original(self)
    paste._puente_original = original
    paste._puente_fabrica = _envolver_paste
    return paste


def instalar() -> None:
    """Ctrl+V con una captura en el portapapeles: PEGARIMAGEN."""
    try:
        from views.tool_controller import ToolController
    except Exception:  # noqa: BLE001 -- sin la vista de IngeCAD (pruebas)
        return
    from .dibujo import envolver
    if getattr(ToolController.paste, "_puente_fabrica", None) is not _envolver_paste:
        envolver(ToolController, "paste", _envolver_paste, reemplazar=True)
