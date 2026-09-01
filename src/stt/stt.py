"""
stt.py -- reconocimiento de voz (Speech-to-Text), híbrido:
- online: Google Speech Recognition (más preciso, requiere internet)
- offline: Vosk (corre localmente, no requiere internet)

También vive aquí la activación por palabra clave ("Alfred"), porque
es, en el fondo, otro tipo de escucha de audio en segundo plano.

Requisito 5.1: "Captura de voz del usuario y transcripción a texto (STT)."
"""
import json
import os
import threading

import speech_recognition as sr
from vosk import Model as VoskModel, KaldiRecognizer

from ..core.state import (
    system_state, check_internet, _marcar_error, BASE_DIR,
    modo_reposo, listen_trigger, _vino_de_voz,
)

# =========================================================
# RECONOCIMIENTO OFFLINE CON VOSK (carga manual y directa)
# =========================================================
# Usamos el paquete `vosk` directamente en vez de
# `recognizer.recognize_vosk(...)` de SpeechRecognition. La razón es que
# distintas versiones de SpeechRecognition buscan el modelo en lugares
# distintos (algunas dentro de site-packages/speech_recognition/models/vosk,
# no en la carpeta del proyecto), lo que provocaba el error
# "Vosk model not found" aunque el modelo sí existiera en model/.
# Cargando el modelo nosotros mismos, la ruta siempre es la misma
# (la carpeta model/ junto al proyecto) sin importar la versión
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


# --- Escucha paciente para no cortar la frase ---
# - pause_threshold en 1.6s: da margen antes de asumir que terminaste
#   de hablar (una pausa natural para pensar/respirar no corta la frase).
# - phrase_time_limit en None: no hay tope de duración fijo; solo corta
#   cuando de verdad dejas de hablar por pause_threshold segundos seguidos.
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
# ACTIVACIÓN POR PALABRA CLAVE ("ALFRED")
# =========================================================
WAKE_WORDS = ["alfred", "alfredo", "oye alfred"]
FRASES_ACTIVACION = [
    "Sí, señor.",
    "Dígame, señor.",
    "¿En qué puedo ayudarle?",
    "A sus órdenes.",
    "Le escucho.",
]

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


def _contiene_wake_word(texto: str) -> bool:
    texto = texto.lower()
    return any(w in texto for w in WAKE_WORDS)


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
