"""Las tres etapas de la impresión muestran la misma hoja (Fernando,
16/10/2026: «debería haber una correlación directa entre las tres etapas»).

Una lámina A0 VERTICAL de un dibujo en metros (1 mm = 0,001 m), con una
ventana a 1:15000 sobre un rectángulo de 3000 × 6000 m en Gauss-Krüger y un
marco dibujado en la hoja:

1. La PRESENTACIÓN (lo que IngeCAD dibuja en pantalla): la hoja de
   paper_frame y la ventana con model_to_paper. De ahí sale lo esperado, en
   mm de hoja.
2. TRAZAR: arranca en «Layout (hoja 1:1)», A0, vertical.
3. VISTAPREVIA (grabar de impresion_ui) y 4. el PDF (TRAZAR > Guardar PDF):
   la misma hoja (tamaño, orientación) y el marco y el rectángulo en el
   mismo lugar, a 1:15000. Se dibujan con el Qt de IngeCAD; sin PySide6
   (las pruebas de siempre) se prueba sólo lo que no usa Qt.
5. La vista previa de Page Setup imprime: aplica la página y abre TRAZAR.
6. Las letras TrueType se imprimen sin el borde de la capa (no se empastan).
"""
import os, sys, tempfile, types
os.environ["HOME"] = tempfile.mkdtemp()
from pathlib import Path
from importlib import import_module
import ezdxf
from core.plugins import load_plugin
from core import layouts as L

lp = load_plugin(Path(__file__).resolve().parents[2] / "INGECAD" / "codigo" / "geocad", bundled=False)
assert lp.available, lp.reason
P = import_module("ingecad_plugin_geocad.papel")
P.instalar()

ESCALA = 15000.0
X0, Y0 = 5_431_000.0, 7_000_000.0                       # Gauss-Krüger, en m


def lamina():
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = 6
    doc = types.SimpleNamespace(doc=d, dirty=False, uninitialized_layouts=set())
    lay = d.layouts.get("Layout1")
    L.page_setup_command(lay, 841.0, 1189.0, (20.0, 7.5, 20.0, 7.5), "ISO A0",
                         fit_to_paper=False, scale=(1.0, 0.001)).do(doc)
    d.modelspace().add_lwpolyline(
        [(X0, Y0), (X0 + 3000, Y0), (X0 + 3000, Y0 + 6000), (X0, Y0 + 6000)],
        close=True, dxfattribs={"color": 1})                       # rojo
    L.viewport_fit_printable(doc, "Layout1").do(doc)
    vp = L.visible_viewports(lay)[-1]
    L.xp_zoom_command(vp, L.parse_xp_factor(f"1/{ESCALA:g}XP")).do(doc)
    # el marco: 30 mm adentro del borde de la hoja, en unidades de la hoja
    x0, y0, x1, y1 = L.paper_frame(lay)["sheet"]
    m = 0.030
    lay.add_lwpolyline([(x0 + m, y0 + m), (x1 - m, y0 + m), (x1 - m, y1 - m), (x0 + m, y1 - m)],
                       close=True, dxfattribs={"color": 5})        # azul
    return doc, lay, vp


doc, lay, vp = lamina()
k = P.unidades_por_mm(lay)
assert abs(k - 0.001) < 1e-15

# ------------------------------------------------------------- 1. la presentación
sx0, sy0, sx1, sy1 = L.paper_frame(lay)["sheet"]
ANCHO, ALTO = (sx1 - sx0) / k, (sy1 - sy0) / k
assert abs(ANCHO - 841.0) < 1e-6 and abs(ALTO - 1189.0) < 1e-6        # A0 vertical


def en_hoja(x, y):
    """Un punto de la hoja (unidades) -> mm desde la esquina de arriba a la izquierda."""
    return (x - sx0) / k, (sy1 - y) / k


def caja(puntos):
    xs = [p[0] for p in puntos]; ys = [p[1] for p in puntos]
    return min(xs), min(ys), max(xs), max(ys)


