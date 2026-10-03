# SP2 — Ontology Expansion Design

**Date:** 2026-08-16
**Branch:** `feature/incremental-append-knn`
**Status:** revised (Claude + Gemini providers added; Ollama extraction
retired) — awaiting user re-review before implementation plan
**Predecessor:** SP1 (native Ollama provider) — complete, merge-ready
**Roadmap:** sub-project 2 of 3 (Ollama provider → **ontology expansion** → kNN finish)

## Goal

Expand xVector's entity model from two types (Person/Business) to a
user-mandated **five-type ontology** — Business, People, Organization,
Facility, Location — and add a **two-layer edge multigraph**: LLM-extracted
typed *relation* edges alongside the existing embedding-similarity
(`EMBEDDED`) edges. The LLM performs both entity typing and relation
extraction in a single schema-constrained call.

## Scope

Full package in one spec (user decision): five-type nodes **and** typed
relation edges **and** the two-layer multigraph where relation and `EMBEDDED`
edges coexist on the same node pair. The plan decomposes this into tasks; the
design travels as one document.

Out of scope (later sub-projects / follow-ups):
- SP3 kNN finish/integration of incremental append + top-k search.
- Directed graph solving (relations store direction via row order, but the
  emitted graph stays UNDIRECTED — see §5).
- LLM confidence-modulated relation weights (relations are weight ≈ 1.0 for
  now; the accumulator columns leave room to add this later).

## Global Constraints (bind every task)

- Single file: app code in `index.html`; no deps/CDN/localStorage/build.
  `scripts/` stays stdlib-only.
- `DIM` stays 64, never a UI field.
- User-facing strings go through `log(msg, cls)` — `ok`/`err`/`warn`/`dim`.
- SQL escaping via `esc()`; floats via `num()` (6 decimals).
- Pure DOM-free logic lives inside `/* CORE:BEGIN … CORE:END */` so
  `scripts/test_graph.mjs` (`node --test`) can extract and eval it.
- LLM structured output is schema-constrained per provider (Claude
  `--json-schema`, Gemini `responseSchema`/`responseMimeType`), matching the
  SP1 hardening; all providers share the same post-processing guards.
- Credentials never reach the browser. Cloud LLM calls go through same-origin
  proxy routes in `scripts/serve.py` (stdlib-only: `subprocess` + `urllib`),
  mirroring the existing `/kinetica` and `/ollama` routes.
- Canonical-name-is-stable rule (append mode): a node's PK name never changes;
  new variants become aliases.

---

## 1. Type system

### 1.1 The five types

| Type | Definition | Examples |
|------|-----------|----------|
| **People** | individual humans | Kaan, Tan |
| **Business** | for-profit commercial companies | Bloomberg, BabelStreet |
| **Organization** | government / agency / NGO / academic / associations | State Department, a university |
| **Facility** | physical built structures & venues | airport, stadium, hospital, museum, plant |
| **Location** | geographic places | Arlington, Brooklyn, Vienna |

The Business-vs-Organization boundary is **commerciality**: for-profit
company → Business; government/agency/NGO/academic/association → Organization.
The LLM decides commerciality; the local extractor approximates lexically.

Note the label string is **"People"** (not "Person") in the five-type world.
Existing code uses `"Person"`. **Decision (settled, see §7.1): the canonical
label token is `"People"`.** The implementation renames it consistently across
extraction, disambiguation, palette, and tests — every `=== "Person"`
comparison and every `"Person"`/`"Business"` literal is updated to read from
the `TYPES` source of truth (§1.2) rather than hard-coding strings.

### 1.2 Single source of truth

Introduce a `TYPES` structure (CORE) mapping each type to its metadata:
color CSS var name and blocking/merge strategy (`"person"` name-logic vs
`"core"` suffix-strip vs `"norm"` normalized-name). Extraction, disambiguation,
and rendering all read from `TYPES` rather than hard-coding label strings.

### 1.3 Palette

Extends the existing per-strip convention. Add three CSS custom properties in
`:root`; keep the two existing ones.

