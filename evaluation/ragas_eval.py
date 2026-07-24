"""Phase 2 — Évaluation RAGAS : comparer RAG naïf vs RAG avancé.

POURQUOI : sans mesure, tu ne sais pas si le rerank ou l'hybride apportent
quelque chose. Ce script produit le TABLEAU COMPARATIF qui sera ton premier
chapitre expérimental.

Métriques :
- context_recall   : le contexte récupéré contient-il l'info de la réponse de
                     référence ? (mesure le RETRIEVAL — ta métrique n°1)
- context_precision: les chunks pertinents sont-ils bien classés en tête ?
- faithfulness     : la réponse générée est-elle fidèle au contexte ? (hallucinations)
- answer_relevancy : la réponse répond-elle à la question ?

Prérequis : golden_dataset.json rempli à la main (50 Q/R). Commence par 10
pour valider le pipeline, complète ensuite.

RAGAS utilise un LLM juge : configure un provider cloud dans .env pour cette
étape (le juge local 7B donne des métriques peu fiables).

Usage :
    python evaluation/ragas_eval.py --system naive
    python evaluation/ragas_eval.py --system v2
    python evaluation/ragas_eval.py --compare      # les deux + tableau
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"
RESULTS_PATH = Path(__file__).parent / "results"


def load_golden() -> list[dict]:
    with GOLDEN_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    items = [d for d in data["items"] if d.get("question") and d.get("ground_truth")]
    if len(items) < 5:
        raise RuntimeError(
            f"Golden dataset trop petit ({len(items)} items). "
            "Complète evaluation/golden_dataset.json (10 minimum, 50 visés).")
    return items


def run_system(system: str, items: list[dict]) -> list[dict]:
    """Exécute le RAG choisi sur chaque question du golden dataset."""
    if system == "naive":
        from retrieval.query_naive import retrieve_dense as retr
        from retrieval.query_naive import build_prompt, generate
        def pipeline(q):
            chunks = retr(q, top_k=5)
            return generate(build_prompt(q, chunks)), chunks
    elif system == "v2":
        from retrieval.reranker import retrieve_final
        from retrieval.query_naive import build_prompt, generate
        def pipeline(q):
            chunks = retrieve_final(q, top_k=5)
            return generate(build_prompt(q, chunks)), chunks
    else:
        raise ValueError(system)

    rows = []
    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] {item['question'][:60]}...")
        answer, chunks = pipeline(item["question"])
        rows.append({
            "user_input": item["question"],
            "response": answer,
            "retrieved_contexts": [c.text for c in chunks],
            "reference": item["ground_truth"],
        })
    return rows


def evaluate_with_ragas(rows: list[dict]) -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (answer_relevancy, context_precision,
                               context_recall, faithfulness)
    ds = Dataset.from_list(rows)
    result = evaluate(ds, metrics=[context_recall, context_precision,
                                   faithfulness, answer_relevancy])
    return {k: round(float(v), 4) for k, v in result.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["naive", "v2"])
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    items = load_golden()
    RESULTS_PATH.mkdir(exist_ok=True)
    systems = ["naive", "v2"] if args.compare else [args.system]

    all_scores = {}
    for sysname in systems:
        print(f"\n=== Système : {sysname} ===")
        rows = run_system(sysname, items)
        (RESULTS_PATH / f"outputs_{sysname}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        scores = evaluate_with_ragas(rows)
        all_scores[sysname] = scores
        print(json.dumps(scores, indent=2))

    if args.compare:
        print("\n=== TABLEAU COMPARATIF ===")
        metrics = list(next(iter(all_scores.values())).keys())
        header = f"{'Métrique':<22}" + "".join(f"{s:>10}" for s in systems)
        print(header)
        print("-" * len(header))
        for m in metrics:
            print(f"{m:<22}" + "".join(f"{all_scores[s][m]:>10}" for s in systems))
        (RESULTS_PATH / "comparison.json").write_text(
            json.dumps(all_scores, indent=2), encoding="utf-8")
        print(f"\nSeuils visés : context_recall > 0.80, faithfulness > 0.85")


if __name__ == "__main__":
    main()
