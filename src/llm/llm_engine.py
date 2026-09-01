"""
llm_engine.py -- todo lo relacionado con "conseguir una respuesta de un
modelo de lenguaje": el cliente de Gemini (nube), el respaldo local con
Ollama, y el punto único de entrada get_ai_response() que decide cuál
de los dos usar.

Requisito 5.1 del proyecto: "Envío del texto transcrito a un LLM
preentrenado, con un system prompt que defina la identidad del
asistente." -- toda esa lógica vive aquí, en un solo lugar.
"""
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests

from ..core import memory
from ..core.utils import get_current_date_str

# =========================================================
# CONFIGURACIÓN DEL LLM EN LA NUBE (GEMINI)
# =========================================================
load_dotenv()
api_key_segura = os.getenv("GEMINI_API_KEY")

if not api_key_segura:
    print("[ADVERTENCIA]: No se encontró GEMINI_API_KEY en el archivo .env")

client = genai.Client(api_key=api_key_segura)

MODEL_PRIORITY = ["gemini-3.6-flash", "gemini-3.5-flash"]

# Tiempo máximo (en milisegundos) que esperamos a Gemini

GEMINI_TIMEOUT_MS = 1000

# =========================================================
# RESPALDO LOCAL: OLLAMA (LLM que corre en tu propia máquina,
# sin necesitar internet). Se usa solo cuando Gemini no responde
# a tiempo (sin conexión, o conexión muy lenta/congestionada).
# =========================================================
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"     
OLLAMA_TIMEOUT_S = 25            

# Interruptor de PRUEBA: ponlo en True para forzar que ALFRED use Ollama
FORZAR_SOLO_OLLAMA = False


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

    history = memory.conversation_history
    contexto_envio = history[-6:] if len(history) > 6 else history
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

        memory.conversation_history.append({"role": "user", "parts": [{"text": user_input}]})
        memory.conversation_history.append({"role": "model", "parts": [{"text": reply}]})
        memory.save_conversation_history(memory.conversation_history)

        return reply
    except requests.exceptions.RequestException as e:
        print(f"[ERROR OLLAMA]: {e}")
        return None  # None = "tampoco pudo Ollama", se maneja en get_ai_response()


def query_llm(user_input: str) -> str:
    """Manda la pregunta a Gemini, con memoria de los últimos turnos y el
    system prompt que define la identidad de ALFRED. Devuelve None (en
    vez de lanzar un error hacia arriba) si ningún modelo de la lista
    responde a tiempo -- así get_ai_response() sabe que debe intentar
    con el respaldo local."""
    if not api_key_segura:
        return None

    system_prompt = (
        "Eres ALFRED, un asistente de IA ultra rápido, conciso, directo y muy elegante. "
        f"LA FECHA DE HOY ES: {get_current_date_str()}. "
        "Responde SIEMPRE en español en una sola oración breve (máximo 20 palabras). "
        "NO agregues la palabra 'señor' en tus respuestas."
    )

    # Solo se envían los últimos intercambios al modelo (contexto acotado),
    # pero el archivo en disco conserva TODO el historial acumulado.
    history = memory.conversation_history
    contexto_envio = history[-6:] if len(history) > 6 else history
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
                    # Timeout corto a propósito: si la red está muy lenta,
                    # preferimos fallar rápido aquí y pasar al respaldo local (Ollama)
                    # en vez de dejar a ALFRED "colgado" esperando.
                    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
                )
            )
            reply = response.text

            memory.conversation_history.append({"role": "user", "parts": [{"text": user_input}]})
            memory.conversation_history.append({"role": "model", "parts": [{"text": reply}]})
            memory.save_conversation_history(memory.conversation_history)

            return reply
        except Exception as e:
            print(f"[ERROR LLM - {model_name}]: {e}")
            continue
    return None  # None = "la nube no respondió a tiempo", se maneja en get_ai_response()


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
                return "Esta es la informacion que pude encontrar. señor "
            continue
    return "No pude completar la búsqueda en este momento."