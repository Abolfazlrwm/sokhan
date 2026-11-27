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

// Best-accuracy engine (measured 37.5% WER on the Persian server fixture vs
// 70.0% for small — benchmarks/README.md). Auto-selected on WebGPU browsers;
// small stays the default everywhere else. The user's manual pick is
// remembered, but only ever restored when the browser can still run it.
const TURBO_MODEL = "onnx-community/whisper-large-v3-turbo";
const MODEL_STORE_KEY = "sokhan-model";

const SAMPLE_RATE = 16000;
const FILE_CAP_MB = 60; // pre-decode guard; protects RAM on giant uploads
const ABS_MAX_SECONDS = 1800; // hard ceiling even on WebGPU (30 min)
const DECODE_TIMEOUT_MS = 45000; // watchdog: decodeAudioData must resolve

const $ = (id) => document.getElementById(id);
const modelSel = $("model");
const modelHint = $("model-hint");
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

// ---------- Persian orthographic polish (v2) ----------
// Deterministic port of backend/sokhan/core/fa_polish.py: repairs ZWNJ
// placement ("می کنی" -> "می‌کنی"), split imperatives ("بی پوش" ->
// "بپوش"), Arabic look-alike code points and Latin digits. It never
// rewords — measured -3.6 WER points on the Persian fixture.

const _ZWNJ = "\u200c";
const POLISH_ARABIC_CHARS = {
  "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "\u0640": "",
  "٠": "۰", "١": "۱", "٢": "۲", "٣": "۳", "٤": "۴",
  "٥": "۵", "٦": "۶", "٧": "۷", "٨": "۸", "٩": "۹",
};

function polishChars(text) {
  let out = "";
  for (const ch of text) {
    if (ch in POLISH_ARABIC_CHARS) out += POLISH_ARABIC_CHARS[ch];
    else if (ch >= "0" && ch <= "9") out += String.fromCharCode(0x06f0 + (ch.charCodeAt(0) - 48));
    else out += ch;
  }
  return out;
}

// Very common verbs Whisper writes without the ZWNJ: "میکنم" -> "می‌کنم".
const POLISH_ZWNJ_WORDS = new Set([
  "میکنم", "میکنی", "میکند", "میکنیم", "میکنید", "میکنند",
  "میشوم", "میشوی", "میشود", "میشویم", "میشوید", "میشوند",
  "میگویم", "میگویی", "میگوید", "میگوییم", "میگویید", "میگویند",
  "میگم", "میگی", "میگه", "میگن",
  "میخواهم", "میخواهی", "میخواهد", "میخواهیم", "میخواهید", "میخواهند",
  "میخوام", "میخوای", "میخواد", "میخوان",
  "میدانم", "میدانی", "میداند", "میدانیم", "میدانید", "میدانند",
  "میدم", "میدی", "میده", "میدن",
  "میبرم", "میبری", "میبرد", "میبریم", "میبرید", "میبرند",
  "میرم", "میری", "میره", "میرن",
  "میروم", "میروی", "میرود", "میرویم", "میروید", "میروند",
  "میآیم", "میآیی", "میآید", "میآییم", "میآیید", "میآیند",
  "میشنوم", "میشنوی", "میشنود", "میشنویم", "میشنوید", "میشنوند",
  "میبینم", "میبینی", "میبیند", "میبینیم", "میبینید", "میبینند",
  "میشه",
  "نمیکنم", "نمیکنی", "نمیکند", "نمیکنیم", "نمیکنید", "نمیکنند",
  "نمیشود", "نمیشه",
  "نمیگویم", "نمیگم", "نمیگی", "نمیگه", "نمیگن",
  "نمیخواهم", "نمیخواهد", "نمیخوام", "نمیخواد",
  "نمیدانم", "نمیدانی", "نمیداند",
  "نمیدونم", "نمیدونی", "نمیدونه", "نمیدونن",
  "نمیدم", "نمیدی", "نمیده", "نمیدن",
  "نمیرم", "نمیری", "نمیره", "نمیرن", "نمیرود",
  "نمیآید", "نمیاد",
  "نمیبینم", "نمیبینی", "نمیبیند",
]);

