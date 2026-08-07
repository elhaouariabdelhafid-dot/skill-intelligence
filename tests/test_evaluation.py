"""Phase 4 — Test du pipeline d'évaluation sur une question réelle.

Prend une question de ta banque acceptée, fabrique 3 réponses candidates de
qualité différente (bonne / moyenne / hallucinée), et montre comment les agents
les notent. C'est la démonstration que ton système discrimine les niveaux.

Usage :
    python agents/test_evaluation.py              # 1ère question, réponse bonne
    python agents/test_evaluation.py --quality bad
    python agents/test_evaluation.py --index 3 --quality medium
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.graph import evaluate_answer

ACCEPTED = Path("data/processed/questions_accepted.jsonl")


def load_question(index: int) -> dict:
    qs = [json.loads(l) for l in ACCEPTED.open() if l.strip()]
    if index >= len(qs):
        raise SystemExit(f"Index {index} hors limites ({len(qs)} questions)")
    return qs[index]


def make_candidate_answer(q: dict, quality: str) -> str:
    """Fabrique une réponse candidate de qualité contrôlée pour le test."""
    if quality == "good":
        # La réponse de référence = une bonne réponse
        return q["expected_answer"]
    if quality == "medium":
        # Version tronquée : partiellement correcte
        ref = q["expected_answer"]
        return ref[:len(ref) // 2] + "..."
    if quality == "bad":
        # Réponse plausible mais fausse (hallucination)
        return ("AWS automatically handles this for you with no configuration. "
                "The default limit is unlimited and there are no restrictions. "
                "You can enable the 'AutoMagic' feature which solves everything.")
    raise ValueError(quality)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--quality", choices=["good", "medium", "bad"],
                        default="good")
    args = parser.parse_args()

    q = load_question(args.index)
    candidate = make_candidate_answer(q, args.quality)

    print("=" * 70)
    print(f"QUESTION [{q['service']} / {q['bloom_level']} / {q['difficulty']}]")
    print(q["question"])
    print(f"\nRÉPONSE CANDIDATE ({args.quality}) :")
    print(candidate[:300])
    print("=" * 70)
    print("\nÉvaluation par les 3 agents en cours...\n")

    result = evaluate_answer(
        question=q["question"],
        expected_answer=q["expected_answer"],
        key_points=q["key_points"],
        rubric=q["rubric"],
        candidate_answer=candidate,
        service=q["service"],
    )

    print("--- SCORES PAR AGENT ---")
    print(f"  Grader (exactitude)  : {result['grader']['score']}/4")
    print(f"    {result['grader']['justification'][:180]}")
    print(f"  Reasoner (logique)   : {result['reasoner']['score']}/4")
    print(f"    {result['reasoner']['justification'][:180]}")
    print(f"  Critic (problèmes)   : {result['critic']['score']}/4 (0=aucun)")
    print(f"    {result['critic']['justification'][:180]}")

    print(f"\n--- SCORE FINAL : {result['final_score']}/4 ---")
    print("\nForces :")
    for s in result.get("strengths", []):
        print(f"  + {s}")
    print("Faiblesses :")
    for w in result.get("weaknesses", []):
        print(f"  - {w}")


if __name__ == "__main__":
    main()
