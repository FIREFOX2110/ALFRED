import pygame
import sys
import os
import math
import datetime
import alfred_core

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

DEBUG_VIDEO = True

WIN_W, WIN_H = 1272, 718

# ------------------------------------------------------------------
# PALETA (calcada del mockup): chasis gris cálido oscuro, pantalla
# negra, un único acento cian para todo el HUD, y una burbuja crema
# para el mensaje activo. El color de estado sustituye al cian cuando
# el modo cambia (ESCUCHANDO / PROCESANDO / HABLANDO / ERROR).
# ------------------------------------------------------------------
CHASIS = (43, 43, 45)
CHASIS_BORDE = (26, 26, 28)
PANTALLA_BG = (8, 10, 12)
PANTALLA_BORDE = (34, 36, 38)
TEXTO_BLANCO = (225, 227, 228)
TEXTO_TENUE = (120, 150, 150)
BARRA_FONDO = (18, 30, 32)
CREMA = (228, 220, 198)
CREMA_TEXTO = (24, 24, 20)

CIAN = (46, 224, 214)
STATUS_COLORS = {
    "INACTIVO": (46, 224, 214),
    "ESCUCHANDO": (224, 180, 46),
    "PROCESANDO": (170, 110, 224),
    "HABLANDO": (70, 210, 130),
    "ERROR": (224, 70, 80),
}
STATUS_LABELS = {
    "INACTIVO": "EN ESPERA",
    "ESCUCHANDO": "ESCUCHANDO",
    "PROCESANDO": "PROCESANDO",
    "HABLANDO": "HABLANDO",
    "ERROR": "ERROR",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_PATHS = {
    "INACTIVO": os.path.join(BASE_DIR, "images/alfred_inactivo.mp4"),
    "ESCUCHANDO": os.path.join(BASE_DIR, "images/alfred_escuchando.mp4"),
    "PROCESANDO": os.path.join(BASE_DIR, "images/alfred_procesando.mp4"),
    "HABLANDO": os.path.join(BASE_DIR, "images/alfred_hablando.mp4"),
}
FUENTE_TERMINAL = os.path.join(BASE_DIR, "VT323-Regular.ttf")
FUENTE_TITULO = os.path.join(BASE_DIR, "Orbitron-VariableFont.ttf")

MAX_HISTORIAL = 40


def fuente_terminal(size):
    if os.path.exists(FUENTE_TERMINAL):
        return pygame.font.Font(FUENTE_TERMINAL, int(size * 1.35))
    return pygame.font.SysFont("couriernew", size, bold=True)


def fuente_titulo(size):
    if os.path.exists(FUENTE_TITULO):
        return pygame.font.Font(FUENTE_TITULO, size)
    return pygame.font.SysFont("couriernew", size, bold=True)


def atenuar(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def envolver_texto(texto, font, ancho_max):
    palabras = texto.split(" ")
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = (actual + " " + palabra).strip()
        if font.size(prueba)[0] <= ancho_max:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


# ------------------------------------------------------------------
# VIDEO / FALLBACK
# ------------------------------------------------------------------
class ReproductorModos:
    def __init__(self, tam):
        self.tam = tam
        self.caps = {}
        if not _CV2_OK:
            if DEBUG_VIDEO:
                print("[video] cv2 no está instalado -> usando silueta de respaldo")
            return
        for modo, ruta in VIDEO_PATHS.items():
            if not os.path.exists(ruta):
                if DEBUG_VIDEO:
                    print(f"[video] {modo}: no existe el archivo -> {ruta}")
                continue
            cap = cv2.VideoCapture(ruta)
            abierto = cap.isOpened()
            if DEBUG_VIDEO:
                print(f"[video] {modo}: {ruta} -> abierto={abierto}")
            if abierto:
                self.caps[modo] = cap

    def frame_para(self, modo):
        cap = self.caps.get(modo)
        if cap is None:
            return None
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if not ok:
                return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw = frame.shape[:2]
        tw, th = self.tam
        escala = min(tw / fw, th / fh)
        nw, nh = max(1, int(fw * escala)), max(1, int(fh * escala))
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        frame = frame.swapaxes(0, 1)
        surf = pygame.surfarray.make_surface(frame)
        lienzo = pygame.Surface(self.tam)
        lienzo.fill(PANTALLA_BG)
        lienzo.blit(surf, ((tw - nw) // 2, (th - nh) // 2))
        return lienzo

    def liberar(self):
        for cap in self.caps.values():
            cap.release()


def dibujar_silueta_fallback(surface, rect, status, color, t):
    x, y, w, h = rect
    surface.fill((10, 12, 14), rect)
    cx, cy = x + w // 2, y + int(h * 0.62)
    bob = int(math.sin(t * 2.4) * 3) if status != "INACTIVO" else 0
    silueta = (20, 21, 23)
    pygame.draw.ellipse(surface, silueta, (cx - 70, cy - 130 + bob, 140, 170))
    pygame.draw.circle(surface, silueta, (cx, cy - 150 + bob), 46)
    r = 4 + (int(3 * (math.sin(t * 6) + 1) / 2) if status == "PROCESANDO" else 0)
    pygame.draw.circle(surface, color, (cx, cy - 150 + bob), r)


def dibujar_burbuja_activa(surface, rect, texto, font, color_borde):
    """Burbuja crema con borde de color de estado y colita triangular hacia
    el video, tal como en la referencia."""
    x, y, w, h = rect
    pygame.draw.rect(surface, CREMA, (x, y, w, h), border_radius=6)
    pygame.draw.rect(surface, color_borde, (x, y, w, h), 2, border_radius=6)

    cola_x = x + w // 2
    puntos = [(cola_x - 12, y + h - 1), (cola_x + 12, y + h - 1), (cola_x, y + h + 16)]
    pygame.draw.polygon(surface, CREMA, puntos)
    pygame.draw.polygon(surface, color_borde, puntos, 2)
    pygame.draw.line(surface, CREMA, (cola_x - 11, y + h - 2), (cola_x + 11, y + h - 2), 3)

    lineas = envolver_texto(texto, font, w - 30)
    max_lineas = max(1, (h - 20) // (font.get_height() + 3))
    lineas = lineas[:max_lineas]
    ly = y + (h - len(lineas) * (font.get_height() + 3)) // 2
    for linea in lineas:
        surf = font.render(linea, True, CREMA_TEXTO)
        surface.blit(surf, (x + 16, ly))
        ly += font.get_height() + 3


def dibujar_barra_medidor(surface, rect, ratio, color):
    x, y, w, h = rect
    pygame.draw.rect(surface, BARRA_FONDO, rect, border_radius=2)
    lleno = max(0, min(w, int(w * ratio)))
    if lleno > 0:
        pygame.draw.rect(surface, color, (x, y, lleno, h), border_radius=2)


def dibujar_encabezado(surface, rect, font_marca, font_sep):
    x, y, w, h = rect
    marca = font_marca.render("ALFRED", True, TEXTO_BLANCO)
    sep = font_sep.render("·", True, TEXTO_TENUE)
    sub = font_marca.render("BATCOMPUTER TERMINAL", True, TEXTO_BLANCO)

    espacio = 22
    total_w = marca.get_width() + espacio + sep.get_width() + espacio + sub.get_width()
    cx = x + (w - total_w) // 2
    cy = y + h // 2
    surface.blit(marca, (cx, cy - marca.get_height() // 2))
    cx += marca.get_width() + espacio
    surface.blit(sep, (cx, cy - sep.get_height() // 2))
    cx += sep.get_width() + espacio
    surface.blit(sub, (cx, cy - sub.get_height() // 2))


def dibujar_panel_telemetria(surface, rect, status, color, t, historial, font_titulo, font_txt, font_chico):
    x, y, w, h = rect

    titulo = font_titulo.render("BATCOMPUTER", True, color)
    surface.blit(titulo, (x, y))

    ahora = datetime.datetime.now()
    reloj = font_titulo.render(ahora.strftime("%H:%M:%S"), True, color)
    surface.blit(reloj, (x + w - reloj.get_width(), y))

    yy = y + titulo.get_height() + 8
    label = font_txt.render(STATUS_LABELS.get(status, status), True, color)
    surface.blit(label, (x, yy))
    yy += label.get_height() + 14
    pygame.draw.line(surface, atenuar(color, 0.35), (x, yy), (x + w, yy), 1)
    yy += 20

    vals = [
        ("CPU", 0.55 + 0.15 * math.sin(t * 0.7)),
        ("MEM", 0.40 + 0.10 * math.sin(t * 0.5 + 1)),
        ("GPU", 0.30 + 0.20 * math.sin(t * 0.9 + 2)),
    ]
    for etiqueta, ratio in vals:
        lbl = font_txt.render(etiqueta, True, color)
        surface.blit(lbl, (x, yy))
        dibujar_barra_medidor(surface, (x + 70, yy + 4, w - 70, 16), max(0, min(1, ratio)), color)
        yy += 34

    yy += 6
    pygame.draw.line(surface, atenuar(color, 0.35), (x, yy), (x + w, yy), 1)
    yy += 24

    reg = font_txt.render("REGISTRO", True, color)
    surface.blit(reg, (x, yy))
    yy += reg.get_height() + 12

    area_h = h - (yy - y) - 40
    line_h = font_chico.get_height() + 6
    max_lineas = max(1, area_h // line_h)
    visibles = historial[-max_lineas:]
    for tipo, texto in visibles:
        if tipo == "usuario":
            prefijo = "TU: "
        elif tipo == "alfred":
            prefijo = "AL> "
        else:
            prefijo = "-- "
        completo = prefijo + texto
        max_chars = max(6, w // font_chico.size("A")[0])
        if len(completo) > max_chars:
            completo = completo[:max_chars - 3] + "..."
        surf = font_chico.render(completo, True, color)
        surface.blit(surf, (x, yy))
        yy += line_h

    yy = y + h - 28
    pygame.draw.line(surface, atenuar(color, 0.35), (x, yy - 12), (x + w, yy - 12), 1)
    instr = font_txt.render("ESPACIO / CLIC = HABLAR", True, color)
    surface.blit(instr, (x, yy))


def dibujar_led_power(surface, pos, t):
    pulso = (math.sin(t * 3) + 1) / 2
    pygame.draw.circle(surface, atenuar(CIAN, 0.6 + 0.4 * pulso), pos, 6)
    etiqueta = fuente_terminal(13).render("POWER", True, TEXTO_TENUE)
    surface.blit(etiqueta, (pos[0] + 16, pos[1] - etiqueta.get_height() // 2))


def dibujar_grid_puntos(surface, top_right, filas=4, cols=4, paso=13):
    x0, y0 = top_right
    for fila in range(filas):
        for col in range(cols):
            px = x0 - col * paso
            py = y0 + fila * paso
            pygame.draw.circle(surface, (70, 70, 72), (px, py), 2)


def iniciar_interfaz():
    pygame.init()
    ventana = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("ALFRED - Batcomputer Terminal")

    font_burbuja = fuente_terminal(19)
    font_marca = fuente_titulo(17)
    font_sep = fuente_titulo(20)
    font_panel_titulo = fuente_titulo(19)
    font_txt = fuente_terminal(16)
    font_chico = fuente_terminal(15)

    header_rect = pygame.Rect(0, 8, WIN_W, 48)
    pantalla_rect = pygame.Rect(36, 64, WIN_W - 72, WIN_H - 64 - 108)

    col_izq_w = int(pantalla_rect.width * 0.36)
    col_x = pantalla_rect.x + 16
    col_y = pantalla_rect.y + 16

    burbuja_h = 110
    burbuja_rect = pygame.Rect(col_x, col_y, col_izq_w, burbuja_h)
    video_rect = pygame.Rect(col_x, burbuja_rect.bottom + 24, col_izq_w,
                              pantalla_rect.bottom - 16 - (burbuja_rect.bottom + 24))

    panel_rect = pygame.Rect(col_x + col_izq_w + 38, col_y,
                              pantalla_rect.right - 16 - (col_x + col_izq_w + 38),
                              pantalla_rect.height - 32)

    reproductor = ReproductorModos((video_rect.width, video_rect.height))

    historial = [("sistema", "Sistemas inicializados. En espera de activación.")]
    ultimo_user_text = ""
    ultimo_alfred_text = ""

    clock = pygame.time.Clock()
    alfred_core.start_backend()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                alfred_core.trigger_listening()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                alfred_core.trigger_listening()

        t = pygame.time.get_ticks() / 1000.0
        status = alfred_core.system_state.get("status", "INACTIVO")
        color = STATUS_COLORS.get(status, STATUS_COLORS["INACTIVO"])
        alfred_text = alfred_core.system_state.get("alfred_text", "").replace("ALFRED: ", "")
        user_text = alfred_core.system_state.get("user_text", "")

        if user_text and user_text != ultimo_user_text:
            historial.append(("usuario", user_text))
            ultimo_user_text = user_text
        if alfred_text and alfred_text != ultimo_alfred_text:
            historial.append(("alfred", alfred_text))
            ultimo_alfred_text = alfred_text
        if len(historial) > MAX_HISTORIAL:
            historial = historial[-MAX_HISTORIAL:]

        # chasis
        ventana.fill(CHASIS_BORDE)
        pygame.draw.rect(ventana, CHASIS, (6, 6, WIN_W - 12, WIN_H - 12), border_radius=28)

        dibujar_encabezado(ventana, header_rect, font_marca, font_sep)

        # pantalla
        pygame.draw.rect(ventana, PANTALLA_BG, pantalla_rect, border_radius=14)
        pygame.draw.rect(ventana, PANTALLA_BORDE, pantalla_rect, 2, border_radius=14)

        # video
        frame = reproductor.frame_para(status)
        if frame is not None:
            ventana.blit(frame, video_rect.topleft)
        else:
            dibujar_silueta_fallback(ventana, video_rect, status, color, t)
        pygame.draw.rect(ventana, color, video_rect, 2, border_radius=6)

        # burbuja activa (último mensaje de Alfred, o el del usuario si es más reciente)
        texto_burbuja = alfred_text if alfred_text else (user_text if user_text else "En espera...")
        dibujar_burbuja_activa(ventana, burbuja_rect, texto_burbuja, font_burbuja, color)

        dibujar_panel_telemetria(ventana, panel_rect, status, color, t, historial,
                                 font_panel_titulo, font_txt, font_chico)

        dibujar_led_power(ventana, (44, WIN_H - 42), t)
        dibujar_grid_puntos(ventana, (WIN_W - 40, WIN_H - 68))

        pygame.display.flip()
        clock.tick(60)

    reproductor.liberar()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    iniciar_interfaz()
