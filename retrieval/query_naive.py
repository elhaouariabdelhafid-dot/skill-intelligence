"""Phase 1 — RAG naïf : retrieval dense top-k -> prompt -> LLM.

C'est ta BASELINE. Toutes les améliorations de Phase 2 seront mesurées contre
ce pipeline. Ne le supprime jamais.

POURQUOI les balises [S1], [S2] : elles forcent le modèle à ancrer chaque
affirmation. C'est l'embryon de l'Explainable AI, et RAGAS mesure la
faithfulness sur cette base.

Usage :
    python retrieval/query_naive.py "How do security groups differ from NACLs?"
    python retrieval/query_naive.py --service IAM "What is a permissions boundary?"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from ingestion.embeddings import get_embedder

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

TOP_K = 5


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source_file: str
    service: str
    section: str
    score: float


def retrieve_dense(query: str, top_k: int = TOP_K,
                   service: str | None = None) -> list[RetrievedChunk]:
    client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
    vector = get_embedder().encode_query(query)

    qfilter = None
    if service:
        qfilter = Filter(must=[FieldCondition(key="service",
                                              match=MatchValue(value=service))])

    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=top_k,
        query_filter=qfilter,
        with_payload=True,
    ).points

    return [
        RetrievedChunk(
            chunk_id=h.payload["chunk_id"],
            text=h.payload["text"],
            source_file=h.payload["source_file"],
            service=h.payload["service"],
            section=h.payload["section"],
            score=h.score,
        )
        for h in hits
    ]


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(
        f"[S{i+1}] ({c.service} — {c.section})\n{c.text}"
        for i, c in enumerate(chunks)
    )
    return f"""You are an AWS technical expert. Answer the question using ONLY the sources below.
Cite the sources you use with their tag, e.g. [S1]. If the sources do not contain
the answer, say so explicitly — do not invent.

SOURCES:
{context}

QUESTION: {query}

ANSWER (with citations):"""


def generate(prompt: str) -> str:
    from llm.client import complete
    return complete(prompt, temperature=0.1, max_tokens=700)


def answer(query: str, service: str | None = None) -> dict:
    chunks = retrieve_dense(query, service=service)
    if not chunks:
        return {"answer": "Aucun contexte trouvé.", "sources": []}
    text = generate(build_prompt(query, chunks))
    return {
        "answer": text,
        "sources": [
            {"tag": f"S{i+1}", "file": c.source_file, "section": c.section,
             "score": round(c.score, 3)}
            for i, c in enumerate(chunks)
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    parser.add_argument("--service", default=None,
                        help="EC2, S3, VPC, IAM, RDS, Lambda, Well-Architected")
    parser.add_argument("--no-llm", action="store_true",
                        help="Afficher seulement les chunks récupérés")
    args = parser.parse_args()
    q = " ".join(args.query)

    if args.no_llm:
        for i, c in enumerate(retrieve_dense(q, service=args.service), 1):
            print(f"\n[S{i}] {c.score:.3f}  {c.source_file}  ({c.service})")
            print(c.text[:300])
    else:
        result = answer(q, service=args.service)
        print("\n=== RÉPONSE ===\n")
        print(result["answer"])
        print("\n=== SOURCES ===")
        for s in result["sources"]:
            print(f"  [{s['tag']}] {s['file']}  ({s['section']})  score={s['score']}")
