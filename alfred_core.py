import asyncio
import io
import json
import os
import random
import socket
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
import ctypes
import psutil

import speech_recognition as sr
import edge_tts
import pygame
import pyttsx3
from google import genai
from google.genai import types
try:
    import pywhatkit
except Exception as e:
    print(f"[AVISO] pywhatkit no disponible (sin internet al iniciar): {e}")
    pywhatkit = None
import pyautogui
import screen_brightness_control as sbc

# Vosk cargado directamente, sin depender de dónde busque
# SpeechRecognition internamente (esto varía entre versiones de la
# librería y fue la causa del error "Vosk model not found").
from vosk import Model as VoskModel, KaldiRecognizer

from dotenv import load_dotenv

# =========================================================
# 1. ESTADO GLOBAL Y COMPROBACIÓN DE RED
# =========================================================
system_state = {
    "status": "INICIALIZANDO",
    "user_text": "",
    "alfred_text": "Iniciando sistemas de la Baticueva..."
}

listen_trigger = threading.Event()
_vino_de_voz = threading.Event()  # marca si la activación fue por palabra clave, no por clic/espacio

# modo_reposo controla quién tiene derecho al micrófono: mientras está
# activo (set), el wake_word_loop escucha por "Alfred"; cuando ALFRED
# despierta se limpia, y el bucle de atención activa tiene el micrófono
# para sí sin que el wake_word_loop interfiera. Es independiente del
# campo "status" (que es solo para mostrar en la GUI), así evitamos que
# un simple ESCUCHANDO/HABLANDO/PROCESANDO reactive el wake word a medias.
modo_reposo = threading.Event()
modo_reposo.set()


def check_internet(host="8.8.8.8", port=53, timeout=2) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False


def trigger_listening():
    """Activación manual: clic o barra espaciadora. No dispara saludo de voz."""
    if modo_reposo.is_set():
        _vino_de_voz.clear()
        modo_reposo.clear()
        listen_trigger.set()


def _marcar_error(mensaje: str, segundos: float = 1.5):
    """Pone el sistema en estado ERROR de forma visible (GUI + consola)
    antes de volver a INACTIVO en la siguiente vuelta del bucle principal."""
    system_state["status"] = "ERROR"
    system_state["alfred_text"] = f"ALFRED: {mensaje}"
    print(f"[ERROR]: {mensaje}")
    time.sleep(segundos)

# =========================================================
# 2. CONFIGURACIÓN DEL LLM (NUBE) Y MEMORIA JSON
# =========================================================
load_dotenv()
api_key_segura = os.getenv("GEMINI_API_KEY")

if not api_key_segura:
    print("[ADVERTENCIA]: No se encontró GEMINI_API_KEY en el archivo .env")

client = genai.Client(api_key=api_key_segura)

MODEL_PRIORITY = ["gemini-3.6-flash", "gemini-3.5-flash"]

# Tiempo máximo (en milisegundos) que esperamos a Gemini antes de darlo
# por "muy lento" y pasar al respaldo local con Ollama. Con wifi saturado
# (ej. el de un salón de clases) check_internet() puede seguir devolviendo
# True aunque la respuesta tarde mucho -- este timeout es lo que nos
# protege de quedarnos "colgados" esperando en ese caso.
GEMINI_TIMEOUT_MS = 6000

# =========================================================
# 2.1 RESPALDO LOCAL: OLLAMA (LLM que corre en tu propia máquina,
#     sin necesitar internet). Se usa solo cuando Gemini no responde
#     a tiempo (sin conexión, o conexión muy lenta/congestionada).
# =========================================================
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"    # ajustado para RTX 3050 (4GB VRAM) + 32GB RAM:
                                 # no cabe completo en la GPU, pero con tanta RAM
                                 # de sobra Ollama reparte el resto ahí sin problema
OLLAMA_TIMEOUT_S = 25            # un poco más alto que con el modelo de 3B, porque
                                 # parte del modelo corre en CPU/RAM, no solo GPU


def ollama_disponible() -> bool:
    """Revisa si el servidor de Ollama está corriendo en esta máquina
    (¡ojo!: esto NO revisa internet, Ollama corre 100% local)."""
    try:
        requests.get("http://localhost:11434", timeout=1.5)
        return True
    except requests.exceptions.RequestException:
        return False


