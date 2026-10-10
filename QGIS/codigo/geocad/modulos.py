# SPDX-License-Identifier: GPL-3.0-or-later
"""Qué módulos de GeoCAD están activos en cada programa.

    ~/.config/geocad/modulos.json   {"ingecad": {"puente": true, ...}, "qgis": {...}}

Cada programa tiene su propia lista (prender Dibujo en QGIS no lo prende en
IngeCAD), pero el archivo es uno solo, así que los dos menús pueden mostrar
qué está activo en cada lado. Un módulo apagado no deja rastro: sin menú,
sin barra, sin comandos, y el programa se comporta como venía.

Python puro (sin Qt): el complemento de QGIS usa una copia idéntica.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROGRAMAS = ("ingecad", "qgis")


@dataclass(frozen=True)
class Modulo:
    clave: str
    nombre: str
    detalle: str
    defecto: bool = True
    requiere: str = ""           # otro módulo del mismo programa
    disponible: bool = True      # False = se muestra como «próximamente»
    cambia_programa: bool = False  # cambia un comportamiento propio del programa


CATALOGO = {
    "ingecad": (
        Modulo("puente", "Puente con QGIS",
               "Recibe las capas que manda QGIS y se las devuelve con los cambios."),
        Modulo("datos", "Datos (barra y submenú)",
               "Tabla de atributos, consultas, temático, rótulos y objeto nuevo con formulario.",
               requiere="puente"),
        Modulo("boton_derecho", "Botón derecho = Enter",
               "Termina la orden, acepta lo escrito y repite la última. "
               "Ctrl + botón derecho muestra el menú.", cambia_programa=True),
        Modulo("empalme", "Empalme estilo AutoCAD (EMPALME / F)",
               "Como el FILLET de AutoCAD: también polilíneas (tramos de una misma "
               "polilínea, línea + polilínea, dos polilíneas) y respeta el lado elegido.",
               cambia_programa=True),
        Modulo("chaflan", "Chaflán estilo AutoCAD (CHAFLAN / CHA)",
               "Como el CHAMFER de AutoCAD, con Ochava (largo del bisel, ángulos iguales) por "
               "defecto: polilíneas, lado elegido, Distancia o Ángulo, "
               "Polilínea entera, Múltiple; conserva capa y vínculo con QGIS.",
               cambia_programa=True),
        Modulo("bloques", "Bloques: BLOQUE mejorado y edición en el lugar",
               "BLOQUE: objetos resaltados, punto base con referencias, vista previa y "
               "confirmación. INSERT con vista previa y el bloque siguiendo al cursor. "
               "Doble clic sobre un bloque para editarlo en el lugar.",
               cambia_programa=True),
        Modulo("texto", "Texto como AutoCAD (TEXTO / DT)",
               "El 1er punto ubica el texto, el 2º da la altura y el 3º la dirección, con "
               "línea elástica y el valor junto al cursor. Al terminar, los textos quedan "
               "elegidos para retocarlos en la paleta Properties.", cambia_programa=True),
        Modulo("estirar", "Estirar al instante y con vista previa (ESTIRA / S)",
               "Mientras se elige el segundo punto se ven los objetos estirados y lo "
               "atrapado entero sigue al cursor; al hacer clic el resultado queda en el "
               "momento, sin «Regenerando...».", cambia_programa=True),
        Modulo("partir", "Partir en punto (PARTEENPUNTO)",
               "Corta un objeto en un punto elegido con referencias (intersección, "
               "punto final, medio...). Muestra los dos pedazos antes del clic."),
        Modulo("orden", "Orden de dibujo (ALFRENTE, ALFONDO)",
               "Dos botones en la barra GeoCAD, como el DRAWORDER de AutoCAD: lo "
               "elegido se dibuja encima o debajo de todo (líneas, sombreados, "
               "textos, bloques). En pantalla, lo enviado al fondo queda debajo de "
               "todo y lo traído al frente encima de todo, también entre líneas, "
               "sombreados y textos. AutoCAD respeta el orden al abrir el DXF.",
               cambia_programa=True),
        Modulo("seleccion", "Selección estilo AutoCAD (SEL, FILTRO; W, C, WP, CP, F...)",
               "En cualquier «Designar objetos» (BORRA, DESPLAZA...) se escriben las "
               "opciones de AutoCAD: W, C, WP, CP, F, ALL, L, P, R, A, U (o V, PV, PC, B, "
               "TODO, UL, E, H) y FI (filtro). Órdenes SEL y FILTRO (FI): filtros de "
               "selección por tipo, capa, color, medidas, textos y datos de QGIS. "
               "La línea de comandos deja de autocompletar.",
               cambia_programa=True),
        Modulo("propiedades", "Propiedades en masa (paleta Properties)",
               "Con varios objetos seleccionados, la paleta Properties (Ctrl+1) deja "
               "cambiar en todos a la vez lo propio de su tipo (altura de texto, radio, "
               "escala de bloque...), los atributos de los bloques, y muestra largo y "
               "área totales. Al editar un texto, su formato va a la paleta y sobre el "
               "texto queda sólo la regla.", cambia_programa=True),
        Modulo("papel", "Espacio papel como AutoCAD (escala de la hoja)",
               "La presentación respeta la escala de su configuración de página: "
               "con 1 mm = 0,001 unidades (m) la hoja se dibuja en metros, la ventana "
               "a 1:100 (1/100XP) muestra 100 m en 1000 mm y se imprime así. Las "
               "presentaciones nuevas de un dibujo en metros nacen con 1 mm = 0,001.",
               cambia_programa=True),
        Modulo("impresion", "Vista previa y plumas (VISTAPREVIA, PLUMAS)",
               "VISTAPREVIA muestra la presentación como sale impresa (hoja, escalas, "
               "plumas) con zoom e Imprimir. PLUMAS edita la tabla de plumas .ctb como "
               "AutoCAD (color 1 Rojo, 2 Amarillo... -> color de impresión, grosor, "
               "tramado). En Page Setup suma Editar... y Vista previa... junto a la "
               "tabla de plumas.", cambia_programa=True),
        Modulo("cotas", "Cotas para el papel (CREAR COTA)",
               "CREAR COTA arma un estilo de cota con la escala del papel, la letra, "
               "la altura en mm de hoja, los decimales y la cabecera (p. ej. "
               "«Acot-100-6mm»). Los botones de medir (lineal, alineada, angular) "
               "acotan con él y cada cota cae en su capa «COTAS Acot-100-6mm».",
               cambia_programa=True),
        Modulo("angulos_relativos", "Ángulos relativos al tramo anterior",
               "En LÍNEA y POLILÍNEA, @d<ángulo es el ángulo interior, antihorario "
               "(180 = recto), como en Dibujo CAD.", cambia_programa=True),
    ),
    "qgis": (
        Modulo("puente", "Puente con IngeCAD",
               "Envía capas a IngeCAD y las recarga cuando IngeCAD guarda."),
        Modulo("dibujo", "Dibujo CAD",
               "Línea de comandos, barras Dibujo, Edición y Texto CAD, PROPIEDADES y UNIDADES "
               "(antes el complemento Dibujo CAD 16.3)."),
        Modulo("bloques", "Bloques CAD",
               "BLOQUE, INSERT, WBLOQUE y LIMPIA, con su barra.", requiere="dibujo"),
        Modulo("papel", "Espacio papel",
               "Presentaciones, VENTANAS, BLOQVENT y TRAZAR, con las pestañas Modelo / "
               "Presentaciones.", requiere="dibujo"),
        Modulo("capas", "Capas CAD (Layer Properties)",
               "Administrador de capas estilo AutoCAD con LAYER_CODE (antes Layer Properties 6.7)."),
    ),
}


def archivo() -> Path:
    return Path.home() / ".config" / "geocad" / "modulos.json"


def catalogo(programa: str):
    return CATALOGO[programa]


def _leer() -> dict:
    try:
        data = json.loads(archivo().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def elegido(programa: str) -> bool:
    """¿Ya se eligieron los módulos de este programa (al instalar)?"""
    return isinstance(_leer().get(programa), dict)


#: lo que se podía elegir en GeoCAD 2.0.0, que todavía no registraba los vistos
_VISTOS_2_0 = {"ingecad": {"puente", "datos", "boton_derecho", "angulos_relativos"},
               "qgis": {"puente"}}


def _vistos(data: dict, programa: str) -> set:
    """Módulos que ya estaban disponibles cuando se eligió."""
    reg = data.get("_vistos")
    if isinstance(reg, dict) and isinstance(reg.get(programa), list):
        return set(reg[programa])
    return set(_VISTOS_2_0.get(programa, ()))


def nuevos(programa: str) -> list:
    """Módulos que llegaron con una versión nueva después de la elección: se
    ofrecen con su valor por defecto (no quedan apagados por una elección
    hecha cuando todavía no existían)."""
    data = _leer()
    if not isinstance(data.get(programa), dict):
        return []
    vistos = _vistos(data, programa)
    return [m.clave for m in CATALOGO[programa] if m.disponible and m.clave not in vistos]


def aceptar_nuevos(programa: str) -> dict:
    """Los módulos nuevos quedan con su valor por defecto y ya no son nuevos."""
    por_defecto = {m.clave: m.defecto for m in CATALOGO[programa] if m.clave in nuevos(programa)}
    return guardar(programa, por_defecto)


def estado(programa: str) -> dict:
    """{clave: bool} con todos los módulos del catálogo. Los que no se
    eligieron todavía toman su valor por defecto; los no disponibles, False."""
    data = _leer()
    guardado = data.get(programa) or {}
    nuevos_ = set(nuevos(programa))
    out = {}
    for m in CATALOGO[programa]:
        if not m.disponible:
            valor = False
        elif m.clave in nuevos_:
            valor = m.defecto
        else:
            valor = guardado.get(m.clave, m.defecto)
        out[m.clave] = bool(valor)
    for m in CATALOGO[programa]:
        if m.requiere and not out.get(m.requiere, False):
            out[m.clave] = False
    return out


def activo(programa: str, clave: str) -> bool:
    return estado(programa).get(clave, False)


def guardar(programa: str, valores: dict) -> dict:
    """Guarda la elección (sólo las claves del catálogo) de forma atómica,
    sin tocar la del otro programa. Devuelve el estado resultante."""
    claves = {m.clave for m in CATALOGO[programa]}
    data = _leer()
    actual = dict(data.get(programa) or {})
    for k, v in valores.items():
        if k in claves:
            actual[k] = bool(v)
    data[programa] = actual
    reg = data.get("_vistos") if isinstance(data.get("_vistos"), dict) else {}
    reg[programa] = sorted(m.clave for m in CATALOGO[programa] if m.disponible)
    data["_vistos"] = reg
    path = archivo()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".modulos-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return estado(programa)


def poner(programa: str, clave: str, valor: bool) -> dict:
    return guardar(programa, {clave: valor})


def resumen(programa: str) -> str:
    """Una línea: qué está activo (para «Acerca de» y la línea de comandos)."""
    est = estado(programa)
    nombres = [m.nombre for m in CATALOGO[programa] if est.get(m.clave)]
    return ", ".join(nombres) if nombres else "ningún módulo activo"
