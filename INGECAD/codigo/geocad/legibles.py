# SPDX-License-Identifier: GPL-3.0-or-later
"""Los textos se ven mientras se leen, cada uno según SU tamaño (3.26.4).

Error de IngeCAD (0.6.7), encontrado por Fernando con los rótulos de
PC_2_DE_MAYO (16/10/2026): al alejar la vista desaparecían también los
rótulos grandes, que se leían perfectamente.

Para que un catastro se mueva rápido, IngeCAD no dibuja los textos que en
pantalla miden menos de 2 píxeles. Pero no lo decide texto por texto: junta
los de la misma capa, color, espesor y orden de dibujo en un «balde» y usa
la ALTURA PROMEDIO del balde. En una capa de rótulos con muchos chicos
(parcelas urbanas) y algunos grandes (chacras), el promedio es chico y al
alejarse se escondía todo el balde, grandes incluidos.

Ahora cada balde de textos lleva además un ESCALÓN DE TAMAÑO: alturas que
difieren a lo sumo √2 (media octava) comparten balde, y cada escalón se
esconde recién cuando SUS textos ya no se leen. Lo rápido sigue igual (los
chicos se esconden como antes) y el archivo no cambia: es sólo la pantalla.
Retoque fijo de IngeCAD, como los candados (pedido de Fernando: «es
fundamental en un SIG poder ver las etiquetas legibles a cada escala»).

Tamaño mínimo configurable (3.27.0, elegido por Fernando): los 2 píxeles
de IngeCAD (``MIN_TEXT_PX`` de views/viewport.py, que lee en cada dibujado)
pasan a ser el ajuste «texto_minimo_px» de la configuración común (6 por
defecto; 0 = no esconder ninguno). Se aplica al cargar GeoCAD y cada vez
que se guarda la configuración: sólo se repinta, sin regenerar.

La regen en paralelo de IngeCAD usa fork: los procesos hijos heredan el
retoque. La clave del balde conserva el tipo al final (pack ordena por
él); el escalón va justo antes, como texto.

3.31.3: IngeCAD 0.6.8 lo corrigió por su cuenta (``_text_size_step``: un
escalón por octava, en la misma posición de la clave, como número). Con ese
IngeCAD el retoque se aparta: no se mezclan los dos escalones en la clave y
queda el de IngeCAD. El tamaño mínimo configurable sigue igual.
"""
from __future__ import annotations

import math
from importlib import import_module

#: escalones por cada vez que se duplica la altura (2 = media octava, √2)
ESCALONES_POR_OCTAVA = 2


def escalon(altura) -> str:
    """El escalón de tamaño de un texto de ``altura`` (unidades del dibujo);
    "" si no se sabe (queda en el balde de siempre)."""
    try:
        h = float(altura)
    except (TypeError, ValueError):
        return ""
    if not h > 0 or math.isinf(h):
        return ""
    return f"h{math.floor(math.log2(h) * ESCALONES_POR_OCTAVA):+03d}"


