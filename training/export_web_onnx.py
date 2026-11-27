#!/usr/bin/env python3
"""Export a fine-tuned Sokhan whisper checkpoint to a transformers.js web model.

Bridges the training world (PEFT LoRA adapter or merged checkpoint,
PyTorch) and the browser demo (transformers.js ONNX). Run this on a
machine with the model files — a free Colab T4 is enough — then wire the
resulting HF repo id into space/index.html as a new <option>
(Xenova-format ONNX is loaded by the same worker code path).

What it does:

1. builds the merged transformers checkpoint — either by loading the base
   whisper checkpoint and the Sokhan LoRA adapter and merging them
   (`merge_and_unload`), or by taking an already-merged checkpoint folder
   (notebook cell 6/7 leaves one at training/runs/whisper-small-fa-lora/merged),
2. exports the merged model to ONNX the way transformers.js expects
   (encoder + decoder-merged, no monolith),
3. quantizes to int8/q4 files for the browser dtypes,
4. uploads the finished model repo to the Hugging Face Hub.

Usage (Colab / any machine with ~4 GB RAM):

    pip install transformers peft torch optimum onnxruntime "av<14" \
        "huggingface_hub>=0.26" onnx
    export HF_TOKEN=hf_...          # a write token for the target repo

    # path A — from the LoRA adapter (local dir or Hub repo carrying
    # adapter_config.json):
    python training/export_web_onnx.py \
        --base openai/whisper-small \
        --adapter training/runs/whisper-small-fa-lora \
        --repo Abol0pati/whisper-small-fa-sokhan-web \
        --push

    # path B — from an already-merged checkpoint folder (skips the merge):
    python training/export_web_onnx.py \
        --merged training/runs/whisper-small-fa-lora/merged \
        --repo Abol0pati/whisper-small-fa-sokhan-web \
        --push

Note: the Hub repo `Abol0pati/whisper-small-fa-sokhan` is a CTranslate2
build (model.bin, for faster-whisper) — it is NOT a LoRA adapter and
cannot be exported here. Publish the adapter or the merged weights first
(training/finetune_fa_colab.ipynb cell 11 does both in one run).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ADAPTER_MARKER = "adapter_config.json"
# Where the adapter lives right after a notebook training run, so the
# error message can point at it directly.
TRAINING_ADAPTER_DIR = "training/runs/whisper-small-fa-lora"


class ExportInputError(RuntimeError):
    """Raised when the given adapter/merged input cannot be exported."""


def _looks_like_repo_id(value: str) -> bool:
    return "://" not in value and value.count("/") == 1 and not Path(value).exists()


def check_adapter(adapter: str) -> None:
    """Fail fast with an honest message when the adapter is not usable.

    The published fine-tune repo is a CTranslate2 build — feeding it here
    would die deep inside peft with an opaque error; this check replaces
    that with instructions that actually unblock the user.
    """
    local = Path(adapter)
    if local.exists():
        if (local / ADAPTER_MARKER).is_file():
            return
        raise ExportInputError(
            f"{local} exists but has no {ADAPTER_MARKER} — it is not a PEFT "
            "adapter. After a notebook run the adapter lives at "
            f"{TRAINING_ADAPTER_DIR} and the merged checkpoint at "
            f"{TRAINING_ADAPTER_DIR}/merged (use --merged for the latter)."
        )
    if _looks_like_repo_id(adapter):
        from huggingface_hub import file_exists

        if file_exists(adapter, ADAPTER_MARKER):
            return
        raise ExportInputError(
            f"Hub repo {adapter} does not carry {ADAPTER_MARKER} (the "
            "published fine-tune is a CTranslate2 build for faster-whisper, "
            "which ONNX export cannot read). Run notebook cell 6 first, or "
            "upload the adapter/merged weights (cell 11), then export from "
            f"{TRAINING_ADAPTER_DIR} or {TRAINING_ADAPTER_DIR}/merged."
        )
    raise ExportInputError(
        f"adapter {adapter!r} is neither an existing local directory nor a "
        "Hub repo id of the form owner/name."
    )


def merge_lora(base: str, adapter: str, out_dir: Path) -> None:
    check_adapter(adapter)  # fail fast, before the heavy imports below
    from peft import PeftModel
    from transformers import AutoFeatureExtractor, AutoModelForSpeechSeq2Seq, AutoTokenizer

    print(f"[1/4] loading base {base} and adapter {adapter}")
    model = AutoModelForSpeechSeq2Seq.from_pretrained(base)
    model = PeftModel.from_pretrained(model, adapter)
    merged = model.merge_and_unload()
    print("[2/4] saving merged transformers checkpoint")
    merged.save_pretrained(out_dir)
    AutoTokenizer.from_pretrained(base).save_pretrained(out_dir)
    AutoFeatureExtractor.from_pretrained(base).save_pretrained(out_dir)
    # generation config must carry forced decoder ids the demo relies on
    if hasattr(merged, "generation_config"):
        merged.generation_config.save_pretrained(out_dir)


def load_merged(merged: str, out_dir: Path) -> None:
    """Stage an already-merged checkpoint (notebook cell 11's folder)."""
    src = Path(merged)
    if not (src / "config.json").is_file():
        raise ExportInputError(
            f"{src} has no config.json — pass a transformers checkpoint "
            "folder (e.g. the `merged/` folder a notebook run produces), "
            "not a CTranslate2 build."
        )
    print(f"[1/4] using already-merged checkpoint {src}")
    print("[2/4] staging merged transformers checkpoint")
    shutil.copytree(src, out_dir)
    # the processing configs must ride along; a merged folder without them
    # is rejected with instructions instead of failing deep in optimum-cli.
    missing = [
        name
        for name in ("tokenizer_config.json", "preprocessor_config.json")
        if not (out_dir / name).is_file()
    ]
    if missing:
        raise ExportInputError(
            f"{src} is missing {', '.join(missing)} — save the tokenizer and "
            "feature extractor next to the merged model (merge_lora does "
            "this) or re-run the notebook's merge cell."
        )


def export_onnx(model_dir: Path, onnx_dir: Path) -> None:
    print("[3/4] exporting ONNX (encoder + decoder-merged)")
    subprocess.run(
        [
            "optimum-cli", "export", "onnx",
            "--model", str(model_dir),
            "--task", "automatic-speech-recognition",
            "--monolith", "false",
            "--device", "cpu",
            str(onnx_dir),
        ],
        check=True,
    )
    # int8 quantization for the wasm/q8 dtype path
    from onnxruntime.quantization import QuantType, quantize_dynamic

    for onnx_file in list(onnx_dir.rglob("*.onnx")):
        if "_quantized" in onnx_file.stem or "_q4" in onnx_file.stem:
            continue
        quantize_dynamic(
            str(onnx_file),
            str(onnx_file.with_name(onnx_file.stem + "_quantized.onnx")),
            weight_type=QuantType.QInt8,
        )
    # tokenizer/processing configs ride along for transformers.js
    for name in (
        "config.json", "generation_config.json", "preprocessor_config.json",
        "tokenizer_config.json", "tokenizer.json", "special_tokens_map.json",
    ):
        src = model_dir / name
        if src.exists():
            shutil.copy(src, onnx_dir / name)
    (onnx_dir / "onnx").mkdir(exist_ok=True)
    for onnx_file in list(onnx_dir.glob("*.onnx")):
        shutil.move(str(onnx_file), onnx_dir / "onnx" / onnx_file.name)


def push(repo: str, onnx_dir: Path) -> None:
    from huggingface_hub import HfApi

    print(f"[4/4] uploading to {repo}")
    api = HfApi(token=None)  # token comes from HF_TOKEN env / cached login
    api.create_repo(repo, repo_type="model", exist_ok=True)
    api.upload_folder(folder_path=str(onnx_dir), repo_id=repo, repo_type="model")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="openai/whisper-small",
                    help="base whisper checkpoint (used only with --adapter)")
    ap.add_argument("--adapter", default=None,
                    help="PEFT LoRA adapter (local dir or Hub repo with adapter_config.json)")
    ap.add_argument("--merged", default=None,
                    help="already-merged transformers checkpoint folder (skips the merge)")
    ap.add_argument("--repo", default="Abol0pati/whisper-small-fa-sokhan-web",
                    help="target Hub repo for the finished ONNX model")
    ap.add_argument("--push", action="store_true", help="upload the finished repo to the Hub")
    args = ap.parse_args()

    if bool(args.adapter) == bool(args.merged):
        ap.error(
            "give exactly one input: --adapter <LoRA dir|repo> to merge, or "
            "--merged <checkpoint folder> to skip the merge"
        )

    try:
        with tempfile.TemporaryDirectory(prefix="sokhan-web-export-") as tmp:
            root = Path(tmp)
            merged_dir = root / "merged"
            onnx_dir = root / "onnx"
            if args.merged:
                load_merged(args.merged, merged_dir)
            else:
                merge_lora(args.base, args.adapter, merged_dir)
            export_onnx(merged_dir, onnx_dir)
            if args.push:
                push(args.repo, onnx_dir)
            else:
                keep = Path("sokhan-web-model")
                if keep.exists():
                    shutil.rmtree(keep)
                shutil.copytree(onnx_dir, keep)
                print(f"kept local copy at ./{keep}")
    except ExportInputError as err:
        print(f"error: {err}")
        return 2
    print("done — add the repo id as a new <option> in space/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
