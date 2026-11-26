# Contributing to Sokhan

**English** | [فارسی](CONTRIBUTING.fa.md)

Thanks for looking into Sokhan. This repo is a self-hostable Persian
speech-to-text kit: a FastAPI backend with a faster-whisper engine, a
Celery worker, a Next.js (Persian-first, RTL) dashboard, an optional
Telegram bot, a measured LoRA fine-tune pipeline, and a public browser
demo on Hugging Face.

## Dev setup

Python 3.12 for the backend and bot, Node 22 for the web dashboard:

    pip install -e "backend[dev]" -e "bot[dev]"
    cd web && npm ci

Heavy extras (torch / faster-whisper) are only needed for the training
and benchmark tooling:

    pip install -r training/requirements.txt -r benchmarks/requirements.txt
    pip install -r space/gradio/requirements.txt   # self-hostable Gradio demo

## Tests, lint and commit hygiene

CI runs the same commands on every push and pull request:

    ruff check backend bot training benchmarks space deploy
    mypy --config-file backend/pyproject.toml backend/sokhan
    pytest backend/tests bot/tests
    cd web && npm ci && npm run build

Enable the pre-commit hooks (ruff plus basic hygiene) once per clone:

    pip install pre-commit && pre-commit install

Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, ...) and
the project versions with Semantic Versioning; every user-facing change
gets a line in CHANGELOG.md.

## The browser demo and the sync-space workflow

`space/` is the static demo where Whisper runs entirely client-side
(transformers.js). The `Sync demo Space` workflow publishes it to
hf.co/spaces/Abol0pati/sokhan-fa-demo on every push that touches
`space/`, using the repo's `HF_TOKEN` Actions secret - so the public
demo can never drift from `main`. `space/gradio/` is a separate,
self-hostable app that serves the fine-tuned checkpoint with the
production engine config; it is deliberately not uploaded to the public
Space (HF's 2026 pricing gates hosted Gradio/Docker Spaces behind PRO).

## Measurement-first rule

Any accuracy claim (WER, CER, speed) that lands in the README, the model
card or the changelog must come from `benchmarks/benchmark_wer.py` (or
the notebook eval) with the fixture and hardware noted. No invented
numbers.

## Security

Do not open public issues for security reports - see SECURITY.md for
private disclosure.
