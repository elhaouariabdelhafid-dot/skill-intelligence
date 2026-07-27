"""Rend complete() et complete_json() résistants au 429 : au lieu de retenter
immédiatement, on attend le délai indiqué par l'API (backoff)."""
from pathlib import Path
import sys, re

p = Path("llm/client.py")
if not p.exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)
s = p.read_text()

if "_handle_rate_limit" in s:
    print("client.py : déjà patché"); sys.exit(0)

# Helper de backoff, inséré avant def complete(
helper = '''
def _handle_rate_limit(exc, attempt: int) -> bool:
    """Si l'exception est un 429, attend le délai suggéré et retourne True
    (il faut retenter). Sinon retourne False."""
    import time as _t
    msg = str(exc)
    if "429" in msg or "rate_limit" in msg.lower() or "RateLimit" in type(exc).__name__:
        # Chercher "try again in 21.4s" dans le message
        m = re.search(r"try again in ([0-9.]+)s", msg)
        wait = float(m.group(1)) + 2 if m else 20 * (attempt + 1)
        print(f"    [429] attente {wait:.0f}s...")
        _t.sleep(wait)
        return True
    return False

'''

# Insérer le helper et 'import re' si absent
if "\nimport re\n" not in s:
    s = s.replace("import json\n", "import json\nimport re\n", 1)
s = s.replace("\ndef complete(", helper + "\ndef complete(", 1)

# Envelopper l'appel LLM dans complete() avec backoff sur 429
# On cible la branche groq et gemini (les deux utilisent llm.invoke)
old_groq = '''    if provider == "groq":
        import os
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
        from langchain_groq import ChatGroq
        model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        llm = ChatGroq(model=model, temperature=temperature,
                       api_key=settings.groq_api_key, max_retries=3)
        messages = ([("system", system)] if system else []) + [("human", prompt)]
        return _gemini_text(llm.invoke(messages).content)'''
new_groq = '''    if provider == "groq":
        import os, time as _t
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
        from langchain_groq import ChatGroq
        model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        llm = ChatGroq(model=model, temperature=temperature,
                       api_key=settings.groq_api_key, max_retries=1)
        messages = ([("system", system)] if system else []) + [("human", prompt)]
        for attempt in range(5):
            try:
                return _gemini_text(llm.invoke(messages).content)
            except Exception as e:
                if _handle_rate_limit(e, attempt):
                    continue
                raise
        raise RuntimeError("Groq : trop de 429 successifs")'''

if old_groq in s:
    s = s.replace(old_groq, new_groq)
    print("client.py : backoff 429 ajouté à la branche Groq")
else:
    print("ATTENTION : branche Groq non trouvée telle quelle")

p.write_text(s)
print("client.py : patch appliqué")
