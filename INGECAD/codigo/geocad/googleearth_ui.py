# SPDX-License-Identifier: GPL-3.0-or-later
"""Módulo «Google Earth» (3.33.0): la ventanita «GeoCAD Yaguareté» y
Configurar captura. Sirve a los dos programas: IngeCAD pasa PySide6 y QGIS
qgis.PyQt (misma forma de uso), más un ``programa`` con lo propio de cada
lado:

    nombre             "ingecad" o "qgis"
    sistema()          (crs, "del dibujo" / "del proyecto"), o ("", motivo)
    escribir_jpg       función (arreglo, ruta) o None
    insertar(ruta, crs)    la pone en el dibujo / proyecto; devuelve un texto
    otro_disponible()  ¿el otro programa está abierto con el Puente?
    enviar_otro(ruta, crs) se la manda por el buzón

El servidor sigue vivo al cerrar la ventanita (3.33.3): Google Earth
abandona el enlace si se cae, y había que volver a abrirlo con GeoCAD cada
vez. Se apaga sólo con el módulo (o al salir del programa). Ctrl+Alt+G se
escucha mientras la ventanita está abierta, con el foco en ella o en Google
Earth. La captura corre en otro hilo; un temporizador de Qt
lee su avance (nada de Qt fuera del hilo principal).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import googleearth as GE
from . import googleearth_vivo as V

_ESTADO = {"ventana": None}
OTRO = {"ingecad": "QGIS", "qgis": "IngeCAD"}
PROPIO = {"ingecad": "IngeCAD", "qgis": "QGIS"}


def _enum(cls, grupo: str, nombre: str):
    return getattr(getattr(cls, grupo, cls), nombre)


def _exec(d):
    return (getattr(d, "exec", None) or getattr(d, "exec_"))()


def destinos(programa_nombre: str) -> tuple:
    """(clave del propio, clave del otro) en los ajustes."""
    return ("insertar_ingecad", "agregar_qgis") if programa_nombre == "ingecad" \
        else ("agregar_qgis", "insertar_ingecad")


def resumen(aj: dict, programa, crs: str, de_donde: str) -> str:
    propio, otro = destinos(programa.nombre)
    envio = []
    if aj[propio]:
        envio.append("se inserta en " + PROPIO[programa.nombre])
    if aj[otro]:
        envio.append("se manda a " + OTRO[programa.nombre])
    sis = f"{crs} ({de_donde})" if crs else f"sin sistema: {de_donde}"
    return (f"{GE.FORMATOS[aj['formato']]} · {sis}\nCarpeta: {aj['carpeta']}"
            + ("\n" + (lambda s: s[:1].upper() + s[1:])(" y ".join(envio)) if envio else "")
            + f"\nMosaico: piezas a {aj['altura_pieza']:g} m")


def sistema_elegido(aj: dict, programa) -> tuple:
    """(crs, de dónde sale); crs "" si no hay uno en planas."""
    if aj["sistema"]:
        crs, de = aj["sistema"], "elegido en Configurar captura"
    else:
        crs, de = programa.sistema()
    if crs and not GE.es_planas(crs):
        return "", f"{crs} no es un sistema en planas"
    return crs, de


# ================================================================== listo para capturar
VERDE, ROJO = "#2e7d32", "#c62828"


def requisitos(enlazado: bool, vista, crs: str, de: str, problema_carpeta: str,
               programa_nombre: str, zona=None) -> list:
    """[(ok, texto)]: lo que hace falta para capturar, con qué hacer si falta
    (3.33.1, pedido de Fernando: que se vea qué falta antes de apretar)."""
    if vista is not None:
        sugerido = f" (para esta zona: {GE.sistema_sugerido(vista.lon, vista.lat)})"
    else:
        sugerido = ""
    donde = "SISTEMAGEO en el dibujo" if programa_nombre == "ingecad" else \
        "un sistema en planas en el proyecto"
    return [
        (enlazado, "Google Earth enlazado" if enlazado else
         "Google Earth sin enlazar: tocá «Abrir Google Earth con GeoCAD»"),
        (vista is not None,
         f"Vista recibida: {vista.rango:,.0f} m de altura".replace(",", ".") if vista is not None else
         "Falta la vista: mové un poco Google Earth (un toque de rueda) y esperá un segundo"),
        (bool(crs), f"Sistema {crs} ({de})" if crs else
         f"Falta el sistema: {de}. Usá {donde} o elegilo en Configurar captura{sugerido}"),
        (not problema_carpeta, "Carpeta lista" if not problema_carpeta else problema_carpeta),
    ] + ([zona] if zona is not None else [])          # (ok, texto) de la zona en pantalla


def html_requisitos(lista) -> str:
    return "<br>".join(
        f'<span style="color:{VERDE if ok else ROJO}; font-weight:bold">{"✔" if ok else "✘"}</span> '
        + texto.replace("&", "&amp;").replace("<", "&lt;") for ok, texto in lista)


def zona_de(programa, crs: str):
    """(zona en ``crs``, texto) de lo que se ve en el programa, o (None,
    motivo). La pantalla está en el sistema del dibujo / proyecto."""
    leer = getattr(programa, "zona", None)
    z = leer() if leer is not None else None
    crs_prog = programa.sistema()[0] or crs     # sin sistema propio: el de la captura (3.33.2)
    nombre = PROPIO[programa.nombre]
    if z is None:
        return None, f"no se puede leer la pantalla de {nombre}"
    if not crs_prog:
        return None, f"falta el sistema {'del dibujo' if programa.nombre == 'ingecad' else 'del proyecto'}"
    if not crs:
        return None, "falta el sistema de la captura"
    try:
        zc = GE.zona_en(z, crs_prog, crs)
    except GE.GoogleEarthError as exc:
        return None, str(exc)
    return zc, f"{zc[2] - zc[0]:,.0f} x {zc[3] - zc[1]:,.0f} m".replace(",", ".")


def _miles(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def con_hora(texto: str) -> str:
    return time.strftime("%H:%M:%S") + " — " + texto


# ================================================================== Configurar captura
def configurar(QtCore, QtGui, QtWidgets, parent, programa) -> bool:
    """La ventana de los ajustes (modal). True si se guardó."""
    aj = GE.ajustes()
    d = QtWidgets.QDialog(parent)
    d.setWindowTitle("Configurar captura de Google Earth — GEO-CAD-YAGUARETÉ")
    d.setMinimumWidth(560)
    lay = QtWidgets.QVBoxLayout(d)
    botones = QtWidgets.QDialogButtonBox(d)
    sb = getattr(QtWidgets.QDialogButtonBox, "StandardButton", QtWidgets.QDialogButtonBox)
    botones.setStandardButtons(sb.Ok | sb.Cancel)
    lay.addWidget(botones)                               # Aceptar arriba (Fernando, 16/10/2026)
    form = QtWidgets.QFormLayout()
    lay.addLayout(form)

    formato = QtWidgets.QComboBox(d)
    for k, t in GE.FORMATOS.items():
        if k != "jpg" or programa.escribir_jpg is not None:
            formato.addItem(t, k)
    formato.setCurrentIndex(max(0, formato.findData(aj["formato"])))
    form.addRow("Formato:", formato)

    calidad = QtWidgets.QComboBox(d)
    for k, t in GE.CALIDADES.items():
        calidad.addItem(t, k)
    calidad.setCurrentIndex(max(0, calidad.findData(aj["calidad"])))
    form.addRow("Calidad:", calidad)

    altura = QtWidgets.QDoubleSpinBox(d)
    altura.setRange(30, 5000)
    altura.setDecimals(0)
    altura.setSuffix(" m")
    altura.setValue(aj["altura_pieza"])
    altura.setToolTip("Altura de la cámara en cada pieza del mosaico. Más baja = más detalle "
                      f"y más piezas (tope {GE.TOPE_PIEZAS}; unos {GE.SEGUNDOS_POR_PIEZA:.0f} s cada una).")
    form.addRow("Altura de las piezas del mosaico:", altura)

    crs_prog, de_prog = programa.sistema()
    del_programa = QtWidgets.QRadioButton(
        f"El {de_prog.replace('del ', '') if crs_prog else 'del dibujo / proyecto'}"
        f" ({crs_prog or 'sin sistema todavía'})", d)
    otro = QtWidgets.QRadioButton("Este:", d)
    otro_crs = QtWidgets.QLineEdit(aj["sistema"], d)
    otro_crs.setPlaceholderText("EPSG:5349")
    (otro if aj["sistema"] else del_programa).setChecked(True)
    fila = QtWidgets.QHBoxLayout()
    fila.addWidget(otro)
    fila.addWidget(otro_crs, 1)
    caja_sis = QtWidgets.QVBoxLayout()
    caja_sis.addWidget(del_programa)
    caja_sis.addLayout(fila)
    form.addRow("Sistema (en planas):", caja_sis)

    carpeta = QtWidgets.QLineEdit(aj["carpeta"], d)
    elegir = QtWidgets.QPushButton("Elegir...", d)
    fila_c = QtWidgets.QHBoxLayout()
    fila_c.addWidget(carpeta, 1)
    fila_c.addWidget(elegir)
    form.addRow("Carpeta:", fila_c)
    nota = QtWidgets.QLabel("La misma carpeta para IngeCAD y QGIS: tiene que ser una a la que "
                            "lleguen los dos (p. ej. dentro de Documentos o de un disco en /media).", d)
    nota.setWordWrap(True)
    form.addRow("", nota)

    propio_k, otro_k = destinos(programa.nombre)
    propio = QtWidgets.QCheckBox(("Insertarla en el dibujo de IngeCAD" if programa.nombre == "ingecad"
                                  else "Agregarla al proyecto de QGIS"), d)
    propio.setChecked(aj[propio_k])
    mandar = QtWidgets.QCheckBox(f"Mandarla a {OTRO[programa.nombre]} (con el Puente abierto)", d)
    mandar.setChecked(aj[otro_k])
    form.addRow("Después de capturar:", propio)
    form.addRow("", mandar)

    siempre = QtWidgets.QCheckBox("Mostrar las cruces mientras la ventanita está abierta "
                                  "(si no aparecen sólo al capturar)", d)
    siempre.setChecked(aj["marcas_siempre"])
    form.addRow("Cruces de control:", siempre)

    def elegir_carpeta():
        r = QtWidgets.QFileDialog.getExistingDirectory(d, "Carpeta de las capturas", carpeta.text())
        if r:
            carpeta.setText(r)

    elegir.clicked.connect(elegir_carpeta)

    def aceptar():
        problema = GE.problema_carpeta(carpeta.text())
        sis = otro_crs.text().strip().upper() if otro.isChecked() else ""
        if sis and not sis.startswith("EPSG:") and sis.isdigit():
            sis = "EPSG:" + sis
        if not problema and sis and not GE.es_planas(sis):
            problema = f"{sis} no es un sistema en planas (o no se reconoce)."
        if problema:
            QtWidgets.QMessageBox.warning(d, "GeoCAD Yaguareté", problema)
            return
        GE.guardar_ajustes({
            "formato": formato.currentData(), "calidad": calidad.currentData(),
            "altura_pieza": altura.value(), "sistema": sis,
            "carpeta": str(Path(carpeta.text().strip()).expanduser()),
            propio_k: propio.isChecked(), otro_k: mandar.isChecked(),
            "marcas_siempre": siempre.isChecked()})
        d.accept()

    botones.accepted.connect(aceptar)
    botones.rejected.connect(d.reject)
    ok = bool(_exec(d))
    v = _ESTADO["ventana"]
    if ok and v is not None:
        v.releer()
    return ok


# ================================================================== la ventanita
def abierta():
    return _ESTADO["ventana"]


def cerrar() -> None:
    """Al apagar el módulo: ventanita, servidor y atajo fuera, y el KML
    también (sin rastro)."""
    v = _ESTADO["ventana"]
    if v is not None:
        v.apagar()
    try:
        GE.archivo_kml().unlink()
    except OSError:
        pass


def abrir(QtCore, QtGui, QtWidgets, parent, programa, capturar: bool = False,
          abrir_ge: bool = False):
    """Abre (o trae al frente) la ventanita. ``capturar`` captura en el
    acto; ``abrir_ge`` abre Google Earth con el enlace de GeoCAD."""
    v = _ESTADO["ventana"]
    if v is None:
        try:
            v = _Ventanita(QtCore, QtGui, QtWidgets, parent, programa)
        except GE.GoogleEarthError as exc:
            QtWidgets.QMessageBox.warning(parent, "GeoCAD Yaguareté", str(exc))
            return None
        _ESTADO["ventana"] = v
    else:
        v.reanudar()                            # estaba cerrada con el servidor vivo
    v.show()
    v.raise_()
    v.activateWindow()
    if abrir_ge:
        v.abrir_google_earth()
    if capturar:
        v.capturar()
    return v


#: los colores de la barra de fotogramas (3.33.4, idea de Fernando)
COLOR_FOTOGRAMA = {"ok": "#27ae60", "falla": "#e74c3c", "actual": "#f1c40f", "": None}


def resumen_fotogramas(estados) -> str:
    """«12 de 25 listos · 2 a repetir» para el costado de la barra."""
    ok = sum(1 for e in estados if e == "ok")
    mal = sum(1 for e in estados if e == "falla")
    return f"{ok} de {len(estados)} listos" + (f" · {mal} a repetir" if mal else "")


def _Fotogramas(QtCore, QtGui, QtWidgets, parent):  # noqa: N802
    """La barra de fotogramas: una celda por pieza (Pantalla: una sola);
    verde las que quedaron, roja las que hay que repetir, amarilla la que se
    está haciendo y vacías las que faltan."""

    class Fotogramas(QtWidgets.QWidget):
        def __init__(self):
            super().__init__(parent)
            self.estados = []
            self.setFixedHeight(22)
            self.setToolTip("Fotogramas: verde listos, rojo a repetir, amarillo el que se está "
                            "haciendo, vacío los que faltan.")
            self.hide()

        def poner(self, estados):
            estados = list(estados)
            if estados != self.estados:
                self.estados = estados
                self.setToolTip(resumen_fotogramas(estados))
                self.show()
                self.update()

        def paintEvent(self, _ev):  # noqa: N802
            n = len(self.estados)
            if not n:
                return
            p = QtGui.QPainter(self)
            ancho = self.width() - 1
            borde = QtGui.QColor("#888888")
            for i, e in enumerate(self.estados):
                x0, x1 = int(i * ancho / n), int((i + 1) * ancho / n)
                r = QtCore.QRect(x0, 1, max(1, x1 - x0 - 1), self.height() - 3)
                color = COLOR_FOTOGRAMA.get(e)
                if color:
                    p.fillRect(r, QtGui.QColor(color))
                p.setPen(borde)
                p.drawRect(r)
            p.end()

    return Fotogramas()


def _Ventanita(QtCore, QtGui, QtWidgets, parent, programa):  # noqa: N802
    Qt = QtCore.Qt

    class Ventanita(QtWidgets.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.programa = programa
            self.setWindowTitle("GeoCAD Yaguareté — Google Earth")
            self.setWindowFlags(self.windowFlags() | _enum(Qt, "WindowType", "WindowStaysOnTopHint"))
            self.setModal(False)
            self.aj = GE.ajustes()
            self.srv = V.Servidor(marcas_siempre=self.aj["marcas_siempre"])
            self.srv.iniciar()
            self._escribir_kml()
            self._hilo = None
            self._avance = {"texto": "", "fraccion": 0.0, "fin": False, "error": "", "ruta": None}
            self._captura = None
            self._tecla = threading.Event()
            self._plan_de = None
            self._carpeta = ("", "", 0.0)       # (carpeta, problema, cuándo se miró)
            self._t_captura = 0.0
            self._armar()
            self.atajo = V.AtajoX11(self._tecla.set)
            self._atajo_ok = self.atajo.iniciar()
            self._apagando = False
            self.reloj = QtCore.QTimer(self)
            self.reloj.timeout.connect(self._tic)
            self.reloj.start(200)
            self._iniciar_previa()
            self.releer()

        def reanudar(self):
            """Se vuelve a abrir: atajo y reloj de nuevo; el servidor y el
            enlace con Google Earth nunca se cortaron."""
            if not self.srv.vivo:
                self.srv.iniciar()
                self._escribir_kml()
            if not self.reloj.isActive():
                self._tecla.clear()
                self._atajo_ok = self.atajo.iniciar()
                self.reloj.start(200)
            self._iniciar_previa()
            self.releer()

        # -- armado
        def _armar(self):
            exterior = QtWidgets.QVBoxLayout(self)
            # 3.33.3/3.33.4 (ideas de Fernando): Google Earth en VIDEO, sólo la
            # vista 3D y a todo el ancho; abajo, un fotograma por pieza
            self.previa = QtWidgets.QLabel("Google Earth no está a la vista.", self)
            self.previa.setAlignment(_enum(Qt, "AlignmentFlag", "AlignCenter"))
            self.previa.setFixedHeight(220)
            self.previa.setMinimumWidth(200)
            self.previa.setSizePolicy(_enum(QtWidgets.QSizePolicy, "Policy", "Ignored"),
                                      _enum(QtWidgets.QSizePolicy, "Policy", "Fixed"))
            self.previa.setStyleSheet("background:#202020; color:#aaaaaa;")
            exterior.addWidget(self.previa)
            self.fotogramas = _Fotogramas(QtCore, QtGui, QtWidgets, self)
            exterior.addWidget(self.fotogramas)
            self._cuadro = None                 # (número, arreglo) que deja el hilo del video
            self._cuadro_visto = 0
            self._hilo_previa = None
            self._parar_previa = threading.Event()
            self._ancho_previa = 800
            self._forma_previa = 0.0
            self.reloj_video = QtCore.QTimer(self)
            self.reloj_video.timeout.connect(self._mostrar_previa)
            # el resto se desplaza si no entra (en pantallas chicas se encimaba)
            desliz = QtWidgets.QScrollArea(self)
            desliz.setWidgetResizable(True)
            desliz.setFrameShape(_enum(QtWidgets.QFrame, "Shape", "NoFrame"))
            adentro = QtWidgets.QWidget(desliz)
            lay = QtWidgets.QVBoxLayout(adentro)
            lay.setContentsMargins(0, 0, 0, 0)
            desliz.setWidget(adentro)
            exterior.addWidget(desliz, 1)
            titulo = QtWidgets.QLabel("<b>Listo para capturar:</b>", self)
            lay.addWidget(titulo)
            self.lista = QtWidgets.QLabel(self)
            self.lista.setWordWrap(True)
            self.lista.setTextFormat(_enum(Qt, "TextFormat", "RichText"))
            lay.addWidget(self.lista)
            self.estado = QtWidgets.QLabel(self)
            self.estado.setWordWrap(True)
            lay.addWidget(self.estado)
            self.boton_ge = QtWidgets.QPushButton("Abrir Google Earth con GeoCAD", self)
            self.boton_ge.clicked.connect(self.abrir_google_earth)
            lay.addWidget(self.boton_ge)

            fila = QtWidgets.QHBoxLayout()
            self.r_pantalla = QtWidgets.QRadioButton("Pantalla", self)
            self.r_mosaico = QtWidgets.QRadioButton("Mosaico", self)
            self.r_zona = QtWidgets.QRadioButton(f"Lo que veo en {PROPIO[programa.nombre]}", self)
            self.r_zona.setToolTip("Mosaico que cubre exactamente lo que se ve en la pantalla de "
                                   f"{PROPIO[programa.nombre]} (Google Earth vuela solo).")
            fila.addWidget(QtWidgets.QLabel("Calidad:", self))
            fila.addWidget(self.r_pantalla)
            fila.addWidget(self.r_mosaico)
            fila.addWidget(self.r_zona)
            fila.addStretch(1)
            lay.addLayout(fila)
            self.r_mosaico.toggled.connect(self._calidad)
            self.r_zona.toggled.connect(self._calidad)
            self.boton_llevar = QtWidgets.QPushButton(
                f"Llevar Google Earth a lo que veo en {PROPIO[programa.nombre]}", self)
            self.boton_llevar.clicked.connect(self.llevar)
            lay.addWidget(self.boton_llevar)
            self.plan = QtWidgets.QLabel(self)
            self.plan.setWordWrap(True)
            lay.addWidget(self.plan)

            fila = QtWidgets.QHBoxLayout()
            fila.addWidget(QtWidgets.QLabel("Fecha de la imagen:", self))
            self.fecha = QtWidgets.QLineEdit(self)
            self.fecha.setPlaceholderText("opcional: la que muestra Google Earth abajo")
            self.fecha.setToolTip("GeoCAD no cambia la fecha de Google Earth: se captura la que\n"
                                  "tenga puesta. Lo que se escriba acá es sólo el rótulo, y vale\n"
                                  "para la próxima captura.")
            fila.addWidget(self.fecha, 1)
            lay.addLayout(fila)

            self.resumen = QtWidgets.QLabel(self)
            self.resumen.setWordWrap(True)
            lay.addWidget(self.resumen)
            conf = QtWidgets.QPushButton("Configurar captura...", self)
            conf.clicked.connect(lambda: configurar(QtCore, QtGui, QtWidgets, self, self.programa))
            lay.addWidget(conf)

            aviso = QtWidgets.QLabel(
                "Antes de capturar: borrá la chincheta del buscador (la X del buscador) y, si "
                "tapan una cruz, apagá la brújula (Ver > Brújula). La vista se endereza sola "
                "(norte arriba, mirando hacia abajo).", self)
            aviso.setWordWrap(True)
            lay.addWidget(aviso)
            lay.addStretch(1)
            lay = exterior                      # CAPTURAR, la barra y el resultado: siempre a la vista

            self.boton = QtWidgets.QPushButton("CAPTURAR  (Ctrl+Alt+G)", self)
            f = self.boton.font()
            f.setPointSizeF(f.pointSizeF() * 1.4)
            f.setBold(True)
            self.boton.setFont(f)
            self.boton.setMinimumHeight(48)
            self.boton.clicked.connect(self._boton)
            lay.addWidget(self.boton)
            self.barra = QtWidgets.QProgressBar(self)
            self.barra.setRange(0, 100)
            self.barra.hide()
            lay.addWidget(self.barra)
            self.salida = QtWidgets.QLabel(self)
            self.salida.setWordWrap(True)
            self.salida.setTextInteractionFlags(_enum(Qt, "TextInteractionFlag",
                                                      "TextSelectableByMouse"))
            lay.addWidget(self.salida)
            atajo = getattr(QtGui, "QShortcut", None) or getattr(QtWidgets, "QShortcut")
            self._sc = atajo(QtGui.QKeySequence("Ctrl+Alt+G"), self)
            self._sc.activated.connect(self.capturar)
            self.setMinimumWidth(420)
            self.resize(560, 900)

        def _escribir_kml(self):
            ruta = GE.archivo_kml()
            try:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(GE.kml_enlaces(self.srv.puerto))
            except OSError:
                pass

        def releer(self):
            self.aj = GE.ajustes()
            self.srv.marcas_siempre = self.aj["marcas_siempre"]
            {"mosaico": self.r_mosaico, "zona": self.r_zona}.get(
                self.aj["calidad"], self.r_pantalla).setChecked(True)
            self._plan_de = None
            self._mostrar_resumen()

        def _mostrar_resumen(self):
            crs, de = sistema_elegido(self.aj, self.programa)
            self.resumen.setText(resumen(self.aj, self.programa, crs, de))

        def _calidad(self, *_a):
            q = "mosaico" if self.r_mosaico.isChecked() else \
                "zona" if self.r_zona.isChecked() else "pantalla"
            if q != self.aj["calidad"]:
                self.aj = GE.guardar_ajustes({"calidad": q})
            self._plan_de = None

        # -- Google Earth
        def abrir_google_earth(self):
            if self.srv.conectado():               # 3.33.3: no duplicar el enlace
                self.salida.setStyleSheet("")
                self.salida.setText(con_hora("Google Earth ya está abierto y enlazado con GeoCAD."))
                return
            self._escribir_kml()
            url = QtCore.QUrl.fromLocalFile(str(GE.archivo_kml()))
            if not QtGui.QDesktopServices.openUrl(url):
                QtWidgets.QMessageBox.information(
                    self, "GeoCAD Yaguareté",
                    f"Abrí este archivo con Google Earth Pro (Archivo > Abrir):\n{GE.archivo_kml()}")
                return
            self.salida.setStyleSheet("")             # no es un error (3.33.2)
            self.salida.setText(con_hora("Google Earth abre el enlace de GeoCAD en Lugares "
                                         "temporales (no se guarda en Mis lugares)."))

        def llevar(self):
            """Google Earth a lo que se ve en el programa (3.33.1, idea de Fernando)."""
            if self._hilo is not None:
                return
            nombre = PROPIO[self.programa.nombre]
            crs_prog = self.programa.sistema()[0] or sistema_elegido(self.aj, self.programa)[0]
            leer = getattr(self.programa, "zona", None)
            z = leer() if leer is not None else None
            if not self.srv.conectado():
                self._error("Google Earth sin enlazar: tocá «Abrir Google Earth con GeoCAD».")
                return
            if z is None or not crs_prog:
                self._error(f"No se puede leer la pantalla de {nombre} en un sistema: "
                            f"{'SISTEMAGEO en el dibujo' if self.programa.nombre == 'ingecad' else 'el proyecto en planas'}.")
                return
            try:
                a_planas, a_geo = GE.transformadores(crs_prog)
                lon, lat, rango = GE.camara_para_zona(z, a_geo, self.srv.vista, a_planas)
                self.srv.volar(lon, lat, rango)
            except GE.GoogleEarthError as exc:
                self._error(str(exc))
                return
            self.salida.setStyleSheet("")
            self.salida.setText(con_hora(
                f"Google Earth va a lo que se ve en {nombre} ({_miles(z[2] - z[0])} x "
                f"{_miles(z[3] - z[1])} m, cámara a {_miles(rango)} m), norte arriba."))

        # -- temporizador
        # -- el video: un hilo filma la vista 3D de Google Earth (unos 25
        #    cuadros por segundo, sin trabar la ventana) y otro reloj muestra
        #    el último cuadro (3.33.4)
        def _iniciar_previa(self):
            if self._hilo_previa is not None:
                return
            self._parar_previa.clear()
            self._hilo_previa = threading.Thread(target=self._sacar_previas,
                                                 name="geocad-ge-video", daemon=True)
            self._hilo_previa.start()
            self.reloj_video.start(40)

        def _detener_previa(self):
            self.reloj_video.stop()
            self._parar_previa.set()
            if self._hilo_previa is not None:
                self._hilo_previa.join(2)
                self._hilo_previa = None

        def _sacar_previas(self):
            try:
                video = V.VideoX11()
            except Exception:  # noqa: BLE001 -- sin X11: sin video
                return
            n = 0
            try:
                while not self._parar_previa.is_set():
                    t = time.time()
                    try:
                        a = video.cuadro(self._ancho_previa)
                    except Exception:  # noqa: BLE001
                        a = None
                    n += 1
                    self._cuadro = (n, a)
                    self._parar_previa.wait(max(0.005, 0.04 - (time.time() - t)))
            finally:
                video.cerrar()

        def _mostrar_previa(self):
            escala = self.previa.devicePixelRatioF() if hasattr(self.previa, "devicePixelRatioF") else 1.0
            self._ancho_previa = max(200, int(self.previa.width() * escala))
            cuadro = self._cuadro
            if cuadro is None or cuadro[0] == self._cuadro_visto:
                return
            self._cuadro_visto, a = cuadro
            if a is None:
                self.previa.setText("Google Earth no está a la vista (¿minimizado o cerrado?).")
                return
            h, w = a.shape[:2]
            forma = w / h
            if abs(forma - self._forma_previa) > 0.01:      # el alto, a la forma de la vista 3D
                self._forma_previa = forma
                self.previa.setFixedHeight(max(140, min(380, int(self.previa.width() / forma))))
            img = QtGui.QImage(a.data, w, h, 3 * w, _enum(QtGui.QImage, "Format", "Format_RGB888")).copy()
            pm = QtGui.QPixmap.fromImage(img).scaled(
                int(self.previa.width() * escala), int(self.previa.height() * escala),
                _enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
                _enum(Qt, "TransformationMode", "SmoothTransformation"))
            if hasattr(pm, "setDevicePixelRatio"):
                pm.setDevicePixelRatio(escala)
            self.previa.setPixmap(pm)

        def _tic(self):
            if self._tecla.is_set():
                self._tecla.clear()
                self.capturar()
            cap = self._captura
            if cap is not None and cap.estados:
                self.fotogramas.poner(cap.estados)
            ocupado = self._hilo is not None
            enlazado = self.srv.conectado()
            self.boton_ge.setVisible(not enlazado)
            self.boton_llevar.setEnabled(enlazado and not ocupado)
            self.estado.setText("" if self._atajo_ok else
                                "Ctrl+Alt+G sólo con esta ventana al frente ("
                                + (self.atajo.error or "sin X11") + ").")
            v = self.srv.vista
            ph = f"la de Google Earth: {v.fecha}" if v is not None and v.fecha else \
                "opcional: la que muestra Google Earth abajo"
            if ph != self.fecha.placeholderText():
                self.fecha.setPlaceholderText(ph)
            lista = self._requisitos()
            crs, de = sistema_elegido(self.aj, self.programa)
            texto = resumen(self.aj, self.programa, crs, de)
            if texto != self.resumen.text():
                self.resumen.setText(texto)             # p. ej. después de SISTEMAGEO (3.33.2)
            html = html_requisitos(lista)
            if html != self.lista.text():
                self.lista.setText(html)
                self.adjustSize()                       # que no quede cortada (3.33.2)
            if not ocupado:
                listo = all(ok for ok, _t in lista)
                self.boton.setEnabled(listo)
                self.boton.setStyleSheet(f"background:{VERDE}; color:white;" if listo else "")
                self.boton.setToolTip("" if listo else "Falta lo que está en rojo arriba.")
                self._estimar()
                return
            av = self._avance
            self.barra.setValue(int(100 * av["fraccion"]))
            self.salida.setStyleSheet("")
            self.salida.setText(f"{av['texto']}\n(trabajando hace {time.time() - self._t_captura:.0f} s; "
                                "Cancelar la corta y la vista vuelve)")
            if av["fin"]:
                self._hilo = None
                self._terminar(av)

        def _requisitos(self):
            crs, de = sistema_elegido(self.aj, self.programa)
            carpeta, problema, cuando = self._carpeta
            if carpeta != self.aj["carpeta"] or time.time() - cuando > 5:
                problema = GE.problema_carpeta(self.aj["carpeta"])      # no en cada vuelta
                self._carpeta = (self.aj["carpeta"], problema, time.time())
            zona = None
            if self.r_zona.isChecked():
                zc, texto = zona_de(self.programa, crs)
                nombre = PROPIO[self.programa.nombre]
                zona = (zc is not None, f"Zona de {nombre}: {texto}" if zc is not None
                        else f"Falta la zona de {nombre}: {texto}")
            return requisitos(self.srv.conectado(), self.srv.vista, crs, de, problema,
                              self.programa.nombre, zona)

        def _estimar(self):
            if self.r_pantalla.isChecked():
                self.plan.setText("Pantalla: lo que se ve ahora en Google Earth, de una vez.")
                return
            v = self.srv.vista
            zona = None
            if self.r_zona.isChecked():
                crs_z, _de = sistema_elegido(self.aj, self.programa)
                zona, _t = zona_de(self.programa, crs_z)
                if zona is None:
                    self.plan.setText(f"Lo que veo en {PROPIO[self.programa.nombre]}: {_t}.")
                    self._plan_de = None
                    return
            clave = (id(v), self.aj["altura_pieza"], self.aj["sistema"],
                     tuple(round(c, 1) for c in zona) if zona else None)
            if v is None or clave == self._plan_de:
                if v is None:
                    self.plan.setText("Mosaico: falta la vista de Google Earth.")
                return
            self._plan_de = clave
            crs, _de = sistema_elegido(self.aj, self.programa)
            if not crs:
                crs = GE.sistema_sugerido(v.lon, v.lat)
            try:
                a, b = GE.transformadores(crs)
                p = GE.plan_mosaico(v, a, b, self.aj["altura_pieza"], zona=zona)
                n = len(p.centros)
                self.plan.setText(
                    "Mosaico: a esta altura alcanza con la pantalla." if n == 1 and zona is None else
                    f"Mosaico: {p.columnas} x {p.filas} = {n} pieza{'s' if n > 1 else ''} a {p.rango:g} m"
                    + (f" (subida de {p.pedida:g} m para no pasar de {GE.TOPE_PIEZAS})"
                       if p.pedida and p.rango > p.pedida else "")
                    + f", unos {p.segundos / 60:.1f} min. Google Earth se mueve solo y vuelve.")
            except GE.GoogleEarthError as exc:
                self.plan.setText(str(exc))

        # -- la captura
        def _boton(self):
            if self._hilo is not None and self._captura is not None:
                self._captura.cancelar.set()
                self.salida.setText("Cancelando... (la vista vuelve a donde estaba)")
                return
            self.capturar()

        def capturar(self):
            if self._hilo is not None:
                return
            # 3.33.3 (Fernando): manda lo que tiene Google Earth en ese
            # momento; la fecha escrita vale para esta captura y no se guarda
            self.aj = GE.ajustes()
            crs, de = sistema_elegido(self.aj, self.programa)
            v = self.srv.vista
            escrita = self.fecha.text().strip()
            fecha, origen = (escrita, "escrita") if escrita else \
                (v.fecha, "de Google Earth") if v is not None and v.fecha else ("", "")
            self._carpeta = ("", "", 0.0)              # la carpeta se mira de nuevo ahora
            faltan = [texto for ok, texto in self._requisitos() if not ok]
            if faltan:
                self._error("No se puede capturar todavía: " + "; ".join(faltan) + ".")
                return
            aviso_faja = GE.aviso_faja(crs, v.lon)
            zona = zona_de(self.programa, crs)[0] if self.aj["calidad"] == "zona" else None
            datos = dict(self.aj, crs=crs, de=de, aviso_faja=aviso_faja, zona=zona,
                         fecha=fecha, origen_fecha=origen, t_crudo=self.srv.t_crudo)
            self._t_captura = time.time()
            self.salida.setStyleSheet("")
            self.salida.setText(con_hora("Empezando la captura..."))
            self.boton.setEnabled(True)
            self.boton.setStyleSheet("")
            self._avance = {"texto": "Empezando la captura...", "fraccion": 0.0, "fin": False,
                            "error": "", "ruta": None, "crs": crs, "datos": datos}
            self.barra.setValue(0)
            self.barra.show()
            self.fotogramas.poner([])
            self.fotogramas.hide()
            self.boton.setText("Cancelar")
            self._hilo = threading.Thread(target=self._trabajar, args=(datos,),
                                          name="geocad-ge-captura", daemon=True)
            self._hilo.start()

        def _trabajar(self, d):
            av = self._avance

            def aviso(texto, fraccion=None):
                av["texto"] = texto
                if fraccion is not None:
                    av["fraccion"] = fraccion

            foto = None
            try:
                foto = V.FotoX11()
                if foto.ventana() is None:
                    raise GE.GoogleEarthError("No se encuentra la ventana de Google Earth Pro.")
                cap = V.Captura(self.srv, foto.foto, aviso)
                self._captura = cap
                a_planas, a_geo = GE.transformadores(d["crs"])
                t0 = time.time()

                def ciclo(intento):
                    # 3.33.3: si algo falla, la captura empieza de nuevo sola
                    if d["calidad"] in ("mosaico", "zona"):
                        fotos = cap.mosaico(a_planas, a_geo, d["altura_pieza"], zona=d["zona"])
                    else:
                        fotos = cap.pantalla(volar=intento > 1)
                    aviso("4/5 Uniendo y llevando a planas...", 0.85)
                    return V.procesar(
                        fotos, d["crs"], progreso=lambda f: aviso("4/5 Uniendo y llevando a planas... "
                                                                  f"{int(f * 100)} %", 0.85 + 0.1 * f),
                        cancelado=cap.cancelar.is_set, zona=d["zona"], completo=not cap.faltan)

                im, m, piezas, cost = V.con_reintentos(ciclo, aviso, cap.cancelar)
                vista = cap.original
                aviso("5/5 Guardando...", 0.97)
                try:                                    # el centro de la imagen, en grados
                    centro = GE.transformadores(d["crs"])[1]((m.xmin + m.xmax) / 2, (m.ymin + m.ymax) / 2)
                except Exception:  # noqa: BLE001
                    centro = (vista.lon, vista.lat) if vista else (None, None)
                ruta = Path(d["carpeta"]) / GE.nombre_archivo(d["fecha"], d["formato"],
                                                              lon=centro[0], lat=centro[1])
                info = {
                    "Fecha de la imagen": (f"{d['fecha']} ({d['origen_fecha']})" if d["fecha"]
                                           else "(no se escribió)"),
                    "Capturada": time.strftime("%d/%m/%Y %H:%M:%S"),
                    "Calidad": GE.CALIDADES[d["calidad"]] + (
                        f", {len(piezas)} piezas a {cap.plan.rango:g} m" if len(piezas) > 1 and cap.plan
                        else ""),
                    "Sistema": f"{d['crs']} ({d['de']})",
                    "Píxel": f"{m.res:.2f} m",
                    "Tamaño": f"{m.ancho} x {m.alto} px = {m.ancho * m.res:.0f} x {m.alto * m.res:.0f} m",
                    "Esquina NO": f"{m.xmin:.2f}, {m.ymax:.2f}",
                    "Control de las marcas (afín, máx.)":
                        f"{max(p.residuo for p in piezas) * 100:.1f} cm",
                    "Piezas que faltaron": (f"{len(cap.faltan)} de {len(cap.plan.centros)} (fila, columna: "
                                            + ", ".join(f"{f + 1},{c + 1}" for f, c in cap.faltan)
                                            + "), en blanco" if cap.faltan and cap.plan else "-"),
                    "Costuras (máx.)": (f"{max(c for *_x, c in cost) * 100:.1f} cm" if cost else "-"),
                    "Cámara de Google Earth": (f"{vista.lon:.7f}, {vista.lat:.7f}, {vista.rango:.0f} m"
                                               if vista else "-"),
                    "Tiempo": f"{time.time() - t0:.0f} s",
                    "Programa": PROPIO[self.programa.nombre],
                }
                desc = f"Google Earth {d['fecha']}".strip()
                GE.guardar(im, m, d["crs"], ruta, d["formato"], self.programa.escribir_jpg, desc)
                GE.informe(ruta, info)
                av.update(ruta=ruta, info=info, texto="5/5 Insertando...", fraccion=1.0)
            except V.Cancelado:
                av["error"] = "Captura cancelada; la vista volvió a donde estaba."
            except GE.GoogleEarthError as exc:
                av["error"] = str(exc)
            except Exception as exc:  # noqa: BLE001 -- nunca tumba el programa
                av["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if foto is not None:
                    foto.cerrar()
                if self._captura is not None:
                    av["estados"] = list(self._captura.estados)
                self._captura = None
                av["fin"] = True

        def _terminar(self, av):
            self.boton.setText("CAPTURAR  (Ctrl+Alt+G)")
            self.barra.hide()
            if av.get("estados"):
                self.fotogramas.poner(av["estados"])     # queda a la vista cómo salió
            if av["error"]:
                self._error(av["error"])
                return
            ruta, crs, d = av["ruta"], av["crs"], av["datos"]
            info = av["info"]
            textos = [f"Guardada: {ruta}", f"{info['Tamaño']}, píxel de {info['Píxel']}; control "
                      f"{info['Control de las marcas (afín, máx.)']}"
                      + (f", costuras {info['Costuras (máx.)']}" if info["Costuras (máx.)"] != "-" else "")]
            if d["aviso_faja"]:
                textos.append(d["aviso_faja"])
            propio, otro = destinos(self.programa.nombre)
            if d[propio]:
                try:
                    textos.append(self.programa.insertar(ruta, crs) or "")
                except Exception as exc:  # noqa: BLE001
                    textos.append(f"No se pudo insertar: {exc}")
            if d[otro]:
                if self.programa.otro_disponible():
                    self.programa.enviar_otro(ruta, crs)
                    textos.append(f"Mandada a {OTRO[self.programa.nombre]}.")
                else:
                    textos.append(f"{OTRO[self.programa.nombre]} no está abierto con el Puente: "
                                  "la imagen queda en la carpeta.")
            textos.insert(0, f"✔ Captura lista en {time.time() - self._t_captura:.0f} s.")
            if info.get("Piezas que faltaron", "-") != "-":
                textos.insert(1, f"Ojo: faltaron piezas, {info['Piezas que faltaron']}. "
                                 "Podés capturar de nuevo esa parte.")
            self.fecha.clear()                          # la escrita valía para ésta sola
            self.salida.setStyleSheet(f"color: {VERDE};")
            self.salida.setText(con_hora("\n".join(t for t in textos if t)))
            avisar = getattr(self.programa, "avisar", None)
            if avisar is not None:
                try:
                    avisar(f"Google Earth: captura lista ({info['Tamaño']}, píxel de "
                           f"{info['Píxel']}) en {ruta}")
                except Exception:  # noqa: BLE001
                    pass

        def _error(self, texto):
            self.salida.setStyleSheet(f"color: {ROJO};")
            self.salida.setText(con_hora("✘ " + texto))

        # -- cierre: atajo fuera; el servidor sigue (3.33.3) salvo al apagar
        def closeEvent(self, ev):  # noqa: N802
            if self._captura is not None:
                self._captura.cancelar.set()
            if self._hilo is not None:
                self._hilo.join(35)            # la vista vuelve antes de seguir
                self._hilo = None
                if self._avance.get("fin"):
                    self._terminar(self._avance)
            self.reloj.stop()
            self.atajo.detener()
            self._detener_previa()
            if self._apagando:
                self.srv.detener()
                if _ESTADO["ventana"] is self:
                    _ESTADO["ventana"] = None
            super().closeEvent(ev)

        def apagar(self):
            """Módulo apagado: todo fuera, servidor incluido."""
            self._apagando = True
            self.close()
            if self.srv.vivo:                  # ya estaba cerrada: close() no llama a closeEvent
                self.srv.detener()
            if _ESTADO["ventana"] is self:
                _ESTADO["ventana"] = None

        def reject(self):                      # Esc también cierra como corresponde
            self.close()

    return Ventanita()
