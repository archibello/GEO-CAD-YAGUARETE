# SPDX-License-Identifier: GPL-3.0-or-later
"""GEOHATCH: el HATCH de IngeCAD con la categoría «Custom» (3.99.0).

Con el módulo «sombreado» activo, HATCH (H, BH) arranca ésta
(dibujo.REEMPLAZOS). Con cualquier patrón de IngeCAD hace exactamente lo de
IngeCAD. Con Custom:
  - «Elegir en el dibujo <» de la ventana se cierra, pide el punto de origen
    y el segundo punto de la dirección (con línea elástica, referencias a
    objeto y ayudas al dibujo), y vuelve a la ventana, como «Origen» de
    AutoCAD;
  - las áreas se eligen como siempre (clic dentro u objetos); los bordes
    encontrados con un clic guardan sus arcos como arcos;
  - Intro: un sombreado con todo, o uno por área («Crear sombreados
    separados»), cada uno con sus islas. Un solo U.
"""
from __future__ import annotations

import math

from tools.blocks import HatchTool

from . import sombreado as S


class GeoHatchTool(HatchTool):
    #: el botón «Sombreado Custom» de GeoCAD abre la ventana ya en Custom
    _abrir_custom = False

    #: 3.101.0 (Fernando: «un puntero que me permita elegir polígonos cerrados,
    #: varios, o espacios entre líneas, sumándolos de a uno»): al elegir áreas el
    #: cursor es el cuadradito de elección (sin referencias a objeto, como el
    #: «Designe un punto interno» de AutoCAD); al pedir origen o dirección, la cruz
    entity_picker = True

    #: 3.101.1 (Fernando: «quiero que haya dos opciones, una, elegir islas y otra
    #: elegir objetos (polilíneas cerradas)»): en Islas el clic toma siempre el
    #: espacio vacío con sus islas, aunque toque un borde; en Objetos, sólo el
    #: objeto por su borde. Arranca en Islas.
    PROMPT = ("Elegir islas: designe un punto interno o [Objetos(O)/desHacer(H)/"
              "Quitar contornos(Q)/parámeTros(T)], Intro para aplicar:")
    PROMPT_SELECCION = ("Elegir objetos: designe polilíneas cerradas o [Islas(I)/desHacer(H)/"
                        "Quitar contornos(Q)/parámeTros(T)], Intro para aplicar:")
    PROMPT_QUITAR = "Designe contornos para quitar o [Agregar contornos(A)], Intro para volver:"

    def start(self) -> None:
        self._regiones: list = []           # (exterior, [islas]) de cada clic
        self._elegidos: list = []           # en orden: ("area", (ext, islas)) / ("objeto", e)
        self._trazos = None                 # lo elegido, en tramos (para resaltarlo)
        self._antes = "pick"                # a qué vuelve Quitar contornos
        self._pedir = None                  # "origen" / "direccion"
        if type(self)._abrir_custom or GeoHatchTool._abrir_custom:
            GeoHatchTool._abrir_custom = False
            ultimo = dict(HatchTool._last)
            if not S.es_custom(ultimo):
                ultimo["pattern"] = S.CUSTOM
                ultimo.setdefault("custom", dict(getattr(GeoHatchTool, "_custom", S.DEFECTO)))
            HatchTool._last = ultimo
        self.name = "HATCH"
        self.mode = "pick"
        self.outer = []
        self.islands = []
        self.selected = []
        self.settings = dict(HatchTool._last)
        if HatchTool._skip_dialog:
            HatchTool._skip_dialog = False
            self._prompt()
            return
        self._ventana(primera=True)

    def _largo(self, v: float) -> str:
        f = getattr(super(), "length_text", None)
        return f(v) if f else f"{v:.4f}"

    def _angulo(self, v: float) -> str:
        f = getattr(super(), "angle_text", None)
        return f(v) if f else f"{v:g}"

    # -- la ventana ----------------------------------------------------------------
    def _ventana(self, primera: bool = False) -> None:
        pedido = dict(self.settings)
        pedido["_puede_pedir"] = True
        pedido["_modo"] = self._antes if self.mode == "quitar" else self.mode
        pedido["_hay_elegidos"] = bool(getattr(self, "_elegidos", None))
        chosen = self.ctx.ask_hatch(pedido)
        if chosen is None:
            if primera:
                self.ctx.finish()
            else:
                self._prompt()
            return
        chosen = dict(chosen)
        for k in ("_puede_pedir", "_modo", "_hay_elegidos"):
            chosen.pop(k, None)
        contornos = chosen.pop("_contornos", None)      # botón del grupo Contornos
        if contornos == "quitar" and self._elegidos:
            if self.mode != "quitar":
                self._antes = self.mode
            self.mode = "quitar"
        elif contornos in ("pick", "select"):
            self.mode = contornos
        custom = dict(chosen.get("custom") or {})
        pedir = custom.pop("_pedir", None)
        if S.es_custom(chosen):
            chosen["custom"] = S.custom_de({"custom": custom})
            GeoHatchTool._custom = dict(chosen["custom"])
        self.settings = chosen
        HatchTool._last = dict(chosen)
        if pedir and S.es_custom(chosen):
            self._pedir = "origen"
            self.entity_picker = False        # un punto: con referencias a objeto
            self.prompt("Punto de origen del sombreado <{x}, {y}>:",
                        x=self._largo(chosen["custom"]["origen"][0]),
                        y=self._largo(chosen["custom"]["origen"][1]))
            return
        self._prompt()

    def _prompt(self) -> None:
        self._pedir = None
        self.entity_picker = True
        if self.mode == "quitar":
            self.prompt(self.PROMPT_QUITAR)
        elif self.mode == "select":
            self.prompt(self.PROMPT_SELECCION)
        else:
            self.prompt(self.PROMPT)

    # -- lo elegido (3.101.0) ----------------------------------------------------------
    def _rearmar(self) -> None:
        """outer, islands, selected y _regiones salen de _elegidos (Deshacer y
        Quitar los cambian)."""
        self._regiones = [d for k, d in self._elegidos if k == "area"]
        self.outer = [o for o, _i in self._regiones]
        self.islands = [i for _o, isl in self._regiones for i in isl]
        self.selected = [d for k, d in self._elegidos if k == "objeto"]
        self._trazos = None

    def _sumar(self, tipo: str, dato) -> None:
        self._elegidos.append((tipo, dato))
        self._rearmar()

    @staticmethod
    def _puntos_de(e) -> list:
        try:
            from ezdxf import path as P
            pts = [(v.x, v.y) for v in P.make_path(e).flattening(0.01 * max(1e-9, _tam(e)))]
            if len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-12:
                pts.pop()                       # cerrado: el último repite el primero
            if len(pts) >= 2:
                return pts
        except Exception:  # noqa: BLE001
            pass
        return S.poligono_de(e)

    def trazos(self) -> list:
        """Los bordes de lo elegido, en tramos: se ven a trazos, como en AutoCAD."""
        if self._trazos is None:
            lazos = []
            for k, d in self._elegidos:
                if k == "area":
                    lazos.append(d[0])
                    lazos.extend(d[1])
                else:
                    lazos.append(self._puntos_de(d))
            tramos = []
            for lazo in lazos:
                pts = [(float(p[0]), float(p[1])) for p in lazo]
                if len(pts) >= 2:
                    tramos.extend(zip(pts, pts[1:] + pts[:1]))
            self._trazos = tramos
        return self._trazos

    def _deshacer(self) -> None:
        if not self._elegidos:
            self.ctx.echo("No hay nada que deshacer.")
        else:
            self._elegidos.pop()
            self._rearmar()
            self.ctx.echo("Se quitó el último contorno elegido.")
        self._prompt()

    def _quitar_en(self, point) -> None:
        """Quita lo elegido donde se hizo clic: el objeto tocado, o el área que
        lo contiene (la más chica, si hay varias)."""
        quitar = self._elegido_bajo(point)      # lo mismo que se ve en rojo
        if quitar is None:
            self.ctx.echo("Ahí no hay un contorno elegido.")
            return
        del self._elegidos[quitar]
        self._rearmar()
        self.ctx.echo("1 contorno quitado.")

    def _volver(self) -> None:
        self._pedir = None
        HatchTool._last = dict(self.settings)
        self._ventana()

    def _poner(self, **valores) -> None:
        c = S.custom_de(self.settings)
        c.update(valores)
        self.settings["custom"] = S.custom_de({"custom": c})
        GeoHatchTool._custom = dict(self.settings["custom"])

    def _pedir_direccion(self) -> None:
        self._pedir = "direccion"
        self.prompt("Segundo punto de la dirección <{a}>:",
                    a=self._angulo(S.custom_de(self.settings)["direccion"]))

    # -- entradas ------------------------------------------------------------------
    def on_point(self, point) -> None:
        if self._pedir == "origen":
            self._poner(origen=(float(point[0]), float(point[1])))
            self.last_point = (float(point[0]), float(point[1]))
            self._pedir_direccion()
            return
        if self._pedir == "direccion":
            ox, oy = S.custom_de(self.settings)["origen"]
            dx, dy = float(point[0]) - ox, float(point[1]) - oy
            if math.hypot(dx, dy) <= 1e-12:
                self.ctx.echo("El segundo punto tiene que ser distinto del origen.")
                self._pedir_direccion()
                return
            self._poner(direccion=math.degrees(math.atan2(dy, dx)) % 360.0)
            self._volver()
            return
        # 3.99.1 (Fernando): en Objetos, un clic SOBRE un objeto lo toma de contorno
        # (también una polilínea abierta, que se cierra); en Islas (3.101.1: siempre,
        # aunque toque un borde) busca el área y, si no cierra, toma como cerradas las
        # abiertas y salva las aberturas chicas. Con todos los patrones.
        servicios = self.ctx.services
        objeto = None
        if servicios is not None:
            try:
                objeto = servicios.pick_entity(point)
            except Exception:  # noqa: BLE001
                objeto = None
        if self.mode == "quitar":
            self._quitar_en(point)
            return
        if self.mode == "select" and objeto is not None and S.contorno_posible(objeto):
            if objeto in self.selected:
                self.ctx.echo("Ese objeto ya está elegido.")
            else:
                self._sumar("objeto", objeto)
                self.ctx.echo("1 contorno agregado.")
            return
        if self.mode == "select":
            self.ctx.echo("Ahí no hay un objeto que sirva de contorno.")
            return
        region = servicios.hatch_region_at(point) if servicios is not None else None
        if region is None and servicios is not None:
            region = S.region_abierta(servicios, point)
            if region is not None:
                self.ctx.echo("Contorno abierto o mal cerrado: se tomó como cerrado.")
        if region is None:
            self.ctx.echo("No se encontró un contorno cerrado en ese punto.")
            return
        outer, islands = region
        self._sumar("area", (outer, list(islands)))
        self.ctx.echo("Contorno encontrado.")

    def on_option(self, text: str) -> bool:
        if self._pedir is not None:
            t = text.strip()
            if t == "":                       # Intro: queda el valor de antes
                if self._pedir == "origen":
                    self.last_point = S.custom_de(self.settings)["origen"]
                    self._pedir_direccion()
                else:
                    self._volver()
                return True
            if self._pedir == "direccion":
                # con coma, @ o < son coordenadas: que IngeCAD lo lea como punto.
                # 3.99.2 (Fernando): un número solo NO es la dirección (sería un ángulo
                # respecto de la X del dibujo): la dirección se da con un punto y el
                # ángulo, respecto de ella, en la ventana
                if "," in t or "@" in t or "<" in t:
                    return False
                try:
                    float(t.rstrip("dD°"))
                except ValueError:
                    return False
                self.ctx.echo("La dirección se da con un punto. El ángulo de las líneas, "
                              "respecto de esa dirección, se escribe en la ventana (Ángulo).")
                self._pedir_direccion()
                return True
            return False
        t = S.sin_tildes(text.strip().lstrip("_")).upper()
        if self.mode == "quitar":
            if t in ("A", "AGREGAR", "AGREGAR CONTORNOS", "ADD"):
                self.mode = self._antes
                self._prompt()
                return True
            return False
        if t in ("H", "U", "DESHACER", "UNDO"):
            self._deshacer()
            return True
        if t in ("Q", "R", "QUITAR", "QUITAR CONTORNOS", "REMOVE"):
            self._antes = self.mode
            self.mode = "quitar"
            self._prompt()
            return True
        if t in ("O", "OBJETOS", "ELEGIR OBJETOS", "S", "SELECCIONAR", "SELECCIONAR OBJETOS",
                 "SELECT"):
            self.mode = "select"
            self._prompt()
            return True
        if t in ("I", "ISLAS", "ELEGIR ISLAS", "P", "PUNTOS", "PICK"):
            self.mode = "pick"
            self._prompt()
            return True
        if t in ("T", "K", "PARAMETROS", "SETTINGS"):
            self._ventana()
            return True
        return super().on_option(text)

    def on_cancel(self) -> None:
        if self._pedir is not None:           # Esc mientras pide: vuelve a la ventana
            self._volver()
            return
        super().on_cancel()

    # -- resaltado (3.101.1; lo pinta dibujo.py sobre la vista de IngeCAD) ----------
    #: el área bajo el cursor se busca a lo sumo cada tanto (segundos), y no se
    #: busca más al pasar si una búsqueda tardó demasiado (dibujo muy grande)
    PAUSA_AREA = 0.12
    DEMASIADO = 0.35

    def _objeto_bajo(self, cursor):
        """El objeto de contorno cuyo BORDE está bajo el cursor (no su interior)."""
        servicios = self.ctx.services
        if servicios is None:
            return None
        try:
            e = servicios.pick_entity(cursor)
        except Exception:  # noqa: BLE001
            return None
        return e if e is not None and S.contorno_posible(e) else None

    def _area_bajo(self, cursor):
        """(exterior, islas) del espacio vacío bajo el cursor, o None. Se guarda la
        última: mientras el cursor siga dentro de ella no se vuelve a buscar."""
        import time

        p = (float(cursor[0]), float(cursor[1]))
        hecho = getattr(self, "_area_cursor", None)
        if hecho is not None:
            ext, islas = hecho
            if S.adentro(p, [(q[0], q[1]) for q in ext]) and not any(
                    len(i) >= 3 and S.adentro(p, [(q[0], q[1]) for q in i]) for i in islas):
                return hecho
        if getattr(self, "_area_lenta", False):
            return None
        ahora = time.monotonic()
        if ahora - getattr(self, "_area_cuando", 0.0) < self.PAUSA_AREA:
            return None
        servicios = self.ctx.services
        region = None
        try:
            region = servicios.hatch_region_at(p)
            if region is None and time.monotonic() - ahora < self.DEMASIADO:
                region = S.region_abierta(servicios, p)
        except Exception:  # noqa: BLE001 -- un resaltado nunca corta la orden
            region = None
        fin = time.monotonic()
        self._area_cuando = fin
        if fin - ahora > self.DEMASIADO:
            self._area_lenta = True
        self._area_cursor = (list(region[0]), list(region[1])) if region else None
        return self._area_cursor

    def _elegido_bajo(self, cursor):
        """Índice en _elegidos de lo que quitaría un clic (como _quitar_en)."""
        objeto = self._objeto_bajo(cursor)
        for i, (k, d) in enumerate(self._elegidos):
            if k == "objeto" and d is objeto:
                return i
        p = (float(cursor[0]), float(cursor[1]))
        mejor = None
        for i, (k, d) in enumerate(self._elegidos):
            lazo = d[0] if k == "area" else self._puntos_de(d)
            if k == "area" and any(len(j) >= 3 and S.adentro(p, [(q[0], q[1]) for q in j])
                                   for j in d[1]):
                continue
            if len(lazo) >= 3 and S.adentro(p, [(q[0], q[1]) for q in lazo]):
                a = abs(S.area([(q[0], q[1]) for q in lazo]))
                if mejor is None or a < mejor[0]:
                    mejor = (a, i)
        return mejor[1] if mejor else None

    @staticmethod
    def _tramos_de_lazos(lazos) -> list:
        tramos = []
        for lazo in lazos:
            pts = [(float(q[0]), float(q[1])) for q in lazo]
            if len(pts) >= 2:
                tramos.extend(zip(pts, pts[1:] + pts[:1]))
        return tramos

    def _tramos_elegido(self, k, d) -> list:
        return self._tramos_de_lazos([d[0], *d[1]] if k == "area" else [self._puntos_de(d)])

    def resaltado(self, cursor) -> dict:
        """Fernando (27/11/2026): la silueta de lo que tomaría el clic se resalta
        al pasar por arriba, y lo ya elegido, más intenso y grueso. Con objetos,
        por el borde; con un punto interno, el espacio vacío bajo el cursor con
        sus islas. En Quitar contornos, en rojo lo que se quitaría."""
        if self._pedir is not None:
            return {}
        datos = {"sombreado_elegido": list(self.trazos())}
        if cursor is None:
            return datos
        if self.mode == "quitar":
            i = self._elegido_bajo(cursor)
            if i is not None:
                datos["sombreado_quitar"] = self._tramos_elegido(*self._elegidos[i])
            return datos
        if self.mode == "select":
            objeto = self._objeto_bajo(cursor)
            if objeto is not None:
                datos["sombreado_cursor"] = self._tramos_de_lazos([self._puntos_de(objeto)])
        else:
            area = self._area_bajo(cursor)
            if area is not None:
                datos["sombreado_cursor"] = self._tramos_de_lazos([area[0], *area[1]])
        return datos

    def preview_segments(self, cursor):
        if self._pedir == "direccion":
            o = S.custom_de(self.settings)["origen"]
            return [(tuple(o), (float(cursor[0]), float(cursor[1])))]
        if self._pedir is None:
            return list(self.trazos())
        return super().preview_segments(cursor)

    # -- Intro: crear --------------------------------------------------------------
    def _entidades_cerca(self, loop) -> list:
        """Lo que puede formar un contorno (para devolverle los arcos)."""
        index = getattr(self.ctx.services, "index", None)
        if index is None or not loop:
            return []
        xs, ys = [p[0] for p in loop], [p[1] for p in loop]
        pad = max(max(xs) - min(xs), max(ys) - min(ys)) * 1e-6
        try:
            handles = index.crossing((min(xs) - pad, min(ys) - pad,
                                      max(xs) + pad, max(ys) + pad))
            return [e for h in handles if (e := index.entity(h)) is not None]
        except Exception:  # noqa: BLE001
            return []

    def _exacto(self, loop):
        return S.con_arcos(loop, self._entidades_cerca(loop))

    def grupos(self) -> list:
        """[(exteriores, islas)]: uno solo con todo, o uno por área."""
        c = S.custom_de(self.settings)
        regiones = [(self._exacto(o), [self._exacto(i) for i in isl if len(i) >= 3])
                    for o, isl in self._regiones if len(o) >= 3]
        objetos = list(self.selected)
        if not c["separados"]:
            exteriores = [r[0] for r in regiones] + objetos
            islas = [i for r in regiones for i in r[1]]
            return [(exteriores, islas)] if exteriores else []
        grupos = [([o], isl) for o, isl in regiones]
        polis = [S.poligono_de(e) for e in objetos]
        validos = [i for i, p in enumerate(polis) if len(p) >= 3]
        for ext, islas in S.agrupar([polis[i] for i in validos]):
            grupos.append(([objetos[validos[ext]]], [objetos[validos[j]] for j in islas]))
        return grupos

    def on_enter(self) -> None:
        if self._pedir is not None:
            self.on_option("")
            return
        if self.mode == "quitar":                 # Intro: vuelve a sumar
            self.mode = self._antes
            self._prompt()
            return
        if not S.es_custom(self.settings):
            super().on_enter()
            return
        grupos = self.grupos()
        if not grupos:
            self.ctx.echo("No se eligió ningún contorno.")
            self.ctx.finish()
            return
        bordes = [b for e, _i in grupos for b in e]
        if S.muy_denso(bordes, self.settings):
            try:
                from core import actions
                self.ctx.echo(actions.too_dense_message())
            except Exception:  # noqa: BLE001
                self.ctx.echo("Demasiadas líneas: aumente la separación.")
            self._prompt()
            return
        self.ctx.execute(S.orden_crear(grupos, self.settings))
        n = len(grupos)
        self.ctx.echo("Sombreado Custom creado." if n == 1
                      else f"{n} sombreados Custom creados.")
        self.ctx.finish()


