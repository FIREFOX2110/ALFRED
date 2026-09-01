"""
Prueba rápida de conexión con la API de Gemini.
Corre este script antes de lanzar la app completa para confirmar que tu
GEMINI_API_KEY funciona y que los modelos configurados responden.
"""
import os
from dotenv import load_dotenv
from google import genai

# Apuntamos explícitamente al .env de la RAÍZ del proyecto, para que
# funcione sin importar desde qué carpeta se ejecute este script.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("[ERROR] No se encontró GEMINI_API_KEY en tu archivo .env")
    raise SystemExit(1)

client = genai.Client(api_key=api_key)

# Debe coincidir con MODEL_PRIORITY de src/llm/llm_engine.py
MODELOS_A_PROBAR = ["gemini-3.6-flash", "gemini-3.5-flash"]

for modelo in MODELOS_A_PROBAR:
    try:
        respuesta = client.models.generate_content(
            model=modelo,
            contents="Responde solo con la palabra: OK",
        )
        print(f"[OK] {modelo} respondió: {respuesta.text.strip()}")
    except Exception as e:
        print(f"[ERROR] {modelo} falló: {e}")

print("\nSi al menos un modelo respondió OK, tu API Key funciona correctamente.")