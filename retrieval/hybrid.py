"""Phase 2 — Recherche hybride : dense (Qdrant) + lexicale (BM25), fusion RRF.

POURQUOI l'hybride : le dense capture le sens ("isoler des ressources réseau"
-> VPC) mais rate les termes exacts et rares ("gp3", "NACL", "IMDSv2") que
BM25 attrape parfaitement. Sur un corpus technique AWS plein de sigles, c'est
le gain le plus rentable de toute la Phase 2.

POURQUOI RRF (Reciprocal Rank Fusion) : fusionner des scores de natures
différentes (cosinus vs BM25) est instable ; fusionner des RANGS est robuste
et sans hyperparamètre sensible.  score(d) = Σ 1/(k + rang_i(d)), k=60.

Usage :
    python retrieval/hybrid.py "What is the difference between gp2 and gp3 volumes?"
"""
from __future__ import annotations
import pickle
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_DIR, settings
from ingestion.chunking import load_chunks
from retrieval.query_naive import RetrievedChunk, retrieve_dense

from rank_bm25 import BM25Okapi

RRF_K = 60
BM25_INDEX_PATH = PROCESSED_DIR / "bm25_index.pkl"


def _tokenize(text: str) -> list[str]:
    """Tokenisation simple ; conserve les termes techniques (gp3, t3.micro)."""
    return re.findall(r"[a-z0-9][a-z0-9.\-]*", text.lower())


class BM25Index:
    def __init__(self, chunk_ids: list[str], texts: list[str]):
        self.chunk_ids = chunk_ids
        self.bm25 = BM25Okapi([_tokenize(t) for t in texts])
        # Pour reconstruire les RetrievedChunk sans requêter Qdrant
        self.payloads = {}

    @classmethod
    def build(cls) -> "BM25Index":
        chunks = load_chunks()
        idx = cls([c.chunk_id for c in chunks], [c.text for c in chunks])
        idx.payloads = {c.chunk_id: c for c in chunks}
        BM25_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        # On ne pickle QUE les données brutes, pas l'objet — évite les erreurs
        # de résolution de classe selon le module appelant (__main__ vs import).
        import pickle as _pk
        with BM25_INDEX_PATH.open("wb") as f:
            _pk.dump({"chunk_ids": idx.chunk_ids,
                      "texts": [idx.payloads[c].text for c in idx.chunk_ids],
                      "payloads": idx.payloads}, f)
        return idx

    @classmethod
    def load(cls) -> "BM25Index":
        import pickle as _pk
        if not BM25_INDEX_PATH.exists():
            print("Index BM25 absent — construction (une seule fois)...")
            return cls.build()
        with BM25_INDEX_PATH.open("rb") as f:
            data = _pk.load(f)
        # Ancien format (objet complet pickle) -> reconstruire proprement
        if not isinstance(data, dict):
            return cls.build()
        idx = cls(data["chunk_ids"], data["texts"])
        idx.payloads = data["payloads"]
        return idx

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        scores = self.bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in ranked[:top_k]:
            c = self.payloads[self.chunk_ids[i]]
            out.append(RetrievedChunk(
                chunk_id=c.chunk_id, text=c.text, source_file=c.source_file,
                service=c.service, section=c.section, score=float(scores[i]),
            ))
        return out


def rrf_fusion(result_lists: list[list[RetrievedChunk]],
               top_k: int) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) \
                                     + 1.0 / (RRF_K + rank + 1)
            best.setdefault(chunk.chunk_id, chunk)
    fused = sorted(scores, key=scores.get, reverse=True)[:top_k]
    out = []
    for cid in fused:
        c = best[cid]
        out.append(RetrievedChunk(chunk_id=c.chunk_id, text=c.text,
                                  source_file=c.source_file, service=c.service,
                                  section=c.section, score=scores[cid]))
    return out


def retrieve_hybrid(query: str, top_k: int = 10,
                    fetch_k: int = 25) -> list[RetrievedChunk]:
    """fetch_k > top_k : chaque retriever ramène large, la fusion départage.
    Le top_k=10 restant sera réduit à 5 par le reranker (voir reranker.py)."""
    dense = retrieve_dense(query, top_k=fetch_k)
    lexical = BM25Index.load().search(query, top_k=fetch_k)
    return rrf_fusion([dense, lexical], top_k=top_k)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    args = parser.parse_args()
    q = " ".join(args.query)

    print("=== DENSE seul (top 5) ===")
    for c in retrieve_dense(q, top_k=5):
        print(f"  {c.score:.3f}  [{c.service}] {c.section}")
    print("\n=== BM25 seul (top 5) ===")
    for c in BM25Index.load().search(q, top_k=5):
        print(f"  {c.score:.2f}  [{c.service}] {c.section}")
    print("\n=== HYBRIDE RRF (top 5) ===")
    for c in retrieve_hybrid(q, top_k=5):
        print(f"  {c.score:.4f}  [{c.service}] {c.section}")
