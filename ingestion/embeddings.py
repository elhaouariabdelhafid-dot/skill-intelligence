"""Couche d'embeddings — FastEmbed (ONNX, CPU) ou SentenceTransformers.

POURQUOI FastEmbed : BGE-M3 via sentence-transformers prend ~60 s pour 24
chunks sur un CPU modeste (mesuré : 16 h pour 25 000 chunks). FastEmbed
exécute le modèle en ONNX Runtime, quantifié, sans PyTorch : 20 à 40× plus
rapide pour une qualité de retrieval très proche sur un corpus anglais.

ARBITRAGE ASSUMÉ : bge-small-en-v1.5 est monolingue anglais (384 dimensions).
Le corpus AWS est en anglais, donc l'indexation n'y perd rien. En Phase 4, si
les candidats répondent en français, le cross-lingual sera dégradé — deux
parades : demander des réponses en anglais, ou repasser sur un modèle
multilingue une fois les mesures de Phase 2 établies.
Ce compromis se documente en une ligne dans le rapport : contrainte matérielle,
pas choix scientifique.

Usage :
    from ingestion.embeddings import get_embedder
    emb = get_embedder()
    vectors = emb.encode_documents(["texte 1", "texte 2"])
    qvec = emb.encode_query("ma question")
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

# Dimensions par modèle — doit correspondre à la config Qdrant
MODEL_DIMS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-m3": 1024,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


class FastEmbedder:
    """Backend ONNX — rapide sur CPU."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding
        self.model_name = model_name
        self.dim = MODEL_DIMS.get(model_name, 384)
        self.model = TextEmbedding(model_name=model_name)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]

    def encode_query(self, text: str) -> list[float]:
        # BGE recommande un préfixe d'instruction côté requête uniquement.
        # FastEmbed l'applique via query_embed.
        return list(self.model.query_embed([text]))[0].tolist()


class STEmbedder:
    """Backend sentence-transformers — lent sur CPU, gardé pour comparaison."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.dim = MODEL_DIMS.get(model_name, 1024)
        self.model = SentenceTransformer(model_name)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True,
                                 show_progress_bar=False).tolist()

    def encode_query(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()


_embedder = None


def get_embedder():
    """Singleton — le chargement du modèle coûte plusieurs secondes."""
    global _embedder
    if _embedder is None:
        backend = getattr(settings, "embedding_backend", "fastembed").lower()
        model = settings.embedding_model
        _embedder = (FastEmbedder(model) if backend == "fastembed"
                     else STEmbedder(model))
    return _embedder


def get_dim() -> int:
    return MODEL_DIMS.get(settings.embedding_model, 384)


if __name__ == "__main__":
    import time
    emb = get_embedder()
    print(f"Modèle    : {emb.model_name}")
    print(f"Dimension : {emb.dim}")

    texts = ["Security groups are stateful firewalls at the instance level."] * 24
    t0 = time.time()
    vecs = emb.encode_documents(texts)
    dt = time.time() - t0
    print(f"24 chunks : {dt:.2f} s  ({dt/24*1000:.0f} ms/chunk)")
    print(f"Estimation 25 490 chunks : {dt/24*25490/60:.1f} min")