// The imperative "ب" mis-heard as the real word "بی": "بی پوش" -> "بپوش".
const POLISH_SPLIT_IMPERATIVES = {
  "پوش": "بپوش", "بین": "ببین", "بینم": "ببینم", "بینی": "ببینی",
  "بینید": "ببینید", "بینند": "ببینند", "خواب": "بخواب", "خور": "بخور",
  "شین": "بشین", "نشین": "بنشین", "گیر": "بگیر", "گو": "بگو",
  "گوی": "بگو", "بخش": "ببخش",
};

// Separated ZWNJ prefixes/suffixes: "می کنم" -> "می‌کنم".
const POLISH_FUSED_PREFIXES = {
  "می کنم": "می‌کنم", "می کنی": "می‌کنی", "می کند": "می‌کند",
  "می کنیم": "می‌کنیم", "می کنید": "می‌کنید", "می کنند": "می‌کنند",
  "می شود": "می‌شود", "می شن": "می‌شن", "می شه": "می‌شه",
  "می گویم": "می‌گویم", "می گوید": "می‌گوید", "می گم": "می‌گم",
  "می گی": "می‌گی", "می گه": "می‌گه", "می گن": "می‌گن",
  "می خواهم": "می‌خواهم", "می خواهد": "می‌خواهد",
  "می خوام": "می‌خوام", "می خواد": "می‌خواد",
  "می دانم": "می‌دانم", "می داند": "می‌داند",
  "می دونم": "می‌دونم", "می دم": "می‌دم", "می دی": "می‌دی",
  "می ده": "می‌ده", "می دن": "می‌دن",
  "می برم": "می‌برم", "می برد": "می‌برد",
  "می رم": "می‌رم", "می ره": "می‌ره", "می رن": "می‌رن",
  "می روم": "می‌روم", "می رود": "می‌رود",
  "می آید": "می‌آید", "می این": "می‌این",
  "می شنوم": "می‌شنوم", "می شنوی": "می‌شنوی", "می شنود": "می‌شنود",
  "می بینم": "می‌بینم", "می بینی": "می‌بینی", "می بیند": "می‌بیند",
  "نمی کنم": "نمی‌کنم", "نمی کند": "نمی‌کند",
  "نمی شود": "نمی‌شود", "نمی شه": "نمی‌شه",
  "نمی گم": "نمی‌گم", "نمی گه": "نمی‌گه",
  "نمی خوام": "نمی‌خوام", "نمی خواد": "نمی‌خواد",
  "نمی دانم": "نمی‌دانم", "نمی دونم": "نمی‌دونم",
  "نمی رم": "نمی‌رم", "نمی ره": "نمی‌ره", "نمی آید": "نمی‌آید",
  "نمی این": "نمی‌این", "نمی بینم": "نمی‌بینم", "نمی بیند": "نمی‌بیند",
};
const POLISH_PREFIXES = new Set(["می", "نمی"]);
const POLISH_SUFFIXES = new Set(["ها", "های", "هایی", "تر", "ترین"]);
const POLISH_PUNCT_EDGES = "،؛:.!?؟…«»()\"'-–—,";
const POLISH_CLOSING_PUNCT = "،؛:.!?؟…»)";

function polishSplitEdges(token) {
  // Mirror Python's str.strip(chars): peel edge punctuation both sides.
  let start = 0;
  let end = token.length;
  while (start < end && POLISH_PUNCT_EDGES.includes(token[start])) start++;
  while (end > start && POLISH_PUNCT_EDGES.includes(token[end - 1])) end--;
  return [token.slice(0, start), token.slice(start, end), token.slice(end)];
}

