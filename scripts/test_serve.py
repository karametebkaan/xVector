import json
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


class VertexModelId(unittest.TestCase):
    def test_dated_model_gets_at_sign(self):
        self.assertEqual(serve._vertex_model_id("claude-haiku-4-5-20251001"),
                         "claude-haiku-4-5@20251001")

    def test_undated_alias_passes_through(self):
        self.assertEqual(serve._vertex_model_id("claude-opus-4-8"), "claude-opus-4-8")

    def test_empty_is_empty(self):
        self.assertEqual(serve._vertex_model_id(""), "")


class ExtractJson(unittest.TestCase):
    def test_bare_object(self):
        self.assertEqual(serve._extract_json('{"a":1}'), {"a": 1})

    def test_fenced_with_prose(self):
        text = 'Here you go:\n```json\n{"entities":[],"relations":[]}\n```\nDone.'
        self.assertEqual(serve._extract_json(text), {"entities": [], "relations": []})

    def test_trailing_text_after_object(self):
        self.assertEqual(serve._extract_json('{"a":1} and more'), {"a": 1})

    def test_no_json_returns_none(self):
        self.assertIsNone(serve._extract_json("no json here"))

    def test_empty_returns_none(self):
        self.assertIsNone(serve._extract_json(""))


class RunClaude(unittest.TestCase):
    def _claude_body(self, text):
        return json.dumps({"content": [{"type": "text", "text": text}]}).encode()

    def test_success_parses_content_json(self):
        captured = {}
        def post(url, body, token, timeout):
            captured["url"] = url; captured["token"] = token; captured["body"] = body
            return self._claude_body('{"entities":[{"name":"Kaan","label":"People"}],"relations":[]}')
        r = serve.run_claude("prompt", {"type": "object"}, "claude-haiku-4-5-20251001",
                             "proj-x", "global", _token="tok-123", _post=post)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"]["entities"][0]["name"], "Kaan")
        self.assertIn("aiplatform.googleapis.com", captured["url"])
        self.assertIn("projects/proj-x/locations/global", captured["url"])
        self.assertIn("publishers/anthropic/models/claude-haiku-4-5@20251001:rawPredict",
                      captured["url"])
        self.assertEqual(captured["token"], "tok-123")
        self.assertIn(b"vertex-2023-10-16", captured["body"])

    def test_regional_host(self):
        def post(url, body, token, timeout):
            self.assertTrue(url.startswith("https://us-east5-aiplatform.googleapis.com/"))
            return self._claude_body("{}")
        serve.run_claude("p", {"type": "object"}, "claude-opus-4-8", "proj", "us-east5",
                         _token="t", _post=post)

    def test_default_model_when_blank(self):
        def post(url, body, token, timeout):
            self.assertIn("claude-haiku-4-5@20251001:rawPredict", url)
            return self._claude_body("{}")
        serve.run_claude("p", {"type": "object"}, "", "proj", "global", _token="t", _post=post)

    def test_no_schema_returns_raw_text(self):
        def post(url, body, token, timeout):
            return self._claude_body("just words, not json")
        r = serve.run_claude("p", None, "claude-opus-4-8", "proj", "global",
                             _token="t", _post=post)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"], "just words, not json")

    def test_no_token_returns_error(self):
        r = serve.run_claude("p", None, "claude-opus-4-8", "proj", "global",
                             _token="", _post=lambda *a: b"{}")
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("gcloud", r["message"])

    def test_vertex_error_body_surfaces_message(self):
        def post(url, body, token, timeout):
            return json.dumps({"error": {"message": "model not found"}}).encode()
        r = serve.run_claude("p", None, "bad-model", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("model not found", r["message"])

    def test_content_not_json_returns_error(self):
        def post(url, body, token, timeout):
            return self._claude_body("this is not json")
        r = serve.run_claude("p", {"type": "object"}, "claude-opus-4-8", "proj", "global",
                             _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("not JSON", r["message"])

    def test_list_wrapped_response(self):
        def post(url, body, token, timeout):
            return json.dumps([{"content": [{"type": "text", "text": '{"ok":1}'}]}]).encode()
        r = serve.run_claude("p", {"type": "object"}, "claude-opus-4-8", "proj", "global",
                             _token="t", _post=post)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"], {"ok": 1})

    def test_invalid_model_rejected_before_post(self):
        called = {"n": 0}
        def post(url, body, token, timeout):
            called["n"] += 1
            return self._claude_body("{}")
        r = serve.run_claude("p", None, "a/b", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("invalid model", r["message"])
        self.assertEqual(called["n"], 0)


class RunGemini(unittest.TestCase):
    def _gemini_body(self, text):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()

    def test_success_parses_content_json(self):
        captured = {}
        def post(url, body, token, timeout):
            captured["url"] = url; captured["token"] = token
            return self._gemini_body('{"entities":[{"name":"Kaan","label":"People"}],"relations":[]}')
        r = serve.run_gemini("prompt", "gemini-2.5-flash", "proj-x", "global",
                             _token="tok-123", _post=post)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"]["entities"][0]["name"], "Kaan")
        self.assertIn("aiplatform.googleapis.com", captured["url"])
        self.assertIn("projects/proj-x/locations/global", captured["url"])
        self.assertIn("gemini-2.5-flash:generateContent", captured["url"])
        self.assertEqual(captured["token"], "tok-123")

    def test_regional_host(self):
        def post(url, body, token, timeout):
            self.assertTrue(url.startswith("https://us-central1-aiplatform.googleapis.com/"))
            return self._gemini_body("{}")
        serve.run_gemini("p", "m", "proj", "us-central1", _token="t", _post=post)

    def test_no_token_returns_error(self):
        r = serve.run_gemini("p", "m", "proj", "global", _token="", _post=lambda *a: b"{}")
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("gcloud", r["message"])

    def test_google_error_body_surfaces_message(self):
        def post(url, body, token, timeout):
            return json.dumps({"error": {"message": "permission denied"}}).encode()
        r = serve.run_gemini("p", "m", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("permission denied", r["message"])

    def test_content_not_json_returns_error(self):
        def post(url, body, token, timeout):
            return self._gemini_body("this is not json")
        r = serve.run_gemini("p", "m", "proj", "global", _token="t", _post=post)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("not JSON", r["message"])

    def test_invalid_model_rejected_before_post(self):
        called = {"n": 0}
        def post(url, body, token, timeout):
            called["n"] += 1
            return self._gemini_body("{}")
        for bad in ("a/b", "../evil"):
            r = serve.run_gemini("p", bad, "proj", "global", _token="t", _post=post)
            self.assertEqual(r["status"], "ERROR")
            self.assertIn("invalid model", r["message"])
        self.assertEqual(called["n"], 0)   # no upstream request attempted


if __name__ == "__main__":
    unittest.main()
