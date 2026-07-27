"""Phase 4 — Agrégation des 3 agents + feedback explicable.

CE N'EST PAS UN AGENT (pas d'appel LLM pour le score) : c'est une fonction
déterministe, comme prévu dans ton cahier des charges. Le score final est une
formule pondérée, transparente et reproductible — un jury peut la vérifier.

FORMULE :
    base = 0.45 * grader + 0.45 * reasoner + 0.10 * (4 - critic_severity)
    puis VETO : si le Critic signale une hallucination majeure, le score est
    plafonné à 1.5 — une réponse dangereuse ne peut pas obtenir une bonne note,
    même bien écrite.

POURQUOI ces poids : exactitude (grader) et raisonnement (reasoner) comptent
autant ; le critic ajuste à la marge sauf veto. À justifier/ajuster dans ton
rapport — c'est un choix de conception, pas une vérité absolue.

Le feedback textuel, lui, PEUT utiliser un LLM pour être fluide — mais on le
génère à partir des justifications déjà produites, sans réévaluer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.state import EvaluationState

W_GRADER = 0.45
W_REASONER = 0.45
W_CRITIC = 0.10
VETO_CAP = 1.5


def aggregate(state: EvaluationState) -> dict:
    """Nœud LangGraph final : combine les scores et bâtit le feedback."""
    grader = state["grader"]
    reasoner = state["reasoner"]
    critic = state["critic"]

    # Critic : score = sévérité des problèmes (0 bon, 4 mauvais) -> on inverse
    critic_positive = 4.0 - critic["score"]

    base = (W_GRADER * grader["score"]
            + W_REASONER * reasoner["score"]
            + W_CRITIC * critic_positive)

    # Veto hallucination majeure
    veto = "MAJOR_HALLUCINATION" in critic.get("citations", [])
    final = min(base, VETO_CAP) if veto else base
    final = round(max(0.0, min(4.0, final)), 2)

    # Feedback structuré, assemblé à partir des justifications (pas de réévaluation)
    strengths = []
    weaknesses = []

    if grader["score"] >= 3:
        strengths.append(f"Exactitude technique : {grader['justification'][:200]}")
    else:
        weaknesses.append(f"Exactitude technique : {grader['justification'][:200]}")

    if reasoner["score"] >= 3:
        strengths.append(f"Raisonnement : {reasoner['justification'][:200]}")
    else:
        weaknesses.append(f"Raisonnement : {reasoner['justification'][:200]}")

    if critic["score"] >= 2:
        weaknesses.append(f"Problèmes détectés : {critic['justification'][:200]}")

    if veto:
        weaknesses.append("⚠ Hallucination majeure — score plafonné.")

    feedback = (
        f"Score final : {final}/4. "
        f"Détail — exactitude {grader['score']}/4, "
        f"raisonnement {reasoner['score']}/4, "
        f"problèmes {critic['score']}/4 (0 = aucun)."
    )

    return {
        "final_score": final,
        "feedback": feedback,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
