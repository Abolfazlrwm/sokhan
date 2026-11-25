// Sokhan demo worker — runs Whisper entirely in the browser via
// transformers.js. The worker keeps model download + inference off the UI
// thread. Nothing about this app calls a server: the model and the audio
// both live on the visitor's machine.

import { pipeline, env } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";

// The model repos live on the HF Hub; never look for local copies.
env.allowLocalModels = false;

let asr = null;
let currentModelId = null;

async function loadModel(modelId) {
  if (asr && currentModelId === modelId) return;
  currentModelId = null;
  asr = null;
  post("status", `در حال دانلود مدل ${modelId} …`);
  asr = await pipeline("automatic-speech-recognition", modelId, {
    // q8 keeps whisper-base at ~75 MB and runs on plain WASM SIMD —
    // deterministic on every browser, no WebGPU requirement.
    dtype: { encoder_model: "q8", decoder_model_merged: "q8" },
    progress_callback: (p) => {
      if (p.status === "progress" && p.total) {
        post("progress", { file: p.file, loaded: p.loaded, total: p.total });
      }
    },
  });
  currentModelId = modelId;
  post("status", "ready");
}

async function transcribe(audioF32, modelId) {
  await loadModel(modelId);
  post("status", "در حال پیاده‌سازی …");
  const start = performance.now();
  const out = await asr(audioF32, {
    language: "fa",
    task: "transcribe",
    chunk_length_s: 30,
    stride_length_s: 5,
  });
  const elapsed = (performance.now() - start) / 1000;
  post("result", { text: (out.text || "").trim(), elapsed });
}

function post(type, payload) {
  self.postMessage({ type, payload });
}

self.onmessage = async (event) => {
  // Dedicated worker: only accept commands from the page that created us.
  // Belt-and-braces same-origin guard — the demo page and this script are
  // always served from the same origin, so anything else is not ours.
  if (event.origin !== self.location.origin) return;
  const { kind, modelId, audio } = event.data;
  try {
    if (kind === "load") {
      await loadModel(modelId);
    } else if (kind === "transcribe") {
      await transcribe(audio, modelId);
    }
  } catch (err) {
    console.error(err);
    post("error", String(err && err.message ? err.message : err));
  }
};
