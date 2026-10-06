import { list, put } from '@vercel/blob';

const PREFIX = 'reflexflow/jobs/';
const CATEGORIES = new Set(['landscapes', 'cities', 'mixed', 'animals']);
const STATUSES = new Set(['queued', 'claimed', 'working', 'completed', 'completed_with_errors', 'error']);

function keyFrom(req) {
  const raw = req.headers['x-reflexflow-key'];
  return Array.isArray(raw) ? raw[0] : String(raw || '');
}

function authorized(req) {
  const expected = String(process.env.REFLEXFLOW_REMOTE_KEY || '');
  return expected && keyFrom(req) === expected;
}

function reply(res, code, body) {
  res.status(code).setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(body));
}

async function readJob(blob) {
  const url = `${blob.url}${blob.url.includes('?') ? '&' : '?'}rf=${Date.now()}`;
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`No pude leer el trabajo ${blob.pathname}`);
  return await r.json();
}

async function getJobs() {
  const { blobs } = await list({ prefix: PREFIX, limit: 100 });
  const jobs = [];
  for (const blob of blobs) {
    try { jobs.push(await readJob(blob)); } catch { /* ignore damaged entry */ }
  }
  return jobs.sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
}

async function saveJob(job) {
  job.updatedAt = Date.now();
  await put(`${PREFIX}${job.id}.json`, JSON.stringify(job), {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: 'application/json'
  });
  return job;
}

function cleanCreate(body) {
  const items = Array.isArray(body?.items) ? body.items : [];
  if (items.length < 1 || items.length > 10) throw new Error('Configura entre 1 y 10 videos.');
  const aspect = body?.settings?.aspect === '16:9' ? '16:9' : '9:16';
  const originality = body?.settings?.originality === 'balanced' ? 'balanced' : 'strict';
  const cleanItems = items.map((item, idx) => {
    const duration = Number(item.duration_seconds);
    const clip = Number(item.clip_seconds);
    const fade = Number(item.fade);
    const category = String(item.visual_category || 'mixed');
    if (!Number.isFinite(duration) || duration < 5 || duration > 600) throw new Error(`Video ${idx + 1}: duración inválida.`);
    if (!Number.isFinite(clip) || clip < 3 || clip > 5) throw new Error(`Video ${idx + 1}: duración de clip inválida.`);
    if (!Number.isFinite(fade) || fade < 0.1 || fade > 1) throw new Error(`Video ${idx + 1}: transición inválida.`);
    if (!CATEGORIES.has(category)) throw new Error(`Video ${idx + 1}: categoría inválida.`);
    return {
      index: idx + 1,
      duration_seconds: Math.round(duration * 10) / 10,
      visual_category: category,
      clip_seconds: Math.round(clip * 10) / 10,
      fade: Math.round(fade * 10) / 10,
      title: String(item.title || '').slice(0, 90)
    };
  });
  return { settings: { aspect, originality }, items: cleanItems };
}

async function parseBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  return await new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', c => raw += c);
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

export default async function handler(req, res) {
  if (!authorized(req)) return reply(res, 401, { error: 'Código de acceso incorrecto.' });
  const action = String(req.query?.action || 'list');
  try {
    if (req.method === 'GET' && action === 'health') {
      return reply(res, 200, { ok: true, service: 'ReflexFlow Mobile', now: Date.now() });
    }
    if (req.method === 'GET' && action === 'list') {
      const jobs = await getJobs();
      return reply(res, 200, { jobs: jobs.slice(0, 30) });
    }
    if (req.method === 'GET' && action === 'next') {
      const workerId = String(req.query?.workerId || '').slice(0, 80);
      if (!workerId) return reply(res, 400, { error: 'workerId requerido.' });
      const jobs = await getJobs();
      const already = jobs.find(j => j.workerId === workerId && ['claimed', 'working'].includes(j.status));
      if (already) return reply(res, 200, { job: already });
      const next = [...jobs].reverse().find(j => j.status === 'queued');
      if (!next) return reply(res, 200, { job: null });
      next.status = 'claimed';
      next.workerId = workerId;
      next.claimedAt = Date.now();
      next.detail = 'Trabajo recibido por ReflexFlow Studio';
      await saveJob(next);
      return reply(res, 200, { job: next });
    }
    if (req.method === 'POST' && action === 'create') {
      const body = await parseBody(req);
      const clean = cleanCreate(body);
      const id = `R${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
      const job = {
        id,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        status: 'queued',
        progress: 0,
        etaSeconds: 0,
        currentIndex: 0,
        detail: 'Esperando a que ReflexFlow Studio lo tome en el PC',
        settings: clean.settings,
        items: clean.items,
        workerId: '',
        batchId: '',
        error: ''
      };
      await saveJob(job);
      return reply(res, 200, { ok: true, job });
    }
    if (req.method === 'POST' && action === 'status') {
      const body = await parseBody(req);
      const id = String(body.id || '');
      if (!id) return reply(res, 400, { error: 'id requerido.' });
      const jobs = await getJobs();
      const job = jobs.find(j => j.id === id);
      if (!job) return reply(res, 404, { error: 'Trabajo no encontrado.' });
      if (body.workerId && job.workerId && String(body.workerId) !== String(job.workerId)) return reply(res, 409, { error: 'Worker distinto.' });
      if (body.status && STATUSES.has(String(body.status))) job.status = String(body.status);
      for (const field of ['progress', 'etaSeconds', 'currentIndex', 'batchId', 'detail', 'error', 'finishedAt']) {
        if (body[field] !== undefined) job[field] = body[field];
      }
      if (Array.isArray(body.items)) job.resultItems = body.items.slice(0, 10);
      await saveJob(job);
      return reply(res, 200, { ok: true, job });
    }
    if (req.method === 'POST' && action === 'retry') {
      const body = await parseBody(req);
      const jobs = await getJobs();
      const job = jobs.find(j => j.id === String(body.id || ''));
      if (!job) return reply(res, 404, { error: 'Trabajo no encontrado.' });
      job.status = 'queued'; job.progress = 0; job.etaSeconds = 0; job.currentIndex = 0; job.workerId = ''; job.batchId = ''; job.error = '';
      job.detail = 'Reintento solicitado desde el celular';
      await saveJob(job);
      return reply(res, 200, { ok: true, job });
    }
    return reply(res, 404, { error: 'Acción no disponible.' });
  } catch (error) {
    return reply(res, 500, { error: String(error?.message || error) });
  }
}
