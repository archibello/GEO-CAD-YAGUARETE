# SPDX-License-Identifier: GPL-3.0-or-later
"""Los módulos de GeoCAD en QGIS que antes eran complementos propios:
Dibujo CAD (con Bloques y Papel) y Capas CAD (Layer Properties).

Cada uno se arranca como siempre (initGui / unload), pero:

- con un «iface» intermediario: lo que antes iba al menú Complementos
  (addPluginToMenu) va a un submenú del menú GeoCAD;
- registrado en qgis.utils.plugins con su nombre de siempre ('Dibujo_CAD',
  'Layer_Properties'), así se siguen encontrando entre sí (los comandos de
  capa en la línea de comandos, los colores de los textos...);
- si el complemento suelto de antes está instalado, se retira (se descarga y
  su carpeta queda como .anterior-<nombre>) para que no haya dos.
"""
from __future__ import annotations

import importlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sub:
    clave: str          # módulo de GeoCAD
    paquete: str        # subpaquete dentro de geocad
    modulo: str         # archivo con la clase
    clase: str
    nombre: str         # nombre en qgis.utils.plugins (el de siempre)
    titulo: str         # submenú en GeoCAD


SUBS = (
    Sub("dibujo", "dibujo", "plugin", "DibujoCADPlugin", "Dibujo_CAD", "Dibujo CAD"),
    Sub("capas", "capas", "plugin", "LayerPropertiesPlugin", "Layer_Properties", "Capas CAD"),
)
VIEJOS = {"dibujo": ("Dibujo_CAD",), "capas": ("Layer_Properties",)}


class IfaceIntermedio:
    """El iface de QGIS, salvo el menú Complementos: esas acciones se guardan
    por nombre de menú y GeoCAD las pone en su propio submenú."""

    def __init__(self, iface, al_cambiar=None):
        self._iface = iface
        self._al_cambiar = al_cambiar
        self.menus: dict = {}

    def __getattr__(self, name):
        return getattr(self._iface, name)

    def addPluginToMenu(self, menu, action):
        self.menus.setdefault(menu.replace("&", ""), []).append(action)
        if self._al_cambiar:
            self._al_cambiar()

    def removePluginMenu(self, menu, action):
        lista = self.menus.get(menu.replace("&", ""), [])
        if action in lista:
            lista.remove(action)
        if self._al_cambiar:
            self._al_cambiar()

    def acciones(self) -> list:
        out = []
        for lista in self.menus.values():
            out += lista
        return out


def _registro():
    try:
        import qgis.utils
        return qgis.utils.plugins
    except Exception:  # noqa: BLE001
        return {}


def fabricar(paquete_base: str, sub: Sub, iface):
    mod = importlib.import_module(f"{paquete_base}.{sub.paquete}.{sub.modulo}")
    return getattr(mod, sub.clase)(iface)


def retirar_viejos(clave: str, carpeta_plugins: Path) -> list:
    """Retira el complemento suelto de antes (si está): lo descarga y deja su
    carpeta como .anterior-<nombre>. Devuelve los nombres retirados."""
    retirados = []
    for viejo in VIEJOS.get(clave, ()):
        carpeta = carpeta_plugins / viejo
        if not carpeta.is_dir():
            continue
        try:
            import qgis.utils
            qgis.utils.unloadPlugin(viejo)
        except Exception:  # noqa: BLE001
            pass
        guardado = carpeta_plugins / f".anterior-{viejo}"
        try:
            shutil.rmtree(guardado, ignore_errors=True)
            carpeta.rename(guardado)
            retirados.append(viejo)
        except OSError:
            pass
    return retirados


class Cargador:
    """Arranca y descarga los submódulos según los módulos activos."""

    def __init__(self, iface, paquete_base: str, carpeta_plugins: Path, al_cambiar=None,
                 fabrica=fabricar):
        self.iface = iface
        self.paquete_base = paquete_base
        self.carpeta_plugins = Path(carpeta_plugins)
        self.al_cambiar = al_cambiar
        self.fabrica = fabrica
        self.activos: dict = {}       # clave -> (instancia, iface intermedio)
        self.avisos: list = []

    def cargar(self, estado: dict) -> None:
        reg = _registro()
        for sub in SUBS:
            if not estado.get(sub.clave) or sub.clave in self.activos:
                continue
            retirados = retirar_viejos(sub.clave, self.carpeta_plugins)
            if retirados:
                self.avisos.append(f"Se retiró el complemento {', '.join(retirados)} "
                                   f"(ahora es el módulo {sub.titulo} de GeoCAD Yaguareté; queda una "
                                   f"copia como .anterior-{retirados[0]}).")
            ifc = IfaceIntermedio(self.iface, self.al_cambiar)
            inst = None
            try:
                inst = self.fabrica(self.paquete_base, sub, ifc)
                reg[sub.nombre] = inst          # antes de initGui: se buscan entre sí
                inst.initGui()
            except Exception as exc:  # noqa: BLE001
                if inst is not None and reg.get(sub.nombre) is inst:
                    reg.pop(sub.nombre, None)
                    try:
                        inst.unload()           # lo que haya alcanzado a poner, afuera
                    except Exception:  # noqa: BLE001
                        pass
                self.avisos.append(f"No se pudo iniciar {sub.titulo}: {type(exc).__name__}: {exc}")
                continue
            self.activos[sub.clave] = (inst, ifc)

    def descargar(self, claves=None) -> None:
        reg = _registro()
        # al revés: primero Capas (se desengancha de Dibujo), después Dibujo
        for sub in reversed(SUBS):
            if sub.clave not in self.activos or (claves is not None and sub.clave not in claves):
                continue
            inst, _ifc = self.activos.pop(sub.clave)
            try:
                inst.unload()
            except Exception as exc:  # noqa: BLE001
                self.avisos.append(f"{sub.titulo}: {type(exc).__name__}: {exc}")
            if reg.get(sub.nombre) is inst:
                reg.pop(sub.nombre, None)

    def menus(self) -> list:
        """[(título del submenú, [acciones])] de los submódulos activos."""
        out = []
        for sub in SUBS:
            if sub.clave in self.activos:
                out.append((sub.titulo, self.activos[sub.clave][1].acciones()))
        return out

    def tomar_avisos(self) -> list:
        avisos, self.avisos = self.avisos, []
        return avisos
