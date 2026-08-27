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

WIN_W, WIN_H = 1280, 720

# ------------------------------------------------------------------
# PALETA RETRO-FUTURISTA: azul-negro profundo + dos acentos neón que
# contrastan entre sí (cian = color "activo" por modo, magenta = acento
# fijo del chasis/HUD, independiente del estado).
# ------------------------------------------------------------------
BG_DEEP = (5, 6, 12)
BG_DEEP_2 = (10, 15, 28)
CHASIS = (24, 26, 34)
CHASIS_OSC = (14, 15, 20)
CHASIS_CLARO = (40, 44, 56)
CREMA = (225, 235, 245)
LINEA_OSC = (12, 12, 18)

ACCENT_FIJO = (225, 40, 200)          # magenta -> chasis, HUD, grid
COLOR_USUARIO = (60, 170, 255)        # acento fijo para la burbuja/registro del usuario
STATUS_COLORS = {
    "INACTIVO": (0, 225, 255),
    "ESCUCHANDO": (255, 200, 40),
    "PROCESANDO": (180, 90, 255),
    "HABLANDO": (60, 255, 170),
    "ERROR": (255, 60, 90),
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
    "INACTIVO": os.path.join(BASE_DIR, "alfred_inactivo.mp4"),
    "ESCUCHANDO": os.path.join(BASE_DIR, "alfred_escuchando.mp4"),
    "PROCESANDO": os.path.join(BASE_DIR, "alfred_procesando.mp4"),
    "HABLANDO": os.path.join(BASE_DIR, "alfred_hablando.mp4"),
}
FUENTE_TERMINAL = os.path.join(BASE_DIR, "VT323-Regular.ttf")
FUENTE_TITULO = os.path.join(BASE_DIR, "Orbitron-VariableFont.ttf")

PANTALLA_RECT = pygame.Rect(52, 78, WIN_W - 104, WIN_H - 190)
MAX_HISTORIAL = 40


def fuente_terminal(size):
    if os.path.exists(FUENTE_TERMINAL):
        return pygame.font.Font(FUENTE_TERMINAL, int(size * 1.35))
    return pygame.font.SysFont("couriernew", size)


def fuente_titulo(size):
    if os.path.exists(FUENTE_TITULO):
        return pygame.font.Font(FUENTE_TITULO, size)
    return pygame.font.SysFont("couriernew", size, bold=True)


