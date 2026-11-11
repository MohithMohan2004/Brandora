"""The all-combined ablation variant must return exactly retrieve_context's ranked IDs
on every development query (needs local Ollama with the embedding model).
Run: venv/bin/python eval/test_retrieval_dev.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import retrieval_core as R  # noqa: E402
from retrieval_dev import verify_equivalence  # noqa: E402


class Equivalence(unittest.TestCase):
    def test_full_variant_matches_retrieve_context_on_all_dev_queries(self):
        queries = R.dev_queries()
        self.assertEqual(len(queries), 200)
        self.assertEqual(verify_equivalence(R.Ranker(), queries, 6), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
