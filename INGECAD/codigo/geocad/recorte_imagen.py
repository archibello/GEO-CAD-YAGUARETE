"""Recortar una imagen con Ctrl + agarre (3.35.0, pedido de Fernando).

Los agarres de una imagen en IngeCAD son sus cuatro esquinas y la escalan
desde la esquina opuesta. Con **Ctrl** al soltar el agarre, GeoCAD la
RECORTA: la esquina queda donde se suelta (con las referencias, justo en una
línea o un vértice) y los dos lados que llegan a ella se achican; la imagen
no se mueve ni cambia de escala. Hacia afuera se vuelve a abrir, hasta el
tamaño de la original: un recorte no pierde nada.

IngeCAD no dibuja el recorte que el DWG guarda en la imagen (muestra la
imagen entera), así que GeoCAD arma una COPIA recortada (los mismos píxeles,
sin remuestrear) en «<dibujo>_imagenes», como ASPECTOIMAGEN, y el dibujo
pasa a usarla. La original no se toca. En la imagen quedan anotados (XDATA)
la original y la ventana recortada, para volver a abrir. Un solo U lo
deshace. Mientras se arrastra con Ctrl la imagen queda quieta.

Va con el módulo «georref» (Imágenes georreferenciadas). Las cuentas no
usan Qt.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

APPID = "GEOCAD_RECORTE"
MARCA = "GEOCAD_RECORTE_1"

_activo_cache = [0.0, False]
#: mientras GeoCAD suelta el agarre él mismo, el agarre no escala
_soltando = [False]


class RecorteError(Exception):
    pass


def _activo() -> bool:
    """Módulo georref prendido (se relee el archivo cada 2 s como mucho)."""
    ahora = time.monotonic()
    if ahora - _activo_cache[0] > 2.0:
        _activo_cache[0] = ahora
        from . import modulos
        _activo_cache[1] = modulos.activo("ingecad", "georref")
    return _activo_cache[1]


def _ctrl() -> bool:
    """¿Está apretada la tecla Ctrl? Sin Qt (pruebas), no."""
    try:
        from PySide6 import QtCore, QtWidgets
    except Exception:  # noqa: BLE001
        return False
    if QtWidgets.QApplication.instance() is None:
        return False
    return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)


def _recortando(entity) -> bool:
    try:
        return entity.dxftype() == "IMAGE" and (_soltando[0] or (_activo() and _ctrl()))
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ la marca
def leer(img):
    """(original, (x0, y0, x1, y1)) si la imagen es un recorte de GeoCAD."""
    try:
        tags = [t[1] for t in img.get_xdata(APPID)]
    except Exception:  # noqa: BLE001 -- sin XDATA
        return None
    if len(tags) < 3 or tags[0] != MARCA:
        return None
    try:
        ventana = tuple(int(n) for n in json.loads(tags[1]))
    except (TypeError, ValueError):
        return None
    if len(ventana) != 4:
        return None
    return "".join(str(t) for t in tags[2:]), ventana


def etiquetas(original, ventana) -> list:
    """Marca, ventana (JSON) y la original en trozos de 200 caracteres (el
    límite de un texto de XDATA es 255)."""
    original = str(original)
    trozos = [original[i:i + 200] for i in range(0, len(original), 200)] or [""]
    return ([(1000, MARCA), (1000, json.dumps([int(n) for n in ventana]))]
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


# ------------------------------------------------------------------ las cuentas
def _vec(p):
    return float(p[0]), float(p[1])


def _local(img, punto):
    """(s, t) del punto en el marco entero de la imagen: 0..1 de izquierda a
    derecha (s) y de abajo hacia arriba (t)."""
    from . import georref as G
    w, h = G.tamano(img)
    ix, iy = _vec(img.dxf.insert)
    ux, uy = _vec(img.dxf.u_pixel)
    vx, vy = _vec(img.dxf.v_pixel)
    ax, ay, bx, by = ux * w, uy * w, vx * h, vy * h
    det = ax * by - ay * bx
    if abs(det) < 1e-18:
        raise RecorteError("la imagen no tiene tamaño")
    dx, dy = punto[0] - ix, punto[1] - iy
    return (dx * by - dy * bx) / det, (ax * dy - ay * dx) / det


def ventana_actual(img, document=None):
    """(original, (x0, y0, x1, y1) en píxeles de la original, arriba a la
    izquierda = 0, 0, ancho y alto de la original)."""
    from . import georref as G
    marca = leer(img)
    if marca is not None:
        original, ventana = marca
        ancho, alto = _tamano_archivo(original)
        return Path(original), ventana, ancho, alto
    ruta = G.archivo_imagen(img, document)
    if ruta is None:
        raise RecorteError("la imagen no tiene archivo")
    w, h = G.tamano(img)
    return Path(ruta), (0, 0, int(round(w)), int(round(h))), int(round(w)), int(round(h))


def _tamano_archivo(ruta):
    from . import aspecto
    Image = aspecto._pil()
    try:
        with Image.open(str(ruta)) as im:
            return im.size
    except Exception as exc:  # noqa: BLE001
        raise RecorteError(f"no se encuentra la original {Path(ruta).name}") from exc


def nueva_ventana(img, indice: int, punto, ventana, ancho: int, alto: int):
    """La ventana (en píxeles de la original) después de soltar la esquina
    ``indice`` en ``punto``: la esquina opuesta queda fija. Hacia afuera,
    hasta el borde de la original."""
    from . import georref as G
    esquinas = list(img.boundary_path_wcs())[:4]
    if indice >= len(esquinas):
        raise RecorteError("agarre desconocido")
    fija = esquinas[(indice + 2) % 4]
    fs, ft = _local(img, (fija.x, fija.y))
    ns, nt = _local(img, punto)
    s0, s1 = sorted((fs, ns))
    t0, t1 = sorted((ft, nt))
    w, h = G.tamano(img)
    x0, y0 = ventana[0], ventana[1]
    c0 = max(0, min(ancho, round(x0 + s0 * w)))
    c1 = max(0, min(ancho, round(x0 + s1 * w)))
    f0 = max(0, min(alto, round(y0 + (1 - t1) * h)))
    f1 = max(0, min(alto, round(y0 + (1 - t0) * h)))
    if c1 - c0 < 1 or f1 - f0 < 1:
        raise RecorteError("el recorte deja la imagen sin nada")
    return (c0, f0, c1, f1)


def nombre_copia(carpeta, original, ventana) -> Path:
    """<original>_recorte_<x>_<y>_<ancho>x<alto>.png: la misma ventana de la
    misma original es siempre el mismo archivo (U vuelve a una que existe)."""
    x0, y0, x1, y1 = ventana
    return Path(carpeta) / f"{Path(original).stem}_recorte_{x0}_{y0}_{x1 - x0}x{y1 - y0}.png"


def guardar_copia(original, ventana, ruta_dibujo):
    """Recorta la original (los mismos píxeles) y la guarda junto al
    dibujo: (ruta, tiene transparencia)."""
    from . import aspecto, pegarimagen
    carpeta = pegarimagen.carpeta_destino(ruta_dibujo)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = nombre_copia(carpeta, original, ventana)
    im = aspecto.abrir(original)
    transparente = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if not ruta.exists():
        hecha = im.crop(tuple(ventana))
        if hecha.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
            hecha = hecha.convert("RGBA" if transparente else "RGB")
        aspecto.guardar_png(hecha, ruta)
    return ruta, transparente


def preparar(img, indice: int, punto, document=None):
    """El comando que recorta ``img`` al soltar la esquina ``indice`` en
    ``punto`` (ya con las referencias), o RecorteError."""
    from ezdxf.math import Matrix44
    from . import georref as G
    original, ventana, ancho, alto = ventana_actual(img, document)
    nueva = nueva_ventana(img, indice, punto, ventana, ancho, alto)
    if nueva == tuple(ventana):
        raise RecorteError("la imagen queda igual")
    w, h = G.tamano(img)
    # la esquina inferior izquierda nueva, en el marco de ahora
    s = (nueva[0] - ventana[0]) / w
    t = 1 - (nueva[3] - ventana[1]) / h
    ix, iy = _vec(img.dxf.insert)
    ux, uy = _vec(img.dxf.u_pixel)
    vx, vy = _vec(img.dxf.v_pixel)
    nx, ny = ix + s * ux * w + t * vx * h, iy + s * uy * w + t * vy * h
    matriz = Matrix44.translate(nx - ix, ny - iy, 0)
    tamano = (nueva[2] - nueva[0], nueva[3] - nueva[1])
    if nueva == (0, 0, ancho, alto):
        copia, transparente, marca = original, False, None      # de vuelta entera
    else:
        ruta_dibujo = getattr(document, "path", None)
        copia, transparente = guardar_copia(original, nueva, ruta_dibujo)
        marca = etiquetas(original, nueva)
    return RecorteCommand(img, matriz, copia, tamano, transparente, marca)


_clase_cache: list = []


def _clase():
    """RecorteCommand hereda de GeorrefCommand (que necesita IngeCAD): se
    arma la primera vez que se usa."""
    if _clase_cache:
        return _clase_cache[0]
    from . import georref as G

    class RecorteCommand(G.GeorrefCommand):
        """La imagen recortada: otra copia, otro tamaño y la esquina en su
        lugar, en un solo paso (U lo deshace entero, la marca incluida)."""

        def __init__(self, img, matriz, copia, tamano, transparente, marca) -> None:
            super().__init__(img, matriz, copia=copia, tamano=tamano, transparente=transparente)
            self.name = "RECORTE"
            self.marca = marca
            self._marca_antes = None

        def do(self, document) -> None:
            self._marca_antes = _xdata(self.img)
            super().do(document)
            _poner_xdata(self.img, self.marca)

        def undo(self, document) -> None:
            super().undo(document)
            _poner_xdata(self.img, self._marca_antes)

    _clase_cache.append(RecorteCommand)
    return RecorteCommand


def RecorteCommand(*args, **kwargs):  # noqa: N802 -- se usa como una clase
    return _clase()(*args, **kwargs)


# ------------------------------------------------------------------ IngeCAD
def _envolver_agarre(original):
    def apply_grip_edit(entity, grip_index, role, new_point):
        if _recortando(entity):
            return True       # con Ctrl la imagen no se escala: se recorta al soltar
        return original(entity, grip_index, role, new_point)

    apply_grip_edit._puente_original = original
    apply_grip_edit._puente_fabrica = _envolver_agarre
    return apply_grip_edit


def _echo(controlador, texto: str) -> None:
    try:
        controlador.window.command_line.echo(texto)
    except Exception:  # noqa: BLE001
        pass


def _envolver_soltar(original):
    def finish_grip_drag(self, wx, wy):
        datos = getattr(self, "_grip_drag", None)
        try:
            handle, indice, _rol, snap = datos
            entidad = self.index.entity(handle) if snap is not None else None
            recortar = (entidad is not None and entidad.dxftype() == "IMAGE"
                        and _activo() and _ctrl())
        except Exception:  # noqa: BLE001
            recortar = False
        if not recortar:
            return original(self, wx, wy)
        documento = self.window.document
        snap.undo(documento)           # la imagen como estaba al tomar el agarre
        comando, aviso = None, ""
        try:
            comando = preparar(entidad, indice, (wx, wy), documento)
        except RecorteError as exc:
            aviso = f"GeoCAD Yaguareté: no se recorta, {exc}."
        except Exception as exc:  # noqa: BLE001
            aviso = f"GeoCAD Yaguareté: no se pudo recortar la imagen ({exc})."
        base = getattr(self, "_grip_base", None) or (wx, wy)
        _soltando[0] = True
        try:
            original(self, *base)      # suelta el agarre sin cambiar nada
        finally:
            _soltando[0] = False
        historia = getattr(self.window, "history", None)
        pila = getattr(historia, "_undo", None)
        if pila and pila[-1] is snap:
            pila.pop()                 # ese paso vacío no cuenta para U
        if comando is not None:
            self._execute(comando)
            w, h = comando.tamano
            _echo(self, f"Imagen recortada: {int(w)} x {int(h)} píxeles. "
                        "Con Ctrl hacia afuera se vuelve a abrir.")
        elif aviso:
            _echo(self, aviso)

    finish_grip_drag._puente_original = original
    finish_grip_drag._puente_fabrica = _envolver_soltar
    return finish_grip_drag


def _poner(modulo, nombre: str, fabrica) -> None:
    actual = getattr(modulo, nombre, None)
    if actual is None or getattr(actual, "_puente_fabrica", None) is fabrica:
        return
    setattr(modulo, nombre, fabrica(getattr(actual, "_puente_original", actual)))


def instalar() -> None:
    """Se llama al cargar el plugin. Sin la ventana de IngeCAD (pruebas) se
    instala sólo sobre core.select."""
    try:
        from core import select
    except Exception:  # noqa: BLE001
        return
    _poner(select, "apply_grip_edit", _envolver_agarre)
    try:
        from views import tool_controller
    except Exception:  # noqa: BLE001 -- sin Qt
        return
    _poner(tool_controller, "apply_grip_edit", _envolver_agarre)
    from .dibujo import envolver
    envolver(tool_controller.ToolController, "finish_grip_drag", _envolver_soltar, reemplazar=True)
