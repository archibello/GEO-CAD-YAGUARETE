# Final — Dónde conseguir e instalar los programas

El puente tiene tres orillas: para que funcione completo hacen falta
**QGIS**, **IngeCAD** y **Google Earth Pro** instalados en la misma
computadora, y **GEO-CAD-YAGUARETÉ** instalado dentro de IngeCAD y de QGIS.
Los cuatro son gratuitos.

| Programa | Qué es | Licencia | ¿Imprescindible? |
|---|---|---|---|
| **QGIS** | el SIG | libre (GPL) | sí, para el puente |
| **IngeCAD** | el CAD | libre (GPL) | sí, para el puente |
| **Google Earth Pro** | las imágenes del mundo | gratuito, de Google | sólo para las funciones de Google Earth |
| **GEO-CAD-YAGUARETÉ** | el puente | libre (GPL-3.0 o posterior) | — |

## F.1 Antes de empezar

### Windows o Linux

GEO-CAD-YAGUARETÉ funciona en **Windows** (desde la versión 3.54.0) y en
**Linux**. Casi todo es igual en los dos; lo que cambia está marcado en cada
capítulo y en esta tabla:

| Función | Windows | Linux |
|---|---|---|
| Puente QGIS ⇄ IngeCAD, Datos, ROTULOSIG | sí | sí |
| Dibujo, Capas, Bloques, Papel, Cotas, Imágenes, GEORREF | sí | sí |
| GeoPackage (.gpkg) en IngeCAD | sí (GeoCAD trae lo que le falta al IngeCAD de Windows) | sí |
| Exportar e importar KML/KMZ, Ver en Google Earth | sí | sí |
| **Capturar imágenes de Google Earth** (pantalla y mosaico) | sí (desde la 3.75.0) | sí |

**Versiones probadas:**

| | Windows | Linux |
|---|---|---|
| IngeCAD | 0.6.8.2 | 0.7.0, 0.6.8.2, 0.6.7 (Flatpak) |
| QGIS | 4.2.3 | 4.2.2 (Flatpak), 3.40.5 (Debian), 3.28.9 LTS |

### En los dos sistemas

- **Orden recomendado:** primero QGIS e IngeCAD (y Google Earth Pro, si se
  va a usar), después GEO-CAD-YAGUARETÉ.
- ⚠ **Abrir cada programa una vez y cerrarlo** antes de instalar GeoCAD. Al
  abrirse por primera vez crean su carpeta de configuración (en QGIS, su
  *perfil*), y el instalador sólo instala donde la encuentra: un programa
  que nunca se abrió queda sin GeoCAD.
- **Python:** en Windows no hace falta instalarlo (GeoCAD usa el que trae
  QGIS). En Linux viene con casi todas las distribuciones.
- **No hace falta ser administrador**: GeoCAD se instala en la carpeta del
  usuario.

## F.2 QGIS

**Dónde conseguirlo:** sitio oficial **qgis.org**, sección *Descargar*.

**En Windows:**

1. En qgis.org > *Descargar*, elegir **QGIS para Windows** y bajar el
   instalador (.msi) de la versión más nueva, o la LTR (versión de largo
   plazo) si se prefiere estabilidad.
2. Doble clic en el .msi y aceptar los pasos (Siguiente, Siguiente,
   Instalar). Queda en `C:\Program Files\QGIS <versión>`.
3. Abrir QGIS desde el menú Inicio **una vez** y cerrarlo.

**En Linux:**

- Lo más simple: **Flathub**, `org.qgis.qgis` (flathub.org/apps/org.qgis.qgis),
  o la tienda de software de la distribución. En una terminal:

  ```bash
  flatpak install flathub org.qgis.qgis
  ```

- Permiso opcional (Flatpak), para que QGIS **abra IngeCAD solo** al
  enviarle capas:

  ```bash
  flatpak override --user --talk-name=org.freedesktop.Flatpak org.qgis.qgis
  ```

## F.3 IngeCAD

**Dónde conseguirlo:** sitio oficial **ingecad.org**; todas las versiones,
para Windows y Linux, en **github.com/ingelibre/ingecad/releases**.

**En Windows:**

1. En las versiones de IngeCAD, bajar el instalador de **Windows** de la
   última versión.
2. Doble clic y seguir los pasos.
3. Abrir IngeCAD **una vez** y cerrarlo.

**En Linux:**