| Type | Var | Hex |
|------|-----|-----|
| People | `--signal` | `#4B2ED6` (existing indigo) |
| Business | `--warm` | `#C97A19` (existing amber) |
| Organization | `--org` | `#0E7C86` (deep teal) |
| Facility | `--facility` | `#A6317D` (plum) |
| Location | `--loc` | `#3B7A2E` (forest green) |

`--good`/`--bad` stay reserved for status, not types. The Entities panel
colors each entity by its type via `TYPES[label].colorVar`.

---

## 2. Extraction

### 2.1 LLM providers and transport

The real-LLM extractor runs against a hosted Claude or Gemini model, reached
through same-origin proxy routes in `scripts/serve.py` so no credential ever
touches the browser. Both are stdlib-only. The Ollama *extraction* provider
is **retired** (see §2.1.3); Ollama remains an *embeddings* provider (SP1),
which is untouched by this spec.

#### 2.1.1 Claude provider — `/claude` route

serve.py's `/claude` handler shells out (stdlib `subprocess`) to the local
`claude` CLI using its stored login (Vertex — no API key):

```
claude -p --output-format json --json-schema <INLINE_JSON_SCHEMA> --model <id>
```

with the prompt on **stdin** and a timeout. The CLI emits one JSON object on
stdout whose `structured_output` field is the schema-validated result (already
parsed — no second-layer unwrap). On `is_error:true`, a non-zero exit, or a
timeout, the handler returns `{"status":"ERROR","message":...}` (same shape
`/kinetica` uses so the browser's error path is unchanged). Model IDs are
passed through verbatim; `--json-schema` takes **inline JSON**, not a file
path. Models: `claude-haiku-4-5-20251001` (default — fast) and
`claude-opus-4-8` (selectable — best extraction). A `--claude-bin` flag
defaults to `claude` on `PATH`.

#### 2.1.2 Gemini provider — `/gemini` route

serve.py's `/gemini` handler obtains a Vertex access token via
`gcloud auth print-access-token` (stdlib `subprocess`, stored gcloud login —
no API key) and POSTs (stdlib `urllib`) to the Vertex REST endpoint:

```
POST https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent
Authorization: Bearer <token>
```

with `generationConfig.responseMimeType:"application/json"` and
`generationConfig.responseSchema` = the combined schema. The response text is
JSON-parsed; token/HTTP/`gcloud` failures return the same
`{"status":"ERROR","message":...}` shape. Project and region come from
`--gcp-project` (default: `gcloud config get-value project`) and `--gcp-region`
(default `global`). Models: `gemini-2.5-flash` (default — fast) and
`gemini-2.5-pro` (selectable). One-time operator setup: `gcloud auth login`.
Gemini's `responseSchema` dialect is a restricted subset (no `$ref`, limited
keywords); the schema stays flat enough to satisfy it, and the shared
post-processing guards below are the safety net regardless.

#### 2.1.3 Ollama extraction retired

The SP1 Ollama *chat/extraction* provider and its `format`-schema path are
removed from the extraction dropdown (the user's "offline LLM can go"
decision). The `/ollama` proxy route and the Ollama *embeddings* provider
stay — embeddings still need a real local option, which neither cloud LLM
supplies here.

#### 2.1.4 The combined call

Every provider issues ONE schema-constrained call returning BOTH entities and
relations:

```json
{
  "entities":  [{"name":"...","label":"People|Business|Organization|Facility|Location","doc_ids":[int]}],
  "relations": [{"subject":"...","predicate":"WORKS_AT|...","object":"...","doc_ids":[int]}]
}
```

- `label` and `predicate` are `enum`-constrained in the schema (Claude
  `--json-schema`; Gemini `responseSchema`). Determinism is requested where
  the provider supports it (Gemini `temperature:0`).
