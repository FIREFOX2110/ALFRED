"""
orchestrator.py -- ORQUESTADOR PRINCIPAL.

Este archivo ya NO contiene la implementación de STT, TTS, ni del
cliente del LLM -- esas viven cada una en su propia carpeta con nombre
específico dentro de src/ (src/core, src/llm, src/tts, src/stt,
src/commands). Aquí solo se COORDINA el flujo: escuchar -> decidir
qué hacer con lo escuchado -> responder.

alfred_gui.py importa este módulo como:
    from src import orchestrator as alfred_core
y sigue usando alfred_core.start_backend(), alfred_core.trigger_listening()
y alfred_core.system_state exactamente igual que antes -- ese alias es
lo único que cambió en alfred_gui.py, nada más.
"""
import os
import random
import threading
import time

# Re-exportados para que alfred_gui.py los siga encontrando en
# "alfred_core.system_state", "alfred_core.start_backend", etc.
from .core.state import system_state, trigger_listening, check_internet, _marcar_error, modo_reposo, listen_trigger, _vino_de_voz  # noqa: F401

from .tts.tts import speak
from .stt.stt import (
    listen, wake_word_loop,
    FRASES_ACTIVACION, FRASES_DESCANSO_RESPUESTA, _contiene_frase_descanso,
)
from .llm.llm_engine import get_ai_response, ollama_disponible
from .commands.commands import ejecutar_comando_sistema, handle_local_commands, handle_web_commands

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
