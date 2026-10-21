"""Carpetas temporales de las pruebas: todo lo que la prueba crea con tempfile
(HOME falso, obras, salidas) queda dentro de UNA carpeta, que se borra al
terminar, pase o falle la prueba. /tmp es tmpfs: lo que queda ocupa RAM.
Se importa antes del primer uso de tempfile:  import tmp_pruebas"""
import atexit, os, shutil, signal, sys, tempfile

RAIZ = tempfile.mkdtemp(prefix="geocad-prueba-")
tempfile.tempdir = RAIZ
atexit.register(shutil.rmtree, RAIZ, ignore_errors=True)
# timeout manda SIGTERM: salir con sys.exit para que corra atexit
signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))
