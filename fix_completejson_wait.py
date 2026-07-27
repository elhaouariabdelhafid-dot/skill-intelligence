"""Rend complete_json intelligent face au 429 : au lieu de sleep(0.5) fixe,
il détecte un 429 et attend le délai réel indiqué par l'API avant de retenter.
C'est LE correctif qui fait tenir les 3 agents sous la limite 6000 tokens/min."""
from pathlib import Path
import sys

p = Path("llm/client.py")
s = p.read_text()

# Trouver le bloc de retry dans complete_json et remplacer le sleep(0.5)
old = '''        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_error = str(e)[:300]
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)'''

new = '''        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_error = str(e)[:300]
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)
        except Exception as e:
            # 429 ou autre erreur réseau : attendre le délai réel puis retenter
            last_error = str(e)[:300]
            m = re.search(r"try again in ([0-9.]+)s", str(e))
            if "429" in str(e) or "rate_limit" in str(e).lower() or m:
                wait = (float(m.group(1)) + 2) if m else 25
                print(f"    [429] complete_json attend {wait:.0f}s...")
                time.sleep(wait)
            elif attempt < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                raise'''

if old in s:
    s = s.replace(old, new)
    # s'assurer que 're' est importé
    if "\nimport re\n" not in s:
        s = s.replace("import json\n", "import json\nimport re\n", 1)
    # augmenter MAX_RETRIES pour laisser le temps aux attentes
    s = s.replace("MAX_RETRIES = 3", "MAX_RETRIES = 5")
    p.write_text(s)
    print("client.py : complete_json attend le vrai délai 429, MAX_RETRIES=5")
elif "complete_json attend" in s:
    print("client.py : déjà patché")
else:
    print("motif introuvable — le bloc except a peut-être une autre forme")
    # afficher le bloc actuel pour diagnostic
    import re as _re
    m = _re.search(r"except.*?time\.sleep\(0\.5\)", s, _re.DOTALL)
    if m:
        print("BLOC ACTUEL :"); print(m.group(0)[:300])
