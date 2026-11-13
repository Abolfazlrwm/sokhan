# Sokhan · سخن

**Persian-first speech-to-text toolkit.** Send a voice message — get back a transcript and a summary.

> Status: early development. The transcription engine and REST API are the first building blocks; the web dashboard and Telegram bot follow.

## Why

Most speech-to-text tooling treats Persian as an afterthought. Sokhan is built for Persian speakers from the first commit:

- Persian UI and Persian-normalized archive search (ی/ي and ک/ك variants handled)
- Persian prompts for LLM summaries
- Chunking tuned for long lectures and interviews on modest hardware

## Target users

- **Students** — record a lecture, get clean text plus a summary
- **Journalists and podcasters** — turn long interviews into searchable text
- **Everyone** — send a long voice message, get the text and a three-line summary

## Repository layout

```
backend/   FastAPI service, Whisper engine, worker pipeline
bot/       Telegram bot
web/       Next.js dashboard (planned)
deploy/    docker-compose for one-command self-hosting (planned)
docs/      architecture and decision records
```

## Development

```bash
pip install -e "backend[dev]"
pytest -m "not gpu_optional"
```

## License

MIT — see [LICENSE](LICENSE).
