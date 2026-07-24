"""Phase 1 — Indexation : embeddings -> Qdrant.

CHANGEMENT : passe par ingestion/embeddings.py, qui utilise FastEmbed (ONNX)
au lieu de sentence-transformers. Motif : 60 s/24 chunks mesuré sur CPU avec
BGE-M3, soit 16 h pour le corpus. FastEmbed ramène cela à ~30 min.

POURQUOI stocker le texte dans le payload : au retrieval on récupère le chunk
sans requête secondaire, et les métadonnées permettent le filtrage par service.

Usage :
    python ingestion/indexer.py
    python ingestion/indexer.py --rebuild    # supprime et réindexe
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from ingestion.chunking import Chunk, chunk_corpus, load_chunks, save_chunks
from ingestion.embeddings import get_dim, get_embedder

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, PayloadSchemaType, PointStruct,
                                  VectorParams)
from tqdm import tqdm

BATCH = 128   # FastEmbed est rapide : batch large sans risque mémoire


def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, check_compatibility=False)


def ensure_collection(client: QdrantClient, dim: int,
                      rebuild: bool = False) -> None:
    name = settings.qdrant_collection
    exists = client.collection_exists(name)

    if exists and not rebuild:
        info = client.get_collection(name)
        current_dim = info.config.params.vectors.size
        if current_dim != dim:
            raise RuntimeError(
                f"La collection '{name}' est en {current_dim} dimensions mais le "
                f"modèle en produit {dim}. Relance avec --rebuild.")

    if exists and rebuild:
        client.delete_collection(name)
        exists = False

    if not exists:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        client.create_payload_index(name, "service", PayloadSchemaType.KEYWORD)
        client.create_payload_index(name, "category", PayloadSchemaType.KEYWORD)


def index_chunks(chunks: list[Chunk], rebuild: bool = False) -> None:
    client = get_client()
    embedder = get_embedder()
    dim = embedder.dim
    print(f"Modèle : {embedder.model_name} ({dim} dimensions)")
    ensure_collection(client, dim, rebuild=rebuild)

    for i in tqdm(range(0, len(chunks), BATCH), desc="Indexation"):
        batch = chunks[i:i + BATCH]
        vectors = embedder.encode_documents([c.text for c in batch])
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_OID, c.chunk_id)),
                vector=v,
                payload={
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "source_file": c.source_file,
                    "service": c.service,
                    "category": c.category,
                    "title": c.title,
                    "section": c.section,
                    "doc_type": c.doc_type,
                },
            )
            for c, v in zip(batch, vectors)
        ]
        client.upsert(collection_name=settings.qdrant_collection, points=points)

    info = client.get_collection(settings.qdrant_collection)
    print(f"Collection '{settings.qdrant_collection}' : {info.points_count} points")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    chunks_path = Path("data/processed/chunks.jsonl")
    if chunks_path.exists():
        chunks = load_chunks()
        print(f"Chunks chargés : {len(chunks)}")
    else:
        print("Chunking du corpus...")
        chunks = chunk_corpus()
        save_chunks(chunks)
        print(f"Chunks produits : {len(chunks)}")

    index_chunks(chunks, rebuild=args.rebuild)
