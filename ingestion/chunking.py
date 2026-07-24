"""Phase 1 — Chunking du corpus.

POURQUOI ce design :
- Phase 1 : chunking récursif ~512 tokens, overlap 50. Simple, baseline mesurable.
- Le splitter respecte d'abord la structure Markdown (titres ##) avant de couper
  au caractère : un chunk qui coupe une section en plein milieu perd son contexte.
- Chaque chunk hérite des métadonnées du document parent + un chunk_id stable
  (hash du contenu) : indispensable pour les citations et la déduplication.

En Phase 2 tu compareras cette baseline au chunking sémantique — garde-la.

Usage :
    python ingestion/chunking.py     # aperçu + stats, écrit data/processed/chunks.jsonl
"""
from __future__ import annotations
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROCESSED_DIR
from ingestion.loaders import RawDocument, load_corpus

from langchain_text_splitters import (MarkdownHeaderTextSplitter,
                                      RecursiveCharacterTextSplitter)

# ~512 tokens ≈ 2000 caractères pour du texte technique anglais
CHUNK_SIZE_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_file: str
    service: str
    category: str
    title: str
    doc_type: str
    section: str          # dernier titre Markdown rencontré


def _chunk_id(text: str, source: str) -> str:
    return hashlib.sha1(f"{source}::{text[:200]}".encode()).hexdigest()[:16]


def chunk_document(doc: RawDocument) -> list[Chunk]:
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
        separators=["\n\n", "\n", ". ", " "],
    )

    # Le splitter par titres ne s'applique qu'au vrai Markdown. Sur du texte
    # extrait de PDF il ne trouve aucun titre et renvoie un bloc unique —
    # autant l'éviter et découper directement.
    is_markdown = doc.source_file.endswith(".md")

    if is_markdown:
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        sections = [(s.page_content,
                     s.metadata.get("h2") or s.metadata.get("h1") or doc.title)
                    for s in header_splitter.split_text(doc.content)]
    else:
        sections = [(doc.content, doc.title)]

    chunks: list[Chunk] = []
    for content, section_title in sections:
        for piece in char_splitter.split_text(content):
            if len(piece) < 150:
                continue
            chunks.append(Chunk(
                chunk_id=_chunk_id(piece, doc.source_file),
                text=piece,
                source_file=doc.source_file,
                service=doc.service,
                category=doc.category,
                title=doc.title,
                doc_type=doc.doc_type,
                section=section_title,
            ))
    return chunks


def chunk_corpus(docs: list[RawDocument] | None = None) -> list[Chunk]:
    docs = docs or load_corpus()
    all_chunks: list[Chunk] = []
    seen: set[str] = set()
    for doc in docs:
        for c in chunk_document(doc):
            if c.chunk_id in seen:     # dédup exacte (pages dupliquées AWS)
                continue
            seen.add(c.chunk_id)
            all_chunks.append(c)
    return all_chunks


def save_chunks(chunks: list[Chunk], path: Path | None = None) -> Path:
    path = path or PROCESSED_DIR / "chunks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    return path


def load_chunks(path: Path | None = None) -> list[Chunk]:
    path = path or PROCESSED_DIR / "chunks.jsonl"
    with path.open(encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f]


if __name__ == "__main__":
    chunks = chunk_corpus()
    lengths = [len(c.text) for c in chunks]
    print(f"Chunks produits : {len(chunks)}")
    print(f"Taille moyenne  : {sum(lengths)//len(lengths)} caractères")
    print(f"Min / Max       : {min(lengths)} / {max(lengths)}")
    out = save_chunks(chunks)
    print(f"Écrit dans      : {out}")
    print("\n--- Exemple de chunk ---")
    ex = chunks[len(chunks)//2]
    print(f"[{ex.service} / {ex.section}]")
    print(ex.text[:400])
