// Sokhan demo worker — runs Whisper entirely in the browser via
// transformers.js. The worker keeps model download + inference off the UI
// thread and reports per-window progress so a long clip always feels
// alive instead of sitting at an eternal "processing" state.
// Nothing about this app calls a server: the model and the audio both
// live on the visitor's machine.
//
// Speed model:
// - WebGPU (Chrome/Edge with a working GPU adapter): fp32 encoder and
//   q4 decoder on the GPU — the fast path, several times faster than WASM.
// - WASM SIMD fallback (Firefox / Safari / no adapter): q8 everywhere.
//   Correct but single-threaded, so durations are capped and progress is
//   reported per 30-second window with an ETA.
//
// Chunking is done here (30 s windows, 5 s overlap, timestamp-midpoint
// trimming) instead of relying on the pipeline's chunk_length_s, because
// transformers.js 3.8.1 exposes no per-chunk callback — and owning the
// loop is what makes real progress reporting and clean caps possible.
// Segments whose midpoint falls in the non-overlapping core of each
// window are kept, which removes seam duplication without the token-level
// LCS merge the pipeline does internally.

import { pipeline, env } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";

// The model repos live on the HF Hub; never look for local copies.
env.allowLocalModels = false;

const SAMPLE_RATE = 16000;
const WINDOW_SECONDS = 30; // whisper's native window
const STRIDE_SECONDS = 5; // overlap on each side of a window
const WINDOW = WINDOW_SECONDS * SAMPLE_RATE;
const JUMP = WINDOW - 2 * STRIDE_SECONDS * SAMPLE_RATE; // 20 s of new audio per window
const MAX_SECONDS = { webgpu: 1800, wasm: 600 };

// Per-model load profiles. small/base run everywhere: fp32 encoder + q4
// decoder on WebGPU, q8 everywhere on WASM. The turbo repo is WebGPU-only
// in practice — its q8 WASM path would decode glacially slow and download
// ~1.6 GB for the privilege. fp16 needs the shader-f16 GPU feature; when
// it is missing, one retry with the fp32 encoder (a bigger download)
// runs before giving up with an honest message.
const MODEL_PROFILES = {
  "onnx-community/whisper-large-v3-turbo": {
    webgpuOnly: true,
    webgpu: { encoder_model: "fp16", decoder_model_merged: "q4" },
    webgpuFallback: { encoder_model: "fp32", decoder_model_merged: "q4" },
  },
  // The fine-tuned Sokhan checkpoint ships as an int8 ONNX build from
  // training/export_web_onnx.py: the repo carries fp32 and _quantized (q8)
  // files only, so WebGPU pairs the fp32 encoder with a q8 decoder — a q4
  // request would 404 against files that do not exist there.
  "Abol0pati/whisper-small-fa-sokhan-web": {
    webgpu: { encoder_model: "fp32", decoder_model_merged: "q8" },
    webgpuFallback: { encoder_model: "fp32", decoder_model_merged: "q8" },
  },
};
const DEFAULT_WEBGPU = { encoder_model: "fp32", decoder_model_merged: "q4" };
const DEFAULT_WASM = { encoder_model: "q8", decoder_model_merged: "q8" };

let asr = null;
let currentModelId = null;
let currentDevice = null;

function post(type, payload) {
  self.postMessage({ type, payload });
}

async function gpuAvailable() {
  try {
    if (!self.navigator || !self.navigator.gpu) return false;
    const adapter = await self.navigator.gpu.requestAdapter();
    return !!adapter;
  } catch {
    return false;
  }
}

async function loadModel(modelId, device, dtype) {
  post(
    "status",
    `در حال دانلود مدل ${modelId} (${device === "webgpu" ? "WebGPU" : "CPU"}) …`
  );
  const config =
    device === "webgpu"
      ? { device: "webgpu", dtype: dtype || DEFAULT_WEBGPU }
      : { device: "wasm", dtype: dtype || DEFAULT_WASM };
  asr = await pipeline("automatic-speech-recognition", modelId, {
    ...config,
    progress_callback: (p) => {
      if (p.status === "progress" && p.total) {
        post("progress", { file: p.file, loaded: p.loaded, total: p.total });
      }
    },
  });
  currentModelId = modelId;
  currentDevice = device;
  post("device", device);
  post("status", "ready");
}

/** Load the requested model on the fastest device this browser supports. */
async function loadBest(modelId) {
  if (asr && currentModelId === modelId) return;
  asr = null;
  currentModelId = null;
  currentDevice = null;
  const profile = MODEL_PROFILES[modelId] ?? {};
  const gpu = await gpuAvailable();
  if (!gpu && profile.webgpuOnly) {
    throw new Error(
      "این مدل فقط با WebGPU اجرا می‌شود و مرورگر شما از آن پشتیبانی نمی‌کند؛ " +
        "مدل «کوچک (small)» را انتخاب کنید."
    );
  }
  if (gpu) {
    try {
      await loadModel(modelId, "webgpu", profile.webgpu);
      return;
    } catch (err) {
      console.error("WebGPU load failed", err);
      if (profile.webgpuOnly && profile.webgpuFallback) {
        post(
          "status",
          "نسخهٔ fp16 روی GPU شما اجرا نشد — تلاش با نسخهٔ سازگارتر (دانلود بزرگ‌تر) …"
        );
        try {
          await loadModel(modelId, "webgpu", profile.webgpuFallback);
          return;
        } catch (err2) {
          console.error("WebGPU fp32 fallback failed", err2);
          throw new Error(
            "بارگذاری این مدل روی WebGPU ممکن نشد؛ مدل «کوچک (small)» را انتخاب کنید."
          );
        }
      }
      post("status", "WebGPU در دسترس نبود — بازگشت به حالت CPU …");
      asr = null;
    }
  }
  await loadModel(modelId, "wasm", profile.wasm || DEFAULT_WASM);
}

