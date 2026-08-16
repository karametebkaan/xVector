# Incremental Append + Top-k kNN Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an **Append** write mode that inserts new document batches with globally unique `doc_id`s and maintains the entity graph incrementally via top-k kNN over Kinetica's vector index, plus an editable, runnable SQL box for graph creation.

**Architecture:** The browser orchestrates; Kinetica executes. New docs get ids from `MAX(doc_id)+1` and land in a primary-keyed, HNSW-indexed embeddings table. Each new doc's top-k neighbors are found by one index-backed query; entity edges are maintained as per-edge accumulators (`sum_wv`, `sum_w`, `weight = sum_wv/sum_w`) so a batch adds contributions instead of recomputing O(D²) pairs. Entity identity across batches is a blocking-key lookup (`block_key`) into the persistent node table, then the existing heuristic merge within the tiny block. All new pipeline logic that is DOM-free lives inside `/* CORE:BEGIN/END */` markers and is unit-tested by `scripts/test_graph.mjs`.

**Tech Stack:** Vanilla JS in a single `index.html` (no framework, no CDN, no build). Node stdlib test harness (`node --test`). Kinetica SQL over `POST /execute/sql`.

## Global Constraints

- Single file: all app code stays in `index.html`; no new dependencies, no CDN, no `localStorage`, no build step. `scripts/` may add stdlib-only helpers/tests.
- `DIM` stays `64` and is never a UI field.
- Every user-facing string goes through `log(msg, cls)` with `ok` / `err` / `warn` / `dim`.
- SQL string escaping is `esc()` (double single quotes, strip NUL, preserve spaces). Floats serialize via `num()` (6 decimals). Names clamp to 64 chars via `guardName()`. Typed array literals via `arrayLit(items, "int"|"str")`.
- Vector literals are bracketed string literals **without** a `VECTOR(...)` wrapper — match the working `btnSearch` pattern: `COSINE_DISTANCE(embedding, '[0.1,-0.2,...]')`.
- Kinetica SQL: no nested aggregates (use CTEs), double-quote identifiers only when needed, `DECIMAL` not `NUMERIC`, statements carry **no trailing semicolon** when sent to `/execute/sql` one at a time. Upsert is `INSERT INTO /* KI_HINT_UPDATE_ON_EXISTING_PK */ ...`.
- Pure functions destined for reuse/tests live inside `/* CORE:BEGIN */ … /* CORE:END */`. The harness evals CORE segments in a `node:vm` context whose globals are `Math, Map, Set, Array, JSON, String, Number, Date, isNaN, parseInt, parseFloat, Float64Array, RegExp, Object` — CORE functions must not depend on `DIM`, `document`, `fetch`, or any other global outside that list.
- `sql/schema.sql` is documentation kept in sync with the emitters **in the same commit**; the emitters in `index.html` are the single source of truth.
- Threshold (`#threshold`) filters graph edges at **display/read-back** time only. The persistent edge table stores every edge with complete accumulators so cross-batch weights stay exact.

---

## File Structure

- `index.html` — the whole app. All new CORE functions and UI wiring go here. Modified regions: the CORE blocks (lines ~633–865), `ddl()` (~877), the Graph panel HTML (~375–394), the store/graph wiring (~1218–1248).
- `scripts/test_graph.mjs` — stdlib test harness. New tests append to the existing file; no structural change.
- `sql/schema.sql` — reference DDL. Updated to v2 (embeddings PK+HNSW, nodes `block_key`+PK, new membership table, edges accumulators+PK).
- `CLAUDE.md` — architecture doc. New subsections for write modes, incremental accumulators, blocking key, membership table, k/β params, editable SQL box.
- `README.md` — user-facing quickstart. Append-mode paragraph.
- `samples/append-batch.txt` — **new** second batch that overlaps entities with `samples/`' existing text, for manual append testing.

Task order builds bottom-up: data-model emitters and pure functions first (Tasks 1–5, all unit-tested), then the browser orchestration and UI that compose them (Tasks 6–7, manually verified), then docs (Task 8).

---

## Deviations from the approved spec

Planning resolved four points where the concrete design differs from or refines the spec. Each keeps the spec's *intent* (all N-sensitive work stays server-side against the index) while simplifying what runs in the browser. Called out here so the reviewer sees them deliberately rather than as drift.

1. **Edge aggregation runs in the browser, not as a server-side `GROUP BY`.** The spec sketched a `WITH … JOIN <membership> … GROUP BY` query (its step 6). Instead, the browser reads back the kNN doc pairs, fetches membership only for the neighbor docs, and expands pairs → entity-edge deltas via the unit-tested `docPairContributions()`. The *scalability-critical* step — the per-new-doc top-k over the whole table — stays server-side and index-backed (`knnQuery`). The pair→entity expansion is bounded by `batch × k × mentions²`, tiny, and avoids Kinetica's no-nested-aggregate and `LEAST`/`GREATEST` pitfalls entirely. Fully covered by tests instead of live-only.

2. **Canonical node name is frozen at first creation (PK stability).** Because `node CHAR(64)` is the node PRIMARY KEY and edges/membership reference it, a later, longer variant must **not** rename the node (that would orphan rows and break upserts). `resolveIncremental()` keeps the existing node's name and folds new variants into `aliases`. This refines the spec's "longest variant becomes canonical," which still holds *within a batch's first creation*.

3. **No batch-tagged staging table.** The spec's step-6 correctness note mentioned staging new ids in a batch-tagged table for crash-idempotency. The plan instead relies on PRIMARY KEYs + `KI_HINT_UPDATE_ON_EXISTING_PK` upserts on the identity-keyed tables (nodes, edges, membership), which converge on re-run. The embeddings `INSERT` itself is **not** transactional: a crash mid-insert leaves partial rows, and re-clicking Append re-reads `MAX(doc_id)` and continues from the new max (orphaning nothing, but not de-duplicating the partial rows either). This is the same "no transaction wrapper" boundary CLAUDE.md already documents; a staging table can be added later if crash-idempotency becomes a hard requirement. **Surface to the user at plan review.**

4. **Missing-HNSW handling is create-on-append, not detect-then-offer.** The spec wanted the tool to detect a missing index before the kNN step and offer the `ALTER`. The plan creates the index during append when the existing **Add HNSW index** checkbox is set (`hnswIndexSql`), and `knnQuery` still returns correct results without an index (via full scan, just slower). Explicit pre-kNN index detection is deferred.

---

## Task 1: Embeddings table v2 — global ids (PRIMARY KEY + HNSW) and id assignment

**Files:**
- Modify: `index.html` — replace `ddl()` (~877–892); add `embDdl`, `nextIdBase`, `maxIdQuery` inside a new CORE block near the other SQL emitters (after line 865).
- Test: `scripts/test_graph.mjs` — append new tests.

**Interfaces:**
- Consumes: `DIM` (module const, 64) and DOM fields `#createMode`, `#normalize`, `fqName()` — used only by the DOM wrapper `ddl()`, never by the CORE functions.
- Produces:
  - `embDdl(opts)` where `opts = {table:string, createMode:"ifnot"|"replace"|"skip", dim:number, normalize:boolean}` → DDL string, or `null` when `createMode==="skip"`. Emits a `PRIMARY KEY (doc_id)`.
  - `nextIdBase(maxId)` → `number`. `maxId` may be `null`/`undefined`/string/number; returns `Math.floor(maxId)+1` when finite and > 0, else `1`.
  - `maxIdQuery(table)` → `"SELECT MAX(doc_id) AS max_id FROM <table>"`.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs`:

```javascript
test("nextIdBase: empty/null table starts at 1, else max+1", () => {
  assert.equal(core.nextIdBase(null), 1);
  assert.equal(core.nextIdBase(undefined), 1);
  assert.equal(core.nextIdBase(0), 1);
  assert.equal(core.nextIdBase(8), 9);
  assert.equal(core.nextIdBase("12"), 13);
});

