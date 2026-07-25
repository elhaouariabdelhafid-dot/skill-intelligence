"""Ajoute Cerebras comme provider (1M tokens/jour gratuit, Llama 3.3 70B).
Cerebras expose une API compatible OpenAI -> on réutilise le client OpenAI."""
from pathlib import Path
import sys

if not Path("llm/client.py").exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)

# 1) config.py
c = Path("config.py"); s = c.read_text()
if "cerebras_api_key" not in s:
    s = s.replace(
        '    groq_model: str = "llama-3.3-70b-versatile"',
        '    groq_model: str = "llama-3.3-70b-versatile"\n'
        '    cerebras_api_key: str = ""\n'
        '    cerebras_model: str = "llama-3.3-70b"')
    c.write_text(s); print("config.py : cerebras ajouté")
else:
    print("config.py : déjà à jour")

# 2) client.py : provider cerebras via endpoint OpenAI-compatible
cl = Path("llm/client.py"); s = cl.read_text()
if 'provider == "cerebras"' not in s:
    branch = '''    if provider == "cerebras":
        from openai import OpenAI
        client = OpenAI(api_key=settings.cerebras_api_key,
                        base_url="https://api.cerebras.ai/v1")
        model = getattr(settings, "cerebras_model", "llama-3.3-70b")
        messages = ([{"role": "system", "content": system}] if system else []) \\
                   + [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens)
        return resp.choices[0].message.content

'''
    anchor = '    raise ValueError(f"Provider inconnu : {settings.llm_provider}")'
    s = s.replace(anchor, branch + anchor, 1)
    cl.write_text(s); print("client.py : provider cerebras ajouté")
else:
    print("client.py : déjà à jour")

# 3) ragas_eval.py : juge Cerebras via ChatOpenAI pointé sur l'endpoint Cerebras
r = Path("evaluation/ragas_eval.py"); s = r.read_text()
if "cerebras" not in s.lower():
    old = '''def build_gemini_judge():
    """Juge = Groq (llama-3.3-70b). Embedder = local (fastembed via HF),
    pour ne pas dépendre d'un embedder cloud soumis à quota."""
    import os
    from config import settings
    os.environ["GROQ_API_KEY"] = settings.groq_api_key
    from langchain_groq import ChatGroq
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    judge = LangchainLLMWrapper(
        ChatGroq(model=settings.groq_model, temperature=0,
                 api_key=settings.groq_api_key, max_retries=3))
    embedder = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5"))
    return judge, embedder'''
    new = '''def build_gemini_judge():
    """Juge = Cerebras (Llama 3.3 70B, 1M tokens/jour gratuit) via endpoint
    OpenAI-compatible. Embedder = local (BGE-small) pour éviter tout quota."""
    from config import settings
    from langchain_openai import ChatOpenAI
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    judge = LangchainLLMWrapper(
        ChatOpenAI(model=settings.cerebras_model, temperature=0,
                   api_key=settings.cerebras_api_key,
                   base_url="https://api.cerebras.ai/v1",
                   max_retries=3, timeout=120))
    embedder = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5"))
    return judge, embedder'''
    s = s.replace(old, new)
    r.write_text(s); print("ragas_eval.py : juge Cerebras")
else:
    print("ragas_eval.py : déjà à jour")

print("\nPatch Cerebras terminé.")
