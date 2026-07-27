"""Phase 5 — Profil de compétences d'un collaborateur.

PRINCIPE : agréger toutes les évaluations d'un utilisateur en un profil
structuré. Une évaluation = une réponse à une question sur une compétence. Le
profil moyenne les scores PAR COMPÉTENCE et PAR SERVICE, sur une échelle 0-100%.

POURQUOI par compétence ET par service : le RH veut voir "IAM policy: 60%" (fin)
mais aussi "Security: 55%" (agrégé). Les deux vues servent à des décisions
différentes.

POURQUOI pondérer par difficulté : réussir une question 'advanced' vaut plus que
réussir une 'beginner'. Un profil qui ignore la difficulté surestime les niveaux.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.models import Evaluation, Submission, User, get_session

# Poids par niveau de difficulté (une réussite advanced compte plus)
DIFFICULTY_WEIGHT = {"beginner": 1.0, "intermediate": 1.5, "advanced": 2.0}


def compute_profile(user_id: int) -> dict:
    """Construit le profil de compétences d'un utilisateur depuis la base."""
    session = get_session()
    rows = (session.query(Submission, Evaluation)
            .join(Evaluation, Evaluation.submission_id == Submission.id)
            .filter(Submission.user_id == user_id)
            .all())
    session.close()

    if not rows:
        return {"user_id": user_id, "n_evaluations": 0, "skills": {},
                "services": {}, "overall": 0.0}

    # Accumulateurs pondérés
    skill_num, skill_den = defaultdict(float), defaultdict(float)
    svc_num, svc_den = defaultdict(float), defaultdict(float)
    total_num = total_den = 0.0

    for sub, ev in rows:
        w = DIFFICULTY_WEIGHT.get(sub.difficulty, 1.0)
        score_pct = (ev.final_score / 4.0) * 100  # 0-4 -> 0-100%

        skill_num[sub.skill] += score_pct * w
        skill_den[sub.skill] += w
        svc_num[sub.service] += score_pct * w
        svc_den[sub.service] += w
        total_num += score_pct * w
        total_den += w

    skills = {s: round(skill_num[s] / skill_den[s], 1) for s in skill_num}
    services = {s: round(svc_num[s] / svc_den[s], 1) for s in svc_num}
    overall = round(total_num / total_den, 1) if total_den else 0.0

    return {
        "user_id": user_id,
        "n_evaluations": len(rows),
        "overall": overall,
        "skills": dict(sorted(skills.items(), key=lambda x: x[1])),
        "services": dict(sorted(services.items(), key=lambda x: x[1])),
    }


def print_profile(profile: dict, user_name: str = "") -> None:
    print(f"\n{'='*55}")
    print(f"PROFIL DE COMPÉTENCES{' — ' + user_name if user_name else ''}")
    print(f"{'='*55}")
    print(f"Évaluations : {profile['n_evaluations']}")
    print(f"Niveau global : {profile['overall']}%\n")

    print("Par service (du plus faible au plus fort) :")
    for svc, score in profile["services"].items():
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        print(f"  {svc:<18} {bar} {score}%")

    print("\nPar compétence :")
    for skill, score in profile["skills"].items():
        print(f"  {skill:<35} {score}%")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=1)
    args = parser.parse_args()

    session = get_session()
    user = session.query(User).filter(User.id == args.user).first()
    name = user.name if user else f"User {args.user}"
    session.close()

    profile = compute_profile(args.user)
    print_profile(profile, name)
