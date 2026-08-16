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