# ------------------------------------------------------------------
# GLOW: renderiza un texto con halo de color detrás (simula bloom
# escalando una copia hacia abajo y hacia arriba -> blur barato).
# ------------------------------------------------------------------
def render_glow_text(font, texto, color_texto, color_glow, intensidad=3):
    base = font.render(texto, True, color_texto)
    w, h = base.get_size()
    lienzo = pygame.Surface((w + 24, h + 24), pygame.SRCALPHA)
    glow_src = font.render(texto, True, color_glow)
    chico = pygame.transform.smoothscale(glow_src, (max(1, w // 4), max(1, h // 4)))
    borroso = pygame.transform.smoothscale(chico, (w + 16, h + 16))
    for _ in range(intensidad):
        borroso.set_alpha(70)
        lienzo.blit(borroso, (4, 4), special_flags=pygame.BLEND_RGBA_ADD)
    lienzo.blit(base, (12, 12))
    return lienzo


class ReproductorModos:
    def __init__(self, tam):
        self.tam = tam
        self.caps = {}
        if not _CV2_OK:
            if DEBUG_VIDEO:
                print("[video] cv2 no está instalado -> usando sprite de respaldo")
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
        lienzo.fill(BG_DEEP_2)
        lienzo.blit(surf, ((tw - nw) // 2, (th - nh) // 2))
        return lienzo

    def liberar(self):
        for cap in self.caps.values():
            cap.release()


def dibujar_sprite_alfred_fallback(surface, rect, status, t):
    x, y, w, h = rect
    color = STATUS_COLORS.get(status, STATUS_COLORS["INACTIVO"])
    piel = (222, 184, 150)
    traje = (26, 26, 34)
    cx = x + w // 2
    bob = int(math.sin(t * 3) * 4) if status != "INACTIVO" else 0

    pygame.draw.rect(surface, traje, (cx - 55, y + h - 90 + bob, 110, 90))
    pygame.draw.rect(surface, piel, (cx - 40, y + h - 150 + bob, 80, 70))
    pygame.draw.rect(surface, (250, 250, 250), (cx - 40, y + h - 118 + bob, 80, 14))
    pygame.draw.rect(surface, (60, 60, 66), (cx - 46, y + h - 160 + bob, 92, 18))

    ojo_h = 6 if status != "PROCESANDO" else int(6 + 5 * (math.sin(t * 6) + 1) / 2)
    pygame.draw.rect(surface, (20, 20, 24), (cx - 22, y + h - 124 + bob, 13, ojo_h))
    pygame.draw.rect(surface, (20, 20, 24), (cx + 9, y + h - 124 + bob, 13, ojo_h))

    if status == "HABLANDO":
        boca_w = 26 + int(10 * abs(math.sin(t * 8)))
        pygame.draw.rect(surface, (120, 40, 40), (cx - boca_w // 2, y + h - 98 + bob, boca_w, 6))
    else:
        pygame.draw.rect(surface, (120, 40, 40), (cx - 13, y + h - 98 + bob, 26, 5))

    pygame.draw.rect(surface, color, (x + 8, y + 8, 14, 14))


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


def dibujar_burbuja_arcade(surface, rect, texto, font, color_borde, etiqueta=None,
                           font_etiqueta=None, cola=True, cola_dir=1):
    """Burbuja estilo arcade. etiqueta = pequeña pestaña con el nombre del hablante.
    cola_dir: 1 = colita hacia abajo (apunta al video), -1 = hacia arriba."""
    x, y, w, h = rect
    pygame.draw.rect(surface, CREMA, (x, y, w, h), border_radius=4)
    grosor = 3
    pygame.draw.rect(surface, LINEA_OSC, (x, y, w, h), grosor, border_radius=4)
    pygame.draw.rect(surface, color_borde, (x - grosor, y - grosor, w + grosor * 2, h + grosor * 2),
                      grosor, border_radius=6)

    if cola:
        cola_x = x + w // 2
        cola_ancho, cola_alto = 20, 16
        if cola_dir == 1:
            puntos = [
                (cola_x - cola_ancho // 2, y + h - 2),
                (cola_x + cola_ancho // 2, y + h - 2),
                (cola_x, y + h + cola_alto),
            ]
        else:
            puntos = [
                (cola_x - cola_ancho // 2, y + 2),
                (cola_x + cola_ancho // 2, y + 2),
                (cola_x, y - cola_alto),
            ]
        pygame.draw.polygon(surface, CREMA, puntos)
        pygame.draw.polygon(surface, LINEA_OSC, puntos, 2)

    # pestaña con el nombre del hablante, sobre el borde superior izquierdo
    if etiqueta and font_etiqueta:
        tag_surf = font_etiqueta.render(etiqueta, True, (12, 12, 16))
        tag_w, tag_h = tag_surf.get_width() + 14, tag_surf.get_height() + 6
        tag_rect = (x + 10, y - tag_h // 2, tag_w, tag_h)
        pygame.draw.rect(surface, color_borde, tag_rect, border_radius=4)
        pygame.draw.rect(surface, LINEA_OSC, tag_rect, 2, border_radius=4)
        surface.blit(tag_surf, (tag_rect[0] + 7, tag_rect[1] + 3))

    lineas = envolver_texto(texto, font, w - 28)
    max_lineas = max(1, (h - 16) // (font.get_height() + 3))
    lineas = lineas[:max_lineas]
    ly = y + 10
    for linea in lineas:
        txt_surf = font.render(linea, True, (18, 18, 26))
        surface.blit(txt_surf, (x + 14, ly))
        ly += font.get_height() + 3


# ------------------------------------------------------------------
# CUADRÍCULA DE HORIZONTE (perspectiva tipo synthwave) de fondo
# ------------------------------------------------------------------
def dibujar_grid_horizonte(surface, rect, color, t):
    x, y, w, h = rect
    fuga = (x + w // 2, y + int(h * 0.05))
    n_horiz = 9
    for i in range(1, n_horiz + 1):
        frac = (i / n_horiz) ** 2
        ly = fuga[1] + (h - fuga[1] + y) * frac
        medio_ancho = (w / 2) * frac
        alpha = int(120 * (1 - frac) + 20)
        col = (*color, max(10, alpha))
        superficie = pygame.Surface((w, 1), pygame.SRCALPHA)
        pygame.draw.line(superficie, col, (fuga[0] - medio_ancho - x, 0), (fuga[0] + medio_ancho - x, 0))
        surface.blit(superficie, (x, int(ly)))

    n_radial = 7
    for i in range(n_radial + 1):
        frac = i / n_radial
        bx = x + w * frac
        alpha = 55
        col = (*color, alpha)
        superficie = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.line(superficie, col, (fuga[0] - x, fuga[1] - y), (bx - x, h))
        surface.blit(superficie, (x, y))


def dibujar_anillo_radar(surface, center, radio, color, t):
    n = 28
    for i in range(n):
        if i % 2 == 0:
            continue
        a0 = t * 0.6 + (i / n) * 2 * math.pi
        a1 = t * 0.6 + ((i + 0.65) / n) * 2 * math.pi
        p0 = (center[0] + radio * math.cos(a0), center[1] + radio * math.sin(a0))
        p1 = (center[0] + radio * math.cos(a1), center[1] + radio * math.sin(a1))
        pygame.draw.line(surface, color, p0, p1, 2)
    ang_punto = t * 0.6
    punto = (center[0] + radio * math.cos(ang_punto), center[1] + radio * math.sin(ang_punto))
    pygame.draw.circle(surface, color, punto, 4)


def dibujar_hex_pulsante(surface, center, radio, color, t):
    puntos = []
    for i in range(6):
        ang = math.pi / 3 * i - math.pi / 2
        puntos.append((center[0] + radio * math.cos(ang), center[1] + radio * math.sin(ang)))
    pulso = (math.sin(t * 5) + 1) / 2
    pygame.draw.polygon(surface, color, puntos, 2)
    interior = [(center[0] + (px - center[0]) * 0.5, center[1] + (py - center[1]) * 0.5) for px, py in puntos]
    alpha_col = tuple(int(c * (0.3 + 0.5 * pulso)) for c in color)
    pygame.draw.polygon(surface, alpha_col, interior)


def dibujar_corchetes_hud(surface, rect, color, tam=26, grosor=3):
    x, y, w, h = rect
    esquinas = [
        (x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)
    ]
    for ex, ey, dx, dy in esquinas:
        pygame.draw.line(surface, color, (ex, ey), (ex + dx * tam, ey), grosor)
        pygame.draw.line(surface, color, (ex, ey), (ex, ey + dy * tam), grosor)


def dibujar_mueble_computadora(surface, color_estado, t, font_marca):
    surface.fill(BG_DEEP)
    pygame.draw.rect(surface, CHASIS, (0, 0, WIN_W, WIN_H))
    pygame.draw.rect(surface, CHASIS_OSC, (0, 0, WIN_W, WIN_H), 10, border_radius=22)
    pygame.draw.rect(surface, CHASIS_CLARO, (6, 6, WIN_W - 12, WIN_H - 12), 2, border_radius=20)

    # filo de neón fino en el borde del bisel (magenta fijo, no cambia con el modo)
    pygame.draw.rect(surface, ACCENT_FIJO, (10, 10, WIN_W - 20, WIN_H - 20), 1, border_radius=18)

    marca_surf = render_glow_text(font_marca, "A L F R E D", (225, 235, 245), color_estado, intensidad=2)
    surface.blit(marca_surf, (WIN_W // 2 - marca_surf.get_width() // 2, 18))

    bisel = PANTALLA_RECT.inflate(20, 20)
    pygame.draw.rect(surface, CHASIS_OSC, bisel, border_radius=14)
    pygame.draw.rect(surface, ACCENT_FIJO, bisel, 1, border_radius=14)
    pygame.draw.rect(surface, (4, 5, 9), PANTALLA_RECT, border_radius=8)

    # sombra interior del bisel
    sombra = pygame.Surface((PANTALLA_RECT.width, PANTALLA_RECT.height), pygame.SRCALPHA)
    for i in range(14):
        alpha = int(90 * (1 - i / 14))
        pygame.draw.rect(sombra, (0, 0, 0, alpha),
                          (i, i, PANTALLA_RECT.width - i * 2, PANTALLA_RECT.height - i * 2), 1)
    surface.blit(sombra, PANTALLA_RECT.topleft)

    # corchetes HUD en las cuatro esquinas de la pantalla, color de estado
    dibujar_corchetes_hud(surface, PANTALLA_RECT, color_estado)

    # LED de encendido
    led_pos = (34, WIN_H - 34)
    pulso = (math.sin(t * 4) + 1) / 2
    led_color = tuple(int(c * (0.55 + 0.45 * pulso)) for c in color_estado)
    pygame.draw.circle(surface, led_color, led_pos, 6)
    pygame.draw.circle(surface, (0, 0, 0), led_pos, 6, 1)

    # hexágono pulsante junto al LED (acento fijo)
    dibujar_hex_pulsante(surface, (led_pos[0] + 40, led_pos[1]), 10, ACCENT_FIJO, t)


def dibujar_aberracion_cromatica(surface, rect, fuerza=2):
    """Fringing rojo/azul en el marco de la pantalla -> aspecto de holograma."""
    x, y, w, h = rect
    rojo = pygame.Surface((w, h), pygame.SRCALPHA)
    azul = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(rojo, (255, 40, 40, 55), (0, 0, w, h), 2)
    pygame.draw.rect(azul, (40, 120, 255, 55), (0, 0, w, h), 2)
    surface.blit(rojo, (x - fuerza, y), special_flags=pygame.BLEND_RGBA_ADD)
    surface.blit(azul, (x + fuerza, y), special_flags=pygame.BLEND_RGBA_ADD)


def dibujar_scanlines(surface, rect, alpha=12):
    x, y, w, h = rect
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(0, h, 3):
        pygame.draw.line(overlay, (0, 0, 0, alpha), (0, yy), (w, yy))
    surface.blit(overlay, (x, y))


def dibujar_barra_pixel(surface, rect, ratio, color, fondo=(14, 18, 26)):
    x, y, w, h = rect
    pygame.draw.rect(surface, fondo, rect, border_radius=3)
    lleno = max(0, min(w, int(w * ratio)))
    if lleno > 0:
        pygame.draw.rect(surface, color, (x, y, lleno, h), border_radius=3)
    pygame.draw.rect(surface, LINEA_OSC, rect, 1, border_radius=3)


def dibujar_panel_frontal(surface, rect, status, color, t, historial, font_titulo, font_txt, font_chico):
    x, y, w, h = rect

    ahora = datetime.datetime.now()
    reloj = font_titulo.render(ahora.strftime("%H:%M:%S"), True, color)
    surface.blit(reloj, (x + w - reloj.get_width(), y))

    titulo_surf = render_glow_text(font_titulo, "BATCOMPUTER", color, ACCENT_FIJO, intensidad=1)
    surface.blit(titulo_surf, (x - 12, y - 12))
    subtitulo = font_txt.render(STATUS_LABELS.get(status, status), True, ACCENT_FIJO)
    surface.blit(subtitulo, (x, y + 36))

    pygame.draw.line(surface, color, (x, y + 64), (x + w, y + 64), 1)

    vals = [
        ("CPU", 0.55 + 0.15 * math.sin(t * 0.7)),
        ("MEM", 0.40 + 0.10 * math.sin(t * 0.5 + 1)),
        ("GPU", 0.30 + 0.20 * math.sin(t * 0.9 + 2)),
    ]
    yy = y + 80
    for etiqueta, ratio in vals:
        lbl = font_txt.render(etiqueta, True, (150, 210, 230))
        surface.blit(lbl, (x, yy))
        dibujar_barra_pixel(surface, (x + 66, yy + 4, w - 66, 14), max(0, min(1, ratio)), color)
        yy += 32

    pygame.draw.line(surface, color, (x, yy + 8), (x + w, yy + 8), 1)
    yy += 26

    label_reg = font_txt.render("REGISTRO", True, ACCENT_FIJO)
    surface.blit(label_reg, (x, yy))
    yy += 30

    area_transcripcion_h = h - (yy - y) - 40
    line_h = font_chico.get_height() + 6
    max_lineas = max(1, area_transcripcion_h // line_h)
    visibles = historial[-max_lineas:]
    n = len(visibles)
    for i, (tipo, texto) in enumerate(visibles):
        antiguedad = (n - 1 - i)
        alpha = max(90, 255 - antiguedad * 22)
        if tipo == "usuario":
            prefijo, col = "TU>  ", (140, 220, 255)
        else:
            prefijo, col = "AL>  ", color
        completo = prefijo + texto
        max_chars = max(6, (w - 4) // (font_chico.size("A")[0]))
        if len(completo) > max_chars:
            completo = completo[:max_chars - 3] + "..."
        surf = font_chico.render(completo, True, col)
        surf.set_alpha(alpha)
        surface.blit(surf, (x, yy))
        yy += line_h

    instrucciones = font_txt.render("ESPACIO / CLIC = HABLAR", True, ACCENT_FIJO)
    surface.blit(instrucciones, (x, y + h - 24))


def iniciar_interfaz():
    pygame.init()
    ventana = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("ALFRED - Terminal")

    font_burbuja = fuente_terminal(18)
    font_titulo = fuente_titulo(22)
    font_txt = fuente_terminal(16)
    font_chico = fuente_terminal(14)
    font_marca = fuente_titulo(30)
    font_etiqueta = fuente_titulo(11)

    area = pygame.Rect(PANTALLA_RECT.x, PANTALLA_RECT.y, PANTALLA_RECT.width, PANTALLA_RECT.height)
    col_izq_w = int(area.width * 0.38)

    # dos cuadros de diálogo apilados: ALFRED arriba, TÚ debajo, encima del video
    burbuja_h = 78
    gap_burbujas = 22
    burbuja_alfred_rect = pygame.Rect(area.x + 8, area.y + 16, col_izq_w - 16, burbuja_h)
    burbuja_usuario_rect = pygame.Rect(area.x + 8, burbuja_alfred_rect.bottom + gap_burbujas,
                                        col_izq_w - 16, burbuja_h)
    video_rect = pygame.Rect(area.x + 8, burbuja_usuario_rect.bottom + 26, col_izq_w - 16,
                              area.height - (burbuja_h * 2 + gap_burbujas) - 42)

    panel_rect = pygame.Rect(area.x + col_izq_w + 30, area.y + 8,
                              area.width - col_izq_w - 40, area.height - 16)

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

        dibujar_mueble_computadora(ventana, color, t, font_marca)

        dibujar_grid_horizonte(ventana, area, ACCENT_FIJO, t)

        frame = reproductor.frame_para(status)
        if frame is not None:
            ventana.blit(frame, video_rect.topleft)
        else:
            ventana.fill(BG_DEEP_2, video_rect)
            dibujar_sprite_alfred_fallback(ventana, video_rect, status, t)
        pygame.draw.rect(ventana, color, video_rect, 2, border_radius=4)
        dibujar_anillo_radar(ventana, video_rect.center,
                              max(video_rect.width, video_rect.height) * 0.62, color, t)

        texto_alfred_burbuja = alfred_text if alfred_text else "..."
        texto_usuario_burbuja = user_text if user_text else "..."

        dibujar_burbuja_arcade(ventana, burbuja_alfred_rect, texto_alfred_burbuja, font_burbuja,
                               color, etiqueta="ALFRED", font_etiqueta=font_etiqueta,
                               cola=False)
        dibujar_burbuja_arcade(ventana, burbuja_usuario_rect, texto_usuario_burbuja, font_burbuja,
                               COLOR_USUARIO, etiqueta="TÚ", font_etiqueta=font_etiqueta,
                               cola=True, cola_dir=1)

        dibujar_panel_frontal(ventana, panel_rect, status, color, t, historial,
                               font_titulo, font_txt, font_chico)

        dibujar_scanlines(ventana, area, alpha=10)
        dibujar_aberracion_cromatica(ventana, area, fuerza=2)

        pygame.display.flip()
        clock.tick(60)

    reproductor.liberar()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    iniciar_interfaz()