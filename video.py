"""Funciones utilitarias para la generación de videos."""

from __future__ import annotations

import math
import os
import uuid
from typing import List, Sequence

import pyttsx3
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    concatenate_videoclips,
    vfx,
)

# Directorios base utilizados para almacenar recursos y resultados.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FRAMES_DIR = os.path.join(OUTPUT_DIR, "frames")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

# Lista de rutas posibles para una fuente TTF por defecto.
DEFAULT_FONT_PATHS = [
    os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"),  # el usuario puede colocar una TTF aquí
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def get_font(size: int) -> ImageFont.ImageFont:
    """Devuelve una fuente TrueType del tamaño solicitado."""
    for path in DEFAULT_FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    """Envuelve el texto para que se ajuste al ancho máximo dado."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        width, _ = draw.textsize(test, font=font)
        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def make_slide_image(text: str, size: Sequence[int] = (1280, 720)) -> Image.Image:
    """Genera una imagen para una diapositiva con el texto indicado."""
    img = Image.new("RGB", size, color=(20, 20, 24))
    draw = ImageDraw.Draw(img)

    for y in range(size[1]):
        shade = 20 + int(60 * (y / size[1]))
        draw.line([(0, y), (size[0], y)], fill=(shade, shade, shade + 10))

    panel_margin = 60
    panel = [panel_margin, panel_margin, size[0] - panel_margin, size[1] - panel_margin]
    draw.rounded_rectangle(panel, radius=30, fill=(0, 0, 0, 180), outline=(255, 255, 255), width=2)

    title_font = get_font(56)
    text_font = get_font(40)
    title = " ".join(text.split()[:6])

    tw, th = draw.textsize(title, font=title_font)
    tx = (size[0] - tw) // 2
    ty = panel[1] + 30
    draw.text((tx, ty), title, font=title_font, fill=(255, 255, 255))

    body_area_width = size[0] - panel_margin * 2 - 80
    lines = wrap_text(draw, text, text_font, max_width=body_area_width)
    line_height = text_font.getbbox("A")[3] - text_font.getbbox("A")[1] + 8

    start_y = ty + th + 30
    x = panel[0] + 40
    y = start_y
    for line in lines[:8]:
        draw.text((x, y), line, font=text_font, fill=(230, 230, 230))
        y += line_height

    return img


def synth_tts_to_wav(
    text: str,
    wav_path: str,
    voice_preference: str = "default",
    rate: int = 180,
) -> None:
    """Genera audio en formato WAV a partir de texto usando pyttsx3."""
    engine = pyttsx3.init()
    try:
        if voice_preference in ("male", "female"):
            voices = engine.getProperty("voices")
            chosen = None
            for v in voices:
                name_low = (getattr(v, "name", "") or "").lower()
                gender_low = (getattr(v, "gender", "") or "").lower()
                if voice_preference == "male" and ("male" in gender_low or "male" in name_low):
                    chosen = v.id
                    break
                if voice_preference == "female" and ("female" in gender_low or "female" in name_low):
                    chosen = v.id
                    break
            if chosen:
                engine.setProperty("voice", chosen)
        engine.setProperty("rate", rate)
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
    finally:
        engine.stop()


def split_script_by_scenes(text: str, scenes: int) -> List[str]:
    """Divide el guion en partes iguales según la cantidad de escenas."""
    words = text.split()
    if scenes <= 0 or not words:
        return [text]
    per_scene = max(1, math.ceil(len(words) / scenes))
    chunks: List[str] = []
    for i in range(0, len(words), per_scene):
        chunk = " ".join(words[i : i + per_scene])
        chunks.append(chunk)
    return chunks


def build_video(
    slides_text: Sequence[str],
    audio_path: str,
    out_path: str,
    per_slide_sec: float = 2.0,
    size: Sequence[int] = (1280, 720),
) -> None:
    """Construye un video a partir de las diapositivas y una pista de audio."""
    clips = []
    for text in slides_text:
        img = make_slide_image(text, size=size)
        frame_name = os.path.join(FRAMES_DIR, f"frame_{uuid.uuid4().hex}.png")
        img.save(frame_name)
        clip = ImageClip(frame_name, duration=per_slide_sec)
        clip = clip.resize(lambda tt: 1.0 + 0.03 * (tt / per_slide_sec)).fx(vfx.fadein, 0.25).fx(
            vfx.fadeout, 0.25
        )
        clips.append(clip)

    if not clips:
        raise ValueError("No clips generated")

    video = concatenate_videoclips(clips, method="compose")
    audio = AudioFileClip(audio_path)

    if video.duration < audio.duration:
        last = clips[-1].set_duration(clips[-1].duration + (audio.duration - video.duration))
        clips[-1] = last
        video = concatenate_videoclips(clips, method="compose")
    else:
        video = video.subclip(0, audio.duration)

    final = video.set_audio(audio)
    final.write_videofile(
        out_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        verbose=False,
        logger=None,
    )

    audio.close()
    for clip in clips:
        clip.close()
    final.close()
