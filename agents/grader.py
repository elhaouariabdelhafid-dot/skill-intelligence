"""Phase 4 — Agent Retriever-Grader.

RÔLE : vérifier l'EXACTITUDE TECHNIQUE de la réponse du candidat par rapport au
corpus AWS. Il ne juge pas le style ni le raisonnement — seulement : "ce que le
candidat affirme est-il correct selon la documentation ?"

POURQUOI il s'appuie sur le contexte récupéré : c'est ce qui distingue ton
système d'un simple "demande à ChatGPT si c'est juste". Le Grader compare la
réponse à des sources RÉELLES du corpus, et cite lesquelles. C'est le fondement
de ton Explainable AI : chaque point de score est justifié par une source.

SORTIE : score 0-4, justification, citations (les chunks qui appuient le jugement).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.state import AgentResult, EvaluationState
from llm.client import json_with_backoff

from pydantic import BaseModel, Field


class GraderOutput(BaseModel):
    score: int = Field(ge=0, le=4,
                       description="0=entièrement faux, 4=techniquement exact et complet")
    justification: str = Field(description="Ce qui est correct/incorrect selon le corpus")
    correct_points: list[str] = Field(description="Affirmations exactes du candidat")
    incorrect_points: list[str] = Field(description="Affirmations fausses ou non soutenues")


GRADER_SYSTEM = """You are a strict AWS technical fact-checker. You evaluate ONLY
factual/technical accuracy against the provided documentation context. You do not
reward good writing or reasoning — only whether the claims are correct according
to the sources. If a claim is not supported by the context, treat it as unverified."""


def grade(state: EvaluationState) -> dict:
    """Nœud LangGraph : évalue l'exactitude technique."""
    prompt = f"""Evaluate the TECHNICAL ACCURACY of the candidate's answer against the AWS documentation.

QUESTION: {state['question']}

REFERENCE ANSWER (ground truth): {state['expected_answer']}

KEY POINTS the answer should cover: {state['key_points']}

DOCUMENTATION CONTEXT (the source of truth):
{state['context']}

CANDIDATE'S ANSWER:
{state['candidate_answer']}

Score 0-4 based ONLY on technical correctness:
- 4: all claims accurate and supported by the documentation
- 3: mostly accurate, minor imprecision
- 2: partially accurate, some errors
- 1: mostly inaccurate
- 0: entirely wrong or off-topic

List the correct and incorrect points explicitly."""

    try:
        out = json_with_backoff(prompt, GraderOutput, system=GRADER_SYSTEM,
                           temperature=0.1)
    except RuntimeError:
        # En cas d'échec LLM, score neutre plutôt que planter tout le graphe
        return {"grader": AgentResult(score=2.0,
                                      justification="Évaluation indisponible (erreur LLM)",
                                      citations=[])}

    justification = out.justification
    if out.incorrect_points:
        justification += " | Erreurs : " + "; ".join(out.incorrect_points)

    return {"grader": AgentResult(
        score=float(out.score),
        justification=justification,
        citations=state.get("context_chunk_ids", []),
    )}
