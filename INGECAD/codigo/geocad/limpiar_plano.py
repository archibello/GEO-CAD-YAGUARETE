# SPDX-License-Identifier: GPL-3.0-or-later
"""LIMPIARPLANO: limpiar un plano antiguo escaneado (3.86.0).

Pedido de Fernando (19/11/2026, plano de mensura de 1958 con manchas de
humedad): sacar las manchas y los pliegues y que los textos se lean al
final. Va con el módulo «georref» (Imágenes), en la barra «Yaguá Imagenes»
y en el menú GeoCAD, junto a ASPECTOIMAGEN.

  1. clic en la imagen (o elegida antes);
  2. zonas de sello (opcional): dos esquinas por rectángulo; ahí van
     umbrales suaves para la tinta tenue (sellos de goma, lápiz, firmas).
     D deshace la última zona; Enter limpia;
  3. se hace la copia limpia (las cuentas: limpieza.py), en gris y al doble
     de resolución (así se leen los rumbos chicos), como PNG en la carpeta de
     imágenes del dibujo (la de PEGARIMAGEN), sin pisar nada; la imagen pasa
     a usarla en el mismo lugar y del mismo tamaño. Un U lo deshace.

El original NUNCA se toca. Queda anotado en la imagen (XDATA
GEOCAD_LIMPIEZA) con las zonas: al volver a limpiarla se parte otra vez del
original y aparecen las zonas de antes, para corregirlas. Si la imagen tenía
aspecto (ASPECTOIMAGEN) o recorte de GeoCAD, se limpia el archivo que usa
ahora y esas marcas se sueltan (U las devuelve): ASPECTOIMAGEN después
parte de la copia limpia. Sin Qt (las pruebas), sin barra de avance.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tools.base import Tool

from . import georref as G
from . import limpieza as L

APPID = "GEOCAD_LIMPIEZA"
MARCA = "LIMPIEZA 1"
SUFIJO = "_limpio"
#: marcas de otras órdenes que dejan de valer sobre la copia limpia
OTRAS = ("GEOCAD_ASPECTO", "GEOCAD_RECORTE")

PEDIDO = "Designe la imagen del plano a limpiar (clic en la imagen o en su borde):"
PEDIDO_ZONA = ("Zona de sello (tinta tenue): primera esquina, D deshace la última, "
               "Enter limpia:")
PEDIDO_ESQUINA = "Esquina opuesta de la zona de sello:"


# ------------------------------------------------------------------ las marcas
def leer(img):
    """(original como estaba escrito, zonas) o None si no está limpia."""
    try:
        tags = [t[1] for t in img.get_xdata(APPID)]
    except Exception:  # noqa: BLE001 -- sin XDATA
        return None
    if len(tags) < 3 or tags[0] != MARCA:
        return None
    try:
        zonas = [tuple(int(c) for c in z) for z in json.loads(tags[1])]
    except (TypeError, ValueError):
        zonas = []
    return "".join(str(t) for t in tags[2:]), zonas


def etiquetas(original, zonas) -> list:
    original = str(original)
    trozos = [original[i:i + 200] for i in range(0, len(original), 200)] or [""]
    return ([(1000, MARCA), (1000, json.dumps([list(z) for z in zonas]))]
            + [(1000, t) for t in trozos])


def _xdata(img, appid):
    try:
        return list(img.get_xdata(appid))
    except Exception:  # noqa: BLE001
        return None


def _poner(img, appid, tags) -> None:
    if tags:
        doc = img.doc
        if doc is not None and appid not in doc.appids:
            doc.appids.add(appid)
        img.set_xdata(appid, tags)
    elif img.has_xdata(appid):
        img.discard_xdata(appid)


# ------------------------------------------------------------------ archivos
def destino(original, ruta_dibujo) -> Path:
    from . import aspecto, pegarimagen
    carpeta = pegarimagen.carpeta_destino(ruta_dibujo)
    carpeta.mkdir(parents=True, exist_ok=True)
    return aspecto.nombre_copia(carpeta, original, SUFIJO)


def limpiar_archivo(original, zonas=(), avance=None):
    """La imagen limpia (PIL) de un archivo."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    try:
        im = Image.open(str(original))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise L.LimpiezaError(f"no se puede leer {Path(original).name} ({exc})") from exc
    return L.limpiar(im, zonas, avance=avance)


def guardar(hecha, ruta) -> None:
    hecha.save(str(ruta), "PNG", compress_level=3)


