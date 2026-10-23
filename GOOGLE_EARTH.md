# Imágenes de Google Earth en el dibujo — guía de uso

Con **GeoCAD Yaguareté** se captura lo que se ve en Google Earth y la imagen
queda **ubicada en su lugar** dentro del dibujo de IngeCAD y del proyecto de
QGIS, ya llevada al sistema de coordenadas del trabajo (por ejemplo, POSGAR
2007 en su faja). No hace falta georreferenciar a mano.

![La captura entra en su lugar en IngeCAD, debajo de las parcelas](imagenes/google_earth_2_ingecad.webp)

## Se necesitan los tres programas

La herramienta trabaja con **los tres programas instalados en la misma
computadora**. Sin cualquiera de ellos no funciona como fue pensada:

| Programa | Para qué |
|---|---|
| **Google Earth Pro** (de escritorio, no la versión web) | Es de donde salen las imágenes. GeoCAD lo mueve, pone las cruces de control y saca la foto. |
| **IngeCAD** con GeoCAD Yaguareté | Recibe la imagen en el dibujo, en su lugar y en su escala. |
| **QGIS** con GeoCAD Yaguareté | Recibe la misma imagen como capa, en su lugar. |

Se captura desde **IngeCAD o desde QGIS** (uno por vez) y la imagen llega
también al otro por el Puente de GeoCAD. Las tres cosas tienen que estar
instaladas antes de empezar: ver la [guía de instalación](INSTALAR.md) y su
sección **6 bis** para Google Earth Pro.

En Linux, Google Earth Pro funciona por X11 (con Wayland, por XWayland: así
viene en Ubuntu).

## Antes de la primera captura (una sola vez)

1. Activar el módulo: **GeoCAD Yaguareté > Módulos… > Google Earth**.
2. Decirle al dibujo en qué sistema está: **SISTEMAGEO** en IngeCAD (en QGIS,
   un proyecto en coordenadas planas).
3. En Google Earth Pro: **Herramientas > Opciones > Navegación > Velocidad de
   vuelo**, al máximo (**5**; de fábrica viene en 0,18), y **Aceptar**. Con
   0,18 cada pieza del mosaico tarda unos 45 s; con 5, unos 10 s (25 piezas:
   4 min en vez de 25). Si vuela lento, GeoCAD lo avisa en la ventanita.
4. Si Google Earth Pro es Flatpak y da el error del archivo de caché, ver
   [INSTALAR.md, 6 bis](INSTALAR.md).

## Cómo se usa

1. **GeoCAD Yaguareté > Google Earth > Abrir Google Earth con GeoCAD**
   (orden ABRIRGE en IngeCAD). Se abre la ventanita de GeoCAD y Google
   Earth con el enlace **«GeoCAD Yaguareté»** en *Lugares temporales*, que
   tiene tres partes: Vista, Cámara y Cruces. Tiene que haber **uno solo**:
   si quedó alguno de antes, borrarlo. La ventanita avisa si el enlace es
   viejo.
2. Arriba de la ventanita se ve **Google Earth en video**: sólo la vista del
   mapa, sin paneles. Es lo mismo que va a capturar GeoCAD.
3. Llevar Google Earth a la zona: moverlo a mano o tocar **«Llevar Google
   Earth a lo que veo en IngeCAD/QGIS»**.
4. Si interesa la **fecha** de la imagen, elegirla en Google Earth (imágenes
   históricas, el reloj de la barra). GeoCAD captura la que esté puesta.
5. Elegir la **calidad**:
   - **Pantalla**: lo que se ve, de una vez (unos segundos). Más detalle
     con la ventana de Google Earth más grande.
   - **Mosaico**: varias fotos más de cerca, unidas en UNA imagen con mucho
     más detalle. Tarda más (hasta 25 piezas). Si la vista está muy alta,
     GeoCAD sube solo la altura de las piezas para que entren en 25.
   - **Lo que veo en IngeCAD/QGIS**: un mosaico de exactamente la zona que
     se ve en la pantalla del programa.
