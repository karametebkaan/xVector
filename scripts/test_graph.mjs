import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import assert from "node:assert/strict";
import assertNonStrict from "node:assert";

export function loadCore(){
  const path = fileURLToPath(new URL("../index.html", import.meta.url));
  const html = readFileSync(path, "utf8");
  const segments = [...html.matchAll(/\/\* CORE:BEGIN \*\/([\s\S]*?)\/\* CORE:END \*\//g)].map(m => m[1]);
  if (!segments.length) throw new Error("no CORE segments found in index.html");
  const ctx = { Math, Map, Set, Array, JSON, String, Number, Date, isNaN, parseInt, parseFloat, Float64Array, RegExp, Object };
  vm.createContext(ctx);
  vm.runInContext(segments.join("\n"), ctx);
  return ctx;
}

const core = loadCore();

test("esc doubles single quotes, strips NUL, preserves spaces", () => {
  const NUL = String.fromCharCode(0);
  assert.equal(core.esc("O'Brien"), "O''Brien");
  assert.equal(core.esc("Kaan Karamete"), "Kaan Karamete");
  assert.equal(core.esc("a" + NUL + "b"), "ab");
});

test("num formats to <=6 decimals", () => {
  assert.equal(core.num(0.1234567), "0.123457");
  assert.equal(core.num(1), "1");
});

test("extractLocalMentions finds person and business with title/suffix", () => {
  const m = core.extractLocalMentions([{id:1, text:"Dr Kaan Karamete leads Acme Corp."}]);
  assertNonStrict.deepEqual(m, [
    {surface:"Kaan Karamete", label:"Person",   docId:1},
    {surface:"Acme Corp",     label:"Business", docId:1},
  ]);
});

test("extractLocalMentions keeps multiword orgs, strips leading article", () => {
  const m = core.extractLocalMentions([{id:2, text:"The University of Texas hired Jane Doe."}]);
  assertNonStrict.deepEqual(m, [
    {surface:"University of Texas", label:"Business", docId:2},
    {surface:"Jane Doe",           label:"Person",   docId:2},
  ]);
});

test("extractLocalMentions skips bare single tokens, keeps acronyms as business", () => {
  const m = core.extractLocalMentions([{id:3, text:"Chicago is big. IBM announced results."}]);
  assertNonStrict.deepEqual(m, [{surface:"IBM", label:"Business", docId:3}]);
});

test("extractLocalMentions accepts title-preceded single surname as person", () => {
  const m = core.extractLocalMentions([{id:4, text:"President Obama spoke."}]);
  assertNonStrict.deepEqual(m, [{surface:"Obama", label:"Person", docId:4}]);
});

test("normalizeName strips punctuation, case, possessive", () => {
  assert.equal(core.normalizeName("  O'Brien's "), "o'brien");
  assert.equal(core.normalizeName("Acme, Inc."), "acme inc");
});

test("givenCompatible handles initials and equality", () => {
  assert.equal(core.givenCompatible("Kaan","K"), true);
  assert.equal(core.givenCompatible("K","Kaan"), true);
  assert.equal(core.givenCompatible("Jane","John"), false);
});

test("mergeMentions none keeps variants distinct", () => {
  const e = core.mergeMentions([
    {surface:"Kaan Karamete",label:"Person",docId:1},
    {surface:"K Karamete",label:"Person",docId:2},
  ], "none");
  assert.equal(e.length, 2);
});

test("mergeMentions heuristic merges person variants", () => {
  const e = core.mergeMentions([
    {surface:"Kaan Karamete",label:"Person",docId:1},
    {surface:"K Karamete",label:"Person",docId:2},
    {surface:"Kaan Karamete",label:"Person",docId:2},
  ], "heuristic");
  assert.equal(e.length, 1);
  assert.equal(e[0].name, "Kaan Karamete");
  assertNonStrict.deepEqual(e[0].docIds, [1,2]);
  assertNonStrict.deepEqual(e[0].aliases, ["K Karamete","Kaan Karamete"]);
  assert.equal(e[0].count, 3);
});

test("mergeMentions heuristic merges business by core, not different people", () => {
  const biz = core.mergeMentions([
    {surface:"Acme Corp",label:"Business",docId:1},
    {surface:"Acme Inc",label:"Business",docId:2},
  ], "heuristic");
  assert.equal(biz.length, 1);
  const ppl = core.mergeMentions([
    {surface:"Jane Smith",label:"Person",docId:1},
    {surface:"John Smith",label:"Person",docId:2},
  ], "heuristic");
  assert.equal(ppl.length, 2);
});

test("cosineOf is the dot product", () => {
  assert.equal(core.cosineOf([1,0],[1,0]), 1);
  assert.equal(core.cosineOf([1,0],[0,1]), 0);
});

test("edgeType orders labels canonically", () => {
  assert.equal(core.edgeType("Person","Person"), "person-person");
  assert.equal(core.edgeType("Business","Business"), "business-business");
  assert.equal(core.edgeType("Business","Person"), "person-business");
  assert.equal(core.edgeType("Person","Business"), "person-business");
});

test("computeEdges: identical single-doc vectors give weight ~1", () => {
  const ents = [
    {name:"A",label:"Person",docIds:[1]},
    {name:"B",label:"Person",docIds:[2]},
  ];
  const dv = new Map([[1,[1,0]],[2,[1,0]]]);
  const e = core.computeEdges(ents, dv);
  assert.equal(e.length, 1);
  assert.ok(Math.abs(e[0].weight - 1) < 1e-3, "weight ~1");
  assert.equal(e[0].node1, "A"); assert.equal(e[0].node2, "B");
  assert.equal(e[0].type, "person-person");
});

test("computeEdges: orthogonal vectors give weight ~0.5", () => {
  const ents = [{name:"A",label:"Person",docIds:[1]},{name:"B",label:"Business",docIds:[2]}];
  const dv = new Map([[1,[1,0]],[2,[0,1]]]);
  const e = core.computeEdges(ents, dv);
  assert.ok(Math.abs(e[0].weight - 0.5) < 1e-3, "weight ~0.5");
  assert.equal(e[0].type, "person-business");
});

test("computeEdges: co-occurrence in same doc gives weight ~1", () => {
  const ents = [{name:"A",label:"Person",docIds:[1]},{name:"B",label:"Person",docIds:[1]}];
  const dv = new Map([[1,[0.6,0.8]]]);
  const e = core.computeEdges(ents, dv);
  assert.ok(Math.abs(e[0].weight - 1) < 1e-6);
});

test("filterEdges keeps weight >= threshold", () => {
  const edges = [{node1:"A",node2:"B",type:"x",weight:0.7},{node1:"A",node2:"C",type:"x",weight:0.4}];
  assert.equal(core.filterEdges(edges, 0.5).length, 1);
});

const OPTS = {prefix:"graph", stamp:"20260101", schema:"", createMode:"ifnot", batchSize:50, createdAt:"2026-01-01 00:00:00"};

test("arrayLit builds typed literals and escapes strings", () => {
  assert.equal(core.arrayLit(["Person"], "str"), "ARRAY['Person']");
  assert.equal(core.arrayLit([1,3,5], "int"), "ARRAY[1,3,5]");
  assert.equal(core.arrayLit(["O'Brien"], "str"), "ARRAY['O''Brien']");
});

test("graphDdl emits grammar-aligned node/edge tables", () => {
  const d = core.graphDdl(OPTS);
  assert.match(d.nodes, /CREATE TABLE IF NOT EXISTS graph_nodes_20260101/);
  assert.match(d.nodes, /node\s+CHAR\(64\) NOT NULL/);
  assert.match(d.nodes, /label\s+VARCHAR\[\] NOT NULL/);
  assert.match(d.nodes, /doc_ids\s+INT\[\] NOT NULL/);
  assert.match(d.edges, /node1\s+CHAR\(64\) NOT NULL/);
  assert.match(d.edges, /weight\s+FLOAT NOT NULL/);
  assert.equal(core.graphDdl({...OPTS, createMode:"skip"}), null);
});

test("nodeInserts and edgeInserts produce ARRAY literals and filtered rows", () => {
  const ents = [{name:"Kaan Karamete",label:"Person",docIds:[1,2],count:3,aliases:["K Karamete","Kaan Karamete"]}];
  const ni = core.nodeInserts(ents, OPTS);
  assert.match(ni[0], /INSERT INTO graph_nodes_20260101/);
  assert.match(ni[0], /ARRAY\['Person'\]/);
  assert.match(ni[0], /ARRAY\[1,2\]/);
  assert.match(ni[0], /'Kaan Karamete'/);

  const edges = [{node1:"A",node2:"B",type:"person-person",weight:0.73},{node1:"A",node2:"C",type:"person-person",weight:0.2}];
  const ei = core.edgeInserts(edges, OPTS, 0.5);
  assert.equal(ei.length, 1);              // one batch
  assert.match(ei[0], /ARRAY\['person-person'\]/);
  assert.match(ei[0], /0\.73/);
  assert.ok(!/'C'/.test(ei[0]));           // below-threshold edge dropped
});

test("graphScript includes commented CREATE GRAPH trailer", () => {
  const s = core.graphScript([{name:"A",label:"Person",docIds:[1],count:1,aliases:["A"]}], [], OPTS, 0.5);
  assert.match(s, /-- CREATE UNDIRECTED GRAPH entity_graph_20260101/);
  assert.match(s, /\(1 - weight\) AS WEIGHT_VALUESPECIFIED/);
});

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

test("blockKey: person -> surname, business -> suffix-stripped core", () => {
  assert.equal(core.blockKey("Kaan Karamete", "Person"), "karamete");
  assert.equal(core.blockKey("K Karamete", "Person"), "karamete");
  assert.equal(core.blockKey("Obama", "Person"), "obama");
  assert.equal(core.blockKey("Acme Corp", "Business"), "acme");
  assert.equal(core.blockKey("Acme Inc", "Business"), "acme");
  assert.equal(core.blockKey("University of Texas", "Business"), "university of texas");
});

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