- Seguir las instrucciones de ingecad.org (Flatpak recomendado).
- Permiso (Flatpak) para trabajar con capas en un **disco externo**
  (pendrive, disco USB):

  ```bash
  flatpak override --user --filesystem=/media org.ingecad.IngeCAD
  ```

Con IngeCAD 0.6.7 o más nuevo hace falta GeoCAD 3.20.1 o más nuevo.

## F.4 Google Earth Pro

**Dónde conseguirlo:** sitio oficial de Google, **google.com/earth/versions**,
la versión **Google Earth Pro para computadoras**.

⚠ Tiene que ser **Google Earth Pro de escritorio**, no la versión web ni la
del teléfono: GeoCAD se comunica con él por un enlace de red que sólo tiene
la de escritorio.

**En Windows:** bajar *Google Earth Pro para Windows*, doble clic en el
instalador y seguir los pasos. (La captura de imágenes en Windows necesita
GeoCAD 3.75.0 o más nuevo.)

**En Linux:** el paquete .deb (Ubuntu, Debian) o .rpm (Fedora) de la misma
página, o **Flathub**:

```bash
flatpak install flathub com.google.EarthPro
```

Si es **Flatpak** y al abrirlo dice que *no puede acceder a la ubicación del
archivo de caché*, o no deja guardar en Documentos, una sola vez:

```bash
mkdir -p ~/.googleearth
flatpak override --user --filesystem=~/.googleearth --filesystem=xdg-documents com.google.EarthPro
```

y salir de Google Earth del todo (**Archivo > Salir**; cerrar la ventana no
alcanza) antes de volver a abrirlo. En Linux, Google Earth Pro funciona por
X11; con Wayland, por XWayland (así viene en Ubuntu).

**En los dos:** **Herramientas > Opciones > Navegación > Velocidad de
vuelo** al máximo (5). Ver capítulo 3.

## F.5 GEO-CAD-YAGUARETÉ

### Descargar

En **github.com/archibello/GEO-CAD-YAGUARETE/releases/latest** bajar:

| Archivo | Para qué |
|---|---|
| `GeoCAD_<versión>.zip` | todo junto: los instaladores de Windows y Linux, el de QGIS, LEEME y CAMBIOS |
| `instalar_geocad_<versión>.py` | el instalador único: IngeCAD **y** QGIS |
| `INSTALAR_GeoCAD_Windows.bat` | el que se usa en **Windows** (llama al anterior) |
| `geocad_qgis_<versión>.zip` | sólo para QGIS (camino B) |
| `Manual_GEO-CAD-YAGUARETE.pdf` | este manual |

En Windows lo más cómodo es bajar `GeoCAD_<versión>.zip`, hacer clic
derecho > **Extraer todo** y entrar a la carpeta **GeoCAD_<versión>**.

### Instalar en Windows

1. **Cerrar IngeCAD y QGIS.**
2. En la carpeta **GeoCAD_<versión>**, doble clic en
   **INSTALAR_GeoCAD_Windows.bat**.
3. Se abre una ventana negra: busca el Python que trae QGIS y corre el
   instalador. Al final dice en qué programas quedó instalado. Apretar una
   tecla para cerrarla.
   - Si dice *«No se encontró QGIS…»*: QGIS no está en `C:\Program Files`.
     Instalarlo (F.2) y volver a intentar.
   - Si QGIS nunca se abrió en ese usuario, no tiene perfil: abrirlo una
     vez, cerrarlo y volver a correr el .bat.
4. Abrir IngeCAD y QGIS: cada uno pregunta qué módulos usar (ver abajo) y
   aparece el menú **GeoCAD Yaguareté**.

Dónde queda instalado (por si hace falta revisarlo):

| Programa | Carpeta |
|---|---|
| IngeCAD | `%APPDATA%\IngeCAD\plugins\geocad` (activado en el Registro de Windows del usuario) |
| QGIS | cada perfil de `%APPDATA%\QGIS\QGIS4\profiles` (y de QGIS3, si lo hay) |

**Comprobar el GeoPackage en Windows:** en IngeCAD, **GeoCAD Yaguareté >
Diagnóstico de GeoCAD Yaguareté en esta computadora** (DIAGNOSTICOGEOCAD)
tiene que decir **«GeoPackage (sqlite3): sí»**. El IngeCAD de Windows no
trae esa pieza; GeoCAD trae la suya y la usa sólo si falta.

### Instalar en Linux: elegir UN camino

**A. Desde IngeCAD (recomendado)**