test("maxIdQuery targets doc_id", () => {
  assert.equal(core.maxIdQuery("ki.vector_embeddings_20260101"),
    "SELECT MAX(doc_id) AS max_id FROM ki.vector_embeddings_20260101");
});

test("embDdl adds PRIMARY KEY on doc_id and honors NORMALIZE", () => {
  const base = {table:"vector_embeddings_20260101", createMode:"ifnot", dim:64, normalize:true};
  const d = core.embDdl(base);
  assert.match(d, /CREATE TABLE IF NOT EXISTS vector_embeddings_20260101/);
  assert.match(d, /doc_id INT NOT NULL/);
  assert.match(d, /embedding VECTOR\(64, NORMALIZE\) NOT NULL/);
  assert.match(d, /PRIMARY KEY \(doc_id\)/);
  assert.match(core.embDdl({...base, normalize:false}), /VECTOR\(64\) NOT NULL/);
  assert.match(core.embDdl({...base, createMode:"replace"}), /CREATE OR REPLACE TABLE/);
  assert.equal(core.embDdl({...base, createMode:"skip"}), null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.nextIdBase is not a function` (and the other new tests error the same way).

- [ ] **Step 3: Add the CORE functions and rewire `ddl()`**

Add a new CORE block immediately after the existing `/* CORE:END */` at line 865:

```javascript
/* CORE:BEGIN */
function embDdl(opts){
  if (opts.createMode === "skip") return null;
  const head = opts.createMode === "replace"
    ? "CREATE OR REPLACE TABLE "+opts.table
    : "CREATE TABLE IF NOT EXISTS "+opts.table;
  const norm = opts.normalize ? opts.dim+", NORMALIZE" : String(opts.dim);
  return head+"\n(\n"+
    "    doc_id INT NOT NULL,\n"+
    "    content VARCHAR NOT NULL,\n"+
    "    token_count INT,\n"+
    "    char_count INT,\n"+
    "    embed_source VARCHAR(64),\n"+
    "    created_at TIMESTAMP NOT NULL,\n"+
    "    embedding VECTOR("+norm+") NOT NULL,\n"+
    "    PRIMARY KEY (doc_id)\n"+
    ")";
}
function nextIdBase(maxId){
  const m = Number(maxId);
  return (Number.isFinite(m) && m > 0) ? Math.floor(m) + 1 : 1;
}
function maxIdQuery(table){ return "SELECT MAX(doc_id) AS max_id FROM "+table; }
/* CORE:END */
```

Replace the existing `ddl()` body (lines ~877–892) with a thin DOM wrapper:

```javascript
function ddl(){
  return embDdl({ table: fqName(), createMode: $("createMode").value, dim: DIM, normalize: $("normalize").checked });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (all prior tests still green; 3 new tests pass).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: embeddings table gets PRIMARY KEY(doc_id) + id-assignment helpers"
```

---

## Task 2: Blocking key (pure)

**Files:**
- Modify: `index.html` — add `blockKey` inside the mergeMentions CORE block (after `mergeMentions`, before its `/* CORE:END */` at line 751), so it can reuse `personName`/`businessCore`.
- Test: `scripts/test_graph.mjs`.

**Interfaces:**
- Consumes: `personName(surface)` → `{given:string[], sur:string}` and `businessCore(surface)` → lowercase suffix-stripped string (both already in CORE).
- Produces: `blockKey(name, label)` → `string`. Person → surname (lowercased, from `personName().sur`). Business → `businessCore(name)`. Never throws on empty input (returns `""`).

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs`:

```javascript
test("blockKey: person -> surname, business -> suffix-stripped core", () => {
  assert.equal(core.blockKey("Kaan Karamete", "Person"), "karamete");
  assert.equal(core.blockKey("K Karamete", "Person"), "karamete");
  assert.equal(core.blockKey("Obama", "Person"), "obama");
  assert.equal(core.blockKey("Acme Corp", "Business"), "acme");
  assert.equal(core.blockKey("Acme Inc", "Business"), "acme");
  assert.equal(core.blockKey("University of Texas", "Business"), "university of texas");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.blockKey is not a function`.

- [ ] **Step 3: Add `blockKey`**

Insert immediately before the `/* CORE:END */` that closes the mergeMentions block (line 751):

```javascript
function blockKey(name, label){
  if (label === "Business") return businessCore(name);
  return personName(name).sur;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: blockKey derives surname / business core for incremental disambiguation"
```

---

## Task 3: Incremental identity resolution (pure)

**Files:**
- Modify: `index.html` — inside the mergeMentions CORE block: extract a shared predicate `sameEntity`, refactor `mergeMentions` to call it, and add `unionSorted` + `resolveIncremental`.
- Test: `scripts/test_graph.mjs`.

**Interfaces:**
- Consumes: `personName`, `givenCompatible`, `businessCore`, `blockKey` (Task 2), `mergeMentions(mentions, "heuristic")`.
- Produces:
  - `sameEntity(label, surfaceA, surfaceB)` → `boolean`. Person: same surname and given-name compatibility across the shorter given list. Business: equal `businessCore`.
  - `unionSorted(a, b)` → array of the de-duplicated union of two arrays (order not guaranteed; caller sorts).
  - `resolveIncremental(mentions, existingNodes)` → `{ nodeUpserts: Entity[], membership: {node, docId, label}[] }`.
    - `mentions`: `{surface, label, docId}[]` from the new batch only.
    - `existingNodes`: `{name, label, docIds:int[], aliases:string[], count:number, block_key?:string}[]` read back from the persisted node table (empty on first append).
    - `Entity` = `{name, label, docIds:int[], count:number, aliases:string[], block_key:string}`.
    - **Canonical name is stable:** when a new batch entity matches an existing node (same label + `block_key` + `sameEntity`), the existing node's `name` is kept as the PK; the new variant is folded into `aliases`. Only a brand-new block/entity introduces a new `name`. `docIds` and `aliases` are the sorted union; `count` is the sum.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs`:

```javascript
test("sameEntity matches person variants and business cores, rejects different people", () => {
  assert.equal(core.sameEntity("Person", "Kaan Karamete", "K Karamete"), true);
  assert.equal(core.sameEntity("Person", "Jane Smith", "John Smith"), false);
  assert.equal(core.sameEntity("Business", "Acme Corp", "Acme Inc"), true);
});

test("resolveIncremental merges a new variant into an existing block, keeping the PK name", () => {
  const existing = [{name:"Kaan Karamete", label:"Person", docIds:[1], aliases:["Kaan Karamete"], count:1, block_key:"karamete"}];
  const r = core.resolveIncremental([{surface:"K Karamete", label:"Person", docId:5}], existing);
  assert.equal(r.nodeUpserts.length, 1);
  const e = r.nodeUpserts[0];
  assert.equal(e.name, "Kaan Karamete");              // PK name preserved
  assertNonStrict.deepEqual(e.docIds, [1,5]);
  assert.ok(e.aliases.includes("K Karamete"));
  assert.equal(e.count, 2);
  assert.equal(e.block_key, "karamete");
  assertNonStrict.deepEqual(r.membership, [{node:"Kaan Karamete", docId:5, label:"Person"}]);
});

test("resolveIncremental spawns a new node when nothing in the block matches", () => {
  const existing = [{name:"Jane Smith", label:"Person", docIds:[2], aliases:["Jane Smith"], count:1, block_key:"smith"}];
  const r = core.resolveIncremental([{surface:"John Smith", label:"Person", docId:7}], existing);
  assert.equal(r.nodeUpserts.length, 1);
  assert.equal(r.nodeUpserts[0].name, "John Smith");
  assert.equal(r.nodeUpserts[0].block_key, "smith");
  assertNonStrict.deepEqual(r.nodeUpserts[0].docIds, [7]);
});

test("resolveIncremental on an empty table creates fresh nodes with membership", () => {
  const r = core.resolveIncremental([{surface:"Acme Corp", label:"Business", docId:3}], []);
  assert.equal(r.nodeUpserts.length, 1);
  assert.equal(r.nodeUpserts[0].name, "Acme Corp");
  assert.equal(r.nodeUpserts[0].block_key, "acme");
  assertNonStrict.deepEqual(r.membership, [{node:"Acme Corp", docId:3, label:"Business"}]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.sameEntity is not a function`.

- [ ] **Step 3: Extract `sameEntity`, refactor `mergeMentions`, add `resolveIncremental`**

Add `sameEntity` just above `mergeMentions` (after `longest`, ~line 714):

```javascript
function sameEntity(label, surfaceA, surfaceB){
  if (label === "Person"){
    const a = personName(surfaceA), b = personName(surfaceB);
    if (a.sur !== b.sur) return false;
    const n = Math.min(a.given.length, b.given.length);
    for (let i=0;i<n;i++) if (!givenCompatible(a.given[i], b.given[i])) return false;
    return true;
  }
  return businessCore(surfaceA) === businessCore(surfaceB);
}
```

Refactor the two heuristic branches inside `mergeMentions` (lines ~730–742) to use it — behavior is identical, so the existing mergeMentions tests stay green:

```javascript
    if (m.label === "Person"){
      put(m, b => sameEntity("Person", b.items[0].surface, m.surface));
    } else {
      put(m, b => sameEntity("Business", b.items[0].surface, m.surface));
    }
```

Add `unionSorted` and `resolveIncremental` immediately after `blockKey` (before the block's `/* CORE:END */`):

```javascript
function unionSorted(a, b){ return [...new Set([...(a||[]), ...(b||[])])]; }

function resolveIncremental(mentions, existingNodes){
  const existing = (existingNodes||[]).map(n => ({
    name: n.name, label: n.label,
    docIds: (n.docIds||[]).slice(),
    aliases: (n.aliases||[]).slice(),
    count: n.count||0,
    block_key: n.block_key || blockKey(n.name, n.label)
  }));
  const keyOf = e => e.label+"\u0000"+e.block_key;
  const byKey = new Map();
  for (const n of existing){ const k = keyOf(n); if (!byKey.has(k)) byKey.set(k, []); byKey.get(k).push(n); }

  const fresh = mergeMentions(mentions, "heuristic");
  const nodeUpserts = [], membership = [];
  for (const e of fresh){
    const bk = blockKey(e.name, e.label);
    const k = e.label+"\u0000"+bk;
    const cands = byKey.get(k) || [];
    const match = cands.find(n => sameEntity(e.label, n.name, e.name));
    let canonical;
    if (match){
      match.docIds = unionSorted(match.docIds, e.docIds).sort((a,b)=>a-b);
      match.aliases = unionSorted(match.aliases, [e.name, ...e.aliases]).sort();
      match.count = match.count + e.count;
      canonical = match;                       // PK name unchanged
    } else {
      canonical = { name:e.name, label:e.label,
        docIds:e.docIds.slice().sort((a,b)=>a-b), count:e.count,
        aliases:unionSorted([e.name], e.aliases).sort(), block_key:bk };
      cands.push(canonical); byKey.set(k, cands);
    }
    nodeUpserts.push(canonical);
    for (const d of e.docIds) membership.push({ node: canonical.name, docId: d, label: e.label });
  }
  return { nodeUpserts, membership };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (existing mergeMentions tests unaffected; 4 new tests pass).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: resolveIncremental folds new mentions into blocked existing nodes"
```

---

## Task 4: Edge accumulator math + doc-pair contributions (pure)

**Files:**
- Modify: `index.html` — inside the computeEdges CORE block (lines ~753–793): make `computeEdges` also return `sum_wv`/`sum_w`; add `edgeDelta`, `mergeEdgeAccum`, `docPairContributions`.
- Test: `scripts/test_graph.mjs`.

**Interfaces:**
- Consumes: `edgeType(la, lb)` (already in CORE).
- Produces:
  - `edgeDelta(cos, eps?)` → `{w, v, wv}` with `eps` default `1e-6`, `w=1/(eps+(1-cos))`, `v=(1+cos)/2`, `wv=w*v`.
  - `mergeEdgeAccum(existing, delta)` → `{sum_wv, sum_w, weight}`. `existing` may be `null`/`undefined` (treated as zeros); `delta = {d_wv, d_w}`; `weight = sum_w===0 ? 0 : sum_wv/sum_w`.
  - `docPairContributions(pairs, membership)` → `{node1, node2, type, d_wv, d_w}[]`.
    - `pairs`: `{i, j, cos}[]`. `i===j` marks a **same-document self co-occurrence** (all entity pairs within doc `i`, `cos` ignored and treated as `1`). `i!==j` is a cross-doc neighbor pair; caller must already dedupe new-new pairs to a single orientation.
    - `membership`: `Map<docId, {node, label}[]>`.
    - Output edges are canonically ordered (`node1 < node2`), skip self-edges (`node===node`), and merge duplicate entity pairs by summing `d_wv`/`d_w`.
  - `computeEdges(...)` now returns edges carrying `{node1, node2, type, weight, sum_wv, sum_w}` (added fields; existing callers/tests that read `weight`/`node1`/`node2`/`type` are unaffected).

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs`:

```javascript
test("edgeDelta: cos=1 -> v=1 and huge w; cos=0 -> v=0.5, w~1", () => {
  const d1 = core.edgeDelta(1);
  assert.equal(d1.v, 1);
  assert.ok(d1.w > 1e5);
  assert.ok(Math.abs(d1.wv - d1.w) < 1e-6);
  const d0 = core.edgeDelta(0);
  assert.ok(Math.abs(d0.v - 0.5) < 1e-9);
  assert.ok(Math.abs(d0.w - 1) < 1e-3);
});

test("mergeEdgeAccum sums and recomputes weight as sum_wv/sum_w", () => {
  const a = core.mergeEdgeAccum(null, {d_wv:2, d_w:4});
  assert.equal(a.sum_wv, 2); assert.equal(a.sum_w, 4); assert.equal(a.weight, 0.5);
  const b = core.mergeEdgeAccum(a, {d_wv:2, d_w:4});
  assert.equal(b.sum_wv, 4); assert.equal(b.sum_w, 8); assert.equal(b.weight, 0.5);
  assert.equal(core.mergeEdgeAccum(null, {d_wv:0, d_w:0}).weight, 0);
});

test("docPairContributions: cross-doc pair expands to ordered entity edge", () => {
  const mem = new Map([[1,[{node:"Z",label:"Person"}]],[2,[{node:"A",label:"Business"}]]]);
  const out = core.docPairContributions([{i:1,j:2,cos:0.5}], mem);
  assert.equal(out.length, 1);
  assert.equal(out[0].node1, "A"); assert.equal(out[0].node2, "Z");
  assert.equal(out[0].type, "person-business");
  assert.ok(out[0].d_w > 0 && out[0].d_wv > 0);
});

test("docPairContributions: same-doc self pair uses cos=1 co-occurrence", () => {
  const mem = new Map([[1,[{node:"A",label:"Person"},{node:"B",label:"Person"}]]]);
  const out = core.docPairContributions([{i:1,j:1,cos:0}], mem);
  assert.equal(out.length, 1);
  assert.equal(out[0].node1, "A"); assert.equal(out[0].node2, "B");
  assert.equal(out[0].type, "person-person");
  assert.ok(Math.abs(out[0].d_wv - out[0].d_w) < 1e-6);   // v=1 => wv==w
});

test("docPairContributions: same entity in both docs makes no self-edge; dupes merge", () => {
  const mem = new Map([[1,[{node:"A",label:"Person"}]],[2,[{node:"A",label:"Person"}]]]);
  assert.equal(core.docPairContributions([{i:1,j:2,cos:1}], mem).length, 0);
  const mem2 = new Map([[1,[{node:"A",label:"Person"}]],[2,[{node:"B",label:"Person"}]],[3,[{node:"B",label:"Person"}]]]);
  const out = core.docPairContributions([{i:1,j:2,cos:0.5},{i:1,j:3,cos:0.5}], mem2);
  assert.equal(out.length, 1);                            // A-B merged across two neighbor docs
  assert.ok(out[0].d_w > core.edgeDelta(0.5).w * 1.5);   // both contributions summed
});

test("computeEdges now also returns sum_wv and sum_w", () => {
  const ents = [{name:"A",label:"Person",docIds:[1]},{name:"B",label:"Person",docIds:[2]}];
  const dv = new Map([[1,[1,0]],[2,[1,0]]]);
  const e = core.computeEdges(ents, dv);
  assert.ok(typeof e[0].sum_wv === "number" && typeof e[0].sum_w === "number");
  assert.ok(Math.abs(e[0].sum_wv / e[0].sum_w - e[0].weight) < 1e-12);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.edgeDelta is not a function`.

- [ ] **Step 3: Add the functions and extend `computeEdges`**

In the computeEdges CORE block, add before `computeEdges`:

```javascript
function edgeDelta(cos, eps){
  eps = (eps === undefined) ? 1e-6 : eps;
  const d = 1 - cos;
  const w = 1 / (eps + d);
  const v = (1 + cos) / 2;
  return { w, v, wv: w*v };
}
function mergeEdgeAccum(existing, delta){
  const sum_wv = ((existing && existing.sum_wv) || 0) + delta.d_wv;
  const sum_w  = ((existing && existing.sum_w)  || 0) + delta.d_w;
  return { sum_wv, sum_w, weight: sum_w === 0 ? 0 : sum_wv / sum_w };
}
function docPairContributions(pairs, membership){
  const acc = new Map();
  const add = (na, la, nb, lb, del) => {
    if (na === nb) return;
    const flip = nb < na;
    const n1 = flip ? nb : na, n2 = flip ? na : nb;
    const l1 = flip ? lb : la, l2 = flip ? la : lb;
    const key = n1+"\u0000"+n2;
    let cur = acc.get(key);
    if (!cur){ cur = {node1:n1, node2:n2, type: edgeType(l1,l2), d_wv:0, d_w:0}; acc.set(key,cur); }
    cur.d_wv += del.wv; cur.d_w += del.w;
  };
  for (const p of pairs){
    const A = membership.get(p.i) || [];
    if (p.i === p.j){
      const del = edgeDelta(1);
      for (let x=0;x<A.length;x++) for (let y=x+1;y<A.length;y++)
        add(A[x].node, A[x].label, A[y].node, A[y].label, del);
    } else {
      const B = membership.get(p.j) || [];
      const del = edgeDelta(p.cos);
      for (const a of A) for (const b of B) add(a.node, a.label, b.node, b.label, del);
    }
  }
  return [...acc.values()];
}
```

In `computeEdges`, change the edge push (line ~786) to carry the accumulators:

```javascript
      edges.push({ node1: n1, node2: n2, type: edgeType(A.label, B.label), weight, sum_wv: sumWV, sum_w: sumW });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: edge accumulator math + doc-pair contribution expansion"
```

---

## Task 5: Append SQL emitters (pure strings)

**Files:**
- Modify: `index.html` — the graph-emitters CORE block (lines ~795–865): extend `graphDdl`, `nodeInserts`, `edgeInserts`; add `membershipDdl`, `membershipInserts`, `edgeUpserts`, `knnQuery`, `inList`, `membershipQuery`, `edgeAccumQuery`, `nodeBlockQuery`, `createGraphSql`, `hnswIndexSql`.
- Test: `scripts/test_graph.mjs`.

**Interfaces:**
- Consumes: `graphTableName(prefix, kind, stamp, schema)`, `arrayLit`, `esc`, `guardName`, `num`, `blockKey` (Task 2).
- Produces (all take an `opts` shaped like the existing `graphOpts()` output `{prefix, stamp, schema, createMode, batchSize, createdAt}` unless noted):
  - `graphDdl(opts)` → `{nodes, edges}` (or `null` for `createMode:"skip"`). Nodes gain `block_key CHAR(64)` and `PRIMARY KEY (node)`; edges gain `sum_wv DOUBLE`, `sum_w DOUBLE` and `PRIMARY KEY (node1, node2)`.
  - `membershipDdl(opts)` → membership-table DDL string (or `null` for skip).
  - `nodeInserts(entities, opts)` → statements; row includes `block_key` (falls back to `blockKey(name,label)` if absent). When `opts.upsert` is truthy the statement is prefixed `INSERT INTO /* KI_HINT_UPDATE_ON_EXISTING_PK */`.
  - `edgeInserts(edges, opts, threshold)` → **threshold-filtered** statements (legacy Recreate/Copy path) with the new `sum_wv`/`sum_w` columns.
  - `edgeUpserts(edges, opts)` → **all** edges, upsert-hinted, `sum_wv`/`sum_w` columns (Append path).
  - `membershipInserts(rows, opts)` where `rows={node, docId, label}[]` → statements.
  - `knnQuery(table, vecLit, k, beta, excludeId)` → top-k SQL. `vecLit` is a bracketed literal from `vecLiteral()` (no quotes/no `VECTOR()` wrapper).
  - `inList(values, kind)` → `"(v1,v2,...)"` (`kind:"int"|"str"`, str values escaped+quoted); `"(NULL)"` when empty.
  - `membershipQuery(table, docIds)` → membership rows for those docs.
  - `edgeAccumQuery(table, names)` → existing accumulators for edges touching any of `names`.
  - `nodeBlockQuery(table, keys)` → existing nodes whose `block_key` is in `keys`.
  - `createGraphSql(opts)` → runnable (uncommented) `CREATE UNDIRECTED GRAPH ...`.
  - `hnswIndexSql(table)` → `"ALTER TABLE <table> ADD HNSW INDEX (embedding)"`.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs` (reuses the existing `OPTS` constant):

```javascript
test("graphDdl v2 adds block_key, edge accumulators, and primary keys", () => {
  const d = core.graphDdl(OPTS);
  assert.match(d.nodes, /block_key\s+CHAR\(64\)/);
  assert.match(d.nodes, /PRIMARY KEY \(node\)/);
  assert.match(d.edges, /sum_wv\s+DOUBLE/);
  assert.match(d.edges, /sum_w\s+DOUBLE/);
  assert.match(d.edges, /PRIMARY KEY \(node1, node2\)/);
});

test("membershipDdl emits node/doc_id/label bridge table", () => {
  const d = core.membershipDdl(OPTS);
  assert.match(d, /CREATE TABLE IF NOT EXISTS graph_membership_20260101/);
  assert.match(d, /node\s+CHAR\(64\) NOT NULL/);
  assert.match(d, /doc_id INT NOT NULL/);
  assert.match(d, /label\s+VARCHAR\[\] NOT NULL/);
  assert.equal(core.membershipDdl({...OPTS, createMode:"skip"}), null);
});

test("nodeInserts includes block_key and supports upsert hint", () => {
  const ents = [{name:"Kaan Karamete",label:"Person",docIds:[1,2],count:3,aliases:["K Karamete","Kaan Karamete"],block_key:"karamete"}];
  const plain = core.nodeInserts(ents, OPTS);
  assert.match(plain[0], /INSERT INTO graph_nodes_20260101/);
  assert.match(plain[0], /'karamete'/);
  const up = core.nodeInserts(ents, {...OPTS, upsert:true});
  assert.match(up[0], /INSERT INTO \/\* KI_HINT_UPDATE_ON_EXISTING_PK \*\/ graph_nodes_20260101/);
});

test("edgeUpserts stores all edges with accumulators and the upsert hint", () => {
  const edges = [
    {node1:"A",node2:"B",type:"person-person",weight:0.7,sum_wv:7,sum_w:10},
    {node1:"A",node2:"C",type:"person-person",weight:0.2,sum_wv:2,sum_w:10},
  ];
  const s = core.edgeUpserts(edges, OPTS);
  assert.match(s[0], /INSERT INTO \/\* KI_HINT_UPDATE_ON_EXISTING_PK \*\/ graph_edges_20260101/);
  assert.match(s[0], /'A', 'B'/);
  assert.match(s[0], /'A', 'C'/);        // no threshold filter — both kept
  assert.match(s[0], /0\.7,\s*7,\s*10/);
});

test("membershipInserts builds typed rows", () => {
  const s = core.membershipInserts([{node:"Kaan Karamete",docId:5,label:"Person"}], OPTS);
  assert.match(s[0], /INSERT INTO graph_membership_20260101/);
  assert.match(s[0], /'Kaan Karamete', 5, ARRAY\['Person'\]/);
});

test("knnQuery builds an index-backed top-k with a distance cutoff", () => {
  const q = core.knnQuery("ki.emb", "[0.1,-0.2]", 20, 0.35, 7);
  assert.match(q, /SELECT TOP 20 doc_id/);
  assert.match(q, /\(1 - COSINE_DISTANCE\(embedding, '\[0.1,-0.2\]'\)\) AS cos/);
  assert.match(q, /WHERE doc_id <> 7 AND COSINE_DISTANCE\(embedding, '\[0.1,-0.2\]'\) <= 0\.35/);
  assert.match(q, /ORDER BY COSINE_DISTANCE\(embedding, '\[0.1,-0.2\]'\) ASC/);
});

test("inList quotes/escapes strings and passes ints; empty -> (NULL)", () => {
  assert.equal(core.inList([1,2,3], "int"), "(1,2,3)");
  assert.equal(core.inList(["O'Brien","Acme"], "str"), "('O''Brien','Acme')");
  assert.equal(core.inList([], "str"), "(NULL)");
});

test("read-back queries target the right tables and filters", () => {
  assert.equal(core.membershipQuery("m", [1,2]), "SELECT node, doc_id, label FROM m WHERE doc_id IN (1,2)");
  assert.equal(core.edgeAccumQuery("e", ["A","B"]),
    "SELECT node1, node2, sum_wv, sum_w FROM e WHERE node1 IN ('A','B') OR node2 IN ('A','B')");
  assert.equal(core.nodeBlockQuery("n", ["karamete","acme"]),
    "SELECT node, label, doc_ids, doc_count, aliases, block_key FROM n WHERE block_key IN ('karamete','acme')");
});

test("createGraphSql is runnable (uncommented) and aliases WEIGHT_VALUESPECIFIED", () => {
  const s = core.createGraphSql(OPTS);
  assert.match(s, /^CREATE UNDIRECTED GRAPH entity_graph_20260101/);
  assert.ok(!/^--/.test(s));
  assert.match(s, /\(1 - weight\) AS WEIGHT_VALUESPECIFIED FROM graph_edges_20260101/);
});

test("hnswIndexSql targets the embedding column", () => {
  assert.equal(core.hnswIndexSql("ki.emb"), "ALTER TABLE ki.emb ADD HNSW INDEX (embedding)");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — first on the `graphDdl v2` assertions (`block_key` not present), then missing-function errors.

- [ ] **Step 3: Extend and add the emitters**

Replace `graphDdl` (lines ~806–823) with:

```javascript
function graphDdl(opts){
  if (opts.createMode === "skip") return null;
  const head = k => (opts.createMode === "replace" ? "CREATE OR REPLACE TABLE " : "CREATE TABLE IF NOT EXISTS ")+graphTableName(opts.prefix,k,opts.stamp,opts.schema);
  const nodes = head("nodes")+"\n(\n"+
    "    node       CHAR(64) NOT NULL,\n"+
    "    label      VARCHAR[] NOT NULL,\n"+
    "    doc_ids    INT[] NOT NULL,\n"+
    "    doc_count  INT,\n"+
    "    aliases    VARCHAR[],\n"+
    "    block_key  CHAR(64),\n"+
    "    created_at TIMESTAMP NOT NULL,\n"+
    "    PRIMARY KEY (node)\n)";
  const edges = head("edges")+"\n(\n"+
    "    node1  CHAR(64) NOT NULL,\n"+
    "    node2  CHAR(64) NOT NULL,\n"+
    "    label  VARCHAR[] NOT NULL,\n"+
    "    weight FLOAT NOT NULL,\n"+
    "    sum_wv DOUBLE,\n"+
    "    sum_w  DOUBLE,\n"+
    "    created_at TIMESTAMP NOT NULL,\n"+
    "    PRIMARY KEY (node1, node2)\n)";
  return { nodes, edges };
}
function membershipDdl(opts){
  if (opts.createMode === "skip") return null;
  const head = (opts.createMode === "replace" ? "CREATE OR REPLACE TABLE " : "CREATE TABLE IF NOT EXISTS ")+graphTableName(opts.prefix,"membership",opts.stamp,opts.schema);
  return head+"\n(\n"+
    "    node   CHAR(64) NOT NULL,\n"+
    "    doc_id INT NOT NULL,\n"+
    "    label  VARCHAR[] NOT NULL\n)";
}
```

Replace `nodeInserts` (lines ~824–836) with the block_key + upsert-aware version:

```javascript
function nodeInserts(entities, opts){
  const t = graphTableName(opts.prefix,"nodes",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const head = "INSERT INTO "+(opts.upsert ? "/* KI_HINT_UPDATE_ON_EXISTING_PK */ " : "")+t;
  const cols = "(node, label, doc_ids, doc_count, aliases, block_key, created_at)";
  const out = [];
  for (let i=0;i<entities.length;i+=size){
    const rows = entities.slice(i,i+size).map(e =>
      "    ('"+esc(guardName(e.name))+"', "+arrayLit([e.label],"str")+", "+arrayLit(e.docIds,"int")+", "+
      (parseInt(e.count,10)||e.docIds.length)+", "+arrayLit(e.aliases,"str")+", '"+
      esc(guardName(e.block_key || blockKey(e.name, e.label)))+"', '"+opts.createdAt+"')");
    out.push(head+"\n"+cols+"\nVALUES\n"+rows.join(",\n"));
  }
  return out;
}
```

Replace `edgeInserts` (lines ~837–849) with the accumulator-column version (still threshold-filtered for the legacy path):

```javascript
function edgeInserts(edges, opts, threshold){
  const t = graphTableName(opts.prefix,"edges",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const cols = "(node1, node2, label, weight, sum_wv, sum_w, created_at)";
  const kept = edges.filter(e => e.weight >= threshold);
  const out = [];
  for (let i=0;i<kept.length;i+=size){
    const rows = kept.slice(i,i+size).map(e =>
      "    ('"+esc(guardName(e.node1))+"', '"+esc(guardName(e.node2))+"', "+arrayLit([e.type],"str")+", "+
      num(e.weight)+", "+num(e.sum_wv!=null?e.sum_wv:e.weight)+", "+num(e.sum_w!=null?e.sum_w:1)+", '"+opts.createdAt+"')");
    out.push("INSERT INTO "+t+"\n"+cols+"\nVALUES\n"+rows.join(",\n"));
  }
  return out;
}
```

Add the remaining new emitters after `edgeInserts`:

```javascript
function edgeUpserts(edges, opts){
  const t = graphTableName(opts.prefix,"edges",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const cols = "(node1, node2, label, weight, sum_wv, sum_w, created_at)";
  const out = [];
  for (let i=0;i<edges.length;i+=size){
    const rows = edges.slice(i,i+size).map(e =>
      "    ('"+esc(guardName(e.node1))+"', '"+esc(guardName(e.node2))+"', "+arrayLit([e.type],"str")+", "+
      num(e.weight)+", "+num(e.sum_wv)+", "+num(e.sum_w)+", '"+opts.createdAt+"')");
    out.push("INSERT INTO /* KI_HINT_UPDATE_ON_EXISTING_PK */ "+t+"\n"+cols+"\nVALUES\n"+rows.join(",\n"));
  }
  return out;
}
function membershipInserts(rows, opts){
  const t = graphTableName(opts.prefix,"membership",opts.stamp,opts.schema);
  const size = Math.max(1, opts.batchSize||50);
  const cols = "(node, doc_id, label)";
  const out = [];
  for (let i=0;i<rows.length;i+=size){
    const vals = rows.slice(i,i+size).map(r =>
      "    ('"+esc(guardName(r.node))+"', "+(r.docId|0)+", "+arrayLit([r.label],"str")+")");
    out.push("INSERT INTO "+t+"\n"+cols+"\nVALUES\n"+vals.join(",\n"));
  }
  return out;
}
function knnQuery(table, vecLit, k, beta, excludeId){
  const dist = "COSINE_DISTANCE(embedding, '"+vecLit+"')";
  return "SELECT TOP "+(k|0)+" doc_id, (1 - "+dist+") AS cos\n"+
         "FROM "+table+"\n"+
         "WHERE doc_id <> "+(excludeId|0)+" AND "+dist+" <= "+num(beta)+"\n"+
         "ORDER BY "+dist+" ASC";
}
function inList(values, kind){
  if (!values || !values.length) return "(NULL)";
  return "("+values.map(v => kind==="int" ? (v|0) : "'"+esc(String(v))+"'").join(",")+")";
}
function membershipQuery(table, docIds){
  return "SELECT node, doc_id, label FROM "+table+" WHERE doc_id IN "+inList(docIds,"int");
}
function edgeAccumQuery(table, names){
  const l = inList(names,"str");
  return "SELECT node1, node2, sum_wv, sum_w FROM "+table+" WHERE node1 IN "+l+" OR node2 IN "+l;
}
function nodeBlockQuery(table, keys){
  return "SELECT node, label, doc_ids, doc_count, aliases, block_key FROM "+table+" WHERE block_key IN "+inList(keys,"str");
}
function createGraphSql(opts){
  const nt = graphTableName(opts.prefix,"nodes",opts.stamp,opts.schema);
  const et = graphTableName(opts.prefix,"edges",opts.stamp,opts.schema);
  return "CREATE UNDIRECTED GRAPH entity_graph_"+opts.stamp+" (\n"+
         "  NODES => INPUT_TABLES((SELECT * FROM "+nt+")),\n"+
         "  EDGES => INPUT_TABLES((SELECT node1, node2, label,\n"+
         "                         (1 - weight) AS WEIGHT_VALUESPECIFIED FROM "+et+")))";
}
function hnswIndexSql(table){ return "ALTER TABLE "+table+" ADD HNSW INDEX (embedding)"; }
```

Update the existing `graphScript` trailer (lines ~857–862) so Copy SQL now emits the runnable statement as a commented reference plus the real one is available via the box; keep the commented trailer but source it from `createGraphSql` to avoid drift:

```javascript
  sql += "\n-- Runnable graph creation (also available in the editable SQL box):\n-- "+
         createGraphSql(opts).replace(/\n/g, "\n-- ")+"\n";
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS. The pre-existing `graphScript includes commented CREATE GRAPH trailer` test still matches (`-- CREATE UNDIRECTED GRAPH entity_graph_20260101` and `(1 - weight) AS WEIGHT_VALUESPECIFIED` both appear); if the exact commented prefix differs, update that test's regex to `/CREATE UNDIRECTED GRAPH entity_graph_20260101/` (drop the leading `-- `).

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: append SQL emitters — membership, upserts, kNN, read-backs, runnable CREATE GRAPH"
```

---

## Task 6: UI — write mode, k/β params, and the Append pipeline

**Files:**
- Modify: `index.html` — Graph panel HTML (~375–394): add write-mode select, `k`/`β` inputs, and rename the action button dynamically. Wiring (~1218–1248): `graphOpts()` gains no change; add the Append orchestration; keep `btnBuildGraph`/Recreate as-is.

**Interfaces:**
- Consumes: everything from Tasks 1–5 (`maxIdQuery`, `nextIdBase`, `ddl()`, `insertStatements()`, `hnswIndexSql`, `extractLocalMentions`/`extractLLM`, `resolveIncremental`, `nodeBlockQuery`, `nodeInserts` (upsert), `membershipInserts`, `graphDdl`, `membershipDdl`, `knnQuery`, `vecLiteral`, `membershipQuery`, `docPairContributions`, `edgeAccumQuery`, `mergeEdgeAccum`, `edgeUpserts`, `filterEdges`), plus `ksql`, `recordsToRows`, `log`.
- Produces: DOM controls `#writeMode` (`recreate`|`append`), `#knnK`, `#knnBeta`; module state reuse of `DOCS`, `ENTITIES`, `EDGES`. A new `async function appendBatch()` orchestrator and a helper `graphSqlText(mode)` (used by Task 7).

> **Testing note:** This task is browser/live-Kinetica orchestration — the same headless-untestable boundary the spec calls out. Verification is (a) `node --test scripts/test_graph.mjs` stays green (no CORE regressions), and (b) the manual checklist in Step 4. All N-sensitive/pure logic it calls is already unit-tested in Tasks 1–5.

- [ ] **Step 1: Add the Graph-panel controls**

Replace the Graph panel's first `.row` and `.btns` (lines ~377–391) with:

```html
      <div class="row">
        <div class="field" style="max-width:160px">
          <label for="gPrefix">Table prefix</label>
          <input type="text" id="gPrefix" value="graph">
        </div>
        <div class="field" style="max-width:200px">
          <label for="writeMode">Write mode</label>
          <select id="writeMode">
            <option value="recreate">Recreate (drop + rebuild)</option>
            <option value="append">Append (incremental)</option>
          </select>
        </div>
      </div>
      <div class="row">
        <div class="field" style="max-width:110px">
          <label for="knnK">kNN k</label>
          <input type="number" id="knnK" value="20" min="1" max="1000">
        </div>
        <div class="field" style="max-width:140px">
          <label for="knnBeta">β max cos-dist</label>
          <input type="number" id="knnBeta" value="0.35" min="0" max="2" step="0.01">
        </div>
        <div class="field">
          <label for="threshold">Min weight — <span id="thVal">0.50</span></label>
          <input type="range" id="threshold" min="0" max="1" step="0.01" value="0.5">
        </div>
      </div>
      <div class="btns">
        <button class="go" id="btnBuildGraph">Build graph</button>
        <button id="btnAppendBatch">Append batch to Kinetica</button>
        <button class="ghost" id="btnGraphSql">Copy graph SQL</button>
      </div>
```

- [ ] **Step 2: Add the Append orchestrator and wiring**

Replace the `btnStoreGraph` handler (lines ~1234–1248) with the `appendBatch` orchestrator and its button wiring. `btnBuildGraph`/`btnGraphSql`/`threshold` handlers stay as they are (Recreate preview path):

```javascript
async function readRows(sql){ const r = await ksql(sql); return recordsToRows(r.records); }

async function appendBatch(){
  if (!DOCS.length){ log("Generate embeddings first.", "warn"); return; }
  const btn = $("btnAppendBatch"); btn.disabled = true;
  const bar = $("gbar"); bar.style.display = "block"; const fill = bar.querySelector("span");
  const opts = graphOpts(); const emb = fqName();
  const k = Math.max(1, parseInt($("knnK").value,10)||20);
  const beta = Math.max(0, parseFloat($("knnBeta").value)||0.35);
  const th = parseFloat($("threshold").value);
  const step = (n,tot) => fill.style.width = Math.round(100*n/tot)+"%";
  try {
    // 1. global ids
    const mx = await readRows(maxIdQuery(emb));                     // may throw if table absent
    const base = nextIdBase(mx && mx.rows.length ? mx.rows[0][0] : null);
    DOCS.forEach((d,i) => d.id = base + i);
    log("Assigned doc_ids "+base+".."+(base+DOCS.length-1)+".", "ok");
    // 2. ensure table + insert embeddings (append)
    const d = ddl(); if (d) await ksql(d);
    const ins = insertStatements();
    for (let i=0;i<ins.length;i++){ await ksql(ins[i]); step(i+1, ins.length+6); }
    if ($("hnsw").checked) await ksql(hnswIndexSql(emb));
    log("Inserted "+DOCS.length+" documents into "+emb+".", "ok");
    // 3. extract mentions from the new docs
    const docs = DOCS.map(x => ({id:x.id, text:x.text}));
    const mentions = $("extractProvider").value === "llm" ? await extractLLM(docs) : extractLocalMentions(docs);
    // 4. incremental identity resolution against the persisted node table
    const gd = graphDdl(opts), md = membershipDdl(opts);
    if (gd){ await ksql(gd.nodes); await ksql(gd.edges); } if (md) await ksql(md);
    const keys = [...new Set(mentions.map(m => blockKey(m.surface, m.label)))];
    let existingNodes = [];
    if (keys.length){
      const nb = await readRows(nodeBlockQuery(graphTableName(opts.prefix,"nodes",opts.stamp,opts.schema), keys));
      if (nb) existingNodes = nb.rows.map(r => ({ name:r[0], label:(Array.isArray(r[1])?r[1][0]:r[1]),
        docIds:(Array.isArray(r[2])?r[2]:[]), count:r[3]||0, aliases:(Array.isArray(r[4])?r[4]:[]), block_key:r[5] }));
    }
    const res = resolveIncremental(mentions, existingNodes);
    ENTITIES = res.nodeUpserts;
    for (const s of nodeInserts(res.nodeUpserts, {...opts, upsert:true})) await ksql(s);
    for (const s of membershipInserts(res.membership, opts)) await ksql(s);
    log("Resolved "+res.nodeUpserts.length+" entities; wrote "+res.membership.length+" membership rows.", "ok");
    // 5. kNN candidate pairs (index-backed, per new doc)
    const newIds = new Set(DOCS.map(d => d.id));
    const pairs = []; const neighborDocs = new Set();
    const seen = new Set();                                          // dedupe new-new to one orientation
    for (const doc of DOCS){
      const rows = await readRows(knnQuery(emb, vecLiteral(doc.vec), k, beta, doc.id));
      if (rows) for (const [j, cos] of rows.rows){
        if (newIds.has(j)){ const a=Math.min(doc.id,j), b=Math.max(doc.id,j); const key=a+"-"+b;
          if (seen.has(key)) continue; seen.add(key); pairs.push({i:a, j:b, cos}); }
        else { pairs.push({i:doc.id, j, cos}); neighborDocs.add(j); }
      }
      pairs.push({i:doc.id, j:doc.id, cos:1});                       // same-doc co-occurrence
    }
    step(ins.length+3, ins.length+6);
    // 6. membership for old neighbor docs + new docs -> entity-pair deltas
    const membership = new Map();
    for (const m of res.membership){ if (!membership.has(m.docId)) membership.set(m.docId, []); membership.get(m.docId).push({node:m.node, label:m.label}); }
    if (neighborDocs.size){
      const mm = await readRows(membershipQuery(graphTableName(opts.prefix,"membership",opts.stamp,opts.schema), [...neighborDocs]));
      if (mm) for (const [node, docId, label] of mm.rows){ const id=docId|0;
        if (!membership.has(id)) membership.set(id, []); membership.get(id).push({node, label:(Array.isArray(label)?label[0]:label)}); }
    }
    const deltas = docPairContributions(pairs, membership);
    // 7. merge with existing accumulators and upsert edges
    const names = [...new Set(deltas.flatMap(e => [e.node1, e.node2]))];
    const accum = new Map();
    if (names.length){
      const ea = await readRows(edgeAccumQuery(graphTableName(opts.prefix,"edges",opts.stamp,opts.schema), names));
      if (ea) for (const [n1,n2,swv,sw] of ea.rows) accum.set(n1+"\u0000"+n2, {sum_wv:swv||0, sum_w:sw||0});
    }
    EDGES = deltas.map(e => { const m = mergeEdgeAccum(accum.get(e.node1+"\u0000"+e.node2), {d_wv:e.d_wv, d_w:e.d_w});
      return {node1:e.node1, node2:e.node2, type:e.type, weight:m.weight, sum_wv:m.sum_wv, sum_w:m.sum_w}; });
    EDGES.sort((a,b) => b.weight - a.weight);
    for (const s of edgeUpserts(EDGES, opts)) await ksql(s);
    step(ins.length+6, ins.length+6);
    renderGraph();
    log("Updated "+EDGES.length+" edges ("+filterEdges(EDGES,th).length+" at/above "+th.toFixed(2)+"). Run CREATE GRAPH from the SQL box to build the solver graph.", "ok");
    LAST_TABLE = emb;
  } catch(e){
    log("Append failed: "+e.message, "err");
    log("Batch is safe to retry (upserts converge). Or use Copy graph SQL / the editable box in Workbench.", "dim");
  } finally { btn.disabled = false; setTimeout(()=>{ bar.style.display="none"; fill.style.width="0"; }, 1200); }
}

$("btnAppendBatch").addEventListener("click", appendBatch);
$("writeMode").addEventListener("change", () => {
  const append = $("writeMode").value === "append";
  $("btnAppendBatch").style.display = append ? "" : "none";
  $("btnBuildGraph").textContent = append ? "Preview graph (local)" : "Build graph";
});
$("writeMode").dispatchEvent(new Event("change"));
```

- [ ] **Step 3: Run the CORE test suite (regression gate)**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS — this task adds no CORE functions, so all tests from Tasks 1–5 stay green.

- [ ] **Step 4: Manual verification (browser + local Kinetica)**

Start `python3 scripts/serve.py`, open `http://localhost:8000`, set Instance URL `/kinetica`. Confirm:
- With **Write mode = Append**: load sample, Generate, then **Append batch to Kinetica**. Console logs id range `1..N`, inserts, resolution counts, edge count.
- Load `samples/append-batch.txt` (Task 8) as a **second** batch, Generate, Append again. Console shows the id range continuing (`N+1..`), "merged into existing" counts > 0, and edges updating rather than duplicating.
- `SELECT doc_id, COUNT(*) FROM vector_embeddings_<stamp> GROUP BY doc_id HAVING COUNT(*) > 1` returns **zero rows** (the original duplicate-id bug is gone).
- k and β inputs visibly affect neighbor counts (lower β → fewer edges).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: Append write mode with global ids, kNN k/beta params, incremental graph pipeline"
```

---

## Task 7: Editable, runnable SQL box + Run

**Files:**
- Modify: `index.html` — Graph panel HTML (after `#graphOut`, ~393): add the textarea + Run button. Wiring: add `graphSqlText()`, populate the box from Build/Append, and a `btnRunGraphSql` handler.

**Interfaces:**
- Consumes: `graphDdl`, `membershipDdl`, `nodeInserts`, `membershipInserts`, `edgeInserts`/`edgeUpserts`, `createGraphSql`, `graphOpts`, `ENTITIES`, `EDGES`, `ksql`, `log`.
- Produces: DOM `#graphSqlBox` (textarea), `#btnRunGraphSql`; `function graphSqlText(mode)` → the full statement script (statements joined by `;\n\n`, ending with the runnable `createGraphSql`), and a splitter that runs the box statement-by-statement.

> **Testing note:** Browser path (untestable headlessly). Gate is the CORE suite staying green plus the Step 4 manual check. `graphSqlText` only concatenates already-tested emitters.

- [ ] **Step 1: Add the box + Run button**

Insert after the `#graphOut` div (line ~393):

```html
      <div class="field" style="margin-top:12px">
        <label for="graphSqlBox">Graph SQL — editable, runs top to bottom</label>
        <textarea id="graphSqlBox" rows="10" spellcheck="false" placeholder="Build or Append to populate; edit freely, then Run."></textarea>
      </div>
      <div class="btns"><button class="go" id="btnRunGraphSql">Run SQL in Kinetica</button></div>
```

- [ ] **Step 2: Populate the box and wire Run**

Add near the graph wiring:

```javascript
function graphSqlText(mode){
  const opts = graphOpts(); const th = parseFloat($("threshold").value);
  const parts = [];
  const gd = graphDdl(opts), md = membershipDdl(opts);
  if (gd){ parts.push(gd.nodes, gd.edges); } if (md) parts.push(md);
  if (mode === "append"){
    parts.push(...nodeInserts(ENTITIES, {...opts, upsert:true}));
    parts.push(...edgeUpserts(EDGES, opts));
  } else {
    parts.push(...nodeInserts(ENTITIES, opts));
    parts.push(...edgeInserts(EDGES, opts, th));
  }
  parts.push(createGraphSql(opts));
  return parts.join(";\n\n")+";\n";
}
function populateGraphBox(){
  if (!ENTITIES.length) return;
  $("graphSqlBox").value = graphSqlText($("writeMode").value);
}
$("btnRunGraphSql").addEventListener("click", async () => {
  const text = $("graphSqlBox").value.trim();
  if (!text){ log("Nothing in the SQL box to run.", "warn"); return; }
  const stmts = text.split(/;\s*(?:\n|$)/).map(s => s.trim()).filter(Boolean);
  const bar = $("gbar"); bar.style.display = "block"; const fill = bar.querySelector("span");
  const btn = $("btnRunGraphSql"); btn.disabled = true;
  try {
    for (let i=0;i<stmts.length;i++){
      await ksql(stmts[i]);
      fill.style.width = Math.round(100*(i+1)/stmts.length)+"%";
      log("Ran statement "+(i+1)+"/"+stmts.length+".", "dim");
    }
    log("Ran "+stmts.length+" statements from the SQL box.", "ok");
  } catch(e){
    log("SQL box run failed: "+e.message, "err");
    log("Statements before the failure were applied; fix and re-run (upserts converge).", "dim");
  } finally { btn.disabled = false; setTimeout(()=>{ bar.style.display="none"; fill.style.width="0"; }, 1200); }
});
```

Populate the box from both graph actions. In the `btnBuildGraph` handler (after `renderGraph();`) add `populateGraphBox();`. In `appendBatch()` (after `renderGraph();`) add `populateGraphBox();`.

- [ ] **Step 3: Run the CORE test suite (regression gate)**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS.

- [ ] **Step 4: Manual verification**

- Build graph (Recreate mode) → box fills with node/edge INSERTs and a runnable `CREATE UNDIRECTED GRAPH ...` at the end. **Run SQL in Kinetica** executes each and logs per-statement progress.
- Edit a value in the box (e.g., change the graph name) → Run reflects the edit.
- Append mode → box shows upsert-hinted statements + membership + `CREATE GRAPH`.
- A paragraph/name containing `;` still splits correctly (statements are separated by `;\n\n`; a mid-value `;` not followed by a newline is not a split point).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: editable, runnable graph SQL box supersedes silent store"
```

---

## Task 8: Docs, schema, and append sample

**Files:**
- Modify: `sql/schema.sql`, `CLAUDE.md`, `README.md`.
- Create: `samples/append-batch.txt`.

**Interfaces:** none (documentation + fixture).

- [ ] **Step 1: Update `sql/schema.sql` to v2**

Rewrite the DDL to match the emitters exactly: embeddings table with `PRIMARY KEY (doc_id)` and an `ALTER TABLE ... ADD HNSW INDEX (embedding)`; `graph_nodes_<stamp>` with `block_key CHAR(64)` and `PRIMARY KEY (node)`; the new `graph_membership_<stamp> (node CHAR(64), doc_id INT, label VARCHAR[])`; `graph_edges_<stamp>` with `sum_wv DOUBLE`, `sum_w DOUBLE`, `PRIMARY KEY (node1, node2)`; and the runnable `CREATE UNDIRECTED GRAPH` example aliasing `(1 - weight) AS WEIGHT_VALUESPECIFIED`. Add a one-line header comment: `-- Kept in sync with the emitters in index.html (embDdl/graphDdl/membershipDdl/…). Do not edit independently.`

- [ ] **Step 2: Update `CLAUDE.md`**

Add to the pipeline description: a **Write mode** (Recreate vs Append) note; that `doc_id` is now a PRIMARY KEY assigned from `MAX(doc_id)+1` via `nextIdBase()`, fixing cross-run id collisions; the **incremental accumulators** (`sum_wv`/`sum_w`, `weight = sum_wv/sum_w`, `mergeEdgeAccum`); the **blocking key** (`block_key`, `blockKey()`, `resolveIncremental()`); the **membership table** and why the aggregation joins on it instead of `ARRAY_CONTAINS` at scale; the **kNN step** (`knnQuery`, per-new-doc top-k, k/β UI params) and that only new docs are search origins (the scalability win); the **canonical-name-is-stable** rule in Append (PK never renamed; new variants become aliases); and the **editable SQL box** superseding the old silent store. Note the new CORE functions are covered by `scripts/test_graph.mjs`.

- [ ] **Step 3: Update `README.md`**

Add an Append paragraph to **Use**: choose Write mode = Append to add a new batch with globally unique ids and update the graph incrementally; tune `k`/`β`; review/edit the generated statements in the Graph SQL box and Run them (including `CREATE GRAPH`). Mention `samples/append-batch.txt` as the second batch for trying append.

- [ ] **Step 4: Create `samples/append-batch.txt`**

A second batch that overlaps entities with the existing in-app sample (Kaan Karamete / Acme / University of Texas) so append-time merging is observable, plus one fresh entity:

```
Kaan Karamete presented the graph analytics roadmap at the Acme Corporation summit, where Acme announced a new vector-search product line for enterprise customers.
The University of Texas expanded its partnership with Acme Inc, funding three more fellowships and a shared lab that K Karamete will co-supervise next year.
Meanwhile, Globex Systems entered the market with a competing embedding service, hiring several researchers away from the university.
```

- [ ] **Step 5: Verify and commit**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (docs-only change; suite still green).

```bash
git add sql/schema.sql CLAUDE.md README.md samples/append-batch.txt
git commit -m "docs: document incremental append + kNN; v2 schema; append sample"
```

---

## Notes for the executor

- **Kinetica read-back shapes vary by version.** The orchestrator (Task 6) uses `recordsToRows()` and treats `VARCHAR[]` columns as arrays; if a target version returns array columns as JSON strings, add a defensive `JSON.parse` in the row-mapping (mirror the existing defensive parsing in `ksql`). Flag this as a `DONE_WITH_CONCERNS` observation rather than blocking.
- **The kNN loop issues one query per new doc.** That is intentional and index-bound (bounded by batch size, not table size). Do not "optimize" it into a cross join — that would defeat the HNSW index and reintroduce the O(D²) scan.
- **Threshold is display-only now.** Never filter what `edgeUpserts` stores; the accumulators must stay complete for future batches.
- Live HNSW kNN accuracy, actual upsert semantics, and `INT[]`/`ARRAY_CONTAINS` acceptance are human/live-verified (same boundary as the first feature) — the CORE suite covers everything DOM-free.
