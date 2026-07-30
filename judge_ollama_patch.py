"""Bascule le juge RAGAS sur Ollama local (illimité, pas de quota).

Ollama expose une API compatible OpenAI sur http://localhost:11434/v1.
On utilise ChatOpenAI pointé dessus, avec une clé factice (Ollama l'ignore).
L'embedder reste local (bge-small) — inchangé.

Avantage : plus aucun 429, le run RAGAS va jusqu'au bout.
Compromis : Qwen 7B est un juge moins fin que le 70B, mais cohérent entre
naïf et v2 (même juge) -> la comparaison reste valide.
"""
from pathlib import Path
import sys

p = Path("evaluation/ragas_eval.py")
if not p.exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)
s = p.read_text()

old = '''def build_gemini_judge():
    """Juge = Cerebras (Llama 3.3 70B, 1M tokens/jour gratuit) via endpoint
    OpenAI-compatible. Embedder = local (BGE-small) pour éviter tout quota."""
    from config import settings
    from langchain_groq import ChatGroq
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    import os
    os.environ["GROQ_API_KEY"] = settings.groq_api_key
    judge = LangchainLLMWrapper(
        ChatGroq(model=settings.groq_model, temperature=0,
                 api_key=settings.groq_api_key, max_retries=3))
    embedder = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5"))
    return judge, embedder'''

new = '''def build_gemini_judge():
    """Juge = Ollama local (Qwen 2.5) via endpoint OpenAI-compatible.
    Illimité, pas de quota. Embedder = local (BGE-small).

    On passe par ChatOpenAI pointé sur http://localhost:11434/v1 : Ollama
    accepte l'API OpenAI. La clé est factice (ignorée par Ollama)."""
    from config import settings
    from langchain_openai import ChatOpenAI
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    model = getattr(settings, "ollama_model", "qwen2.5:7b")
    base = getattr(settings, "ollama_base_url", "http://localhost:11434")
    judge = LangchainLLMWrapper(
        ChatOpenAI(model=model, temperature=0,
                   api_key="ollama",  # factice, ignorée par Ollama
                   base_url=f"{base}/v1",
                   timeout=180, max_retries=2))
    embedder = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5"))
    return judge, embedder'''

if old in s:
    s = s.replace(old, new)
    p.write_text(s)
    print("juge RAGAS basculé sur Ollama local")
elif "Ollama local (Qwen" in s:
    print("déjà sur Ollama")
else:
    print("ATTENTION : fonction non trouvée telle quelle, envoie-moi le fichier")
