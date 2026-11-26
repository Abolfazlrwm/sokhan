#!/usr/bin/env python3
"""Export a fine-tuned Sokhan whisper checkpoint to a transformers.js web model.

Bridges the training world (PEFT LoRA adapter, PyTorch) and the browser
demo (transformers.js ONNX). Run this on a machine with the model files —
a free Colab T4 is enough — then wire the resulting HF repo id into
space/index.html as a new <option> (Xenova-format ONNX is loaded by the
same worker code path).

What it does:

1. loads the base whisper checkpoint and the Sokhan LoRA adapter,
2. merges the adapter (`merge_and_unload`) and saves a plain transformers
   model + tokenizer + feature extractor,
3. exports the merged model to ONNX the way transformers.js expects
   (encoder + decoder-merged, no monolith),
4. quantizes to int8/q4 files for the browser dtypes,
5. uploads the finished model repo to the Hugging Face Hub.

Usage (Colab / any machine with ~4 GB RAM):

    pip install transformers peft torch optimum onnxruntime "av<14" \
        "huggingface_hub>=0.26" onnx
    python training/export_web_onnx.py \
        --base openai/whisper-small \
        --adapter Abol0pati/whisper-small-fa-sokhan \
        --repo Abol0pati/whisper-small-fa-sokhan-web \
        --push
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


def merge_lora(base: str, adapter: str, out_dir: Path) -> None:
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
    ap.add_argument("--base", default="openai/whisper-small")
    ap.add_argument("--adapter", default="Abol0pati/whisper-small-fa-sokhan")
    ap.add_argument("--repo", default="Abol0pati/whisper-small-fa-sokhan-web")
    ap.add_argument("--push", action="store_true", help="upload the finished repo to the Hub")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="sokhan-web-export-") as tmp:
        root = Path(tmp)
        merged_dir = root / "merged"
        onnx_dir = root / "onnx"
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
    print("done — add the repo id as a new <option> in space/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
