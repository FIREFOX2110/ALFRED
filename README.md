# ALFRED — Asistente de voz con IA (Batcomputer Terminal)

Asistente de voz con interfaz gráfica retro-futurista en Pygame. Captura voz,
la transcribe, consulta un LLM en la nube (Gemini) con memoria de conversación,
y responde por voz. Incluye activación por palabra clave, control de funciones
del sistema, un respaldo local con Ollama para cuando no hay internet (o la
nube está muy lenta/sin cuota), y un módulo de exploración de un modelo
Transformer real.

## 1. Requisitos previos

- Python 3.10 o superior
- Windows (varias funciones de automatización usan `ctypes.windll`,
  `os.startfile`, atajos `.lnk` y `taskkill`, exclusivas de Windows)
- Micrófono y bocinas/audífonos funcionando
- Conexión a internet (para el LLM en la nube, TTS online y STT en línea).
  Sin internet, ALFRED sigue funcionando con comandos locales, STT/TTS
  offline, y conversación vía Ollama (ver sección 5).

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

**Nota sobre cuota gratuita:** el plan gratis de Gemini tiene un límite bajo
de peticiones por día (20 para `gemini-3.6-flash` al momento de escribir
esto). Si haces muchas pruebas seguidas, es normal agotarla — el respaldo
con Ollama (sección 5) sigue funcionando aunque eso pase.

## 4. Modelo Vosk (reconocimiento de voz offline, opcional)

Para que el reconocimiento de voz funcione **sin conexión a internet**,
descarga un modelo en español de Vosk (por ejemplo `vosk-model-small-es-0.42`)
desde https://alphacephei.com/vosk/models, descomprímelo, y renombra la
carpeta a `model/` en la raíz del proyecto. Si no lo haces, ALFRED seguirá
funcionando normalmente siempre que haya internet (usa Google STT en línea).

## 5. Respaldo local con Ollama (conversación sin internet)