def query_ollama(user_input: str) -> str:
    """Genera una respuesta con un modelo local vía Ollama. Usa el mismo
    'espíritu' de system prompt que Gemini, para que ALFRED no cambie de
    personalidad solo porque cambió de motor por debajo."""
    system_prompt = (
        "Eres ALFRED, un asistente de IA conciso y directo. "
        f"LA FECHA DE HOY ES: {get_current_date_str()}. "
        "Responde SIEMPRE en español en una sola oración breve (máximo 20 palabras). "
        "Estás funcionando en modo local sin internet, sé breve."
    )

    # Igual que con Gemini, solo mandamos los últimos turnos -- los
    # modelos locales chicos suelen tener ventanas de contexto más
    # limitadas que Gemini en la nube.
    contexto_envio = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
    mensajes = [{"role": "system", "content": system_prompt}]
    for turno in contexto_envio:
        rol = "assistant" if turno.get("role") == "model" else "user"
        texto = turno["parts"][0]["text"]
        mensajes.append({"role": rol, "content": texto})
    mensajes.append({"role": "user", "content": user_input})

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "messages": mensajes, "stream": False},
            timeout=OLLAMA_TIMEOUT_S,
        )
        resp.raise_for_status()
        reply = resp.json()["message"]["content"].strip()

        conversation_history.append({"role": "user", "parts": [{"text": user_input}]})
        conversation_history.append({"role": "model", "parts": [{"text": reply}]})
        save_conversation_history(conversation_history)

        return reply
    except requests.exceptions.RequestException as e:
        print(f"[ERROR OLLAMA]: {e}")
        return None  # None = "tampoco pudo Ollama", se maneja arriba

# Ruta absoluta -> evita que el historial se guarde en un directorio
# distinto según desde dónde se ejecute el script.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")


def load_conversation_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[AVISO]: No se pudo leer el historial existente: {e}")
            return []
    return []


def save_conversation_history(history: list):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[ERROR GUARDANDO HISTORIAL]: {e}")


# Cargamos el historial al iniciar el sistema (así la conversación
# reciente persiste entre ejecuciones del programa).
conversation_history = load_conversation_history()
print(f"[MEMORIA] Historial cargado: {len(conversation_history)} mensajes desde {HISTORY_FILE}")


def get_current_date_str() -> str:
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
              "septiembre", "octubre", "noviembre", "diciembre"]
    now = datetime.now()
    return f"{days[now.weekday()]}, {now.day} de {months[now.month - 1]} de {now.year}"


def query_llm(user_input: str) -> str:
    global conversation_history

    if not api_key_segura:
        return "Error: API Key de Gemini no configurada en el archivo .env."

    system_prompt = (
        "Eres ALFRED, un asistente de IA ultra rápido, conciso, directo y muy elegante. "
        f"LA FECHA DE HOY ES: {get_current_date_str()}. "
        "Responde SIEMPRE en español en una sola oración breve (máximo 20 palabras). "
        "NO agregues la palabra 'señor' en tus respuestas."
    )

    # Solo se envían los últimos intercambios al modelo (contexto acotado),
    # pero el archivo en disco conserva TODO el historial acumulado.
    contexto_envio = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
    contents = list(contexto_envio)
    contents.append({"role": "user", "parts": [{"text": user_input}]})

    for model_name in MODEL_PRIORITY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    # Timeout corto a propósito: si la red está muy lenta
                    # (ej. wifi saturado de un salón de clases), preferimos
                    # fallar rápido aquí y pasar al respaldo local (Ollama)
                    # en vez de dejar a ALFRED "colgado" esperando.
                    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
                )
            )
            reply = response.text

            conversation_history.append({"role": "user", "parts": [{"text": user_input}]})
            conversation_history.append({"role": "model", "parts": [{"text": reply}]})
            save_conversation_history(conversation_history)

            return reply
        except Exception as e:
            print(f"[ERROR LLM - {model_name}]: {e}")
            continue
    return None  # None = "la nube no respondió a tiempo", se maneja en get_ai_response()


