"""Retire les evaluations de test pour retrouver des profils presentables.

DEUX MODES :
  --auto   retire les reponses sans contenu (detectees par le meme controle
           que celui de la chaine d'evaluation) et les scores nuls
  --ids    retire des evaluations precises, listees a la main

Les suppressions portent sur Evaluation ET Submission : une soumission sans
evaluation resterait orpheline et fausserait les compteurs.
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.coverage import is_non_answer
from db.models import Evaluation, Submission, User, get_session


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true",
                    help="retirer les non-reponses et les scores nuls")
    ap.add_argument("--ids", type=str, default="",
                    help="identifiants d'evaluations a retirer, separes par des virgules")
    ap.add_argument("--person", type=str, default="",
                    help="limiter a une personne")
    ap.add_argument("--apply", action="store_true",
                    help="appliquer reellement (sinon simulation)")
    args = ap.parse_args()

    s = get_session()
    q = (s.query(Evaluation, Submission, User)
         .join(Submission, Evaluation.submission_id == Submission.id)
         .join(User, Submission.user_id == User.id))
    if args.person:
        q = q.filter(User.name.ilike(f"%{args.person}%"))
    rows = q.all()

    targets = []
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",") if x.strip().isdigit()}
        targets = [(ev, sub, u) for ev, sub, u in rows if ev.id in wanted]
    elif args.auto:
        for ev, sub, u in rows:
            empty, reason = is_non_answer(sub.answer_text or "")
            if empty:
                targets.append((ev, sub, u, "non-reponse"))
            elif ev.final_score is not None and ev.final_score < 1.0:
                targets.append((ev, sub, u, "score < 1.0"))
    else:
        print("Precisez --auto ou --ids"); s.close(); return

    if not targets:
        print("Rien a retirer."); s.close(); return

    print(f"{len(targets)} evaluation(s) concernee(s) :\n")
    for t in targets:
        ev, sub, u = t[0], t[1], t[2]
        why = t[3] if len(t) > 3 else "selection manuelle"
        ans = (sub.answer_text or "").replace("\n", " ")[:40]
        print(f"  #{ev.id:<4} {u.name:<14} {(sub.service or ''):<16} "
              f"{ev.final_score:>5.2f}  {why:<14} {ans}")

    if not args.apply:
        print("\nSimulation. Relancez avec --apply pour supprimer.")
        s.close(); return

    for t in targets:
        ev, sub = t[0], t[1]
        s.delete(ev)
        s.delete(sub)
    s.commit()
    print(f"\n{len(targets)} evaluation(s) supprimee(s).")

    # Profils recalcules
    from skills.profile import compute_profile
    print("\nProfils apres nettoyage :")
    for u in s.query(User).all():
        try:
            p = compute_profile(u.id)
            if p.get("n_evaluations"):
                print(f"  {u.name:<14} {p['overall']:>5.1f}%  "
                      f"({p['n_evaluations']} evaluations)")
        except Exception:
            pass
    s.close()


if __name__ == "__main__":
    main()
