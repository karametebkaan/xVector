# xVector — Entities → Graph design

**Date:** 2026-08-16
**Status:** Approved for planning
**Scope:** Add two pipeline stages to `index.html` — entity extraction and graph
building — plus their Kinetica output, keeping the tool's single-file, no-dependency,
offline-first character.

## 1. Goal

From the paragraphs already pasted and embedded, extract **People** and **Businesses**
(organizations, facilities, institutions — folded into one "Business" label), then relate
those entities to each other as weighted graph edges and write the result to Kinetica as
grammar-aligned node and edge tables.

Two new stages slot in after **Embed**:

```
Text → Split → Embed → Extract entities → Build graph → Send
        DOCS        ENTITIES        EDGES        Kinetica
```

Vectors are L2-normalized, so cosine similarity between two document vectors is their dot
product — cheap to compute in the browser.

## 2. New module-level state

Alongside the existing `DOCS`:

- `ENTITIES = [{ name, label, docIds:[...], count, aliases:[...] }]`
  - `name` — canonical display form, **also the Kinetica node identity**.
  - `label ∈ {"Person", "Business"}`.
  - `docIds` — sorted unique document ids the entity is stated in.
  - `aliases` — surface variants merged into this entity (provenance).
- `EDGES = [{ node1, node2, type, weight }]`
  - **All** cross-entity pairs, computed once, unfiltered. The threshold slider filters at
    render/store time (so the slider is live and free).
  - `node1 < node2` by canonical name (undirected, stored once).
  - `type ∈ {"person-person", "person-business", "business-business"}`.
  - `weight ∈ (0, 1]`.
- `LAST_GRAPH = { nodes:"", edges:"" }` — table names of the last successful graph write,
  for the post-join hint.

An internal `Map<name,int>` index is used **only in the browser** to build the edge matrix
efficiently; it never reaches Kinetica.

## 3. Stage A — Extract entities

Two providers, mirroring the existing local/remote embedder split. Selected in a new
**Entities** panel independently of the embedding provider.

### 3.1 Local heuristic (`extractLocal(docs)`) — default, offline, deterministic

A stand-in for real NER, exactly as the local hash embedder stands in for a real model.
The console and docs state this plainly.

- Candidate spans = runs of Capitalized words, allowing internal connectors
  (`of`, `and`, `&`, `the`, `for`) so "Bank of America" and "University of Texas" stay
  whole. All-caps acronyms (≥2 letters) are candidates too.
- **Business** if the span contains/ends with a gazetteer keyword or legal suffix:
  Inc, Inc., LLC, Ltd, Corp, Corporation, Co, Company, GmbH, PLC, LP, LLP, Group, Holdings,
  Partners, Systems, Technologies, Labs, Bank, Capital, Ventures, University, College,
  Institute, Hospital, Clinic, Airport, Station, Stadium, Museum, Library, Hotel,
  Foundation, Association, Agency, Department, Ministry, Committee, Center, Centre, School,
  Church, Factory, Plant, Mall, Market, Store (extendable list).
- **Person** if title-preceded (Mr, Mrs, Ms, Dr, Prof, President, CEO, Senator, Governor…)
  or a 2–3 token Capitalized run with no business keyword.
- Single bare-capitalized tokens are skipped (sentence starts, ambiguous places).
- Output: raw mentions `[{surface, label, docId}]` fed to disambiguation (Stage B-pre).

### 3.2 LLM (`extractLLM(docs)`) — optional, higher quality

- `POST {base}/v1/chat/completions` in JSON mode. Prompt: extract entities labeled
  `Person` or `Business` (organizations, facilities, institutions) and, per entity, the doc
  ids it appears in and a `canonical` normalized name.
- Batched; response parsed defensively (same posture as `ksql` — shapes vary, degrade to a
  logged error rather than throwing).
- Its own endpoint + model fields in the Entities panel, defaulting the base URL and API
  key to the existing embedding-API fields when set.

## 4. Stage B — Entity disambiguation (optional, 3 modes)

Runs on the raw mentions before nodes are finalized. Mode selector in the Entities panel,
**defaulting to Ad-hoc heuristic**. Merged variants are always surfaced as `aliases` and
stored on the node, so any merge is auditable/reversible by re-running with a different mode.

