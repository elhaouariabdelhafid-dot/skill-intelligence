"""complete_json fait 3 tentatives internes rapides qui court-circuitent le
backoff 429. On enveloppe chaque agent avec un backoff propre : si complete_json
lève une erreur contenant 429, on attend et on retente au niveau de l'agent."""
from pathlib import Path
import sys

# Créer un helper partagé dans llm/client.py : call_with_backoff
p = Path("llm/client.py")
s = p.read_text()

if "def json_with_backoff" not in s:
    helper = '''

def json_with_backoff(prompt, schema, system=None, temperature=0.3,
                      max_tokens=2000, max_wait_rounds=4):
    """complete_json + gestion du 429 au niveau appelant.

    complete_json retente en interne mais rapidement ; si le quota par minute
    est atteint, on attend le délai indiqué puis on relance complete_json en
    entier. Évite le fallback 'indisponible' sur simple 429."""
    import time as _t, re as _re
    last = None
    for round_i in range(max_wait_rounds):
        try:
            return complete_json(prompt, schema, system=system,
                                 temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            last = e
            msg = str(e)
            m = _re.search(r"try again in ([0-9.]+)s", msg)
            if "429" in msg or "rate_limit" in msg.lower() or m:
                wait = (float(m.group(1)) + 2) if m else 25
                print(f"    [429 agent] attente {wait:.0f}s...")
                _t.sleep(wait)
                continue
            raise
    raise RuntimeError(f"json_with_backoff: échec après {max_wait_rounds} rounds: {last}")
'''
    # insérer après la définition de complete_json (à la fin du fichier avant __main__)
    if 'if __name__ == "__main__":' in s:
        s = s.replace('if __name__ == "__main__":', helper + '\n\nif __name__ == "__main__":', 1)
    else:
        s = s + helper
    p.write_text(s)
    print("client.py : json_with_backoff ajouté")
else:
    print("client.py : json_with_backoff déjà présent")

# Remplacer complete_json par json_with_backoff dans les 3 agents
for name in ["grader", "reasoner", "critic"]:
    ap = Path(f"agents/{name}.py")
    a = ap.read_text()
    changed = False
    if "from llm.client import complete_json" in a:
        a = a.replace("from llm.client import complete_json",
                      "from llm.client import json_with_backoff")
        changed = True
    if "complete_json(" in a:
        a = a.replace("complete_json(", "json_with_backoff(")
        changed = True
    if changed:
        ap.write_text(a)
        print(f"{name}.py : utilise json_with_backoff")
    else:
        print(f"{name}.py : rien à changer")
