# SPDX-License-Identifier: GPL-3.0-or-later
"""Los textos se dibujan con la fuente elegida (3.11.2, módulo «Propiedades»).

Error de IngeCAD 0.6.5 (también sin GeoCAD), encontrado por Fernando al usar
el editor de texto: la fuente, la negrita y la cursiva elegidas en el editor
quedaban escritas en el texto ({\\fArial|b0|i1;...}) pero el dibujo no las
mostraba; todo salía en DejaVu Sans Mono. Dos causas:

1. El dibujo busca las letras con ezdxf, que dentro del Flatpak sólo conoce
   las ~90 fuentes del Flatpak. La lista «Fuente» del editor (Qt) muestra
   también las del sistema (unas 300 familias). Arial no está en ninguna:
   ezdxf no encontraba nada.
2. ezdxf compara el COMIENZO del nombre: «DejaVu Sans» también es «DejaVu
   Sans Mono» y «DejaVu Sans Condensed»; y busca la cursiva por «Italic»
   (DejaVu la llama «Oblique»). Terminaba en la Mono normal.

Ahora cada fuente se busca como la busca el editor: con fontconfig
(fc-match), lo mismo que usa Qt. Arial -> Liberation Sans (la equivalente
libre, igual que en el editor), «DejaVu Sans» cursiva -> DejaVu Sans
Oblique, y las del sistema (Ubuntu, Noto...) se agregan a ezdxf al usarlas.
Cada pedido se resuelve una sola vez. Sin fc-match o con el módulo
apagado, como viene.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import propiedades

GENERICAS = {"sans-serif", "serif", "monospace"}
TTF = {".ttf", ".ttc", ".otf"}

_resueltas: dict = {}           # (familia, negrita, cursiva) -> FontFace | None
_candado = threading.Lock()     # el dibujo se arma en otro hilo
_activo = [0.0, False]          # (cuándo se miró, valor): leerlo es leer un archivo


def activo() -> bool:
    ahora = time.monotonic()
    if ahora - _activo[0] > 2.0:
        try:
            _activo[1] = propiedades.activo()
        except Exception:  # noqa: BLE001
            _activo[1] = False
        _activo[0] = ahora
    return _activo[1]


def consulta(familia: str, negrita: bool, cursiva: bool) -> str:
    """El pedido para fc-match: 'Familia:bold:italic' (con - : , escapados)."""
    q = familia
    for c in "\\-:,":
        q = q.replace(c, "\\" + c)
    partes = [q]
    if negrita:
        partes.append("bold")
    if cursiva:
        partes.append("italic")
    return ":".join(partes)


def fc_match(familia: str, negrita: bool, cursiva: bool):
    """El archivo de la fuente que usaría Qt, o None."""
    exe = shutil.which("fc-match")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-f", "%{file}", consulta(familia, negrita, cursiva)],
                           capture_output=True, text=True, timeout=5)
    except Exception:  # noqa: BLE001
        return None
    ruta = Path(r.stdout.strip())
    if r.returncode != 0 or ruta.suffix.lower() not in TTF or not ruta.is_file():
        return None
    return ruta


def cara_de(ruta: Path):
    """La FontFace del archivo, agregada a las fuentes de ezdxf si faltaba."""
    from ezdxf.fonts import font_manager as fmod
    from ezdxf.fonts import fonts
    cache = fonts.font_manager._font_cache
    if ruta.name in cache and cache[ruta.name].file_path == ruta:
        return cache[ruta.name].font_face
    cara = fmod.get_ttf_font_face(ruta)
    cache.add_entry(ruta, cara)
    return cara


def resolver(familia: str, weight: int, italic: bool):
    """FontFace para el pedido, o None (entonces decide ezdxf, como viene)."""
    clave = (familia.lower(), weight >= 600, bool(italic))
    with _candado:
        if clave in _resueltas:
            return _resueltas[clave]
        cara = None
        ruta = fc_match(familia, weight >= 600, bool(italic))
        if ruta is not None:
            try:
                cara = cara_de(ruta)
            except Exception:  # noqa: BLE001
                cara = None
        _resueltas[clave] = cara
        return cara


def _envolver_find_best_match(original):
    def find_best_match(*, family="sans-serif", style="Regular", weight=400,
                        width=5, italic=False):
        if activo() and italic is not None and family \
                and str(family).lower() not in GENERICAS:
            try:
                cara = resolver(str(family), int(weight or 400), bool(italic))
            except Exception:  # noqa: BLE001
                cara = None
            if cara is not None:
                return cara
        return original(family=family, style=style, weight=weight,
                        width=width, italic=italic)
    find_best_match._puente_original = original
    find_best_match._puente_fabrica = _envolver_find_best_match
    return find_best_match


def instalar() -> None:
    """Se llama al cargar el plugin."""
    try:
        from ezdxf.fonts import fonts
    except Exception:  # noqa: BLE001
        return
    from .dibujo import envolver
    if getattr(fonts.find_best_match, "_puente_fabrica", None) is not _envolver_find_best_match:
        envolver(fonts, "find_best_match", _envolver_find_best_match, reemplazar=True)
