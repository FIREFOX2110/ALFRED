"""
commands.py -- comandos que NO pasan por ningún modelo de IA: control
del sistema operativo (volumen, brillo, apps), y comandos que abren
sitios/reproducen contenido en la web. Van primero en el orden de
decisión del orquestador -- solo si nada de aquí coincide, la pregunta
termina yendo al LLM (ver llm_engine.get_ai_response).
"""
import ctypes
import os
import urllib.parse
import webbrowser
from datetime import datetime

import psutil
import pyautogui
import screen_brightness_control as sbc

try:
    import pywhatkit
except Exception as e:
    print(f"[AVISO] pywhatkit no disponible (sin internet al iniciar): {e}")
    pywhatkit = None

from ..core.state import system_state, check_internet
from ..tts.tts import speak
from ..llm.llm_engine import buscar_con_ia
from ..core.utils import get_current_date_str

# =========================================================
# DIRECTORIOS Y RUTAS LOCALES (OFFLINE)
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
# COMANDOS WEB
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


# =========================================================
# COMANDOS DE HARDWARE / SISTEMA OPERATIVO
# =========================================================
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