6. Revisar la lista **«Listo para capturar»**: todo en verde (enlace, vista,
   sistema, carpeta). Lo que está en rojo dice qué hacer.
7. **CAPTURAR** (o **Ctrl+Alt+G**, con la ventanita abierta).

![Mientras captura: Google Earth en video arriba y la barra de fotogramas](imagenes/google_earth_1_ventanita.webp)

Mientras captura:

- **No mover, tapar ni minimizar Google Earth.** La foto es de su ventana.
- La vista se endereza sola: **a plomo y con el norte arriba**.
- Aparecen **cuatro cruces magenta**: son las marcas de control que ubican
  la imagen. La chincheta del buscador y la brújula pueden tapar una: borrar
  la chincheta y, si hace falta, apagar la brújula (**Ver > Brújula**).
- El video muestra lo que hace Google Earth y la **barra de fotogramas**, el
  avance: **verde** las piezas listas, **amarillo** la que se está haciendo
  y **rojo** las que hay que repetir.
- Si algo falla, GeoCAD **vuelve a intentar solo**. Si una pieza no sale, se
  sigue con las demás y se repite al final. Si aun así falta alguna, se
  entrega el mosaico con ese hueco en blanco y se avisa cuál.
- **Cancelar** la corta y Google Earth vuelve a donde estaba.

Al terminar, Google Earth vuelve a la vista de antes y la imagen:

- queda en la **carpeta** de Configurar captura, con un nombre que dice
  cuándo y dónde se sacó:
  `GE_20261021-093512_S27.09633_W54.88868_img-9-7-2023.png`
  (fecha y hora, coordenadas del centro y la fecha de la imagen, si se
  escribió), con su archivo de ubicación (.pgw/.jgw/.tfw), su .prj y un
  .txt con el detalle (tamaño del píxel, control de las cruces, costuras);
- se **inserta** en el dibujo de IngeCAD (**U** la quita) y se **manda** a
  QGIS como capa, o al revés si se capturó desde QGIS.

![La misma captura en QGIS, como capa](imagenes/google_earth_3_qgis.webp)

## Configurar captura

**GeoCAD Yaguareté > Google Earth > Configurar captura…** (CONFIGURARGE):
formato (GeoTIFF, PNG o JPG), calidad, altura de las piezas del mosaico,
sistema (el del dibujo o uno elegido), carpeta (la misma para IngeCAD y
QGIS), qué hacer después (insertar, mandar al otro programa) y si las cruces
se muestran siempre.

## Si algo no anda

- **«Google Earth con el enlace de antes»**: en Google Earth borrar todos los
  «GeoCAD Yaguareté» (Lugares temporales y Mis lugares) y tocar «Abrir
  Google Earth con GeoCAD».
- **«Se cortó el enlace»**: Google Earth se cerró o dejó de pedir el enlace.
  Abrirlo de nuevo con GeoCAD.
- **No se ve una cruz**: algo la tapa (chincheta, brújula, otra ventana).
- **El mosaico tarda mucho** o la ventanita dice **«Google Earth vuela
  lento»**: poner la velocidad de vuelo de Google Earth en 5 (ver arriba).
  GeoCAD no la puede cambiar solo: el Flatpak de Google Earth le esconde su
  configuración.
- **«Another instance of this application is already running»** al abrir
  Google Earth, sin que haya otro abierto: quedó trabado de un cierre de
  golpe. «Abrir Google Earth con GeoCAD» lo destraba solo (si no hay ninguna
  ventana de Google Earth, ni minimizada); a mano: borrar
  `~/.googleearth/instance-running-lock`.
- Lo que pasa entre GeoCAD y Google Earth queda en
  `~/.config/geocad/googleearth_registro.txt`, útil para reportar un
  problema en [Issues](https://github.com/archibello/GEO-CAD-YAGUARETE/issues).

## Condiciones de uso

Las imágenes de Google Earth tienen las condiciones de uso de Google: sirven
de referencia para el trabajo y hay que respetar su atribución.
