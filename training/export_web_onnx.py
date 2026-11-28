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
   (encoder + decoder_model_merged with the `use_cache_branch` KV-cache If,
   attention outputs for return_timestamps) via optimum's Python API,
3. quantizes to int8/q8 files for the browser dtypes (EnableSubgraph so the
   merged decoder's branch subgraphs are quantized too),
4. uploads the finished model repo to the Hugging Face Hub.

Environment note: optimum's classic ONNX exporter requires torch <= 2.8
(torch 2.9+ removed the private onnx symbols it imports) and optimum < 2
(optimum 2.x deleted the exporter). The notebook cell 11 installs the
right pins; on any machine run:

    pip install "torch==2.8.0" --index-url https://download.pytorch.org/whl/cpu \
        "optimum==1.27.*" "transformers>=4.55" peft onnx onnxruntime

Usage (Colab / any machine with ~4 GB RAM):

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
    if "preprocessor_config.json" in missing and (out_dir / "processor_config.json").is_file():
        # transformers v5's ProcessorMixin.save_pretrained writes
        # processor_config.json (feature-extractor kwargs nested under
        # "feature_extractor") and no longer emits preprocessor_config.json,
        # which optimum export and transformers.js still expect. Re-derive
        # the feature-extractor config from the staged processor file.
        try:
            import json as _json

            pcfg = _json.loads((out_dir / "processor_config.json").read_text())
            fe_kwargs = dict(pcfg.get("feature_extractor") or pcfg)
            fe_kwargs.pop("feature_extractor_type", None)
            fe_kwargs.pop("processor_class", None)
            if fe_kwargs.get("feature_size"):
                try:
                    from transformers import WhisperFeatureExtractor

                    WhisperFeatureExtractor(**fe_kwargs).save_pretrained(out_dir)
                except Exception:
                    (out_dir / "preprocessor_config.json").write_text(
                        _json.dumps(dict(pcfg.get("feature_extractor") or pcfg),
                                    indent=2, sort_keys=True) + "\n"
                    )
                if (out_dir / "preprocessor_config.json").is_file():
                    missing.remove("preprocessor_config.json")
                    print(
                        "      derived preprocessor_config.json from processor_config.json"
                        " (transformers v5 layout)"
                    )
        except Exception as err:  # repair is best-effort; guidance below if it fails
            print(f"      could not derive preprocessor_config.json automatically ({err})")
    if missing:
        raise ExportInputError(
            f"{src} is missing {', '.join(missing)} — save the tokenizer and "
            "feature extractor next to the merged model (merge_lora does "
            "this) or re-run the notebook's merge cell. On transformers v5, "
            "run: AutoFeatureExtractor.from_pretrained('openai/whisper-small')"
            ".save_pretrained(<merged folder>) — processor.save_pretrained "
            "alone no longer writes preprocessor_config.json."
        )


def _whisper_web_onnx_config_class():
    """optimum whisper config that emits the attention outputs transformers.js
    needs for `return_timestamps` (cross_attentions feed the alignment heads).
    Mirrors transformers.js v2's scripts/extra/whisper.py."""
    from optimum.exporters.onnx.base import ConfigBehavior
    from optimum.exporters.onnx.model_configs import WhisperOnnxConfig

    class WhisperWebOnnxConfig(WhisperOnnxConfig):
        @property
        def outputs(self):
            common_outputs = super().outputs
            if self._behavior is ConfigBehavior.ENCODER:
                for i in range(self._config.encoder_layers):
                    common_outputs[f"encoder_attentions.{i}"] = {0: "batch_size"}
            elif self._behavior is ConfigBehavior.DECODER:
                for i in range(self._config.decoder_layers):
                    common_outputs[f"decoder_attentions.{i}"] = {
                        0: "batch_size",
                        2: "decoder_sequence_length",
                        3: "past_decoder_sequence_length + 1",
                    }
                for i in range(self._config.decoder_layers):
                    common_outputs[f"cross_attentions.{i}"] = {
                        0: "batch_size",
                        2: "decoder_sequence_length",
                        3: "encoder_sequence_length_out",
                    }
            return common_outputs

        @property
        def values_override(self):
            # both decoder variants must run with the KV cache enabled so the
            # no-past trace really produces the present.* tensors the merge
            # needs, and with output_attentions so the traced graphs carry the
            # attention outputs transformers.js reads for return_timestamps.
            # Only the merged file ships to the browser.
            return {"use_cache": True, "output_attentions": True,
                    "_attn_implementation": "eager"}

        @property
        def torch_to_onnx_output_map(self):
            if self._behavior is ConfigBehavior.ENCODER:
                # the encoder export returns the key "attentions"
                return {"attentions": "encoder_attentions"}
            return {}

    return WhisperWebOnnxConfig


def export_onnx(model_dir: Path, onnx_dir: Path) -> None:
    print("[3/4] exporting ONNX via optimum (encoder + decoder_model_merged)")
    import torch  # noqa: F401  (import checked below)
    from optimum.exporters.onnx import main_export

    if tuple(int(p) for p in torch.__version__.split(".")[:2]) > (2, 8):
        raise ExportInputError(
            f"torch {torch.__version__} is too new for optimum's ONNX exporter "
            "(it needs torch.onnx private symbols removed in 2.9). Install the "
            "CPU build: pip install 'torch==2.8.0' "
            "--index-url https://download.pytorch.org/whl/cpu"
        )

    cfg_cls = _whisper_web_onnx_config_class()
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained(str(model_dir))
    cfg = cfg_cls(config=config, task="automatic-speech-recognition")
    # use_past=True mirrors optimum's own whisper-with-past flow: it emits the
    # present.* outputs while use_past_in_inputs=False keeps the past tensors
    # out of the no-past decoder's inputs.
    custom_onnx_configs = {
        "encoder_model": cfg.with_behavior("encoder"),
        "decoder_model": cfg.with_behavior(
            "decoder", use_past=True, use_past_in_inputs=False
        ),
        "decoder_with_past_model": cfg.with_behavior(
            "decoder", use_past=True, use_past_in_inputs=True
        ),
    }

    # The generic seq2seq merge path (config.py's post-process) merges with
    # strict=True, but the with-past decoder drops the constant cross-attention
    # presents, so the output counts differ. strict=False is exactly what
    # optimum's own whisper-with-past path (model_configs.py) uses; the added
    # constant branch outputs are never consumed by transformers.js, which
    # re-uses its step-1 cross-attention cache instead.
    import optimum.onnx as _oonnx
    from optimum.onnx.graph_transformations import merge_decoders as _orig_merge

    def _merge_decoders_lenient(decoder, decoder_with_past, **kwargs):
        kwargs["strict"] = False
        return _orig_merge(decoder, decoder_with_past, **kwargs)

    _oonnx.merge_decoders = _merge_decoders_lenient

    main_export(
        model_name_or_path=str(model_dir),
        output=str(onnx_dir),
        task="automatic-speech-recognition-with-past",
        custom_onnx_configs=custom_onnx_configs,
        model_kwargs={"output_attentions": True},
        monolith=False,
        device="cpu",
        do_validation=False,
        library_name="transformers",
    )

    merged_path = onnx_dir / "decoder_model_merged.onnx"
    if not merged_path.is_file():
        raise ExportInputError(
            "optimum did not produce decoder_model_merged.onnx — the browser "
            "demo cannot load this export. Check the optimum/torch pins "
            "(optimum==1.27.*, torch==2.8.0)."
        )

    # int8 quantization for the wasm/q8 dtype path. EnableSubgraph is what
    # quantizes the merged decoder's If-branch subgraphs (same recipe the
    # transformers.js v2 converter used).
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic

    for onnx_file in sorted(onnx_dir.glob("*.onnx")):
        if "_quantized" in onnx_file.stem or "_q4" in onnx_file.stem:
            continue
        loaded = onnx.load(str(onnx_file), load_external_data=True)
        op_types = {n.op_type for n in loaded.graph.node}
        weight_type = QuantType.QUInt8 if "Conv" in op_types else QuantType.QInt8
        quantize_kwargs = {"extra_options": {"EnableSubgraph": True}}
        try:
            quantize_dynamic(
                model_input=str(onnx_file),
                model_output=str(onnx_file.with_name(onnx_file.stem + "_quantized.onnx")),
                weight_type=weight_type,
                **quantize_kwargs,
            )
        except TypeError:
            # older onnxruntime needs optimize_model=False (no pre-processing)
            quantize_dynamic(
                model_input=str(onnx_file),
                model_output=str(onnx_file.with_name(onnx_file.stem + "_quantized.onnx")),
                weight_type=weight_type,
                optimize_model=False,
                **quantize_kwargs,
            )

    # tokenizer/processing configs ride along for transformers.js
    for name in (
        "config.json", "generation_config.json", "preprocessor_config.json",
        "processor_config.json", "tokenizer_config.json", "tokenizer.json",
        "special_tokens_map.json",
    ):
        src = model_dir / name
        if src.exists():
            shutil.copy(src, onnx_dir / name)
    # transformers.js only loads the encoder and the merged decoder; the two
    # intermediate decoder files are merge fodder, not shipping cargo
    for spare in ("decoder_model.onnx", "decoder_with_past_model.onnx"):
        for variant in (onnx_dir / spare, onnx_dir / spare.replace(".onnx", "_quantized.onnx")):
            if variant.is_file():
                variant.unlink()

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
