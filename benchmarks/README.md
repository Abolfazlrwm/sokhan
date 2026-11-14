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

## Latest results (measured, 2026-11-15)

Total audio: 61.1 s across 12 clips (3.5–6.9 s each). All four models were
measured back to back in one session, same library versions.

| Model | Params | WER | CER |
| --- | --- | --- | --- |
| tiny | 39 M | 92.7% | 43.5% |
| base | 74 M | 90.2% | 37.6% |
| small | 244 M | 80.5% | 26.7% |
| Abol0pati/whisper-tiny-fa-sokhan (fine-tuned) | 39 M | 103.7% | 47.4% |

The 2026-11-13 runs (tiny 93.9% / base 90.2% / small 80.5%) are archived in
[results/results-2026-11-13.json](results/results-2026-11-13.json). tiny
drifted from 93.9% to 92.7% between the two dates — that is library-version
noise, not a fixture change; the fixture is identical. Full per-clip output
of the current run lives in
[results/results.json](results/results.json).

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

The honest conclusion of the run: at CPU scale (`whisper-tiny`, 45 minutes
of data, 2 epochs) LoRA does not improve Persian WER. Meaningful gains need
the free-GPU path documented in [docs/free-gpu.md](../docs/free-gpu.md) —
`whisper-small` (or larger) on hours of data via
`training/finetune_fa_colab.ipynb`. Until such a run is measured, no
improvement claim exists in this repo.

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
~140 MB base, ~460 MB small).

## Data attribution

- Audio + references: Mozilla Common Voice, Persian (fa), clean subset,
  [CC-0](https://creativecommons.org/publicdomain/zero/1.0/), obtained via
  the public mirror `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean`
  (Common Voice release 26.0). 12 clips sampled with a fixed seed
  (`random.seed(7)`) from the 96 test rows whose audio shipped in that
  mirror.
