"""Phase 3 — Génération synthétique de questions ancrées sur les chunks.

PRINCIPE : chaque question naît d'un chunk réel du corpus. C'est ce qui garantit
(1) qu'elle est vérifiable, (2) qu'elle est spécifique au corpus donc peu
"googlable", (3) qu'on peut citer la source lors de l'évaluation.

STRATÉGIE D'ÉCHANTILLONNAGE : on ne prend pas des chunks au hasard. On
sélectionne les chunks les plus DENSES en information technique (heuristique :
présence de termes AWS, longueur, structure). Un chunk de navigation ou
d'introduction produit une question creuse.

Usage :
    python generation/question_gen.py --n 20 --service IAM
    python generation/question_gen.py --n 200                 # tous services
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_DIR
from generation.schemas import (BloomLevel, Difficulty, GeneratedQuestion,
                                StoredQuestion)
from ingestion.chunking import Chunk, load_chunks
from llm.client import complete_json

from tqdm import tqdm

CANDIDATES_PATH = PROCESSED_DIR / "questions_candidates.jsonl"

# Termes signalant un contenu technique exploitable
TECH_MARKERS = re.compile(
    r"\b(policy|policies|encryption|IAM|VPC|subnet|gateway|bucket|instance|"
    r"volume|latency|throughput|IOPS|availability|failover|replica|snapshot|"
    r"permission|role|principal|endpoint|throttl|quota|limit|scaling|"
    r"stateful|stateless|ephemeral|durability|consistency|timeout|"
    r"concurrency|cold start|multi-AZ|cross-region)\b", re.IGNORECASE)

SYSTEM_PROMPT = """You are a senior AWS solutions architect who designs technical
assessments for cloud engineers. You write questions that test understanding and
reasoning, never simple recall of marketing text."""

BLOOM_INSTRUCTIONS = {
    BloomLevel.REMEMBER: (
        "Ask for a precise technical fact, limit, or definition that an engineer "
        "must know. Short answer expected."),
    BloomLevel.APPLY: (
        "Describe a concrete, realistic scenario and ask the candidate to apply "
        "the concept to solve it. The answer requires choosing and justifying an "
        "approach."),
    BloomLevel.ANALYZE: (
        "Present a situation with a trade-off, a failure, or two competing "
        "options. Ask the candidate to diagnose, compare, or justify a decision. "
        "There must be no single obvious answer."),
}


def _density_score(chunk: Chunk) -> float:
    """Heuristique de richesse technique d'un chunk."""
    n_markers = len(TECH_MARKERS.findall(chunk.text))
    length_factor = min(len(chunk.text) / 2000, 1.0)
    # Pénalise les chunks trop listés (sommaires, tables de matières)
    bullet_ratio = chunk.text.count("\n-") / max(chunk.text.count("\n"), 1)
    penalty = 0.5 if bullet_ratio > 0.5 else 1.0
    return n_markers * length_factor * penalty


