"""Command-line entrypoint. No downloads or model inference during generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import build_dataset, compare_lots
from .render import Config, PROFILE_LAYOUT
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
        "--layout-profile", choices=[PROFILE_LAYOUT],
        help="Mise en page par zones ; exige --degradation-profile (identity accepté)",
    )
    degradation_options = generate.add_mutually_exclusive_group()
    degradation_options.add_argument(
        "--degradation", choices=["clean", "aged", "faint", "mixed"], default="mixed"
    )
    generate.add_argument("--jobs", type=int, default=1)
    generate.add_argument("--partition", help="Partition à utiliser depuis le bundle vérifié")
    degradation_options.add_argument(
        "--degradation-profile",
        help="Profil JSON ou nom livré (identity, controlled-v1) de dégradations mesurées",
    )
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
    importer = commands.add_parser("import-texts", help="Importer des documents locaux vérifiés")
    importer.add_argument("--manifest", required=True, type=Path, help="Manifeste JSONL des documents")
    importer.add_argument("--into", required=True, type=Path, help="Bundle de destination neuf ou vide")
    importer.add_argument("--exclude-documents", type=Path)
    importer.add_argument("--exclude-ngrams", type=Path)
    partition = commands.add_parser("partition", help="Répartir les groupes sources avant composition")
    partition.add_argument("--bundle", required=True, type=Path)
    partition.add_argument("--ratios", nargs=3, type=float, metavar=("TRAIN", "DEV", "TEST"),
                           default=[0.8, 0.1, 0.1])
    partition.add_argument("--seed", type=int, default=20261007)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            profile = None
            if args.degradation_profile is not None:
                from .degrade import load_profile

                profile = load_profile(args.degradation_profile)
            config = Config(
                width=args.width,
                height=args.height,
                dpi=args.dpi,
                columns=args.columns,
                degradation=args.degradation,
                seed=args.seed,
                partition=args.partition,
                degradation_profile=profile,
                layout_profile=args.layout_profile,
            )
            config.validate()
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
        elif args.command == "compare":
            result = compare_lots(args.first, args.second)
        elif args.command == "import-texts":
            from .catalog import import_texts

            result = import_texts(args.manifest, args.into, exclusions={
                "documents": args.exclude_documents, "ngrams": args.exclude_ngrams,
            })
        else:
            from .partition import assign_partitions

            plan = assign_partitions(
                args.bundle, dict(zip(("train", "dev", "test"), args.ratios)), args.seed
            )
            result = {"status": "pass", "path": str(args.bundle / "assets/partition.json"), "plan": plan}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
