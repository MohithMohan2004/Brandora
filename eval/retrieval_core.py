"""Retrieval ranking with switchable components, for the ablation (retrieval_dev.py).

Only the ablated parts are re-implemented here (document text, query prefix, which
rankers are fused). Embeddings, BM25 scoring, record text and the catalogue loader are
the app's own functions. The all-on variant is verified to return exactly the ranked
IDs of app.retrieve_context (see test_retrieval_dev.py and retrieval_dev.py --check).
"""
import numpy as np

from common import import_app

A = import_app()
RRF_K = 60

VARIANTS = {
    "dense_baseline":   dict(prefix=False, clean=False, dense=True,  bm25=False),
    "dense+prefixes":   dict(prefix=True,  clean=False, dense=True,  bm25=False),
    "dense+prefix+clean": dict(prefix=True, clean=True, dense=True,  bm25=False),
    "bm25_only":        dict(prefix=False, clean=True,  dense=False, bm25=True),
    "all_combined":     dict(prefix=True,  clean=True,  dense=True,  bm25=True),
}


def build_records():
    products, guidelines = A.load_data()
    recs = []
    for _, row in products.iterrows():
        recs.append({"source_id": f"products:{row['product_id']}", "kind": "product", "row": row,
                     "full": A.row_to_text(row, "product"), "search": A.search_text(row, "product"),
                     "title": str(row.get("product_name", "")).strip() or "none"})
    for _, row in guidelines.iterrows():
        recs.append({"source_id": f"guidelines:{row['guideline_id']}", "kind": "guideline", "row": row,
                     "full": A.row_to_text(row, "guideline"), "search": A.search_text(row, "guideline"),
                     "title": "none"})
    return recs


class Ranker:
    def __init__(self):
        self.recs = build_records()
        self.doc_vecs = {}

    def _docs(self, prefix, clean):
        body = (lambda r: r["search"]) if clean else (lambda r: r["full"])
        return tuple((f"title: {r['title']} | text: {body(r)}" if prefix else body(r)) for r in self.recs)

    def _vectors(self, prefix, clean):
        key = (prefix, clean)
        if key not in self.doc_vecs:
            m = np.array(A.cached_ollama_embed_texts(self._docs(prefix, clean), A.EMBED_MODEL, A.OLLAMA_BASE_URL),
                         dtype=np.float32)
            self.doc_vecs[key] = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)
        return self.doc_vecs[key]

    def rank(self, query, prefix, clean, dense, bm25):
        """All record IDs, best first."""
        n = len(self.recs)
        fused = np.zeros(n)
        if dense:
            q = np.array(A.ollama_embed([f"task: search result | query: {query}" if prefix else query])[0],
                         dtype=np.float32)
            q = q / max(np.linalg.norm(q), 1e-12)
            scores = self._vectors(prefix, clean) @ q
            fused += 1 / (RRF_K + np.argsort(-scores).argsort()) if bm25 else scores
        if bm25:
            ranks = np.argsort(-A.bm25_scores([r["search"] for r in self.recs], query)).argsort()
            fused = (fused + 1 / (RRF_K + ranks)) if dense else 1 / (RRF_K + ranks)
        order = np.argsort(-fused)   # same call as app.retrieve_context, so ties break identically
        return [self.recs[int(i)]["source_id"] for i in order]


def dev_queries():
    """The 200 development queries: same two templates as backend/evaluate.py eval_retrieval()."""
    products, _ = A.load_data()
    out = []
    for _, row in products.iterrows():
        target = f"products:{row['product_id']}"
        out.append(("named", f"Create an Instagram ad for the {row['product_name']}.", target))
        out.append(("descriptive",
                    f"Create an ad for a {row['category'].lower()} product made of {row['materials']} "
                    f"for {row['target_audience'].lower()}.", target))
    return out
