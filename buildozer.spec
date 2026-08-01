[app]
title = DocConvert NCTS
package.name = docconvertncts
package.domain = mx.novacoretech

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# Dependencias: fitz = PyMuPDF (usado internamente por pdf2docx).
# python-docx es requerido por pdf2docx para escribir el .docx de salida.
requirements = python3,kivy,plyer,pypdf,python-docx,pyjnius

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
