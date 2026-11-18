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

## Latest results (measured, 2026-11-18)

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

Earlier sessions are archived so every published number stays reproducible:
[results-2026-11-13.json](results/results-2026-11-13.json) (tiny 93.9% /
base 90.2% / small 80.5%) and
[results-2026-11-15.json](results/results-2026-11-15.json) (first
four-model session). tiny drifted 93.9% → 92.7% and its CER 43.5% → 44.3%
between library versions — that is version noise, not a fixture change;
the fixture is identical. Full per-clip output of the current run lives
in [results/results.json](results/results.json).

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