# Interruptor de PRUEBA: ponlo en True para forzar que ALFRED use
# SOLO Ollama (ignora Gemini por completo), sin necesidad de apagar
# el wifi. Déjalo en False para el funcionamiento normal.
FORZAR_SOLO_OLLAMA = False


def get_ai_response(user_input: str) -> str:
    """Punto único de entrada para conseguir una respuesta conversacional:
    1) intenta Gemini en la nube (rápido y más capaz),
    2) si no responde a tiempo (sin internet, o internet muy lento/
       congestionado), cae a Ollama corriendo localmente,
    3) si ninguno de los dos funciona, lo dice honestamente en vez
       de fingir una respuesta o quedarse en silencio."""
    if api_key_segura and not FORZAR_SOLO_OLLAMA:
        reply = query_llm(user_input)
        if reply:
            return reply
        print("[INFO] Gemini no respondió a tiempo, probando respaldo local (Ollama)...")
    elif FORZAR_SOLO_OLLAMA:
        print("[INFO] FORZAR_SOLO_OLLAMA está activo: se omite Gemini a propósito.")

    if ollama_disponible():
        reply = query_ollama(user_input)
        if reply:
            return reply

    return "No pude conectar ni con la nube ni con el modelo local. Revisa tu conexión o que Ollama esté corriendo."


def buscar_con_ia(consulta: str) -> str:
    """Busca en internet usando la herramienta de Búsqueda de Google
    integrada de Gemini (grounding) y devuelve un resumen hablado,
    como el 'modo IA' de un buscador. No usa ni guarda el historial
    de conversación -- es una consulta puntual, no un turno de charla."""
    if not api_key_segura:
        return "No puedo buscar en internet: falta la API Key de Gemini."

    system_prompt_busqueda = (
        "Eres ALFRED. Te acaban de pedir una búsqueda en internet. "
        "Resume en español, en máximo 3 oraciones breves, la información "
        "más relevante y actualizada que encuentres. Sé directo, sin "
        "rodeos ni disculpas."
    )

    for model_name in MODEL_PRIORITY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=consulta,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt_busqueda,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                ),
            )
            return response.text
        except Exception as e:
            mensaje_error = str(e)
            print(f"[ERROR BÚSQUEDA IA - {model_name}]: {mensaje_error}")
            if "RESOURCE_EXHAUSTED" in mensaje_error or "429" in mensaje_error:
                # La cuota de búsqueda con IA (grounding) se comparte entre
                # modelos -- si ya se agotó, seguir probando el siguiente
                # modelo casi siempre falla igual, así que se corta aquí
                # en vez de esperar el segundo error.
                return "Se agotó mi cuota de búsquedas con IA por ahora. Intenta más tarde."
            continue
    return "No pude completar la búsqueda en este momento."

# =========================================================
# 3. DIRECTORIOS Y RUTAS LOCALES (OFFLINE)
# =========================================================
USER_HOME = os.path.expanduser('~')

APP_COMMANDS = {
    "word": "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Word.lnk",
    "excel": "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Excel.lnk",
    "powerpoint": "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\PowerPoint.lnk",
    "calculadora": "calc",
    "bloc de notas": "notepad",
    "notas": "notepad",
    "explorador": "explorer",
    "carpetas": "explorer",
    "descargas": os.path.join(USER_HOME, "Downloads"),
    "documentos": os.path.join(USER_HOME, "Documents"),
    "imágenes": os.path.join(USER_HOME, "Pictures")
}

WEB_URLS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "whatsapp web": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com"
}

