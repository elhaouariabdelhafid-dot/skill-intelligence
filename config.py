"""Configuration centralisée — lue depuis .env via pydantic-settings.

Pourquoi : un seul point de vérité pour toutes les variables, validation
au démarrage (une URL manquante échoue immédiatement, pas au milieu d'un run).
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env",
                                      env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    gemini_model: str = "gemini-flash-latest"
    google_api_key: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "aws_docs"

    # Modèles
    embedding_backend: str = "fastembed"   # fastembed | sentence_transformers
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Postgres
    database_url: str = "postgresql://skill:skill@localhost:5432/skilldb"
    jwt_secret: str = "change-me-in-production-please"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"


settings = Settings()
