"""
Demo en vivo: efecto de 'temperature' y 'top_p' sobre las respuestas de Gemini.

Uso:
    python demo_temperatura.py
"""
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Apuntamos explícitamente al .env de la RAÍZ del proyecto
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("[ERROR] No se encontró GEMINI_API_KEY en tu archivo .env")
    raise SystemExit(1)

client = genai.Client(api_key=api_key)
MODELO = "gemini-3.6-flash"  # debe coincidir con MODEL_PRIORITY de alfred_core.py

# La misma pregunta, la misma instrucción de sistema -- SOLO cambia
# temperature y top_p entre cada llamada, para que la diferencia en las
# respuestas se deba únicamente a eso.
PREGUNTA = "Dame una idea para pasar la tarde en Quito."
SYSTEM_PROMPT = "Eres ALFRED, un asistente conciso. Responde en una sola oración breve."

# Puedes editar estos tres escenarios antes de la demo si quieres otros valores
ESCENARIOS = [
    {"nombre": "BAJA  (temperature=0.1, top_p=0.5)", "temperature": 0.1, "top_p": 0.5},
    {"nombre": "MEDIA (temperature=0.3, top_p=0.9)  <- la que usa ALFRED", "temperature": 0.3, "top_p": 0.9},
    {"nombre": "ALTA  (temperature=1.2, top_p=1.0)", "temperature": 1.2, "top_p": 1.0},
]


def preguntar(temperature: float, top_p: float) -> str:
    respuesta = client.models.generate_content(
        model=MODELO,
        contents=PREGUNTA,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=temperature,
            top_p=top_p,
        ),
    )
    return respuesta.text.strip()


if __name__ == "__main__":
    print(f"Pregunta fija: '{PREGUNTA}'\n")
    print("Corremos la MISMA pregunta 3 veces cada una, cambiando solo")
    print("temperature/top_p, para ver cómo varía (o no) la respuesta.\n")

    for escenario in ESCENARIOS:
        print(f"=== {escenario['nombre']} ===")
        for intento in range(1, 4):
            try:
                texto = preguntar(escenario["temperature"], escenario["top_p"])
                print(f"  Intento {intento}: {texto}")
            except Exception as e:
                print(f"  [ERROR] {e}")
        print()

    print("Fíjate: con temperatura baja, las 3 respuestas de cada bloque suelen")
    print("parecerse mucho entre sí (el modelo casi siempre elige lo más probable).")
    print("Con temperatura alta, las 3 respuestas del mismo bloque tienden a variar")
    print("más entre sí -- el modelo se arriesga más con palabras menos probables.")