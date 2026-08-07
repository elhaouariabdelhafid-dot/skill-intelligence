"""Couche LLM unifiée — Ollama (local) ou Anthropic/OpenAI (cloud).

POURQUOI cette abstraction : en Phase 3 et 4 tu appelles le LLM depuis une
dizaine d'endroits. Sans couche commune, changer de provider = modifier 10
fichiers. Ici tu changes une variable dans .env.

POURQUOI `complete_json` séparé : la génération de questions et l'évaluation
par agents exigent du JSON valide. Un LLM 7B produit souvent du JSON entouré
de ```json ou précédé d'un préambule. Cette fonction nettoie et re-tente
automatiquement — c'est LA source d'erreurs n°1 en Phase 3.

Usage :
    from llm.client import complete, complete_json
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Type, TypeVar

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

MAX_RETRIES = 5


# --------------------------------------------------------------------------
# Appel brut
# --------------------------------------------------------------------------

def _gemini_text(content) -> str:
    """Gemini 3.x renvoie parfois une liste de blocs [{'type':'text','text':...}]
    au lieu d'une chaîne. On extrait le texte quel que soit le format."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


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


def complete(prompt: str, system: str | None = None,
             temperature: float = 0.2, max_tokens: int = 1500) -> str:
    """Appel texte simple, quel que soit le provider configuré."""
    provider = settings.llm_provider.lower()

    if provider == "ollama":
        import ollama
        client = ollama.Client(host=settings.ollama_base_url)
        resp = client.generate(
            model=settings.ollama_model,
            prompt=prompt,
            system=system or "",
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return resp["response"]

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        kwargs = {"model": "claude-sonnet-4-6", "max_tokens": max_tokens,
                  "temperature": temperature,
                  "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        return client.messages.create(**kwargs).content[0].text

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        messages = ([{"role": "system", "content": system}] if system else []) \
                   + [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages,
            temperature=temperature, max_tokens=max_tokens)
        return resp.choices[0].message.content

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = getattr(settings, "gemini_model", "gemini-flash-latest")
        llm = ChatGoogleGenerativeAI(model=model, temperature=temperature,
                                     max_retries=3,
                                     google_api_key=settings.google_api_key)
        messages = ([("system", system)] if system else []) + [("human", prompt)]
        return _gemini_text(llm.invoke(messages).content)

    if provider == "groq":
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
        raise RuntimeError("Groq : trop de 429 successifs")

    if provider == "cerebras":
        from openai import OpenAI
        client = OpenAI(api_key=settings.cerebras_api_key,
                        base_url="https://api.cerebras.ai/v1")
        model = getattr(settings, "cerebras_model", "llama-3.3-70b")
        messages = ([{"role": "system", "content": system}] if system else []) \
                   + [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens)
        return resp.choices[0].message.content

    raise ValueError(f"Provider inconnu : {settings.llm_provider}")


# --------------------------------------------------------------------------
# Extraction JSON robuste
# --------------------------------------------------------------------------
def _extract_json(text: str) -> str:
    """Récupère le premier objet JSON d'une réponse LLM.

    Gère : ```json ... ```, préambule bavard, texte après l'objet.
    """
    # 1) bloc de code balisé
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 2) premier { ou [ jusqu'à son délimiteur équilibré
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1),
                default=-1)
    if start == -1:
        raise ValueError("Aucun JSON trouvé dans la réponse")
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("JSON incomplet dans la réponse")


def _schema_example(schema) -> str:
    """Construit un exemple de sortie a partir du schema Pydantic.

    Montrer une reponse plutot que le schema : un petit modele imite ce qu'il
    voit. Lui presenter un objet JSON de description l'incite a le recopier.
    """
    props = schema.model_json_schema().get("properties", {})
    example = {}
    for name, spec in props.items():
        t = spec.get("type")
        if t == "integer":
            example[name] = 2
        elif t == "number":
            example[name] = 2.0
        elif t == "boolean":
            example[name] = False
        elif t == "array":
            example[name] = ["..."]
        else:
            example[name] = "..."
    return json.dumps(example, ensure_ascii=False)


def _schema_fields(schema) -> str:
    """Decrit les champs en clair : nom, type, role."""
    props = schema.model_json_schema().get("properties", {})
    required = set(schema.model_json_schema().get("required", []))
    lines = []
    for name, spec in props.items():
        t = spec.get("type", "string")
        if t == "array":
            t = "array of " + spec.get("items", {}).get("type", "string")
        desc = spec.get("description", "")
        mark = "" if name in required else " (optional)"
        lines.append(f"- {name} ({t}){mark}: {desc}")
    return "\n".join(lines)


def _looks_like_schema(raw: str) -> bool:
    """Detecte le cas ou le modele a renvoye le schema au lieu d'une reponse."""
    lowered = raw.lower()
    return ('"properties"' in lowered or '"$schema"' in lowered
            or '"type": "object"' in lowered)


def complete_json(prompt: str, schema: Type[T], system: str | None = None,
                  temperature: float = 0.3, max_tokens: int = 2000) -> T:
    """Appel LLM avec validation Pydantic et re-tentative automatique.

    PIÈGE ÉVITÉ : ne jamais faire json.loads() directement sur la sortie d'un 7B.
    Le taux d'échec au premier essai est de 10-30 % selon le modèle.
    """
    full_system = (
        (system + "\n\n" if system else "")
        + "Reply with ONE JSON object and nothing else. "
        + "No markdown fences, no preamble, no explanation.\n\n"
        + "FIELDS TO FILL:\n" + _schema_fields(schema) + "\n\n"
        + "SHAPE OF YOUR REPLY (replace the placeholder values with your own "
        + "analysis, keep the same keys):\n" + _schema_example(schema) + "\n\n"
        + "Never reply with a schema, a type description or the word "
        + "'properties'. Reply with the filled object only."
    )

    last_error = ""
    retry_hint = "Reply with valid JSON only."
    for attempt in range(MAX_RETRIES):
        try:
            raw = complete(
                prompt if attempt == 0
                else f"{prompt}\n\nPrevious attempt failed: {last_error}\n{retry_hint}",
                system=full_system,
                temperature=temperature + 0.1 * attempt,  # varier si blocage
                max_tokens=max_tokens,
            )
            if _looks_like_schema(raw):
                # Le modele a recopie le schema : on le lui dit explicitement
                retry_hint = ("You replied with the schema instead of the answer. "
                              "Reply with the FILLED object: "
                              + _schema_example(schema))
                raise ValueError("schema echoed instead of answer")
            return schema.model_validate_json(_extract_json(raw))
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
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
                raise

    raise RuntimeError(
        f"Échec après {MAX_RETRIES} tentatives. Dernière erreur : {last_error}")




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


if __name__ == "__main__":
    class Ping(BaseModel):
        status: str
        model_used: str

    print("Provider :", settings.llm_provider)
    print("Texte    :", complete("Réponds uniquement: OK").strip()[:80])
    print("JSON     :", complete_json(
        "Return status='ok' and model_used with the name of the model you are.",
        Ping))
