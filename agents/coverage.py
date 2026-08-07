"""Controle de couverture — detecte les non-reponses avant tout appel LLM.

POURQUOI EN AMONT : un LLM face a une reponse vide n'a rien a evaluer, il
produit alors une note instable (0, 2, parfois 3 pour un contenu identique).
Une regle deterministe garantit le meme resultat a chaque fois, sans cout ni
latence.

CE QUI N'EST PAS UN CRITERE : la longueur. Une reponse breve mais exacte
("DescribeDBInstances") doit garder un bon score. Seule compte l'absence de
contenu repondant a la question.
"""
from __future__ import annotations

import re
import unicodedata

# Formulations d'abandon explicites, francais et anglais.
ABANDON = [
    "je ne sais pas", "je sais pas", "jsp", "aucune idee", "aucune idée",
    "pas de reponse", "pas de réponse", "sans reponse", "sans réponse",
    "je ne connais pas", "je connais pas", "rien a dire", "rien à dire",
    "i do not know", "i don't know", "idk", "no idea", "no answer",
    "not sure", "no clue", "cannot answer", "can't answer",
]

# Reponses vides de sens meme si non explicites.
FILLER = {"rien", "nothing", "none", "na", "n", "a", "-", "?", "??", "...",
          "x", "xx", "test", "aucun", "aucune", "vide", "empty", "skip",
          "nada", "nan", "non", "no", "oui", "yes", "ok"}


def _normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces normalises."""
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_non_answer(answer: str) -> tuple[bool, str]:
    """Retourne (True, motif) si la reponse n'apporte aucun contenu.

    Trois cas traites :
      - chaine vide ou espaces seuls
      - mot de remplissage isole ("rien", "?", "n/a")
      - formulation d'abandon, seule ou dominante dans le texte
    """
    raw = (answer or "").strip()
    if not raw:
        return True, "Reponse vide."

    norm = _normalize(raw)
    if not norm:
        return True, "Reponse sans contenu textuel."

    words = norm.split()
    if len(words) <= 3 and all(w in FILLER for w in words):
        return True, "Reponse sans contenu (mot de remplissage)."

    for phrase in ABANDON:
        p = _normalize(phrase)
        if norm == p:
            return True, "Le candidat declare ne pas savoir."
        # Formulation d'abandon qui occupe l'essentiel du texte
        if p in norm and len(norm) <= len(p) + 25:
            return True, "Le candidat declare ne pas savoir."

    return False, ""


def zero_result(reason: str) -> dict:
    """Construit un resultat d'evaluation a zero, coherent avec le format agents."""
    return {
        "grader": {"score": 0.0, "justification": reason, "citations": []},
        "reasoner": {"score": 0.0, "justification": "Aucun raisonnement a evaluer.",
                     "citations": []},
        "critic": {"score": 0.0, "justification": "Aucune affirmation a verifier.",
                   "citations": []},
        "final_score": 0.0,
        "feedback": f"Score final : 0.0/4. {reason} "
                    "Aucun element de reponse n'a pu etre evalue.",
        "strengths": [],
        "weaknesses": [reason],
        "skipped_llm": True,
    }
