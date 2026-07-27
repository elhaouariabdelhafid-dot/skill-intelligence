"""Phase 5 — Identification des besoins de formation + recommandations.

PRINCIPE : à partir du profil, détecter les compétences sous un seuil (les gaps),
puis recommander des ressources de révision. Les recommandations pointent vers
les sections RÉELLES du corpus AWS (via le RAG) — pas des suggestions génériques.

C'est là que ton RAG sert une deuxième fois : non plus pour évaluer, mais pour
GUIDER l'apprentissage. Pour chaque gap, on récupère les passages du corpus les
plus pertinents à réviser.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

GAP_THRESHOLD = 60.0        # sous 60%, la compétence est un besoin de formation
PRIORITY_HIGH = 40.0        # sous 40%, priorité haute


def identify_gaps(profile: dict) -> list[dict]:
    """Détecte les compétences faibles, triées par priorité."""
    gaps = []
    for service, score in profile["services"].items():
        if score < GAP_THRESHOLD:
            gaps.append({
                "service": service,
                "score": score,
                "priority": "haute" if score < PRIORITY_HIGH else "moyenne",
                "gap": round(GAP_THRESHOLD - score, 1),
            })
    return sorted(gaps, key=lambda g: g["score"])


def recommend_resources(gap: dict, n: int = 3) -> list[dict]:
    """Recommande des sections du corpus à réviser pour combler un gap.

    Utilise le retrieval pour trouver les passages du service concerné les plus
    fondamentaux (on cherche les concepts de base de ce service)."""
    from retrieval.reranker import retrieve_final

    query = f"{gap['service']} fundamentals key concepts best practices"
    chunks = retrieve_final(query, top_k=n)
    return [
        {"source": c.source_file, "service": c.service,
         "excerpt": c.text[:200].strip()}
        for c in chunks if c.service == gap["service"]
    ][:n] or [
        {"source": c.source_file, "service": c.service,
         "excerpt": c.text[:200].strip()}
        for c in chunks[:n]
    ]


def build_learning_plan(profile: dict) -> dict:
    """Plan de formation complet : gaps + ressources + priorités."""
    gaps = identify_gaps(profile)
    plan = {"user_id": profile["user_id"], "overall": profile["overall"],
            "n_gaps": len(gaps), "recommendations": []}

    for gap in gaps:
        resources = recommend_resources(gap)
        plan["recommendations"].append({
            "service": gap["service"],
            "current_level": gap["score"],
            "priority": gap["priority"],
            "resources": resources,
        })
    return plan


def print_learning_plan(plan: dict) -> None:
    print(f"\n{'='*55}")
    print("PLAN DE FORMATION RECOMMANDÉ")
    print(f"{'='*55}")
    print(f"Niveau global : {plan['overall']}%")
    print(f"Compétences à renforcer : {plan['n_gaps']}\n")

    if not plan["recommendations"]:
        print("Aucun besoin de formation critique — profil solide.")
        return

    for i, rec in enumerate(plan["recommendations"], 1):
        print(f"{i}. {rec['service']} — niveau {rec['current_level']}% "
              f"[priorité {rec['priority']}]")
        print("   À réviser :")
        for r in rec["resources"]:
            print(f"     • {r['source']}")
            print(f"       {r['excerpt'][:120]}...")
        print()


if __name__ == "__main__":
    import argparse
    from skills.profile import compute_profile
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=1)
    args = parser.parse_args()

    profile = compute_profile(args.user)
    plan = build_learning_plan(profile)
    print_learning_plan(plan)
