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
> another port with `--port`, e.g. `python3 scripts/serve.py --port 8181`, and
> open http://localhost:8181. The `/kinetica` and `/ollama` proxy routes are
> relative to whatever port you serve on, so nothing else changes.

## 2. Kinetica (required for the Store/Search steps)

A local Kinetica instance on `http://localhost:9191` (the proxy default). Point
elsewhere with `--kinetica http://host:9191`. You can skip this and still use
**Copy SQL** to run the generated script in Workbench.

## 3. Ollama (for local embeddings)

Ollama serves the embedding models, reached through a same-origin `/ollama` proxy route in
`scripts/serve.py` (mirrors the `/kinetica` proxy — no `OLLAMA_ORIGINS` needed).

> **Status:** the **Ollama embeddings provider** is available. Models are discovered via `/api/tags`
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
| Embeddings (768-d → reduced to 64) | `nomic-embed-text` | `ollama pull nomic-embed-text` |

- **Embedding note:** `nomic-embed-text` returns 768 dims; the app reduces to
  `DIM=64` by **random projection** (it is not a Matryoshka model, so truncation
  would lose information).

### Verified local environment (2026-08-16)

- Ollama API up on `127.0.0.1:11434`.
- Present: `nomic-embed-text:latest` — embeddings ready (768-d → projected to 64).

Model installed means you can skip the `ollama pull` steps above. If
`ollama serve` reports `bind: address already in use`, Ollama is already
running as a background service — don't start a second one.

## 4. Serving everything together

serve.py proxies both backends through same-origin routes:

```bash
python3 scripts/serve.py --port 8181 --kinetica http://localhost:9191 --ollama http://localhost:11434
```

(`--port 8181` avoids Kinetica Workbench on `:8000`; drop it if `:8000` is free.)

## 5. LLM providers for extraction

The app supports two LLM providers for entity extraction and relation inference. Choose one:

### Claude (Anthropic)

Requires a logged-in `claude` CLI (stored login). Install the Claude CLI and run:

```bash
claude login
```

The app routes extraction to the `/claude` endpoint using the stored login. No API key in the browser.
Model options: `claude-haiku-4-5-20251001` (fast) or `claude-opus-4-8` (best).

### Gemini (Google)

Requires `gcloud auth login` and a GCP project. Set up once with:

```bash
gcloud auth login
gcloud config set project <your-project-id>
```

Launch the server with:

```bash
python3 scripts/serve.py --port 8181 --gcp-project <your-project-id>
```

The app routes extraction to the `/gemini` endpoint via Vertex. Model options: `gemini-2.5-flash` (fast) or `gemini-2.5-pro` (best).

## 6. Verifying embeddings and extraction

With Ollama running (embeddings) and your LLM provider configured, open the app (http://localhost:8181
if you used the port above) and walk these checks:

- **Model discovery / health check (Ollama).** Provider → **Ollama — native**: the
  embedding-model dropdown auto-fills and the console logs
  `Ollama: N model(s) available` (green). Click **Refresh** for the same.
  Stop Ollama, click **Refresh** → a red, actionable error line appears
  (mentions `ollama serve` / `--ollama`). Restart Ollama afterward.
- **Embedding round-trip.** Pick `nomic-embed-text`, paste a sample (e.g.
  `samples/kinetica-notes.txt`), **Generate embeddings** → 64-d strips render
  and the console shows `via nomic-embed-text`. This exercises the 768→64
  random-projection path.
- **Extraction round-trip.** Extraction → **Claude (Anthropic)** (or **Gemini (Google)**), 
  **Extract entities** → five distinctly colored types render (People indigo, Business amber, 
  Organization teal, Facility plum, Location green) and relations appear.
- **Source label (optional).** **Copy SQL** and **Download JSON** should both
  report `source: nomic-embed-text`.
