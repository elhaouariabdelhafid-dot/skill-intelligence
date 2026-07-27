"""Phase 4 — Agent Critic-Verifier.

RÔLE : chercher activement les PROBLÈMES — hallucinations, contradictions
internes, affirmations inventées non présentes dans le corpus. C'est le
garde-fou : là où le Grader et le Reasoner notent la qualité, le Critic
cherche ce qui cloche.

POURQUOI un veto : si le Critic détecte une hallucination MAJEURE (le candidat
invente un service, une limite, un comportement qui n'existe pas), cela doit
peser lourd — une réponse dangereuse ne doit pas passer parce qu'elle est bien
écrite. L'aggregator applique ce veto.

SORTIE : un score de "gravité des problèmes" (0=aucun, 4=graves) + les alertes.
Attention : ici un score BAS = BON (peu de problèmes). L'aggregator inverse.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.state import AgentResult, EvaluationState
from llm.client import json_with_backoff

from pydantic import BaseModel, Field


class CriticOutput(BaseModel):
    problem_severity: int = Field(ge=0, le=4,
        description="0=aucun problème, 4=hallucinations graves")
    hallucinations: list[str] = Field(description="Affirmations inventées / non soutenues")
    contradictions: list[str] = Field(description="Incohérences internes")
    has_major_hallucination: bool = Field(
        description="True si une erreur invalide dangereusement la réponse")


CRITIC_SYSTEM = """You are a rigorous verifier. Your job is to find problems in the
candidate's answer: hallucinations (invented services, limits, or behaviors not in
the documentation), internal contradictions, and unsupported claims. Be skeptical.
Compare every technical claim to the provided context."""


def criticize(state: EvaluationState) -> dict:
    """Nœud LangGraph : détecte hallucinations et contradictions."""
    prompt = f"""Find problems in the candidate's answer by comparing it to the documentation.

QUESTION: {state['question']}

DOCUMENTATION CONTEXT (source of truth):
{state['context']}

CANDIDATE'S ANSWER:
{state['candidate_answer']}

Identify:
- hallucinations: claims about AWS not supported by the context (invented limits,
  services, behaviors)
- contradictions: internal inconsistencies in the answer
- problem_severity 0-4: 0=no problems, 4=severe hallucinations that make the
  answer dangerous or fundamentally wrong
- has_major_hallucination: true only if an error would seriously mislead"""

    try:
        out = json_with_backoff(prompt, CriticOutput, system=CRITIC_SYSTEM,
                           temperature=0.1)
    except RuntimeError:
        return {"critic": AgentResult(score=0.0,
                                      justification="Vérification indisponible (erreur LLM)",
                                      citations=[])}

    problems = []
    if out.hallucinations:
        problems.append("Hallucinations : " + "; ".join(out.hallucinations))
    if out.contradictions:
        problems.append("Contradictions : " + "; ".join(out.contradictions))
    justification = " | ".join(problems) if problems else "Aucun problème détecté."

    # On stocke la sévérité dans score, et le flag de veto dans citations[0]
    return {"critic": AgentResult(
        score=float(out.problem_severity),
        justification=justification,
        citations=["MAJOR_HALLUCINATION"] if out.has_major_hallucination else [],
    )}
