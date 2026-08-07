"""Verifie la fiabilite de la sortie structuree sur plusieurs essais."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.client import complete_json, _schema_example, _schema_fields
from agents.grader import GraderOutput

print("Ce que le modele voit maintenant :\n")
print("FIELDS TO FILL:")
print(_schema_fields(GraderOutput))
print("\nSHAPE OF YOUR REPLY:")
print(_schema_example(GraderOutput))
print("\n" + "=" * 70 + "\n")

prompt = """Evaluate the technical accuracy of this answer.

QUESTION: What is the recommended approach for managing access to AWS services?
CONTEXT: We recommend that you evaluate access continuously and restrict access
to only those services and service actions needed to complete the current job.
ANSWER: Il faut evaluer les acces en continu et appliquer le moindre privilege.

Score 0-4 on technical correctness only."""

ok = 0
N = 5
for i in range(1, N + 1):
    t0 = time.time()
    try:
        out = complete_json(prompt, GraderOutput, temperature=0.1)
        ok += 1
        print(f"  essai {i} : OK    score {out.score}/4  ({time.time()-t0:.1f}s)")
    except Exception as e:
        print(f"  essai {i} : ECHEC {str(e)[:110]}  ({time.time()-t0:.1f}s)")

print(f"\n{ok}/{N} reussites")
