import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.ingest.service import IngestService
from app.retrieval.embeddings import EmbeddingClient
from app.retrieval.vector_store import create_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild SmartTCM RAG index from a directory.")
    parser.add_argument("--path", default="data/raw")
    parser.add_argument("--source-type", default="mixed")
    args = parser.parse_args()

    settings = get_settings()
    embeddings = EmbeddingClient(settings)
    store = create_vector_store(settings)
    service = IngestService(settings, embeddings, store)
    for result in service.ingest_path(Path(args.path), args.source_type, []):
        print(result.model_dump_json(ensure_ascii=False))


if __name__ == "__main__":
    main()
