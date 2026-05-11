from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import load_settings
from backend.app.integrations.rag_server.cli_gateway import RagServerCliGateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Proxy ingestion to sibling RAG-SERVER.")
    parser.add_argument("--path", "-p", required=True)
    parser.add_argument("--collection", "-c", default=None)
    parser.add_argument("--config", default="config/settings.test.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.config)
    result = RagServerCliGateway(settings).ingest(
        args.path,
        collection=args.collection,
        dry_run=args.dry_run,
    )
    print(
        {
            "status": result.status,
            "return_code": result.return_code,
            "error_code": result.error_code,
            "error_message": result.error_message,
        }
    )
    return 0 if result.status == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
