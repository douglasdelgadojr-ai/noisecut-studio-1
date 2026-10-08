# Instrucciones para Codex (o cualquier agente de código)

## Objetivo
Dejar funcionando **NoiseCut Studio**, un editor de video de escritorio (NO web) hecho con
Python + PySide6 (interfaz) + FFmpeg (procesamiento). Todo el código está en `noisecut.py`.
El usuario es hispanohablante y NO es programador: la app debe ser fácil de usar y la
entrega final debe ser un `.exe` (Windows) que abra con doble clic.

## Funciones que debe tener (ya implementadas, falta verificarlas)
- Importar video, audio e imágenes; línea de tiempo con clips reordenables (arrastrar).
- Dividir en el cabezal, duplicar, eliminar, recortar inicio/fin, cambiar velocidad.
- Brillo, contraste, saturación, desenfoque, transición de fundido.
- Texto y stickers (PNG) con posición, tamaño y color. Pista de música/audio.
- **Reducción de ruido de fondo** (la función más importante para el usuario): por clip y por
  pista de audio, filtros FFmpeg `highpass` + `afftdn`.
- Exportar a MP4 (H.264 + AAC, 1920x1080, 30 fps) con barra de progreso.

## Estado
- El motor de exportación fue probado en Linux (`python test_engine.py` -> OK).
- La interfaz (PySide6) **nunca se ha ejecutado**: puede tener errores. Es lo primero a probar.

## Pasos
1. Instalar: Python 3.9+, FFmpeg en PATH (`winget install ffmpeg` en Windows), `pip install -r requirements.txt`.
2. `python test_engine.py` debe imprimir OK.
3. `python noisecut.py`: abrir la app, importar un video, añadirlo a la línea de tiempo, mover
   ajustes, añadir texto/sticker/música, activar reducción de ruido y exportar. Corregir cualquier
   error o fallo de interfaz que aparezca.
4. Mejoras prioritarias (en este orden):
   a. Vista previa que muestre los efectos (render corto de baja resolución con FFmpeg).
   b. Botón de deshacer/rehacer y guardar/abrir proyecto (JSON).
   c. Opción de reducción de ruido con IA (filtro `arnndn` de FFmpeg con un modelo RNNoise).
   d. Textos en español claros y mensajes de error entendibles para un usuario no técnico.
5. Empaquetar a `.exe`:
   `pip install pyinstaller` y `pyinstaller --noconsole --onefile --name NoiseCutStudio noisecut.py`.
   Incluir una carpeta `ffmpeg/` (con `ffmpeg.exe` y `ffprobe.exe`) junto al .exe; la app ya la
   busca ahí primero, así el usuario no instala nada más.

## Reglas
- Mantener la interfaz en español y simple. No convertirla en app web.
- No romper `test_engine.py`; añadir pruebas si cambias `build()`.
- Al terminar, entregar el `.exe` y una guía de 5 líneas para el usuario.
