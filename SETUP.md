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

> **Port conflict:** Kinetica Workbench also uses `:8000`. Serve xVector on
> another port with `--port`, e.g. `python3 scripts/serve.py --port 8090`, and
> open http://localhost:8090. The `/kinetica` and `/ollama` proxy routes are
> relative to whatever port you serve on, so nothing else changes.

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

- Ollama API up on `127.0.0.1:11434`.
- Present: `llama3.2:latest` — chat/extraction ready.
- Present: `nomic-embed-text:latest` — embeddings ready (768-d → projected to 64).

Both models installed means you can skip the `ollama pull` steps above. If
`ollama serve` reports `bind: address already in use`, Ollama is already
running as a background service — don't start a second one.

## 4. Serving everything together

serve.py proxies both backends through same-origin routes:

```bash
python3 scripts/serve.py --port 8090 --kinetica http://localhost:9191 --ollama http://localhost:11434
```

(`--port 8090` avoids Kinetica Workbench on `:8000`; drop it if `:8000` is free.)

## 5. Verifying the Ollama provider

With Ollama running and serving via `--ollama`, open the app (http://localhost:8090
if you used the port above) and walk these checks:

- **Model discovery / health check.** Provider → **Ollama — native**: the
  embedding-model dropdown auto-fills and the console logs
  `Ollama: N model(s) available` (green). Click **Refresh** for the same.
  Stop Ollama, click **Refresh** → a red, actionable error line appears
  (mentions `ollama serve` / `--ollama`). Restart Ollama afterward.
- **Embedding round-trip.** Pick `nomic-embed-text`, paste a sample (e.g.
  `samples/kinetica-notes.txt`), **Generate embeddings** → 64-d strips render
  and the console shows `via nomic-embed-text`. This exercises the 768→64
  random-projection path.
- **Extraction round-trip.** Extraction → **Ollama — chat**, pick `llama3.2`,
  **Extract entities** → Person (indigo) / Business (amber) entities render.
- **Source label (optional).** **Copy SQL** and **Download JSON** should both
  report `source: nomic-embed-text`.

If `/api/embed` or `/api/chat` returns an unexpected shape, the console throws
rather than rendering — the one failure mode the automated tests can't catch.