# =========================================================
# 4. MANEJO DE COMANDOS LOCALES Y RED
# =========================================================
def handle_web_commands(command_text: str) -> bool:
    if pywhatkit is None or not check_internet():
        return False

    text = command_text.lower().strip()

    if "reproduce " in text or "pon " in text:
        if "en youtube" in text:
            busqueda = text.replace("reproduce ", "").replace("pon ", "").replace("en youtube", "").strip()
            speak(f"Reproduciendo {busqueda} en YouTube.")
            pywhatkit.playonyt(busqueda)
            return True
        elif "en spotify" in text:
            busqueda = text.replace("reproduce ", "").replace("pon ", "").replace("en spotify", "").strip()
            speak(f"Buscando {busqueda} en Spotify.")
            query = urllib.parse.quote(busqueda)
            # Abre la búsqueda en Spotify Web. No hay forma de reproducir
            # automáticamente sin autenticar al usuario (OAuth de la API
            # oficial de Spotify) -- esto abre los resultados y el usuario
            # solo tiene que darle play.
            webbrowser.open(f"https://open.spotify.com/search/{query}")
            return True

    if "abre " in text or "abrir " in text:
        target = text.replace("abre ", "").replace("abrir ", "").replace("el ", "").replace("la ", "").replace("página ", "").strip()
        if target in WEB_URLS:
            speak(f"Abriendo {target}.")
            webbrowser.open(WEB_URLS[target])
            return True

    # Búsqueda genérica en el navegador: "busca X" / "buscar X" / "búscame X"
    # Cubre cualquier consulta libre -- cartelera de cine, hoteles, clima
    # de un lugar, lo que sea -- sin necesidad de mapear cada caso a mano.
    disparadores_busqueda = ["busca ", "buscar ", "búscame ", "investiga "]
    for disparador in disparadores_busqueda:
        if text.startswith(disparador) or f" {disparador}" in text:
            consulta = text.split(disparador, 1)[1].strip() if disparador in text else ""
            if consulta:
                query = urllib.parse.quote(consulta)
                webbrowser.open(f"https://www.google.com/search?q={query}")

                system_state["status"] = "PROCESANDO"
                resumen = buscar_con_ia(consulta)
                speak(resumen)
                return True

    return False


def ejecutar_comando_sistema(comando: str) -> str:
    comando = comando.lower().strip()

    if "sube el volumen" in comando or "subir volumen" in comando:
        pyautogui.press('volumeup', presses=5)
        return "Volumen incrementado."
    elif "baja el volumen" in comando or "bajar volumen" in comando:
        pyautogui.press('volumedown', presses=5)
        return "Volumen reducido."
    elif "muteate" in comando or "silenciar" in comando:
        pyautogui.press('volumemute')
        return "Sistema silenciado."

    elif "sube el brillo" in comando or "subir brillo" in comando:
        try:
            sbc.set_brightness('+15')
            return "Brillo aumentado."
        except Exception:
            return "No pude ajustar el brillo."
    elif "baja el brillo" in comando or "bajar brillo" in comando:
        try:
            sbc.set_brightness('-15')
            return "Brillo reducido."
        except Exception:
            return "No pude ajustar el brillo."

    elif "suspender" in comando or "suspende" in comando:
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Entrando en modo suspensión."

    elif "bloquear pantalla" in comando or "bloquea la pantalla" in comando or "bloquea el equipo" in comando:
        ctypes.windll.user32.LockWorkStation()
        return "Pantalla bloqueada."

    elif "pausar música" in comando or "reproducir música" in comando or "pausa" in comando:
        pyautogui.press('playpause')
        return "Comando multimedia ejecutado."
    elif "siguiente canción" in comando:
        pyautogui.press('nexttrack')
        return "Siguiente pista."
    elif "canción anterior" in comando:
        pyautogui.press('prevtrack')
        return "Pista anterior."

    elif "mostrar escritorio" in comando or "minimizar todo" in comando or "minimiza todo" in comando:
        pyautogui.hotkey('win', 'd')
        return "Mostrando el escritorio."

    elif "captura de pantalla" in comando or "tomar captura" in comando:
        pictures_dir = os.path.join(USER_HOME, "Pictures")
        if not os.path.exists(pictures_dir):
            os.makedirs(pictures_dir)
        filename = f"Captura_ALFRED_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(pictures_dir, filename)
        pyautogui.screenshot(filepath)
        return "Captura de pantalla guardada en Imágenes."

    elif "batería" in comando or "cuánta carga" in comando:
        battery = psutil.sensors_battery()
        if battery:
            estado = "conectado a la corriente" if battery.power_plugged else "usando batería"
            return f"El nivel de batería es del {battery.percent} por ciento, {estado}."
        return "No pude leer el sensor de batería."

    elif comando.startswith("cerrar "):
        programa = comando.replace("cerrar ", "").strip()
        ejecutables = {
            "chrome": "chrome.exe",
            "excel": "excel.exe",
            "word": "winword.exe",
            "powerpoint": "powerpnt.exe",
            "power point": "powerpnt.exe",
            "bloc de notas": "notepad.exe",
            "notas": "notepad.exe",
            "calculadora": "CalculatorApp.exe"
        }
        nombre_exe = ejecutables.get(programa, f"{programa}.exe")
        resultado = os.system(f"taskkill /IM {nombre_exe} /F >nul 2>&1")
        if resultado != 0 and programa == "calculadora":
            resultado = os.system("taskkill /IM calc.exe /F >nul 2>&1")

        if resultado == 0:
            return f"{programa.capitalize()} cerrado."
        return f"No encontré {programa} en ejecución."

    return None


