"""Verifie que les non-reponses sont notees 0 de facon stable."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.coverage import is_non_answer

CASES = [
    ("je sais pas", True), ("Je ne sais pas.", True), ("I don't know", True),
    ("", True), ("?", True), ("n/a", True), ("rien", True),
    ("DescribeDBInstances", False),
    ("Oui, il faut attacher une politique de lecture seule.", False),
    ("Un groupe de securite agit comme un pare-feu virtuel a etat.", False),
]

print("Controle de couverture — detection sans appel LLM\n")
ok = 0
for text, expected in CASES:
    got, reason = is_non_answer(text)
    status = "OK   " if got == expected else "ECHEC"
    if got == expected:
        ok += 1
    label = "score 0 direct" if got else "envoye aux agents"
    print(f"  {status} {label:<18} {text[:50]!r}")
print(f"\n{ok}/{len(CASES)} cas corrects")

print("\nStabilite : meme entree, 5 appels")
scores = [is_non_answer("je sais pas")[0] for _ in range(5)]
print(f"  resultats : {scores} — {'stable' if len(set(scores)) == 1 else 'INSTABLE'}")
