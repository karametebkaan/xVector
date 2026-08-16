# Local development setup

Prerequisites for running xVector and driving it with local models. The app
itself has no build step and no dependencies — this is about the services it
talks to.

## 1. Python (required)

Python 3 (stdlib only). No packages to install.

```bash
python3 scripts/serve.py                 # serves :8000, proxies /kinetica → :9191
```

Then open http://localhost:8000 and set **Instance URL** to `/kinetica`.

## 2. Kinetica (required for the Store/Search steps)

A local Kinetica instance on `http://localhost:9191` (the proxy default). Point
elsewhere with `--kinetica http://host:9191`. You can skip this and still use
**Copy SQL** to run the generated script in Workbench.

## 3. Ollama (for local embeddings + extraction)

Ollama serves both the embedding models and the chat model used for entity
extraction, reached through a same-origin `/ollama` proxy route in
`scripts/serve.py` (mirrors the `/kinetica` proxy — no `OLLAMA_ORIGINS` needed).

> **Status:** the first-class **Ollama provider** (for both embeddings and extraction)
> and the `--ollama` proxy flag are now available. Models are discovered via `/api/tags`
> and reduction of >64-dim embeddings is applied via random projection.

### Install & run

```bash
# install: https://ollama.com/download
ollama serve                             # exposes the API on :11434
curl -s http://localhost:11434/api/tags  # sanity check — lists installed models
```

### Models

| Purpose                     | Model                 | Pull command                     |
|-----------------------------|-----------------------|----------------------------------|
| Extraction / NER (chat)     | `llama3.2`            | `ollama pull llama3.2`           |
| Embeddings (768-d → reduced to 64) | `nomic-embed-text` | `ollama pull nomic-embed-text` |

- **Embedding note:** `nomic-embed-text` returns 768 dims; the app reduces to
  `DIM=64` by **random projection** (it is not a Matryoshka model, so truncation
  would lose information).
- **Extraction note:** `llama3.2:latest` reports `completion` + `tools`
  capabilities, which is what the extraction path needs.

### Verified local environment (2026-08-16)

- Ollama **0.32.14** installed at `/usr/local/bin/ollama`, API up on `:11434`.
- Present: `llama3.2:latest` (3.2B, Q4_K_M) — chat/extraction ready.
- **Missing:** an embedding model. Run `ollama pull nomic-embed-text` before
  using the Ollama embedding provider.

## 4. Serving everything together

Once the Ollama provider lands, serve.py proxies both backends:

```bash
python3 scripts/serve.py --kinetica http://localhost:9191 --ollama http://localhost:11434
```
