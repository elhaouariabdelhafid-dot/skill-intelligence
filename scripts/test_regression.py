"""Test de non-regression sur six profils de reponse.

Chaque cas porte une attente explicite. Le test ne verifie pas un score exact
— il verifie que le systeme place chaque reponse dans la bonne plage.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph import evaluate_answer

CASES = [
    ("complete", 3.0, 4.0,
     "Utiliser l'AWS Policy Generator pour creer une bucket policy avec une "
     "condition aws:SourceIp restreignant l'acces aux adresses IP autorisees. "
     "Cette approche reste compatible avec les roles IAM et les identity "
     "providers existants : la bucket policy est une politique de ressource "
     "qui s'evalue en complement des politiques d'identite, sans les remplacer. "
     "Les roles IAM continuent donc de fonctionner, l'acces effectif etant "
     "l'intersection des deux."),

    ("correcte-courte", 2.0, 4.0,
     "Ajouter une condition aws:SourceIp dans la bucket policy et retirer "
     "le principal public."),

    ("outil-reel-hors-contexte", 2.0, 4.0,
     "Passer par l'AWS Policy Generator pour construire la bucket policy avec "
     "la condition d'adresse IP."),

    ("partiellement-fausse", 0.5, 2.5,
     "Il faut modifier les politiques IAM de chaque utilisateur pour y ajouter "
     "les adresses IP, la bucket policy ne permettant pas de filtrer par IP."),

    ("hallucination", 0.0, 1.5,
     "Il faut activer AWS S3 IPGuard qui filtre automatiquement les adresses IP "
     "autorisees sur le bucket."),

    ("hors-sujet", 0.0, 1.5,
     "Un groupe de securite agit comme un pare-feu virtuel a etat qui controle "
     "le trafic entrant et sortant des instances EC2 dans un VPC."),
]


def main():
    path = Path(__file__).parent.parent / "data" / "processed" / "questions_accepted.jsonl"
    q = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("service") == "S3":
                q = d; break
    if q is None:
        print("Aucune question S3"); return

    print(f"Question : {q['question'][:88]}...")
    print(f"Points cles : {q.get('key_points')}\n")
    print(f"{'cas':<26} {'attendu':>11}  {'obtenu':>7}  {'G/R/C':>10}  etat")
    print("-" * 74)

    passed = 0
    for label, lo, hi, answer in CASES:
        try:
            r = evaluate_answer(
                question=q["question"], expected_answer=q["expected_answer"],
                key_points=q.get("key_points", []), rubric=q.get("rubric", []),
                candidate_answer=answer, service=q.get("service", ""))
            f = r["final_score"]
            trio = (f"{r['grader']['score']:.0f}/{r['reasoner']['score']:.0f}"
                    f"/{r['critic']['score']:.0f}")
            ok = lo <= f <= hi
            passed += ok
            print(f"{label:<26} {lo:>4.1f}-{hi:<4.1f}  {f:>7.2f}  {trio:>10}  "
                  f"{'OK' if ok else 'HORS PLAGE'}")
            if not ok:
                print(f"    Grader : {r['grader']['justification'][:150]}")
                if r["critic"]["score"] > 0:
                    print(f"    Critic : {r['critic']['justification'][:150]}")
        except Exception as e:
            print(f"{label:<26} {'—':>11}  {'ECHEC':>7}  {str(e)[:40]}")

    print("-" * 74)
    print(f"{passed}/{len(CASES)} cas dans la plage attendue")

    print("\nNON-REGRESSION : 'AWS Policy Generator' figure dans les points cles.")
    print("Il ne doit jamais etre signale comme hallucination.")


if __name__ == "__main__":
    main()
