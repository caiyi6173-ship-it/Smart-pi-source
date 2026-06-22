import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.ingest.service import IngestService
from app.retrieval.embeddings import EmbeddingClient
from app.retrieval.vector_store import create_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Index documents into SmartTCM RAG.")
    parser.add_argument("path", help="File or directory to ingest")
    parser.add_argument("--source-type", default="mixed")
    parser.add_argument("--tag", action="append", default=[])
    args = parser.parse_args()

    settings = get_settings()
    embeddings = EmbeddingClient(settings)
    store = create_vector_store(settings)
    service = IngestService(settings, embeddings, store)

    for result in service.ingest_path(Path(args.path), args.source_type, args.tag):
        print(result.model_dump_json(ensure_ascii=False))


if __name__ == "__main__":
    main()
