import os
import math
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from PIL import Image, ImageDraw, ImageFont
import pyttsx3
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, vfx
import logging

logging.basicConfig(level=logging.INFO)

# App setup
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
FRAMES_DIR = os.path.join(OUTPUT_DIR, 'frames')
FONTS_DIR = os.path.join(BASE_DIR, 'fonts')

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

# Try to load a default TTF font if present, else fall back to PIL default
DEFAULT_FONT_PATHS = [
    os.path.join(FONTS_DIR, 'DejaVuSans-Bold.ttf'),  # user can drop a TTF here
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'C:/Windows/Fonts/arial.ttf',
]

def get_font(size: int):
    for p in DEFAULT_FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int):
    words = text.split()
    lines = []
    current = ''
    for w in words:
        test = (current + ' ' + w).strip()
        w_width, _ = draw.textsize(test, font=font)
        if w_width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def make_slide_image(text: str, size=(1280, 720)):
    # Simple gradient background
    img = Image.new('RGB', size, color=(20, 20, 24))
    draw = ImageDraw.Draw(img)

    for y in range(size[1]):
        shade = 20 + int(60 * (y / size[1]))
        draw.line([(0, y), (size[0], y)], fill=(shade, shade, shade + 10))

    # Semi-transparent panel
    panel_margin = 60
    panel = [panel_margin, panel_margin, size[0] - panel_margin, size[1] - panel_margin]
    draw.rounded_rectangle(panel, radius=30, fill=(0, 0, 0, 180), outline=(255, 255, 255), width=2)

    # Text
    title_font = get_font(56)
    text_font = get_font(40)

    # Title from first 6 words
    title = ' '.join(text.split()[:6])

    # Draw title centered at top panel
    tw, th = draw.textsize(title, font=title_font)
    tx = (size[0] - tw) // 2
    ty = panel[1] + 30
    draw.text((tx, ty), title, font=title_font, fill=(255, 255, 255))

    # Body wrapped
    body_area_width = size[0] - panel_margin * 2 - 80
    lines = wrap_text(draw, text, text_font, max_width=body_area_width)
    line_height = text_font.getbbox('A')[3] - text_font.getbbox('A')[1] + 8

    start_y = ty + th + 30
    x = panel[0] + 40
    y = start_y
    for line in lines[:8]:
        draw.text((x, y), line, font=text_font, fill=(230, 230, 230))
        y += line_height

    return img


def synth_tts_to_wav(text: str, wav_path: str, voice_preference: str = 'default', rate: int = 180):
    logging.info("Synthesizing TTS to %s", wav_path)
    engine = pyttsx3.init()
    try:
        # Select voice by gender preference if possible
        if voice_preference in ('male', 'female'):
            voices = engine.getProperty('voices')
            chosen = None
            for v in voices:
                name_low = (getattr(v, 'name', '') or '').lower()
                gender_low = (getattr(v, 'gender', '') or '').lower()
                if voice_preference == 'male' and ('male' in gender_low or 'male' in name_low):
                    chosen = v.id
                    break
                if voice_preference == 'female' and ('female' in gender_low or 'female' in name_low):
                    chosen = v.id
                    break
            if chosen:
                engine.setProperty('voice', chosen)
        engine.setProperty('rate', rate)
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        logging.info("TTS synthesis completed: %s", wav_path)
    except Exception:
        logging.exception("Error during TTS synthesis")
        raise
    finally:
        engine.stop()


def split_script_by_scenes(text: str, scenes: int):
    words = text.split()
    if scenes <= 0 or not words:
        return [text]
    per_scene = max(1, math.ceil(len(words) / scenes))
    chunks = []
    for i in range(0, len(words), per_scene):
        chunk = ' '.join(words[i:i + per_scene])
        chunks.append(chunk)
    return chunks


def build_video(slides_text, audio_path, out_path, per_slide_sec=2.0, size=(1280, 720)):
    logging.info("Building video with %d slides", len(slides_text))
    clips = []
    audio = None
    final = None
    try:
        for t in slides_text:
            img = make_slide_image(t, size=size)
            fname = os.path.join(FRAMES_DIR, f"frame_{uuid.uuid4().hex}.png")
            img.save(fname)
            clip = ImageClip(fname, duration=per_slide_sec)
            # gentle zoom effect
            clip = clip.resize(lambda tt: 1.0 + 0.03 * (tt / per_slide_sec)).fx(vfx.fadein, 0.25).fx(vfx.fadeout, 0.25)
            clips.append(clip)

        if not clips:
            raise ValueError('No clips generated')

        video = concatenate_videoclips(clips, method='compose')
        audio = AudioFileClip(audio_path)

        # Sync: trim or pad video to match audio duration
        if video.duration < audio.duration:
            last = clips[-1].set_duration(clips[-1].duration + (audio.duration - video.duration))
            clips[-1] = last
            video = concatenate_videoclips(clips, method='compose')
        else:
            video = video.subclip(0, audio.duration)

        final = video.set_audio(audio)

        # Export
        final.write_videofile(out_path, fps=24, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        logging.info("Video written to %s", out_path)
    except Exception:
        logging.exception("Error building video")
        raise
    finally:
        if audio:
            audio.close()
        for c in clips:
            c.close()
        if final:
            final.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.post('/api/generate')
def api_generate():
    data = request.get_json(force=True, silent=True) or {}
    script = (data.get('script') or '').strip()
    voice = (data.get('voice') or 'default')
    rate = int(data.get('rate') or 180)
    per_slide = float(data.get('perSlideSec') or 2.0)

    if not script:
        return jsonify({'error': 'El guion no puede estar vacío.'}), 400

    # Paths
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_id = uuid.uuid4().hex[:8]
    audio_path = os.path.join(OUTPUT_DIR, f'audio_{ts}_{session_id}.wav')
    video_path = os.path.join(OUTPUT_DIR, f'video_{ts}_{session_id}.mp4')
    logging.info("Session %s: generating video", session_id)
    try:
        # 1) TTS
        synth_tts_to_wav(script, audio_path, voice_preference=voice, rate=rate)

        # 2) Estimate scenes by audio duration
        audio_clip = AudioFileClip(audio_path)
        duration = max(1.0, float(audio_clip.duration))
        audio_clip.close()
        scenes = max(1, math.ceil(duration / per_slide))

        # 3) Split text and render video
        slides = split_script_by_scenes(script, scenes)
        build_video(slides, audio_path, video_path, per_slide_sec=per_slide)
        rel = os.path.basename(video_path)
        logging.info("Session %s: video generation completed", session_id)
        return jsonify({'ok': True, 'video': f'/download/{rel}'}), 200
    except Exception:
        logging.exception("Session %s: error generating video", session_id)
        return jsonify({'error': 'Error al generar el video.'}), 500


@app.get('/download/<path:filename>')
def download_file(filename):
    # Only allow files from OUTPUT_DIR
    if '..' in filename or filename.startswith('/'):
        abort(400)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == '__main__':
    # For local dev
    app.run(host='0.0.0.0', port=5000, debug=True)
