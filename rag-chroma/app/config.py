from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8094

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    llm_model: str = "qwen3-max"

    vector_backend: str = Field(default="local", pattern="^(local|qdrant|chroma)$")
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "smartpi_tcm_knowledge"
    chroma_path: Path = Path("./data/chroma")
    local_vector_path: Path = Path("./data/local_vectors.json")

    chunk_size: int = 800
    chunk_overlap: int = 120
    default_top_k: int = 8
    recall_top_k: int = 24
    lexical_top_k: int = 24
    vector_weight: float = 0.65
    lexical_weight: float = 0.35
    min_relevance_score: float = 0.08
    min_chunks_for_answer: int = 1
    enable_query_rewrite: bool = True
    enable_hybrid_search: bool = True
    enable_rerank: bool = True
    rerank_provider: str = Field(default="dashscope", pattern="^(dashscope|local|none)$")
    rerank_model: str = "qwen3-rerank"
    rerank_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    rerank_top_n: int = 0
    rerank_instruction: str = "Given a TCM question, rank the documents by their evidence relevance. Prefer passages that directly answer the question and contain source-specific knowledge."
    data_raw_dir: Path = Path("./data/raw")
    data_processed_dir: Path = Path("./data/processed")

    request_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
