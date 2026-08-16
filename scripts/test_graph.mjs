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
