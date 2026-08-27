import asyncio
import io
import json
import os
import random
import socket
import threading
import time
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
import pywhatkit
import pyautogui
import screen_brightness_control as sbc

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


def check_internet(host="8.8.8.8", port=53, timeout=2) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False


def trigger_listening():
    """Activación manual: clic o barra espaciadora. No dispara saludo de voz."""
    if system_state["status"] == "INACTIVO":
        _vino_de_voz.clear()
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
                    temperature=0.3
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
    return "Error al conectar con la IA en la nube."

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
    "gmail": "https://mail.google.com", 
    "spotify": "https://open.spotify.com",
    "twitter": "https://twitter.com",
    "tiktok": "https://www.tiktok.com",
    "linkedin": "https://www.linkedin.com",

}

# =========================================================
# 4. MANEJO DE COMANDOS LOCALES Y RED
# =========================================================
def handle_web_commands(command_text: str) -> bool:
    if not check_internet():
        return False

    text = command_text.lower().strip()

    if "reproduce " in text or "pon " in text:
        if "en youtube" in text:
            busqueda = text.replace("reproduce ", "").replace("pon ", "").replace("en youtube", "").strip()
            speak(f"Reproduciendo {busqueda} en YouTube.")
            pywhatkit.playonyt(busqueda)
            return True
        if "en spotify" in text:
            busqueda = text.replace("reproduce ", "").replace("pon ", "").replace("en spotify", "").strip()
            speak(f"Reproduciendo {busqueda} en Spotify.")
            pywhatkit.playonyt(busqueda)
            return True

    if "abre " in text or "abrir " in text:
        target = text.replace("abre ", "").replace("abrir ", "").replace("el ", "").replace("la ", "").replace("página ", "").strip()
        if target in WEB_URLS:
            speak(f"Abriendo {target}.")
            webbrowser.open(WEB_URLS[target])
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


def listen() -> str:
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8

    with sr.Microphone() as source:
        system_state["status"] = "ESCUCHANDO"
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            _marcar_error("No escuché nada. Inténtalo de nuevo.")
            return ""
        except Exception as e:
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
                raw_res = recognizer.recognize_vosk(audio)
                data = json.loads(raw_res) if raw_res else {}
                text = data.get("text", "")
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


def wake_word_loop():
    """Escucha en segundo plano mientras ALFRED está inactivo, esperando
    que se diga su nombre para activarse por voz (sin clic ni espacio)."""
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.6

    while True:
        if system_state["status"] != "INACTIVO":
            threading.Event().wait(0.25)
            continue
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
        except Exception:
            continue

        if system_state["status"] != "INACTIVO":
            continue  # se activó por clic/espacio mientras escuchábamos

        try:
            texto = recognizer.recognize_google(audio, language="es-ES")
        except Exception:
            continue

        if texto and _contiene_wake_word(texto):
            _vino_de_voz.set()
            listen_trigger.set()

# =========================================================
# 7. ORQUESTADOR PRINCIPAL
# =========================================================
def main_loop():
    speak("Sistemas inicializados. En espera de activación.")
    EXIT_COMMANDS = ["salir", "adiós", "termina", "ciérrate"]

    while True:
        system_state["status"] = "INACTIVO"
        listen_trigger.wait()
        listen_trigger.clear()

        if _vino_de_voz.is_set():
            _vino_de_voz.clear()
            speak(random.choice(FRASES_ACTIVACION))

        user_text = listen()

        if user_text:
            text_lower = user_text.lower()
            if any(cmd in text_lower for cmd in EXIT_COMMANDS):
                speak("Desconectando sistemas.")
                os._exit(0)

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
            if check_internet():
                system_state["status"] = "PROCESANDO"
                response_text = query_llm(user_text)
                if response_text.startswith("Error"):
                    system_state["status"] = "ERROR"
                    time.sleep(0.8)
                speak(response_text)
            else:
                system_state["status"] = "ERROR"
                system_state["alfred_text"] = "ALFRED: Sin conexión a internet."
                time.sleep(0.8)
                speak("Modo sin conexión. Solo ejecuto comandos locales.")


def start_backend():
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=wake_word_loop, daemon=True).start()