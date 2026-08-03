[app]
title = DocConvert NCTS
package.name = docconvertncts
package.domain = mx.novacoretech

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# pypdf: extracción de texto de PDF (sin dependencias nativas).
# python-docx: generación del archivo Word de salida (requiere lxml, que sí
#   tiene una receta de compilación en python-for-android, pero hay que
#   listarla explícitamente: p4a no resuelve dependencias transitivas de
#   paquetes pip genéricos como python-docx).
requirements = python3,kivy,plyer,pypdf,python-docx,lxml,fpdf2,pyjnius

# Buildozer clona su propia copia de python-for-android desde GitHub
# (ignora la versión instalada por pip). La rama por defecto (master/develop)
# usa Python 3.14 como intérprete objetivo, que tiene un bug de compatibilidad
# con su propio pip al compilarse para Android. Fijamos un tag anterior y
# estable que usa Python 3.11.5.
p4a.branch = v2024.01.21

# Receta local de lxml (ver recipes/lxml/__init__.py): la oficial de p4a
# está fijada a lxml 4.8.0, cuyo código C generado no compila contra
# Python 3.11+ ("incomplete definition of type 'struct _frame'"). Esta
# carpeta local tiene prioridad y usa lxml 5.2.2 en su lugar.
p4a.local_recipes = ./recipes

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# API 32 evita el "scoped storage" estricto de API 33+, simplificando
# el guardado directo en Download/DocConvert NCTS. Se puede migrar a
# MediaStore/SAF más adelante para soportar API 33+ sin este workaround.
android.api = 32
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
