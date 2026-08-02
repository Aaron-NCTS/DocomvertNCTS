[app]
title = DocConvert NCTS
package.name = docconvertncts
package.domain = mx.novacoretech

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# pypdf: extracción de texto de PDF (sin dependencias nativas).
# python-docx: generación del archivo Word de salida.
requirements = python3,kivy,plyer,pypdf,python-docx,reportlab,pyjnius

# Buildozer clona su propia copia de python-for-android desde GitHub
# (ignora la versión instalada por pip). La rama por defecto (master/develop)
# usa Python 3.14 como intérprete objetivo, que tiene un bug de compatibilidad
# con su propio pip al compilarse para Android. Fijamos un tag anterior y
# estable que usa Python 3.11.5.
p4a.branch = v2024.01.21

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
