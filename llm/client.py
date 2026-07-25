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

MAX_RETRIES = 3


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
        import os
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
        from langchain_groq import ChatGroq
        model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        llm = ChatGroq(model=model, temperature=temperature,
                       api_key=settings.groq_api_key, max_retries=3)
        messages = ([("system", system)] if system else []) + [("human", prompt)]
        return _gemini_text(llm.invoke(messages).content)

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


def complete_json(prompt: str, schema: Type[T], system: str | None = None,
                  temperature: float = 0.3, max_tokens: int = 2000) -> T:
    """Appel LLM avec validation Pydantic et re-tentative automatique.

    PIÈGE ÉVITÉ : ne jamais faire json.loads() directement sur la sortie d'un 7B.
    Le taux d'échec au premier essai est de 10-30 % selon le modèle.
    """
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    full_system = (
        (system + "\n\n" if system else "")
        + "You MUST reply with a single valid JSON object matching this schema.\n"
        + "No markdown fences, no preamble, no explanation. JSON only.\n"
        + f"SCHEMA: {schema_json}"
    )

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            raw = complete(
                prompt if attempt == 0
                else f"{prompt}\n\nPrevious attempt failed: {last_error}\nReply with valid JSON only.",
                system=full_system,
                temperature=temperature + 0.1 * attempt,  # varier si blocage
                max_tokens=max_tokens,
            )
            return schema.model_validate_json(_extract_json(raw))
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_error = str(e)[:300]
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)

    raise RuntimeError(
        f"Échec après {MAX_RETRIES} tentatives. Dernière erreur : {last_error}")


if __name__ == "__main__":
    class Ping(BaseModel):
        status: str
        model_used: str

    print("Provider :", settings.llm_provider)
    print("Texte    :", complete("Réponds uniquement: OK").strip()[:80])
    print("JSON     :", complete_json(
        "Return status='ok' and model_used with the name of the model you are.",
        Ping))