function polishZwnjInWord(word) {
  if (word.startsWith("نمی") && word.length > 3) return "نمی" + _ZWNJ + word.slice(3);
  if (word.startsWith("می") && word.length > 2) return "می" + _ZWNJ + word.slice(2);
  return word;
}

function polishFuse(tokens) {
  const out = [];
  for (let i = 0; i < tokens.length; i++) {
    const tok = tokens[i];
    const bare = tok.split("").filter((c) => !POLISH_PUNCT_EDGES.includes(c)).join("") || tok;
    const isClean = tok === bare;
    if (POLISH_PREFIXES.has(bare) && i + 1 < tokens.length && isClean) {
      const fused = POLISH_FUSED_PREFIXES[`${tok} ${tokens[i + 1]}`] ?? `${tok}${_ZWNJ}${tokens[i + 1]}`;
      out.push(fused);
      i++;
      continue;
    }
    if (POLISH_SUFFIXES.has(bare) && out.length && isClean) {
      const prev = out[out.length - 1];
      const prevCore = prev.split("").filter((c) => !POLISH_PUNCT_EDGES.includes(c)).join("");
      if (prevCore && /[\u0600-\u06FF]/.test(prevCore[prevCore.length - 1])) {
        out[out.length - 1] = prev + _ZWNJ + bare;
        continue;
      }
    }
    out.push(tok);
  }
  return out.join(" ");
}

function polishTokens(text) {
  const tokens = text.split(/\s+/).filter(Boolean);
  const fixed = [];
  for (const token of tokens) {
    const [leading, core, trailing] = polishSplitEdges(token);
    if (!core) { fixed.push(token); continue; }
    const repaired = POLISH_ZWNJ_WORDS.has(core) ? polishZwnjInWord(core) : core;
    fixed.push(leading + repaired + trailing);
  }
  const fused = polishFuse(fixed).split(/\s+/);
  const repaired = [];
  for (const token of fused) {
    const core = polishSplitEdges(token)[1];
    const prev = repaired.length ? repaired[repaired.length - 1] : "";
    const prevCore = prev.split("").filter((c) => !POLISH_PUNCT_EDGES.includes(c)).join("");
    if (core && POLISH_SPLIT_IMPERATIVES[core] && (prevCore === "بی" || prevCore === "به")) {
      repaired[repaired.length - 1] = POLISH_SPLIT_IMPERATIVES[core];
      continue;
    }
    repaired.push(token);
  }
  return repaired.join(" ");
}

function polishSpacing(text) {
  text = text.split(_ZWNJ + " ").join(_ZWNJ).split(" " + _ZWNJ).join(_ZWNJ);
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (POLISH_CLOSING_PUNCT.includes(ch) && out.endsWith(" ")) out = out.slice(0, -1);
    out += ch;
    const nxt = text[i + 1] || "";
    if (POLISH_CLOSING_PUNCT.includes(ch) && nxt && !POLISH_CLOSING_PUNCT.includes(nxt) && nxt !== " ") {
      const prevCh = out.length >= 2 ? out[out.length - 2] : "";
      const digitClass = /[0-9\u06F0-\u06F9]/;
      const isDecimal = ch === "." && digitClass.test(prevCh) && digitClass.test(nxt);
      if (!isDecimal) out += " ";
    }
  }
  return out;
}

function polishTranscript(text) {
  if (!text || !text.trim()) return text;
  return polishSpacing(polishTokens(polishChars(text))).trim();
}

function polishTranscriptParagraph(text) {
  return text.split("\n").map((line) => polishTranscript(line)).join("\n");
}

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

// ---------- model auto-pick ----------
// WebGPU browsers get the best-measured engine by default; everyone else
// keeps small. An explicit choice (localStorage) wins, but a stored turbo
// pick is only restored when this browser still supports WebGPU.

async function gpuAvailable() {
  try {
    if (!navigator.gpu) return false;
    const adapter = await navigator.gpu.requestAdapter();
    return !!adapter;
  } catch {
    return false;
  }
}

