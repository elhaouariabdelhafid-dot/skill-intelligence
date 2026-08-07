"""Verifie que le Critic detecte un service inexistant."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from agents.graph import evaluate_answer

CASES = [
    ("Reponse correcte",
     "Ajouter une condition aws:SourceIp dans la bucket policy pour n'autoriser "
     "que les adresses IP voulues, et retirer le principal public."),
    ("Service invente",
     "Il faut activer AWS S3 IPGuard qui filtre automatiquement les adresses IP "
     "autorisees sur le bucket."),
]

q = None
with open("data/processed/questions_accepted.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if d.get("service") == "S3":
            q = d; break
if q is None:
    print("Aucune question S3 trouvee"); sys.exit(1)

print(f"Question : {q['question'][:90]}...\n")
for label, answer in CASES:
    t0 = time.time()
    try:
        r = evaluate_answer(question=q["question"], expected_answer=q["expected_answer"],
                            key_points=q.get("key_points", []), rubric=q.get("rubric", []),
                            candidate_answer=answer, service=q.get("service", ""))
        print(f"{label}")
        print(f"  Grader {r['grader']['score']:.1f} · Reasoner {r['reasoner']['score']:.1f} "
              f"· Critic {r['critic']['score']:.1f} → {r['final_score']:.2f}/4  "
              f"({time.time()-t0:.0f}s)")
        print(f"  Critic : {r['critic']['justification'][:160]}\n")
    except Exception as e:
        print(f"{label} : ECHEC {type(e).__name__} {str(e)[:120]}\n")

print("Attendu : Critic eleve (3-4) et score final bas sur la reponse inventee.")
