"""LoRA fine-tune of a Whisper model on Persian speech.

Trains a parameter-efficient adapter (LoRA) on top of a Whisper checkpoint
using the manifest produced by ``prepare_common_voice.py``. The base weights
stay frozen, so an 8-16 GB GPU is enough for ``whisper-small``.

Usage:

    python training/train_whisper_lora.py \
        --manifest training/data/common-voice-fa/manifest.jsonl \
        --output training/runs/whisper-small-fa-lora \
        --epochs 3

After training, convert the adapter for faster-whisper (the engine Sokhan
actually runs):

    ct2-transformers-converter \
        --model training/runs/whisper-small-fa-lora/merged \
        --output_dir models/whisper-small-fa-ct2 \
        --quantization float16

and point ``WHISPER_MODEL_SIZE`` at the converted model directory.

Persian WER evaluation inside the loop reuses the exact normalization the
product ships (``sokhan.core.persian.normalize_persian``), so the numbers are
comparable with ``benchmarks/benchmark_wer.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sokhan.core.persian import normalize_persian  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, required=True, help="JSONL from prepare_common_voice.py"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="where to store the adapter and logs"
    )
    parser.add_argument(
        "--base-model", default="openai/whisper-small", help="HF Whisper checkpoint"
    )
    parser.add_argument(
        "--language", default="persian", help="language name used by the HF processor"
    )
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--eval-fraction", type=float, default=0.02, help="hold-out share for WER eval"
    )
    parser.add_argument(
        "--max-samples", type=int, default=0, help="0 = use the whole manifest"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue from the last checkpoint saved in --output "
        "(free-GPU sessions can be preempted mid-run)",
    )
    return parser.parse_args()


def load_manifest(path: Path, limit: int) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    if not rows:
        raise SystemExit(f"no rows in {path}")
    return rows


def main() -> int:
    args = parse_args()

    import soundfile as sf
    import torch  # noqa: F401 - confirms the CUDA runtime early
    import torchaudio.functional  # resample only; loading uses soundfile
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )

    try:
        import jiwer
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SystemExit("pip install -r training/requirements.txt first") from exc

    rows = load_manifest(args.manifest, args.max_samples)
    split_index = max(1, int(len(rows) * (1.0 - args.eval_fraction)))
    train_rows, eval_rows = rows[:split_index], rows[split_index:]
    print(f"train: {len(train_rows)}  eval: {len(eval_rows)}")

    processor = WhisperProcessor.from_pretrained(args.base_model)
    model = WhisperForConditionalGeneration.from_pretrained(args.base_model)
    model.config.forced_decoder_ids = None
    model.generation_config.language = args.language
    model.generation_config.task = "transcribe"

    lora = LoraConfig(
        r=args.lora_rank,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    def to_features(row: dict) -> dict:
        # torchaudio.load now requires TorchCodec; soundfile needs no codec
        # layer and reads the wav/flac/mp3 headers Common Voice ships.
        audio, rate = sf.read(row["audio"], dtype="float32", always_2d=True)
        waveform = torch.from_numpy(audio.mean(axis=1))
        if rate != 16_000:
            waveform = torchaudio.functional.resample(waveform, rate, 16_000)
        features = processor(
            audio=waveform.numpy(), sampling_rate=16_000, return_tensors="pt"
        )
        labels = processor.tokenizer(row["text"], return_tensors="pt")
        return {
            "input_features": features.input_features[0],
            "labels": labels.input_ids[0],
        }

    train_dataset = Dataset.from_list(train_rows).map(to_features, remove_columns=["audio", "text"])
    eval_dataset = Dataset.from_list(eval_rows).map(to_features, remove_columns=["audio", "text"])

    def collate(batch: list[dict]) -> dict:
        # Dataset.map round-trips tensors through Arrow, so features arrive
        # as nested lists; rebuild them before stacking.
        features = torch.stack(
            [torch.as_tensor(item["input_features"]) for item in batch]
        )
        labels = processor.tokenizer.pad(
            [{"input_ids": item["labels"]} for item in batch], return_tensors="pt"
        )
        labels["input_ids"].masked_fill_(labels.attention_mask.ne(1), -100)
        return {"input_features": features, "labels": labels["input_ids"]}

    def compute_metrics(prediction: tuple) -> dict:
        ids, label_ids = prediction
        decoded = processor.batch_decode(ids, skip_special_tokens=True)
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        references = processor.batch_decode(label_ids, skip_special_tokens=True)
        normalized_ref = [" ".join(normalize_persian(text).split()) for text in references]
        normalized_hyp = [" ".join(normalize_persian(text).split()) for text in decoded]
        wer = jiwer.wer(normalized_ref, normalized_hyp)
        return {"wer": round(wer, 4)}

    training_args = Seq2SeqTrainingArguments(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        eval_strategy="epoch",
        logging_steps=50,
        save_strategy="epoch",
        predict_with_generate=True,
        fp16=torch.cuda.is_available(),
        report_to=[],
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=collate,
        compute_metrics=compute_metrics,
        processing_class=processor,
    )
    trainer.train(resume_from_checkpoint=args.resume or None)
    trainer.save_model(str(args.output / "adapter"))

    # a merged copy is what the CTranslate2 converter expects
    merged = model.merge_and_unload()
    merged.save_pretrained(str(args.output / "merged"))
    processor.save_pretrained(str(args.output / "merged"))
    print(f"adapter + merged model saved under {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
