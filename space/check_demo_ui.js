// Headless validation for space/demo.js new accuracy features:
//   1. the pure WER helpers (wordLev / sampleWer) behave,
//   2. applyDefaultModel picks turbo on WebGPU, keeps small without it,
//      restores a stored choice, and refuses a stale turbo pick,
//   3. the whole module evaluates against DOM/Worker stubs.
// Run: node space/check_demo_ui.js   (plain node, no dependencies)
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const os = require("os");

const source = fs.readFileSync(path.join(__dirname, "demo.js"), "utf8");

function makeEl(value) {
  return {
    value: value || "",
    textContent: "",
    innerHTML: "",
    style: {},
    dataset: {},
    disabled: false,
    options: [],
    firstElementChild: { style: {} },
    classList: { add() {}, remove() {}, toggle() {} },
    _handlers: {},
    addEventListener(type, fn) {
      this._handlers[type] = fn;
    },
    onchange: null,
  };
}

const tests = `
const { strict: assert } = await import("node:assert");

// ---- 1. pure WER helpers ----
assert.strictEqual(wordLev(["a","b","c"], ["a","b","c"]), 0, "identical");
assert.strictEqual(wordLev(["a","b","c"], ["a","x","c"]), 1, "one sub");
assert.strictEqual(wordLev(["a","b"], ["a","b","c","d"]), 2, "insertions");
assert.strictEqual(wordLev([], ["a"]), 1);

// identical transcript -> 0 WER even with a trailing punctuation mark
assert.strictEqual(sampleWer("معلومه حسابی قاطی کردی."), 0, "exact + punct");
// one word missing out of four -> 25% (edit distance / reference words)
assert.strictEqual(sampleWer("معلومه قاطی کردی"), 25, "one word missing");
// gibberish of the same length -> 100%
assert.strictEqual(sampleWer("foo bar baz"), 100, "totally wrong");
// empty hypothesis -> null (nothing to judge)
assert.strictEqual(sampleWer(""), null, "empty hyp");

// ---- 2. model auto-pick ----
async function pick(storedPick, hasGpu) {
  globalThis.__stored = storedPick;
  globalThis.__navStub = {
    gpu: hasGpu ? { requestAdapter: async () => ({}) } : undefined,
  };
  // The module captured modelSel/modelHint at load time, so mutate THOSE
  // elements instead of replacing them.
  const el = globalThis.__els["model"];
  el.value = "Xenova/whisper-small";
  el.options = [
    { value: "onnx-community/whisper-large-v3-turbo" },
    { value: "Xenova/whisper-small" },
    { value: "Abol0pati/whisper-small-fa-sokhan-web" },
    { value: "Xenova/whisper-base" },
  ];
  globalThis.__els["model-hint"].textContent = "";
  await applyDefaultModel();
  return { value: el.value, hint: globalThis.__els["model-hint"].textContent, el };
}

let r = await pick(null, true);
assert.strictEqual(r.value, "onnx-community/whisper-large-v3-turbo",
  "WebGPU + no stored pick -> turbo");
assert.ok(r.hint.includes("WebGPU"), "hint explains the auto-pick");

r = await pick(null, false);
assert.strictEqual(r.value, "Xenova/whisper-small",
  "no WebGPU + no stored pick -> small default");
assert.strictEqual(r.hint, "", "no noise hint on the plain default");

r = await pick("Xenova/whisper-base", false);
assert.strictEqual(r.value, "Xenova/whisper-base",
  "stored non-turbo pick restores anywhere");
assert.ok(r.hint.length > 0, "restore hint shown");

r = await pick("onnx-community/whisper-large-v3-turbo", false);
assert.strictEqual(r.value, "Xenova/whisper-small",
  "stale turbo pick on a WebGPU-less browser falls back to small");
assert.ok(r.hint.includes("WebGPU"), "fallback hint explains itself");

r = await pick("onnx-community/whisper-large-v3-turbo", true);
assert.strictEqual(r.value, "onnx-community/whisper-large-v3-turbo",
  "stored turbo pick restores where WebGPU exists");

// ---- 3. the fine-tuned ONNX option is wired end to end ----
const FINETUNED = "Abol0pati/whisper-small-fa-sokhan-web";
assert.ok(INDEX_HTML.includes('value="' + FINETUNED + '"'),
  "index.html lists the fine-tuned repo as an <option>");
assert.ok(WORKER_SOURCE.includes('"' + FINETUNED + '"'),
  "worker.js carries the fine-tuned load profile");
r = await pick(FINETUNED, false);
assert.strictEqual(r.value, FINETUNED,
  "stored fine-tuned pick restores on a WebGPU-less browser");

// change listener persists the pick and clears the hint
let persisted = null;
globalThis.__setStored = (v) => { persisted = v; };
r = await pick("Xenova/whisper-base", true);
r.el._handlers.change();
assert.strictEqual(persisted, "Xenova/whisper-base", "change persists choice");
assert.strictEqual(globalThis.__els["model-hint"].textContent, "",
  "hint cleared on change");

console.log("all demo UI checks passed");
`;

const prelude = `
globalThis.__els = {};
globalThis.__stored = null;
globalThis.__navStub = { gpu: undefined };
globalThis.__makeEl = ${makeEl.toString()};
globalThis.__setStored = () => {};
const document = {
  getElementById: (id) => (globalThis.__els[id] ??= globalThis.__makeEl()),
  querySelectorAll: () => [],
};
const localStorage = {
  getItem: () => globalThis.__stored,
  setItem: (_k, v) => globalThis.__setStored(v),
};
const Worker = class { constructor() {} terminate() {} postMessage() {} };
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  get: () => globalThis.__navStub,
});
function makeEl(value) {
  return globalThis.__makeEl(value);
}
`;

const harness = `
// the space files are read here, in the CommonJS host, and injected as
// string literals — the assembled temp module must stay dependency-free
const INDEX_HTML = ${JSON.stringify(fs.readFileSync(path.join(__dirname, "index.html"), "utf8"))};
const WORKER_SOURCE = ${JSON.stringify(fs.readFileSync(path.join(__dirname, "worker.js"), "utf8"))};
globalThis.__run = async () => {
${tests.trim()}
};
globalThis.__run()
  .then(() => process.exit(0))
  .catch((err) => { console.error("FAIL:", err.message); process.exit(1); });
`;

const code = `${prelude}\n${source}\n${harness}`.replace(
  "spawnWorker();\napplyDefaultModel();",
  "spawnWorker();\n// applyDefaultModel is driven per-case by the tests, not at load"
);

const tmp = path.join(os.tmpdir(), "sokhan_demo_ui_check.mjs");
fs.writeFileSync(tmp, code);
execSync(`node "${tmp}"`, { stdio: "inherit" });
console.log("check_demo_ui: OK");
