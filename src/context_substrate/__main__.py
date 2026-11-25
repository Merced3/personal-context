"""CLI entry point: python -m context_substrate."""

from __future__ import annotations

from context_substrate.runtime import run_service


def main() -> None:
    run_service()


if __name__ == "__main__":
    main()