def launch_app(target: str) -> bool:
    executable = APP_COMMANDS.get(target, target)
    try:
        if os.path.isdir(executable):
            os.system(f'explorer "{executable}"')
        else:
            os.startfile(executable)
        return True
    except Exception:
        return False


def handle_local_commands(command_text: str) -> bool:
    text = command_text.lower().strip()

    if "día es hoy" in text or "fecha es" in text:
        speak(f"Hoy es {get_current_date_str()}.")
        return True
    if "hora es" in text or "qué hora" in text:
        speak(f"Son las {datetime.now().strftime('%H:%M')}.")
        return True

    if "abre " in text or "abrir " in text:
        target = text.replace("abre ", "").replace("abrir ", "").replace("el ", "").replace("la ", "").replace("carpeta ", "").strip()
        if launch_app(target):
            speak(f"Abriendo {target}.")
            return True

    return False

# =========================================================
# 5. AUDIO HÍBRIDO (ONLINE / OFFLINE)
# =========================================================
VOICE_NAME = "es-ES-AlvaroNeural"


def speak_offline(text: str):
    engine = pyttsx3.init()
    engine.setProperty('rate', 170)
    engine.say(text)
    engine.runAndWait()


async def get_audio_bytes(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE_NAME, rate="+5%")
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


async def speak_async(text: str):
    audio_data = await get_audio_bytes(text)
    audio_stream = io.BytesIO(audio_data)

    pygame.mixer.init()
    pygame.mixer.music.load(audio_stream)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.02)
    pygame.mixer.quit()


def speak(text: str):
    system_state["status"] = "HABLANDO"
    system_state["alfred_text"] = f"ALFRED: {text}"
    print(f"ALFRED: {text}")

    if check_internet():
        try:
            asyncio.run(speak_async(text))
        except Exception:
            speak_offline(text)
    else:
        speak_offline(text)

    system_state["status"] = "INACTIVO"


# =========================================================
# 5.1 RECONOCIMIENTO OFFLINE CON VOSK (carga manual y directa)
# =========================================================
# Usamos el paquete `vosk` directamente en vez de
# `recognizer.recognize_vosk(...)` de SpeechRecognition. La razón es que
# distintas versiones de SpeechRecognition buscan el modelo en lugares
# distintos (algunas dentro de site-packages/speech_recognition/models/vosk,
# no en la carpeta del proyecto), lo que provocaba el error
# "Vosk model not found" aunque el modelo sí existiera en model/.
# Cargando el modelo nosotros mismos, la ruta siempre es la misma
# (la carpeta model/ junto a este archivo) sin importar la versión
# de la librería instalada.
VOSK_MODEL_PATH = os.path.join(BASE_DIR, "model")
_vosk_model = None
_vosk_model_error = None


def _get_vosk_model():
    """Carga el modelo Vosk una sola vez (es pesado) y lo reutiliza."""
    global _vosk_model, _vosk_model_error
    if _vosk_model is not None:
        return _vosk_model
    if _vosk_model_error is not None:
        # Ya sabemos que falta el modelo; no reintentamos en cada llamada.
        raise _vosk_model_error
    if not os.path.isdir(VOSK_MODEL_PATH):
        _vosk_model_error = RuntimeError(
            f"No se encontró la carpeta del modelo Vosk en: {VOSK_MODEL_PATH}. "
            "Descárgalo desde https://alphacephei.com/vosk/models "
            "(por ejemplo vosk-model-small-es-0.42), descomprímelo y "
            "renombra la carpeta resultante a 'model'."
        )
        raise _vosk_model_error
    try:
        _vosk_model = VoskModel(VOSK_MODEL_PATH)
        return _vosk_model
    except Exception as e:
        _vosk_model_error = e
        raise


