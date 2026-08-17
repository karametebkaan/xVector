import json
import os
import sys
import types
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


class RunClaude(unittest.TestCase):
    def _fake_run(self, returncode, stdout, stderr=b""):
        def run(cmd, stdin_bytes, timeout):
            self.captured = {"cmd": cmd, "stdin": stdin_bytes, "timeout": timeout}
            return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        return run

    def test_success_returns_structured_output(self):
        out = json.dumps({"is_error": False, "structured_output": {"entities": [], "relations": []}}).encode()
        r = serve.run_claude("hi", {"type": "object"}, "claude-haiku-4-5-20251001", _run=self._fake_run(0, out))
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"], {"entities": [], "relations": []})
        self.assertIn("--json-schema", self.captured["cmd"])
        self.assertIn("--model", self.captured["cmd"])
        self.assertEqual(self.captured["stdin"], b"hi")

    def test_no_schema_omits_flag(self):
        out = json.dumps({"is_error": False, "structured_output": {}}).encode()
        serve.run_claude("hi", None, "", _run=self._fake_run(0, out))
        self.assertNotIn("--json-schema", self.captured["cmd"])
        self.assertNotIn("--model", self.captured["cmd"])

    def test_is_error_true_returns_error(self):
        out = json.dumps({"is_error": True, "result": "model not found"}).encode()
        r = serve.run_claude("hi", None, "bad", _run=self._fake_run(1, out))
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("model not found", r["message"])

    def test_non_json_stdout_returns_error(self):
        r = serve.run_claude("hi", None, "m", _run=self._fake_run(0, b"not json", b"boom"))
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("non-JSON", r["message"])

    def test_missing_structured_output_returns_error(self):
        out = json.dumps({"is_error": False}).encode()
        r = serve.run_claude("hi", None, "m", _run=self._fake_run(0, out))
        self.assertEqual(r["status"], "ERROR")

    def test_binary_not_found_returns_error(self):
        def run(cmd, stdin_bytes, timeout):
            raise FileNotFoundError("no claude")
        r = serve.run_claude("hi", None, "m", _run=run)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("not found", r["message"])


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