MARCO = caja([en_hoja(sx0 + 0.030, sy0 + 0.030), en_hoja(sx1 - 0.030, sy1 - 0.030)])
RECT = caja([en_hoja(*L.model_to_paper(vp, X0, Y0)),
             en_hoja(*L.model_to_paper(vp, X0 + 3000, Y0 + 6000))])
assert L.scale_label(L.viewport_scale(vp)) == "1:15000"
assert abs((RECT[2] - RECT[0]) - 200.0) < 1e-6 and abs((RECT[3] - RECT[1]) - 400.0) < 1e-6, RECT
assert abs(MARCO[0] - 30.0) < 1e-9 and abs(MARCO[3] - (1189.0 - 30.0)) < 1e-6, MARCO
print("ok presentación: A0 vertical, 3000 × 6000 m = 200 × 400 mm a 1:15000")

# ------------------------------------------------------------- 2. TRAZAR arranca con la hoja
TAMANOS = [(210.0, 297.0), (297.0, 420.0), (420.0, 594.0), (594.0, 841.0),
           (841.0, 1189.0), (215.9, 279.4)]                 # los de pdf_out
pagina = L.effective_page(lay)
assert P.papel_de_la_hoja(pagina["width"], pagina["height"], TAMANOS) == (4, False)
print("ok TRAZAR: A0 vertical")

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # noqa: BLE001 -- sin Qt: lo demás se prueba con el Qt de IngeCAD
    print("(sin PySide6: la vista previa y el PDF se prueban con el Qt de IngeCAD)")
    print("TODO OK ETAPAS DE IMPRESIÓN")
    sys.exit(0)

# ------------------------------------------------------------- 3 y 4. vista previa y PDF
from PySide6.QtCore import QPointF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
app = QApplication.instance() or QApplication([])
P.instalar()                                         # ahora también pdf_out
from core.document import Document
from formats import pdf_out
UI = import_module("ingecad_plugin_geocad.impresion_ui")

carpeta = Path(tempfile.mkdtemp())
doc.doc.saveas(carpeta / "lamina.dxf")
documento = Document.load(carpeta / "lamina.dxf")
PX = 2.0                                             # px por mm al comparar


def tinta(imagen):
    """Cajas (en mm) de lo rojo y de lo azul de la imagen."""
    rojo, azul = [], []
    for y in range(imagen.height()):
        for x in range(imagen.width()):
            c = imagen.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            if r > 120 and r - max(g, b) > 60:
                rojo.append((x / PX, y / PX))
            elif b > 120 and b - max(r, g) > 60:
                azul.append((x / PX, y / PX))
    assert rojo and azul, (len(rojo), len(azul))
    return caja(rojo), caja(azul)


def igual(a, b, tol=2.0):
    return all(abs(u - v) <= tol for u, v in zip(a, b))


def lienzo(ancho, alto):
    imagen = QImage(int(round(ancho * PX)), int(round(alto * PX)), QImage.Format_RGB32)
    imagen.fill(Qt.white)
    return imagen


# 3. VISTAPREVIA: lo grabado, en la hoja que muestra el visor
dibujo, ancho, alto = UI.grabar(documento, "Layout1", "")
assert abs(ancho - 841.0) < 1e-6 and abs(alto - 1189.0) < 1e-6, (ancho, alto)   # vertical
previa = lienzo(ancho, alto)
p = QPainter(previa)
p.scale(PX / UI._PX_MM, PX / UI._PX_MM)              # como el Visor
p.drawPicture(0, 0, dibujo)
p.end()
rojo_previa, azul_previa = tinta(previa)
assert igual(rojo_previa, RECT) and igual(azul_previa, MARCO), (rojo_previa, RECT, azul_previa, MARCO)
print("ok vista previa = presentación")