def recognize_vosk_local(audio: "sr.AudioData") -> str:
    """Transcribe un AudioData de SpeechRecognition usando Vosk directamente,
    sin pasar por recognizer.recognize_vosk()."""
    model = _get_vosk_model()
    raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
    rec = KaldiRecognizer(model, 16000)
    rec.AcceptWaveform(raw_data)
    resultado = json.loads(rec.FinalResult())
    return resultado.get("text", "").strip()


# --- CORREGIDO: escucha más paciente para no cortar la frase ---
# Antes:
#   recognizer.pause_threshold = 0.8
#   audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
# Con eso, cualquier pausa natural de más de 0.8s (para pensar, respirar,
# etc.) cortaba la grabación, y además nunca se podía hablar más de
# 10 segundos seguidos sin que se cortara a la fuerza.
#
# Ahora:
# - pause_threshold sube a 1.6s: da más margen antes de asumir que
#   terminaste de hablar.
# - phrase_time_limit se quita (None): ya no hay un tope de duración fijo;
#   solo corta cuando de verdad dejas de hablar por pause_threshold
#   segundos seguidos.
# - non_speaking_duration se ajusta junto con pause_threshold para que
#   el margen de silencio capturado al final de la frase sea consistente.
def listen() -> str:
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.6
    recognizer.non_speaking_duration = 1.0

    audio = None
    try:
        with sr.Microphone() as source:
            system_state["status"] = "ESCUCHANDO"
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=None)
    except sr.WaitTimeoutError:
        _marcar_error("No escuché nada. Inténtalo de nuevo.")
        return ""
    except Exception as e:
        # Cubre cualquier fallo al abrir/usar el micrófono (dispositivo
        # ocupado, desconectado, permisos, etc.), no solo el timeout.
        _marcar_error("Problema con el micrófono.")
        print(f"[ERROR MICRÓFONO]: {e}")
        return ""

    system_state["status"] = "PROCESANDO"
    text = ""
    try:
        if check_internet():
            text = recognizer.recognize_google(audio, language="es-ES")
        else:
            try:
                text = recognize_vosk_local(audio)
            except Exception as e:
                print(f"[AVISO VOSK]: Reconocimiento offline falló. ¿Descargaste el modelo Vosk?\nError: {e}")
                _marcar_error("No pude reconocer el audio sin conexión.")
                return ""
    except sr.UnknownValueError:
        _marcar_error("No entendí lo que dijiste.")
        return ""
    except sr.RequestError as e:
        print(f"[ERROR STT]: {e}")
        _marcar_error("Falló el servicio de reconocimiento de voz.")
        return ""

    if not text:
        _marcar_error("No detecté ninguna palabra.")
        return ""

    system_state["user_text"] = f"Tú: {text}"
    print(f"Tú: {text}")  # para seguir viendo en la terminal lo que se reconoce
    return text

# =========================================================
# 6. ACTIVACIÓN POR PALABRA CLAVE ("ALFRED")
# =========================================================
WAKE_WORDS = ["alfred", "alfredo", "oye alfred"]
FRASES_ACTIVACION = [
    "Sí, señor.",
    "Dígame, señor.",
    "¿En qué puedo ayudarle?",
    "A sus órdenes.",
    "Le escucho.",
]


def _contiene_wake_word(texto: str) -> bool:
    texto = texto.lower()
    return any(w in texto for w in WAKE_WORDS)


FRASES_DESCANSO_TRIGGER = [
    "descansa", "ve a descansar", "vete a descansar", "puedes descansar",
    "ponte a descansar", "duérmete", "duerme", "vete a dormir", "a dormir",
]
FRASES_DESCANSO_RESPUESTA = [
    "Entendido, quedo en reposo.",
    "De acuerdo, me pongo a descansar.",
    "Como diga, en reposo.",
    "Muy bien, aquí estaré si me necesita.",
]


def _contiene_frase_descanso(texto: str) -> bool:
    texto = texto.lower()
    return any(f in texto for f in FRASES_DESCANSO_TRIGGER)


