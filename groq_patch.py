"""Bascule le projet sur Groq (quota gratuit large) pour la génération et le juge RAGAS."""
from pathlib import Path
import sys

root = Path.cwd()
if not (root / "llm" / "client.py").exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)

# 1) config.py : ajouter groq
c = Path("config.py"); s = c.read_text()
if "groq_api_key" not in s:
    s = s.replace(
        '    google_api_key: str = ""',
        '    google_api_key: str = ""\n'
        '    groq_api_key: str = ""\n'
        '    groq_model: str = "llama-3.3-70b-versatile"')
    c.write_text(s); print("config.py : groq ajouté")
else:
    print("config.py : déjà à jour")

# 2) client.py : brancher provider groq
cl = Path("llm/client.py"); s = cl.read_text()
if 'provider == "groq"' not in s:
    branch = '''    if provider == "groq":
        from langchain_groq import ChatGroq
        model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")
        llm = ChatGroq(model=model, temperature=temperature,
                       api_key=settings.groq_api_key, max_retries=3)
        messages = ([("system", system)] if system else []) + [("human", prompt)]
        return _gemini_text(llm.invoke(messages).content)

'''
    anchor = '    raise ValueError(f"Provider inconnu : {settings.llm_provider}")'
    s = s.replace(anchor, branch + anchor, 1)
    cl.write_text(s); print("client.py : provider groq ajouté")
else:
    print("client.py : déjà à jour")

# 3) ragas_eval.py : juge Groq
r = Path("evaluation/ragas_eval.py"); s = r.read_text()
if "ChatGroq" not in s:
    old = '''def build_gemini_judge():
    """Configure Gemini comme juge et embedder pour RAGAS."""
    from langchain_google_genai import (ChatGoogleGenerativeAI,
                                        GoogleGenerativeAIEmbeddings)
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    judge = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model=JUDGE_MODEL, temperature=0,
                               max_retries=3))
    embedder = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(model=EMBED_MODEL))
    return judge, embedder'''
    new = '''def build_gemini_judge():
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
    s = s.replace(old, new)
    r.write_text(s); print("ragas_eval.py : juge Groq + embedder local")
else:
    print("ragas_eval.py : déjà à jour")

print("\nPatch terminé.")
