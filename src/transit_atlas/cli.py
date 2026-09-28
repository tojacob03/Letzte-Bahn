"""Command line interface: ``atlas run --config config/saarland.yaml [--steps ...]``."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from pathlib import Path

from . import download, export, prepare, routing, warehouse
from .config import Config, Paths, load_config

log = logging.getLogger("transit_atlas")


def _download(config: Config, paths: Paths, args: argparse.Namespace) -> None:
    download.download_all(config, paths.raw, force=args.force_download)


def _stage(function: Callable[[Config, Paths], object]) -> Callable:
    return lambda config, paths, _args: function(config, paths)


STEPS: dict[str, Callable[[Config, Paths, argparse.Namespace], object]] = {
    "download": _download,
    "prepare": _stage(prepare.run),
    "route": _stage(routing.run),
    "transform": _stage(warehouse.run),
    "export": _stage(export.run),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas", description="Public transport accessibility atlas pipeline"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run one or more pipeline steps")
    run.add_argument("--config", required=True, type=Path, help="YAML file, e.g. config/saarland.yaml")
    run.add_argument(
        "--steps",
        default=",".join(STEPS),
        help=f"comma-separated subset of: {', '.join(STEPS)} (default: all)",
    )
    run.add_argument("--root", type=Path, default=None, help="repository root (auto-detected)")
    run.add_argument("--force-download", action="store_true", help="download sources again")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    steps = [step.strip() for step in args.steps.split(",") if step.strip()]
    unknown = sorted(set(steps) - set(STEPS))
    if unknown:
        raise SystemExit(f"Unknown steps: {', '.join(unknown)}")
    config = load_config(args.config)
    paths = (Paths(args.root.resolve()) if args.root else Paths()).ensure()
    for name, step in STEPS.items():
        if name not in steps:
            continue
        started = time.monotonic()
        log.info("=== %s ===", name)
        step(config, paths, args)
        log.info("=== %s finished in %.1f min ===", name, (time.monotonic() - started) / 60)
    return 0
