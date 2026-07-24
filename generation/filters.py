"""Phase 3 — Filtrage qualité des questions générées.

C'EST LA PARTIE QUI COMPTE. Générer 200 questions est facile ; démontrer que
140 sont valides et expliquer pourquoi 60 ont été rejetées, c'est ton résultat
expérimental. Le taux de rejet est un critère de validation du cahier des
charges (< 30 %).

QUATRE FILTRES, du moins cher au plus cher :

  F1 STRUCTURE   (gratuit)   — longueurs, rubrique cohérente, poids = 1.0
  F2 DÉDUPLICATION (embeddings) — similarité cosinus entre questions
  F3 ANCRAGE     (retrieval) — la question est-elle retrouvable dans le corpus ?
  F4 AUTO-CRITIQUE (LLM)     — question ambiguë, triviale, ou mal posée ?

ORDRE VOLONTAIRE : chaque filtre élimine avant d'appeler le suivant, plus
coûteux. C'est le principe du cascade filtering.

Usage :
    python generation/filters.py                 # filtre les candidates
    python generation/filters.py --report        # rapport détaillé des rejets
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_DIR, settings
from generation.schemas import StoredQuestion
from llm.client import complete_json

CANDIDATES_PATH = PROCESSED_DIR / "questions_candidates.jsonl"


def load_candidates(path: Path = CANDIDATES_PATH) -> list[StoredQuestion]:
    with path.open(encoding="utf-8") as f:
        return [StoredQuestion.model_validate_json(l) for l in f if l.strip()]

import numpy as np
from pydantic import BaseModel, Field
from tqdm import tqdm

ACCEPTED_PATH = PROCESSED_DIR / "questions_accepted.jsonl"
REPORT_PATH = PROCESSED_DIR / "filtering_report.json"

# Seuils — à justifier dans le rapport, ajustables après observation
SIM_THRESHOLD = 0.90          # au-delà : questions quasi-identiques
GROUNDING_THRESHOLD = 0.35    # score de rerank minimal du chunk source
MIN_QUESTION_WORDS = 8
MAX_QUESTION_WORDS = 120


# ==========================================================================
# F1 — Structure
# ==========================================================================
def filter_structure(q: StoredQuestion) -> str | None:
    """Retourne la raison du rejet, ou None si la question passe."""
    words = len(q.question.split())
    if words < MIN_QUESTION_WORDS:
        return "question_too_short"
    if words > MAX_QUESTION_WORDS:
        return "question_too_long"
    if len(q.expected_answer.split()) < 20:
        return "answer_too_short"

    total_weight = sum(c.weight for c in q.rubric)
    if not (0.95 <= total_weight <= 1.05):
        return f"rubric_weights_invalid ({total_weight:.2f})"

    if any(len(c.descriptor_0) < 10 or len(c.descriptor_4) < 10 for c in q.rubric):
        return "rubric_descriptors_empty"

    # Une question qui contient déjà sa réponse est inutile
    answer_start = q.expected_answer[:60].lower()
    if answer_start and answer_start in q.question.lower():
        return "answer_leaked_in_question"

    return None


# ==========================================================================
# F2 — Déduplication sémantique
# ==========================================================================
def filter_duplicates(questions: list[StoredQuestion]
                      ) -> dict[str, tuple[str, float]]:
    """Retourne {question_id: (raison, similarité)} pour les doublons.

    POURQUOI : le LLM génère souvent la même question depuis deux chunks
    voisins. Sans ce filtre, ta banque est artificiellement grosse et ton
    évaluation biaisée (on teste deux fois la même chose).
    """
    from ingestion.embeddings import get_embedder

    if len(questions) < 2:
        return {}

    vectors = np.array(
        get_embedder().encode_documents([q.question for q in questions]))
    # Normalisation explicite : FastEmbed ne garantit pas des vecteurs unitaires
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    sim_matrix = vectors @ vectors.T
    np.fill_diagonal(sim_matrix, 0.0)

    rejected: dict[str, tuple[str, float]] = {}
    for i in range(len(questions)):
        if questions[i].question_id in rejected:
            continue
        for j in range(i + 1, len(questions)):
            if questions[j].question_id in rejected:
                continue
            sim = float(sim_matrix[i, j])
            if sim >= SIM_THRESHOLD:
                # On garde la première, on rejette la suivante
                rejected[questions[j].question_id] = ("duplicate", sim)
    # Enregistre la similarité max pour toutes (utile au rapport)
    for i, q in enumerate(questions):
        q.max_similarity = float(sim_matrix[i].max())
    return rejected


# ==========================================================================
# F3 — Ancrage dans le corpus
# ==========================================================================
def filter_grounding(q: StoredQuestion) -> tuple[str | None, float]:
    """Vérifie que le chunk source est bien retrouvé quand on cherche la question.

    POURQUOI : si la question ne permet pas de retrouver son propre chunk
    d'origine, elle est soit trop vague, soit hors corpus — donc inévaluable
    par les agents en Phase 4, qui s'appuient sur le retrieval.
    """
    from retrieval.reranker import retrieve_final

    hits = retrieve_final(q.question, top_k=5)
    if not hits:
        return "no_retrieval", 0.0

    source_ids = set(q.source_chunk_ids)
    for hit in hits:
        if hit.chunk_id in source_ids:
            score = float(hit.score)
            if score < GROUNDING_THRESHOLD:
                return "weak_grounding", score
            return None, score

    # Le chunk source n'est pas dans le top-5 : la question a dérivé
    return "source_not_retrieved", float(hits[0].score)


# ==========================================================================
# F4 — Auto-critique par LLM
# ==========================================================================
class QuestionCritique(BaseModel):
    is_self_contained: bool = Field(
        description="True if answerable without seeing any source document")
    is_unambiguous: bool = Field(
        description="True if the question has a clear, determinate scope")
    is_non_trivial: bool = Field(
        description="False if answerable by pure common sense without AWS knowledge")
    matches_difficulty: bool = Field(
        description="True if the stated difficulty level matches the question")
    verdict: str = Field(description="'accept' or 'reject'")
    reason: str = Field(description="One short sentence justifying the verdict")


CRITIQUE_SYSTEM = """You are a strict reviewer of technical assessment questions.
You reject questions that are ambiguous, trivial, self-referential, or whose
reference answer does not actually answer the question."""


def filter_critique(q: StoredQuestion) -> tuple[str | None, dict]:
    prompt = f"""Review this AWS assessment question.

