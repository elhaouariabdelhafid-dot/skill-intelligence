"""Phase 4 — Assemblage du graphe d'évaluation avec LangGraph.

STRUCTURE DU GRAPHE :
    START -> retrieve_context -> [grader, reasoner, critic] -> aggregator -> END
                                  (les 3 agents en parallèle)

POURQUOI LangGraph : il gère l'exécution PARALLÈLE des 3 agents (ils ne
dépendent pas les uns des autres) et la fusion de leurs sorties dans l'état
partagé. Séquentiel serait 3x plus lent.

POURQUOI retrieve_context d'abord : les 3 agents ont besoin du même contexte
documentaire. On le récupère une seule fois, avant, avec TON pipeline
hybride+rerank de Phase 2.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.state import EvaluationState
from agents.grader import grade
from agents.reasoner import reason
from agents.critic import criticize
from agents.aggregator import aggregate

import time
from langgraph.graph import END, START, StateGraph


def retrieve_context_node(state: EvaluationState) -> dict:
    """Récupère le contexte documentaire via le pipeline de Phase 2."""
    from retrieval.reranker import retrieve_final
    chunks = retrieve_final(state["question"], top_k=3)
    context = "\n\n".join(
        f"[{c.service}] {c.text}" for c in chunks
    )
    return {
        "context": context,
        "context_chunk_ids": [c.chunk_id for c in chunks],
    }


def build_evaluation_graph():
    """Construit et compile le graphe d'évaluation."""
    g = StateGraph(EvaluationState)

    def _paced(fn):
        def wrapped(state):
            time.sleep(0)  # respecte 6000 tokens/min de Groq 8B
            return fn(state)
        return wrapped

    g.add_node("retrieve", retrieve_context_node)
    g.add_node("grader", _paced(grade))
    g.add_node("reasoner", _paced(reason))
    g.add_node("critic", _paced(criticize))
    g.add_node("aggregator", aggregate)

    # Agents SÉQUENTIELS pour respecter la limite 6000 tokens/min de Groq 8B.
    # Le parallèle envoyait les 3 prompts dans la même minute -> 429.
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grader")
    g.add_edge("grader", "reasoner")
    g.add_edge("reasoner", "critic")
    g.add_edge("critic", "aggregator")
    g.add_edge("aggregator", END)

    return g.compile()


def evaluate_answer(question: str, expected_answer: str, key_points: list[str],
                    rubric: list[dict], candidate_answer: str,
                    service: str = "") -> dict:
    """Point d'entrée : évalue une réponse de candidat, retourne le rapport."""
    # Controle de couverture : une non-reponse est traitee sans appel LLM,
    # ce qui garantit un score stable et evite un jugement arbitraire.
    from agents.coverage import is_non_answer, zero_result
    empty, reason = is_non_answer(candidate_answer)
    if empty:
        return zero_result(reason)

    graph = build_evaluation_graph()
    initial: EvaluationState = {
        "question": question,
        "expected_answer": expected_answer,
        "key_points": key_points,
        "rubric": rubric,
        "candidate_answer": candidate_answer,
        "service": service,
    }
    return graph.invoke(initial)