def wake_word_loop():
    """Escucha en segundo plano mientras ALFRED está en reposo, esperando
    que se diga su nombre para activarse por voz (sin clic ni espacio).
    Se pausa por completo mientras ALFRED está despierto/activo."""
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.6

    while True:
        if not modo_reposo.is_set():
            threading.Event().wait(0.25)
            continue
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
        except Exception:
            continue

        if not modo_reposo.is_set():
            continue  # se activó por clic/espacio mientras escuchábamos

        try:
            texto = recognizer.recognize_google(audio, language="es-ES")
        except Exception:
            continue

        if texto and _contiene_wake_word(texto):
            modo_reposo.clear()
            _vino_de_voz.set()
            listen_trigger.set()

# =========================================================
# 7. ORQUESTADOR PRINCIPAL
# =========================================================
EXIT_COMMANDS = ["salir", "adiós", "termina", "ciérrate"]


def atender_activo():
    """Mientras ALFRED está despierto, el micrófono escucha en bucle
    continuo -- no vuelve a reposo entre un comando y el siguiente.
    Solo regresa (a reposo) cuando se pide explícitamente que descanse,
    o el programa termina por completo con un comando de salida."""
    while True:
        try:
            user_text = listen()

            if not user_text:
                # silencio, timeout o error de reconocimiento: seguimos
                # despiertos y escuchando, sin pedir la palabra clave de nuevo
                continue

            text_lower = user_text.lower()

            if any(cmd in text_lower for cmd in EXIT_COMMANDS):
                speak("Desconectando sistemas.")
                os._exit(0)

            if _contiene_frase_descanso(text_lower):
                speak(random.choice(FRASES_DESCANSO_RESPUESTA))
                return  # vuelve a reposo -> el llamador reactiva el wake word

            hw_response = ejecutar_comando_sistema(text_lower)
            if hw_response:
                speak(hw_response)
                continue

            if handle_local_commands(text_lower):
                continue

            if handle_web_commands(text_lower):
                continue

            # Ya NO se dice ninguna frase de relleno mientras se busca/procesa:
            # se piensa en silencio y solo se habla la respuesta final.
            # get_ai_response() decide por su cuenta si usa Gemini (nube) o
            # cae a Ollama (local) -- atender_activo() ya no necesita saber
            # ese detalle, solo pide "una respuesta" y confía en el resultado.
            if check_internet() or ollama_disponible():
                system_state["status"] = "PROCESANDO"
                response_text = get_ai_response(user_text)
                if response_text.startswith("No pude conectar"):
                    system_state["status"] = "ERROR"
                    time.sleep(0.8)
                speak(response_text)
            else:
                system_state["status"] = "ERROR"
                system_state["alfred_text"] = "ALFRED: Sin conexión a internet ni modelo local disponible."
                time.sleep(0.8)
                speak("Modo sin conexión. Solo ejecuto comandos locales.")
        except Exception as e:
            # Red de seguridad: cualquier error no previsto en esta vuelta
            # (micrófono, red, lo que sea) queda registrado en consola, pero
            # ALFRED sigue despierto y escuchando en la siguiente vuelta en
            # vez de morir en silencio.
            print(f"[ERROR INESPERADO EN atender_activo]: {e}")
            _marcar_error("Ocurrió un problema inesperado. Sigo en línea.")


def main_loop():
    # Aviso ético (requisito del proyecto, sección 11 del PDF): el usuario
    # debe saber que interactúa con una IA y que puede cometer errores.
    speak(
        "Sistemas inicializados. Soy una inteligencia artificial y puedo "
        "cometer errores. En espera de activación."
    )

    while True:
        try:
            system_state["status"] = "INACTIVO"
            listen_trigger.wait()
            listen_trigger.clear()

            if _vino_de_voz.is_set():
                _vino_de_voz.clear()
                speak(random.choice(FRASES_ACTIVACION))

            atender_activo()

            # atender_activo() solo retorna cuando se pidió "descansa" ->
            # ahora sí volvemos a reposo y el wake_word_loop se reactiva.
            modo_reposo.set()
        except Exception as e:
            print(f"[ERROR INESPERADO EN main_loop]: {e}")
            _marcar_error("Ocurrió un problema inesperado. Sigo en línea.")
            modo_reposo.set()


def start_backend():
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=wake_word_loop, daemon=True).start()