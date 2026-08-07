"""Liste les evaluations en base pour choisir lesquelles retirer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Evaluation, Submission, User, get_session

s = get_session()
rows = (s.query(Evaluation, Submission, User)
        .join(Submission, Evaluation.submission_id == Submission.id)
        .join(User, Submission.user_id == User.id)
        .order_by(Evaluation.id).all())

print(f"{len(rows)} evaluations en base\n")
print(f"{'id':>4}  {'personne':<14} {'service':<18} {'score':>6}  reponse")
print("-" * 96)
for ev, sub, u in rows:
    ans = (sub.answer_text or "").replace("\n", " ")[:44]
    print(f"{ev.id:>4}  {u.name:<14} {(sub.service or ''):<18} "
          f"{ev.final_score:>6.2f}  {ans}")

print("\nPar personne :")
by = {}
for ev, sub, u in rows:
    by.setdefault(u.name, []).append(ev.final_score)
for name, scores in by.items():
    print(f"  {name:<14} {len(scores):>3} evaluations · moyenne {sum(scores)/len(scores):.2f}/4")
s.close()
