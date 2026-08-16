# xVector

Paste paragraphs, get 64-dimension vectors, write them to Kinetica as
`vector_embeddings_<datestamp>`. One HTML file, no dependencies.

## Run

```bash
python3 scripts/serve.py
```

Open http://localhost:8000 and set **Instance URL** to `/kinetica`. The server proxies SQL
to `http://localhost:9191`, so the browser makes no cross-origin call. Point it elsewhere
with `--kinetica http://host:9191`.

Opening `index.html` directly from disk also works, but then the app calls Kinetica from
the browser and the instance has to allow the origin.

## Use

1. Paste text. Blank lines separate documents by default.
2. **Generate embeddings.** The built-in embedder is deterministic and offline; switch the
   provider to any OpenAI-compatible `/v1/embeddings` endpoint for real semantics.
3. **Store in Kinetica.** Creates the table if missing, then inserts in batches.
4. Search the table to confirm the vectors landed.

If the write can't get through, **Copy SQL** gives you the whole script for Workbench.

`samples/kinetica-notes.txt` holds three related paragraphs and two unrelated ones, so
distances mean something on a first run.

See CLAUDE.md for how the pieces fit together and what's unfinished.
