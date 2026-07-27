"""Phase 4 — État partagé du graphe d'évaluation (LangGraph).

POURQUOI un état partagé : dans LangGraph, chaque agent est un nœud qui lit et
écrit dans un état commun (un TypedDict). Le Grader écrit son score, le Reasoner
le sien, l'Aggregator lit les trois. L'état est le "tableau blanc" que tous les
agents se partagent.

POURQUOI TypedDict et pas une classe : LangGraph attend un dict typé qu'il peut
fusionner automatiquement entre les nœuds parallèles. Chaque agent ne remplit
que SA case, LangGraph combine.
"""
from __future__ import annotations

from typing import TypedDict


class AgentResult(TypedDict):
    """Sortie standardisée d'un agent évaluateur."""
    score: float                 # 0 à 4
    justification: str
    citations: list[str]         # chunk_ids ou références utilisées


class EvaluationState(TypedDict, total=False):
    """État circulant dans le graphe d'évaluation.

    total=False : tous les champs ne sont pas présents dès le départ.
    Le contexte est rempli par retrieve_context, puis chaque agent ajoute
    sa clé, enfin l'aggregator produit le résultat final.
    """
    # Entrées (fournies au lancement)
    question: str
    expected_answer: str
    key_points: list[str]
    rubric: list[dict]
    candidate_answer: str
    service: str

    # Rempli par le nœud de retrieval
    context: str                 # chunks concaténés, prêts pour les prompts
    context_chunk_ids: list[str]

    # Rempli par chaque agent
    grader: AgentResult
    reasoner: AgentResult
    critic: AgentResult

    # Rempli par l'aggregator
    final_score: float
    feedback: str
    strengths: list[str]
    weaknesses: list[str]