- **Ad-hoc heuristic** *(default)* — deterministic, offline:
  - PERSON: merge when surnames match **and** given names are compatible — one is the
    other, one is an initial of the other, or one token set is a superset. Canonical = the
    longest / most complete surface form.
    - Example: `Kaan Karamete` + `K Karamete` → surname `Karamete` = `Karamete`, given
      `Kaan ⊇ K` → merge, canonical `Kaan Karamete`,
      `aliases = ["Kaan Karamete","K Karamete"]`.
  - BUSINESS: strip legal suffixes (Inc/LLC/Corp/…), merge when the core name is identical.
    - Example: `Acme Corp` + `Acme Inc` → core `Acme` → merge.
  - Conservative: differing initials do not merge (`Jane Smith` ≠ `John Smith`).
- **None (exact match)** — case/punctuation/whitespace-normalized exact key only; no
  merging. Zero false positives, more nodes.
- **External API** — `POST {resolveUrl}` with the entity list; expects canonical groupings
  back. UI, request body, and defensive response parsing are wired now; the endpoint is a
  configurable field left blank by default (pluggable later). Falls back to heuristic +
  logged warning if unreachable.

Canonicalization key for all modes starts from: trim, collapse whitespace, strip
surrounding punctuation and trailing possessive `'s`, case-fold. Display `name` = most
frequent original surface form within the merged group. Label conflicts resolve by majority;
tie → Business if any business-keyword hit, else Person.

## 5. Stage C — Build graph (True IDW weighted mean)

For each unordered pair of distinct entities (A, B), over every document pair
`a ∈ Docs(A)`, `b ∈ Docs(B)`:

```
cos = dot(vec_a, vec_b)          // vectors normalized ⇒ cosine similarity
d   = 1 − cos                    // distance; same document ⇒ d = 0
w   = 1 / (ε + d)               // ε = 1e-6; bounded, near-∞ at co-occurrence
v   = (1 + cos) / 2             // similarity mapped to [0,1]
weight(A,B) = Σ(w·v) / Σ(w)     // ∈ (0,1]; nearer doc pairs dominate
```

- Co-occurrence (`a == b`): `cos = 1`, `d = 0`, `w = 1/ε` (dominates), `v = 1` → weight ≈ 1
  ("absolutely an edge"). The bounded kernel means no literal infinity and the result is
  provably in `(0,1]` — no clamp needed.
- `edge_type` from endpoint labels: person-person / person-business / business-business.
- Edge kept iff `weight ≥ threshold` (slider 0–1, step 0.01, default 0.5). Slider only
  filters; weights are computed once.
- `ε` and the Dijkstra cost transform live as commented top-level constants.
- Complexity is `O(M² · D²)` worst case (M entities, D docs each). Acceptable for the tool's
  paste-sized inputs; a `log()` warning fires past a guard threshold (e.g. > 2M doc-pair
  operations), consistent with the "degrade, don't throw" convention.

**Forward to Dijkstra:** stored `weight` is a **strength** in `(0,1]`. Graph solvers
minimize cost, so `CREATE GRAPH` aliases `(1 − weight) AS WEIGHT_VALUESPECIFIED`
(or `−LN(weight)`). Both are bounded and non-negative — the reason weights stay on a 0–1
base rather than 0–100.

## 6. Kinetica output — grammar-aligned tables

Column names match the Kinetica graph grammar so a future graph is a `SELECT *`. Node
identity is the canonical **name** (`CHAR(64)`); edges reference `node1`/`node2` by that
same name — there is no integer id, hence nothing to keep in sync.

```sql
CREATE TABLE IF NOT EXISTS <prefix>_nodes_<stamp> (
    node      CHAR(64)   NOT NULL,   -- NODE  : canonical entity name = identity
    label     VARCHAR[]  NOT NULL,   -- LABEL : ARRAY['Person'] | ARRAY['Business']
    doc_ids   INT[]      NOT NULL,   -- documents the entity is stated in  (post-join key)
    doc_count INT,
    aliases   VARCHAR[],             -- merged surface variants
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS <prefix>_edges_<stamp> (
    node1   CHAR(64)  NOT NULL,      -- NODE1 : source entity name
    node2   CHAR(64)  NOT NULL,      -- NODE2 : target entity name
    label   VARCHAR[] NOT NULL,      -- LABEL : ARRAY['person-business']
    weight  FLOAT     NOT NULL,      -- IDW strength (0,1]
    created_at TIMESTAMP NOT NULL
);
```

