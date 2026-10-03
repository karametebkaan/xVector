# xVector

**A kNN-based document entity and relationship extraction engine.**

A large language model asked to build a knowledge graph from text will assert only what a sentence states. Across a
corpus, that faithfulness is also the method's ceiling: three paragraphs about one family can produce two disconnected
components, because no single sentence ever names the tie between them. xVector adds a purely additive second pass that
recovers those ties without touching what the extractor found:

- Each document is split into paragraph chunks and embedded once.
- A top-*k* nearest-neighbour query, originating only in the new document's chunks but searching every chunk in the
  graph, yields chunk pairs, which expand through a chunk-to-entity membership map into candidate node pairs.
- Each pair is scored by Shepard inverse-distance weighting over every chunk pair its endpoints co-occur in.
- The per-pair accumulators form a commutative monoid, so the pass is order-independent and needs no recomputation as
  the corpus grows.
- The implementation is engine-neutral: the same weighted embedded edges go into FalkorDB, Kinetica, ArangoDB or Neo4j
  through one adapter contract.

**Paper:** B. K. Karamete, H. Casten. *Hidden relationships in a document-derived property graph: top-k chunk
embeddings and inverse-distance weighting over a dynamically evolving ontology.*
[arXiv:2609.00387](https://arxiv.org/abs/2609.00387) (2026).

---

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

For local embeddings and extraction via Ollama (models to pull, proxy flag), see `SETUP.md`.

## Use

### First run (Recreate mode)

1. Paste text. Blank lines separate documents by default.
2. **Generate embeddings.** The built-in embedder is deterministic and offline; switch the
   provider to any OpenAI-compatible `/v1/embeddings` endpoint for real semantics.
3. **Store in Kinetica.** Set **Write mode** to Recreate, creates the table if missing, then inserts in batches.
4. Search the table to confirm the vectors landed.

If the write can't get through, **Copy SQL** gives you the whole script for Workbench.

`samples/kinetica-notes.txt` holds three related paragraphs and two unrelated ones, so
distances mean something on a first run.

### Adding batches later (Append mode)

To build a graph incrementally with new documents and entities:

1. Paste a second batch of text (e.g., `samples/append-batch.txt`). Generate embeddings.
2. Set **Write mode** to Append. The app assigns new document IDs from `MAX(existing_id) + 1`.
3. Tune **k** (nearest neighbors per new doc, e.g., 5) and **β** (distance threshold, e.g., 0.5)
   to control which old documents feed into merging.
4. **Review the Graph SQL box**. The app generates DDL to create the graph tables (if missing)
   and UPSERT statements to merge entities and edges. Edit any statement before running.
5. **Run** the SQL. The graph incrementally updates: new entities merge with existing ones by
   blocking key, edges accumulate their IDW weights over time.

See CLAUDE.md for how the pieces fit together and what's unfinished.
