# Native Ollama Provider — Design

**Date:** 2026-08-16
**Status:** Approved (design); implementation pending
**Sub-project:** 1 of 3 (Ollama first → ontology expansion → kNN finish/integrate)

## Goal

Make Ollama a first-class provider in xVector for **both** embeddings and
extraction, with live model discovery, a same-origin proxy route, and native
Ollama API endpoints. Today Ollama is only reachable indirectly through the
OpenAI-compatible `api` provider (its URL default already points at
`http://localhost:11434/v1/embeddings`); this makes it a proper, discoverable
provider with a health check.

This is the first of three coupled sub-projects. It is scoped to stand alone and
ship on its own; the 4-type ontology extraction prompt is explicitly deferred to
sub-project 2. Sub-project 1 wires the Ollama chat *transport* into extraction
but keeps the current 2-type prompt.

## Non-goals (YAGNI)

- No model pulling/management from the UI (`/api/pull`).
- No streaming responses.
- No `keep_alive` / GPU / context-length tuning.
- No auto-detection of embed-vs-chat models (`/api/tags` doesn't distinguish
  them; both dropdowns list all installed models with a hint).
- No 4-type ontology prompt — that is sub-project 2.

## Architecture

The browser orchestrates; `scripts/serve.py` proxies to Ollama from the same
origin, exactly as it already does for Kinetica. This sidesteps CORS and
mixed-content the same way and keeps the "opens anywhere" property: no
`OLLAMA_ORIGINS` env setup required.

```
browser (index.html)
  ├── /ollama/api/tags   (GET)  ─┐
  ├── /ollama/api/embed  (POST) ─┼─ serve.py proxy ──► http://localhost:11434
  ├── /ollama/api/chat   (POST) ─┘
  └── /kinetica/execute/sql (POST) ─ serve.py proxy ──► http://localhost:9191
```

## Component 1 — Proxy (`scripts/serve.py`)

Generalize the single-target proxy into a small route table.

- Add `--ollama` CLI flag (default `http://localhost:11434`, env `OLLAMA_URL`),
  keep `--kinetica`.
- Replace hard-coded `PREFIX`/`TARGET` with a routes mapping:
  `ROUTES = {"/kinetica": kinetica_url, "/ollama": ollama_url}`.
- Extract a **pure** helper `resolve_target(path, routes)` returning
  `(target_base, upstream_path)` for the longest-matching prefix, or `None` when
  no prefix matches. This is the unit-tested seam.
- `do_POST`: dispatch via `resolve_target`; on no match, keep the current
  404 behavior. Forward body, `Content-Type`, and `Authorization` as today.
- **`do_GET` override (new):** if `resolve_target(path)` matches, forward the GET
  upstream (needed for `/ollama/api/tags`); otherwise call `super().do_GET()` so
  static files still serve. Today only POST is proxied.
- Proxy error shape stays the JSON `{"status":"ERROR","message":"..."}` with 502
  so the client parses failures uniformly.
- Startup banner prints both proxied targets.

## Component 2 — Provider UI (`index.html`)

- Add `<option value="ollama">Ollama — native (local models)</option>` to the
  Provider `<select>` (`#provider`) and to the Extraction `<select>`
  (`#extractProvider`).
- New Ollama field group (shown when provider === `ollama`), mirroring the API
  group's show/hide logic in the `#provider` change handler:
  - Base URL text field, default `/ollama`.
  - Embed-model `<select>` (`#ollamaEmbedModel`), populated from `/api/tags`.
  - "Refresh / health" affordance that calls `ollamaModels()` and reports
    reachability through `log()`.
- Extraction Ollama group: chat-model `<select>` (`#ollamaChatModel`), also from
  `/api/tags`.
- A short hint near the dropdowns: model list is unfiltered because `/api/tags`
  does not label embed vs chat models.

## Component 3 — Embedding path (`index.html`)

- `embedOllama(texts)`: batches using the existing `#apiBatch` field (no new
  batch control) to `POST /ollama/api/embed` with body
  `{model, input: chunk, truncate: true}`.