1. Abrir IngeCAD.
2. En la línea de comandos escribir `AP` y Enter (APPLOAD, «cargar
   aplicación»).
3. Elegir `instalar_geocad_<versión>.py`.
4. IngeCAD instala GeoCAD en el momento, sin reiniciar, y pregunta qué
   módulos usar. Aparece el menú **GeoCAD Yaguareté**.
5. En la misma pasada intenta instalarlo en QGIS. Leer la línea de
   comandos:
   - «QGIS: … instalado y activado»: listo (si QGIS estaba abierto,
     reiniciarlo).
   - «QGIS: no se encontró o no se pudo escribir…»: pasa cuando los dos
     programas son Flatpak y no se ven entre sí. Terminar con el camino B o
     el C.

**B. Desde QGIS (sólo QGIS; sirve también en Windows)**

1. Abrir QGIS: **Complementos > Administrar e instalar complementos…**
2. **Instalar a partir de ZIP**, elegir `geocad_qgis_<versión>.zip` e
   **Instalar complemento**.
3. QGIS pregunta qué módulos usar y aparece el menú **GeoCAD Yaguareté**.
4. Para IngeCAD, hacer después el camino A (o, en Windows, el .bat).

**C. Desde una terminal (los dos de una vez)**

Con IngeCAD y QGIS **cerrados**, en la carpeta de la descarga:

```bash
python3 instalar_geocad_<versión>.py
```

o doble clic en `INSTALAR_GeoCAD.sh`. Al final dice en qué programas quedó
instalado.

### La primera vez: elegir los módulos

Al abrir cada programa con GeoCAD aparece la ventana de módulos. Si hay
dudas, dejar los que vienen marcados. Se cambian cuando se quiera en
**GeoCAD Yaguareté > Módulos…** (capítulos 1 y 2).

### Comprobar que quedó bien

- **IngeCAD:** está el menú **GeoCAD Yaguareté** y su barra;
  **Acerca de GEO-CAD-YAGUARETÉ…** muestra la versión.
- **QGIS:** está el menú **GeoCAD Yaguareté**, con la **misma versión** en
  **Acerca de…**
- **Los dos se ven:** en QGIS, **GeoCAD Yaguareté > Estado del puente…**
  con IngeCAD abierto dice «abierto».
- **Google Earth (Linux):** **GeoCAD Yaguareté > Google Earth > Abrir
  Google Earth con GeoCAD**; en *Lugares temporales* aparece «GeoCAD
  Yaguareté».

### Actualizar más adelante

No hace falta repetir la instalación: **GeoCAD Yaguareté > Actualizar
GeoCAD Yaguareté…** en cualquiera de los dos programas, en Windows y en
Linux. La primera vez pregunta la **carpeta de actualizaciones**: elegir la
carpeta donde se guardan las versiones descargadas (la que tiene las
carpetas «GeoCAD <versión>»). Busca la más nueva, muestra sus cambios, pide
confirmación e instala; después avisa al otro programa, que ofrece
actualizarse también. Sólo ofrece versiones más nuevas que la instalada.

### Quitarlo

Apagar los módulos en **Módulos…** deja cada programa como venía, sin
rastro. En QGIS también se puede quitar del todo: **Complementos >
Administrar e instalar complementos > GEO-CAD-YAGUARETÉ > Desinstalar**.

## F.6 Dónde pedir ayuda

- **Problemas, ideas y propuestas:**
  github.com/archibello/GEO-CAD-YAGUARETE/issues. Contar el **sistema**
  (Windows o Linux), la **versión**, el **programa** y el **mensaje** que
  apareció.
- **Informe para adjuntar:** en IngeCAD, **GeoCAD Yaguareté > Diagnóstico
  de GeoCAD Yaguareté en esta computadora** (DIAGNOSTICOGEOCAD). Para
  Google Earth (Linux), el archivo `~/.config/geocad/googleearth_registro.txt`.
- **Ayuda de cada programa:** QGIS en qgis.org (documentación y
  comunidad); IngeCAD en ingecad.org; Google Earth en
  support.google.com/earth.

## Autor y licencia

**Arq. Fernando Pablo Bellocchio** · Posadas, Misiones, Argentina.
Desarrollado con la ayuda de Claude (Anthropic).

© 2026 Fernando Pablo Bellocchio. **GPL-3.0-or-later**: libre para usar,
estudiar, modificar y compartir.

Las imágenes de Google Earth tienen las condiciones de uso de Google.