- **Post-processing guards (shared, all providers):**
  - `normLabel(v)` folds any label wording onto the five types (exact match
    first; then keyword contains — `busin`→Business, `org|agenc|govern|
    ngo|univers|institut|associat`→Organization, `facilit|airport|stadium|
    hospital|museum|plant|station|venue`→Facility, `locat|city|country|
    region|place`→Location; default People). The mapping table lives in CORE
    and is unit-tested.
  - `normPredicate(v)` folds a predicate onto the closed vocabulary
    (§3), defaulting to `RELATED_TO`.
  - `doc_ids` are trusted only when they name a doc in the batch; otherwise
    recovered by scanning the batch for the surface form (the SP1 fix,
    reused for both entities and relation endpoints).
  - Empty-name entities and relations with an empty subject or object are
    dropped.

`extractLLM` returns `{mentions:[{surface,label,docId}], relations:[{subject,predicate,object,docIds}]}`.
(The current return is a bare mentions array; callers update to read the
`mentions` field. See §7.)

### 2.2 Local path — best-effort five-type (`extractLocalMentions` / `classifySpan`)

The local heuristic remains a documented stand-in. `classifySpan` returns one
of the five types or `null` (unlabeled → dropped):

- **People** — title-prefixed, or a 2+-token capitalized span with no
  business/facility/org keyword.
- **Business** — contains a commercial suffix (`inc|llc|ltd|corp|co|company|
  gmbh|plc|lp|llp|holdings|partners|ventures|capital`).
- **Facility** — contains a facility keyword (`airport|stadium|museum|
  hospital|clinic|hotel|station|mall|plant|factory|library|theater|arena|
  center|centre`).
- **Organization** — contains an org keyword (`agency|department|ministry|
  committee|university|college|institute|school|foundation|association|
  bank|church`). (Bank/church are judgment calls; documented as approximate.)
- **Location** — a small built-in gazetteer of common place names; otherwise
  a single-token or bare capitalized span with no other signal stays
  `null` rather than guessing.

The existing keyword sets (`BIZ_WORDS`) are split into `BIZ_SUFFIX_WORDS`,
`FACILITY_WORDS`, `ORG_WORDS` accordingly. Precedence when multiple match:
Business (suffix) > Facility > Organization > People. **The local path
produces no relations** — the relation layer is LLM-only; local runs still
get `EMBEDDED` similarity edges. A `log(...,"warn")` note states this when
extraction provider is local and the graph is built.

---

## 3. Relation predicate vocabulary

Closed canonical set (enum) + `RELATED_TO` fallback:

| Predicate | Typical typing (subject → object) |
|-----------|-----------------------------------|
| `WORKS_AT` | People → Business/Organization |
| `FOUNDED` | People → Business/Organization |
| `LEADS` | People → Business/Organization |
| `MEMBER_OF` | People → Organization |
| `LOCATED_IN` | Business/Organization/Facility → Location |
| `HEADQUARTERED_IN` | Business/Organization → Location |
| `PART_OF` | Organization → Organization, Facility → Organization |
| `OWNS` | Business → Business/Facility |
| `AFFILIATED_WITH` | org ↔ org / facility (generic association) |
| `VISITED` | People → Location/Facility |
| `RELATED_TO` | generic fallback / anything unmatched |

Typing is advisory (guides the prompt); it is NOT enforced at storage — a
`WORKS_AT` between two People still stores, because forcing type rules would
drop true-but-unusual relations. `normPredicate` folds any out-of-set string
to `RELATED_TO`.

---

## 4. Disambiguation (per-type)

`sameEntity`, `blockKey`, and `mergeMentions` become type-aware via
`TYPES[label].strategy`:

- **People** (`strategy:"person"`) — existing surname-equality + given-name
  initial-compatibility logic (`personName`, `givenCompatible`).
- **Business, Organization** (`strategy:"core"`) — suffix-stripped core match
  (`businessCore`, extended to strip both commercial and org/facility
  suffixes where appropriate — Business strips `BIZ_SUFFIX`, others strip a
  trailing generic descriptor if present, else compare normalized name).