Gemini vive en la nube y requiere internet siempre. Para que ALFRED pueda
seguir **conversando** (no solo ejecutar comandos locales) cuando no hay
internet, o cuando la red está muy lenta/congestionada, o si se agota la
cuota gratuita de Gemini, se agregó un respaldo automático con
[Ollama](https://ollama.com), que corre un modelo de lenguaje directamente
en tu computadora.

**Instalación:**

1. Descarga e instala Ollama desde https://ollama.com/download
2. Descarga un modelo (con buena conexión, hazlo con anticipación):
   ```bash
   ollama pull llama3.1:8b
   ```
   *(El modelo configurado por defecto en `src/llm/llm_engine.py` es
   `llama3.1:8b`, pensado para equipos con al menos 4GB de VRAM y bastante
   RAM de sistema. Si tu equipo es más limitado, puedes usar un modelo más
   chico como `llama3.2` (3B) y cambiar `OLLAMA_MODEL` en ese archivo.)*
3. Verifica que responda: `ollama run llama3.1:8b`

**Cómo funciona automáticamente:** `src/llm/llm_engine.py` primero intenta
Gemini con un tiempo límite de espera; si no responde a tiempo (sin
internet, red lenta, o cuota agotada), cae solo a Ollama, sin que el
usuario tenga que hacer nada. Si tampoco Ollama está disponible, ALFRED lo
informa honestamente en vez de fingir una respuesta.

**Para pruebas:** existe un interruptor `FORZAR_SOLO_OLLAMA` en
`src/llm/llm_engine.py` que, puesto en `True`, obliga a ALFRED a usar solo
el modelo local (útil para probar sin gastar cuota de Gemini). Debe quedar
en `False` para el funcionamiento normal.

## 6. Videos/imágenes de Alfred por modo (opcional)

La interfaz busca, dentro de `assets/images/`, un video distinto por cada
estado del asistente:

```
assets/images/alfred_inactivo.mp4
assets/images/alfred_escuchando.mp4
assets/images/alfred_procesando.mp4
assets/images/alfred_hablando.mp4
assets/images/alfred_error.mp4
```

Si falta alguno, la interfaz usa automáticamente un sprite pixel-art de
respaldo dibujado por código — no es necesario tenerlos todos para que
la app corra. Las fuentes (`assets/fonts/`) siguen la misma lógica de
carpeta dedicada.

## 7. Ejecutar la aplicación

**Importante:** ejecuta el comando desde la carpeta raíz del proyecto (la
que contiene `alfred_gui.py` directamente), no desde dentro de `src/` ni
de `tests/` — si no, Python no encuentra el paquete `src` correctamente.

```bash
python alfred_gui.py
```

- **Clic o barra espaciadora**: activa a ALFRED manualmente.
- **Decir "Alfred" en voz alta**: lo activa por palabra clave, sin tocar
  nada (responde con un saludo tipo "Sí, señor.").
- Di "salir", "adiós", "termina" o "ciérrate" para cerrar el asistente.
- Di "descansa" para que vuelva a modo reposo sin cerrar el programa.

## 8. Módulo de exploración del modelo (requisito obligatorio)

Muestra la tokenización y los pesos de self-attention de un modelo
Transformer real (`dccuchile/bert-base-spanish-wwm-cased`, en español),
y guarda un heatmap de atención como imagen:

```bash
python src/exploration/exploracion_llm.py
```

Esto imprime en consola los tokens, sus IDs, y la forma de la matriz de
atención; y genera `src/exploration/output/atencion_ultima_capa.png` con
la visualización. La primera ejecución descarga el modelo (~450MB) desde
HuggingFace, así que requiere conexión la primera vez.

Nota: este módulo usa un modelo distinto al que responde las preguntas de
ALFRED (Gemini/Ollama), porque los LLMs conversacionales no exponen sus
pesos de atención de forma sencilla — el módulo demuestra la arquitectura
Transformer con un modelo real y abierto (encoder) que sí los expone.

## 9. Pruebas rápidas (opcionales)

```bash
# Verifica que la conexión con Gemini funciona correctamente
python tests/test_gemini_connection.py

# Compara respuestas de Gemini con distinta temperature/top_p
# (¡ojo!: esta prueba SÍ consume cuota real de Gemini, hasta 9 peticiones)
python tests/test_temperature_demo.py
```

## 10. Estructura del proyecto

```
alfred_gui.py              # interfaz gráfica Pygame (HUD retro-futurista) — punto de entrada
requirements.txt
README.md

src/                        # todo el código fuente del backend
├── orchestrator.py          # coordina el flujo: STT -> decisión -> LLM/comandos -> TTS
├── core/
│   ├── state.py              # estado compartido (system_state), check_internet()
│   ├── memory.py             # guarda/carga chat_history.json
│   └── utils.py               # utilidades pequeñas (fecha actual)
├── llm/
│   └── llm_engine.py         # cliente de Gemini + respaldo con Ollama
├── stt/
│   └── stt.py                 # voz a texto (Google/Vosk) + palabra de activación
├── tts/
│   └── tts.py                  # texto a voz (edge-tts/pyttsx3)
├── commands/
│   └── commands.py            # comandos locales/web que NO usan IA
└── exploration/
    ├── exploracion_llm.py      # tokenización + atención (BERT)
    └── output/                  # aquí se guarda el heatmap generado

tests/
├── test_gemini_connection.py  # prueba de conexión con Gemini
└── test_temperature_demo.py    # demo de temperature/top_p

assets/
├── fonts/                      # Orbitron, VT323
└── images/                     # videos por estado (.mp4)

.env                           # (no versionado) API key
chat_history.json               # (no versionado) memoria de conversación persistida
model/                          # (no versionado) modelo Vosk offline
venv/                           # (no versionado) entorno virtual
```

## 11. Estados del sistema (visibles en la GUI)

| Estado       | Significado                                      |
|--------------|---------------------------------------------------|
| INACTIVO     | En espera de activación                            |
| ESCUCHANDO   | Capturando audio del micrófono                     |
| PROCESANDO   | Transcribiendo o consultando al LLM                |
| HABLANDO     | Reproduciendo la respuesta en voz                  |
| ERROR        | Falló el micrófono, el STT, o no hay internet ni Ollama disponible |

## 12. Limitaciones conocidas

- Las funciones de control del sistema (volumen, brillo, cerrar programas,
  abrir aplicaciones de Office) están pensadas para Windows.
- El wake word y el clic/espacio comparten el mismo micrófono; si tu
  hardware no soporta acceso concurrente, puede haber conflictos.
- El plan gratuito de Gemini tiene un límite bajo de peticiones diarias;
  al agotarse, ALFRED sigue conversando vía Ollama, pero con menor
  capacidad que el modelo en la nube.
- El respaldo con Ollama requiere que el usuario lo instale y descargue
  un modelo por separado (sección 5); si no está instalado, ALFRED
  informa honestamente que no puede generar una respuesta conversacional
  sin internet.
- Como todo LLM, tanto Gemini como el modelo local pueden generar
  información incorrecta con aparente seguridad (alucinaciones); por eso
  ALFRED avisa al iniciar que es una IA y puede cometer errores.