# 4. El PDF de TRAZAR > Guardar PDF con «Layout (hoja 1:1)»
from PySide6.QtPdf import QPdfDocument
(w, h), _hoja = pdf_out.layout_sheet(documento, "Layout1")
ruta = str(carpeta / "lamina.pdf")
impresora = pdf_out.make_pdf_printer_mm(ruta, w, h)
pdf_out.plot_layout(documento, impresora, "Layout1")
pdf = QPdfDocument()
pdf.load(ruta)
assert pdf.pageCount() == 1
pt = pdf.pagePointSize(0)
assert pt.height() > pt.width(), pt                                   # vertical
assert abs(pt.width() * 25.4 / 72 - 841.0) < 1.0 and abs(pt.height() * 25.4 / 72 - 1189.0) < 1.0, pt
hoja_pdf = pdf.render(0, previa.size())
rojo_pdf, azul_pdf = tinta(hoja_pdf.convertToFormat(QImage.Format_RGB32))
assert igual(rojo_pdf, RECT) and igual(azul_pdf, MARCO), (rojo_pdf, RECT, azul_pdf, MARCO)
assert igual(rojo_pdf, rojo_previa, 1.0) and igual(azul_pdf, azul_previa, 1.0)
print("ok PDF = vista previa = presentación (A0 vertical, 1:15000, mismo lugar)")

# 5. La vista previa de Page Setup también tiene «Imprimir...» (Fernando,
# 3.27.2): aplica la página elegida (Aceptar) y, liberado el diálogo, TRAZAR.
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QPushButton, QWidget
from views.page_setup_dialog import PageSetupDialog
ventana = QWidget()
ventana.document, ventana._active_layout = documento, "Layout1"
ordenes = []
ventana._invoke_command = ordenes.append
lay_doc = documento.doc.layouts.get("Layout1")
config = PageSetupDialog(ventana, lay_doc)
UI.agregar_a_page_setup(config, ventana, lay_doc)
boton = [b for b in config.findChildren(QPushButton) if b.text() == "Vista previa..."][0]
vistos = []


def en_la_previa():
    vista = [w for w in app.topLevelWidgets() if isinstance(w, UI.VistaPrevia) and w.isVisible()][0]
    imprimir = [b for b in vista.findChildren(QPushButton) if b.text() == "Imprimir..."]
    vistos.append(bool(imprimir))
    (imprimir or [vista.findChildren(QPushButton)[-1]])[0].click()


QTimer.singleShot(0, boton.click)
QTimer.singleShot(50, en_la_previa)
assert config.exec() == 1 and vistos == [True], vistos       # Page Setup aceptado
app.processEvents()
assert ordenes == []                    # IngeCAD aplica la página antes de TRAZAR
config.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
app.processEvents()
assert ordenes == ["PLOT"], ordenes
print("ok vista previa de Page Setup: Imprimir... aplica la página y abre TRAZAR")

# 6. Las letras TrueType salen sin el borde de la capa (3.27.2): en el PDF un
# texto de 1 mm no se empasta. Con el contorno de 0,25 mm las letras grandes
# de Fernando salían como manchas.
IMP = import_module("ingecad_plugin_geocad.impresion")
IMP.instalar()
from PySide6.QtCore import Qt as _Qt
d2 = ezdxf.new("R2018"); d2.header["$INSUNITS"] = 6
d2.styles.add("ARIAL", font="arial.ttf")
d2.modelspace().add_text("265A", height=15.0, dxfattribs={"style": "ARIAL", "lineweight": 50})
d2.saveas(carpeta / "texto.dxf")
doc_texto = Document.load(carpeta / "texto.dxf")
escena = pdf_out.build_graphics_scene(doc_texto, None, None)
rellenos = [it for it in escena.items() if hasattr(it, "brush") and it.brush().style() != _Qt.NoBrush]
assert rellenos, "el texto TrueType tendría que dibujarse relleno"
pdf_out._use_physical_pens(escena, 1.0 / ESCALA, True)
assert all(it.pen().style() == _Qt.NoPen for it in rellenos)
print("ok letras TrueType sin el borde de la capa")

print("TODO OK ETAPAS DE IMPRESIÓN")
