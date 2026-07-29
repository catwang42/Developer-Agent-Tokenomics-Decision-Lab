"""CLI entry point: ``python -m harness.aggregate <results_dir>``."""

from .aggregate import main

if __name__ == "__main__":
    raise SystemExit(main())
