"""
memory.py -- memoria persistente de la conversación (chat_history.json).

Separado del cliente del LLM a propósito: guardar/cargar el historial
en disco no tiene nada que ver con CÓMO se genera una respuesta
(Gemini u Ollama); es una responsabilidad de almacenamiento aparte.
"""
import json
import os

from .state import BASE_DIR

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
