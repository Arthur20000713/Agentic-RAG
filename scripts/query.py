from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import load_settings
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.model.answer_generator import AnswerGenerator


def main() -> int:
    parser = argparse.ArgumentParser(description="Query livestock RAG adapter.")
    parser.add_argument("--query", "-q", required=True)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--config", default="config/settings.test.yaml")
    args = parser.parse_args()

    settings = load_settings(args.config)
    client = create_rag_server_client(settings)
    result = asyncio.run(client.query(args.query, top_k=args.top_k))
    print(AnswerGenerator().compose_with_citations(result))
    return 0 if result.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
