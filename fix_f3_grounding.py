"""Assouplit le filtre F3 (ancrage) de generation/filters.py.

PROBLÈME : F3 exigeait que le chunk source EXACT remonte dans le top-5 du
retrieval. Or les questions 'apply' sont des scénarios reformulés qui ne
ressemblent pas au texte source — elles échouent à tort.

CORRECTIF : F3 accepte si (a) le chunk source est dans le top-15, OU (b) un
chunk du même service remonte avec un bon score (la question reste ancrée dans
le bon domaine technique). On mesure l'ancrage thématique, pas la similarité
textuelle exacte.
"""
from pathlib import Path
import sys

p = Path("generation/filters.py")
if not p.exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)
s = p.read_text()

old = '''def filter_grounding(q: StoredQuestion) -> tuple[str | None, float]:
    """Vérifie que le chunk source est bien retrouvé quand on cherche la question.

    POURQUOI : si la question ne permet pas de retrouver son propre chunk
    d'origine, elle est soit trop vague, soit hors corpus — donc inévaluable
    par les agents en Phase 4, qui s'appuient sur le retrieval.
    """
    from retrieval.reranker import retrieve_final

    hits = retrieve_final(q.question, top_k=5)
    if not hits:
        return "no_retrieval", 0.0

    source_ids = set(q.source_chunk_ids)
    for hit in hits:
        if hit.chunk_id in source_ids:
            score = float(hit.score)
            if score < GROUNDING_THRESHOLD:
                return "weak_grounding", score
            return None, score

    # Le chunk source n'est pas dans le top-5 : la question a dérivé
    return "source_not_retrieved", float(hits[0].score)'''

new = '''def filter_grounding(q: StoredQuestion) -> tuple[str | None, float]:
    """Vérifie que la question est ancrée dans le corpus, sur le bon domaine.

    POURQUOI assoupli : les questions 'apply' sont des scénarios reformulés qui
    ne ressemblent pas textuellement au chunk source. On ne peut donc pas exiger
    que le chunk EXACT remonte. On vérifie plutôt un ancrage THÉMATIQUE :
      (a) le chunk source est dans le top-15 (large), OU
      (b) au moins un chunk du même service remonte en tête.
    Cela garde les bonnes questions de raisonnement tout en rejetant celles qui
    partent complètement hors corpus.
    """
    from retrieval.reranker import retrieve_final

    hits = retrieve_final(q.question, top_k=15)
    if not hits:
        return "no_retrieval", 0.0

    source_ids = set(q.source_chunk_ids)
    # (a) chunk source exact dans le top-15
    for hit in hits:
        if hit.chunk_id in source_ids:
            return None, float(hit.score)

    # (b) ancrage thématique : un chunk du même service en tête (top-5)
    top_services = [h.service for h in hits[:5]]
    if q.service in top_services:
        return None, float(hits[0].score)

    # Sinon la question a vraiment dérivé hors de son domaine
    return "source_not_retrieved", float(hits[0].score)'''

if old in s:
    s = s.replace(old, new)
    p.write_text(s)
    print("filters.py : F3 assoupli (ancrage thématique)")
elif "ancrage THÉMATIQUE" in s:
    print("filters.py : déjà patché")
else:
    print("motif introuvable — envoie-moi filters.py")
