# SPDX-License-Identifier: GPL-3.0-or-later
"""Módulo «Google Earth» (3.33.0): las cuentas de la captura georreferenciada.

Google Earth no guarda georreferencia ni reproyecta a planas, y el BBOX que
informa no coincide con lo que se ve (prueba del 20/10/2026). Por eso:

  1) GeoCAD sabe la vista por un NetworkLink (``kml_enlaces``) y pone cuatro
     cruces magenta al 10 % del borde (``marcas_de_bbox``);
  2) en la foto de la ventana busca el centro de cada cruz por el cruce de
     sus brazos (``detectar``): la brújula y el logo de Google Earth pueden
     tapar parte de una cruz y el centro no se corre;
  3) con las cuatro marcas, en el sistema elegido (planas), calcula una
     transformación proyectiva píxel -> X, Y (``Pieza``); la convergencia de
     meridianos sale sola;
  4) rehace la imagen con el norte de la faja arriba (``componer``), una sola
     pieza o varias unidas (mosaico), recortada por dentro de las marcas, y
     mide las costuras entre piezas vecinas (``costuras``);
  5) la guarda como GeoTIFF (``geotiff``, sin GDAL ni PIL), PNG (``png``) o
     JPG (lo escribe cada programa) con su archivo de mundo y .prj.

Python puro con numpy (lo traen IngeCAD y QGIS; scipy y GDAL no siempre).
Las coordenadas de píxel son de esquina: el centro del píxel (i, j) es
(i + 0,5; j + 0,5), como en GDAL. Nada de Qt: la ventanita está en
googleearth_ui.py y el servidor y la foto en googleearth_vivo.py.
"""
from __future__ import annotations

import json
import math
import os
import re
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

PUERTO = 48765
ADENTRO = 0.10                 # las marcas, al 10 % del borde de la vista
ALTURA_PIEZA = 200.0           # m (Fernando, 20/10/2026)
TOPE_PIEZAS = 25
SOLAPE = 0.20                  # entre piezas vecinas del mosaico
SEGUNDOS_POR_PIEZA = 8.0       # medido: 6-9 s (vuelo + espera a que se aquiete)
NOMBRE_ENLACE = "GeoCAD Yaguareté"
CARPETA_DEFECTO = Path.home() / "Documentos" / "GeoCAD Google Earth"
FORMATOS = {"tif": "GeoTIFF (.tif)", "png": "PNG + PGW (.png)", "jpg": "JPG + JGW (.jpg)"}
MUNDO = {"tif": ".tfw", "png": ".pgw", "jpg": ".jgw"}
CALIDADES = {"pantalla": "Pantalla (lo que se ve)", "mosaico": "Mosaico (más detalle)",
             "zona": "Mosaico de lo que se ve en IngeCAD / QGIS"}


#: el aviso por el buzón: «la captura está en <ruta>, en <crs>» (Puente)
TIPO_MENSAJE = "imagen_google_earth"


def mensaje(ruta, crs: str) -> dict:
    return {"tipo": TIPO_MENSAJE, "ruta": str(Path(ruta).resolve()), "crs": str(crs or "")}


def ruta_de_mensaje(msg: dict):
    """La ruta de la imagen de un mensaje del otro programa, si existe."""
    if not isinstance(msg, dict) or msg.get("tipo") != TIPO_MENSAJE:
        return None
    p = Path(str(msg.get("ruta") or ""))
    return p if p.is_absolute() and p.is_file() and p.suffix.lower() in (".tif", ".png", ".jpg") \
        else None


class GoogleEarthError(RuntimeError):
    """Algo que el usuario puede arreglar; el texto se le muestra tal cual."""


# ================================================================== ajustes
# en la carpeta de la configuración común (~/.config/geocad): los dos
# programas leen y escriben los mismos (la carpeta de destino es una sola)

DEFECTOS = {
    "calidad": "pantalla",
    "formato": "tif",
    "carpeta": str(CARPETA_DEFECTO),
    "altura_pieza": ALTURA_PIEZA,
    "sistema": "",              # "" = el del dibujo (IngeCAD) o del proyecto (QGIS)
    "insertar_ingecad": True,
    "agregar_qgis": True,
    "fecha": "",
    "marcas_siempre": False,    # si las cruces no aparecen sólo al capturar
}


def archivo_kml() -> Path:
    """El enlace que se abre en Google Earth (lo escribe la ventanita)."""
    return Path.home() / ".config" / "geocad" / "googleearth" / "GeoCAD Google Earth.kml"


def archivo_ajustes() -> Path:
    return Path.home() / ".config" / "geocad" / "googleearth.json"


def _validar(clave: str, valor):
    d = DEFECTOS[clave]
    if clave == "calidad":
        return valor if valor in CALIDADES else d
    if clave == "formato":
        return valor if valor in FORMATOS else d
    if clave == "altura_pieza":
        try:
            v = float(str(valor).replace(",", "."))
        except ValueError:
            return d
        return v if 30 <= v <= 5000 else d
    if isinstance(d, bool):
        return bool(valor)
    return str(valor if valor is not None else "").strip()


def ajustes() -> dict:
    out = dict(DEFECTOS)
    try:
        data = json.loads(archivo_ajustes().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        for k in DEFECTOS:
            if k in data:
                out[k] = _validar(k, data[k])
    if not out["carpeta"]:
        out["carpeta"] = str(CARPETA_DEFECTO)
    return out


def guardar_ajustes(cambios: dict) -> dict:
    datos = ajustes()
    for k, v in cambios.items():
        if k in DEFECTOS:
            datos[k] = _validar(k, v)
    ruta = archivo_ajustes()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".googleearth-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)
    return datos


def es_portal(ruta) -> bool:
    """¿Ruta del «portal» de Flatpak (/run/user/…/doc/…)? El otro programa
    no la ve, y al otro día puede no existir."""
    p = Path(str(ruta)).parts
    return (len(p) > 4 and p[:3] == ("/", "run", "user") and p[4] == "doc") \
        or (len(p) > 3 and p[:4] == ("/", "run", "flatpak", "doc"))


def problema_carpeta(ruta) -> str:
    """"" si en ``ruta`` se puede guardar (la crea si hace falta); si no, el
    motivo. Tiene que ser una carpeta a la que lleguen IngeCAD y QGIS."""
    texto = str(ruta or "").strip()
    if not texto:
        return "Falta la carpeta de destino."
    p = Path(os.path.expanduser(texto))
    if not p.is_absolute():
        return f"La carpeta tiene que ser una ruta completa: {texto}"
    if es_portal(p):
        return ("Esa carpeta llegó por el «portal» de Flatpak (/run/user/…/doc) y el otro "
                "programa no la ve. Escribí la ruta verdadera (p. ej. ~/Documentos/...).")
    try:
        p.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p, prefix=".geocad-prueba-")
        os.close(fd)
        os.remove(tmp)
    except OSError as exc:
        return f"No se puede guardar en {p}: {exc.strerror or exc}"
    return ""


