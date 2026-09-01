"""
tts.py -- conversión de texto a voz (Text-to-Speech), híbrida:
- online: edge-tts (voz más natural, requiere internet)
- offline: pyttsx3 (voz robótica del sistema, no requiere internet)

Requisito 5.1: "Conversión de la respuesta del LLM a voz (TTS) y
reproducción de audio."
"""
import asyncio
import io

import edge_tts
import pygame
import pyttsx3

from ..core.state import system_state, check_internet

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