function countWindows(seconds) {
  if (!(seconds > 0)) seconds = 1;
  if (seconds <= WINDOW_SECONDS) return 1;
  return 1 + Math.ceil((seconds - WINDOW_SECONDS) / (JUMP / SAMPLE_RATE));
}

/**
 * One 30-second window -> trimmed segments with GLOBAL timestamps.
 * The window is transcribed with return_timestamps; segments whose
 * midpoint lies inside the window's non-overlapping core are kept, so
 * consecutive windows never duplicate the phrase spoken across a seam.
 */
async function transcribeWindow(samples, offsetSeconds, isFirst, isLast) {
  const out = await asr(samples, {
    language: "fa",
    task: "transcribe",
    return_timestamps: true,
  });
  const windowStart = offsetSeconds;
  const coreStart = windowStart + (isFirst ? 0 : STRIDE_SECONDS);
  const coreEnd =
    windowStart + samples.length / SAMPLE_RATE - (isLast ? 0 : STRIDE_SECONDS);
  const segments = [];
  for (const s of out.chunks || []) {
    const t0 = Array.isArray(s.timestamp) ? s.timestamp[0] ?? 0 : 0;
    const t1 = Array.isArray(s.timestamp) ? s.timestamp[1] ?? t0 : t0;
    const start = windowStart + t0;
    const end = windowStart + t1;
    const mid = (start + end) / 2;
    if (mid < coreStart || mid > coreEnd) continue;
    const text = (s.text || "").trim();
    if (!text) continue;
    segments.push({ start, end, text });
  }
  return segments;
}

async function transcribe(audio, modelId, seconds) {
  await loadBest(modelId);

  if (!seconds || seconds <= 0) seconds = audio.length / SAMPLE_RATE;
  const cap = MAX_SECONDS[currentDevice] ?? MAX_SECONDS.wasm;
  if (seconds > cap) {
    post(
      "error",
      `این فایل ${Math.round(seconds / 60)} دقیقه است؛ سقف دموی مرورگری روی ` +
        `${currentDevice === "webgpu" ? "WebGPU" : "CPU"} حدود ${Math.round(cap / 60)} دقیقه است. ` +
        "برای فایل‌های بلندتر، نسخهٔ سلف‌هاست (backend) را اجرا کنید."
    );
    return;
  }

  post("status", "در حال پیاده‌سازی …");
  const total = countWindows(seconds);
  const started = performance.now();
  const segments = [];
  let offset = 0;
  let done = 0;
  let retriedOnWasm = false;
  const profile = MODEL_PROFILES[modelId] ?? {};

  while (true) {
    const offsetEnd = offset + WINDOW;
    const sub = audio.subarray(offset, Math.min(offsetEnd, audio.length));
    const isFirst = offset === 0;
    const isLast = offsetEnd >= audio.length;
    let windowSegments;
    try {
      windowSegments = await transcribeWindow(
        sub,
        offset / SAMPLE_RATE,
        isFirst,
        isLast
      );
    } catch (err) {
      if (
        currentDevice === "webgpu" &&
        !profile.webgpuOnly &&
        !retriedOnWasm
      ) {
        // Driver hiccup on the GPU path: reload once on CPU and redo the
        // current window; earlier windows stay valid. (WebGPU-only models
        // like turbo have no usable WASM path, so they never retry here.)
        console.error("WebGPU inference failed; retrying on WASM", err);
        asr = null;
        currentModelId = null;
        await loadModel(modelId, "wasm");
        retriedOnWasm = true;
        continue;
      }
      throw err;
    }
    segments.push(...windowSegments);
    done += 1;
    const elapsed = (performance.now() - started) / 1000;
    post("chunk-progress", { done, total, elapsed });
    if (isLast) break;
    offset += JUMP;
  }

  segments.sort((a, b) => a.start - b.start);
  const text = segments
    .map((s) => s.text)
    .join(" ")
    .replace(/\s{2,}/g, " ")
    .trim();
  const elapsed = (performance.now() - started) / 1000;
  post("result", {
    text,
    segments,
    elapsed,
    device: currentDevice,
    windows: done,
  });
}

self.onmessage = async (event) => {
  // Defence-in-depth origin check. A dedicated worker can only ever be
  // messaged by the page that created it (the browser enforces this), and
  // Chromium 158+ posts such messages with an EMPTY event.origin — a
  // strict `event.origin !== self.location.origin` comparison therefore
  // swallowed every command and left the demo hanging at "processing"
  // forever. Reject only origins that are present AND foreign.
  if (event.origin && event.origin !== self.location.origin) return;
  const { kind, modelId, audio, seconds } = event.data;
  try {
    if (kind === "load") {
      await loadBest(modelId);
    } else if (kind === "transcribe") {
      await transcribe(audio, modelId, seconds);
    }
  } catch (err) {
    console.error(err);
    post("error", String(err && err.message ? err.message : err));
  }
};
