# DocConvert NCTS - Móvil (Android)

Versión Android de DocConvert NCTS. **Solo incluye PDF → Word** (con texto
seleccionable; sin OCR). La conversión Word → PDF se queda en la versión de
escritorio, ya que depende de Microsoft Word/LibreOffice, que no existen en
Android.

Todo el procesamiento ocurre en el propio dispositivo: no se sube ningún
archivo a internet.

## 1. Probar en tu PC antes de compilar (recomendado)

```bash
pip install -r requirements.txt
python main.py
```

Se abrirá una ventana de escritorio con la misma interfaz que verás en el
celular. Prueba seleccionar un PDF y convertirlo antes de generar el APK —
así ahorras tiempo si algo necesita ajuste.

## 2. Compilar el APK

Buildozer **solo corre en Linux** (o WSL en Windows). Si estás en Windows,
usa WSL2 con Ubuntu.

### 2.1 Instalar Buildozer y dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3-pip build-essential git python3-dev \
    ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev \
    zlib1g-dev openjdk-17-jdk unzip

pip install --user buildozer cython
```

### 2.2 Compilar (primera vez tarda 20-40 min: descarga Android SDK/NDK)

Desde la carpeta del proyecto (donde está `buildozer.spec`):

```bash
buildozer android debug
```

El APK queda en `bin/docconvertncts-1.0.0-arm64-v8a_armeabi-v7a-debug.apk`.

### 2.3 Instalar en tu celular

Con el celular conectado por USB y depuración USB activada:

```bash
buildozer android deploy run logcat
```

O simplemente copia el `.apk` al celular y ábrelo (Android pedirá permitir
"instalar apps de fuentes desconocidas" la primera vez).

## 3. Notas importantes

- **Primera compilación**: Buildozer descarga el Android SDK/NDK completo
  (varios GB). Necesitas buena conexión e internet libre en esos dominios.
- **PyMuPDF (`fitz`) en Android**: la mayoría de las veces compila bien con
  Buildozer moderno, pero si el build falla en ese paquete específico,
  avísame el error exacto y lo resolvemos (a veces requiere fijar una
  versión distinta de PyMuPDF).
- **Permisos de almacenamiento**: en el primer arranque la app pedirá
  permiso de almacenamiento. Si el usuario lo niega, no podrá guardar los
  archivos convertidos (se le avisa en pantalla).
- **`android.api = 32`**: se fijó así a propósito para evitar la complejidad
  del "scoped storage" de Android 13+. Si más adelante quieres soportar
  versiones más nuevas con guardado más robusto, hay que migrar el guardado
  a `MediaStore`/`SAF` — es un cambio bien delimitado, avísame cuando quieras
  hacerlo.
- **Reconstruir tras cambios de código**: `buildozer android debug` de nuevo
  es suficiente (no vuelve a descargar el SDK/NDK).

## 4. Estructura del proyecto

```
DocConvertMobile/
├── main.py            # App Kivy (interfaz + flujo de conversión)
├── converter.py        # Lógica de conversión PDF->Word (pdf2docx)
├── android_utils.py    # Permisos y rutas de almacenamiento específicas de Android
├── buildozer.spec       # Configuración de compilación Android
├── requirements.txt     # Dependencias para probar en escritorio
└── assets/
    └── icon.png          # Ícono de la app
```
