# Guía de instalación de GEO-CAD-YAGUARETÉ

Para quien lo instala **por primera vez**. Hay tres caminos: desde IngeCAD,
desde QGIS o desde una terminal. Con cualquiera se llega a lo mismo:
GEO-CAD-YAGUARETÉ funcionando en los dos programas.

## 1. Antes de empezar

- **Linux.** Por ahora funciona sólo en Linux.
- **IngeCAD y QGIS instalados.** Versiones probadas:
  - IngeCAD 0.6.7 (Flatpak), desde [ingecad.org](https://ingecad.org) o sus
    [versiones](https://github.com/ingelibre/ingecad/releases/latest); también 0.6.5 y 0.6.6.
    Con IngeCAD 0.6.7 hace falta GeoCAD 3.20.1 o más nuevo.
  - QGIS 4.2.2 (Flatpak de [Flathub](https://flathub.org/apps/org.qgis.qgis)),
    3.40.5 (Debian) o 3.28.9 LTS.
- **Abrir cada programa una vez y cerrarlo.** Al abrirse por primera vez
  crean su carpeta de configuración; GEO-CAD-YAGUARETÉ se instala ahí. Si un
  programa nunca se abrió, queda sin instalar.

## 2. Descargar

En [Releases](https://github.com/archibello/GEO-CAD-YAGUARETE/releases/latest)
bajar estos dos archivos (`<versión>` es el número, por ejemplo `3.11.2`):

| Archivo | Para qué |
|---|---|
| `instalar_geocad_<versión>.py` | El instalador único: IngeCAD **y** QGIS. |
| `geocad_qgis_<versión>.zip` | Sólo para QGIS (camino B). |

Guardarlos en la carpeta personal o en **Descargas**.

## 3. Instalar: elegir UN camino

### A. Desde IngeCAD (recomendado)

1. Abrir IngeCAD.
2. En la línea de comandos escribir `AP` y Enter (es APPLOAD, «cargar
   aplicación»).
3. Elegir el archivo `instalar_geocad_<versión>.py`.
4. IngeCAD instala GEO-CAD-YAGUARETÉ en el momento, sin reiniciar, y
   pregunta **qué módulos usar** (ver el punto 4). Aparece el menú
   **GeoCAD Yaguareté**.
5. En la misma pasada intenta instalarlo también en QGIS. Leer el mensaje
   de la línea de comandos:
   - «QGIS: … instalado y activado»: listo. Si QGIS estaba abierto,
     reiniciarlo.
   - «QGIS: no se encontró o no se pudo escribir…»: pasa cuando los dos
     programas son Flatpak y no se ven entre sí. Terminar con el camino B
     (sólo el paso de QGIS) o con el camino C.

### B. Desde QGIS

1. Abrir QGIS.
2. Menú **Complementos > Administrar e instalar complementos…**
3. A la izquierda, **Instalar a partir de ZIP**.
4. Elegir `geocad_qgis_<versión>.zip` y **Instalar complemento**.
5. QGIS pregunta qué módulos usar y aparece el menú **GeoCAD Yaguareté**.
6. Este camino instala **sólo QGIS**. Para IngeCAD, hacer después el
   camino A (en IngeCAD, `AP` con `instalar_geocad_<versión>.py`).

### C. Desde una terminal (los dos de una vez)

Con IngeCAD y QGIS **cerrados**, en la carpeta donde se descargó:

```bash
python3 instalar_geocad_<versión>.py
```

También se puede hacer doble clic en `INSTALAR_GeoCAD.sh`, que hace lo
mismo. Al final dice en qué programas quedó instalado.

## 4. La primera vez: elegir los módulos

La primera vez que se abre cada programa con GEO-CAD-YAGUARETÉ aparece una
ventana para elegir los módulos (Puente con el otro programa, Dibujo,
Bloques, Cotas, Selección…). Si hay dudas, dejar los que vienen marcados.
Lo que no se elige no aparece en ningún menú ni cambia nada del programa.
Se cambia cuando se quiera en **GeoCAD Yaguareté > Módulos…**

## 5. Comprobar que quedó bien

- **IngeCAD:** está el menú **GeoCAD Yaguareté** y su barra de botones.
  **GeoCAD Yaguareté > Acerca de GEO-CAD-YAGUARETÉ…** muestra la versión.
- **QGIS:** está el menú **GeoCAD Yaguareté**, con la misma versión en
  **Acerca de…**

## 6. Ajustes que pueden hacer falta (Flatpak)

Una sola vez, en una terminal:

- Capas en un **disco externo** (pendrive, disco USB), para IngeCAD:

  ```bash
  flatpak override --user --filesystem=/media org.ingecad.IngeCAD
  ```

- Para que QGIS pueda **abrir IngeCAD** solo al enviarle capas (opcional):

  ```bash
  flatpak override --user --talk-name=org.freedesktop.Flatpak org.qgis.qgis
  ```

## 6 bis. Google Earth junto a IngeCAD y QGIS (módulo Google Earth)

Para capturar imágenes de Google Earth ya ubicadas en el dibujo
(**GeoCAD Yaguareté > Google Earth**):

- Hace falta **Google Earth Pro de escritorio** (no la versión web). En
  Linux funciona por X11 (con Wayland, por XWayland: así viene en Ubuntu).
- Si Google Earth Pro está instalado como **Flatpak** y al abrirlo dice que
  *no puede acceder a la ubicación del archivo de caché*, o no deja guardar
  en Documentos, una sola vez:

  ```bash
  mkdir -p ~/.googleearth
  flatpak override --user --filesystem=~/.googleearth --filesystem=xdg-documents com.google.EarthPro
  ```

  y salir de Google Earth del todo (**Archivo > Salir**; cerrar la ventana
  no alcanza) antes de volver a abrirlo.
- Abrir Google Earth **desde la ventanita de GeoCAD** («Abrir Google Earth
  con GeoCAD»). En Google Earth tiene que haber **un solo** «GeoCAD
  Yaguareté» (en *Lugares temporales*): no guardarlo en *Mis lugares* y
  borrar los que hayan quedado de antes.
- Capturar desde **un programa por vez** (IngeCAD **o** QGIS): la imagen
  llega igual al otro por el Puente.
- Mientras captura, **no mover Google Earth** ni taparlo o minimizarlo: la
  foto es de su ventana (la vista previa de la ventanita muestra lo que ve
  GeoCAD). La chincheta del buscador y la brújula pueden tapar una cruz.
- La **fecha** de la imagen se elige en Google Earth (imágenes históricas)
  antes de capturar: GeoCAD captura la que esté puesta.
- Más detalle: ventana de Google Earth grande (Pantalla) o Mosaico.
- Las imágenes de Google Earth tienen las condiciones de uso de Google:
  sirven de referencia; respetar su atribución.

## 7. Actualizar más adelante

Ya no hace falta repetir la instalación: **GeoCAD Yaguareté > Actualizar
GeoCAD Yaguareté…** en cualquiera de los dos programas. La primera vez
pregunta la carpeta donde se guardan las versiones descargadas.

## ¿Algo no anduvo?

Contarlo en [Issues](https://github.com/archibello/GEO-CAD-YAGUARETE/issues),
con la versión, el programa y el mensaje que apareció.