- **Facility, Location** (`strategy:"norm"`) — normalized-name equality
  (`normalizeName`: trim, collapse whitespace, strip punctuation/articles,
  lowercase).

`blockKey(name, label)` returns the strategy-appropriate key:
`personName(name).sur` for People, `businessCore(name)` for core-strategy
types, `normalizeName(name)` for norm-strategy types. `mergeMentions` only
merges within the same `label`, so cross-type collisions never occur.

`resolveIncremental` is unchanged in shape; it already keys on
`label + " " + block_key` and calls `blockKey`/`sameEntity`, so it picks
up the type-aware behavior automatically. Canonical-name-stable rule holds.

---

## 5. Two-layer edge model

The graph is a **multigraph** with two edge sources, both carrying
`weight ∈ (0,1]` where solver cost `= 1 - weight`.

### 5.1 Schema — `graph_edges_<ts>`

Columns (changes in **bold**):
- `node1 CHAR(64)`, `node2 CHAR(64)`
- **`label VARCHAR[]`** — `ARRAY['EMBEDDED']` for similarity edges, or
  `ARRAY['<PREDICATE>']` for relation edges (keeps the existing ARRAY convention)
- **`edge_kind CHAR(16)`** — `'relation'` | `'embedded'`
- `weight FLOAT` — current strength
- `sum_wv DOUBLE`, `sum_w DOUBLE` — IDW accumulators (relation edges init
  `sum_wv = sum_w = 1.0` → weight 1.0)
- `created_at TIMESTAMP`
- **`PRIMARY KEY (node1, node2, label)`**

The label is stored as a single-element ARRAY (as today) but the PK references
it; if Kinetica cannot key on an ARRAY column, the plan adds a scalar
`edge_label CHAR(32)` mirroring the array's element and keys on that instead
(see §7 ambiguity). One row per (pair, predicate) plus one `EMBEDDED` row.

### 5.2 EMBEDDED layer (`computeEdges`)

Unchanged math: all-pairs cosine → True-IDW `w = 1/(ε+d)`, `v=(1+cos)/2`,
edge weight `Σ(w·v)/Σ(w)`. Now emits `label=['EMBEDDED']`,
`edge_kind='embedded'`, node order **sorted** (symmetric). The old
`person-business`-style type-pair label on edges is **retired** — node types
live on the nodes; the edge label is now the layer/predicate.

### 5.3 Relation layer (`buildRelationEdges`)

