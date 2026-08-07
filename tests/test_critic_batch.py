"""Verifie que le Critic juge au lieu de recopier, sur cinq cas contrastes."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph import evaluate_answer

CASES = [
    ("RDS", "reponse exacte, une ligne", 0, 1,
     "L'operation DescribeDBInstances."),
    ("EC2", "reponse exacte, une ligne", 0, 1,
     "Un proxy TCP sensible a l'identite (identity-aware TCP proxy)."),
    ("S3", "reponse complete", 0, 1,
     "Utiliser une bucket policy avec une condition aws:SourceIp restreignant "
     "l'acces aux adresses IP autorisees, et retirer l'acces public."),
    ("S3", "service invente", 3, 4,
     "Il faut activer AWS S3 IPGuard qui filtre les adresses IP."),
    ("VPC", "hors-sujet", 0, 4,
     "Un groupe de securite agit comme un pare-feu virtuel a etat."),
]


def load(service):
    path = Path(__file__).parent.parent / "data" / "processed" / "questions_accepted.jsonl"
    with path.open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q.get("service") == service:
                return q
    return None


def main():
    print(f"{'cas':<28} {'critic':>7} {'attendu':>9}  {'score':>6}  constat")
    print("-" * 92)
    ok = 0
    for service, label, lo, hi, answer in CASES:
        q = load(service)
        if q is None:
            print(f"{label:<28} pas de question {service}"); continue
        try:
            r = evaluate_answer(
                question=q["question"], expected_answer=q["expected_answer"],
                key_points=q.get("key_points", []), rubric=q.get("rubric", []),
                candidate_answer=answer, service=service)
            c = r["critic"]["score"]
            good = lo <= c <= hi
            ok += good
            just = r["critic"]["justification"][:52].replace("\n", " ")
            print(f"{label:<28} {c:>7.1f} {lo:>4}-{hi:<4}  {r['final_score']:>6.2f}  "
                  f"{'OK  ' if good else 'HORS'} {just}")
        except Exception as e:
            print(f"{label:<28} ECHEC {str(e)[:50]}")
    print("-" * 92)
    print(f"{ok}/{len(CASES)} cas conformes")
    print("\nAttendu : Critic a 0-1 sur les reponses correctes, 3-4 sur l'invention.")
    print("La justification ne doit jamais reprendre le texte de la consigne.")


if __name__ == "__main__":
    main()