def altura_de(entity) -> float:
    """La altura de letra de un TEXT, ATTRIB, ATTDEF o MTEXT (0 si no tiene)."""
    try:
        if entity.dxftype() == "MTEXT":
            return float(entity.dxf.get("char_height", 0.0) or 0.0)
        return float(entity.dxf.get("height", 0.0) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _envolver_enter(original):
    def enter_entity(self, entity, properties):
        original(self, entity, properties)
        pila = self.__dict__.setdefault("_geocad_escalones", [])
        actual = pila[-1] if pila else ""
        if getattr(self, "_kind", "") == "T":
            actual = escalon(altura_de(entity)) or actual
        pila.append(actual)
        self._geocad_escalon = actual
    enter_entity._puente_original = original
    enter_entity._puente_fabrica = _envolver_enter
    return enter_entity


def _envolver_exit(original):
    def exit_entity(self, entity):
        original(self, entity)
        pila = self.__dict__.get("_geocad_escalones")
        if pila:
            pila.pop()
        self._geocad_escalon = pila[-1] if pila else ""
    exit_entity._puente_original = original
    exit_entity._puente_fabrica = _envolver_exit
    return exit_entity


def _envolver_bucket(original):
    def _bucket(self, properties):
        clase = getattr(self, "_geocad_escalon", "")
        if getattr(self, "_kind", "") != "T" or not clase:
            return original(self, properties)
        from render.batches import Bucket
        key = (self._group, properties.layer, properties.color,
               properties.lineweight, clase, self._kind)
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = self.buckets[key] = Bucket(
                properties.layer, properties.color, properties.lineweight,
                self._kind, group=self._group)
        return bucket
    _bucket._puente_original = original
    _bucket._puente_fabrica = _envolver_bucket
    return _bucket


def ingecad_lo_hace(backend) -> bool:
    """IngeCAD ya separa los textos por tamaño (desde 0.6.8)."""
    return callable(getattr(backend, "_text_size_step", None))


def compatible(backend) -> bool:
    """El backend de IngeCAD es el que conocemos (0.6.7): baldes por
    (grupo, capa, color, espesor, tipo) y el tipo en ``_kind``."""
    vb = getattr(backend, "VertexBackend", None)
    return (vb is not None and hasattr(vb, "_bucket") and hasattr(vb, "enter_entity")
            and hasattr(vb, "exit_entity"))


def quitar(backend) -> None:
    """Saca el retoque si estaba puesto (deja los de IngeCAD)."""
    from .dibujo import desenvolver
    vb = getattr(backend, "VertexBackend", None)
    for nombre in ("enter_entity", "exit_entity", "_bucket"):
        if vb is not None and hasattr(getattr(vb, nombre, None), "_puente_original"):
            desenvolver(vb, nombre)


def instalar() -> bool:
    """Pone el retoque (una sola vez). True si recién se puso (o se cambió
    por el de una versión nueva). Con otro IngeCAD, no toca nada."""
    try:
        from render import backend
    except Exception:  # noqa: BLE001 -- sin la pantalla de IngeCAD
        return False
    if not compatible(backend):
        return False
    if ingecad_lo_hace(backend):
        quitar(backend)
        return False
    from .dibujo import envolver
    vb = backend.VertexBackend
    nuevo = False
    for nombre, fabrica in (("enter_entity", _envolver_enter), ("exit_entity", _envolver_exit),
                            ("_bucket", _envolver_bucket)):
        if getattr(getattr(vb, nombre), "_puente_fabrica", None) is not fabrica:
            envolver(vb, nombre, fabrica, reemplazar=True)
            nuevo = True
    return nuevo


#: lo que trae IngeCAD (0.6.7) si no se puede leer la configuración
MINIMO_INGECAD = 2.0


def minimo_px(valores=None) -> float:
    """El tamaño mínimo (píxeles) de la configuración común."""
    try:
        if valores is None:
            from . import config
            valores = config.load()
        v = float(valores["texto_minimo_px"])
    except Exception:  # noqa: BLE001
        return MINIMO_INGECAD
    return v if v >= 0 and not math.isinf(v) else MINIMO_INGECAD


def aplicar_minimo(valores=None) -> bool:
    """Pone el tamaño mínimo en la pantalla de IngeCAD y la repinta.
    True si cambió. Con otro IngeCAD (sin ``MIN_TEXT_PX``), no toca nada."""
    try:
        viewport = import_module("views.viewport")
    except Exception:  # noqa: BLE001 -- sin la pantalla de IngeCAD
        return False
    if not isinstance(getattr(viewport, "MIN_TEXT_PX", None), (int, float)):
        return False
    v = minimo_px(valores)
    if viewport.MIN_TEXT_PX == v:
        return False
    viewport.MIN_TEXT_PX = v
    _repintar(viewport)
    return True


def _repintar(viewport) -> None:
    clase = getattr(viewport, "Viewport", None)
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001 -- sin Qt
        return
    app = QApplication.instance()
    if app is None or clase is None:
        return
    for w in app.allWidgets():
        if isinstance(w, clase):
            w.update()


def escuchar_config() -> None:
    """Cada vez que se guarda la configuración (Opciones, SHPCONFIG), el
    tamaño mínimo se aplica en el momento (una sola vez por carga)."""
    from . import config
    if aplicar_minimo not in config.AL_GUARDAR:
        config.AL_GUARDAR.append(aplicar_minimo)


def aplicar_ya() -> None:
    """Al cargar GeoCAD (3.26.5): el retoque se pone antes de abrir un dibujo.
    Si ya hay uno abierto (Actualizar sin reiniciar IngeCAD), la pantalla se
    regenera una vez con la regla nueva: antes hacía falta reiniciar.
    El tamaño mínimo (3.27.0) se pone también acá y al guardar la configuración."""
    try:
        escuchar_config()
        aplicar_minimo()
    except Exception:  # noqa: BLE001 -- queda el de IngeCAD
        pass
    if not instalar():
        return
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except Exception:  # noqa: BLE001 -- sin Qt
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        regen = getattr(w, "regen_in_memory", None)
        if callable(regen) and getattr(w, "document", None) is not None:
            QTimer.singleShot(0, regen)
