"""Generate the synthetic dataset and load it into DATABASE_URL.

uv run python -m eaa.synthetic --scale small --seed 42
uv run python -m eaa.synthetic --dry-run          # generate and count, load nothing
uv run python -m eaa.synthetic --replace          # destructive: overwrites the dataset
"""

import argparse
import sys
import time
from typing import get_args

import psycopg

from eaa.config import get_settings
from eaa.synthetic.generator import ScaleName, generate
from eaa.synthetic.loader import DatasetAlreadyLoadedError, load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaa.synthetic", description=__doc__)
    parser.add_argument("--scale", choices=get_args(ScaleName), default="small")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="generate only, load nothing")
    parser.add_argument(
        "--replace", action="store_true", help="empty the sales tables first (destructive)"
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    dataset = generate(seed=args.seed, scale=args.scale)
    print(f"Generated scale={args.scale} seed={args.seed} in {time.perf_counter() - started:.1f} s")
    for table in dataset.tables.values():
        print(f"  {table.name:<22} {len(table.rows):>9,} rows")
    print(f"  digest {dataset.digest()[:16]}")
    if args.dry_run:
        return 0

    started = time.perf_counter()
    with psycopg.connect(get_settings().require_database_url()) as connection:
        try:
            load(connection, dataset, replace=args.replace)
        except DatasetAlreadyLoadedError as error:
            print(f"Not loaded: {error}", file=sys.stderr)
            return 1
    print(f"Loaded in {time.perf_counter() - started:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
