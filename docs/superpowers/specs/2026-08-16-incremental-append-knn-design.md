# Incremental Append + Top-k kNN Graph — Design

**Date:** 2026-08-16
**Status:** Approved (design), pending plan
**Depends on:** the entities + IDW-graph feature (merged, `master`)

## Goal

Add an **Append** write mode so new document-paragraph batches can be added to
an existing `vector_embeddings_<stamp>` table without id collisions, and
maintain the entity graph **incrementally** — comparing each new document only
against its **top-k nearest neighbors** (via Kinetica's vector index) instead
of against every existing document. Also surface graph creation as an
**editable, runnable SQL box** in the Graph panel.

## Motivation

Two problems with the current tool:

1. **Duplicate `doc_id`s.** `doc_id` is a per-batch row index assigned as
   `i+1` at Generate time; the table is named only by date and has no primary
   key; the insert path only appends. Running the pipeline more than once on
   the same day piles overlapping id ranges into one table (observed: 13 rows
   with `doc_id` 1×3, 2×2, 3×2, 4×2, 5–8×1). This also corrupts the graph
   post-join, which keys on `ARRAY_CONTAINS(n.doc_ids, e.doc_id)`.

2. **The graph build is O(D²) and unscalable.** An entity has no vector of its
   own — a Person/Business is a label attached to the documents it appears in.
   An edge between entities A and B is the IDW average of `cos(vec_i, vec_j)`
   over document pairs `(i ∈ A.docIds, j ∈ B.docIds)`. So "which entity pairs
   are related" is entirely a **document k-NN problem**. Comparing every new
   document against ALL existing documents grows without bound. At the target
   scale (hundreds of thousands to millions of paragraphs) this must run as a
   top-k nearest-neighbor search inside the database, not a full cross-product
   in the browser.

## Decisions (settled during brainstorming)

| Decision | Choice |
|----------|--------|
| Target scale | Hundreds of thousands → millions of paragraphs |
| Execution locus | All pairwise work runs in Kinetica (HNSW/CAGRA index + kNN + edge aggregation as SQL); browser orchestrates and reads back edges |
| Edge-weight update | **Exact-incremental** via per-edge accumulators `sum_wv`, `sum_w`; `weight = sum_wv/sum_w`; append adds contributions, never full recompute |
| Entity identity across batches | **Heuristic + blocking key** — indexed lookup against the persisted node table, then the existing heuristic merge within the small block |
| kNN bound | **Top-k + cosine-distance cutoff**, exposed as UI parameters `k` (default 20) and `β` (default 0.35) |
| Graph creation UX | Editable SQL textarea pre-populated with generated statements + a Run button; `CREATE … GRAPH` becomes runnable from the box (no longer comment-only) |

**Chosen architecture — browser-orchestrated, Kinetica-executed.** The browser
assigns ids, inserts the batch, fires a short sequence of SQL statements that
do the kNN + edge aggregation inside Kinetica, and reads back only the changed
edges. No new services, no DB-side stored procedures — the single HTML file
stays the whole app; all N-sensitive math is server-side against the index.
(Rejected: a Kinetica stored procedure — moves logic out of the version-
controlled file; an external worker service — adds a deployable dependency the
tool has never had.)

## Data model

**Embeddings table** `vector_embeddings_<stamp>`
- `doc_id INT` becomes a **PRIMARY KEY** (globally unique within the table).
- New batches assign ids from `SELECT MAX(doc_id)+1` (start at 1 on empty).
- **HNSW index** on `embedding` (`ALTER TABLE … ADD HNSW INDEX (embedding)`) —
  append-friendly, auto-updates as rows land.

**Node table** `graph_nodes_<stamp>` (now the *persistent* entity store)
- Existing columns: `node CHAR(64)` (canonical name, identity/PK), `label
  VARCHAR[]`, `doc_ids INT[]`, `doc_count INT`, `aliases VARCHAR[]`,
  `created_at TIMESTAMP`.
- **New:** `block_key CHAR(64)` — surname for Person, suffix-stripped core for
  Business — **indexed**. Turns incremental disambiguation into a cheap lookup.
- `doc_ids`, `aliases`, `doc_count` are **upserted** as batches merge in.

**Membership table** `graph_membership_<stamp>` — **new**
- `(node CHAR(64), doc_id INT, label VARCHAR[])`, indexed on `doc_id`.
- Normalized entity↔document bridge. `doc_ids INT[]` on nodes stays for the
  convenient display post-join, but the aggregation join runs off this table —
  `ARRAY_CONTAINS` does not scale to millions; an indexed equi-join does.

**Edge table** `graph_edges_<stamp>`
- Existing: `node1`, `node2 CHAR(64)`, `label VARCHAR[]`, `weight FLOAT`,
  `created_at`.
- **New:** `sum_wv DOUBLE`, `sum_w DOUBLE`; PRIMARY KEY `(node1, node2)`.
- Stored `weight = sum_wv/sum_w`. Append does `sum_wv += Δ, sum_w += Δ` and
  recomputes the ratio.

## Append pipeline (per new batch B)

1. **Assign global ids.** `SELECT MAX(doc_id) FROM <emb>` → new docs get
   `max+1 … max+|B|` (start at 1 on empty/fresh table).
2. **Embed + insert** new docs into the embeddings table (existing embed path,
   new ids). HNSW index absorbs them automatically.
3. **Extract mentions** from the new docs only (existing local/LLM extractor) →
   `{surface, label, docId}`.
4. **Incremental identity resolution (blocking).** For each mention: compute
   `block_key`; `SELECT * FROM <nodes> WHERE block_key = ?` (indexed → tiny
   candidate set); run the existing heuristic merge within
   {candidates ∪ same-block new mentions}. Each mention resolves to an existing
   node (append `doc_id`, extend `aliases`, bump `doc_count`) or a new node.
   **Upsert** into `<nodes>`; insert `(node, doc_id, label)` into `<membership>`.
5. **kNN candidate pairs (server-side).** For each new doc, top-k neighbors
   within the distance cutoff, over the whole table (old + new):

   ```sql
   SELECT nd.doc_id AS i, kn.doc_id AS j,
          (1 - COSINE_DISTANCE(nd.embedding, kn.embedding)) AS cos
   FROM <new_docs> nd, <emb> kn        -- lateral top-k per nd, HNSW-backed
   WHERE kn.doc_id <> nd.doc_id
     AND COSINE_DISTANCE(nd.embedding, kn.embedding) <= :cutoff
   -- keep only the k smallest distances per nd
   ```

   Because searches originate only from new docs, old↔old pairs are never
   revisited (already in the accumulators) — the scalability win.
   *(The exact lateral top-k-per-row syntax is verified against Kinetica's
   vector-search docs during planning; the shape is standard.)*
6. **Aggregate edge deltas.** Doc pairs → entity-pair contributions via the
   membership join:

   ```sql
   WITH p AS ( /* step 5, deduped so i<j for new-new pairs */ ),
   calc AS (SELECT i, j, 1.0/(1e-6 + (1-cos)) AS w, (1+cos)/2 AS v FROM p)
   SELECT LEAST(mi.node,mj.node) AS node1, GREATEST(mi.node,mj.node) AS node2,
          SUM(w*v) AS d_wv, SUM(w) AS d_w
   FROM calc c
   JOIN <membership> mi ON mi.doc_id = c.i
   JOIN <membership> mj ON mj.doc_id = c.j
   WHERE mi.node <> mj.node
   GROUP BY 1,2;
   ```
7. **Upsert edges.** For each `(node1,node2)`: `sum_wv += d_wv`,
   `sum_w += d_w`, `weight = sum_wv/sum_w`, set label. Read back changed edges
   (threshold-filtered, `TOP N`) for display.

## Correctness details

- **Double-count.** A *new↔new* pair surfaces twice (each end searches the
  other) → dedup to `i<j` in step 5. A *new↔old* pair surfaces once (old docs
  aren't search origins) → counted once, correct.
- **Same-document co-occurrence.** Two entities in the same new doc form a pair
  with cos=1 → `w` huge, `v=1` → edge≈1. kNN excludes self, so these `(i,i)`
  self-pairs are added explicitly in step 6 (preserves existing `computeEdges`
  co-occurrence behavior).
- **Idempotency / partial failure.** New ids are staged in a batch-tagged
  staging table and steps 4–7 are upserts keyed on identity, so a half-landed
  batch is safe to re-run — it converges rather than double-adding. (Addresses
  the "no transaction wrapper" gap already noted in CLAUDE.md.)

## UI

- **Write mode** selector in the store panel, extending the create-mode
  control: `Recreate (drop + rebuild)` · `Append (incremental)`.
- **Two new UI parameters in the Graph panel** (always visible, retyped per
  session like every other setting): `k` — neighbors per document (default 20)
  — and `β` — max cosine distance cutoff (default 0.35). Both feed the kNN step
  of the Append pipeline; they are labeled inputs, not hidden constants, so the
  operator can tune recall vs. cost per run.
- In Append mode the graph action becomes **"Append batch to Kinetica"** and
  runs the pipeline, logging each stage: ids assigned `N..M` → docs inserted →
  mentions extracted → "merged P into existing entities, created Q new" →
  "updated R edges, added S", with the progress bar over the statement
  sequence. The in-browser `computeEdges` stays as the small-scale / Recreate
  preview path.
- **Editable SQL box.** The Graph panel gains a `<textarea>` pre-populated with
  the generated statements (node/edge/membership DDL + inserts + the
  `CREATE … GRAPH` statement, and in Append mode the batch pipeline). A **Run**
  button executes the box contents statement-by-statement via `ksql()`; the box
  is user-editable before running. `CREATE … GRAPH` is populated live (not
  comment-only) but the user opts in by running the box. Copy/Download remain.
  This box **supersedes the current "Store graph in Kinetica" silent-execution
  behavior**: today that button fires the generated DDL + INSERTs invisibly and
  stops short of `CREATE … GRAPH`; the box makes every statement visible,
  editable, and includes the runnable graph creation.

## Error handling

- Every stage logs via `log()` with `ok`/`err`/`warn`/`dim`.
- Mid-batch failure is safe to retry (staging + identity-keyed upserts); the
  error message says so and points at the editable SQL box / Copy as the
  Workbench fallback.
- Missing HNSW index is detected before the kNN step; the tool offers the
  `ALTER TABLE … ADD HNSW INDEX` statement rather than silently full-scanning.
- `MAX(doc_id)` lookup failure aborts before any insert, so ids are never
  assigned against an unknown table state.

## Testing

New pure functions wrapped in `/* CORE:BEGIN */ … /* CORE:END */`, covered by
`node --test scripts/test_graph.mjs`:
- `nextIdBase(maxId)` — id offset assignment (empty table → base 1).
- `blockKey(name, label)` — surname / suffix-stripped core.
- `resolveIncremental(mentions, existingNodes)` — a new variant merges into its
  block; a new block spawns a node.
- `docPairContributions(pairs, membership)` — dedup-to-`i<j`, same-doc
  self-pair inclusion, `node1<node2` ordering.
- `mergeEdgeAccum(existing, delta)` — `weight = sum_wv/sum_w` after
  accumulation; `cos → (w, v)` delta math.
- SQL-emitter string-shape tests for the staging / kNN / aggregate / upsert /
  membership statements, like the existing `ddl()` tests.

**Not headlessly testable** (human/live verification, same boundary as the
first feature): live HNSW kNN results, actual upsert semantics, the lateral
top-k syntax, and `INT[]`/`ARRAY_CONTAINS` acceptance by the target Kinetica
version.

## Global constraints (carried from the project)

- Single file: all app code stays in `index.html`; no new dependencies, no CDN,
  no `localStorage`, no build step. `scripts/` may add stdlib-only helpers/tests.
- `DIM` stays 64 and is not a UI field.
- All user-facing strings go through `log(msg, cls)` with `ok`/`err`/`warn`/`dim`.
- SQL string escaping via `esc()` (double single quotes, strip NUL, preserve
  spaces); floats via `num()` (6 decimals).
- Pure core functions live inside CORE markers so the stdlib test harness can
  extract and eval them.
- `sql/schema.sql` is documentation kept in sync with the emitters in the same
  commit; `ddl()`/graph emitters are the single source of truth.

## Out of scope

- Chunking long paragraphs over the model's token limit.
- File upload / drag-and-drop ingestion.
- A table picker / history UI (the similarity panel's existing behavior stands).
- Switching the default embedder to a real model (still a provider choice).
- Graph *querying/solvers* beyond emitting a runnable `CREATE … GRAPH`.

## Kinetica specifics to verify during planning

- Exact lateral **top-k-per-row** kNN syntax (per-query `SELECT TOP k … ORDER BY
  <=>` is known; batched per-row form needs confirming against
  docs.kinetica.com vector-search patterns).
- **Upsert** mechanism for the accumulator update (`INSERT … ON CONFLICT` vs
  Kinetica upsert hint / `update_on_existing_pk`).
- `PRIMARY KEY` + `HNSW INDEX` coexistence and auto-update behavior on append.
- Whether `DOUBLE` accumulator columns or `FLOAT` suffice for `sum_wv`/`sum_w`
  precision over millions of contributions.