- Response handling goes through a **pure** `pickEmbeddings(json, expected)` in
  the CORE block that accepts the known shapes and returns an array of number
  arrays (or throws a clear error):
  - native: `{embeddings: [[…], …]}`
  - OpenAI-compat: `{data: [{embedding: […]}, …]}`
  - bare `[[…], …]`
- Each vector runs through the existing `reduceVec()`. Ollama embed models
  (e.g. `nomic-embed-text`, 768-d) are not Matryoshka, so the reduction default
  for the Ollama provider is **random projection**, not truncation. `srcDim` is
  recorded as today. The `#reduce` "ask" option (which sends a `dimensions`
  param) is not supported by native `/api/embed`; for the Ollama provider "ask"
  is treated as project, and the UI notes this.
- `source` label for rows written to Kinetica uses the chosen Ollama model name
  (sliced to 64 chars), consistent with the API provider's `source` handling.

## Component 4 — Extraction path (`index.html`)

- Wire the Ollama option into `extractLLM()`: when extraction provider is
  `ollama`, POST to `/ollama/api/chat` with
  `{model, messages, stream: false, format: "json"}` and parse
  `message.content` as JSON defensively (same tolerance as `ksql`).
- **Keep the current 2-type (Person/Business) prompt.** The 4-type ontology
  prompt, typed edges, and canonical folding are sub-project 2. This boundary is
  deliberate: sub-project 1 delivers Ollama transport; sub-project 2 changes what
  we ask the model for.

## Data flow

1. User selects **Ollama** provider → `ollamaModels()` calls `GET /ollama/api/tags`
   → fills embed/chat model dropdowns; a failed call logs an actionable error.
2. **Embed** → `embedOllama()` batches → `/ollama/api/embed` → `pickEmbeddings()`
   → `reduceVec()` → `DOCS` (unchanged downstream: render, SQL, Kinetica write).
3. **Extract entities** (if Ollama extraction chosen) → `extractLLM()` →
   `/ollama/api/chat` → mentions → existing disambiguation.

## Error handling

- Discovery failure: `log("Can't reach Ollama at /ollama — is `ollama serve`
  running and did you start serve.py with --ollama?", "err")`.
- Embedding/extraction failures throw with the upstream status + a truncated body
  and, for the write path, keep pointing at Copy SQL as the fallback — consistent
  with the existing Kinetica-write failure convention.
- All parsing (`pickEmbeddings`, chat JSON) degrades to a clear thrown error
  rather than a silent wrong result.

## Testing

- **Python (`scripts/`):** unit-test `resolve_target(path, routes)` — longest
  prefix wins, unknown prefix → `None`, path rewrite strips the prefix. Stdlib
  `unittest` only.
- **Node CORE (`scripts/test_graph.mjs`):** unit-test `pickEmbeddings()` across
  the three response shapes plus the count-mismatch error, and confirm it lives
  inside the `/* CORE:BEGIN … CORE:END */` markers.
- Network/DOM functions (`embedOllama`, `ollamaModels`) are exercised manually
  against a local Ollama; their pure seams are the tested parts.

## Files touched

- `scripts/serve.py` — route table, `resolve_target`, `do_GET`, `--ollama`.
- `index.html` — provider/extraction options, Ollama field groups + show/hide,
  `ollamaModels()`, `embedOllama()`, `pickEmbeddings()` (CORE), `extractLLM()`
  Ollama branch.
- `scripts/test_graph.mjs` — `pickEmbeddings` tests.
- New `scripts/test_serve.py` (or extend existing) — `resolve_target` tests.
- `CLAUDE.md` — document the Ollama provider + proxy route.
- `README`/run docs — `--ollama` usage.

## Rollout / sequencing

Sub-project 1 ships independently. It leaves a clean seam for sub-project 2
(ontology): the Ollama chat transport is already wired, so sub-project 2 only
swaps the extraction prompt and the label/edge taxonomy.
