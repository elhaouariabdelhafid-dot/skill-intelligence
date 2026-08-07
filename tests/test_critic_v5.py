"""Verifie l'elargissement du Critic sans regression.

DEUX FAMILLES DE CAS :
  - non-regression : ce qui fonctionnait doit continuer de fonctionner
  - elargissement  : ce que le Critic ne detectait pas doit desormais l'etre
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph import evaluate_answer

CASES = [
    # ── non-regression : pas de faux positif ──
    ("S3", "NR · reponse correcte", 0, 1,
     "Utiliser une bucket policy avec une condition aws:SourceIp restreignant "
     "l'acces aux adresses IP autorisees, et retirer l'acces public."),

    ("RDS", "NR · reponse exacte, breve", 0, 1,
     "L'operation DescribeDBInstances."),

    ("S3", "NR · correcte mais incomplete", 0, 1,
     "Ajouter une condition d'adresse IP dans la politique du bucket."),

    # ── non-regression : detection deja acquise ──
    ("S3", "NR · service invente", 3, 4,
     "Il faut activer AWS S3 IPGuard qui filtre les adresses IP."),

    # ── elargissement : nouveaux cas attendus ──
    ("VPC", "NEW · comportement invente", 2, 4,
     "Les security groups sont stateless : il faut creer une regle sortante "
     "explicite pour autoriser le trafic de retour, sinon la reponse est bloquee."),

    ("S3", "NEW · recommandation dangereuse", 2, 4,
     "Le plus simple est d'attacher la politique AdministratorAccess au role EC2 "
     "et d'ouvrir le bucket a tout le monde, puis de filtrer plus tard."),

    ("IAM", "NEW · contradiction avec le corpus", 2, 4,
     "Un refus explicite dans une politique IAM peut etre annule par une "
     "autorisation explicite placee dans une autre politique."),
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
    print(f"{'cas':<32} {'critic':>7} {'attendu':>9} {'score':>7}  constat")
    print("-" * 100)
    ok = nr_ok = new_ok = 0
    nr_total = new_total = 0
    for service, label, lo, hi, answer in CASES:
        q = load(service)
        if q is None:
            print(f"{label:<32} pas de question {service}"); continue
        est_nr = label.startswith("NR")
        nr_total += est_nr
        new_total += not est_nr
        try:
            r = evaluate_answer(
                question=q["question"], expected_answer=q["expected_answer"],
                key_points=q.get("key_points", []), rubric=q.get("rubric", []),
                candidate_answer=answer, service=service)
            c = r["critic"]["score"]
            bon = lo <= c <= hi
            ok += bon
            nr_ok += bon and est_nr
            new_ok += bon and not est_nr
            just = r["critic"]["justification"][:46].replace("\n", " ")
            print(f"{label:<32} {c:>7.1f} {lo:>4}-{hi:<4} {r['final_score']:>7.2f}  "
                  f"{'OK  ' if bon else 'HORS'} {just}")
        except Exception as e:
            print(f"{label:<32} ECHEC {str(e)[:52]}")
    print("-" * 100)
    print(f"{ok}/{len(CASES)} conformes  "
          f"(non-regression {nr_ok}/{nr_total} · elargissement {new_ok}/{new_total})")
    print("\nUn echec en non-regression est bloquant : restaurer la version "
          "precedente depuis archive/before_fix/.")


if __name__ == "__main__":
    main()
