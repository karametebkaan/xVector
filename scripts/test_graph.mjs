import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import assert from "node:assert/strict";

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

test("esc doubles single quotes and strips NULs", () => {
  assert.equal(core.esc("O'Brien"), "O''Brien");
  assert.equal(core.esc("a b"), "ab");
});

test("num formats to <=6 decimals", () => {
  assert.equal(core.num(0.1234567), "0.123457");
  assert.equal(core.num(1), "1");
});