`buildRelationEdges(relations, entities)` (CORE, new):
1. Build a surface→canonical-node index from the disambiguated `entities`
   (each entity's `name` + `aliases`, matched via `sameEntity`/`normalizeName`).
2. For each relation, resolve `subject` and `object` to canonical node names.
   Drop (and count) relations where either endpoint doesn't resolve.
3. Emit `{node1:subjectCanonical, node2:objectCanonical, label:[predicate],
   edge_kind:'relation', weight:1.0, sum_wv:1.0, sum_w:1.0, docIds}` in
   **subject→object row order** (direction preserved for readability).
4. If subject and object resolve to the same node, drop (no self-loops).

Dropped-relation count is surfaced via `log(...,"warn")`.

### 5.4 Emitters & upserts

`edgeInserts`, `edgeUpserts`, `edgeAccumQuery` gain `label` in the key and the
`edge_kind` column. `mergeEdgeAccum` recomputes weight per accumulator row and
is otherwise unchanged. `edgeUpserts` matches on `(node1, node2, label)` so a
relation edge and an `EMBEDDED` edge on the same pair never collide.

### 5.5 `createGraphSql`

One `CREATE UNDIRECTED GRAPH` over the full edge table, still aliasing
`(1 - weight) AS WEIGHT_VALUESPECIFIED` for solver cost. Both layers
participate. Direction from relation rows is not used by the undirected graph;
it is preserved in storage for query/readability only.

---

## 6. Data flow

```
docs → embed → extractLLM (entities + relations, one call)
   → disambiguate entities (mergeMentions / resolveIncremental, type-aware)
   → resolve relations to canonical nodes (buildRelationEdges)
   → computeEdges (EMBEDDED) + buildRelationEdges (relation)
   → emit: ddl, insertStatements, graphDdl, nodeInserts, membershipInserts,
           edgeInserts/edgeUpserts (both layers), createGraphSql
```

Local extraction provider: same flow minus the relation layer (LLM-only).

---

## 7. Ambiguity resolutions (settled here, not left to the implementer)

1. **People label token** — canonical label string is **`"People"`** across
   the five-type set. All `=== "Person"` comparisons are updated. The palette
   maps `People → --signal`.
2. **Edge label vs PK** — label is stored as `VARCHAR[]` (ARRAY convention).
   The plan's first edge-table task MUST verify Kinetica can PK on the array
   element; if not, add a scalar `edge_label CHAR(32)` column, key on
   `(node1, node2, edge_label)`, and keep the ARRAY `label` for display. The
   test suite asserts against whichever the plan picks.
3. **Relation typing enforcement** — NOT enforced at storage; advisory in the
   prompt only. Unusual-but-stated relations are kept.
4. **businessCore for Organization/Facility** — core-strategy strips the
   commercial `BIZ_SUFFIX`; if no such suffix is present the comparison falls
   back to `normalizeName` equality, so "State Department" merges with "the
   State Department" without needing an org-suffix list.
5. **Old edge type-pair label** — retired; not carried as a separate column.
6. **Local relations** — none; documented and logged.

---

## 8. Testing

Extend `scripts/test_graph.mjs` (all new pure fns inside CORE markers):

- `classifySpan` — one case per type (People, Business, Facility,
  Organization, Location) + a `null` (unlabeled) case + precedence
  (suffix beats facility keyword).
- `normLabel` / `normPredicate` — exact, synonym, and fallback cases.
- `mergeMentions` — per-type merge: two People variants merge; a Business and
  an Organization with the same core do NOT merge (different label); two
  Location surfaces with article difference merge.
- `blockKey` — correct key per strategy.
- `buildRelationEdges` — resolves subject/object to canonical nodes; drops an
  unresolved-endpoint relation (count correct); no self-loops; subject→object
  order; weight 1.0 / accumulators 1.0.
- Edge emitters (`edgeInserts`, `edgeUpserts`, `edgeAccumQuery`,
  `mergeEdgeAccum`) — new PK/`edge_kind` present; a relation edge and an
  `EMBEDDED` edge on the same pair coexist as two rows.

`scripts/test_serve.py` gains cases for the `/claude` and `/gemini` route
dispatch and their error normalization (the subprocess/urllib calls are
stubbed — no live LLM in the automated harness).

Manual (user, live Claude and Gemini): with `claude` logged in and
`gcloud auth login` done, extract the mixed sample under each provider;
confirm five distinct colored types render, relations appear as typed edges,
and Copy SQL emits both edge layers + a runnable `CREATE UNDIRECTED GRAPH`.

`sql/schema.sql` is updated in the same commit as the DDL change (per the
repo convention that `ddl()`/`graphDdl()` are the source of truth and the file
is documentation).

---

## 9. Files touched

- `index.html` — the app (types, palette, extraction with Claude/Gemini
  providers, disambiguation, edges, emitters, entities panel).
- `scripts/serve.py` — new `/claude` (subprocess) and `/gemini` (gcloud token
  + urllib) proxy routes; `--claude-bin`, `--gcp-project`, `--gcp-region`
  flags; Ollama chat route unchanged.
- `scripts/test_graph.mjs` — new/extended CORE tests.
- `scripts/test_serve.py` — `/claude` and `/gemini` dispatch + error tests.
- `sql/schema.sql` — reference DDL kept in sync.
- `SETUP.md` — Claude CLI login + `gcloud auth login` provider setup; retire
  the Ollama-extraction verification step (keep Ollama embeddings).
- `CLAUDE.md` — document the five-type ontology, two-layer edge model, the
  combined extraction call, and the Claude/Gemini providers.