def lugar(lon, lat) -> str:
    """«S27.09633_W54.88868»: el centro de la imagen (5 decimales, ~1 m)."""
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return ""
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return ""
    return f"{'S' if lat < 0 else 'N'}{abs(lat):.5f}_{'W' if lon < 0 else 'E'}{abs(lon):.5f}"


def nombre_archivo(fecha: str, formato: str, cuando: float | None = None,
                   lon=None, lat=None) -> str:
    """«GE_<AAAAMMDD-HHMMSS>_<S27.09633_W54.88868>_img-<fecha>.<ext>»: fecha y
    hora de la captura, el lugar en coordenadas (3.33.3, Fernando: «nombres con
    fecha y hora y lugar actuales; si no es lugar, coordenadas») y la fecha de
    la imagen. Sólo ASCII, sin espacios: sirve en cualquier computadora."""
    sello = time.strftime("%Y%m%d-%H%M%S", time.localtime(cuando or time.time()))
    f = re.sub(r"[^0-9A-Za-z]+", "-", fecha or "").strip("-")
    partes = ["GE", sello, lugar(lon, lat), f"img-{f}" if f else ""]
    return "_".join(p for p in partes if p) + f".{formato}"


# ================================================================== KML
def _kml(cuerpo: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f'{cuerpo}</Document></kml>\n').encode("utf-8")


#: lo que Google Earth le manda a /vista cada vez que la cámara se detiene
VIEW_FORMAT = ("BBOX=[bboxWest],[bboxSouth],[bboxEast],[bboxNorth]"
               "&amp;cam=[lookatLon],[lookatLat],[lookatRange],[lookatTilt],[lookatHeading]"
               "&amp;px=[horizPixels],[vertPixels]")
# (3.33.3: se probó pedir la fecha de la línea de tiempo con [timeBegin],
# [timeEnd]: Google Earth Pro no la manda, devuelve el texto tal cual)


def kml_enlaces(puerto: int = PUERTO) -> bytes:
    """El archivo que se abre en Google Earth: queda en Lugares temporales
    (no toca Mis lugares). /vista sabe la vista y trae las marcas; /camara
    (cada 1 s, flyToView) mueve la cámara cuando GeoCAD lo pide. OJO: la
    vista se lee de /vista; la de /camara llega en 0,0 (viewRefreshMode
    never) y con ella GeoCAD voló una vez a 0°, 0°."""
    url = f"http://127.0.0.1:{int(puerto)}"
    return _kml(
        f"<name>{NOMBRE_ENLACE}</name><open>1</open>"
        "<NetworkLink><name>Vista (GeoCAD)</name>"
        f"<Link><href>{url}/vista</href><viewRefreshMode>onStop</viewRefreshMode>"
        f"<viewRefreshTime>0.5</viewRefreshTime><viewFormat>{VIEW_FORMAT}</viewFormat></Link>"
        "</NetworkLink>"
        "<NetworkLink><name>Cámara (GeoCAD)</name><flyToView>1</flyToView>"
        f"<Link><href>{url}/camara</href><refreshMode>onInterval</refreshMode>"
        "<refreshInterval>1</refreshInterval><viewRefreshMode>never</viewRefreshMode></Link>"
        "</NetworkLink>"
        # 3.33.4: las cruces, en su propio enlace SIN flyToView: con flyToView
        # Google Earth vuela cada vez a encuadrarlas (inclinado) aunque no
        # haya LookAt (probado con Fernando, 21/10/2026)
        "<NetworkLink><name>Cruces (GeoCAD)</name><flyToView>0</flyToView>"
        f"<Link><href>{url}/cruces</href><refreshMode>onInterval</refreshMode>"
        "<refreshInterval>1</refreshInterval><viewRefreshMode>never</viewRefreshMode></Link>"
        "</NetworkLink>")


def kml_vacio() -> bytes:
    return _kml("")


def kml_marcas(marcas, url_icono: str) -> bytes:
    est = (f'<Style id="m"><IconStyle><scale>1</scale><Icon><href>{url_icono}</href></Icon>'
           '<hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/></IconStyle>'
           '<LabelStyle><scale>0</scale></LabelStyle></Style>')
    return _kml(est + "".join(
        f'<Placemark><styleUrl>#m</styleUrl><Point><coordinates>{lon:.9f},{lat:.9f},0'
        '</coordinates></Point></Placemark>' for _k, lon, lat in marcas))


def kml_camara(vuelo, marcas, url_icono: str) -> bytes:
    """El vuelo (/camara) o las cruces (/cruces), 3.33.4. Google Earth NO
    vuelve a pedir /vista después de un vuelo pedido por el enlace (registro
    del 21/10/2026: 1069 vuelos, ninguna vista nueva), así que las cruces de
    cada pieza se ponen por /cruces (cada segundo) junto con el vuelo. NUNCA
    las dos cosas en el mismo enlace: con flyToView, Google Earth vuela a
    encuadrar las cruces."""
    cuerpo = ""
    if vuelo is not None:
        lon, lat, rango = vuelo
        if not posicion_valida(lon, lat, rango):
            raise GoogleEarthError(f"Posición inválida ({lon}, {lat}, {rango} m): no se vuela.")
        cuerpo += (f"<LookAt><longitude>{lon:.9f}</longitude><latitude>{lat:.9f}</latitude>"
                   "<altitude>0</altitude><heading>0</heading><tilt>0</tilt>"
                   f"<range>{rango:.2f}</range><altitudeMode>relativeToGround</altitudeMode></LookAt>")
    if marcas:
        cuerpo += (f'<Style id="m"><IconStyle><scale>1</scale><Icon><href>{url_icono}</href></Icon>'
                   '<hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/></IconStyle>'
                   '<LabelStyle><scale>0</scale></LabelStyle></Style>')
        cuerpo += "".join(f'<Placemark><styleUrl>#m</styleUrl><Point><coordinates>{lon:.9f},{lat:.9f},0'
                          '</coordinates></Point></Placemark>' for _k, lon, lat in marcas)
    return _kml(cuerpo)


def kml_lookat(lon: float, lat: float, rango: float) -> bytes:
    """El vuelo: siempre norte arriba y vista vertical."""
    if not posicion_valida(lon, lat, rango):
        raise GoogleEarthError(f"Posición inválida ({lon}, {lat}, {rango} m): no se vuela.")
    return _kml(f"<LookAt><longitude>{lon:.9f}</longitude><latitude>{lat:.9f}</latitude>"
                "<altitude>0</altitude><heading>0</heading><tilt>0</tilt>"
                f"<range>{rango:.2f}</range><altitudeMode>relativeToGround</altitudeMode></LookAt>")


# ================================================================== la vista
def posicion_valida(lon, lat, rango) -> bool:
    """Nunca se vuela a 0°, 0° ni a una posición fuera del mundo (lección del
    20/10/2026: la vista vacía llega como 0,0)."""
    try:
        lon, lat, rango = float(lon), float(lat), float(rango)
    except (TypeError, ValueError):
        return False
    if not all(map(math.isfinite, (lon, lat, rango))):
        return False
    return (abs(lon) > 1e-3 or abs(lat) > 1e-3) and -180 <= lon <= 180 \
        and -85 <= lat <= 85 and 10 <= rango <= 200000