def select_chunks(n: int, service: str | None = None,
                  seed: int = 42) -> list[Chunk]:
    """Sélectionne n chunks riches, équilibrés entre services."""
    chunks = load_chunks()
    if service:
        chunks = [c for c in chunks if c.service.lower() == service.lower()]
    if not chunks:
        raise RuntimeError(f"Aucun chunk pour service={service}")

    scored = [(c, _density_score(c)) for c in chunks]
    scored = [(c, s) for c, s in scored if s >= 3.0]  # seuil de richesse
    scored.sort(key=lambda x: x[1], reverse=True)

    # Répartition équilibrée par service : évite 180 questions sur EC2
    by_service: dict[str, list[Chunk]] = defaultdict(list)
    for c, _ in scored:
        by_service[c.service].append(c)

    rng = random.Random(seed)
    selected: list[Chunk] = []
    services = sorted(by_service)
    per_service = max(n // max(len(services), 1), 1)
    for svc in services:
        pool = by_service[svc][:per_service * 4]   # top candidats du service
        rng.shuffle(pool)
        selected.extend(pool[:per_service])
    rng.shuffle(selected)
    return selected[:n]


def _build_prompt(chunk: Chunk, bloom: BloomLevel, difficulty: Difficulty) -> str:
    return f"""Generate ONE assessment question from the AWS documentation excerpt below.

EXCERPT (service: {chunk.service}, section: {chunk.section}):
\"\"\"
{chunk.text[:3500]}
\"\"\"

REQUIREMENTS:
- Cognitive level: {bloom.value.upper()}. {BLOOM_INSTRUCTIONS[bloom]}
- Target difficulty: {difficulty.value}
- The question must be SELF-CONTAINED: never refer to "the document", "the text",
  "the excerpt" or "the context". The candidate will NOT see this excerpt.
- The answer must be verifiable from the excerpt content.
- expected_answer: a complete reference answer, 3 to 8 sentences.
- key_points: 2 to 5 factual points the answer must contain.
- skill: a short skill label, e.g. "VPC network isolation", "IAM policy evaluation".
- rubric: 2 to 4 criteria, weights summing to 1.0, each with descriptors for
  score 0 and score 4.

Write the question in English."""


def generate_from_chunk(chunk: Chunk, bloom: BloomLevel,
                        difficulty: Difficulty) -> StoredQuestion | None:
    try:
        gen = complete_json(
            _build_prompt(chunk, bloom, difficulty),
            GeneratedQuestion,
            system=SYSTEM_PROMPT,
            temperature=0.6,          # diversité voulue en génération
        )
    except (RuntimeError, ValueError):
        return None

    qid = hashlib.sha1(gen.question.encode()).hexdigest()[:16]
    return StoredQuestion(
        question_id=qid,
        question=gen.question,
        expected_answer=gen.expected_answer,
        key_points=gen.key_points,
        bloom_level=gen.bloom_level,
        difficulty=gen.difficulty,
        skill=gen.skill,
        rubric=gen.rubric,
        source_chunk_ids=[chunk.chunk_id],
        service=chunk.service,
        category=chunk.category,
        source_files=[chunk.source_file],
    )


# Répartition cible : plus d'APPLY/ANALYZE que de REMEMBER, car ce sont eux
# qui justifient l'évaluation multi-agents.
BLOOM_MIX = ([BloomLevel.REMEMBER] * 2 + [BloomLevel.APPLY] * 4
             + [BloomLevel.ANALYZE] * 4)
DIFFICULTY_BY_BLOOM = {
    BloomLevel.REMEMBER: Difficulty.BEGINNER,
    BloomLevel.APPLY: Difficulty.INTERMEDIATE,
    BloomLevel.ANALYZE: Difficulty.ADVANCED,
}


def generate_batch(n: int, service: str | None = None,
                   seed: int = 42) -> list[StoredQuestion]:
    chunks = select_chunks(n, service=service, seed=seed)
    rng = random.Random(seed)
    out: list[StoredQuestion] = []
    failures = 0

    for chunk in tqdm(chunks, desc="Génération"):
        bloom = rng.choice(BLOOM_MIX)
        q = generate_from_chunk(chunk, bloom, DIFFICULTY_BY_BLOOM[bloom])
        if q is None:
            failures += 1
            continue
        out.append(q)

    print(f"\nGénérées : {len(out)} / {len(chunks)} "
          f"(échecs de format : {failures})")
    return out


def save_candidates(questions: list[StoredQuestion],
                    path: Path = CANDIDATES_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(q.model_dump_json() + "\n")
    return path


def load_candidates(path: Path = CANDIDATES_PATH) -> list[StoredQuestion]:
    with path.open(encoding="utf-8") as f:
        return [StoredQuestion.model_validate_json(line) for line in f if line.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--service", default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    questions = generate_batch(args.n, service=args.service, seed=args.seed)
    out = save_candidates(questions)
    print(f"Écrit : {out}")

    if questions:
        q = questions[0]
        print("\n--- Exemple ---")
        print(f"[{q.service} / {q.bloom_level.value} / {q.difficulty.value}]")
        print(f"Q: {q.question}")
        print(f"Skill: {q.skill}")
        print(f"Key points: {q.key_points}")
