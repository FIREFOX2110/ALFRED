"""
Módulo de exploración del modelo (requisito obligatorio del proyecto).

Muestra, para una entrada de ejemplo:
  1. La tokenización (tokens + IDs numéricos).
  2. Los pesos de self-attention del modelo, con una visualización
     (heatmap) guardada como imagen PNG.

Usa un modelo Transformer real y liviano de HuggingFace en español
(dccuchile/bert-base-spanish-wwm-cased) que sí expone sus pesos de
atención vía output_attentions=True -- Gemini (usado para las
respuestas de ALFRED) no expone esto por API, por eso este módulo
es independiente y sirve como demostración educativa de la
arquitectura Transformer.
"""

import os
from transformers import AutoTokenizer, AutoModel
import torch
import matplotlib
matplotlib.use("Agg")  # backend sin ventana -> funciona también por SSH/servidor
import matplotlib.pyplot as plt

MODELO_NOMBRE = "dccuchile/bert-base-spanish-wwm-cased"
CARPETA_SALIDA = os.path.dirname(os.path.abspath(__file__))


def explorar_arquitectura(texto: str, guardar_imagen: bool = True) -> dict:
    print("=== MÓDULO DE EXPLORACIÓN: TOKENIZACIÓN Y ATENCIÓN ===\n")
    print(f"TEXTO DE ENTRADA: '{texto}'\n")

    print("[1] Cargando Tokenizer y Modelo...")
    tokenizer = AutoTokenizer.from_pretrained(MODELO_NOMBRE)
    # output_attentions=True es el requisito clave del proyecto
    model = AutoModel.from_pretrained(MODELO_NOMBRE, output_attentions=True)
    model.eval()

    # --- FASE 1: TOKENIZACIÓN ---
    print("\n--- FASE 1: TOKENIZACIÓN ---")
    tokens = tokenizer.tokenize(texto)
    ids = tokenizer.convert_tokens_to_ids(tokens)
    print(f"Tokens generados ({len(tokens)}): {tokens}")
    print(f"IDs numéricos (para la capa de embeddings): {ids}")

    # --- FASE 2: SELF-ATTENTION ---
    print("\n--- FASE 2: SELF-ATTENTION ---")
    inputs = tokenizer(texto, return_tensors="pt")
    tokens_con_especiales = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

    with torch.no_grad():
        outputs = model(**inputs)

    # attention: tupla de (num_capas) tensores, cada uno [batch, cabezales, tokens, tokens]
    attention = outputs.attentions
    num_capas = len(attention)
    num_cabezales = attention[-1].shape[1]

    print(f"Número de capas Transformer: {num_capas}")
    print(f"Cabezales de atención por capa: {num_cabezales}")
    print(f"Forma de la matriz de atención en la última capa: {tuple(attention[-1].shape)}")
    print("(Formato: [Batch, Cabezales, Tokens, Tokens])")

    ruta_imagen = None
    if guardar_imagen:
        # Promediamos todos los cabezales de la última capa -> una sola
        # matriz Tokens x Tokens fácil de visualizar como heatmap.
        ultima_capa = attention[-1][0]                # (cabezales, tokens, tokens)
        promedio_cabezales = ultima_capa.mean(dim=0).numpy()  # (tokens, tokens)

        fig, ax = plt.subplots(figsize=(6, 5.5))
        im = ax.imshow(promedio_cabezales, cmap="viridis")
        ax.set_xticks(range(len(tokens_con_especiales)))
        ax.set_yticks(range(len(tokens_con_especiales)))
        ax.set_xticklabels(tokens_con_especiales, rotation=90, fontsize=8)
        ax.set_yticklabels(tokens_con_especiales, fontsize=8)
        ax.set_title(f"Atención promedio — última capa ({num_cabezales} cabezales)")
        fig.colorbar(im, ax=ax, label="Peso de atención")
        fig.tight_layout()

        ruta_imagen = os.path.join(CARPETA_SALIDA, "atencion_ultima_capa.png")
        fig.savefig(ruta_imagen, dpi=150)
        plt.close(fig)
        print(f"\n[OK] Heatmap de atención guardado en: {ruta_imagen}")

    print("\n¡Exploración completada exitosamente!")

    return {
        "tokens": tokens,
        "ids": ids,
        "num_capas": num_capas,
        "num_cabezales": num_cabezales,
        "imagen_atencion": ruta_imagen,
    }


if __name__ == "__main__":
    texto_prueba = "Hola ALFRED, ¿qué hora es?"
    explorar_arquitectura(texto_prueba)