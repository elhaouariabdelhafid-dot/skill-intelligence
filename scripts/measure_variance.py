"""Mesure la reproductibilite du jugement des agents.

POURQUOI : la meme reponse, evaluee plusieurs fois dans des conditions
identiques, a produit des scores de 1,50 a 3,60 sur 4. Avant d'ajuster
quoi que ce soit, il faut savoir si cet ecart est la regle ou l'exception.

Ce que le script produit : min, max, moyenne et ecart-type par agent et pour
le score final, sur N passes de la meme reponse. C'est un resultat exploitable
dans un rapport, pas une impression.
"""
import argparse
import json
import statistics as stats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph import evaluate_answer

CASES = {
    "correcte": (
        "Ajouter une condition aws:SourceIp dans la bucket policy pour n'autoriser "
        "que les adresses IP voulues, et retirer le principal public. Les roles IAM "
        "restent compatibles car la condition s'applique au niveau du bucket."),
    "inventee": (
        "Il faut activer AWS S3 IPGuard qui filtre automatiquement les adresses IP "
        "autorisees sur le bucket."),
    "hors-sujet": (
        "Un groupe de securite agit comme un pare-feu virtuel a etat qui controle "
        "le trafic entrant et sortant des instances EC2 dans un VPC."),
}


def load_question(service: str):
    path = Path(__file__).parent.parent / "data" / "processed" / "questions_accepted.jsonl"
    with path.open(encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            if q.get("service") == service:
                return q
    return None


def summarize(name: str, values: list[float]) -> str:
    if not values:
        return f"  {name:<12} aucun resultat"
    mn, mx = min(values), max(values)
    mean = stats.mean(values)
    sd = stats.stdev(values) if len(values) > 1 else 0.0
    spread = mx - mn
    return (f"  {name:<12} {mean:>5.2f}  ecart-type {sd:>4.2f}  "
            f"min {mn:>4.2f}  max {mx:>4.2f}  amplitude {spread:>4.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--service", default="S3")
    ap.add_argument("--case", default="", help="correcte, inventee, hors-sujet")
    args = ap.parse_args()

    q = load_question(args.service)
    if q is None:
        print(f"Aucune question pour le service {args.service}"); return

    cases = {args.case: CASES[args.case]} if args.case in CASES else CASES

    print(f"Question ({args.service}) : {q['question'][:88]}...")
    print(f"{args.runs} passes par cas · modele evaluateur inchange\n")

    report = {}
    for label, answer in cases.items():
        print(f"── Reponse {label} " + "─" * (58 - len(label)))
        runs = {"grader": [], "reasoner": [], "critic": [], "final": []}
        for i in range(1, args.runs + 1):
            t0 = time.time()
            try:
                r = evaluate_answer(
                    question=q["question"], expected_answer=q["expected_answer"],
                    key_points=q.get("key_points", []), rubric=q.get("rubric", []),
                    candidate_answer=answer, service=q.get("service", ""))
                runs["grader"].append(r["grader"]["score"])
                runs["reasoner"].append(r["reasoner"]["score"])
                runs["critic"].append(r["critic"]["score"])
                runs["final"].append(r["final_score"])
                print(f"  passe {i} : {r['grader']['score']:.1f} / "
                      f"{r['reasoner']['score']:.1f} / {r['critic']['score']:.1f} "
                      f"→ {r['final_score']:.2f}   ({time.time()-t0:.0f}s)")
            except Exception as e:
                print(f"  passe {i} : ECHEC {type(e).__name__} {str(e)[:70]}")
            time.sleep(1)

        print()
        for k in ("grader", "reasoner", "critic", "final"):
            print(summarize(k, runs[k]))
        report[label] = runs
        print()

    # Synthese
    print("═" * 72)
    print("SYNTHESE — score final\n")
    print(f"  {'cas':<12} {'moyenne':>8} {'ecart-type':>11} {'amplitude':>10}")
    for label, runs in report.items():
        v = runs["final"]
        if not v:
            continue
        sd = stats.stdev(v) if len(v) > 1 else 0.0
        print(f"  {label:<12} {stats.mean(v):>8.2f} {sd:>11.2f} {max(v)-min(v):>10.2f}")

    finals = {k: v["final"] for k, v in report.items() if v["final"]}
    if "correcte" in finals and "inventee" in finals:
        gap = stats.mean(finals["correcte"]) - stats.mean(finals["inventee"])
        worst = min(finals["correcte"]) - max(finals["inventee"])
        print(f"\n  Ecart moyen correcte / inventee : {gap:.2f} points")
        print(f"  Ecart dans le pire cas          : {worst:.2f} points")
        print("  → la discrimination tient" if worst > 0
              else "  → les distributions se chevauchent : discrimination non garantie")

    out = Path(__file__).parent.parent / "variance_agents.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nDetail enregistre dans {out.name}")


if __name__ == "__main__":
    main()
