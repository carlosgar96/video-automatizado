"""Definición de rutas de la aplicación Flask."""

import math
import os
import uuid
from datetime import datetime

from flask import abort, jsonify, render_template, request, send_from_directory
from moviepy.editor import AudioFileClip

from app import app
from video import (
    OUTPUT_DIR,
    build_video,
    split_script_by_scenes,
    synth_tts_to_wav,
)


@app.route("/")
def index():
    """Página principal de la aplicación."""
    return render_template("index.html")


@app.post("/api/generate")
def api_generate():
    """Genera un video a partir de un guion enviado por el usuario."""
    data = request.get_json(force=True, silent=True) or {}
    script = (data.get("script") or "").strip()
    voice = data.get("voice") or "default"
    rate = int(data.get("rate") or 180)
    per_slide = float(data.get("perSlideSec") or 2.0)

    if not script:
        return jsonify({"error": "El guion no puede estar vacío."}), 400

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = uuid.uuid4().hex[:8]
    audio_path = os.path.join(OUTPUT_DIR, f"audio_{ts}_{session_id}.wav")
    video_path = os.path.join(OUTPUT_DIR, f"video_{ts}_{session_id}.mp4")

    try:
        synth_tts_to_wav(script, audio_path, voice_preference=voice, rate=rate)
        audio_clip = AudioFileClip(audio_path)
        duration = max(1.0, float(audio_clip.duration))
        audio_clip.close()
        scenes = max(1, math.ceil(duration / per_slide))

        slides = split_script_by_scenes(script, scenes)
        build_video(slides, audio_path, video_path, per_slide_sec=per_slide)

        rel = os.path.basename(video_path)
        return jsonify({"ok": True, "video": f"/download/{rel}"}), 200
    except Exception as exc:  # pragma: no cover - simple error propagation
        return jsonify({"error": str(exc)}), 500


@app.get("/download/<path:filename>")
def download_file(filename: str):
    """Permite descargar archivos generados de la carpeta de salida."""
    if ".." in filename or filename.startswith("/"):
        abort(400)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)
