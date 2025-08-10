const $ = (sel) => document.querySelector(sel);

const scriptEl = $('#script');
const voiceEl = $('#voice');
const rateEl = $('#rate');
const perSlideEl = $('#perSlide');
const generateBtn = $('#generateBtn');
const statusEl = $('#status');
const resultSection = $('#resultSection');
const resultVideo = $('#resultVideo');
const downloadLink = $('#downloadLink');

function setStatus(msg, type = 'info') {
  statusEl.className = `status ${type}`;
  statusEl.textContent = msg;
}

async function generateVideo() {
  const script = scriptEl.value.trim();
  if (!script) {
    setStatus('Por favor, ingresa un guion.', 'error');
    return;
  }

  setStatus('Generando audio y video, por favor espera...', 'info');
  generateBtn.disabled = true;

  try {
    const payload = {
      script,
      voice: voiceEl.value,
      rate: Number(rateEl.value || 180),
      perSlideSec: Number(perSlideEl.value || 2)
    };

    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || 'Error desconocido al generar el video.');
    }

    const url = data.video;
    resultVideo.src = url;
    downloadLink.href = url;
    resultSection.classList.remove('hidden');
    setStatus('¡Listo! Abajo puedes reproducir o descargar tu video.', 'success');
  } catch (e) {
    console.error(e);
    setStatus(`Error: ${e.message}`, 'error');
  } finally {
    generateBtn.disabled = false;
  }
}

generateBtn.addEventListener('click', generateVideo);