# ------------------------------------------------------------------ el comando
class LimpiezaCommand(G.GeorrefCommand):
    """La imagen apunta a la copia limpia, con su tamaño nuevo en píxeles y
    en el mismo lugar (los vectores de píxel se achican en la misma
    proporción, desde el punto de inserción). Un U deshace todo."""

    def __init__(self, img, archivo, tamano_nuevo, tags) -> None:
        from ezdxf.math import Matrix44
        w, _h = G.tamano(img)
        f = w / float(tamano_nuevo[0])
        ix, iy, iz = (float(c) for c in img.dxf.insert)
        m = Matrix44.translate(-ix, -iy, -iz) @ Matrix44.scale(f, f, 1) @ Matrix44.translate(ix, iy, iz)
        super().__init__(img, m, copia=archivo, tamano=tamano_nuevo)
        self.name = "LIMPIARPLANO"
        self.tags = tags
        self._antes = None

    def do(self, document) -> None:
        super().do(document)
        if not self.entities:
            return
        img = self.img
        self._antes = {a: _xdata(img, a) for a in (APPID,) + OTRAS}
        for a in OTRAS:
            _poner(img, a, None)
        _poner(img, APPID, self.tags)

    def undo(self, document) -> None:
        if self.entities and self._antes is not None:
            for a, tags in self._antes.items():
                _poner(self.img, a, tags)
        super().undo(document)


