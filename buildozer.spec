[app]
title = DocConvert NCTS
package.name = docconvertncts
package.domain = mx.novacoretech

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# pypdf: extracción de texto de PDF (sin dependencias nativas).
# fpdf2: generación de PDF (Word -> PDF, Fotos -> PDF), sin dependencias nativas.
# Pillow: procesamiento de fotos (rotar, ajustar a página) para el modo
#   Fotos -> PDF. fpdf2 ya la trae como dependencia transitiva, pero la
#   listamos explícitamente porque python-for-android no resuelve
#   dependencias transitivas de paquetes pip genéricos de forma confiable
#   (aprendido de la saga de lxml/python-docx). Pillow SÍ tiene una receta
#   madura y ampliamente probada en python-for-android (a diferencia de
#   lxml), así que no debería dar problemas.
# El .docx (lectura y escritura) se maneja con nuestro propio módulo
# docx_lite.py (zipfile + xml.etree, librería estándar) en vez de
# python-docx, porque python-docx depende de lxml y esa librería resultó
# imposible de compilar de forma confiable para Android en este entorno
# (varios intentos: receta oficial de p4a incompatible con Python 3.11+,
# y versiones más nuevas de lxml requieren auto-compilar libiconv de una
# forma que no funciona en cross-compilación). Ver docx_lite.py.
requirements = python3,kivy,plyer,pypdf,fpdf2,pillow,pyjnius

# Buildozer clona su propia copia de python-for-android desde GitHub
# (ignora la versión instalada por pip). La rama por defecto (master/develop)
# usa Python 3.14 como intérprete objetivo, que tiene un bug de compatibilidad
# con su propio pip al compilarse para Android. Fijamos un tag anterior y
# estable que usa Python 3.11.5.
p4a.branch = v2024.01.21

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,CAMERA,READ_MEDIA_IMAGES

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
