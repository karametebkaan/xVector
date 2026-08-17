# xVector

A single-page tool that turns pasted paragraphs into 64-dimension vectors and writes them
into a local Kinetica instance as `vector_embeddings_<datestamp>`.

No build step, no package manager, no dependencies. `index.html` is the whole application:
markup, CSS, and vanilla JS in one file. Keep it that way unless there's a concrete reason
not to — the point of this tool is that it opens anywhere.

## Layout

```
index.html          the entire app
scripts/serve.py    static server + CORS-free proxy to Kinetica (stdlib only)
sql/schema.sql      reference DDL, kept in sync with ddl() in index.html
samples/            paragraph fixtures for manual testing
```

## Running it

```bash
python3 scripts/serve.py                                   # serves :8000, proxies to :9191
python3 scripts/serve.py --port 8080 --kinetica http://kinetica-host:9191
python3 scripts/serve.py --kinetica http://localhost:9191 --ollama http://localhost:11434
```

Then open http://localhost:8000 and set **Instance URL** to `/kinetica`. That routes SQL
through the proxy, which sidesteps both CORS and mixed-content blocking. Pointing the app
straight at `http://localhost:9191` also works if you open `index.html` from disk and
Kinetica is configured to allow the origin.

## How the app is wired

Six stages, each a small set of functions in the `<script>` block:

1. **Split** — `splitText()` cuts the textarea into documents (blank line / newline /
   custom delimiter / none) and applies a minimum-length filter.
2. **Embed** — `embedLocal()`, `embedRemote()`, or `embedOllama()` returns `{vec: Float64Array(64), tokens}`
   per document. Results live in the module-level `DOCS` array as
   `{id, text, tokens, vec}`.
3. **Extract entities & relations** — `extractLocalMentions()` or `extractLLM()` returns mentions
   `{surface, label, docId}` and relations `{node1, node2, predicate, docId}` in a combined call.
   Mentions are disambiguated into canonical entities `{name, label, docIds, count, aliases}`
   living in the `ENTITIES` array; relations are stored in the `RELATIONS` array.
4. **Build graph** — `computeEdges()` (for similarity) and `buildRelationEdges()` (for relations)
   return `{node1, node2, label, edge_kind, weight}` edges stored in the `EDGES` array,
   filtered by a threshold slider at render time.
5. **Emit SQL** — `ddl()`, `insertStatements()`, `graphDdl()`, `nodeInserts()`,
   `edgeInserts()`, and `graphScript()` build the statements. `fullScript()` joins them
   for Copy SQL / Download .sql. These are the single source of truth for the schema;
   `sql/schema.sql` is documentation, not the definition.
6. **Send** — `ksql(statement, limit)` POSTs to `/execute/sql` and normalizes the response.

`DIM` is a top-level constant set to 64. It is deliberately not a UI field — the table name
and the `VECTOR(64)` column would drift out of sync with previously written tables.

### The local embedder

Random-projection hashing, not a model. Each term maps through FNV-1a into a seeded
`mulberry32` PRNG that generates a fixed Gaussian vector; documents are the weighted sum of
their term vectors, L2-normalized. Weighting is `1 + log(1 + tf)`, multiplied by
`log(1 + N/df)` when the batch has 3+ documents. Optional word-pair terms carry half weight.

It is deterministic and offline, and lexical overlap ranks correctly — enough to exercise
the pipeline end to end. It has no semantic understanding. Anything about retrieval quality
means switching the provider to a real model, not tuning the hasher.

### The remote embedder

OpenAI-compatible `POST /v1/embeddings` with `{model, input: [...]}`, batched. Handles
`data[].embedding` or a bare array. When the model returns more than 64 dims, `reduceVec()`
either truncates (correct for Matryoshka models like `text-embedding-3-*`) or applies a
seeded random projection (better for everything else).

### The Ollama provider

`embedOllama()` posts a batch to `/ollama/api/embed` with the selected embedding model.
The response shape varies — `pickEmbeddings(json, expected)` normalizes `embedding` arrays
or bare arrays. When Ollama returns embeddings larger than 64 dims (e.g., `nomic-embed-text`
at 768-d), the app reduces via random projection (not truncation, since these are not
Matryoshka models). Model discovery runs via `/api/tags` to populate the embeddings dropdown;
the `/ollama` proxy route (configured with `--ollama http://localhost:11434`) handles both
GET and POST, mirroring the `/kinetica` proxy to sidestep CORS. The reduce "ask" option,
if selected, is treated as a projection (no lookup request necessary).

### Entity extraction and relation inference

