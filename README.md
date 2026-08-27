# ALFRED — Asistente de voz con IA (Batcomputer Terminal)

Asistente de voz con interfaz gráfica retro-futurista en Pygame. Captura voz,
la transcribe, consulta un LLM en la nube (Gemini) con memoria de conversación,
y responde por voz. Incluye activación por palabra clave, control de funciones
del sistema, y un módulo de exploración de un modelo Transformer real.

## 1. Requisitos previos

- Python 3.10 o superior
- Windows (varias funciones de automatización usan `ctypes.windll`,
  `os.startfile`, atajos `.lnk` y `taskkill`, exclusivas de Windows)
- Micrófono y bocinas/audífonos funcionando
- Conexión a internet (para el LLM, TTS online y STT en línea; el modo
  offline con Vosk cubre solo transcripción de voz sin conexión)

## 2. Instalación

```bash
# 1. Clonar el repositorio y entrar a la carpeta
git clone <url-del-repositorio>
cd ALFRED

# 2. Crear y activar un entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux (funciones de sistema no aplicarán)

# 3. Instalar dependencias
pip install -r requirements.txt
```

Si `PyAudio` falla al instalar en Windows:
```bash
pip install pipwin
pipwin install pyaudio
```

## 3. Configurar la API Key (obligatorio)

Crea un archivo `.env` en la raíz del proyecto (este archivo **no** se sube
al repositorio, ya está en `.gitignore`):

```
GEMINI_API_KEY=tu_clave_de_google_ai_studio
```

Consigue una clave gratuita en https://aistudio.google.com/apikey

## 4. Modelo Vosk (reconocimiento de voz offline, opcional)

Para que el reconocimiento de voz funcione **sin conexión a internet**,
descarga un modelo en español de Vosk (por ejemplo `vosk-model-small-es-0.42`)
desde https://alphacephei.com/vosk/models, descomprímelo, y renombra la
carpeta a `model/` en la raíz del proyecto. Si no lo haces, ALFRED seguirá
funcionando normalmente siempre que haya internet (usa Google STT en línea).

## 5. Videos/imágenes de Alfred por modo (opcional)

La interfaz busca, en la raíz del proyecto, un video distinto por cada
estado del asistente:

```
alfred_inactivo.mp4
alfred_escuchando.mp4
alfred_procesando.mp4
alfred_hablando.mp4
```

Si falta alguno, la interfaz usa automáticamente un sprite pixel-art de
respaldo dibujado por código — no es necesario tenerlos todos para que
la app corra.

## 6. Ejecutar la aplicación

```bash
python alfred_gui.py
```

- **Clic o barra espaciadora**: activa a ALFRED manualmente.
- **Decir "Alfred" en voz alta**: lo activa por palabra clave, sin tocar
  nada (responde con un saludo tipo "Sí, señor.").
- Di "salir", "adiós", "termina" o "ciérrate" para cerrar el asistente.

## 7. Módulo de exploración del modelo (requisito obligatorio)

Muestra la tokenización y los pesos de self-attention de un modelo
Transformer real (`dccuchile/bert-base-spanish-wwm-cased`, en español),
y guarda un heatmap de atención como imagen:

```bash
python exploracion_llm.py
```

Esto imprime en consola los tokens, sus IDs, y la forma de la matriz de
atención; y genera `atencion_ultima_capa.png` en la misma carpeta con la
visualización. La primera ejecución descarga el modelo (~450MB) desde
HuggingFace, así que requiere conexión la primera vez.

Nota: este módulo usa un modelo distinto al que responde las preguntas de
ALFRED (Gemini), porque las APIs de LLMs en la nube no exponen sus pesos
de atención — el módulo demuestra la arquitectura Transformer con un
modelo real y abierto que sí los expone.

## 8. Prueba rápida de la API (opcional)

```bash
python test_ia.py
```

Verifica que la conexión con Gemini funciona correctamente.

## 9. Estructura del proyecto

```
alfred_core.py          # backend: STT, LLM, TTS, comandos de sistema, wake word
alfred_gui.py            # interfaz gráfica Pygame (HUD retro-futurista)
exploracion_llm.py        # módulo de exploración: tokenización + atención
test_ia.py                # prueba de conexión con Gemini
requirements.txt
.env                      # (no versionado) API key
chat_history.json         # (no versionado) memoria de conversación persistida
model/                    # (no versionado) modelo Vosk offline
```

## 10. Estados del sistema (visibles en la GUI)

| Estado       | Significado                                      |
|--------------|---------------------------------------------------|
| INACTIVO     | En espera de activación                            |
| ESCUCHANDO   | Capturando audio del micrófono                     |
| PROCESANDO   | Transcribiendo o consultando al LLM                |
| HABLANDO     | Reproduciendo la respuesta en voz                  |
| ERROR        | Falló el micrófono, el STT, o no hay internet       |

## 11. Limitaciones conocidas

- Las funciones de control del sistema (volumen, brillo, cerrar programas,
  abrir aplicaciones de Office) están pensadas para Windows.
- El wake word y el clic/espacio comparten el mismo micrófono; si tu
  hardware no soporta acceso concurrente, puede haber conflictos.
- El modo offline (Vosk) solo cubre STT; el LLM y el TTS en línea
  siguen requiriendo internet.
