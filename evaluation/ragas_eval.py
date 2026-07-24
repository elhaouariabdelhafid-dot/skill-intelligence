"""Phase 2 — Évaluation RAGAS : comparer RAG naïf vs RAG avancé.

Juge : Gemini (gemini-3.6-flash) via son tier gratuit. Les embeddings de
RAGAS (pour answer_relevancy) passent aussi par Gemini.

Métriques :
- context_recall    : le contexte récupéré couvre-t-il la réponse de référence ?
                      (mesure le RETRIEVAL — métrique n°1)
- context_precision : les chunks pertinents sont-ils bien classés en tête ?
- faithfulness      : la réponse est-elle fidèle au contexte ? (hallucinations)
- answer_relevancy  : la réponse répond-elle à la question ?

Usage :
    python evaluation/ragas_eval.py --system naive
    python evaluation/ragas_eval.py --system v2
    python evaluation/ragas_eval.py --compare
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"
RESULTS_PATH = Path(__file__).parent / "results"

# Modèle juge — figé ici, modifiable si le quota change
JUDGE_MODEL = "gemini-3.6-flash"
EMBED_MODEL = "models/text-embedding-004"


def load_golden() -> list[dict]:
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    items = [d for d in data["items"] if d.get("question") and d.get("ground_truth")]
    if len(items) < 5:
        raise RuntimeError(f"Golden dataset trop petit ({len(items)}). Minimum 5.")
    return items


def run_system(system: str, items: list[dict]) -> list[dict]:
    """Exécute le RAG choisi sur chaque question. Pause anti-quota entre appels."""
    from retrieval.query_naive import build_prompt, generate

    if system == "naive":
        from retrieval.query_naive import retrieve_dense
        def pipeline(q):
            chunks = retrieve_dense(q, top_k=5)
            return generate(build_prompt(q, chunks)), chunks
    elif system == "v2":
        from retrieval.reranker import retrieve_final
        def pipeline(q):
            chunks = retrieve_final(q, top_k=5)
            return generate(build_prompt(q, chunks)), chunks
    else:
        raise ValueError(system)

    rows = []
    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] {item['question'][:55]}...")
        answer, chunks = pipeline(item["question"])
        rows.append({
            "user_input": item["question"],
            "response": answer,
            "retrieved_contexts": [c.text for c in chunks],
            "reference": item["ground_truth"],
        })
        time.sleep(5)   # ménage le quota Ollama/Gemini pour la génération
    return rows


def build_gemini_judge():
    """Juge = Groq (llama-3.3-70b). Embedder = local (fastembed via HF),
    pour ne pas dépendre d'un embedder cloud soumis à quota."""
    import os
    from config import settings
    os.environ["GROQ_API_KEY"] = settings.groq_api_key
    from langchain_groq import ChatGroq
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    judge = LangchainLLMWrapper(
        ChatGroq(model=settings.groq_model, temperature=0,
                 api_key=settings.groq_api_key, max_retries=3))
    embedder = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5"))
    return judge, embedder


def evaluate_with_ragas(rows: list[dict]) -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (answer_relevancy, context_precision,
                               context_recall, faithfulness)

    judge, embedder = build_gemini_judge()
    ds = Dataset.from_list(rows)

    # Les métriques reçoivent le juge Gemini ; sans ça RAGAS cherche OpenAI
    from ragas.run_config import RunConfig
    run_config = RunConfig(max_workers=1, timeout=180)
    result = evaluate(
        ds,
        metrics=[context_recall, context_precision, faithfulness, answer_relevancy],
        llm=judge,
        embeddings=embedder,
        run_config=run_config,
    )
    df = result.to_pandas()
    scores = {}
    for col in ["context_recall", "context_precision", "faithfulness",
                "answer_relevancy"]:
        if col in df.columns:
            scores[col] = round(float(df[col].mean()), 4)
    return scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["naive", "v2"])
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    items = load_golden()
    print(f"Golden dataset : {len(items)} questions\n")
    RESULTS_PATH.mkdir(exist_ok=True)
    systems = ["naive", "v2"] if args.compare else [args.system or "v2"]

    all_scores = {}
    for sysname in systems:
        print(f"=== Système : {sysname} — génération des réponses ===")
        rows = run_system(sysname, items)
        (RESULTS_PATH / f"outputs_{sysname}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"=== Système : {sysname} — évaluation RAGAS (Gemini juge) ===")
        scores = evaluate_with_ragas(rows)
        all_scores[sysname] = scores
        print(json.dumps(scores, indent=2), "\n")

    if len(all_scores) > 1:
        print("=== TABLEAU COMPARATIF ===")
        metrics = list(next(iter(all_scores.values())).keys())
        header = f"{'Métrique':<22}" + "".join(f"{s:>10}" for s in systems)
        print(header)
        print("-" * len(header))
        for m in metrics:
            line = f"{m:<22}"
            for s in systems:
                line += f"{all_scores[s].get(m, 0):>10}"
            print(line)
        (RESULTS_PATH / "comparison.json").write_text(
            json.dumps(all_scores, indent=2), encoding="utf-8")

    print("\nSeuils visés : context_recall > 0.80, faithfulness > 0.85")


if __name__ == "__main__":
    main()