# ------------------------------------------------------------------ la orden
class LimpiarPlanoTool(Tool):
    """LIMPIARPLANO: clic en una imagen, zonas de sello y Enter."""

    entity_picker = True

    def start(self) -> None:
        self.name = "LIMPIARPLANO"
        self.img = None
        self.zonas = []            # en píxeles del ORIGINAL (arriba a la izquierda = 0, 0)
        self.esquina = None        # primera esquina de la zona en curso (dibujo)
        s = self.ctx.services
        previa = list(getattr(s, "selection", None) or ())
        if previa:
            aux = G.GeorrefTool(self.ctx)
            imgs = [e for h in previa if (e := aux._entidad(h)) is not None and e.dxftype() == "IMAGE"]
            if len(imgs) == 1:
                s.selection = set()
                self._elegida(imgs[0])
                return
        self.prompt(PEDIDO)

    # -- archivos -----------------------------------------------------------------
    def _documento(self):
        return getattr(getattr(self.ctx.services, "window", None), "document", None)

    def _real(self, escrito) -> Path:
        p = Path(str(escrito))
        if not p.is_absolute():
            base = getattr(self._documento(), "path", None)
            if base:
                p = Path(str(base)).parent / p
        return p

    def _fin(self, texto: str) -> None:
        self.ctx.echo(texto)
        self.ctx.finish()

    # -- elegir la imagen ------------------------------------------------------------
    def _elegida(self, img) -> None:
        marca = leer(img)
        escrito = marca[0] if marca else img.image_def.dxf.filename
        original = self._real(escrito)
        if not original.is_file():
            self._fin("GeoCAD Yaguareté: no se encuentra el archivo de la imagen "
                      f"({original}).")
            return
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(str(original)) as im:
                self.tam_original = im.size
        except Exception as exc:  # noqa: BLE001
            self._fin(f"GeoCAD Yaguareté: no se puede leer {original.name} ({exc}).")
            return
        self.img, self.escrito, self.original = img, escrito, original
        self.zonas = list(marca[1]) if marca else []
        if marca:
            self.ctx.echo(f"La imagen ya está limpia: se rehace desde el original ({original.name})"
                          + (f" con sus {len(self.zonas)} zonas de sello." if self.zonas else "."))
        self.prompt(PEDIDO_ZONA)

    def on_point(self, point) -> None:
        p = (float(point[0]), float(point[1]))
        if self.img is None:
            img, otro = G.GeorrefTool(self.ctx)._imagen_en(p)
            if img is None:
                if otro is not None:
                    self.ctx.echo(f"GeoCAD Yaguareté: {otro.dxftype()} no es una imagen.")
                self.prompt(PEDIDO)
                return
            self._elegida(img)
            return
        if self.esquina is None:
            self.esquina = p
            self.prompt(PEDIDO_ESQUINA)
            return
        zona = self._zona(self.esquina, p)
        self.esquina = None
        if zona is None:
            self.ctx.echo("La zona queda fuera de la imagen: no se agrega.")
        else:
            self.zonas.append(zona)
            self.ctx.echo(f"Zona de sello {len(self.zonas)}: {zona[2] - zona[0]} × "
                          f"{zona[3] - zona[1]} píxeles.")
        self.prompt(PEDIDO_ZONA)

    def ortho_applies(self) -> bool:
        return self.esquina is None

    def on_option(self, text: str) -> bool:
        t = text.strip().upper().lstrip("_")
        if self.img is None or t not in ("D", "U", "DESHACER", "UNDO"):
            return False
        if self.esquina is not None:
            self.esquina = None
        elif self.zonas:
            self.zonas.pop()
            self.ctx.echo(f"Zona de sello quitada; quedan {len(self.zonas)}.")
        else:
            self.ctx.echo("No hay zonas de sello.")
        self.prompt(PEDIDO_ZONA)
        return True

    def on_enter(self) -> None:
        if self.img is None:
            self._fin("LIMPIARPLANO cancelado.")
            return
        if self.esquina is not None:       # Enter a mitad de una zona: se descarta
            self.esquina = None
        self._limpiar()

    def on_cancel(self) -> None:
        self._fin("LIMPIARPLANO cancelado.")

    # -- píxeles <-> dibujo ----------------------------------------------------------
    def _a_original(self, p) -> tuple:
        """Punto del dibujo -> píxel del original (arriba a la izquierda = 0, 0)."""
        w, h = G.tamano(self.img)
        x, y = G.mundo_a_pixel(self.img, p)
        ow, oh = self.tam_original
        return x * ow / w, -y * oh / h

    def _a_dibujo(self, px, py) -> tuple:
        w, h = G.tamano(self.img)
        ow, oh = self.tam_original
        return G.pixel_a_mundo(self.img, (px * w / ow, -py * h / oh))

    def _zona(self, a, b):
        try:
            (x0, y0), (x1, y1) = self._a_original(a), self._a_original(b)
        except ZeroDivisionError:
            return None
        return L._zona((x0, y0, x1, y1), self.tam_original)

    def _marco_zona(self, z) -> list:
        x0, y0, x1, y1 = z
        return G.marco([self._a_dibujo(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])

    # -- limpiar ---------------------------------------------------------------------
    def _limpiar(self) -> None:
        from . import georref_progreso as GP

        img, original, zonas = self.img, self.original, list(self.zonas)
        pantalla = getattr(self.ctx.services, "window", None)
        ruta_dibujo = getattr(self._documento(), "path", None)
        ow, oh = self.tam_original
        mp = ow * oh / 1e6
        with GP.Progreso(pantalla, "LIMPIARPLANO") as prog:
            try:
                hecho = [0.0]
                t0 = time.monotonic()
                hecha = prog.trabajo(
                    "1/3  Limpiando el plano",
                    lambda: limpiar_archivo(original, zonas, lambda f: hecho.__setitem__(0, f)),
                    max(2.0, 0.6 * mp), 0, 60, hecho=hecho)
                copia = destino(original, ruta_dibujo)
                prog.trabajo("2/3  Guardando la copia limpia", lambda: guardar(hecha, copia),
                             max(1.0, 0.3 * mp), 60, 20)
                tam = hecha.size
                del hecha
            except (L.LimpiezaError, OSError, MemoryError) as exc:
                prog.cerrar()
                self._fin(f"GeoCAD Yaguareté: no se pudo limpiar la imagen ({exc}).")
                return
            self.ctx.execute(LimpiezaCommand(img, str(copia), tam, etiquetas(self.escrito, zonas)))
            prog.regeneracion(pantalla, img.dxf.handle, 80, 20,
                              etapa="3/3  Actualizando la pantalla")
        segundos = time.monotonic() - t0
        self.ctx.echo(f"Plano limpio ({tam[0]} × {tam[1]} píxeles, "
                      + (f"{len(zonas)} zonas de sello, " if zonas else "")
                      + f"{segundos:.0f} s): {copia}. El original no se toca. U lo deshace.")
        if not ruta_dibujo:
            self.ctx.echo("El dibujo no está guardado: la copia quedó fuera de su carpeta. "
                          "Si lleva el dibujo a otra computadora, lleve también esa imagen.")
        self.ctx.finish()

    # -- lo que se ve ----------------------------------------------------------------
    def preview_segments(self, cursor) -> list:
        if self.img is None or self.esquina is None or cursor is None:
            return []
        try:
            z = self._zona(self.esquina, (float(cursor[0]), float(cursor[1])))
        except Exception:  # noqa: BLE001
            return []
        return self._marco_zona(z) if z else []

    def resaltado(self, cursor) -> dict:
        if self.img is None:
            if cursor is None:
                return {}
            img, _o = G.GeorrefTool(self.ctx)._imagen_en(tuple(cursor))
            return {"cursor": G.marco(G.esquinas(img))} if img is not None else {}
        segs = []
        for z in self.zonas:
            segs += self._marco_zona(z)
        return {"elegido": G.marco(G.esquinas(self.img)), "sel_borde": segs}