The local heuristic extractor, `extractLocalMentions()`, is a stand-in for real NER, exactly
as the local hash embedder stands in for a real model. It parses Capitalized noun phrases,
strips titles and articles, and classifies each span into five types: **People** (2+ tokens or
title-prefixed), **Business** (biz-word suffix or 2+ letter acronym), **Organization** (org-word
keyword), **Facility** (facility-word keyword), or **Location** (gazetteered place name). Results
are mentions `{surface, label, docId}` — many variants of the same entity across documents.

Three disambiguation modes fold these into canonical entities `{name, label, docIds, count, aliases}`:

- **Ad-hoc heuristic** (default) — within each type, entities merge by surname plus given-initial
  matching (People), suffix-stripped and article-stripped core (Business and Organization, the `core`
  strategy), or normalized-name equality (Facility and Location, the `norm` strategy). Merged variants
  appear as aliases, and the longest variant becomes the canonical name.
- **None** (exact-match) — only identical-cased strings merge; each variant is a separate entity.
- **External API** — `resolveApi()` POSTs to a custom endpoint and falls back to heuristic on error.

Both providers run on Vertex AI and share one credential (Application Default Credentials);
`serve.py` calls Vertex over REST with `urllib` (stdlib only, no SDK) and never exposes a key
to the browser. The Claude provider uses the `/claude` route (Vertex Anthropic `:rawPredict`,
`run_claude()`) with models `claude-haiku-4-5-20251001` (fast) or `claude-opus-4-8` (best);
`_vertex_model_id()` rewrites dated ids to Vertex's `alias@YYYYMMDD` form, and `_extract_json()`
pulls the JSON object out of the model's text (the prompt asks for JSON; the endpoint does not
enforce a schema). The Gemini provider uses the `/gemini` route (Vertex `:generateContent`,
`run_gemini()`) with models `gemini-2.5-flash` (fast) or `gemini-2.5-pro` (best). This REST
transport replaced the earlier `claude` CLI subprocess, which reloaded a large agent system
prompt per call and was the source of extraction slowness. Both providers return mentions and
relations in a single JSON call, with `foldExtraction()` normalizing the response shape. Relations are a closed
predicate vocabulary: WORKS_AT, FOUNDED, LEADS, MEMBER_OF, LOCATED_IN, HEADQUARTERED_IN,
PART_OF, OWNS, AFFILIATED_WITH, VISITED, RELATED_TO (and `normPredicate()` maps unknown
predicates to RELATED_TO). Ollama *embeddings* remain (model discovery, embedding round-trip);
Ollama *chat extraction* is retired.

### Graph edges and tables

Edges are a two-layer multigraph: **similarity edges** (EMBEDDED, computed via True-IDW per
document pair) and **relation edges** (LLM predicates, weight 1.0). Similarity edge weights use
True-IDW: given cos = dot(a,b), d = 1−cos, w = 1/(ε+d) with ε=10⁻⁶, and v = (1+cos)/2, the
edge weight is Σ(w·v)/Σ(w) ∈ (0,1]. Same-document co-occurrence yields weight ≈ 1 (documents
are identical vectors). The threshold slider (default 0.5) filters edges at render/store time
only; it does not affect weight computation. Relation edges always have weight 1.0.

The grammar-aligned tables match Kinetica's ARRAY and CHAR types:
- **Node table** `graph_nodes_<datestamp>`: `node CHAR(64)` (canonical entity name), `label
  VARCHAR[]` (ARRAY['People'] | ARRAY['Business'] | ARRAY['Organization'] | ARRAY['Facility'] |
  ARRAY['Location']), `doc_ids INT[]` (documents where the entity appears, key for post-join),
  `doc_count INT`, `aliases VARCHAR[]` (merged variants), `block_key CHAR(64)` (blocking key for
  incremental merging in append mode), `created_at TIMESTAMP`, `PRIMARY KEY (node)`.
- **Edge table** `graph_edges_<datestamp>`: `node1` and `node2 CHAR(64)` (canonical names),
  `label VARCHAR[]` (ARRAY['EMBEDDED'] for similarity or ARRAY['<PREDICATE>'] for relations),
  `edge_label CHAR(32)` (edge classifier: 'EMBEDDED' or a predicate from the closed vocabulary),
  `edge_kind CHAR(16)` (layer type: 'embedded' for similarity, 'relation' for LLM predicates),
  `weight FLOAT` (IDW strength ∈ (0,1] for similarity; 1.0 for relations), `sum_wv DOUBLE`
  (cumulative numerator for incremental recomputation), `sum_w DOUBLE` (cumulative denominator),
  `created_at TIMESTAMP`, `PRIMARY KEY (node1, node2, edge_label)`.