async function applyDefaultModel() {
  const stored = localStorage.getItem(MODEL_STORE_KEY);
  const valid = [...modelSel.options].some((o) => o.value === stored);
  const gpu = await gpuAvailable();
  if (stored && valid && (stored !== TURBO_MODEL || gpu)) {
    modelSel.value = stored;
    modelHint.textContent =
      stored === TURBO_MODEL
        ? "انتخاب قبلی شما (حداکثر دقت) بازیابی شد."
        : "انتخاب قبلی شما بازیابی شد.";
    return;
  }
  if (gpu) {
    modelSel.value = TURBO_MODEL;
    modelHint.textContent =
      "WebGPU شناسایی شد — دقیق‌ترین مدل (بهترین عدد بنچمارک فارسی) خودکار انتخاب شد؛ مدل سبک‌تر را می‌توانید از فهرست برگزینید.";
  } else if (stored === TURBO_MODEL) {
    // A turbo pick carried over from a WebGPU browser cannot run here.
    modelHint.textContent =
      "انتخاب قبلی شما فقط روی WebGPU اجرا می‌شود؛ روی این مرورگر مدل کوچک پیش‌فرض شد.";
  }
}

modelSel.addEventListener("change", () => {
  localStorage.setItem(MODEL_STORE_KEY, modelSel.value);
  modelHint.textContent = "";
});

// ---------- sample WER (one clip, approximate) ----------
// The bundled sample has a human-verified reference, so after it is
// transcribed we can show an honest per-run word error rate. Both sides go
// through the same polish pass, punctuation is ignored — the same
// normalization philosophy as benchmarks/benchmark_wer.py, minus jiwer.

const WER_PUNCT = /[،؛:.!?؟…«»()"'،\-–—,]/g;

function werWords(text) {
  return polishTranscript(text)
    .replace(WER_PUNCT, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function wordLev(a, b) {
  // DP edit distance over word lists (both tiny: <= 30 words).
  const prev = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    let diag = prev[0];
    prev[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const above = prev[j];
      prev[j] = Math.min(
        prev[j] + 1,
        prev[j - 1] + 1,
        diag + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
      diag = above;
    }
  }
  return prev[b.length];
}

function sampleWer(hypText) {
  const ref = werWords(SAMPLE_REFERENCE);
  const hyp = werWords(hypText);
  if (!ref.length || !hyp.length) return null;
  return Math.round((wordLev(ref, hyp) / ref.length) * 100);
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
let isSampleRun = false; // the bundled sample has a reference -> show WER

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
  isSampleRun = false;
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
  if (isSampleRun) {
    // startWork hid the reference box while processing; bring it back so the
    // human transcript AND the per-run WER are both visible at the end.
    refEl.style.display = "block";
    const wer = sampleWer(lastResult.text);
    isSampleRun = false;
    if (wer !== null) {
      const cls = wer <= 20 ? "var(--ok)" : wer >= 60 ? "var(--err)" : "inherit";
      refEl.innerHTML +=
        `<br>خطای واژه‌ای این اجرا روی همان کلیپ: <b style="color:${cls}">` +
        `${faDigits(wer)}٪</b> (کمتر بهتر — یک کلیپ، تقریبی)`;
    }
  }
  copyBtn.style.display = "inline-block";
}

function renderTranscript() {
  if (!lastResult) return;
  if (stampChk.checked && lastResult.segments.length) {
    const lines = lastResult.segments.map(
      (s) =>
        `[${mmss(s.start)}–${mmss(s.end)}] ` +
        restorePunctuation(polishTranscript(s.text))
    );
    transcriptEl.textContent = lines.join("\n");
  } else {
    transcriptEl.textContent =
      restorePunctuationParagraph(polishTranscriptParagraph(lastResult.text)) ||
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
  isSampleRun = true; // finish() will report the sample's word error rate
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
applyDefaultModel();
