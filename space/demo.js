// Sokhan demo UI wiring — audio capture (mic / file / bundled sample),
// resampling to 16 kHz mono, and talking to the transformers.js worker.
// All inference happens client-side; see worker.js.
//
// Reliability notes (this section is the fix for the "eternal processing"
// bug): audio is decoded in an AudioContext at its own rate and then
// resampled offline to 16 kHz. Forcing a 16 kHz context for
// decodeAudioData hangs Chromium on opus/webm (MediaRecorder and Telegram
// voice audio) — the symptom was a demo stuck forever at "preparing
// audio". Every stage now also has: a watchdog, an elapsed timer, per-
// window progress, a hard duration cap, and a cancel button that
// terminates the worker, so no input can ever wedge the UI again.

const SAMPLE_URL =
  "https://raw.githubusercontent.com/Abolfazlrwm/sokhan/main/benchmarks/data/clips/cv_fa_00001501_39aee6016733.wav";
// Human-verified reference from the benchmark fixture, shown for honest
// comparison after the sample is transcribed.
const SAMPLE_REFERENCE = "معلومه حسابی قاطی کردی";

const SAMPLE_RATE = 16000;
const FILE_CAP_MB = 60; // pre-decode guard; protects RAM on giant uploads
const ABS_MAX_SECONDS = 1800; // hard ceiling even on WebGPU (30 min)
const DECODE_TIMEOUT_MS = 45000; // watchdog: decodeAudioData must resolve

const $ = (id) => document.getElementById(id);
const modelSel = $("model");
const micBtn = $("mic");
const sampleBtn = $("sample");
const fileInput = $("file");
const statusEl = $("status");
const barEl = $("bar");
const barFill = barEl.firstElementChild;
const transcriptEl = $("transcript");
const metaEl = $("meta");
const refEl = $("ref");
const badgeEl = $("badge");
const cancelBtn = $("cancel");
const stampChk = $("stamp");
const copyBtn = $("copy");
const stageEls = [...document.querySelectorAll("#stages span")];

// ---------- Persian punctuation restoration ----------
// Same rule family as backend/sokhan/core/punctuation.py (the worker
// pipeline's post-pass), ported verbatim so the browser demo shows the
// transcript in the same publishable shape the product ships: Latin
// marks become their Persian counterparts, spacing is fixed, and every
// sentence gets a terminal mark — ؟ when it reads as a question, .
// otherwise. Deterministic, no model call.

const LATIN_TO_PERSIAN = { ",": "،", "?": "؟", ";": "؛" };
const PUNCT_CHARS = "،؛:.!?؟…";
const QUESTION_WORDS = new Set([
  "آیا", "چرا", "چطور", "چطوره", "چگونه", "چقدر", "کی", "کیه", "کِی",
  "کجا", "کجاست", "کجای", "کدام", "کدوم", "چیه",
]);

