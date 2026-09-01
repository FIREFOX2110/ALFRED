"""
state.py -- estado global compartido por toda la aplicación:
- system_state: lo que la GUI (alfred_gui.py) lee para pintar la pantalla
- los "semáforos" de threading que coordinan quién tiene el micrófono
- check_internet(): la única función que decide si hay conexión

Se deja aislado en su propio módulo porque casi todos los demás
módulos (tts, stt, commands, el orquestador) necesitan leer o
modificar este mismo estado compartido.
"""
import os
import socket
import time
import threading

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

# Ruta absoluta a la carpeta RAÍZ del proyecto (tres niveles arriba de
# este archivo: src/core/state.py -> src/core -> src -> ALFRED/). Aunque
# este archivo vive anidado, chat_history.json y la carpeta model/ deben
# seguir guardándose en la raíz del proyecto, junto a alfred_gui.py.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
