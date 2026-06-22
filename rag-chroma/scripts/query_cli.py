import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Query SmartTCM RAG API.")
    parser.add_argument("question")
    parser.add_argument("--url", default="http://127.0.0.1:8094")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--include-chunks", action="store_true")
    args = parser.parse_args()

    response = httpx.post(
        f"{args.url.rstrip('/')}/api/v1/query",
        json={
            "question": args.question,
            "top_k": args.top_k,
            "include_chunks": args.include_chunks,
        },
        timeout=120,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