// Punctuation and quote marks are stripped from token edges inside
// isQuestion's regex, so "چطوره،" and «کی؟» still count as question words.
function isQuestion(text) {
  return text
    .split(/\s+/)
    .some((token) => QUESTION_WORDS.has(token.replace(/^[،؛:.!?؟…«»()"'،]+|[،؛:.!?؟…«»()"'،]+$/g, "")));
}

function restorePunctuation(text) {
  let cleaned = text.replace(/[,?;]/g, (ch) => LATIN_TO_PERSIAN[ch] || ch).trim();
  cleaned = cleaned.replace(/\s+([،؛:.!?؟…])/g, "$1");
  cleaned = cleaned.replace(/([،؛؟!…])(?=[^\s،؛:.!?؟…])/g, "$1 ");
  cleaned = cleaned.replace(/\s{2,}/g, " ").trim();
  if (!cleaned || PUNCT_CHARS.includes(cleaned[cleaned.length - 1])) return cleaned;
  return cleaned + (isQuestion(cleaned) ? "؟" : ".");
}

function restorePunctuationParagraph(text) {
  // Apply per line so a multi-segment transcript keeps its sentence bounds.
  return text
    .split("\n")
    .map((line) => restorePunctuation(line))
    .join("\n");
}

// ---------- small formatting helpers ----------

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const faDigits = (s) => String(s).replace(/\d/g, (d) => FA_DIGITS[d]);

function mmss(t) {
  const s = Math.max(0, Math.floor(t));
  const m = Math.floor(s / 60);
  return `${faDigits(String(m).padStart(2, "0"))}:${faDigits(String(s % 60).padStart(2, "0"))}`;
}

const DEVICE_LABELS = { webgpu: "WebGPU", wasm: "CPU (WASM)" };

// ---------- stage pills ----------

function setStage(n) {
  stageEls.forEach((el, i) => {
    el.classList.toggle("active", i + 1 === n);
    el.classList.toggle("done", n > i + 1);
  });
}

// ---------- worker plumbing ----------

let worker = null;
let busy = false;
let runId = 0; // generation counter: any late async callback from a
               // cancelled/stale run is dropped instead of touching the UI
let tickerHandle = null;
let baseStatus = "";
let lastAudioSeconds = 0;
let lastResult = null; // { text, segments } for the timestamp toggle

const downloads = new Map(); // file -> { loaded, total }

function onWorkerMessage(event) {
  const { type, payload } = event.data;
  if (type === "progress") {
    setStage(2);
    downloads.set(payload.file, payload);
    const loaded = [...downloads.values()].reduce((s, d) => s + d.loaded, 0);
    const total = [...downloads.values()].reduce((s, d) => s + d.total, 0);
    if (total > 0) {
      const pct = Math.round((loaded / total) * 100);
      barEl.style.display = "block";
      barFill.style.width = `${pct}%`;
      setBaseStatus(`در حال دانلود مدل … ${faDigits(pct)}٪`);
    }
  } else if (type === "device") {
    badgeEl.textContent = `روی ${DEVICE_LABELS[payload] || payload}`;
    badgeEl.style.display = "inline-block";
  } else if (type === "status" && payload === "ready") {
    setStage(3);
    barEl.style.display = "none";
    setBaseStatus("مدل آماده است — در حال پیاده‌سازی …");
  } else if (type === "status") {
    setBaseStatus(payload);
  } else if (type === "chunk-progress") {
    const { done, total, elapsed } = payload;
    const pct = Math.min(99, Math.round((done / Math.max(1, total)) * 100));
    barEl.style.display = "block";
    barFill.style.width = `${pct}%`;
    let eta = "";
    if (done >= 1 && done < total) {
      const per = elapsed / done;
      const remain = Math.round((total - done) * per);
      if (remain > 3) eta = ` — تخمین پایان: ~${faDigits(remain)} ثانیه`;
    }
    setBaseStatus(
      `در حال پیاده‌سازی — قطعهٔ ${faDigits(done)} از ${faDigits(total)} (${faDigits(pct)}٪)${eta}`
    );
  } else if (type === "result") {
    finish(payload);
  } else if (type === "error") {
    fail("خطا: " + payload);
  }
}

function wireWorker() {
  worker.onmessage = onWorkerMessage;
  worker.onerror = (e) => {
    console.error(e);
    if (busy) fail("خطای worker: " + (e.message || "نامشخص"));
  };
}

function spawnWorker() {
  worker = new Worker("worker.js?v=4", { type: "module" });
  wireWorker();
}

function setBaseStatus(text) {
  baseStatus = text;
  statusEl.textContent = text;
}

function tick() {
  const startedAt = Number(statusEl.dataset.started || 0);
  if (!startedAt) return;
  const sec = Math.round((Date.now() - startedAt) / 1000);
  if (sec >= 5) statusEl.textContent = `${baseStatus} — ${faDigits(sec)} ثانیه گذشته`;
}

function startTicker() {
  stopTicker();
  statusEl.dataset.started = String(Date.now());
  tickerHandle = setInterval(tick, 1000);
}

function stopTicker() {
  if (tickerHandle) clearInterval(tickerHandle);
  tickerHandle = null;
  delete statusEl.dataset.started;
}

function setStatus(text) {
  // One-shot status (not part of the ticking base line).
  stopTicker();
  baseStatus = text;
  statusEl.textContent = text;
}

function startWork(message) {
  // runId is owned by the entry points (sample/file/mic/cancel); startWork
  // must not bump it — transcribeRaw compares its own id after this call.
  busy = true;
  lock();
  downloads.clear();
  refEl.style.display = "none";
  badgeEl.style.display = "none";
  transcriptEl.textContent = "(در حال پردازش…)";
  metaEl.textContent = "";
  copyBtn.style.display = "none";
  lastResult = null;
  barEl.style.display = "none";
  barFill.style.width = "0%";
  cancelBtn.style.display = "inline-block";
  setBaseStatus(message);
  startTicker();
}

function endRun() {
  busy = false;
  stopTicker();
  unlock();
  cancelBtn.style.display = "none";
  barEl.style.display = "none";
}

function fail(message) {
  endRun();
  setStage(0);
  statusEl.textContent = message;
  transcriptEl.textContent = "(پردازش انجام نشد.)";
}

function finish(payload) {
  lastResult = { text: payload.text || "", segments: payload.segments || [] };
  endRun();
  setStage(4);
  setStatus("تمام شد — می‌توانید کلیپ دیگری امتحان کنید.");
  renderTranscript();
  const device = DEVICE_LABELS[payload.device] || payload.device || "";
  metaEl.textContent =
    `زمان پردازش: ${faDigits(payload.elapsed.toFixed(1))} ثانیه` +
    (lastAudioSeconds ? ` برای ${faDigits(lastAudioSeconds.toFixed(1))} ثانیه صدا` : "") +
    (payload.windows > 1 ? ` در ${faDigits(payload.windows)} قطعه` : "") +
    (device ? ` روی ${device}` : "") +
    " — کاملاً روی دستگاه شما.";
  copyBtn.style.display = "inline-block";
}

function renderTranscript() {
  if (!lastResult) return;
  if (stampChk.checked && lastResult.segments.length) {
    const lines = lastResult.segments.map(
      (s) =>
        `[${mmss(s.start)}–${mmss(s.end)}] ` + restorePunctuation(s.text)
    );
    transcriptEl.textContent = lines.join("\n");
  } else {
    transcriptEl.textContent =
      restorePunctuationParagraph(lastResult.text) ||
      "(متنی تشخیص داده نشد — شاید صدا کوتاه یا نویزی بود.)";
  }
}

function lock() {
  micBtn.disabled = true;
  sampleBtn.disabled = true;
  fileInput.disabled = true;
  modelSel.disabled = true;
}

function unlock() {
  micBtn.disabled = false;
  sampleBtn.disabled = false;
  fileInput.disabled = false;
  modelSel.disabled = false;
}

// ---------- audio -> 16 kHz mono Float32 ----------

async function decodeTo16k(arrayBuffer) {
  // Decode at the context's natural rate (never a forced 16 kHz context —
  // Chromium can hang forever on opus/webm there), then resample offline
  // to exactly 16 kHz mono. A watchdog turns a wedged decode into a
  // visible error instead of an eternal spinner.
  const decodeCtx = new AudioContext();
  let decoded;
  try {
    decoded = await Promise.race([
      decodeCtx.decodeAudioData(arrayBuffer),
      new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("زمان زیادی برای رمزگشایی صدا گذشت")),
          DECODE_TIMEOUT_MS
        )
      ),
    ]);
  } finally {
    decodeCtx.close().catch(() => {});
  }
  const frames = Math.max(1, Math.ceil(decoded.duration * SAMPLE_RATE));
  const offline = new OfflineAudioContext(1, frames, SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  // slice(): detach from the OfflineAudioContext's internal buffer so the
  // Float32Array's own buffer is transferable to the worker.
  return { audio: rendered.getChannelData(0).slice(), seconds: decoded.duration };
}

function tooLong(seconds) {
  return (
    `این صدا ${faDigits(Math.round(seconds / 60))} دقیقه است؛ دموی مرورگری برای ` +
    `کلیپ‌های تا ${faDigits(ABS_MAX_SECONDS / 60)} دقیقه طراحی شده (روی CPU سقف کمتر است). ` +
    "برای فایل‌های بلندتر، نسخهٔ سلف‌هاست را اجرا کنید: " +
    "github.com/Abolfazlrwm/sokhan/tree/main/deploy"
  );
}

async function transcribeArrayBuffer(arrayBuffer, sourceLabel) {
  if (busy) return;
  await transcribeRaw(arrayBuffer, sourceLabel);
}

// Core flow without the busy guard — for callers that manage `busy`
// themselves (the sample button fetches first, then starts the pipeline).
async function transcribeRaw(arrayBuffer, sourceLabel) {
  const id = ++runId;
  startWork(`در حال آماده‌سازی صدا (${sourceLabel}) …`);
  setStage(1);
  try {
    const { audio, seconds } = await decodeTo16k(arrayBuffer);
    if (id !== runId) return; // cancelled while decoding
    if (seconds < 0.3) {
      endRun();
      setStage(0);
      transcriptEl.textContent = "(صدا خیلی کوتاه است.)";
      setStatus("صدا خیلی کوتاه است — حداقل نیم ثانیه لازم است.");
      return;
    }
    lastAudioSeconds = seconds;
    if (seconds > ABS_MAX_SECONDS) {
      endRun();
      setStage(0);
      transcriptEl.textContent = "(فایل بیش از حد بلند است.)";
      setStatus(tooLong(seconds));
      return;
    }
    setStage(3); // worker will drop back to stage 2 if the model needs downloading
    setBaseStatus("در حال آماده‌سازی مدل …");
    // Transfer the buffer: the audio is not needed on this thread anymore.
    worker.postMessage(
      { kind: "transcribe", audio, modelId: modelSel.value, seconds },
      [audio.buffer]
    );
  } catch (err) {
    console.error(err);
    if (id !== runId) return;
    fail(
      "خطا در خواندن فایل صوتی: " + err.message +
        " — اگر فایل OGG است، سافاری از آن پشتیبانی نمی‌کند؛ Chrome یا فایل MP3/WAV را امتحان کنید."
    );
  }
}

// ---------- inputs ----------

sampleBtn.onclick = async () => {
  if (busy) return;
  const id = ++runId;
  busy = true;
  lock();
  downloads.clear();
  refEl.style.display = "none";
  badgeEl.style.display = "none";
  transcriptEl.textContent = "(در حال پردازش…)";
  metaEl.textContent = "";
  copyBtn.style.display = "none";
  cancelBtn.style.display = "inline-block";
  setStage(1);
  setBaseStatus("در حال دریافت کلیپ نمونه (از فیکسچر بنچمارک پروژه) …");
  startTicker();
  try {
    const res = await fetch(SAMPLE_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (id !== runId) return;
    refEl.innerHTML = `<b>متن مرجع (انسان):</b> ${SAMPLE_REFERENCE}`;
    refEl.style.display = "block";
    const ab = await res.arrayBuffer();
    busy = false; // transcribeRaw owns the guard from here (no await between this and startWork)
    await transcribeRaw(ab, "نمونه");
  } catch (err) {
    if (id !== runId) return;
    fail("دریافت نمونه ناموفق بود: " + err.message);
  }
};

let recorder = null;
let recordChunks = [];

micBtn.onclick = async () => {
  if (busy) return;
  if (recorder) {
    recorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordChunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => recordChunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      micBtn.textContent = "ضبط با میکروفن";
      micBtn.classList.remove("recording");
      const blob = new Blob(recordChunks, { type: recorder.mimeType });
      recorder = null;
      if (blob.size > FILE_CAP_MB * 1024 * 1024) {
        setStatus(`ضبط شما ${faDigits(Math.round(blob.size / 1048576))} مگابایت است؛ سقف دمو ${faDigits(FILE_CAP_MB)} مگابایت است.`);
        return;
      }
      await transcribeArrayBuffer(await blob.arrayBuffer(), "ضبط میکروفن");
    };
    recorder.start();
    micBtn.textContent = "پایان ضبط";
    micBtn.classList.add("recording");
    setStatus("در حال ضبط — دکمه را دوباره بزنید تا تمام شود.");
  } catch (err) {
    setStatus("دسترسی به میکروفن داده نشد: " + err.message);
  }
};

fileInput.onchange = async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) return;
  fileInput.value = "";
  if (file.size > FILE_CAP_MB * 1024 * 1024) {
    setStatus(
      `فایل ${faDigits(Math.round(file.size / 1048576))} مگابایت است؛ سقف دمو ` +
        `${faDigits(FILE_CAP_MB)} مگابایت است — کلیپ را کوتاه‌تر کنید.`
    );
    return;
  }
  await transcribeArrayBuffer(await file.arrayBuffer(), "فایل");
};

// ---------- cancel / copy / timestamp toggle ----------

cancelBtn.onclick = () => {
  runId += 1;
  worker.terminate();
  spawnWorker(); // fresh worker; model files stay in the browser cache
  busy = false;
  recorder = null;
  endRun();
  setStage(0);
  setStatus("لغو شد — مدل در حافظهٔ مرورگر مانده و اجرای بعدی سریع است.");
  transcriptEl.textContent = "(لغو شد.)";
};

copyBtn.onclick = async () => {
  if (!lastResult) return;
  try {
    await navigator.clipboard.writeText(transcriptEl.textContent);
    copyBtn.textContent = "کپی شد";
    setTimeout(() => {
      copyBtn.textContent = "کپی متن";
    }, 1500);
  } catch (err) {
    setStatus("کپی ناموفق بود: " + err.message);
  }
};

stampChk.onchange = renderTranscript;

spawnWorker();
