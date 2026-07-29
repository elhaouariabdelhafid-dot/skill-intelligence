"""Bascule sur intfloat/multilingual-e5-large avec préfixes query:/passage:.

Le modèle e5 exige :
  - 'passage: ' devant chaque document indexé
  - 'query: ' devant chaque requête
Sans ces préfixes, la qualité chute fortement. On les ajoute dans le backend.
Dimension : 1024.
"""
from pathlib import Path
import sys, re

if not Path("ingestion/embeddings.py").exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)

# 1) .env : modèle
env = Path(".env"); s = env.read_text()
s = re.sub(r"^EMBEDDING_MODEL=.*$",
           "EMBEDDING_MODEL=intfloat/multilingual-e5-large", s, flags=re.M)
env.write_text(s)
print("1. .env : EMBEDDING_MODEL = intfloat/multilingual-e5-large")

# 2) embeddings.py : dimension + préfixes e5
p = Path("ingestion/embeddings.py"); s = p.read_text()

# 2a) Ajouter la dimension du modèle e5
if "multilingual-e5-large" not in s:
    s = s.replace(
        '    "BAAI/bge-m3": 1024,',
        '    "BAAI/bge-m3": 1024,\n    "intfloat/multilingual-e5-large": 1024,')
    print("2a. Dimension 1024 ajoutée pour e5")

# 2b) Détecter si le modèle est un e5 (nécessite préfixes)
#     et adapter FastEmbedder.encode_documents / encode_query
old_fast = '''    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]

    def encode_query(self, text: str) -> list[float]:
        # BGE recommande un préfixe d'instruction côté requête uniquement.
        # FastEmbed l'applique via query_embed.
        return list(self.model.query_embed([text]))[0].tolist()'''

new_fast = '''    def _is_e5(self) -> bool:
        return "e5" in self.model_name.lower()

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        # e5 exige le préfixe 'passage: ' sur les documents
        if self._is_e5():
            texts = [f"passage: {t}" for t in texts]
        return [v.tolist() for v in self.model.embed(texts)]

    def encode_query(self, text: str) -> list[float]:
        # e5 exige le préfixe 'query: ' sur les requêtes
        if self._is_e5():
            return list(self.model.embed([f"query: {text}"]))[0].tolist()
        # BGE : préfixe d'instruction via query_embed
        return list(self.model.query_embed([text]))[0].tolist()'''

if old_fast in s:
    s = s.replace(old_fast, new_fast)
    print("2b. Préfixes e5 (passage:/query:) ajoutés au FastEmbedder")
else:
    print("2b. ATTENTION : bloc FastEmbedder non trouvé tel quel")

p.write_text(s)
print("\nPatch appliqué. Prochaine étape : recréer la collection Qdrant + ré-indexer.")
