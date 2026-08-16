# Native Ollama Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ollama a first-class provider for both embeddings and extraction, with live model discovery, reached through a same-origin `/ollama` proxy route.

**Architecture:** The browser orchestrates; `scripts/serve.py` gains a small route table so it proxies both `/kinetica` and `/ollama` (POST and, newly, GET). `index.html` adds an Ollama provider option, native `/api/embed` + `/api/chat` calls, and `/api/tags` model discovery. Pure seams — the proxy's path→upstream resolver and the embedding-response picker — are unit-tested; DOM/network glue is verified manually against a local Ollama, matching the project's existing testing convention.

**Tech Stack:** Vanilla JS in a single `index.html` (no framework, no CDN, no build). Python 3 stdlib for `serve.py` + `unittest`. Node stdlib `--test` harness for CORE functions. Ollama REST API.

**Spec:** `docs/superpowers/specs/2026-08-16-ollama-provider-design.md`

## Global Constraints

- Single file: all app code stays in `index.html`; no dependencies, no CDN, no `localStorage`, no build step. `scripts/` may add stdlib-only helpers/tests.
- `DIM` stays `64` and is never a UI field.
- Every user-facing string goes through `log(msg, cls)` with `ok` / `err` / `warn` / `dim`.
- SQL escaping stays `esc()`; floats serialize via `num()` at 6 decimals.
- Pure, DOM-free logic lives inside `/* CORE:BEGIN … CORE:END */` markers so `scripts/test_graph.mjs` can extract and eval it.
- Colors/type live in `:root` custom properties; indigo `--signal` = Person, amber `--warm` = Business.
- Reduction of >64-dim vectors: `nomic-embed-text` is not Matryoshka, so the Ollama provider defaults to **projection**; the `#reduce` "ask" option (a `dimensions` request param) is unsupported by native `/api/embed` and is treated as projection.

---

### Task 1: serve.py route table, `resolve_upstream()`, `--ollama`, and GET proxy

**Files:**
- Modify: `scripts/serve.py`
- Test: `scripts/test_serve.py` (create)

**Interfaces:**
- Produces: `resolve_upstream(path: str, routes: dict[str,str]) -> str | None` — the rewritten upstream URL for the longest-matching route prefix, or `None` when no prefix matches. Module global `ROUTES: dict[str,str]` set in `main()`.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_serve.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402

ROUTES = {
    "/kinetica": "http://localhost:9191",
    "/ollama": "http://localhost:11434",
}


class ResolveUpstream(unittest.TestCase):
    def test_kinetica_sql(self):
        self.assertEqual(
            serve.resolve_upstream("/kinetica/execute/sql", ROUTES),
            "http://localhost:9191/execute/sql",
        )

    def test_ollama_tags(self):
        self.assertEqual(
            serve.resolve_upstream("/ollama/api/tags", ROUTES),
            "http://localhost:11434/api/tags",
        )

    def test_exact_prefix(self):
        self.assertEqual(
            serve.resolve_upstream("/ollama", ROUTES),
            "http://localhost:11434",
        )

    def test_trailing_slash_target_not_doubled(self):
        routes = {"/ollama": "http://localhost:11434/"}
        self.assertEqual(
            serve.resolve_upstream("/ollama/api/embed", routes),
            "http://localhost:11434/api/embed",
        )

    def test_static_path_is_none(self):
        self.assertIsNone(serve.resolve_upstream("/index.html", ROUTES))

    def test_prefix_lookalike_is_none(self):
        # "/kineticax" must NOT match the "/kinetica" route
        self.assertIsNone(serve.resolve_upstream("/kineticax/y", ROUTES))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/test_serve.py`
Expected: FAIL with `AttributeError: module 'serve' has no attribute 'resolve_upstream'`

- [ ] **Step 3: Add `resolve_upstream()` to `scripts/serve.py`**

Add near the top of the module (after the imports, before `class Handler`):

```python
def resolve_upstream(path, routes):
    """Rewrite an incoming path to its upstream URL for the longest matching
    route prefix. Returns None when no prefix matches (caller serves it
    locally or 404s)."""
    best = None
    for prefix, target in routes.items():
        if path == prefix or path.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, target)
    if best is None:
        return None
    prefix, target = best
    return target.rstrip("/") + path[len(prefix):]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/test_serve.py`
Expected: PASS (6 tests)

- [ ] **Step 5: Wire the route table, GET proxy, and `--ollama` flag**

Replace the module-level `PREFIX`/`TARGET` constants with:

```python
ROUTES = {}  # populated in main(): {prefix: target_base}
```

Replace the `Handler` class body's `do_POST` with a shared proxy helper plus GET/POST dispatch:

```python
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _proxy(self, method, url, body):
        req = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        auth = self.headers.get("Authorization")
        if auth:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                payload, status = res.read(), res.status
        except urllib.error.HTTPError as e:
            payload, status = e.read(), e.code
        except Exception as e:
            msg = ('{"status":"ERROR","message":"proxy could not reach %s: %s"}'
                   % (url, str(e).replace('"', "'")))
            payload, status = msg.encode(), 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        url = resolve_upstream(self.path, ROUTES)
        if url is None:
            self.send_error(404, "No proxy route for %s" % self.path)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self._proxy("POST", url, body)

    def do_GET(self):
        url = resolve_upstream(self.path, ROUTES)
        if url is None:
            return super().do_GET()  # serve static files
        self._proxy("GET", url, None)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
