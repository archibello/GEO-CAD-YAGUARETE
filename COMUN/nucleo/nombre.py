# SPDX-License-Identifier: GPL-3.0-or-later
"""El nombre de GeoCAD en los dos programas, sus créditos y la ventana
«Acerca de...» (3.8.0).

Sólo cambia lo que se ve: por dentro sigue siendo «geocad» (carpeta del
plugin, órdenes, configuración, archivos geocad_* de Actualizar).
Sirve a los dos programas: IngeCAD le pasa PySide6.QtWidgets y QGIS
qgis.PyQt.QtWidgets.
"""
from __future__ import annotations

from html import escape

NOMBRE = "GEO-CAD-YAGUARETÉ"            # títulos, metadata, instalador, Acerca de
NOMBRE_CORTO = "GeoCAD Yaguareté"       # menú y barra
LEMA = "GIS to CAD y CAD to GIS: QGIS e IngeCAD trabajando como un mismo sistema."
AUTOR = "Arq. Fernando Pablo Bellocchio"
CIUDAD = "Posadas, Misiones, Argentina"
ANIO = "2026"
LICENCIA = "GPL-3.0-or-later"
LICENCIA_TEXTO = "libre para usar, estudiar, modificar y compartir"
REPOSITORIO = "https://github.com/archibello/GEO-CAD-YAGUARETE"
ISSUES = REPOSITORIO + "/issues"
CLAUDE = "Desarrollado con la ayuda de Claude (Anthropic)."

# Manual de usuario en GitHub (3.76.0, Fernando: «un enlace al manual, con el
# capítulo que le corresponde a cada programa»).
MANUAL = REPOSITORIO + "/blob/main/manual/"
CAPITULOS = {
    "qgis": ("02_qgis.md", "Capítulo 1 — GeoCAD en QGIS"),
    "ingecad": ("03_ingecad.md", "Capítulo 2 — GeoCAD en IngeCAD"),
    "googleearth": ("04_google_earth.md", "Capítulo 3 — GeoCAD en Google Earth"),
}


def url_manual(clave: str = "") -> str:
    """La página del manual: el capítulo de ``clave`` o el índice."""
    archivo = CAPITULOS[clave][0] if clave in CAPITULOS else "README.md"
    return MANUAL + archivo


def abrir_manual(clave: str = "", abrir_url=None) -> tuple[str, bool]:
    """Abre el capítulo en el navegador. ``abrir_url`` es el QDesktopServices.openUrl
    de cada programa (con la URL ya armada); si no puede, prueba con webbrowser.
    Devuelve (url, si se pudo abrir), para escribir la dirección si no."""
    url = url_manual(clave)
    abierto = False
    if abrir_url is not None:
        try:
            abierto = bool(abrir_url(url))
        except Exception:  # noqa: BLE001 -- sin Qt o sin navegador: webbrowser
            abierto = False
    if not abierto:
        try:
            import webbrowser
            abierto = bool(webbrowser.open(url))
        except Exception:  # noqa: BLE001
            abierto = False
    return url, abierto


def _nombre_prog(programa: str) -> str:
    return "IngeCAD" if programa == "ingecad" else "QGIS"


def titulo_acerca() -> str:
    return f"Acerca de {NOMBRE}"


def texto_acerca(programa: str, version: str, resumen: str = "") -> str:
    """El contenido de «Acerca de...» en texto plano (línea de comandos)."""
    lineas = [f"{NOMBRE} {version} para {_nombre_prog(programa)}.", LEMA]
    if resumen:
        lineas.append(f"Módulos activos: {resumen}.")
    lineas += [f"Autor: {AUTOR} · {CIUDAD}.",
               f"© {ANIO} {AUTOR.replace('Arq. ', '')}. Licencia {LICENCIA}: {LICENCIA_TEXTO}.",
               f"Código: {REPOSITORIO}",
               f"Ideas y problemas: {ISSUES}",
               CLAUDE]
    return "\n".join(lineas)


def html_acerca(programa: str, version: str, resumen: str = "") -> str:
    """Lo mismo, con enlaces, para la ventana."""
    def a(url):
        return f'<a href="{escape(url)}">{escape(url)}</a>'
    partes = [f"<h3>{escape(NOMBRE)} {escape(version)}</h3>",
              f"<p>{escape(LEMA)}<br>Para {_nombre_prog(programa)}"
              + (f" · módulos activos: {escape(resumen)}" if resumen else "") + ".</p>",
              f"<p><b>{escape(AUTOR)}</b><br>{escape(CIUDAD)}</p>",
              f"<p>© {ANIO} {escape(AUTOR.replace('Arq. ', ''))}. Licencia {LICENCIA}: "
              f"{escape(LICENCIA_TEXTO)}.</p>",
              f"<p>Código: {a(REPOSITORIO)}<br>Ideas y problemas: {a(ISSUES)}</p>",
              f"<p><small>{escape(CLAUDE)}</small></p>"]
    return "".join(partes)


def _exec(dialog):
    run = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return run()


def mostrar_acerca(QtWidgets, parent, programa: str, version: str, resumen: str = "") -> None:
    """La ventana «Acerca de...»: datos y enlaces que se abren en el navegador."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(titulo_acerca())
    dlg.setMinimumWidth(460)
    lay = QtWidgets.QVBoxLayout(dlg)
    label = QtWidgets.QLabel(html_acerca(programa, version, resumen), dlg)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    lay.addWidget(label)
    botones = QtWidgets.QDialogButtonBox(dlg)
    rol = getattr(QtWidgets.QDialogButtonBox, "StandardButton", QtWidgets.QDialogButtonBox)
    botones.setStandardButtons(rol.Close)
    botones.rejected.connect(dlg.reject)
    botones.accepted.connect(dlg.accept)
    lay.addWidget(botones)
    _exec(dlg)