- **Membership table** `graph_membership_<datestamp>` (new in append mode): `node CHAR(64)`,
  `doc_id INT`, `label VARCHAR[]`. Maps entities to the documents they appear in, enabling
  efficient aggregation joins at scale: instead of `ARRAY_CONTAINS(doc_ids, doc_id)`, the join is
  `membership.doc_id = embeddings.doc_id`, which is O(M) with index rather than O(D·M) full scan.

The `doc_ids INT[]` column in the node table still exists in both Recreate and Append modes;
it accumulates the full list of document IDs an entity appears in.

**Write mode (Recreate vs Append).** The UI offers a dropdown to choose between:
- **Recreate** — `CREATE OR REPLACE` for embeddings and graph tables; old data is lost. Use for
  one-off analysis or when you want to start fresh.
- **Append** — `CREATE TABLE IF NOT EXISTS` for all tables; new documents and entities are added
  incrementally. The `doc_id` primary key is assigned from `MAX(doc_id) + 1` via `nextIdBase()`,
  which prevents ID collisions across runs.

**Document ID assignment.** In Append mode, `nextIdBase()` queries the current max ID from the
embeddings table, then assigns `MAX+1, MAX+2, ...` to new documents. This runs synchronously in
the orchestrator before embedding (Task 6), ensuring no two batches ever share an ID.

**Incremental entity merging.** In Append mode, the kNN step finds neighbors of each new document.
For each neighbor, if its source entities already exist in the graph (detected by `blockKey()`
hashing), they merge: `resolveIncremental()` upserts them with accumulated doc_ids and updated
block_key, falls back to the heuristic. Entities new to this batch still use the heuristic. The
blocking key (`block_key` column, set by `blockKey()`) deterministically encodes the entity's
identity: a stable hash of canonical name and label. In Append, the canonical name is never renamed;
if an existing entity gains a new alias, the new variant is added to `aliases` but the `node` PK stays fixed.

**Incremental edge accumulators.** Edges use `sum_wv` and `sum_w` columns. When computing kNN
edges between new entities and old ones, the orchestrator (Task 6) calls `edgeUpserts()` instead
of `edgeInserts()`, which upserts: for each (node1, node2) pair, it either inserts a new row with
accumulators initialized to the current weight, or updates the existing accumulators. The final
`weight = sum_wv / sum_w` recomputes on demand from history. `mergeEdgeAccum()` (in CORE)
recomputes weights from accumulator rows returned by `edgeAccumQuery()`.

**kNN step and per-new-doc search.** After embedding the new batch, `knnQuery()` runs one query per
new document: `SELECT TOP k ... WHERE distance <= β` finds the k nearest neighbors in the existing
embeddings table (all historical docs). The results feed entity extraction and edge building. This
is the scalability win: only new documents are search origins; old documents are search targets. The
index bounds the query cost (per new doc, not per total doc pair).

**Membership table and aggregation.** The membership table (created and populated by `membershipInserts()`
in Append) decouples entity→doc mapping from the node table's denormalized `doc_ids INT[]`. During
incremental aggregation, the join `membership.node = nodes.node` on the upserted node set reconstructs
the per-entity doc list efficiently. This avoids re-reading and re-expanding the entire `doc_ids` array
at the DB layer, which scales better for entities appearing in hundreds of documents.

**Canonical-name-is-stable rule.** In Append mode, the PK (node name) never changes. When an existing
entity acquires a new name variant (e.g., "K Karamete" appearing as "Kaan Karamete"), the merge puts
the longest/best existing variant back as the canonical node, and the new variant becomes an alias.
This ensures graph queries and external links to entities remain valid across appends.

`graphDdl()`, `nodeInserts()`, `edgeInserts()`, `edgeUpserts()`, `membershipInserts()`, and `graphScript()`
emit the full DDL and INSERT/UPSERT statements. `createGraphSql()` emits a runnable `CREATE UNDIRECTED GRAPH`
statement (no longer commented), aliasing `(1 - weight) AS WEIGHT_VALUESPECIFIED` to convert edge strength
to solver cost. The graph name comes from `graphNameOf(opts)`: the **Graph name** input (`#gName`) when it is
identifier-safe (`[A-Za-z_]\w*`, optional `schema.` prefix — it lands in DDL unquoted), else the stable
default `entity_graph_<stamp>`. The editable SQL box (part of Task 7) replaces the old silent store button,
allowing users to review and edit all statements (including the `CREATE GRAPH`) before execution; when the box
runs, the `CREATE ... GRAPH` statement is detected and logged as a distinct green `Graph '<name>' created` line
so graph creation is visible, not buried in the per-statement log.

### Palette extension

Colors extend the existing per-vector strip convention to five entity types:
- Indigo `--signal` for People
- Amber `--warm` for Business
- Teal `--org` for Organization
- Plum `--facility` for Facility
- Green `--loc` for Location

