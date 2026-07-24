"""Phase 3 — Schémas des questions générées.

POURQUOI un schéma strict : c'est le contrat entre la génération (Phase 3),
l'évaluation (Phase 4) et le profil de compétences (Phase 6). Une question
sans rubrique explicite est inévaluable ; une question sans chunk d'ancrage
est invérifiable. Le schéma rend ces oublis impossibles.

POURQUOI le niveau de Bloom : il justifie scientifiquement la difficulté.
En soutenance, "j'ai généré des questions faciles et difficiles" est faible ;
"j'ai ciblé les niveaux Remember/Apply/Analyze de la taxonomie de Bloom, et
mesuré que le score moyen décroît avec le niveau" est un résultat.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class BloomLevel(str, Enum):
    """Taxonomie de Bloom révisée, restreinte à 3 niveaux exploitables."""
    REMEMBER = "remember"    # restituer un fait
    APPLY = "apply"          # utiliser une notion dans un cas concret
    ANALYZE = "analyze"      # comparer, diagnostiquer, arbitrer


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RubricCriterion(BaseModel):
    """Un critère noté de 0 à 4, avec descripteurs des niveaux extrêmes.

    Les descripteurs sont indispensables : sans eux, deux agents (ou deux
    humains) ne notent pas la même chose, et ton Krippendorff alpha s'effondre.
    """
    name: str = Field(description="Nom court du critère, ex: 'Exactitude technique'")
    weight: float = Field(ge=0.0, le=1.0, description="Poids relatif dans la note")
    descriptor_0: str = Field(description="Ce qui caractérise une réponse à 0")
    descriptor_4: str = Field(description="Ce qui caractérise une réponse à 4")


class GeneratedQuestion(BaseModel):
    """Question produite par le LLM, avant filtrage."""
    question: str = Field(min_length=30, description="Énoncé complet, autoportant")
    expected_answer: str = Field(min_length=80,
                                 description="Réponse de référence détaillée")
    key_points: list[str] = Field(min_length=2, max_length=6,
                                  description="Points que la réponse doit couvrir")
    bloom_level: BloomLevel
    difficulty: Difficulty
    skill: str = Field(description="Compétence ciblée, ex: 'VPC Security'")
    rubric: list[RubricCriterion] = Field(min_length=2, max_length=4)

    @field_validator("question")
    @classmethod
    def no_meta_reference(cls, v: str) -> str:
        """PIÈGE FRÉQUENT : le LLM écrit 'According to the provided document...'
        La question doit être autoportante — le candidat n'a pas le document."""
        banned = ["according to the", "in the document", "based on the text",
                  "as mentioned above", "the passage", "the provided context"]
        low = v.lower()
        for b in banned:
            if b in low:
                raise ValueError(f"Question référence le contexte source : '{b}'")
        return v


class StoredQuestion(BaseModel):
    """Question enrichie des métadonnées de traçabilité, prête à stocker."""
    question_id: str
    question: str
    expected_answer: str
    key_points: list[str]
    bloom_level: BloomLevel
    difficulty: Difficulty
    skill: str
    rubric: list[RubricCriterion]

    # Traçabilité — indispensable pour l'Explainable AI et la vérification
    source_chunk_ids: list[str]
    service: str
    category: str
    source_files: list[str]

    # Résultats du filtrage (Phase 3)
    status: str = "candidate"        # candidate | accepted | rejected
    rejection_reason: str | None = None
    grounding_score: float | None = None
    max_similarity: float | None = None
