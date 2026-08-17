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


if __name__ == "__main__":
    unittest.main()
