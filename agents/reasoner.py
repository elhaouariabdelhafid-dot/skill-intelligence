"""Phase 4 — Agent Reasoning Evaluator.

RÔLE : juger la QUALITÉ DU RAISONNEMENT, indépendamment de l'exactitude factuelle
(qui est le travail du Grader). Une réponse peut être factuellement correcte mais
mal raisonnée, ou l'inverse. Cet agent évalue : la logique est-elle cohérente ?
la démarche est-elle structurée ? la solution proposée est-elle pertinente ?

POURQUOI c'est séparé du Grader : sur tes questions 'analyze'/'apply' (la majorité
de ta banque), le raisonnement est justement ce qui compte. Un candidat peut citer
les bons faits sans savoir les articuler pour résoudre le problème posé.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.state import AgentResult, EvaluationState
from llm.client import json_with_backoff

from pydantic import BaseModel, Field


class ReasonerOutput(BaseModel):
    score: int = Field(ge=0, le=4)
    logic_quality: str = Field(description="Évaluation de la cohérence logique")
    structure_quality: str = Field(description="Évaluation de la structure/démarche")
    justification: str = Field(description="Synthèse du jugement sur le raisonnement")


REASONER_SYSTEM = """You evaluate the QUALITY OF REASONING in a candidate's answer,
not its factual accuracy. You assess: logical coherence, structured approach,
relevance of the proposed solution to the problem, and depth of analysis. A
factually correct but poorly reasoned answer should score low here."""


def reason(state: EvaluationState) -> dict:
    """Nœud LangGraph : évalue le raisonnement."""
    prompt = f"""Evaluate the QUALITY OF REASONING in the candidate's answer.

QUESTION: {state['question']}

WHAT A STRONG ANSWER SHOULD COVER: {state['key_points']}

CANDIDATE'S ANSWER:
{state['candidate_answer']}

Judge ONLY the reasoning, not factual accuracy:
- 4: clear logic, well-structured, addresses the problem thoroughly
- 3: sound reasoning, minor gaps
- 2: some logic but incomplete or partly off-track
- 1: weak or confused reasoning
- 0: no coherent reasoning

Assess logical coherence and structure separately, then give an overall score."""

    try:
        out = json_with_backoff(prompt, ReasonerOutput, system=REASONER_SYSTEM,
                           temperature=0.2)
    except RuntimeError:
        return {"reasoner": AgentResult(score=2.0,
                                        justification="Évaluation indisponible (erreur LLM)",
                                        citations=[])}

    justification = (f"{out.justification} | Logique : {out.logic_quality} | "
                     f"Structure : {out.structure_quality}")
    return {"reasoner": AgentResult(
        score=float(out.score), justification=justification, citations=[])}