GeoHatchTool._custom = dict(S.DEFECTO)


def _tam(e) -> float:
    try:
        from ezdxf import bbox
        c = bbox.extents([e])
        return max(c.size.x, c.size.y)
    except Exception:  # noqa: BLE001
        return 1.0


# -- TRIM con sombreados (3.100.0) ------------------------------------------------------------------
from tools.edit import TrimTool  # noqa: E402


class GeoTrimTool(TrimTool):
    """El TRIM de IngeCAD; sobre un sombreado, el clic borra la parte del
    sombreado donde se hizo (Fernando, 27/11/2026)."""

    def apply_to_entity(self, entity, point) -> None:
        try:
            es = (entity.is_alive and entity.dxftype() == "HATCH"
                  and self.trim_mode != self.shift and S.activo())
        except Exception:  # noqa: BLE001
            es = False
        if es:
            self._recortar_sombreado(entity, point)
            return
        super().apply_to_entity(entity, point)

    def _cortadores(self, hatch) -> list:
        from . import sombreado_edicion as E
        index = getattr(self.ctx.services, "index", None)
        if index is None:
            return []
        if self._edges_handles is not None:
            ents = [index.entity(h) for h in self._edges_handles]
        else:
            try:
                from ezdxf import bbox
                caja = bbox.extents([hatch])
                rect = (caja.extmin.x, caja.extmin.y, caja.extmax.x, caja.extmax.y)
                ents = [index.entity(h) for h in index.crossing(rect)]
            except Exception:  # noqa: BLE001
                ents = []
        return [e for e in ents if e is not None and e.is_alive and e is not hatch
                and e.dxftype() in E.CURVAS]

    def _recortar_sombreado(self, hatch, point) -> None:
        from . import sombreado_edicion as E
        cortadores = self._cortadores(hatch)
        try:
            polis = E.recortar(hatch, point, cortadores)
        except Exception:  # noqa: BLE001 -- un borde raro: no se toca
            polis = None
        if polis is None:
            self.ctx.echo("Ningún borde de corte atraviesa el sombreado en ese lugar.")
            return
        self._replace("TRIM", hatch, [E.factoria(hatch, polis, cortadores)])
