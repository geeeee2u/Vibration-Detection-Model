"""Import Case1 Excel data into PostgreSQL and publish the first analysis run."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.analysis_service import rerun_analysis_from_repository
from backend.database import DatabaseRepository
from case1_vibration_isolation_forest import load_case1


def bootstrap_postgres(
    input_path: str | Path,
    database_url: str,
    source_case: str = "Case1",
) -> dict[str, int]:
    """Idempotently import Case1 data and publish a PostgreSQL-backed analysis run."""
    repository = DatabaseRepository(database_url)
    repository.create_schema()
    source = load_case1(input_path)
    imported_rows = repository.import_raw_data(source, source_case)
    settings = repository.load_settings()
    result = rerun_analysis_from_repository(settings, repository, source_case)
    raw_rows = len(repository.load_raw_data(source_case))
    return {
        "imported_rows": imported_rows,
        "raw_rows": raw_rows,
        "analysis_rows": len(result),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Case1 vibration data into PostgreSQL")
    parser.add_argument("--input", required=True, help="Path to AI Model Raw Data.xlsx")
    parser.add_argument("--source-case", default="Case1", help="Source case name to import")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL environment variable is required")

    counts = bootstrap_postgres(args.input, database_url, args.source_case)
    print(
        "Bootstrap complete: "
        f"imported_rows={counts['imported_rows']}, "
        f"raw_rows={counts['raw_rows']}, "
        f"analysis_rows={counts['analysis_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