QUESTION: {q.question}
STATED DIFFICULTY: {q.difficulty.value}
STATED COGNITIVE LEVEL: {q.bloom_level.value}
REFERENCE ANSWER: {q.expected_answer}
KEY POINTS: {json.dumps(q.key_points)}

Reject if any of these holds:
- the question refers to a document, text, excerpt or context the candidate cannot see
- the question is ambiguous or its scope is undefined
- it can be answered without any AWS-specific knowledge
- the reference answer does not actually answer the question
- the difficulty label is clearly wrong"""

    try:
        c = complete_json(prompt, QuestionCritique, system=CRITIQUE_SYSTEM,
                          temperature=0.1)
    except RuntimeError:
        return None, {"critique": "skipped_llm_error"}   # bénéfice du doute

    details = c.model_dump()
    if c.verdict.lower().startswith("reject"):
        return f"llm_critique: {c.reason[:80]}", details
    if not c.is_self_contained:
        return "not_self_contained", details
    if not c.is_unambiguous:
        return "ambiguous", details
    if not c.is_non_trivial:
        return "trivial", details
    return None, details


# ==========================================================================
# Pipeline complet
# ==========================================================================
def run_filters(questions: list[StoredQuestion], use_llm: bool = True
                ) -> tuple[list[StoredQuestion], list[StoredQuestion], dict]:
    stats = Counter()
    rejected: list[StoredQuestion] = []
    survivors: list[StoredQuestion] = []

    # --- F1 structure
    for q in questions:
        reason = filter_structure(q)
        if reason:
            q.status, q.rejection_reason = "rejected", f"F1:{reason}"
            stats[f"F1:{reason.split(' ')[0]}"] += 1
            rejected.append(q)
        else:
            survivors.append(q)
    print(f"F1 structure      : {len(survivors)} restants")

    # --- F2 déduplication
    dupes = filter_duplicates(survivors)
    kept: list[StoredQuestion] = []
    for q in survivors:
        if q.question_id in dupes:
            _, sim = dupes[q.question_id]
            q.status, q.rejection_reason = "rejected", f"F2:duplicate(sim={sim:.3f})"
            stats["F2:duplicate"] += 1
            rejected.append(q)
        else:
            kept.append(q)
    survivors = kept
    print(f"F2 déduplication  : {len(survivors)} restants")

    # --- F3 ancrage
    kept = []
    for q in tqdm(survivors, desc="F3 ancrage"):
        reason, score = filter_grounding(q)
        q.grounding_score = score
        if reason:
            q.status, q.rejection_reason = "rejected", f"F3:{reason}"
            stats[f"F3:{reason}"] += 1
            rejected.append(q)
        else:
            kept.append(q)
    survivors = kept
    print(f"F3 ancrage        : {len(survivors)} restants")

    # --- F4 auto-critique
    if use_llm:
        kept = []
        for q in tqdm(survivors, desc="F4 critique LLM"):
            reason, _ = filter_critique(q)
            if reason:
                q.status, q.rejection_reason = "rejected", f"F4:{reason}"
                stats[f"F4:{reason.split(':')[0]}"] += 1
                rejected.append(q)
            else:
                kept.append(q)
        survivors = kept
        print(f"F4 critique LLM   : {len(survivors)} restants")

    for q in survivors:
        q.status = "accepted"

    total = len(questions)
    report = {
        "total_generated": total,
        "accepted": len(survivors),
        "rejected": len(rejected),
        "rejection_rate": round(len(rejected) / total, 4) if total else 0.0,
        "target_rejection_rate": 0.30,
        "by_reason": dict(stats.most_common()),
        "accepted_by_service": dict(Counter(q.service for q in survivors)),
        "accepted_by_bloom": dict(Counter(q.bloom_level.value for q in survivors)),
        "accepted_by_difficulty": dict(Counter(q.difficulty.value for q in survivors)),
        "mean_grounding_score": round(
            float(np.mean([q.grounding_score for q in survivors
                           if q.grounding_score is not None])), 4)
        if survivors else None,
    }
    return survivors, rejected, report


def save_accepted(questions: list[StoredQuestion],
                  path: Path = ACCEPTED_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(q.model_dump_json() + "\n")
    return path


def load_accepted(path: Path = ACCEPTED_PATH) -> list[StoredQuestion]:
    with path.open(encoding="utf-8") as f:
        return [StoredQuestion.model_validate_json(l) for l in f if l.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true",
                        help="Sauter F4 (rapide, pour tester le pipeline)")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    candidates = load_candidates()
    print(f"Candidates chargées : {len(candidates)}\n")

    accepted, rejected, report = run_filters(candidates, use_llm=not args.no_llm)

    save_accepted(accepted)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    print("\n=== RAPPORT DE FILTRAGE ===")
    print(f"Générées  : {report['total_generated']}")
    print(f"Acceptées : {report['accepted']}")
    print(f"Rejetées  : {report['rejected']} "
          f"({report['rejection_rate']*100:.1f} % — cible < 30 %)")
    print("\nMotifs de rejet :")
    for reason, n in report["by_reason"].items():
        print(f"  {reason:<32} {n:>4}")
    print(f"\nÉcrit : {ACCEPTED_PATH}")

    if args.report:
        print("\nRejets détaillés :")
        for q in rejected[:20]:
            print(f"  [{q.rejection_reason}] {q.question[:70]}...")
