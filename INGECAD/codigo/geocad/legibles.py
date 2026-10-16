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

La regen en paralelo de IngeCAD usa fork: los procesos hijos heredan el
retoque. La clave del balde conserva el tipo al final (pack ordena por
él); el escalón va justo antes, como texto.
"""
from __future__ import annotations

import math

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


def compatible(backend) -> bool:
    """El backend de IngeCAD es el que conocemos (0.6.7): baldes por
    (grupo, capa, color, espesor, tipo) y el tipo en ``_kind``."""
    vb = getattr(backend, "VertexBackend", None)
    return (vb is not None and hasattr(vb, "_bucket") and hasattr(vb, "enter_entity")
            and hasattr(vb, "exit_entity"))


def instalar() -> bool:
    """Pone el retoque (una sola vez). True si recién se puso (o se cambió
    por el de una versión nueva). Con otro IngeCAD, no toca nada."""
    try:
        from render import backend
    except Exception:  # noqa: BLE001 -- sin la pantalla de IngeCAD
        return False
    if not compatible(backend):
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


def aplicar_ya() -> None:
    """Al cargar GeoCAD (3.26.5): el retoque se pone antes de abrir un dibujo.
    Si ya hay uno abierto (Actualizar sin reiniciar IngeCAD), la pantalla se
    regenera una vez con la regla nueva: antes hacía falta reiniciar."""
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