@dataclass
class Vista:
    oeste: float
    sur: float
    este: float
    norte: float
    lon: float
    lat: float
    rango: float
    inclinacion: float = 0.0
    rumbo: float = 0.0
    ancho_px: int = 0
    alto_px: int = 0
    fecha: str = ""          # la de la línea de tiempo de Google Earth, si la mandó

    @property
    def vertical(self) -> bool:
        """¿Mirando hacia abajo y con el norte arriba? (si no, se endereza)"""
        r = self.rumbo % 360
        return abs(self.inclinacion) < 0.5 and min(r, 360 - r) < 0.5


def fecha_de_ge(texto) -> str:
    """«[timeBegin],[timeEnd]» como lo manda Google Earth -> «d/m/aaaa»,
    «m/aaaa» o «aaaa» (la del final; si no hay, la del principio), o "" si
    no mandó fecha (llega el texto con corchetes, o vacío)."""
    for parte in reversed(str(texto or "").split(",")):
        m = re.match(r"\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", parte)
        if m and "[" not in parte:
            a, mes, dia = m.groups()
            return "/".join(str(int(x)) for x in (dia, mes) if x) + ("/" if mes else "") + a
    return ""


def leer_vista(q: dict):
    """La vista que manda Google Earth a /vista, o None si falta algo o es
    inválida (BBOX vacío, 0,0...)."""
    try:
        o, s, e, n = (float(v) for v in str(q["BBOX"]).split(","))
        cam = [float(v) for v in str(q["cam"]).split(",")]
        lon, lat, rango = cam[0], cam[1], cam[2]
        incl = cam[3] if len(cam) > 3 else 0.0
        rumbo = cam[4] if len(cam) > 4 else 0.0
        px = [int(float(v)) for v in str(q.get("px", "0,0")).split(",")]
    except (KeyError, ValueError, IndexError):
        return None
    if not (e > o and n > s) or not posicion_valida(lon, lat, rango):
        return None
    return Vista(o, s, e, n, lon, lat, rango, incl, rumbo, *(px + [0, 0])[:2],
                 fecha=fecha_de_ge(q.get("t")))


def vista_vertical(vista: Vista) -> Vista:
    """La vista mirando hacia abajo con el norte arriba sobre el mismo punto
    y a la misma altura: ella misma si ya lo está; si no, su BBOX estimado
    (Google Earth no manda la vista nueva después de enderezarla)."""
    if vista.vertical:
        return vista
    m_lon = 111320.0 * math.cos(math.radians(vista.lat))
    dx = ANCHO_POR_METRO * vista.rango / 2 / m_lon
    dy = ALTO_POR_METRO * vista.rango / 2 / 110574.0
    if vista.ancho_px and vista.alto_px:                 # la forma de la ventana de verdad
        dy = dx * m_lon / 110574.0 * vista.alto_px / vista.ancho_px
    return Vista(vista.lon - dx, vista.lat - dy, vista.lon + dx, vista.lat + dy, vista.lon,
                 vista.lat, vista.rango, 0.0, 0.0, vista.ancho_px, vista.alto_px)


def bbox_en(vista: Vista, lon: float, lat: float, rango: float) -> tuple:
    """El BBOX que tendrá la cámara vertical en (lon, lat, rango), a escala del
    de ``vista`` (vertical): lo que se ve crece con la altura."""
    k = rango / vista.rango
    dx = (vista.este - vista.oeste) / 2 * k
    dy = (vista.norte - vista.sur) / 2 * k
    return lon - dx, lat - dy, lon + dx, lat + dy


def marcas_de_bbox(o: float, s: float, e: float, n: float, adentro: float = ADENTRO):
    dx, dy = (e - o) * adentro, (n - s) * adentro
    return [("SO", o + dx, s + dy), ("SE", e - dx, s + dy),
            ("NE", e - dx, n - dy), ("NO", o + dx, n - dy)]


