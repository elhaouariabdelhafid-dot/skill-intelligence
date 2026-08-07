"""Importe les réponses Google Forms (CSV) et les évalue avec les agents.

Google Forms exporte un CSV où chaque LIGNE = un répondant, chaque COLONNE = une
question. Ce script : (1) lit ce CSV, (2) relie chaque colonne à une question via
son [question_id], (3) crée le collaborateur en base, (4) évalue chaque réponse
avec les 3 agents, (5) stocke tout. Ensuite profile.py et recommendations.py
fonctionnent normalement.

Usage :
    python import_forms.py --csv reponses.csv --name-column "Nom"
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agents.graph import evaluate_answer
from db.models import Evaluation, Submission, User, get_session

MAP_PATH = Path("data/processed/questions_mapping.csv")


def load_mapping() -> dict:
    """question_id -> métadonnées de la question."""
    mapping = {}
    with MAP_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mapping[row["question_id"]] = row
    return mapping


def load_full_questions() -> dict:
    """question_id -> question complète (avec expected_answer, rubric...)."""
    import json
    qs = {}
    for line in Path("data/processed/questions_accepted.jsonl").open():
        if line.strip():
            q = json.loads(line)
            qs[q["question_id"]] = q
    return qs


def extract_qid(column_header: str) -> str | None:
    """Trouve [Q-xxxx] ou [xxxxxxxx] dans l'entête de colonne."""
    m = re.search(r"\[([a-f0-9]{8,16})\]", column_header)
    return m.group(1) if m else None


def import_responses(csv_path: str, name_column: str):
    full_q = load_full_questions()
    session = get_session()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Relier chaque colonne à un question_id
        col_to_qid = {}
        for h in headers:
            qid = extract_qid(h)
            if qid and qid in full_q:
                col_to_qid[h] = qid
        print(f"{len(col_to_qid)} colonnes reliées à des questions")
        if not col_to_qid:
            print("ERREUR : aucune colonne ne contient de [question_id].")
            print("Vérifie que les titres de questions dans Forms commencent")
            print("bien par [xxxxxxxx] (voir questions_forms.txt).")
            return

        for row in reader:
            name = row.get(name_column, "").strip() or "Anonyme"
            user = User(name=name, role="collaborator")
            session.add(user); session.commit()
            print(f"\nCollaborateur : {name} (id={user.id})")

            for col, qid in col_to_qid.items():
                answer = (row.get(col) or "").strip()
                if not answer:
                    continue
                q = full_q[qid]
                print(f"  {q['service']} — évaluation...")
                result = evaluate_answer(
                    question=q["question"], expected_answer=q["expected_answer"],
                    key_points=q["key_points"], rubric=q["rubric"],
                    candidate_answer=answer, service=q["service"])

                sub = Submission(user_id=user.id, question_id=qid,
                                 skill=q["skill"], service=q["service"],
                                 bloom_level=q["bloom_level"],
                                 difficulty=q["difficulty"], answer_text=answer)
                session.add(sub); session.commit()

                ev = Evaluation(submission_id=sub.id,
                                grader_score=result["grader"]["score"],
                                reasoner_score=result["reasoner"]["score"],
                                critic_score=result["critic"]["score"],
                                final_score=result["final_score"],
                                feedback=result["feedback"],
                                details={"strengths": result.get("strengths", []),
                                         "weaknesses": result.get("weaknesses", [])})
                session.add(ev); session.commit()

    session.close()
    print("\nImport terminé. Vois les profils avec :")
    print("  python skills/profile.py --user <id>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--name-column", default="Nom")
    args = parser.parse_args()
    import_responses(args.csv, args.name_column)
