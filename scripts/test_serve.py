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