- Inserts use `ARRAY[...]` literals: `ARRAY['Person']`, `ARRAY[1,3,5]`, `ARRAY['person-business']`.
  Names run through `esc()`; entity names are validated/guarded to 64 chars (logged if
  truncated). `weight` serialized via `num()`.
- `doc_ids` as `INT[]` gives a clean post-join:
  ```sql
  SELECT n.node, e.doc_id, e.content
  FROM <prefix>_nodes_<stamp> n
  JOIN vector_embeddings_<stamp> e ON ARRAY_CONTAINS(n.doc_ids, e.doc_id);
  ```
  `INT[]` + `ARRAY_CONTAINS` verified against the instance at build; `VARCHAR[]` is the
  documented fallback.
- Reuses `ksql`, batched inserts, `createMode` (create-if-missing / replace / insert-only),
  and the stamp/schema fields. New **Graph table prefix** field, default `graph` →
  `graph_nodes_<stamp>` / `graph_edges_<stamp>`.
- **CREATE GRAPH** is emitted as a commented-out trailer in Copy SQL only (tables are the
  default output — "for the time being"):
  ```sql
  -- CREATE UNDIRECTED GRAPH entity_graph_<stamp> (
  --   NODES => INPUT_TABLES((SELECT * FROM <prefix>_nodes_<stamp>)),
  --   EDGES => INPUT_TABLES((SELECT node1, node2, label,
  --                          (1 - weight) AS WEIGHT_VALUESPECIFIED
  --                          FROM <prefix>_edges_<stamp>)));
  ```

## 7. New functions (matching existing style)

- Extract: `extractLocal(docs)`, `extractLLM(docs)`.
- Resolve: `disambiguate(mentions, mode)` (heuristic / none / api), `personKey()`,
  `businessKey()`.
- Assemble: `buildEntities(mentions)` → `ENTITIES`.
- Graph: `cosineOf(a,b)` (dot product), `buildEdges()` → `EDGES`, `filterEdges(threshold)`.
- SQL: `graphDdl()`, `graphNodeInserts()`, `graphEdgeInserts()`, `graphScript()`
  (mirrors `ddl()`/`insertStatements()`/`fullScript()`).
- Render: `renderEntities()`, `renderGraph(threshold)`.

## 8. UI (two new panels, existing visual language)

- **Entities** panel: extraction provider select (Local heuristic / LLM) with LLM
  endpoint+model fields shown on demand; disambiguation mode select (Heuristic / None / API)
  with the API URL field; **Extract entities** button; results grouped by label with counts,
  doc ids, and merged aliases. Palette: indigo `--signal` = People, amber `--warm` =
  Business (extends the existing strip convention; noted in CLAUDE.md).
- **Graph** panel: live **threshold slider** with value readout; **Build graph** button;
  edge list `source — target · type · weight` sorted desc with a
  `#nodes / #edges kept of total` summary; **Store graph in Kinetica** and **Copy graph SQL**
  buttons.

## 9. Conventions & docs

- Vanilla JS, no framework, no CDN, no `localStorage`. Every user-facing string via
  `log(msg, cls)` with ok/err/warn/dim; graph-write failure points at Copy graph SQL as the
  fallback, matching the existing write-failure message.
- SQL escaping via `esc()`, floats via `num()`.
- Update `sql/schema.sql` (add node/edge DDL, inserts, the commented CREATE GRAPH, and the
  post-join query) and `CLAUDE.md` (document the two new stages, the IDW edge formula, the
  grammar-aligned tables, and the extended palette use) in the same change — per the repo's
  hand-maintained-schema rule.

## 10. Out of scope (YAGNI)

- Node-link graph **visualization** — edge **table/list** only for now.
- Executing `CREATE GRAPH` from the app — it is emitted as commented SQL only.
- Coreference beyond the three disambiguation modes (no vector-based identity resolution).
- Retries / transaction wrapper on graph inserts — same one-statement-per-batch behavior as
  the existing embedding write.
