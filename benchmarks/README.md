# WER benchmark

A small, reproducible word-error-rate benchmark for the transcription engine
on **real Persian speech**: 12 clips from **Mozilla Common Voice (fa)** — real
human recordings with human-verified transcripts, released under CC-0. The
clips and their references ship in this directory (`data/`), so anyone can
re-run the exact same evaluation.

## What is measured

- Engine: faster-whisper, CPU, `int8`, `beam_size=5`, language hint `fa`
- Metric: WER and CER computed with [jiwer](https://pypi.org/project/jiwer/)
- Normalization: both the reference and the hypothesis go through the same
  `sokhan.core.persian.normalize_persian` used by the product's search, so
  Arabic/Persian look-alike characters and digit forms cannot create
  artificial errors

## Latest results (v3 stack, measured 2026-11-27)

Total audio: 61.1 s across 12 clips (3.5–6.9 s each), faster-whisper 1.2.1,
CTranslate2 4.9.1, CPU int8. The v3 decode stack mirrors the product engine
exactly (`backend/sokhan/core/transcribe.py`): **no initial prompt, the VAD
filter on, and a language-drift guard** — a forced-fa decode that comes back
mostly in another script is retried once deterministically (temperature 0,
VAD forced on) and the more-Persian result wins.

| Model | Params | WER (v3) | CER (v3) | Wall time | vs v2 |
| --- | --- | --- | --- | --- | --- |
| tiny | 39 M | 93.8% | 42.7% | 15.8 s | +1.1 |
| Abol0pati/whisper-tiny-fa-sokhan (fine-tuned) | 39 M | 95.0% | 38.8% | 6.1 s | −8.7 |
| small | 244 M | 70.0% | 25.0% | 24.7 s | −5.0 |
| Abol0pati/whisper-small-fa-sokhan (fine-tuned) | 244 M | 66.2% | 22.9% | 23.0 s | −8.8 |
| medium | 769 M | 48.8% | 15.4% | 68.2 s | −7.4 |
| **large-v3-turbo (default)** | 809 M | **37.5%** | **9.9%** | 84.5 s | −6.3 |

Every guarded model improved — the v2 orthography prompt was actively
hurting the modern decode configs, and the drift guard recovers a clip
that Whisper decoded as **Icelandic** (`در هر حال اینکارو کردی` →
`Er hær hálf einhver kjærði?`, retried → `ار هر حال انکار کردی`). The
fine-tuned row is measured in [the fine-tuned section below](#the-fine-tuned-checkpoint-under-the-v3-stack-measured-2026-11-27)
— under the stack the product actually ships, the LoRA checkpoint now
beats untuned `small` by 3.8 WER points. The tiny class is measured for
completeness (both rows, 2026-11-27 sessions archived under
`results/archive/`): the v3 stack narrows most of the fine-tuned tiny's
v1 gap (103.7% → 95.0%) and cuts its CER below untuned tiny (38.8% vs
42.7%), but tiny-scale LoRA still does not win on WER — the honest
tiny-class conclusion in the model card stands.

The v4 sweep (`--quick`-style probes over beam 3/8, best_of+patience,
temperature 0, `condition_on_previous_text`) moved nothing else: beam 5
stays. The remaining errors on the fixture are acoustic (colloquial
pronunciations like «نمردیمو معنی عدالتم فهمیدیم») or metric noise
(written-vs-spoken variants counted as errors), not decode settings.

Why not `large-v3`? It measured well in isolation but **needs >3.4 GB RAM
just to load** (int8), which OOMs on small VPS boxes — the turbo default
keeps the same memory class as `medium`. On a GPU host it remains one
environment variable away: `WHISPER_MODEL_SIZE=large-v3`.

## The fine-tuned checkpoint under the v3 stack (measured, 2026-11-27)

The LoRA fine-tune of `whisper-small` (500 clips, free Colab T4) was
previously measured under the v1 harness only, where it beat untuned
`small` by 1.2 WER points (79.3% vs 80.5%) and tied it under v2 (75.0%).
Re-measured with the v3 decode stack — beam 5, VAD on, no prompt, drift
guard, the exact product engine — it moves to **WER 66.2% / CER 22.9%**,
now **3.8 points better than untuned `small` (70.0%)**. The stack's
improvements compound on the fine-tuned weights; the full per-clip output
lives in
[results/archive/20261127-131850-Abol0pati_whisper-small-fa-sokhan.json](results/archive/20261127-131850-Abol0pati_whisper-small-fa-sokhan.json).

Practical consequences, both measured and honest:

- **Small-RAM deployments get a better engine today, with no code
  change.** faster-whisper loads the Hub repo id directly, so
  `WHISPER_MODEL_SIZE=Abol0pati/whisper-small-fa-sokhan` replaces
  `small` on boxes that cannot fit `medium`/turbo RAM.
- **The browser demo keeps `Xenova/whisper-small` for now.** The
  fine-tuned checkpoint is published as a CTranslate2 build only
  (`model.bin`); transformers.js needs ONNX exports the repo does not
  carry yet. Publishing the merged PyTorch checkpoint (or running
  [training/export_web_onnx.py](../training/export_web_onnx.py) against
  it) unlocks a −3.8-point demo upgrade — tracked on the roadmap.

## Does the browser demo need beam search? (measured: no)

The demo decodes greedily (transformers.js default) while the backend
engine runs beam 5 — an apparent gap worth measuring rather than
assuming. On this fixture, with the same `small` model and the product
protocol, beam search moves nothing: **beam 1 (greedy) 70.0% WER, beam 2
71.2%, beam 5 70.0%** (v2 normalization, VAD on, drift guard). The repo's
own sweep harness agrees under its v1-style normalization:

    python benchmarks/tune_decode.py --models small --beams 1 5

measures 79.3% for both beam widths. Greedy stays the demo's decode: it
matches beam-5 accuracy at ~10–15% less wall time, which on a 2-core
browser tab is the difference visitors feel. If a future fixture ever
shows a gap, wiring `num_beams` into `space/worker.js` is a one-line
change.

## Extending the fixture (issue #29)

Twelve clips put a ~1 WER-point difference near the noise floor; issue #29
wants 30+ verified clips so deltas become solid. The fixture's whole value
is that its references are **human-verified** — listening cannot be
automated, so [extend_fixture.py](extend_fixture.py) automates everything
around it and keeps the promotion a human step:

    pip install -r benchmarks/requirements.txt   # adds pyarrow + soundfile
    python benchmarks/extend_fixture.py --count 20

It samples clips from the mirror's held-out `test` split (the same CC-0
corpus the training pipeline uses — and a split the fine-tune never saw),
filters to the fixture's duration/word band, dedupes against the existing
references, then runs each candidate through two independent engines under
the v3 protocol and records both transcripts + their agreement WER in
`data/candidates/candidates.csv` (agreement ≤ 25% is pre-flagged
`keep=yes`; disagreement flags noisy clips worth skipping). It never
touches `manifest.csv` — the human listens, corrects, appends verified
rows, commits, and re-runs the benchmark session. The default engine pair
is the best-measured one (`large-v3-turbo` + `medium`); pass
`--engines tiny base` for a cheap smoke run.

## Previous sessions

### v2 stack (measured, 2026-11-18)

Total audio: 61.1 s across 12 clips (3.5–6.9 s each). All five models were
measured back to back in one session, same library versions
(faster-whisper 1.2.1, CTranslate2 4.9.0).

| Model | Params | WER | CER |
| --- | --- | --- | --- |
| tiny | 39 M | 92.7% | 44.3% |
| base | 74 M | 90.2% | 37.6% |
| small | 244 M | 80.5% | 26.7% |
| Abol0pati/whisper-tiny-fa-sokhan (fine-tuned, CPU run) | 39 M | 103.7% | 47.4% |
| **Abol0pati/whisper-small-fa-sokhan (fine-tuned, GPU run)** | 244 M | **79.3%** | **24.9%** |

The table above is the **v1 harness** (no prompt, `normalize_persian` only).
The **v2 accuracy stack** changed two things, each measured in isolation
with [tune_decode.py](tune_decode.py):

1. **Persian orthography initial prompt** — whisper copies the script style
   of the prompt, so a ZWNJ-correct Persian prompt nudges the decoder
   towards standard written forms: −1.3 WER points on `small` (79.3% →
   78.0%), −4.8 on the fine-tuned checkpoint (76.8% → 72.0%), both under
   the sweep harness with the same normalization.
2. **`fa_polish` orthographic post-processing** (same module the backend
   pipeline applies) on both sides: −3.6 WER points.

v2 numbers (prompt + polish, both sides, CPU int8, beam 5 — from
[results/results.json](results/results.json), regenerated by the same
command):

| Model | Params | WER (v2) | CER (v2) | Wall time |
| --- | --- | --- | --- | --- |
| small | 244 M | 75.0% | 25.0% | 24.7 s |
| Abol0pati/whisper-small-fa-sokhan (fine-tuned) | 244 M | 75.0% | 31.0% | 25.3 s |
| **medium (new backend default)** | 769 M | **56.2%** | **18.5%** | 75.5 s |

`medium` is the single biggest accuracy lever available without more
training: **−24.3 WER points vs the old default** at ~1.1x realtime on 2
CPU cores (61.1 s of audio in 75.5 s). Decode sweep detail (small, beam 5):

| prompt | cond_prev | WER |
| --- | --- | --- |
| none | true | 79.3% |
| orthography | true | 78.0% |
| domain (no orthography) | true | 79.3% |
| orthography | false | 78.0% |
| orthography, beam 8 | true | 80.5% |

beam 8 hurts on `small`; VAD on/off is a wash on these clean clips; the
orthography prompt helped `small` — the v3 session above shows the same
prompt hurting `large-v3-turbo`, which is why the default engine no longer
sends one.

Earlier sessions are archived so every published number stays reproducible:
[results-2026-11-13.json](results/results-2026-11-13.json) (tiny 93.9% /
base 90.2% / small 80.5%) and
[results-2026-11-15.json](results/results-2026-11-15.json) (first
four-model session). tiny drifted 93.9% → 92.7% and its CER 43.5% → 44.3%
between library versions — that is version noise, not a fixture change;
the fixture is identical. Full per-clip output of the current run lives
in [results/results.json](results/results.json).

## Regression baseline (v3)

[results/baseline.json](results/baseline.json) records the v3 numbers for
`small`, `medium` and `large-v3-turbo`; the weekly benchmark workflow runs
all three against it with a +1.0-point tolerance. If you change the decode
stack or the polish module, regenerate the baseline with the same command
so the gate compares apples to apples:

    python benchmarks/benchmark_wer.py --models small medium large-v3-turbo

## First GPU-scale fine-tune (measured, 2026-11-18)

The GPU-scale run the CPU experiment was waiting for actually happened, on
a **free Colab T4** via `training/finetune_fa_colab.ipynb`: LoRA on
`whisper-small`, **500 clips (≈45 minutes of speech)** from the *train*
split of the same CC-0 mirror, 3 epochs, 186 optimizer steps — **~7
minutes of wall time**. Training loss 3.63 → 1.75, held-out eval loss
2.154 → 1.712, held-out eval WER 85.1% → 81.6%.

On this fixture it is the **first fine-tune that beats its own baseline**:
WER 80.5% → **79.3%** (−1.2 points) and CER 26.7% → **24.9%** (−1.8
points), measured CPU int8 exactly like the baseline row.

Honest caveats, per project policy:

- A 12-clip fixture puts a ~1-point difference close to the noise floor;
  the direction is consistent with the in-training eval WER, but treat
  the magnitude as indicative, not precise.
- The model saw ≈45 minutes of speech. This proves the pipeline moves the
  number; it does not yet show the ceiling.
- Published artifact (re-benchmark it yourself):
  [Abol0pati/whisper-small-fa-sokhan](https://huggingface.co/Abol0pati/whisper-small-fa-sokhan)

```bash
python benchmarks/benchmark_wer.py --models small Abol0pati/whisper-small-fa-sokhan
```

Update 2026-11-27: re-measured under the v3 decode stack this checkpoint
moves to WER 66.2% / CER 22.9% — now clearly ahead of untuned `small`.
See [the fine-tuned section above](#the-fine-tuned-checkpoint-under-the-v3-stack-measured-2026-11-27).

Next run on the same notebook: `MAX_SAMPLES = 0` (the full 10-hour
manifest) — roughly 1.5–2 h on a free T4 — should turn this small gain
into a meaningful one.

## First fine-tune run (measured, 2026-11-15)

The project's first real fine-tune ran end to end **on CPU, no GPU**: LoRA
on `whisper-tiny`, 518 clips / 45.0 minutes from the *train* split of
`pymmdrza/Common-Voice-Speech-26.0-Persian-Clean` (CC-0), 2 epochs, 508
optimizer steps. Training loss fell 3.84 → 1.55 and held-out eval loss
1.646 → 1.545, but **WER did not improve**: 94.6% on the in-training
hold-out (flat across both epochs) and 103.7% on this fixture versus 92.7%
for the untuned tiny. The converted model is published anyway, as the
reproducible artifact of that run:
[Abol0pati/whisper-tiny-fa-sokhan](https://huggingface.co/Abol0pati/whisper-tiny-fa-sokhan)
— re-benchmark it yourself:

```bash
python benchmarks/benchmark_wer.py --models Abol0pati/whisper-tiny-fa-sokhan
```

The honest conclusion of that CPU run: at `whisper-tiny` scale (45 minutes
of data, 2 epochs) LoRA does not improve Persian WER — the follow-up GPU
run at `whisper-small` scale is measured in the next section, and it does.

## How to read these numbers

They are high, and that is the honest result. Two reasons:

1. **Common Voice fa is hard.** The clips are colloquial, crowd-sourced,
   often noisy recordings with informal pronunciations and disfluencies.
   Published Whisper results on Common Voice Persian are consistently far
   worse than on read, studio-quality speech.
2. **Small models struggle with colloquial Persian.** The trend across
   tiny → base → small shows the expected improvement; `small` (the Sokhan
   default) is the best of the three. Read, literary speech is noticeably
   easier: the same `small` engine transcribed a classical poetry recitation
   from the same corpus with a single word error out of 12.

These numbers describe the engine on *this* fixed public sample. They are
not a claim about any other audio. To evaluate on your own material, put
clips + references in the manifest format and extend the script.

## Reproduce

```bash
pip install -e "backend[dev]"
pip install -r benchmarks/requirements.txt
python benchmarks/benchmark_wer.py --models tiny base small
```

Model weights are downloaded automatically on first use (~75 MB tiny,
~140 MB base, ~460 MB small). Any Hugging Face repo id can take the place
of a size name, which is how the fine-tuned rows above are produced.

## Data attribution

- Audio + references: Mozilla Common Voice, Persian (fa), clean subset,
  [CC-0](https://creativecommons.org/publicdomain/zero/1.0/), obtained via
  the public mirror `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean`
  (Common Voice release 26.0). 12 clips sampled with a fixed seed
  (`random.seed(7)`) from the 96 test rows whose audio shipped in that
  mirror.
