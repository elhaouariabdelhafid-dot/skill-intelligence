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
from agents.failures import EvaluationFailed
from llm.client import json_with_backoff

from pydantic import BaseModel, Field


class CriticOutput(BaseModel):
    problem_severity: int = Field(ge=0, le=4,
        description="0=aucun problème, 4=hallucinations graves")
    hallucinations: list[str] = Field(description="Affirmations inventées / non soutenues")
    contradictions: list[str] = Field(description="Incohérences internes")
    has_major_hallucination: bool = Field(
        description="True si une erreur invalide dangereusement la réponse")


CRITIC_SYSTEM = """You check AWS answers for invented facts.
You report only what you actually find. When you find nothing, you return empty lists and severity 0.
You never repeat the instructions back — you write findings, or nothing."""



def _is_echo(item: str) -> bool:
    """Detecte un element de liste qui reprend la consigne au lieu d'un constat."""
    low = (item or "").lower()
    markers = ("do not exist", "does not exist", "contradict the context",
               "list those", "empty list", "api operations or limits",
               "aws services, features")
    return any(m in low for m in markers)

def criticize(state: EvaluationState) -> dict:
    """Nœud LangGraph : détecte hallucinations et contradictions."""
    prompt = f"""QUESTION: {state['question']}

REFERENCE ANSWER: {state['expected_answer']}

KEY POINTS: {state['key_points']}

DOCUMENTATION EXCERPT: {state['context']}

CANDIDATE'S ANSWER: {state['candidate_answer']}

Answer three questions about the candidate's answer.

1. Does it name any AWS service, feature or API that does not exist?
   List those names in `hallucinations`. Nothing invented -> empty list.
   Anything appearing in the reference answer or the key points is real:
   never list it.

2. Does it contradict itself, or contradict the excerpt?
   List those statements in `contradictions`. None -> empty list.

3. How serious is what you found?
   0 = nothing invented, nothing contradicted (usual case)
   1 = minor claims beyond the excerpt
   2 = contradicts the excerpt
   3 = invented API operation or parameter
   4 = invented service, or dangerous advice

Being absent from the excerpt is not a problem: the excerpt is partial.
A correct answer normally scores 0.

Example when nothing is wrong:
{{"problem_severity": 0, "hallucinations": [], "contradictions": [], "has_major_hallucination": false}}

Write findings only. Never copy this instruction text into the lists."""

    try:
        out = json_with_backoff(prompt, CriticOutput, system=CRITIC_SYSTEM,
                           temperature=0.1)
    except RuntimeError as exc:
        # Un echec ne doit pas passer pour "aucun probleme" : on le signale
        # pour que la reponse reste non evaluee et relancable.
        from agents.failures import EvaluationFailed
        raise EvaluationFailed(f"Agent Critic indisponible : {exc}") from exc

    # Un modele de petite taille recopie parfois la consigne dans les
    # listes. Ces elements ne sont pas des constats : on les ecarte.
    out.hallucinations = [h for h in (out.hallucinations or [])
                          if h and not _is_echo(h)]
    out.contradictions = [c for c in (out.contradictions or [])
                          if c and not _is_echo(c)]

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