These are used in the Entities panel and graph visualization to visually distinguish entity types.

### Testing the pure core functions

`scripts/test_graph.mjs` (`node --test scripts/test_graph.mjs`) covers the pure core
functions — `extractLocalMentions()`, `mergeMentions()`, `computeEdges()`, `blockKey()`,
`mergeEdgeAccum()`, `resolveIncremental()`, `pickEmbeddings()`, `foldExtraction()`,
`buildRelationEdges()`, `normLabel()`, `normPredicate()`, `classifySpan()` (five-type),
`graphNameOf()`, and the SQL emitters — which are wrapped in `/* CORE:BEGIN */ … /* CORE:END */` markers so
the stdlib-only harness can extract and eval them. These functions underpin both Recreate
and Append workflows. `scripts/test_serve.py` covers the proxy route dispatcher
`resolve_upstream()`, and the Claude/Gemini transport functions `run_claude()` and `run_gemini()`.

## Kinetica specifics worth not re-deriving

Verified against docs.kinetica.com 7.2.

**Vector column.** `VECTOR(64)` or `VECTOR(64, NORMALIZE)`; NORMALIZE forces L2 magnitude 1
on insert. Values go in as bracketed string literals: `'[0.1,-0.2,...]'`.

**Distance functions.** `COSINE_DISTANCE`, `L2_DISTANCE` (alias `EUCLIDEAN_DISTANCE`),
`L1_DISTANCE`, `LINF_DISTANCE`, `LP_DISTANCE(v1,v2,p)`, `DOT_PRODUCT`,
`L2_SQUAREDDISTANCE`. Operator shorthands: `<->` L2, `<=>` cosine, `<#>` dot product.
Column functions: `L1_NORM`, `L2_NORM`, `LINF_NORM`, `LP_NORM`, `NTH(v,n)`, `SIZE(v)`.

**Top-k form.** `SELECT TOP 5 ... ORDER BY distance` — `TOP` goes after SELECT, not a
trailing LIMIT.

**Indexes.** `ALTER TABLE t ADD HNSW INDEX (col)` updates automatically as rows change.
`ADD CAGRA INDEX (col)` is faster but needs manual refresh. HNSW is the default here
because the table is append-target.

**REST call shape.** `POST {base}/execute/sql`, Basic auth, body:

```json
{"statement":"...","offset":0,"limit":-9999,"encoding":"json",
 "request_schema_str":"","data":[],"options":{}}
```

Errors come back HTTP 200 with `{"status":"ERROR","message":"..."}` — check the body, not
the status code. On success the outer object carries `data_str`, a JSON *string* of the
real response; inside that, `json_encoded_response` is another JSON string holding
`{column_1:[...], column_2:[...], column_headers:[...]}`. `ksql()` unwraps both layers and
`recordsToRows()` transposes columns into rows. Both parse defensively — shapes vary across
versions, so failures degrade to a raw dump rather than throwing.

## Conventions

- Vanilla JS, no framework, no CDN. Nothing that requires network access to render.
- No `localStorage`. Settings are retyped each session by design; if that changes, gate it
  behind a feature the user opts into rather than silently persisting credentials.
- Every user-facing string goes through `log(msg, cls)` with `ok` / `err` / `warn` / `dim`.
  Errors say what failed and what to do next — the Kinetica write failure points at Copy
  SQL as the fallback path.
- SQL string escaping is `esc()`: double the single quotes, strip NULs. If a column type
  ever accepts user input beyond `content`, run it through `esc()` too.
- Floats serialize at 6 decimals via `num()`. Enough precision for 64 dims, keeps the
  INSERT statements readable.
- Colors and type live in the `:root` custom properties. Indigo `--signal` is positive
  dimensions, amber `--warm` is negative; that pairing is used in the per-vector strip and
  should stay consistent if more visualizations are added.

## Known gaps / likely next steps

- Server-side embedding path. Kinetica can do the whole job in SQL via `CREATE MODEL` +
  `GENERATE_EMBEDDINGS(... DIMENSIONS => 64)`, which removes the browser round-trip
  entirely. Would slot in as a third provider option.
- No file upload — text arrives by paste only. Drag-and-drop of `.txt`/`.md` with the same
  splitting rules is the obvious extension.
- Long paragraphs are not chunked. A single document over the model's token limit will fail
  at the API rather than being split.
- Inserts are one statement per batch with no retry. A failed batch leaves earlier batches
  committed; there's no transaction wrapper.
- The similarity panel queries `LAST_TABLE` if a write succeeded this session, otherwise the
  current table name field. No table picker, no history.
- `sql/schema.sql` is maintained by hand. If `ddl()` changes, update it in the same commit.
