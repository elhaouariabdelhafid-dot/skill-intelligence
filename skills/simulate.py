"""Phase 5 — Simulation de collaborateurs pour tester le profil.

POURQUOI simuler : pour construire un profil, il faut un collaborateur qui a
répondu à plusieurs questions et été évalué. Plutôt que d'attendre de vrais
utilisateurs, on simule 3 profils types (fort / moyen / faible) en fabriquant
des réponses de qualité contrôlée, on les évalue avec les agents (Phase 4), et
on stocke tout en base. Le profil et les recommandations se calculent ensuite
sur ces données réelles.

Usage :
    python skills/simulate.py --user-name "Alice" --level strong --n 8
    python skills/simulate.py --user-name "Bob" --level mixed --n 10
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.graph import evaluate_answer
from db.models import Evaluation, Submission, User, get_session

ACCEPTED = Path("data/processed/questions_accepted.jsonl")


def load_questions() -> list[dict]:
    return [json.loads(l) for l in ACCEPTED.open() if l.strip()]


def make_answer(q: dict, level: str, rng: random.Random) -> str:
    """Fabrique une réponse de qualité selon le niveau visé."""
    ref = q["expected_answer"]
    if level == "strong":
        return ref
    if level == "weak":
        return ("I think AWS handles most of this automatically. "
                "You just enable the default settings and it works.")
    if level == "mixed":
        # Aléatoire : parfois bon, parfois faible -> profil réaliste
        roll = rng.random()
        if roll > 0.6:
            return ref
        if roll > 0.3:
            return ref[:len(ref) // 2]  # partiel
        return "This is managed by AWS defaults, no special configuration needed."
    raise ValueError(level)


def simulate_user(name: str, level: str, n: int, seed: int = 42) -> int:
    questions = load_questions()
    rng = random.Random(seed)
    rng.shuffle(questions)
    questions = questions[:n]

    session = get_session()
    user = User(name=name, role="collaborator")
    session.add(user)
    session.commit()
    user_id = user.id
    print(f"Collaborateur créé : {name} (id={user_id}), niveau simulé={level}")

    for i, q in enumerate(questions, 1):
        answer = make_answer(q, level, rng)
        print(f"  [{i}/{len(questions)}] {q['skill'][:40]} — évaluation...")

        result = evaluate_answer(
            question=q["question"], expected_answer=q["expected_answer"],
            key_points=q["key_points"], rubric=q["rubric"],
            candidate_answer=answer, service=q["service"])

        sub = Submission(user_id=user_id, question_id=q["question_id"],
                         skill=q["skill"], service=q["service"],
                         bloom_level=q["bloom_level"], difficulty=q["difficulty"],
                         answer_text=answer)
        session.add(sub)
        session.commit()

        ev = Evaluation(
            submission_id=sub.id,
            grader_score=result["grader"]["score"],
            reasoner_score=result["reasoner"]["score"],
            critic_score=result["critic"]["score"],
            final_score=result["final_score"],
            feedback=result["feedback"],
            details={"strengths": result.get("strengths", []),
                     "weaknesses": result.get("weaknesses", [])})
        session.add(ev)
        session.commit()

    session.close()
    print(f"\nSimulation terminée : {len(questions)} évaluations pour {name}.")
    return user_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-name", default="TestUser")
    parser.add_argument("--level", choices=["strong", "weak", "mixed"],
                        default="mixed")
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    uid = simulate_user(args.user_name, args.level, args.n, args.seed)
    print(f"\nProchaine étape :")
    print(f"  python skills/profile.py --user {uid}")
    print(f"  python skills/recommendations.py --user {uid}")
