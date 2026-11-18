// Sokhan demo UI wiring — audio capture (mic / file / bundled sample),
// resampling to 16 kHz mono, and talking to the transformers.js worker.
// All inference happens client-side; see worker.js.

const SAMPLE_URL =
  "https://raw.githubusercontent.com/Abolfazlrwm/sokhan/main/benchmarks/data/clips/cv_fa_00001501_39aee6016733.wav";
// Human-verified reference from the benchmark fixture, shown for honest
// comparison after the sample is transcribed.
const SAMPLE_REFERENCE = "معلومه حسابی قاطی کردی";

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

const worker = new Worker("worker.js?v=2", { type: "module" });
let busy = false;

// ---------- worker plumbing ----------

const downloads = new Map(); // file -> { loaded, total }

worker.onmessage = (event) => {
  const { type, payload } = event.data;
  if (type === "progress") {
    downloads.set(payload.file, payload);
    const loaded = [...downloads.values()].reduce((s, d) => s + d.loaded, 0);
    const total = [...downloads.values()].reduce((s, d) => s + d.total, 0);
    if (total > 0) {
      const pct = Math.round((loaded / total) * 100);
      barEl.style.display = "block";
      barFill.style.width = `${pct}%`;
      statusEl.textContent = `در حال دانلود مدل … ${pct}%`;
    }
  } else if (type === "status" && payload === "ready") {
    barEl.style.display = "none";
    statusEl.textContent = "مدل آماده است — در حال پیاده‌سازی …";
  } else if (type === "status") {
    statusEl.textContent = payload;
  } else if (type === "result") {
    finish(payload.text, payload.elapsed);
  } else if (type === "error") {
    busy = false;
    unlock();
    barEl.style.display = "none";
    statusEl.textContent = "خطا: " + payload;
  }
};

function setStatus(text) {
  statusEl.textContent = text;
}

function startWork(message) {
  busy = true;
  lock();
  downloads.clear();
  refEl.style.display = "none";
  transcriptEl.textContent = "(در حال پردازش…)";
  metaEl.textContent = "";
  setStatus(message);
}

function finish(text, elapsedSeconds) {
  setStatus("تمام شد — می‌توانید کلیپ دیگری امتحان کنید.");
  transcriptEl.textContent = text || "(متنی تشخیص داده نشد — شاید صدا کوتاه یا نویزی بود.)";
  const audioSeconds = window.__lastAudioSeconds || 0;
  metaEl.textContent =
    `زمان پردازش: ${elapsedSeconds.toFixed(1)} ثانیه` +
    (audioSeconds ? ` برای ${audioSeconds.toFixed(1)} ثانیه صدا` : "") +
    " — کاملاً روی دستگاه شما.";
  busy = false;
  unlock();
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
  const ctx = new AudioContext({ sampleRate: 16000 });
  try {
    const buffer = await ctx.decodeAudioData(arrayBuffer);
    // Mix down to mono if the clip has multiple channels.
    let data = buffer.getChannelData(0);
    if (buffer.numberOfChannels > 1) {
      data = new Float32Array(buffer.length);
      for (let c = 0; c < buffer.numberOfChannels; c++) {
        const ch = buffer.getChannelData(c);
        for (let i = 0; i < ch.length; i++) data[i] += ch[i] / buffer.numberOfChannels;
      }
    }
    return { audio: data, seconds: buffer.duration };
  } finally {
    ctx.close();
  }
}

async function transcribeArrayBuffer(arrayBuffer, sourceLabel) {
  if (busy) return;
  await transcribeRaw(arrayBuffer, sourceLabel);
}

// Core flow without the busy guard — for callers that manage `busy`
// themselves (the sample button fetches first, then starts the pipeline).
async function transcribeRaw(arrayBuffer, sourceLabel) {
  startWork(`در حال آماده‌سازی صدا (${sourceLabel}) …`);
  try {
    const { audio, seconds } = await decodeTo16k(arrayBuffer);
    if (seconds < 0.3) {
      busy = false;
      unlock();
      transcriptEl.textContent = "(صدا خیلی کوتاه است.)";
      return;
    }
    window.__lastAudioSeconds = seconds;
    worker.postMessage({ kind: "transcribe", audio, modelId: modelSel.value });
  } catch (err) {
    console.error(err);
    busy = false;
    unlock();
    setStatus("خطا در خواندن فایل صوتی: " + err.message);
  }
}

// ---------- inputs ----------

sampleBtn.onclick = async () => {
  if (busy) return;
  busy = true;
  lock();
  downloads.clear();
  refEl.style.display = "none";
  transcriptEl.textContent = "(در حال پردازش…)";
  metaEl.textContent = "";
  setStatus("در حال دریافت کلیپ نمونه (از فیکسچر بنچمارک پروژه) …");
  try {
    const res = await fetch(SAMPLE_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    refEl.innerHTML = `<b>متن مرجع (انسان):</b> ${SAMPLE_REFERENCE}`;
    refEl.style.display = "block";
    await transcribeRaw(await res.arrayBuffer(), "نمونه");
  } catch (err) {
    busy = false;
    unlock();
    setStatus("دریافت نمونه ناموفق بود: " + err.message);
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
  await transcribeArrayBuffer(await file.arrayBuffer(), "فایل");
  fileInput.value = "";
};