def distancia_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distancia aproximada en metros (alcanza para comparar vistas)."""
    dy = (lat2 - lat1) * 111_320.0
    dx = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def tolerancia_m(rango: float) -> float:
    """Cuánto puede quedar corrida la cámara: 1 % de la altura, al menos 1 m.
    La foto se ubica por las cruces de la vista que llegó, no por la pedida:
    el corrimiento sólo achica un poco el solape del mosaico (20 %)."""
    return max(1.0, abs(rango) * 0.01)


def llego(vista, lon: float, lat: float, rango: float) -> bool:
    """¿La cámara ya está donde se pidió, mirando hacia abajo y con el norte
    arriba? (3.33.3: antes pedía 0,2 m y Google Earth no siempre devuelve la
    vista con esa precisión: «no fue a la posición pedida» estando enlazado.)"""
    return vista is not None and vista.vertical \
        and distancia_m(vista.lon, vista.lat, lon, lat) <= tolerancia_m(rango) \
        and abs(vista.rango - rango) <= max(1.0, rango * 0.02)


# ================================================================== la cruz
MAGENTA = (255, 0, 255)


def imagen_marca(lado: int = 33, brazo: int = 3, borde: int = 2):
    """La cruz magenta con borde blanco (RGBA), como la de la prueba."""
    import numpy as np

    a = np.zeros((lado, lado, 4), np.uint8)
    c0 = (lado - brazo) // 2
    b0, b1 = c0 - borde, c0 + brazo + borde
    a[b0:b1, :] = (255, 255, 255, 255)
    a[:, b0:b1] = (255, 255, 255, 255)
    a[c0:c0 + brazo, :] = (*MAGENTA, 255)
    a[:, c0:c0 + brazo] = (*MAGENTA, 255)
    return a


def mascara(a):
    """Los píxeles magenta (las cruces) de una imagen RGB uint8."""
    return (a[..., 0] > 200) & (a[..., 2] > 200) & (a[..., 1] < 60)


def _pico(v, ancho: int = 3) -> float:
    """Posición (de esquina) del máximo de ``v``, con su vecindad pesada."""
    import numpy as np

    i = int(v.argmax())
    lo, hi = max(i - ancho, 0), min(i + ancho + 1, len(v))
    w = v[lo:hi].astype(float)
    return float((np.arange(lo, hi) * w).sum() / w.sum()) + 0.5


def _cruce(m, radio: int):
    """El centro de la cruz en la máscara ``m`` (un cuadrante): columna del
    brazo vertical y fila del horizontal. Primero en todo el cuadrante,
    después en una ventana alrededor (lo magenta de otra parte no corre el
    centro). También el largo de los brazos (para el margen del recorte)."""
    x = _pico(m.sum(0)) - 0.5
    y = _pico(m.sum(1)) - 0.5
    x0, y0 = max(int(x) - radio, 0), max(int(y) - radio, 0)
    w = m[y0:int(y) + radio + 1, x0:int(x) + radio + 1]
    if w.sum() == 0:
        w, x0, y0 = m, 0, 0
    cx, cy = x0 + _pico(w.sum(0)), y0 + _pico(w.sum(1))
    largo = int(max(w.sum(1).max(), w.sum(0).max()))
    return cx, cy, largo


def detectar(a, minimo: int = 25, radio: int = 60) -> dict:
    """{"NO": (x, y), "NE":…, "SE":…, "SO":…, "largo": px} con el centro de
    cada cruz. Una cruz por cuadrante; si falta alguna, GoogleEarthError
    diciendo cuál (lo habitual: la chincheta del buscador, la brújula o el
    logo la tapan entera)."""
    m = mascara(a)
    h, w = m.shape
    zonas = {"NO": (0, 0), "NE": (w // 2, 0), "SO": (0, h // 2), "SE": (w // 2, h // 2)}
    nombres = {"NO": "arriba a la izquierda", "NE": "arriba a la derecha",
               "SO": "abajo a la izquierda", "SE": "abajo a la derecha"}
    out, largos, faltan = {}, [], []
    for k, (x0, y0) in zonas.items():
        sub = m[y0:y0 + (h - h // 2 if y0 else h // 2), x0:x0 + (w - w // 2 if x0 else w // 2)]
        if int(sub.sum()) < minimo:
            faltan.append(nombres[k])
            continue
        cx, cy, largo = _cruce(sub, radio)
        out[k] = (x0 + cx, y0 + cy)
        largos.append(largo)
    if faltan:
        raise GoogleEarthError(
            "No se ve la cruz de control " + " ni ".join(faltan) + ". Fijate que no la tapen la "
            "chincheta del buscador (borrala en Lugares temporales o con la X del buscador), "
            "la brújula o el logo (Ver > Brújula), ni otra ventana.")
    no, ne, se, so = out["NO"], out["NE"], out["SE"], out["SO"]
    tol = 0.1 * max(w, h)
    if not (no[0] < ne[0] and so[0] < se[0] and no[1] < so[1] and ne[1] < se[1]) \
            or abs(no[1] - ne[1]) > tol or abs(so[1] - se[1]) > tol \
            or abs(no[0] - so[0]) > tol or abs(ne[0] - se[0]) > tol:
        raise GoogleEarthError("Las cruces de control no forman un rectángulo: la vista tiene "
                               "que estar quieta, vertical y con el norte arriba.")
    out["largo"] = max(largos)
    return out


def forma_coincide(det: dict, marcas, tolerancia: float = 0.12) -> bool:
    """¿Las cruces de la foto (``det``, de detectar) tienen la forma del
    rectángulo de ``marcas`` en el suelo (ancho / alto)? Si la cámara todavía
    no llegó, las cruces de la pieza nueva no forman ese rectángulo."""
    m = {k: (lon, lat) for k, lon, lat in marcas}
    try:
        ancho_px = ((det["NE"][0] - det["NO"][0]) + (det["SE"][0] - det["SO"][0])) / 2
        alto_px = ((det["SO"][1] - det["NO"][1]) + (det["SE"][1] - det["NE"][1])) / 2
        ancho_m = distancia_m(*m["NO"], *m["NE"])
        alto_m = distancia_m(*m["NO"], *m["SO"])
    except KeyError:
        return True
    if min(ancho_px, alto_px, ancho_m, alto_m) <= 0:
        return False
    return abs((ancho_px / alto_px) / (ancho_m / alto_m) - 1) <= tolerancia


# ================================================================== transformación
def homografia(origen, destino):
    """La proyectiva (3x3) que lleva los puntos ``origen`` a ``destino``
    (4 o más, por mínimos cuadrados, normalizados como Hartley)."""
    import numpy as np

    o = np.asarray(origen, float)
    d = np.asarray(destino, float)

    def norm(p):
        c = p.mean(0)
        s = math.sqrt(2) / max(np.sqrt(((p - c) ** 2).sum(1)).mean(), 1e-12)
        return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])

    to, td = norm(o), norm(d)
    on = (to @ np.c_[o, np.ones(len(o))].T).T
    dn = (td @ np.c_[d, np.ones(len(d))].T).T
    filas = []
    for (x, y, _), (X, Y, _) in zip(on, dn):
        filas.append([x, y, 1, 0, 0, 0, -X * x, -X * y, -X])
        filas.append([0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y])
    h = np.linalg.svd(np.array(filas))[2][-1].reshape(3, 3)
    H = np.linalg.inv(td) @ h @ to
    return H / H[2, 2]


def aplicar(H, x, y):
    """(X, Y) = H (x, y); ``x`` e ``y`` pueden ser arreglos."""
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return (H[0, 0] * x + H[0, 1] * y + H[0, 2]) / w, (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / w


def residuo_afin(origen, destino) -> float:
    """El mayor residuo (m) de una afín ajustada a las marcas: con cuatro la
    proyectiva es exacta, la afín dice cuánto se aparta la foto de una
    vista plana (en la prueba, 6-11 mm)."""
    import numpy as np

    o = np.c_[np.asarray(origen, float), np.ones(len(origen))]
    d = np.asarray(destino, float)
    cx = np.linalg.lstsq(o, d[:, 0], rcond=None)[0]
    cy = np.linalg.lstsq(o, d[:, 1], rcond=None)[0]
    return float(np.hypot(o @ cx - d[:, 0], o @ cy - d[:, 1]).max())


ESQUINAS = ("NO", "NE", "SE", "SO")


@dataclass(eq=False)                 # se comparan por identidad (llevan la foto)
class Pieza:
    """Una foto con sus marcas: ``pix`` (detectar) y ``xy`` (las marcas en el
    sistema elegido). ``fila`` y ``col`` ubican la pieza en el mosaico."""
    imagen: object
    pix: dict
    xy: dict
    fila: int = 0
    col: int = 0
    margen: float = 0.0
    H: object = field(init=False)
    Hinv: object = field(init=False)
    recorte: tuple = field(init=False)

    def __post_init__(self) -> None:
        import numpy as np

        self.H = homografia([self.pix[k] for k in ESQUINAS], [self.xy[k] for k in ESQUINAS])
        self.Hinv = np.linalg.inv(self.H)
        m = self.margen or (0.6 * float(self.pix.get("largo", 33)) + 8)
        p = self.pix
        self.recorte = (max(p["NO"][0], p["SO"][0]) + m, max(p["NO"][1], p["NE"][1]) + m,
                        min(p["NE"][0], p["SE"][0]) - m, min(p["SO"][1], p["SE"][1]) - m)
        x0, y0, x1, y1 = self.recorte
        if x1 - x0 < 10 or y1 - y0 < 10:
            raise GoogleEarthError("Las cruces de control están demasiado juntas.")

    @property
    def residuo(self) -> float:
        return residuo_afin([self.pix[k] for k in ESQUINAS], [self.xy[k] for k in ESQUINAS])

    def tamano_pixel(self) -> float:
        """Lo que mide un píxel de la foto en el centro (m)."""
        x0, y0, x1, y1 = self.recorte
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        a, b, c = aplicar(self.H, cx, cy), aplicar(self.H, cx + 1, cy), aplicar(self.H, cx, cy + 1)
        return (math.hypot(b[0] - a[0], b[1] - a[1]) + math.hypot(c[0] - a[0], c[1] - a[1])) / 2

    def interior(self) -> tuple:
        """(xmin, ymin, xmax, ymax): el rectángulo con el norte de la faja
        arriba que entra en el recorte (la foto queda girada la convergencia)."""
        x0, y0, x1, y1 = self.recorte
        no, ne = aplicar(self.H, x0, y0), aplicar(self.H, x1, y0)
        se, so = aplicar(self.H, x1, y1), aplicar(self.H, x0, y1)
        return (max(no[0], so[0]), max(so[1], se[1]), min(ne[0], se[0]), min(no[1], ne[1]))


def pieza_de_foto(imagen, marcas_geo, a_planas, fila: int = 0, col: int = 0) -> Pieza:
    """La pieza de una foto: detecta las cruces y lleva sus coordenadas
    (lon, lat de ``marcas_geo``) a planas con ``a_planas(lon, lat)``."""
    pix = detectar(imagen)
    geo = {k: (lon, lat) for k, lon, lat in marcas_geo}
    xy = {k: tuple(a_planas(*geo[k])) for k in ESQUINAS}
    return Pieza(imagen, pix, xy, fila, col)


# ================================================================== el marco y la unión
@dataclass
class Marco:
    xmin: float
    ymax: float
    res: float
    ancho: int
    alto: int

    @property
    def xmax(self) -> float:
        return self.xmin + self.ancho * self.res

    @property
    def ymin(self) -> float:
        return self.ymax - self.alto * self.res


def resolucion(piezas) -> float:
    """El píxel de la salida: el de las fotos, redondeado al centímetro."""
    t = sum(p.tamano_pixel() for p in piezas) / len(piezas)
    return max(0.01, round(t, 2))


def _rejilla(xmin, ymin, xmax, ymax, res) -> Marco:
    x0 = math.ceil(xmin / res - 1e-9) * res
    y1 = math.floor(ymax / res + 1e-9) * res
    ancho = int(math.floor((xmax - x0) / res + 1e-9))
    alto = int(math.floor((y1 - ymin) / res + 1e-9))
    if ancho < 2 or alto < 2:
        raise GoogleEarthError("La zona capturada quedó vacía.")
    return Marco(x0, y1, res, ancho, alto)


def _elegir(piezas, X, Y):
    """Para cada punto (X, Y), la pieza que lo ve más cerca de su centro
    (las costuras quedan a mitad de camino) y sus coordenadas de píxel; -1
    donde ninguna lo ve."""
    import numpy as np

    mejor = np.full(X.shape, np.inf)
    cual = np.full(X.shape, -1, int)
    for k, p in enumerate(piezas):
        u, v = aplicar(p.Hinv, X, Y)
        x0, y0, x1, y1 = p.recorte
        dentro = (u >= x0) & (u <= x1) & (v >= y0) & (v <= y1)
        d = ((u - (x0 + x1) / 2) / (x1 - x0)) ** 2 + ((v - (y0 + y1) / 2) / (y1 - y0)) ** 2
        mas = dentro & (d < mejor)
        mejor[mas] = d[mas]
        cual[mas] = k
    return cual


def marco(piezas, res: float | None = None) -> Marco:
    """El rectángulo de la salida. Una pieza: su interior. Varias: el
    rectángulo más grande cubierto por todas, recortando los bordes con
    huecos (las piezas no caen exactamente donde se pidió)."""
    import numpy as np

    res = res or resolucion(piezas)
    rects = [p.interior() for p in piezas]
    xmin, ymin = min(r[0] for r in rects), min(r[1] for r in rects)
    xmax, ymax = max(r[2] for r in rects), max(r[3] for r in rects)
    if len(piezas) == 1:
        return _rejilla(*rects[0], res)
    paso = max(res * 4, (xmax - xmin) / 600)
    xs = np.arange(xmin + paso / 2, xmax, paso)
    ys = np.arange(ymax - paso / 2, ymin, -paso)
    X, Y = np.meshgrid(xs, ys)
    cub = _elegir(piezas, X, Y) >= 0
    f0, f1, c0, c1 = 0, cub.shape[0], 0, cub.shape[1]
    while f1 - f0 > 1 and c1 - c0 > 1:
        z = cub[f0:f1, c0:c1]
        bordes = {"arriba": 1 - z[0].mean(), "abajo": 1 - z[-1].mean(),
                  "izq": 1 - z[:, 0].mean(), "der": 1 - z[:, -1].mean()}
        peor = max(bordes, key=bordes.get)
        if bordes[peor] == 0:
            break
        if peor == "arriba":
            f0 += 1
        elif peor == "abajo":
            f1 -= 1
        elif peor == "izq":
            c0 += 1
        else:
            c1 -= 1
    return _rejilla(xmin + c0 * paso, ymax - f1 * paso, xmin + c1 * paso, ymax - f0 * paso, res)


def marco_todo(piezas, res: float | None = None) -> Marco:
    """El rectángulo que abarca todas las piezas (mosaico incompleto: no se
    recorta por los huecos)."""
    res = res or resolucion(piezas)
    rects = [p.interior() for p in piezas]
    return _rejilla(min(r[0] for r in rects), min(r[1] for r in rects),
                    max(r[2] for r in rects), max(r[3] for r in rects), res)


def _muestrear(img, x, y):
    """Bilineal en ``img`` (alto x ancho x canales) en coordenadas de
    esquina; lo de afuera toma el borde."""
    import numpy as np

    h, w = img.shape[:2]
    x = np.clip(x - 0.5, 0, w - 1)
    y = np.clip(y - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(np.intp)
    y0 = np.floor(y).astype(np.intp)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[..., None].astype(np.float32), (y - y0)[..., None].astype(np.float32)
    arriba = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    abajo = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return arriba * (1 - fy) + abajo * fy


def componer(piezas, m: Marco, progreso=None, filas: int = 128, cancelado=None,
             huecos: bool = False):
    """La imagen de salida (alto x ancho x 3, uint8) en el marco ``m``, por
    franjas (no se llena la memoria). ``progreso(fraccion)``; si
    ``cancelado()`` da True se corta con GoogleEarthError."""
    import numpy as np

    out = np.empty((m.alto, m.ancho, 3), np.uint8)
    xs = m.xmin + (np.arange(m.ancho) + 0.5) * m.res
    for f0 in range(0, m.alto, filas):
        if cancelado is not None and cancelado():
            raise GoogleEarthError("Cancelado.")
        f1 = min(f0 + filas, m.alto)
        ys = m.ymax - (np.arange(f0, f1) + 0.5) * m.res
        X, Y = np.meshgrid(xs, ys)
        cual = _elegir(piezas, X, Y)
        if not huecos:
            cual[cual < 0] = 0 if len(piezas) == 1 else _mas_cerca(piezas, X, Y)[cual < 0]
        franja = np.full((f1 - f0, m.ancho, 3), 255.0, np.float32)    # hueco: blanco
        for k, p in enumerate(piezas):
            sel = cual == k
            if sel.any():
                u, v = aplicar(p.Hinv, X[sel], Y[sel])
                franja[sel] = _muestrear(p.imagen, u, v)
        out[f0:f1] = np.clip(franja + 0.5, 0, 255).astype(np.uint8)
        if progreso is not None:
            progreso(f1 / m.alto)
    return out


def _mas_cerca(piezas, X, Y):
    """La pieza de centro más cercano (para los bordes que ninguna ve del todo)."""
    import numpy as np

    d = []
    for p in piezas:
        x0, y0, x1, y1 = p.interior()
        d.append((X - (x0 + x1) / 2) ** 2 + (Y - (y0 + y1) / 2) ** 2)
    return np.argmin(np.stack(d), axis=0)


# ================================================================== costuras
def _fase(a, b):
    """Corrimiento (filas, columnas) de ``b`` respecto de ``a`` por
    correlación de fase, con subpíxel por parábola."""
    import numpy as np

    # la ventana de Hann apaga los bordes: si no, los dos recortes (del mismo
    # marco) se parecen en el borde y el pico queda siempre en 0
    v = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    a = (a - a.mean()) * v
    b = (b - b.mean()) * v
    F = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-9)).real
    i, j = np.unravel_index(int(r.argmax()), r.shape)

    def sub(v, k):
        n = len(v)
        a_, b_, c_ = v[(k - 1) % n], v[k % n], v[(k + 1) % n]
        den = a_ - 2 * b_ + c_
        d = 0.5 * (a_ - c_) / den if den else 0.0
        k = k + d
        return k - n if k > n / 2 else k

    return sub(r[:, j], i), sub(r[i, :], j)


def costuras(piezas, res: float, lado: int = 512) -> list:
    """[(pieza a, pieza b, corrimiento en m)] entre piezas vecinas, en la
    zona que ven las dos (hasta ``lado`` píxeles por lado, en el medio)."""
    import numpy as np

    out = []
    por_lugar = {(p.fila, p.col): p for p in piezas}
    for p in piezas:
        for q in (por_lugar.get((p.fila, p.col + 1)), por_lugar.get((p.fila + 1, p.col))):
            if q is None:
                continue
            a, b = p.interior(), q.interior()
            xmin, ymin, xmax, ymax = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
            if xmax - xmin < 16 * res or ymax - ymin < 16 * res:
                continue
            cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
            mx = min(lado, int((xmax - xmin) / res)) * res / 2
            my = min(lado, int((ymax - ymin) / res)) * res / 2
            xs = np.arange(cx - mx, cx + mx, res) + res / 2
            ys = np.arange(cy + my, cy - my, -res) - res / 2
            X, Y = np.meshgrid(xs, ys)
            gris = []
            for z in (p, q):
                u, v = aplicar(z.Hinv, X, Y)
                gris.append(_muestrear(z.imagen, u, v).mean(-1))
            dy, dx = _fase(*gris)
            out.append((p, q, float(math.hypot(dx, dy) * res)))
    return out


# ================================================================== el mosaico
@dataclass
class Plan:
    centros: list            # [(fila, col, lon, lat)]
    rango: float
    columnas: int
    filas: int
    pedida: float = 0.0      # la altura de Configurar captura (si se subió para no pasar el tope)

    @property
    def segundos(self) -> float:
        return len(self.centros) * SEGUNDOS_POR_PIEZA + 5


#: lo que ve Google Earth entre las cruces, por metro de altura de la cámara,
#: si todavía no mandó su vista (medido en la prueba: 1,016 x 0,733)
ANCHO_POR_METRO, ALTO_POR_METRO = 1.016, 0.733
#: lo que queda de la vista entre las cruces después del recorte (margen del
#: largo de la cruz): 0,9 quedaba corto unos metros en los bordes del mosaico
UTIL = 0.85


def _entre_marcas(vista: Vista, a_planas):
    """(cx, cy, ancho, alto) del rectángulo de las cruces de ``vista``, en planas."""
    pts = {k: a_planas(lon, lat) for k, lon, lat in marcas_de_bbox(
        vista.oeste, vista.sur, vista.este, vista.norte)}
    ancho = ((pts["NE"][0] - pts["NO"][0]) + (pts["SE"][0] - pts["SO"][0])) / 2
    alto = ((pts["NO"][1] - pts["SO"][1]) + (pts["NE"][1] - pts["SE"][1])) / 2
    if ancho <= 0 or alto <= 0:
        raise GoogleEarthError("La vista de Google Earth no es válida.")
    return (sum(p[0] for p in pts.values()) / 4, sum(p[1] for p in pts.values()) / 4, ancho, alto)


def _zona_valida(zona) -> tuple:
    try:
        xmin, ymin, xmax, ymax = (float(v) for v in zona)
    except (TypeError, ValueError):
        raise GoogleEarthError("La zona de la pantalla no es válida.") from None
    if not all(map(math.isfinite, (xmin, ymin, xmax, ymax))) or xmax <= xmin or ymax <= ymin:
        raise GoogleEarthError("La zona de la pantalla no es válida.")
    return xmin, ymin, xmax, ymax


class DemasiadasPiezas(GoogleEarthError):
    pass


def plan_mosaico(vista: Vista, a_planas, a_geo, rango: float = ALTURA_PIEZA,
                 solape: float = SOLAPE, tope: int = TOPE_PIEZAS, zona=None,
                 ajustar: bool = True) -> Plan:
    """Como _plan_fijo, pero si con ``rango`` harían falta más de ``tope``
    piezas, sube la altura de las piezas (de a 10 %, redondeada a 10 m) hasta
    que entren (3.33.3: Fernando, «Mosaico falló todas las veces» con la
    cámara a 2300 m y piezas a 200 m: hacían falta ~180 piezas)."""
    r = float(rango)
    while True:
        try:
            p = _plan_fijo(vista, a_planas, a_geo, r, solape, tope, zona)
            p.pedida = float(rango)
            return p
        except DemasiadasPiezas:
            if not ajustar or r >= 5000:
                raise
            r = min(5000.0, math.ceil(r * 1.1 / 10) * 10)


def _plan_fijo(vista: Vista, a_planas, a_geo, rango: float = ALTURA_PIEZA,
               solape: float = SOLAPE, tope: int = TOPE_PIEZAS, zona=None) -> Plan:
    """Las piezas que cubren lo que se ve ahora (el rectángulo de las marcas),
    con la cámara a ``rango`` metros. Cada pieza ve lo mismo que la vista
    actual achicado ``rango / vista.rango`` (la vista es vertical). Con
    ``zona`` (xmin, ymin, xmax, ymax en el sistema de ``a_planas``) cubre
    ese rectángulo: lo que se ve en IngeCAD o QGIS (3.33.1)."""
    if not posicion_valida(vista.lon, vista.lat, vista.rango):
        raise GoogleEarthError("La vista de Google Earth no es válida.")
    if not 30 <= rango <= 5000:
        raise GoogleEarthError("La altura de las piezas tiene que estar entre 30 y 5000 m.")
    cx, cy, ancho_v, alto_v = _entre_marcas(vista, a_planas)
    ancho, alto = ancho_v, alto_v
    if zona is not None:
        xmin, ymin, xmax, ymax = _zona_valida(zona)
        cx, cy, ancho, alto = (xmin + xmax) / 2, (ymin + ymax) / 2, xmax - xmin, ymax - ymin
    elif rango >= vista.rango:                      # más alto que ahora: no hay más detalle
        lon, lat = a_geo(cx, cy)
        return Plan([(0, 0, lon, lat)], float(vista.rango), 1, 1)
    f = rango / vista.rango * UTIL                  # el recorte por dentro de las cruces
    w, h = ancho_v * f, alto_v * f
    if zona is not None:                            # un margen: después se recorta exacto
        ancho, alto = ancho + 0.1 * w, alto + 0.1 * h

    def reparto(total, pieza):
        if total <= pieza:
            return [0.0]
        n = math.ceil((total - pieza) / (pieza * (1 - solape))) + 1
        paso = (total - pieza) / (n - 1)
        return [-(total - pieza) / 2 + i * paso for i in range(n)]

    dxs, dys = reparto(ancho, w), reparto(alto, h)
    n = len(dxs) * len(dys)
    if n > tope:
        que = ("Achicá la zona en pantalla" if zona is not None else
               "Acercá la vista de Google Earth")
        raise DemasiadasPiezas(
            f"Harían falta {len(dxs)} x {len(dys)} = {n} piezas (el tope es {tope}). {que} "
            "o subí la altura de las piezas en Configurar captura.")
    centros = []
    for fila, dy in enumerate(reversed(dys)):      # la fila 0 es la de arriba (norte)
        for col, dx in enumerate(dxs):
            lon, lat = a_geo(cx + dx, cy + dy)
            if not posicion_valida(lon, lat, rango):
                raise GoogleEarthError("Una pieza del mosaico cae en una posición inválida.")
            centros.append((fila, col, lon, lat))
    return Plan(centros, float(rango), len(dxs), len(dys))


def camara_para_zona(zona, a_geo, vista: Vista | None = None, a_planas=None) -> tuple:
    """(lon, lat, rango): la cámara de Google Earth que muestra ``zona``
    entre sus cruces, norte arriba (3.33.1: la pantalla de IngeCAD o QGIS
    posiciona Google Earth). Cuánto ve por metro de altura se mide de la
    vista de ahora (depende de la ventana de Google Earth)."""
    xmin, ymin, xmax, ymax = _zona_valida(zona)
    fw, fh = ANCHO_POR_METRO, ALTO_POR_METRO
    if vista is not None and a_planas is not None:
        _cx, _cy, ancho_v, alto_v = _entre_marcas(vista, a_planas)
        mw, mh = ancho_v / vista.rango, alto_v / vista.rango
        if 0.25 < mw / fw < 4 and 0.25 < mh / fh < 4:      # una vista disparatada no manda
            fw, fh = mw, mh
    rango = max((xmax - xmin) / (fw * UTIL), (ymax - ymin) / (fh * UTIL))   # el recorte
    rango = min(max(rango, 30.0), 100000.0)
    lon, lat = a_geo((xmin + xmax) / 2, (ymin + ymax) / 2)
    if not posicion_valida(lon, lat, rango):
        raise GoogleEarthError("La zona de la pantalla cae en una posición inválida (¿el "
                               "sistema del dibujo es el correcto?).")
    return lon, lat, rango


def zona_en(zona, crs_origen: str, crs_destino: str) -> tuple:
    """La zona (rectángulo en ``crs_origen``) como rectángulo en
    ``crs_destino``: el que entra en ella (bordes y medios llevados por
    geográficas). Mismo sistema: tal cual."""
    zona = _zona_valida(zona)
    if crs_origen.strip().upper() == crs_destino.strip().upper():
        return zona
    _a, a_geo = transformadores(crs_origen)
    a_planas, _b = transformadores(crs_destino)
    xmin, ymin, xmax, ymax = zona
    xm, ym = (xmin + xmax) / 2, (ymin + ymax) / 2

    def ir(x, y):
        return a_planas(*a_geo(x, y))

    izq = [ir(xmin, y)[0] for y in (ymin, ym, ymax)]
    der = [ir(xmax, y)[0] for y in (ymin, ym, ymax)]
    aba = [ir(x, ymin)[1] for x in (xmin, xm, xmax)]
    arr = [ir(x, ymax)[1] for x in (xmin, xm, xmax)]
    return _zona_valida((max(izq), max(aba), min(der), min(arr)))


def recortar_marco(m: Marco, zona) -> Marco:
    """El marco ``m`` recortado a la zona pedida (en la misma rejilla)."""
    xmin, ymin, xmax, ymax = _zona_valida(zona)
    return _rejilla(max(m.xmin, xmin), max(m.ymin, ymin), min(m.xmax, xmax), min(m.ymax, ymax), m.res)


# ================================================================== sistemas
def transformadores(crs: str):
    """(a_planas, a_geo) entre WGS 84 y ``crs`` con pyproj (x = lon)."""
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise GoogleEarthError("Falta pyproj (PROJ): no se puede llevar a planas.") from exc
    try:
        ida = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        vuelta = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    except Exception as exc:  # noqa: BLE001 -- CRS desconocido
        raise GoogleEarthError(f"No se reconoce el sistema {crs}.") from exc
    return (lambda lon, lat: ida.transform(lon, lat)), (lambda x, y: vuelta.transform(x, y))


def es_planas(crs: str) -> bool:
    try:
        from pyproj import CRS

        return bool(CRS.from_user_input(crs).is_projected)
    except Exception:  # noqa: BLE001
        return False


def wkt_esri(crs: str) -> str:
    try:
        from pyproj import CRS
        from pyproj.enums import WktVersion

        return CRS.from_user_input(crs).to_wkt(WktVersion.WKT1_ESRI)
    except Exception:  # noqa: BLE001
        return ""


def epsg_de(crs: str) -> int:
    m = re.fullmatch(r"\s*EPSG:(\d+)\s*", str(crs or ""), re.I)
    return int(m.group(1)) if m else 0


def sistema_sugerido(lon: float, lat: float) -> str:
    """POSGAR 2007 en su faja si cae en la Argentina; si no, el UTM."""
    from .crs import DATUMS

    if -73.5 <= lon < -52.5 and -56 <= lat <= -21:
        faja = min(7, max(1, round((lon + 72) / 3) + 1))
        return f"EPSG:{DATUMS[0][1] + faja - 1}"
    zona = min(60, max(1, int((lon + 180) // 6) + 1))
    return f"EPSG:{(32700 if lat < 0 else 32600) + zona}"


def aviso_faja(crs: str, lon: float) -> str:
    """Aviso si la captura cae lejos de la faja Gauss-Krüger del sistema."""
    from .crs import DATUMS

    epsg = epsg_de(crs)
    for nombre, base, _geo in DATUMS:
        if base <= epsg <= base + 6:
            faja = epsg - base + 1
            meridiano = -72 + 3 * (faja - 1)
            if abs(lon - meridiano) > 2.0:
                return (f"Atención: la vista está a {abs(lon - meridiano):.1f}° del meridiano de "
                        f"la faja {faja} de {nombre} (lo normal es hasta 1,5°).")
    return ""


# ================================================================== archivos
def texto_mundo(m: Marco) -> str:
    """El archivo de mundo: el centro del píxel de arriba a la izquierda."""
    return "\n".join(f"{v:.10f}" for v in (m.res, 0.0, 0.0, -m.res,
                                             m.xmin + m.res / 2, m.ymax - m.res / 2)) + "\n"


def png(a) -> bytes:
    """PNG (RGB o RGBA, uint8) con zlib, sin PIL."""
    import numpy as np

    a = np.ascontiguousarray(a, np.uint8)
    h, w = a.shape[:2]
    canales = a.shape[2] if a.ndim == 3 else 1
    tipo = {1: 0, 3: 2, 4: 6}[canales]
    crudo = np.empty((h, 1 + w * canales), np.uint8)
    crudo[:, 0] = 0
    crudo[:, 1:] = a.reshape(h, w * canales)

    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, tipo, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(crudo.tobytes(), 6)) + trozo(b"IEND", b""))


def geotiff(a, m: Marco, epsg: int, descripcion: str = "") -> bytes:
    """GeoTIFF RGB (deflate, por tiras) con ModelPixelScale, ModelTiepoint y
    GeoKeyDirectory (proyectado, PixelIsArea, EPSG): lo leen GDAL/QGIS e
    INSERTARGEO. Sin GDAL ni PIL (IngeCAD no trae GDAL; QGIS no trae PIL)."""
    import numpy as np

    a = np.ascontiguousarray(a, np.uint8)
    h, w, n = a.shape
    filas = max(1, 65536 // (w * n))
    tiras = [zlib.compress(a[i:i + filas].tobytes(), 6) for i in range(0, h, filas)]
    desc = (descripcion or "GeoCAD Yaguareté - Google Earth").encode("utf-8") + b"\0"
    soft = b"GeoCAD Yaguarete\0"
    claves = [1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, int(epsg)]
    # (etiqueta, tipo, valores): 3 SHORT, 4 LONG, 2 ASCII, 12 DOUBLE
    etiquetas = [
        (256, 4, [w]), (257, 4, [h]), (258, 3, [8] * n), (259, 3, [8]), (262, 3, [2]),
        (270, 2, desc), (273, 4, [0] * len(tiras)), (277, 3, [n]), (278, 4, [filas]),
        (279, 4, [len(t) for t in tiras]), (284, 3, [1]), (305, 2, soft),
        (33550, 12, [m.res, m.res, 0.0]), (33922, 12, [0.0, 0.0, 0.0, m.xmin, m.ymax, 0.0]),
        (34735, 3, claves),
    ]
    formato = {3: "H", 4: "I", 2: "s", 12: "d"}
    tam = {3: 2, 4: 4, 2: 1, 12: 8}
    n_et = len(etiquetas)
    pos_ifd = 8
    pos_extra = pos_ifd + 2 + 12 * n_et + 4
    extra = bytearray()
    entradas = []
    datos_pos = {}

    def bloque(tipo, vals):
        return vals if tipo == 2 else struct.pack("<" + formato[tipo] * len(vals), *vals)

    for et, tipo, vals in etiquetas:
        cuenta = len(vals)
        crudo = bloque(tipo, vals)
        if len(crudo) <= 4:
            entradas.append((et, tipo, cuenta, crudo.ljust(4, b"\0"), None))
        else:
            if len(extra) % 2:
                extra += b"\0"
            datos_pos[et] = pos_extra + len(extra)
            entradas.append((et, tipo, cuenta, None, pos_extra + len(extra)))
            extra += crudo
    if len(extra) % 2:
        extra += b"\0"
    pos_img = pos_extra + len(extra)
    offsets, p = [], pos_img
    for t in tiras:
        offsets.append(p)
        p += len(t)
    # las posiciones de las tiras, ya sabidas
    crudo_off = struct.pack("<" + "I" * len(offsets), *offsets)
    if len(offsets) == 1:
        entradas = [(e[0], e[1], e[2], crudo_off, None) if e[0] == 273 else e for e in entradas]
    else:
        q = datos_pos[273] - pos_extra
        extra[q:q + len(crudo_off)] = crudo_off
    salida = bytearray(b"II*\0" + struct.pack("<I", pos_ifd) + struct.pack("<H", n_et))
    for et, tipo, cuenta, enlinea, pos in entradas:
        salida += struct.pack("<HHI", et, tipo, cuenta)
        salida += enlinea if enlinea is not None else struct.pack("<I", pos)
    salida += struct.pack("<I", 0) + extra
    assert len(salida) == pos_img
    for t in tiras:
        salida += t
    return bytes(salida)


def _escribir(ruta: Path, datos) -> None:
    """Escribe de forma atómica (nunca un archivo a medias)."""
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix="." + ruta.stem + "-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos if isinstance(datos, (bytes, bytearray)) else datos.encode("utf-8"))
    os.replace(tmp, ruta)


def guardar(a, m: Marco, crs: str, ruta, formato: str, escribir_jpg=None,
            descripcion: str = "") -> list:
    """Guarda la imagen y lo que la acompaña; devuelve las rutas escritas.
    GeoTIFF lleva su sistema adentro; PNG y JPG, archivo de mundo y .prj.
    ``escribir_jpg(a, ruta)`` lo pone cada programa (PIL en IngeCAD, GDAL
    en QGIS)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritas = [ruta]
    if formato == "tif":
        epsg = epsg_de(crs)
        if not epsg:
            raise GoogleEarthError(f"El GeoTIFF necesita un sistema con código EPSG ({crs}).")
        _escribir(ruta, geotiff(a, m, epsg, descripcion))
    elif formato == "png":
        _escribir(ruta, png(a))
    elif formato == "jpg":
        if escribir_jpg is None:
            raise GoogleEarthError("Este programa no puede escribir JPG; elegí GeoTIFF o PNG.")
        escribir_jpg(a, ruta)
    else:
        raise GoogleEarthError(f"Formato desconocido: {formato}")
    mundo = ruta.with_suffix(MUNDO[formato])
    _escribir(mundo, texto_mundo(m))
    escritas.append(mundo)
    wkt = wkt_esri(crs)
    if wkt and formato != "tif":
        prj = ruta.with_suffix(".prj")
        _escribir(prj, wkt + "\n")
        escritas.append(prj)
    return escritas


def informe(ruta, datos: dict) -> Path:
    """«<imagen>.txt»: de dónde salió la imagen (fecha, cámara, controles)."""
    ruta = Path(ruta).with_suffix(".txt")
    lineas = ["GeoCAD Yaguareté - captura de Google Earth", ""]
    lineas += [f"{k}: {v}" for k, v in datos.items()]
    _escribir(ruta, "\n".join(lineas) + "\n")
    return ruta
