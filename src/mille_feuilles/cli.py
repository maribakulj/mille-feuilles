"""Command-line entrypoint. No downloads or model inference during generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import build_dataset, compare_lots
from .render import Config
from .validation import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mille-feuilles")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Produire et vérifier un lot autonome")
    generate.add_argument("--output", required=True, type=Path)
    generate.add_argument("--pages", type=int, default=1)
    generate.add_argument("--seed", type=int, default=20261007)
    generate.add_argument("--width", type=int, default=2680)
    generate.add_argument("--height", type=int, default=3698)
    generate.add_argument("--dpi", type=int, default=150)
    generate.add_argument("--columns", type=int, choices=[4, 5, 6])
    generate.add_argument(
        "--degradation", choices=["clean", "aged", "faint", "mixed"], default="mixed"
    )
    generate.add_argument("--jobs", type=int, default=1)
    generate.add_argument(
        "--assets-root",
        type=Path,
        help="Bundle vérifié contenant assets/catalog.json (actifs embarqués par défaut)",
    )
    validate = commands.add_parser("validate", help="Vérifier empreintes, annotations et exports")
    validate.add_argument("dataset", type=Path)
    compare = commands.add_parser("compare", help="Comparer bit à bit deux générations complètes")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            config = Config(
                width=args.width,
                height=args.height,
                dpi=args.dpi,
                columns=args.columns,
                degradation=args.degradation,
                seed=args.seed,
            )
            result = build_dataset(
                args.output,
                config,
                args.pages,
                args.jobs,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
                asset_source=args.assets_root,
            )
        elif args.command == "validate":
            result = validate_dataset(args.dataset)
        else:
            result = compare_lots(args.first, args.second)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
