"""Phase 6 — Notation humaine des réponses pour la validation humain/IA.

PRINCIPE : te présenter les réponses une par une SANS montrer le score de l'IA,
tu attribues ta note (0-4), le script stocke tes notes séparément. Ensuite,
human_correlation.py compare tes notes aux scores IA.

POURQUOI cacher le score IA : si tu le voyais, tu serais influencé (biais
d'ancrage). Une validation rigoureuse exige que l'humain note à l'aveugle.

Tes notes sont sauvegardées au fur et à mesure : tu peux t'arrêter et reprendre.

Usage :
    python evaluation/human_rating.py                 # noter toutes les réponses
    python evaluation/human_rating.py --annotator Aya # plusieurs annotateurs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.models import Evaluation, Submission, User, get_session

RATINGS_DIR = Path(__file__).parent / "human_ratings"


def load_all_submissions() -> list[dict]:
    """Charge toutes les réponses évaluées, avec le score IA (caché à l'affichage)."""
    s = get_session()
    rows = (s.query(Submission, Evaluation, User)
            .join(Evaluation, Evaluation.submission_id == Submission.id)
            .join(User, User.id == Submission.user_id)
            .order_by(Submission.id).all())
    data = [{
        "submission_id": sub.id,
        "user": user.name,
        "service": sub.service,
        "skill": sub.skill,
        "difficulty": sub.difficulty,
        "question_id": sub.question_id,
        "answer": sub.answer_text,
        "ia_score": ev.final_score,   # caché pendant la notation
    } for sub, ev, user in rows]
    s.close()
    return data


def load_questions() -> dict:
    qs = {}
    for line in Path("data/processed/questions_accepted.jsonl").open():
        if line.strip():
            q = json.loads(line)
            qs[q["question_id"]] = q
    return qs


def ratings_path(annotator: str) -> Path:
    RATINGS_DIR.mkdir(exist_ok=True)
    return RATINGS_DIR / f"ratings_{annotator}.json"


def load_existing(annotator: str) -> dict:
    p = ratings_path(annotator)
    return json.loads(p.read_text()) if p.exists() else {}


def save_ratings(annotator: str, ratings: dict):
    ratings_path(annotator).write_text(json.dumps(ratings, indent=2))


def rate(annotator: str):
    subs = load_all_submissions()
    questions = load_questions()
    ratings = load_existing(annotator)

    todo = [s for s in subs if str(s["submission_id"]) not in ratings]
    print(f"\n{'='*60}")
    print(f"NOTATION HUMAINE — annotateur : {annotator}")
    print(f"{'='*60}")
    print(f"Total : {len(subs)} réponses | Déjà notées : {len(ratings)} | "
          f"À noter : {len(todo)}")
    print("\nÉchelle : 0=faux/vide, 1=très faible, 2=partiel, 3=bon, 4=excellent")
    print("Tape ton score (0-4), 's' pour sauter, 'q' pour quitter.\n")

    for i, sub in enumerate(todo, 1):
        q = questions.get(sub["question_id"], {})
        print(f"\n{'─'*60}")
        print(f"[{i}/{len(todo)}] {sub['user']} · {sub['service']} · {sub['difficulty']}")
        print(f"\nQUESTION : {q.get('question', '(question introuvable)')}")
        print(f"\nRÉPONSE ATTENDUE : {q.get('expected_answer', '')[:250]}")
        print(f"\n>>> RÉPONSE DU CANDIDAT :")
        print(f"    {sub['answer'][:500]}")
        print()

        while True:
            choice = input("Ta note (0-4 / s / q) : ").strip().lower()
            if choice == "q":
                save_ratings(annotator, ratings)
                print(f"\nSauvegardé. {len(ratings)} notes. Relance pour continuer.")
                return
            if choice == "s":
                break
            if choice in {"0", "1", "2", "3", "4"}:
                ratings[str(sub["submission_id"])] = {
                    "human_score": int(choice),
                    "ia_score": sub["ia_score"],
                    "user": sub["user"],
                    "service": sub["service"],
                }
                save_ratings(annotator, ratings)
                break
            print("  Entrée invalide. Tape 0, 1, 2, 3, 4, s ou q.")

    print(f"\n{'='*60}")
    print(f"Terminé ! {len(ratings)} réponses notées.")
    print(f"Calcule la corrélation : python evaluation/human_correlation.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotator", default="hafid")
    args = parser.parse_args()
    rate(args.annotator)