```

Update `main()` to add the flag and build `ROUTES`:

```python
def main():
    global ROUTES
    p = argparse.ArgumentParser(description="Serve xVector with Kinetica + Ollama proxies.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--kinetica", default=os.environ.get("KINETICA_URL", "http://localhost:9191"),
                   help="Kinetica instance URL")
    p.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                   help="Ollama base URL")
    args = p.parse_args()
    ROUTES = {"/kinetica": args.kinetica, "/ollama": args.ollama}

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("xVector   http://%s:%d" % (args.host, args.port))
    print("Kinetica  %s  →  proxied at /kinetica" % args.kinetica)
    print("Ollama    %s  →  proxied at /ollama" % args.ollama)
    print("Set the app's Instance URL to /kinetica\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
```

- [ ] **Step 6: Re-run the unit test and a manual smoke check**

Run: `python3 scripts/test_serve.py`
Expected: PASS (6 tests)

Manual (only if Ollama is running): `python3 scripts/serve.py &` then
`curl -s http://localhost:8000/ollama/api/tags` returns the model list JSON;
`curl -s http://localhost:8000/index.html` still returns the page. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add scripts/serve.py scripts/test_serve.py
git commit -m "feat: generalize serve.py proxy with route table + /ollama GET/POST"
```

---

### Task 2: `pickEmbeddings()` CORE helper + Node tests

**Files:**
- Modify: `index.html` (inside the `/* CORE:BEGIN */ … /* CORE:END */` block at lines 655–658)
- Test: `scripts/test_graph.mjs`

**Interfaces:**
- Produces: `pickEmbeddings(json, expected)` — returns an array of number-arrays extracted from any of the three known response shapes; throws on unknown shape, count mismatch, or a non-array row. `expected` is optional (skip the count check when `undefined`).

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_graph.mjs` (follow the existing `test(...)` style; `core` is the object the harness builds from the CORE block):

```js
test("pickEmbeddings reads Ollama native shape", () => {
  assert.deepEqual(core.pickEmbeddings({embeddings:[[1,2],[3,4]]}, 2), [[1,2],[3,4]]);
});
test("pickEmbeddings reads OpenAI-compatible shape", () => {
  assert.deepEqual(core.pickEmbeddings({data:[{embedding:[1,2]}]}, 1), [[1,2]]);
});
test("pickEmbeddings reads a bare array", () => {
  assert.deepEqual(core.pickEmbeddings([[1,2]], 1), [[1,2]]);
});
test("pickEmbeddings throws on count mismatch", () => {
  assert.throws(() => core.pickEmbeddings({embeddings:[[1,2]]}, 2), /got 1/);
});
test("pickEmbeddings throws on unknown shape", () => {
  assert.throws(() => core.pickEmbeddings({nope:true}), /No embeddings array/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test scripts/test_graph.mjs`
Expected: FAIL — `core.pickEmbeddings is not a function`

- [ ] **Step 3: Add `pickEmbeddings()` inside the CORE block**

In `index.html`, extend the CORE block that currently holds `esc`/`num`:

```js
/* CORE:BEGIN */
function esc(s){ return String(s).replace(/'/g, "''").replace(/\u0000/g,""); }
function num(x){ return String(Number(x.toFixed(6))); }
function pickEmbeddings(json, expected){
  let rows;
  if (json && Array.isArray(json.embeddings)) rows = json.embeddings;               // Ollama native
  else if (json && Array.isArray(json.data)) rows = json.data.map(r => r.embedding || r); // OpenAI-compatible
  else if (Array.isArray(json)) rows = json;                                         // bare array
  else throw new Error("No embeddings array in the response");
  if (expected !== undefined && rows.length !== expected)
    throw new Error("Asked for "+expected+" vectors, got "+rows.length);
  for (const r of rows) if (!Array.isArray(r)) throw new Error("An embedding row is not an array");
  return rows;
}
/* CORE:END */
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (existing 45 + 5 new = 50)

- [ ] **Step 5: Commit**

```bash
git add index.html scripts/test_graph.mjs
git commit -m "feat: add pickEmbeddings CORE helper for embedding response shapes"
```

---

### Task 3: Ollama embedding provider — UI option, options panel, `embedOllama()`

**Files:**
- Modify: `index.html` (provider `<select>` ~245; new `#ollamaOpts` panel after `#apiOpts` ~283; `reduceVec` ~552; `embedOllama` new after `embedRemote` ~608; provider change handler ~1370; embed dispatch ~1237 and ~1302; `source` label ~1079 and ~1361)

**Interfaces:**
- Consumes: `pickEmbeddings(json, expected)` (Task 2), existing `reduceVec`, `tokenize`, `l2norm`, `log`.
- Produces: `embedOllama(texts) -> Promise<Array<{vec:Float64Array, tokens:number, srcDim:number}>>`; DOM ids `#ollamaUrl`, `#ollamaEmbedModel`.

- [ ] **Step 1: Add the provider option and options panel**

In the Provider `<select>` (`#provider`), add a third option:

```html
          <option value="ollama">Ollama — native (local models)</option>
```

Immediately after the `<div id="apiOpts" …>…</div>` block, add:

```html
      <div id="ollamaOpts" style="display:none">
        <div class="field">
          <label for="ollamaUrl">Ollama base URL</label>
          <input type="text" id="ollamaUrl" value="/ollama" />
        </div>
        <div class="row">
          <div class="field">
            <label for="ollamaEmbedModel">Embedding model</label>
            <select id="ollamaEmbedModel"></select>
          </div>
          <div class="field" style="max-width:120px;align-self:end">
            <button type="button" class="ghost" id="btnOllamaRefresh">Refresh</button>
          </div>
        </div>
        <p class="hint">Models come from <code>/api/tags</code>, which doesn't label embed vs chat — pick an embedding model like <code>nomic-embed-text</code>. Output over 64 dims is projected down (the "ask for 64" option doesn't apply to Ollama).</p>
      </div>
```

- [ ] **Step 2: Let `reduceVec` accept a mode override**

Change the first line of `reduceVec` (line 552) from:

```js
function reduceVec(arr){
  const mode = $("reduce").value;
```

to:

```js
function reduceVec(arr, modeOverride){
  const mode = modeOverride || $("reduce").value;
```

(Existing callers pass no second argument, so behavior is unchanged.)

- [ ] **Step 3: Add `embedOllama()`**

After `embedRemote` (ends ~608), add:

```js
async function embedOllama(texts){
  const base  = ($("ollamaUrl").value.trim().replace(/\/+$/,"")) || "/ollama";
  const model = $("ollamaEmbedModel").value.trim();
  if (!model) throw new Error("Pick an Ollama embedding model (Refresh to load the list)");
  const size  = Math.max(1, parseInt($("apiBatch").value,10) || 16);
  const rmode = $("reduce").value === "ask" ? "project" : $("reduce").value;
  const out = [];
  for (let i=0;i<texts.length;i+=size){
    const chunk = texts.slice(i, i+size);
    log("embedding "+(i+1)+"–"+(i+chunk.length)+" of "+texts.length+" via "+model);
    const res = await fetch(base+"/api/embed", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({model, input: chunk, truncate:true})});
    const txt = await res.text();
    if (!res.ok) throw new Error("Ollama /api/embed returned "+res.status+": "+txt.slice(0,300));
    let json; try { json = JSON.parse(txt); } catch(e){ throw new Error("Ollama sent back something that isn't JSON: "+txt.slice(0,200)); }
    const rows = pickEmbeddings(json, chunk.length);
    for (let k=0;k<rows.length;k++)
      out.push({ vec: reduceVec(rows[k], rmode), tokens: tokenize(chunk[k]).length, srcDim: rows[k].length });
  }
  return out;
}
```

- [ ] **Step 4: Show/hide the panel on provider change**

Replace the `#provider` change handler (~1370) with a three-way toggle:

```js
$("provider").addEventListener("change", () => {
  const v = $("provider").value;
  $("apiOpts").style.display    = v === "api"    ? "block" : "none";
  $("ollamaOpts").style.display = v === "ollama" ? "block" : "none";
  $("localOpts").style.display  = v === "local"  ? "block" : "none";
});
```

- [ ] **Step 5: Route the embed + query calls to `embedOllama`**

At the embed dispatch (~1237), change:

```js
const res = $("provider").value === "local" ? embedLocal(texts) : await embedRemote(texts);
```

to:

```js
const pv = $("provider").value;
const res = pv === "local" ? embedLocal(texts) : pv === "ollama" ? await embedOllama(texts) : await embedRemote(texts);
```

At the similarity-query embed (~1302), change:

```js
const r = $("provider").value === "local" ? embedLocal([q]) : await embedRemote([q]);
```

to:

```js
const pv = $("provider").value;
const r = pv === "local" ? embedLocal([q]) : pv === "ollama" ? await embedOllama([q]) : await embedRemote([q]);
```

For the `source` label (~1079 and ~1361), change the `"local"` ternary so Ollama reports its model. At ~1079:

```js
  const src = $("provider").value === "local" ? "local-hash-64"
            : ($("provider").value === "ollama" ? $("ollamaEmbedModel").value.trim() : $("apiModel").value.trim() || "api").slice(0,64);
```

At ~1361:

```js
    source: $("provider").value === "local" ? "local-hash-64"
          : ($("provider").value === "ollama" ? $("ollamaEmbedModel").value.trim() : $("apiModel").value.trim()),
```

- [ ] **Step 6: Verify CORE tests still pass, then manually verify embedding**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (50).

Manual (requires `ollama serve` + `ollama pull nomic-embed-text`, and `python3 scripts/serve.py --ollama http://localhost:11434`): open the app, choose **Ollama** provider, click **Refresh** (dropdown fills — Task 4 delivers Refresh; before Task 4, temporarily type a known model into the select via devtools or proceed after Task 4), paste `samples/kinetica-notes.txt`, Generate embeddings → 64-d strips render, console shows "via nomic-embed-text".

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat: Ollama embedding provider (embedOllama, UI panel, dispatch)"
```

---

### Task 4: Model discovery — `/api/tags`, dropdown population, health check

**Files:**
- Modify: `index.html` (new `ollamaModels`, `fillModelSelect`, `refreshOllamaModels` after `embedOllama`; button + provider-change wiring)

**Interfaces:**
- Consumes: `#ollamaUrl`, `#ollamaEmbedModel`, `#ollamaChatModel` (the chat select is added in Task 5; guard for its absence), `log`.
- Produces: `ollamaModels() -> Promise<string[]>`, `fillModelSelect(sel, names)`, `refreshOllamaModels()`.

- [ ] **Step 1: Add discovery + fill helpers**

After `embedOllama`, add:

```js
async function ollamaModels(){
  const base = ($("ollamaUrl").value.trim().replace(/\/+$/,"")) || "/ollama";
  const res = await fetch(base+"/api/tags");
  if (!res.ok) throw new Error("/api/tags returned "+res.status);
  const j = JSON.parse(await res.text());
  return (j.models||[]).map(m => m.name).filter(Boolean);
}
function fillModelSelect(sel, names){
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = "";
  for (const n of names){ const o = document.createElement("option"); o.value = n; o.textContent = n; sel.appendChild(o); }
  if (names.includes(cur)) sel.value = cur;
}
async function refreshOllamaModels(){
  try {
    const names = await ollamaModels();
    fillModelSelect($("ollamaEmbedModel"), names);
    fillModelSelect($("ollamaChatModel"), names);
    log("Ollama: "+names.length+" model(s) available", names.length ? "ok" : "warn");
  } catch(e){
    log("Can't reach Ollama at "+(($("ollamaUrl").value.trim())||"/ollama")+" — is `ollama serve` running and did you start serve.py with --ollama? ("+e.message+")", "err");
  }
}
```

- [ ] **Step 2: Wire the Refresh button and auto-refresh on provider switch**

Near the other event bindings, add:

```js
$("btnOllamaRefresh").addEventListener("click", refreshOllamaModels);
```

In the `#provider` change handler from Task 3 Step 4, add an auto-load when switching to Ollama (append inside the handler):

```js
  if (v === "ollama" && !$("ollamaEmbedModel").options.length) refreshOllamaModels();
```

- [ ] **Step 3: Manual verification**

With Ollama running and proxied: select **Ollama** provider → the embed-model dropdown auto-populates and the console logs "Ollama: N model(s) available". Stop Ollama, click **Refresh** → an actionable `err` line appears. No unit test (network/DOM).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: Ollama model discovery via /api/tags with health check"
```

---

### Task 5: Ollama extraction — chat transport in `extractLLM()`

**Files:**
- Modify: `index.html` (extraction `<select>` ~213; new `#ollamaChatOpts` panel after `#llmOpts` ~229; `extractLLM` ~1146; extractProvider change handler ~1378; extract dispatch ~1389 and ~1488)

**Interfaces:**
- Consumes: `#ollamaUrl`, `#ollamaChatModel`, `mergeMentions`, `log`.
- Produces: extraction via `/ollama/api/chat` using the **existing 2-type (Person/Business) prompt**; `extractLLM(docs)` return shape unchanged (`[{surface,label,docId}]`).

- [ ] **Step 1: Add the extraction option and chat-model panel**

In the Extraction `<select>` (`#extractProvider`), add:

```html
            <option value="ollama">Ollama — chat</option>
```

After the `<div id="llmOpts" …>…</div>` block, add:

```html
      <div id="ollamaChatOpts" style="display:none">
        <div class="field">
          <label for="ollamaChatModel">Ollama chat model</label>
          <select id="ollamaChatModel"></select>
        </div>
        <p class="hint">Uses the Ollama base URL above. Refresh the model list from the Ollama embedding provider panel.</p>
      </div>
```

- [ ] **Step 2: Refactor `extractLLM` to share the prompt and branch on transport**

Replace the body of `extractLLM` (1146–~1168) with:

```js
async function extractLLM(docs){
  const sys = "Extract entities labeled Person or Business (organizations, facilities, institutions). "+
    "Return ONLY JSON: {\"entities\":[{\"name\":\"...\",\"label\":\"Person|Business\",\"doc_ids\":[int]}]}.";
  const usr = docs.map(d => "["+d.id+"] "+d.text).join("\n\n");
  const messages = [{role:"system",content:sys},{role:"user",content:usr}];
  let content;
  if ($("extractProvider").value === "ollama"){
    const base  = ($("ollamaUrl").value.trim().replace(/\/+$/,"")) || "/ollama";
    const model = $("ollamaChatModel").value.trim();
    if (!model) throw new Error("Pick an Ollama chat model (Refresh to load the list)");
    const res = await fetch(base+"/api/chat", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({model, messages, stream:false, format:"json"})});
    const text = await res.text();
    if (!res.ok) throw new Error("Ollama /api/chat returned "+res.status+": "+text.slice(0,300));
    let j; try { j = JSON.parse(text); } catch(e){ throw new Error("Ollama chat sent back non-JSON: "+text.slice(0,200)); }
    content = j.message && j.message.content;
  } else {
    const url = $("llmUrl").value.trim(); const model = $("llmModel").value.trim();
    if (!url) throw new Error("Set the chat endpoint URL");
    const headers = {"Content-Type":"application/json"};
    const key = $("apiKey").value.trim(); if (key) headers["Authorization"] = "Bearer "+key;
    const res = await fetch(url, {method:"POST", headers, body: JSON.stringify({
      model, messages, temperature:0, response_format:{type:"json_object"} })});
    const text = await res.text();
    let j; try { j = JSON.parse(text); } catch(e){ throw new Error("LLM response was not parseable JSON: "+text.slice(0,200)); }
    content = (j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || text;
  }
  let obj; try { obj = JSON.parse(content); } catch(e){ throw new Error("LLM response was not parseable JSON: "+String(content).slice(0,200)); }
  const list = (obj.entities || []);
  const mentions = [];
  for (const e of list){ const lbl = e.label === "Business" ? "Business" : "Person";
    for (const id of (e.doc_ids||[])) mentions.push({surface:String(e.name), label:lbl, docId:id}); }
  return mentions;
}
```

- [ ] **Step 3: Update the extraction visibility handler and dispatch**

Replace the `#extractProvider` change handler (~1378):

```js
$("extractProvider").addEventListener("change", () => {
  const v = $("extractProvider").value;
  $("llmOpts").style.display        = v === "llm"    ? "block" : "none";
  $("ollamaChatOpts").style.display = v === "ollama" ? "block" : "none";
});
```

At both extract dispatch sites (~1389 and ~1488), change:

```js
const mentions = $("extractProvider").value === "llm" ? await extractLLM(docs) : extractLocalMentions(docs);
```

to:

```js
const mentions = $("extractProvider").value === "local" ? extractLocalMentions(docs) : await extractLLM(docs);
```

- [ ] **Step 4: Verify CORE tests + manual extraction**

Run: `node --test scripts/test_graph.mjs`
Expected: PASS (50) — `extractLLM` is network code, unaffected.

Manual (with `ollama pull llama3.2`): embed a batch, choose Extraction = **Ollama — chat**, pick `llama3.2`, Extract entities → Person/Business entities render. Confirm the OpenAI-compatible `llm` path still works if you have such an endpoint.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: Ollama chat transport for entity extraction (2-type prompt)"
```

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md` (SETUP.md already documents Ollama models/flag)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update CLAUDE.md**

In the "Running it" section, add the combined-proxy invocation:

```
python3 scripts/serve.py --kinetica http://localhost:9191 --ollama http://localhost:11434
```

In "How the app is wired" → **Embed** stage, note the third provider: `embedOllama()` posts to `/ollama/api/embed`, uses `pickEmbeddings()` for response shapes, and reduces via projection. Add a short "### The Ollama provider" subsection describing model discovery (`/api/tags`), the `/ollama` proxy route (POST + GET), and that the reduce "ask" option is treated as projection. In the extraction subsection, note the `ollama` transport option uses `/ollama/api/chat` with the current 2-type prompt.

In "Testing the pure core functions", add `pickEmbeddings()` to the list of CORE functions covered by `scripts/test_graph.mjs`, and note `scripts/test_serve.py` covers `resolve_upstream()`.

- [ ] **Step 2: Confirm README pointer**

Verify `README.md` still points at `SETUP.md` for Ollama setup (added earlier). No further change unless the run command drifted.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document native Ollama provider, proxy route, and tests"
```

---

## Self-Review

**Spec coverage:**
- Proxy route table + `--ollama` + GET proxy → Task 1. ✓
- Provider UI option + Ollama panel → Task 3. ✓
- `embedOllama` + `pickEmbeddings` + projection default + "ask"→project → Tasks 2, 3. ✓
- Model discovery `/api/tags` + health check → Task 4. ✓
- Ollama chat extraction transport, 2-type prompt kept → Task 5. ✓
- Testing (`resolve_upstream` Python, `pickEmbeddings` Node) → Tasks 1, 2. ✓
- Error handling through `log()` with actionable text → Tasks 4, plus throws in 3/5. ✓
- Files touched list (serve.py, index.html, test_graph.mjs, test_serve.py, CLAUDE.md, README) → all covered. ✓
- YAGNI non-goals (no pull, no streaming, no keep-alive, no embed/chat auto-detect) → respected. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. The only forward reference is Task 3's manual step mentioning Refresh (delivered in Task 4) — called out explicitly, not a placeholder.

**Type consistency:** `resolve_upstream(path, routes)` used identically in test and serve.py. `pickEmbeddings(json, expected)` signature matches across Task 2 tests, Task 3 `embedOllama`. `embedOllama`/`ollamaModels`/`fillModelSelect`/`refreshOllamaModels` names consistent across Tasks 3–5. DOM ids (`#ollamaUrl`, `#ollamaEmbedModel`, `#ollamaChatModel`, `#btnOllamaRefresh`, `#ollamaOpts`, `#ollamaChatOpts`) consistent between markup and JS.
