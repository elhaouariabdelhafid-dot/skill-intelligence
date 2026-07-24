"""Phase 2 — Re-ranking par cross-encoder.

POURQUOI : le bi-encoder encode question et document SÉPARÉMENT — rapide mais
approximatif. Le cross-encoder lit la paire ENSEMBLE — précis mais lent.
Stratégie en deux étages : hybride ramène 15-30 candidats, le cross-encoder
réordonne, on garde le top 5.

CHANGEMENT : utilise FastEmbed (ONNX) plutôt que sentence-transformers, pour
la même raison que l'indexation — 10 à 20× plus rapide sur CPU.

Usage :
    python retrieval/reranker.py "How does IAM evaluate policies?"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from retrieval.hybrid import retrieve_hybrid
from retrieval.query_naive import RetrievedChunk, build_prompt, generate

_reranker = None


def reranker():
    """Singleton — le chargement du modèle coûte plusieurs secondes."""
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _reranker = TextCrossEncoder(model_name=settings.reranker_model)
    return _reranker


def rerank(query: str, chunks: list[RetrievedChunk],
           top_k: int = 5) -> list[RetrievedChunk]:
    if not chunks:
        return []
    scores = list(reranker().rerank(query, [c.text for c in chunks]))
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [
        RetrievedChunk(chunk_id=chunks[i].chunk_id, text=chunks[i].text,
                       source_file=chunks[i].source_file,
                       service=chunks[i].service, section=chunks[i].section,
                       score=float(scores[i]))
        for i in order[:top_k]
    ]


def retrieve_final(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Pipeline de retrieval complet : hybride -> rerank.
    C'est CETTE fonction qu'utilisent la génération (Phase 3) et les agents
    (Phase 4)."""
    candidates = retrieve_hybrid(query, top_k=15, fetch_k=30)
    return rerank(query, candidates, top_k=top_k)


def answer_v2(query: str) -> dict:
    chunks = retrieve_final(query)
    return {
        "answer": generate(build_prompt(query, chunks)),
        "sources": [{"tag": f"S{i+1}", "file": c.source_file,
                     "section": c.section, "rerank_score": round(c.score, 3)}
                    for i, c in enumerate(chunks)],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    q = " ".join(args.query)

    if args.no_llm:
        for i, c in enumerate(retrieve_final(q), 1):
            print(f"\n[S{i}] {c.score:.3f}  {c.source_file}  ({c.service})")
            print(c.text[:300])
    else:
        result = answer_v2(q)
        print("\n=== RÉPONSE (RAG v2 : hybride + rerank) ===\n")
        print(result["answer"])
        print("\n=== SOURCES ===")
        for s in result["sources"]:
            print(f"  [{s['tag']}] {s['file']}  ({s['section']})  {s['rerank_score']}")
